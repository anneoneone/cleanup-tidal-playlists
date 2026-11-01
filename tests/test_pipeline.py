from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

import cratekeeper.pipeline as pipeline
from cratekeeper.app import App
from cratekeeper.backups import list_backups
from cratekeeper.db import Playlist, Run
from cratekeeper.db import repository as repo
from cratekeeper.db.models import RunKind
from cratekeeper.jobs import JobContext, JobRunner, JobStatus, held_lock
from cratekeeper.pipeline import SyncOptions, apply, default_groups, restore, sync
from cratekeeper.rekordbox.connection import open_library
from cratekeeper.tidal.client import TidalPlaylist, TidalTrack, TrackListing


class FakeTidal:
    def __init__(self, playlists: dict[str, list[TidalTrack]]) -> None:
        self.data = playlists

    def playlists(self) -> list[TidalPlaylist]:
        return [
            TidalPlaylist(id=name, name=name, last_updated=datetime(2026, 1, 1))
            for name in self.data
        ]

    def playlist_tracks(self, playlist_id: str) -> TrackListing:
        tracks = self.data[playlist_id]
        return TrackListing(tracks=tracks, expected_count=len(tracks))


@pytest.fixture
def app(
    tmp_path: Path, rekordbox_library: Path, monkeypatch: pytest.MonkeyPatch
) -> App:
    music = tmp_path / "music"
    (music / "Playlists").mkdir(parents=True)
    home = Path(str(tmp_path / "cratekeeper-home"))
    home.mkdir()
    (home / "config.toml").write_text(
        f'music_folder = "{music}"\nrekordbox_db = "{rekordbox_library}"\n'
    )
    application = App.open()
    monkeypatch.setattr(application.auth, "session", lambda: object())
    monkeypatch.setattr(application.auth, "persist", lambda: None)
    return application


def run_job(app: App, fn: Any) -> Any:
    job = JobRunner().run("test", fn)
    assert job.status is JobStatus.SUCCEEDED, job.error
    return job.result


def test_full_sync_then_apply_then_restore(
    app: App, make_mp3: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracks = [TidalTrack(id="1", title="Tune", artist="Main", isrc="I1")]
    monkeypatch.setattr(
        pipeline, "TidalClient", lambda s: FakeTidal({"Peak 🏢": tracks})
    )
    make_mp3(app.settings.music_folder / "Playlists" / "Peak 🏢" / "x.mp3", isrc="I1")

    outcome = run_job(app, lambda ctx: sync(app, ctx, SyncOptions(download=False)))

    assert outcome.summary["tidal"]["playlists_created"] == 1
    assert outcome.summary["music"]["linked_to_tidal"] == 1
    assert sorted(default_groups(outcome.plan)) == ["playlist:1"]
    with app.db.session() as s:
        run = repo.get_run(s, outcome.run_id)
        assert run is not None and run.status == "succeeded" and run.plan

    applied = run_job(app, lambda ctx: apply(app, ctx, outcome.run_id))
    assert applied.result.applied == 1
    assert applied.backup.kind == "full"
    rb = open_library(app.rekordbox().db_path)
    try:
        assert rb.get_playlist(Name="Peak", Attribute=0).count() == 1
    finally:
        rb.close()

    again = run_job(app, lambda ctx: sync(app, ctx, SyncOptions(offline=True)))
    assert again.plan.is_empty

    first_refresh = [b for b in list_backups(app.home) if b.kind == "db"][-1]
    run_job(app, lambda ctx: restore(app, ctx, first_refresh.id))
    with app.db.session() as s:
        assert repo.library_counts(s)["playlists"] == 0
        # The Backup was taken while the first sync was running.
        first = repo.get_run(s, outcome.run_id)
        assert first is not None and first.status == "failed"
        assert first.error == "Not finished when the restored Backup was taken"


def test_failed_sync_is_recorded(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(session: Any) -> Any:
        raise RuntimeError("Tidal is down")

    monkeypatch.setattr(pipeline, "TidalClient", broken)
    job = JobRunner().run("sync", lambda ctx: sync(app, ctx, SyncOptions()))
    assert job.status is JobStatus.FAILED
    with app.db.session() as s:
        run = repo.latest_run(s)
        assert run is not None
        assert (run.status, run.error) == ("failed", "Tidal is down")


def test_apply_needs_a_plan(app: App) -> None:
    with app.db.session() as s:
        run_id = repo.start_run(s, pipeline.RunKind.SYNC).id
    job = JobRunner().run("apply", lambda ctx: apply(app, ctx, run_id))
    assert job.status is JobStatus.FAILED
    assert "has no plan" in (job.error or "")


def test_offline_sync_skips_tidal_and_downloads(
    app: App, monkeypatch: pytest.MonkeyPatch, make_mp3: Any
) -> None:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("must not be called offline")

    monkeypatch.setattr(pipeline, "TidalClient", fail)
    monkeypatch.setattr(pipeline, "_download", fail)
    make_mp3(app.settings.music_folder / "Playlists" / "Local Set 🎉" / "A - B.mp3")

    def run_sync(ctx: JobContext) -> Any:
        return sync(app, ctx, SyncOptions(offline=True))

    outcome = run_job(app, run_sync)

    assert "tidal" not in outcome.summary and "download" not in outcome.summary
    assert [g.title for g in outcome.plan.groups] == ["Local Set 🎉"]
    with app.db.session() as s:
        assert s.query(Playlist).one().tidal_id is None
        assert s.query(Run).count() == 1


def test_open_keeps_runs_of_a_job_in_another_process(app: App) -> None:
    with app.db.session() as s:
        run_id = repo.start_run(s, RunKind.SYNC).id

    with held_lock(app.home.lock_file):  # the UI server runs a sync
        App.open().close()
        with app.db.session() as s:
            run = repo.get_run(s, run_id)
            assert run is not None and run.status == "running"

    App.open().close()  # no job holds the lock: the run is stale
    with app.db.session() as s:
        run = repo.get_run(s, run_id)
        assert run is not None and run.status == "failed"
