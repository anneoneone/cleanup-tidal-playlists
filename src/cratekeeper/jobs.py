"""Background jobs with live progress events.

One job runs at a time per home directory. A job is a function that receives a
:class:`JobContext` and reports steps, progress and log lines through it. The UI
reads the events over SSE; the CLI renders them in the terminal.
"""

from __future__ import annotations

import fcntl
import logging
import os
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import IO, Any, Optional

logger = logging.getLogger(__name__)

MAX_EVENTS = 5000
PROGRESS_INTERVAL = 0.1  # seconds between progress events of one step


class JobBusyError(RuntimeError):
    """Raised when a job is already running in this process or another one."""


class JobCancelled(Exception):
    """Raised inside a job when the user cancelled it."""


class JobStatus(str, Enum):
    """Lifecycle of a job."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class JobEvent:
    """One event of a job.

    ``seq`` increases by one per event.
    """

    seq: int
    job_id: str
    kind: str  # started | step | progress | log | finished | failed | cancelled
    message: str = ""
    step: Optional[str] = None
    current: Optional[int] = None
    total: Optional[int] = None
    level: Optional[str] = None
    time: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Return the event as plain data."""
        return asdict(self)


Subscriber = Callable[[JobEvent], None]


class Job:
    """State and event history of one job."""

    def __init__(self, kind: str, label: str = "") -> None:
        """Create a job that has not started yet."""
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.label = label
        self.status = JobStatus.RUNNING
        self.result: Any = None
        self.error: Optional[str] = None
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self.step: Optional[str] = None
        self.cancel_event = threading.Event()
        self._events: deque[JobEvent] = deque(maxlen=MAX_EVENTS)
        self._seq = 0
        self._lock = threading.Lock()
        self._subscribers: list[Subscriber] = []
        self._done = threading.Event()

    def emit(self, kind: str, message: str = "", **fields: Any) -> JobEvent:
        """Record an event and hand it to all subscribers."""
        with self._lock:
            self._seq += 1
            event = JobEvent(
                seq=self._seq, job_id=self.id, kind=kind, message=message, **fields
            )
            self._events.append(event)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber(event)
            except Exception:  # a broken listener must not break the job
                logger.debug("Job event subscriber failed", exc_info=True)
        return event

    def subscribe(
        self, subscriber: Subscriber, after_seq: int = 0
    ) -> tuple[list[JobEvent], Callable[[], None]]:
        """Register a listener.

        Returns the events after ``after_seq`` that happened before the call, and a
        function that removes the listener. No event is lost or repeated.
        """
        with self._lock:
            backlog = [e for e in self._events if e.seq > after_seq]
            self._subscribers.append(subscriber)

        def unsubscribe() -> None:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

        return backlog, unsubscribe

    def events(self, after_seq: int = 0) -> list[JobEvent]:
        """Return recorded events after ``after_seq``."""
        with self._lock:
            return [e for e in self._events if e.seq > after_seq]

    @property
    def done(self) -> bool:
        """Return whether the job has finished."""
        return self._done.is_set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until the job finishes.

        Returns False on timeout.
        """
        return self._done.wait(timeout)

    def snapshot(self) -> dict[str, Any]:
        """Return the job state as plain data."""
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status.value,
            "step": self.step,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "last_seq": self._seq,
        }

    def _finish(self, status: JobStatus, message: str) -> None:
        self.status = status
        self.finished_at = time.time()
        kind = {
            JobStatus.SUCCEEDED: "finished",
            JobStatus.FAILED: "failed",
            JobStatus.CANCELLED: "cancelled",
        }[status]
        self.emit(kind, message)
        self._done.set()


class JobContext:
    """What a running job uses to report progress and check for cancellation."""

    def __init__(self, job: Job) -> None:
        """Wrap ``job``."""
        self.job = job
        self._last_progress = 0.0

    def step(self, name: str, message: str = "") -> None:
        """Begin a named step such as "Refresh Tidal"."""
        self.check_cancelled()
        self.job.step = name
        self._last_progress = 0.0
        self.job.emit("step", message or name, step=name)

    def progress(
        self, current: int, total: Optional[int] = None, message: str = ""
    ) -> None:
        """Report progress in the current step.

        Throttled, except for the last item.
        """
        now = time.monotonic()
        last_item = total is not None and current >= total
        if not last_item and now - self._last_progress < PROGRESS_INTERVAL:
            return
        self._last_progress = now
        self.job.emit(
            "progress", message, step=self.job.step, current=current, total=total
        )

    def log(self, message: str, level: str = "info") -> None:
        """Add a log line to the job."""
        self.job.emit("log", message, step=self.job.step, level=level)

    @property
    def cancelled(self) -> bool:
        """Return whether the user asked to cancel."""
        return self.job.cancel_event.is_set()

    @property
    def abort_event(self) -> threading.Event:
        """Return the event that is set on cancel (for libraries that poll one)."""
        return self.job.cancel_event

    def check_cancelled(self) -> None:
        """Raise :class:`JobCancelled` if the user asked to cancel."""
        if self.cancelled:
            raise JobCancelled()


JobFunction = Callable[[JobContext], Any]

_local = threading.local()


def current_context() -> Optional[JobContext]:
    """Return the job context running in this thread, if any."""
    return getattr(_local, "context", None)


class ProcessLock:
    """Exclusive lock file, so CLI and UI never run jobs at the same time."""

    def __init__(self, path: Path) -> None:
        """Use ``path`` as the lock file."""
        self.path = path
        self._handle: Optional[IO[str]] = None

    def acquire(self) -> None:
        """Take the lock or raise :class:`JobBusyError`."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+", encoding="utf-8")  # noqa: SIM115
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip() or "another process"
            handle.close()
            raise JobBusyError(
                f"Another Cratekeeper job is running (pid {owner})"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle

    def release(self) -> None:
        """Release the lock."""
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None


class JobRunner:
    """Runs one job at a time and keeps recent jobs for lookup."""

    def __init__(self, lock_path: Optional[Path] = None, keep: int = 20) -> None:
        """Create a runner.

        ``lock_path`` enables the cross-process lock.
        """
        self._lock_path = lock_path
        self._keep = keep
        self._mutex = threading.Lock()
        self._current: Optional[Job] = None
        self._jobs: deque[Job] = deque(maxlen=keep)
        self._threads: dict[str, threading.Thread] = {}

    def start(self, kind: str, fn: JobFunction, *, label: str = "") -> Job:
        """Run ``fn`` in a background thread.

        Raises :class:`JobBusyError`.
        """
        job, process_lock = self._claim(kind, label)
        thread = threading.Thread(
            target=self._execute,
            args=(job, fn, process_lock),
            name=f"cratekeeper-job-{job.id}",
            daemon=True,
        )
        self._threads[job.id] = thread
        thread.start()
        return job

    def run(
        self,
        kind: str,
        fn: JobFunction,
        *,
        label: str = "",
        subscriber: Optional[Subscriber] = None,
    ) -> Job:
        """Run ``fn`` in the calling thread (CLI).

        Events go to ``subscriber``.
        """
        job, process_lock = self._claim(kind, label)
        if subscriber is not None:
            job.subscribe(subscriber)
        self._execute(job, fn, process_lock)
        return job

    def current(self) -> Optional[Job]:
        """Return the running job, if any."""
        with self._mutex:
            return self._current

    def get(self, job_id: str) -> Optional[Job]:
        """Return a recent job by ID."""
        with self._mutex:
            return next((j for j in self._jobs if j.id == job_id), None)

    def cancel(self, job_id: str) -> bool:
        """Ask a running job to stop.

        Returns False if it is not running.
        """
        job = self.get(job_id)
        if job is None or job.done:
            return False
        job.cancel_event.set()
        job.emit("log", "Cancel requested", level="warning")
        return True

    def shutdown(self, timeout: Optional[float] = None) -> bool:
        """Wait for the running job to finish.

        Returns False on timeout.
        """
        job = self.current()
        return job.wait(timeout) if job is not None else True

    def _claim(self, kind: str, label: str) -> tuple[Job, Optional[ProcessLock]]:
        with self._mutex:
            running = self._current
            if running is not None and not running.done:
                name = running.label or running.kind
                raise JobBusyError(f"A job is already running: {name}")
            process_lock = ProcessLock(self._lock_path) if self._lock_path else None
            if process_lock is not None:
                process_lock.acquire()
            job = Job(kind, label)
            self._current = job
            self._jobs.append(job)
            return job, process_lock

    def _execute(
        self, job: Job, fn: JobFunction, process_lock: Optional[ProcessLock]
    ) -> None:
        context = JobContext(job)
        _local.context = context
        job.emit("started", job.label or job.kind)
        try:
            job.result = fn(context)
        except JobCancelled:
            job._finish(JobStatus.CANCELLED, "Cancelled")
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job.id, job.kind)
            job.error = str(exc) or exc.__class__.__name__
            job._finish(JobStatus.FAILED, job.error)
        else:
            job._finish(JobStatus.SUCCEEDED, "Done")
        finally:
            _local.context = None
            if process_lock is not None:
                process_lock.release()
            self._threads.pop(job.id, None)


@contextmanager
def held_lock(lock_path: Path) -> Iterator[None]:
    """Hold the cross-process lock for a block of work outside the runner."""
    lock = ProcessLock(lock_path)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
