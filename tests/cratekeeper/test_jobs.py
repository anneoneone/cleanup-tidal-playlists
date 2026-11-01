import logging
import threading
from pathlib import Path

import pytest

from cratekeeper.jobs import (
    JobBusyError,
    JobContext,
    JobEvent,
    JobRunner,
    JobStatus,
    current_context,
)
from cratekeeper.log import setup_logging


def kinds(events: list[JobEvent]) -> list[str]:
    return [e.kind for e in events]


def test_successful_job_reports_steps_and_result(tmp_path: Path) -> None:
    def work(ctx: JobContext) -> str:
        ctx.step("Refresh Tidal")
        ctx.progress(1, 2, "one")
        ctx.progress(2, 2, "two")
        ctx.log("hello")
        return "ok"

    runner = JobRunner(lock_path=tmp_path / "lock")
    job = runner.start("sync", work, label="Sync")
    assert job.wait(5)
    assert job.status is JobStatus.SUCCEEDED
    assert job.result == "ok"
    events = job.events()
    assert kinds(events)[0] == "started"
    assert kinds(events)[-1] == "finished"
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert events[-2].kind == "log" and events[-2].step == "Refresh Tidal"
    last_progress = [e for e in events if e.kind == "progress"][-1]
    assert (last_progress.current, last_progress.total) == (2, 2)


def test_failed_job_keeps_error() -> None:
    def work(ctx: JobContext) -> None:
        raise ValueError("bad input")

    job = JobRunner().run("sync", work)
    assert job.status is JobStatus.FAILED
    assert job.error == "bad input"
    assert job.events()[-1].kind == "failed"


def test_cancel_stops_job_at_next_check() -> None:
    started = threading.Event()

    def work(ctx: JobContext) -> None:
        started.set()
        assert ctx.abort_event.wait(5)
        ctx.check_cancelled()

    runner = JobRunner()
    job = runner.start("sync", work)
    assert started.wait(5)
    assert runner.cancel(job.id)
    assert job.wait(5)
    assert job.status is JobStatus.CANCELLED
    assert runner.cancel(job.id) is False


def test_second_job_is_refused_while_one_runs() -> None:
    release = threading.Event()
    runner = JobRunner()
    job = runner.start("sync", lambda ctx: release.wait(5))
    with pytest.raises(JobBusyError):
        runner.start("apply", lambda ctx: None)
    release.set()
    assert job.wait(5)
    assert runner.run("apply", lambda ctx: 1).result == 1


def test_lock_file_blocks_other_runner(tmp_path: Path) -> None:
    release = threading.Event()
    lock = tmp_path / "cratekeeper.lock"
    first = JobRunner(lock_path=lock)
    job = first.start("sync", lambda ctx: release.wait(5))
    with pytest.raises(JobBusyError, match="Another Cratekeeper job"):
        JobRunner(lock_path=lock).run("sync", lambda ctx: None)
    release.set()
    assert job.wait(5)
    assert JobRunner(lock_path=lock).run("sync", lambda ctx: 2).result == 2


def test_subscribe_gets_backlog_then_live_events_without_gaps() -> None:
    gate = threading.Event()
    runner = JobRunner()

    def work(ctx: JobContext) -> None:
        ctx.log("before")
        gate.wait(5)
        ctx.log("after")

    job = runner.start("sync", work)
    live: list[JobEvent] = []
    while not job.events():
        pass
    backlog, unsubscribe = job.subscribe(live.append)
    gate.set()
    assert job.wait(5)
    unsubscribe()
    seqs = [e.seq for e in backlog + live]
    assert seqs == list(range(1, len(seqs) + 1))
    assert "after" in [e.message for e in live]


def test_context_is_visible_in_job_thread_and_logs_are_forwarded() -> None:
    setup_logging("INFO", console=False)
    seen = []

    def work(ctx: JobContext) -> None:
        seen.append(current_context() is ctx)
        logging.getLogger("cratekeeper.test").info("from logger")

    job = JobRunner().run("sync", work)
    assert seen == [True]
    assert current_context() is None
    assert any(e.kind == "log" and e.message == "from logger" for e in job.events())


def test_runner_lookup_and_shutdown() -> None:
    runner = JobRunner()
    job = runner.run("sync", lambda ctx: None)
    assert runner.get(job.id) is job
    assert runner.get("missing") is None
    assert runner.current() is job
    assert runner.shutdown(1)
    assert job.snapshot()["status"] == "succeeded"
