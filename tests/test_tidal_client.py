import json
import stat
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cratekeeper.tidal.auth import TidalAuth, TidalAuthError
from cratekeeper.tidal.client import TidalClient, naive_utc, to_playlist, to_track


def raw_track(**kw: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "id": 11,
        "name": "Tune",
        "full_name": "Tune (Dub)",
        "version": "Dub",
        "artist": SimpleNamespace(name="Main"),
        "album": SimpleNamespace(
            id="ab-cd",
            name="LP",
            artist=SimpleNamespace(name="Main"),
            universal_product_number="0123",
            release_date=datetime(2020, 1, 2),
        ),
        "duration": 300,
        "track_num": 3,
        "volume_num": 1,
        "explicit": False,
        "isrc": "usabc",
        "tidal_release_date": datetime(2020, 1, 2, tzinfo=timezone.utc),
        "audio_quality": "LOSSLESS",
        "audio_modes": ["STEREO"],
        "user_date_added": datetime(2025, 3, 4, 10, 0, tzinfo=timezone.utc),
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_to_track_converts_all_fields() -> None:
    t = to_track(raw_track())
    assert (t.id, t.title, t.artist, t.version, t.isrc) == (
        "11",
        "Tune",
        "Main",
        "Dub",
        "USABC",
    )
    assert (t.track_number, t.volume_number, t.album_upc) == (3, 1, "0123")
    assert t.album_cover_url == "https://resources.tidal.com/images/ab/cd/640x640.jpg"
    assert t.date_added == datetime(2025, 3, 4, 10, 0)
    assert t.release_date == datetime(2020, 1, 2)


def test_to_playlist_and_naive_utc() -> None:
    raw = SimpleNamespace(
        id="uuid",
        name="House",
        description=None,
        last_updated=datetime(2026, 1, 1, tzinfo=timezone.utc),
        num_tracks=2,
        creator=SimpleNamespace(id=7, name="me"),
        picture="aa-bb",
    )
    p = to_playlist(raw)
    assert (p.id, p.name, p.num_tracks, p.creator_id) == ("uuid", "House", 2, "7")
    assert p.picture_url == "https://resources.tidal.com/images/aa/bb/750x500.jpg"
    assert naive_utc("nope") is None


def test_client_uses_pagination_and_reports_count() -> None:
    playlist = SimpleNamespace(
        get_tracks_count=lambda: 3,
        tracks_paginated=lambda: [raw_track(id=1), raw_track(id=2)],
    )
    session = SimpleNamespace(
        playlist=lambda pid: playlist,
        user=SimpleNamespace(playlists=lambda: [SimpleNamespace(id="x", name="X")]),
    )
    client = TidalClient(session)
    listing = client.playlist_tracks("x")
    assert [t.id for t in listing.tracks] == ["1", "2"]
    assert listing.complete is False
    assert [p.name for p in client.playlists()] == ["X"]


class FakeSession:
    valid = True

    def __init__(self) -> None:
        self.token_type = "Bearer"
        self.access_token = "a1"
        self.refresh_token = "r1"
        self.expiry_time = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.future: Future[None] = Future()

    def load_oauth_session(self, token_type, access, refresh=None, expiry=None):
        self.access_token, self.refresh_token = access, refresh

    def check_login(self) -> bool:
        return self.valid

    def login_oauth(self):
        link = SimpleNamespace(
            verification_uri_complete="link.tidal.com/ABCDE",
            user_code="ABCDE",
            expires_in=300,
        )
        return link, self.future


def test_session_requires_stored_login(tmp_path: Path) -> None:
    auth = TidalAuth(tmp_path / "s.json", FakeSession)
    with pytest.raises(TidalAuthError, match="Not logged in"):
        auth.session()


def test_invalid_login_keeps_file(tmp_path: Path) -> None:
    file = tmp_path / "s.json"
    file.write_text(json.dumps({"access_token": "a", "refresh_token": "r"}))

    class Expired(FakeSession):
        valid = False

    with pytest.raises(TidalAuthError, match="no longer valid"):
        TidalAuth(file, Expired).session()
    assert file.exists()


def test_login_flow_writes_private_file_and_persists_refresh(tmp_path: Path) -> None:
    sessions: list[FakeSession] = []

    def factory() -> FakeSession:
        sessions.append(FakeSession())
        return sessions[-1]

    file = tmp_path / "s.json"
    auth = TidalAuth(file, factory)
    start = auth.start_login()
    assert start.url == "https://link.tidal.com/ABCDE"
    assert auth.login_state() == ("pending", None)

    sessions[0].future.set_result(None)

    assert auth.wait_for_login(1) == "done"
    assert json.loads(file.read_text())["access_token"] == "a1"
    assert stat.S_IMODE(file.stat().st_mode) == 0o600
    session = auth.session()
    session.access_token = "a2"
    auth.persist()
    assert json.loads(file.read_text())["access_token"] == "a2"


def test_failed_login_reports_error(tmp_path: Path) -> None:
    sessions: list[FakeSession] = []

    def factory() -> FakeSession:
        sessions.append(FakeSession())
        return sessions[-1]

    auth = TidalAuth(tmp_path / "s.json", factory)
    auth.start_login()
    sessions[0].future.set_exception(TimeoutError("expired"))
    assert auth.wait_for_login(1) == "failed"
    assert auth.login_state() == ("failed", "expired")
    assert not (tmp_path / "s.json").exists()
