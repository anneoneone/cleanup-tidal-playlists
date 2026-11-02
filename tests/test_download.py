import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from cratekeeper.db import Database, Playlist, PlaylistTrack, Track
from cratekeeper.download import runner as runner_module
from cratekeeper.download.candidates import find_candidates, folder_name
from cratekeeper.download.runner import ConversionError, run_downloads
from cratekeeper.download.tidal_dl import (
    DownloadError,
    TidalDownloader,
    TrackUnavailableError,
    downloader_available,
    resolve_downloaded_file,
)


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "ck.db")
    database.prepare()
    return database


@pytest.fixture
def music(tmp_path: Path) -> Path:
    folder = tmp_path / "music"
    folder.mkdir()
    return folder


@pytest.fixture
def fake_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An ffmpeg stand-in that copies the input file to the output path."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "ffmpeg"
    script.write_text(
        f"#!{sys.executable}\n"
        "import shutil, sys\n"
        "args = sys.argv[1:]\n"
        "shutil.copy(args[args.index('-i') + 1], args[-1])\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    return script


def seed(db: Database, music: Path) -> None:
    with db.session() as s:
        house = Playlist(name="House: Deep/Late 🌃", tidal_id="p1", in_tidal=True)
        other = Playlist(name="Other", tidal_id="p2", in_tidal=True)
        s.add_all([house, other])
        s.flush()
        tracks = [
            Track(tidal_id="1", title="Needs", artist="A", normalized_name="x"),
            Track(tidal_id="2", title="Has", artist="B", normalized_name="x"),
            Track(
                tidal_id="3",
                title="Gone",
                artist="C",
                normalized_name="x",
                tidal_unavailable=True,
            ),
            Track(tidal_id="4", title="Removed", artist="D", normalized_name="x"),
        ]
        s.add_all(tracks)
        s.flush()
        existing = music / "Playlists" / "Other" / "B - Has.mp3"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"x")
        tracks[1].file_paths = ["Playlists/Other/B - Has.mp3"]
        for playlist, track, in_tidal in [
            (house, tracks[0], True),
            (other, tracks[0], True),
            (house, tracks[1], True),
            (house, tracks[2], True),
            (house, tracks[3], False),
        ]:
            s.add(
                PlaylistTrack(
                    playlist_id=playlist.id, track_id=track.id, in_tidal=in_tidal
                )
            )


def test_folder_name_is_safe_and_keeps_emojis() -> None:
    assert folder_name("House: Deep/Late 🌃") == "House- Deep-Late 🌃"
    assert folder_name(" .. ") == "Playlist"


def test_candidates_skip_files_unavailable_and_removed(
    db: Database, music: Path
) -> None:
    seed(db, music)
    with db.session() as s:
        found = find_candidates(s, music)
    assert [(c.tidal_id, c.folder) for c in found] == [
        ("1", "Playlists/House- Deep-Late 🌃")
    ]
    with db.session() as s:
        assert find_candidates(s, music, playlist_name="other")[0].folder == (
            "Playlists/Other"
        )


class FakeDownloader:
    def __init__(self, extension: str = ".flac", fail: Exception | None = None):
        self.extension = extension
        self.fail = fail
        self.calls: list[str] = []

    def download(self, tidal_id: str, target_dir: Path) -> Path:
        self.calls.append(tidal_id)
        if self.fail:
            raise self.fail
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"Artist - Track {tidal_id}{self.extension}"
        path.write_bytes(b"audio")
        return path


def test_download_converts_and_records_file(
    db: Database, music: Path, fake_ffmpeg: Path
) -> None:
    seed(db, music)
    fake = FakeDownloader()

    stats = run_downloads(db, music, "mp3", 2, lambda: fake, check_installed=False)

    assert (stats.candidates, stats.downloaded, stats.failed) == (1, 1, 0)
    folder = music / "Playlists" / "House- Deep-Late 🌃"
    assert [p.name for p in folder.iterdir()] == ["Artist - Track 1.mp3"]
    with db.session() as s:
        track = s.query(Track).filter_by(tidal_id="1").one()
        assert track.file_paths == [
            "Playlists/House- Deep-Late 🌃/Artist - Track 1.mp3"
        ]
        assert track.download_status == "downloaded"
        house = s.query(Playlist).filter_by(tidal_id="p1").one()
        assert house.local_folder_path == "Playlists/House- Deep-Late 🌃"
    again = run_downloads(db, music, "mp3", 2, lambda: fake, check_installed=False)
    assert again.candidates == 0


def test_failures_are_recorded(db: Database, music: Path, fake_ffmpeg: Path) -> None:
    seed(db, music)
    stats = run_downloads(
        db,
        music,
        "mp3",
        2,
        lambda: FakeDownloader(fail=DownloadError("network")),
        check_installed=False,
    )
    assert (stats.failed, stats.errors) == (1, ["A - Needs: network"])
    with db.session() as s:
        track = s.query(Track).filter_by(tidal_id="1").one()
        assert (track.download_status, track.download_error) == ("error", "network")
        assert track.tidal_unavailable is False


def test_unavailable_track_is_flagged(
    db: Database, music: Path, fake_ffmpeg: Path
) -> None:
    seed(db, music)
    stats = run_downloads(
        db,
        music,
        "mp3",
        2,
        lambda: FakeDownloader(fail=TrackUnavailableError("404")),
        check_installed=False,
    )
    assert stats.unavailable == 1
    with db.session() as s:
        assert s.query(Track).filter_by(tidal_id="1").one().tidal_unavailable


def test_missing_downloader_skips_with_message(
    db: Database, music: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(db, music)
    monkeypatch.setattr(runner_module, "downloader_available", lambda: False)
    stats = run_downloads(db, music, "mp3", 2, lambda: FakeDownloader())
    assert stats.skipped and "tidal-dl-ng is not installed" in stats.skipped


def test_missing_ffmpeg_fails_loudly(
    db: Database, music: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seed(db, music)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(ConversionError, match="ffmpeg is not installed"):
        run_downloads(
            db, music, "mp3", 2, lambda: FakeDownloader(), check_installed=False
        )


def test_resolve_downloaded_file(tmp_path: Path) -> None:
    real = tmp_path / "A - B.m4a"
    real.write_bytes(b"x")
    assert resolve_downloaded_file(tmp_path / "A - B.flac") == real
    assert resolve_downloaded_file(tmp_path / "X - Y.flac") is None


@pytest.mark.skipif(not downloader_available(), reason="tidal-dl-ng not installed")
def test_tidal_dl_ng_uses_cratekeeper_config_dir(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tidalapi.session import Session

    def fake_load(self, token_type, access_token, refresh_token=None, expiry=None):
        self.token_type, self.access_token = token_type, access_token
        return True

    monkeypatch.setattr(Session, "load_oauth_session", fake_load)
    config_dir = tmp_path / "ck" / "tidal-dl-ng"
    session = SimpleNamespace(
        token_type="Bearer",
        access_token="token-a",
        refresh_token="token-r",
        expiry_time=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    downloader = TidalDownloader(config_dir, session, "LOSSLESS")
    assert (config_dir / "settings.json").is_file()
    assert not (isolated_home / ".config" / "tidal_dl_ng").exists()
    assert downloader._tidal.session.access_token == "token-a"
