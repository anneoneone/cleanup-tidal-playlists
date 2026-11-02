import subprocess  # noqa: S404 - only for CompletedProcess and TimeoutExpired
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import cratekeeper.api.picker as picker
from cratekeeper.api.app import create_app
from cratekeeper.app import App

HEADERS = {"X-Cratekeeper": "1"}
URL = "/api/settings/pick-path"


class FakeOsascript:
    """Stands in for ``subprocess.run``; records the command it got."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = ""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> Any:
        self.commands.append(command)
        assert kwargs["timeout"] == picker.TIMEOUT_SECONDS
        return subprocess.CompletedProcess(
            command, self.returncode, self.stdout, self.stderr
        )

    @property
    def script(self) -> str:
        args = self.commands[-1][1:-2]
        return "\n".join(a for a in args if a != "-e")

    @property
    def argv(self) -> list[str]:
        return self.commands[-1][-2:]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(App.open(), 8765, extra_hosts={"testserver"}))


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeOsascript:
    fake = FakeOsascript()
    monkeypatch.setattr(picker, "_osascript", lambda: "/usr/bin/osascript")
    monkeypatch.setattr(picker.subprocess, "run", fake)
    return fake


def test_folder_pick_returns_the_path(
    client: TestClient, fake: FakeOsascript, tmp_path: Path
) -> None:
    start = tmp_path / "Music Folder"
    start.mkdir()
    fake.stdout = "/Volumes/HDD1TB/Music/DJing/Tidal/mp3/\n"

    response = client.post(
        URL, json={"field": "music_folder", "start": str(start)}, headers=HEADERS
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"path": "/Volumes/HDD1TB/Music/DJing/Tidal/mp3"}
    assert "choose folder" in fake.script
    assert fake.argv == ["Choose the Music folder", str(start)]


def test_request_values_stay_out_of_the_script(
    client: TestClient, fake: FakeOsascript, tmp_path: Path
) -> None:
    tricky = tmp_path / 'a" & (do shell script "touch x") & "'
    tricky.mkdir()
    fake.stdout = "/Users/me/tag_mapping.json\n"

    response = client.post(
        URL, json={"field": "tag_mapping", "start": str(tricky)}, headers=HEADERS
    )

    assert response.json() == {"path": "/Users/me/tag_mapping.json"}
    assert "do shell script" not in fake.script
    assert 'of type {"json"}' in fake.script
    assert fake.argv[1] == str(tricky)


def test_start_folder_falls_back(
    client: TestClient,
    fake: FakeOsascript,
    tmp_path: Path,
    isolated_home: Path,
) -> None:
    master = tmp_path / "rekordbox" / "master.db"
    master.parent.mkdir()
    master.write_bytes(b"")
    fake.stdout = str(master)

    client.post(
        URL, json={"field": "rekordbox_db", "start": str(master)}, headers=HEADERS
    )
    assert fake.argv[1] == str(master.parent)

    client.post(URL, json={"field": "rekordbox_db", "start": None}, headers=HEADERS)
    assert fake.argv[1] == ""
    pioneer = isolated_home / "Library" / "Pioneer" / "rekordbox"
    pioneer.mkdir(parents=True)
    client.post(URL, json={"field": "rekordbox_db"}, headers=HEADERS)
    assert fake.argv[1] == str(pioneer)
    assert 'of type {"db"}' in fake.script

    for start in ("relative/path", str(tmp_path / "gone" / "x")):
        client.post(
            URL, json={"field": "bandcamp_folder", "start": start}, headers=HEADERS
        )
        assert fake.argv[1] == ""


def test_cancel_returns_null(client: TestClient, fake: FakeOsascript) -> None:
    fake.returncode = 1
    fake.stderr = "0:120: execution error: User canceled. (-128)\n"

    response = client.post(URL, json={"field": "music_folder"}, headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {"path": None}


def test_wrong_file_type_is_rejected(client: TestClient, fake: FakeOsascript) -> None:
    fake.stdout = "/Users/me/Library/Pioneer/rekordbox/masterPlaylists6.xml\n"

    response = client.post(URL, json={"field": "rekordbox_db"}, headers=HEADERS)

    assert response.status_code == 422
    assert response.json()["detail"] == "Choose a .db file, not masterPlaylists6.xml."


def test_relative_answer_is_rejected(client: TestClient, fake: FakeOsascript) -> None:
    fake.stdout = "\n"
    response = client.post(URL, json={"field": "music_folder"}, headers=HEADERS)
    assert response.status_code == 422


def test_dialog_errors_return_503(client: TestClient, fake: FakeOsascript) -> None:
    fake.returncode = 1
    fake.stderr = "execution error: No user interaction allowed. (-1713)"

    response = client.post(URL, json={"field": "music_folder"}, headers=HEADERS)

    assert response.status_code == 503
    assert "No user interaction allowed" in response.json()["detail"]


def test_timeout_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake: FakeOsascript
) -> None:
    def slow(command: list[str], **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(picker.subprocess, "run", slow)

    response = client.post(URL, json={"field": "music_folder"}, headers=HEADERS)

    assert response.status_code == 503
    assert "too long" in response.json()["detail"]
    assert picker._lock.acquire(blocking=False)  # released again
    picker._lock.release()


def test_one_dialog_at_a_time(client: TestClient, fake: FakeOsascript) -> None:
    with picker._lock:
        response = client.post(URL, json={"field": "music_folder"}, headers=HEADERS)
    assert response.status_code == 409
    assert fake.commands == []


def test_not_macos_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(picker.sys, "platform", "linux")
    response = client.post(URL, json={"field": "music_folder"}, headers=HEADERS)
    assert response.status_code == 503
    assert "only works on macOS" in response.json()["detail"]


def test_needs_header_and_known_field(client: TestClient, fake: FakeOsascript) -> None:
    assert client.post(URL, json={"field": "music_folder"}).status_code == 403
    response = client.post(URL, json={"field": "port"}, headers=HEADERS)
    assert response.status_code == 422
    assert fake.commands == []
