import json
import shutil
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import cratekeeper.api.app as api_module
from cratekeeper.api.app import create_app
from cratekeeper.app import App
from cratekeeper.db import PlaylistTrack
from cratekeeper.jobs import held_lock
from cratekeeper.sticks.export_pdb import ExportTrack
from cratekeeper.tidal.auth import LoginStart

HEADERS = {"X-Cratekeeper": "1"}


@pytest.fixture
def core(tmp_path: Path, rekordbox_library: Path, make_mp3: Any) -> App:
    music = tmp_path / "music"
    make_mp3(music / "Playlists" / "Peak 🏢" / "A - One.mp3")
    make_mp3(music / "Playlists" / "Party 2024 🎉" / "B - Two.mp3")
    app = App.open()
    app.home.config_file.write_text(
        f'music_folder = "{music}"\nrekordbox_db = "{rekordbox_library}"\n'
    )
    app.reload_settings()
    return app


@pytest.fixture
def client(core: App) -> TestClient:
    return TestClient(create_app(core, 8765, extra_hosts={"testserver"}))


def wait_job(core: App, job: dict[str, Any]) -> dict[str, Any]:
    running = core.runner.get(job["id"])
    assert running is not None and running.wait(20)
    return running.snapshot()


def offline_sync(client: TestClient, core: App) -> int:
    response = client.post("/api/sync", json={"offline": True}, headers=HEADERS)
    assert response.status_code == 202, response.text
    assert wait_job(core, response.json())["status"] == "succeeded"
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    return int(job["result"]["run_id"])


def test_guard_rejects_foreign_hosts_origins_and_missing_header(core: App) -> None:
    guarded = TestClient(create_app(core, 8765, extra_hosts={"testserver"}))
    assert (
        guarded.get("/api/status", headers={"host": "evil.example"}).status_code == 403
    )
    assert guarded.post("/api/sync", json={}).status_code == 403
    response = guarded.post(
        "/api/sync",
        json={"offline": True},
        headers={**HEADERS, "Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    allowed = TestClient(create_app(core, 8765), base_url="http://127.0.0.1:8765")
    assert allowed.get("/api/status").status_code == 200


def test_status_lists_checks_and_counts(client: TestClient) -> None:
    body = client.get("/api/status").json()
    keys = {c["key"] for c in body["checks"]}
    assert {"music_folder", "rekordbox_library", "tidal_login", "ffmpeg"} <= keys
    assert client.get("/api/status").json()["rekordbox_running"] is False
    assert body["counts"]["playlists"] == 0
    assert body["current_job"] is None


def test_sync_plan_apply_flow(client: TestClient, core: App) -> None:
    run_id = offline_sync(client, core)

    plan = client.get(f"/api/plans/{run_id}").json()
    keys = [g["key"] for g in plan["plan"]["groups"]]
    assert len(keys) == 2 and plan["applied_by_run"] is None

    playlists = client.get("/api/playlists").json()
    assert {p["name"] for p in playlists} == {"Peak 🏢", "Party 2024 🎉"}
    peak = next(p for p in playlists if p["name"] == "Peak 🏢")
    assert peak["sources"] == ["library"] and peak["folder"] == [
        "Genre",
        "Techno",
        "Archived",
    ]
    detail = client.get(f"/api/playlists/{peak['id']}").json()
    track = detail["tracks"][0]
    assert (track["sources"], track["download"], track["rekordbox"]) == (
        ["library"],
        "present",
        "absent",
    )
    assert (detail["tracks_library"], detail["tracks_unsynced"]) == (1, 0)
    assert client.get("/api/playlists/999").status_code == 404

    bad = client.post(
        f"/api/plans/{run_id}/apply", json={"groups": ["nope"]}, headers=HEADERS
    )
    assert bad.status_code == 422
    empty = client.post(
        f"/api/plans/{run_id}/apply", json={"groups": []}, headers=HEADERS
    )
    assert empty.status_code == 422

    response = client.post(
        f"/api/plans/{run_id}/apply", json={"groups": keys}, headers=HEADERS
    )
    assert response.status_code == 202
    assert wait_job(core, response.json())["status"] == "succeeded"
    result = client.get(f"/api/jobs/{response.json()['id']}").json()["result"]
    assert (result["applied"], result["failed"]) == (2, 0)
    apply_run = client.get(f"/api/runs/{result['run_id']}").json()
    assert [g["status"] for g in apply_run["summary"]["groups"]] == ["applied"] * 2
    assert (
        client.get(f"/api/plans/{run_id}").json()["applied_by_run"] == result["run_id"]
    )
    again = client.post(
        f"/api/plans/{run_id}/apply", json={"groups": keys}, headers=HEADERS
    )
    assert again.status_code == 409 and "applied in run" in again.json()["detail"]

    runs = client.get("/api/runs").json()
    assert [r["kind"] for r in runs] == ["apply", "sync"]
    assert runs[1]["totals"]["create_playlist"] == 2
    assert client.get("/api/plans/12345").status_code == 404


def test_older_plan_is_superseded_by_a_newer_sync(
    client: TestClient, core: App
) -> None:
    first = offline_sync(client, core)
    second = offline_sync(client, core)

    old = client.get(f"/api/plans/{first}").json()
    assert old["superseded_by"] == second
    assert client.get(f"/api/plans/{second}").json()["superseded_by"] is None
    keys = [g["key"] for g in old["plan"]["groups"]]
    response = client.post(
        f"/api/plans/{first}/apply", json={"groups": keys}, headers=HEADERS
    )
    assert response.status_code == 409
    assert f"Run {second} made a newer Plan" in response.json()["detail"]


def test_event_stream_replays_events_until_the_end(
    client: TestClient, core: App
) -> None:
    response = client.post("/api/sync", json={"offline": True}, headers=HEADERS)
    job_id = response.json()["id"]
    wait_job(core, response.json())

    stream = client.get(f"/api/jobs/{job_id}/events")

    assert stream.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line[len("data: ") :])
        for line in stream.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[0]["kind"] == "started" and events[-1]["kind"] == "finished"
    steps = [e["step"] for e in events if e["kind"] == "step"]
    assert steps == ["Backup", "Refresh Bandcamp", "Refresh Music folder", "Plan"]
    later = client.get(f"/api/jobs/{job_id}/events?after={events[-2]['seq']}")
    assert later.text.count("data: ") == 1
    assert client.get("/api/jobs/unknown/events").status_code == 404


def test_busy_runner_returns_409(client: TestClient, core: App) -> None:
    release = threading.Event()
    job = core.runner.start("test", lambda ctx: release.wait(10))
    try:
        response = client.post("/api/sync", json={"offline": True}, headers=HEADERS)
        assert response.status_code == 409
        current = client.get("/api/jobs/current").json()
        assert current["id"] == job.id and current["status"] == "running"
        cancel = client.post(f"/api/jobs/{job.id}/cancel", headers=HEADERS).json()
        assert cancel == {"cancelled": True}
    finally:
        release.set()
        job.wait(10)
    assert client.post("/api/jobs/missing/cancel", headers=HEADERS).json() == {
        "cancelled": False
    }


def test_import_file_adds_a_library_track(
    client: TestClient, core: App, tmp_path: Path, make_mp3: Any
) -> None:
    offline_sync(client, core)
    peak = next(
        p for p in client.get("/api/playlists").json() if p["name"] == "Peak 🏢"
    )
    data = make_mp3(
        tmp_path / "upload" / "x.mp3", title="Three", artist="C"
    ).read_bytes()
    url = f"/api/playlists/{peak['id']}/files"

    response = client.post(
        url, params={"name": "C - Three.mp3"}, content=data, headers=HEADERS
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["file_path"], body["library_track"]) == (
        "Playlists/Peak 🏢/C - Three.mp3",
        True,
    )
    music = core.settings.music_folder
    assert (music / body["file_path"]).read_bytes() == data
    detail = client.get(f"/api/playlists/{peak['id']}").json()
    new = next(t for t in detail["tracks"] if t["id"] == body["track_id"])
    assert (new["title"], new["sources"], new["rekordbox"]) == (
        "Three",
        ["library"],
        "absent",
    )
    run_id = offline_sync(client, core)  # the next Plan adds it to Rekordbox
    changes = [
        c
        for g in client.get(f"/api/plans/{run_id}").json()["plan"]["groups"]
        for c in g["changes"]
    ]
    assert any("Three" in json.dumps(c) for c in changes)

    again = client.post(
        url, params={"name": "C - Three.mp3"}, content=b"x", headers=HEADERS
    )
    assert (
        again.status_code == 409 and "already in the folder" in again.json()["detail"]
    )
    assert (music / body["file_path"]).read_bytes() == data


def test_import_file_errors(client: TestClient, core: App) -> None:
    offline_sync(client, core)
    pid = client.get("/api/playlists").json()[0]["id"]
    url = f"/api/playlists/{pid}/files"

    def post(name: str, content: bytes = b"data", **kwargs: Any) -> Any:
        return client.post(
            url, params={"name": name}, content=content, headers=HEADERS, **kwargs
        )

    assert post("notes.txt").status_code == 422
    assert post("../x.mp3").status_code == 422
    assert post("x.mp3", b"").json()["detail"] == "The file is empty"
    assert (
        client.post(
            "/api/playlists/999/files",
            params={"name": "x.mp3"},
            content=b"data",
            headers=HEADERS,
        ).status_code
        == 404
    )
    assert client.post(url, params={"name": "x.mp3"}, content=b"d").status_code == 403

    release = threading.Event()
    job = core.runner.start("test", lambda ctx: release.wait(10), label="Busy")
    try:
        busy = post("x.mp3")
        assert busy.status_code == 409 and "Busy" in busy.json()["detail"]
    finally:
        release.set()
        job.wait(10)
    with held_lock(core.home.lock_file):  # a job in another process (the CLI)
        cli_busy = post("x.mp3")
    assert cli_busy.status_code == 409 and "job is running" in cli_busy.json()["detail"]
    assert list(core.settings.music_folder.rglob("x.mp3")) == []
    assert list(core.settings.music_folder.rglob(".*.part")) == []


def test_settings_round_trip_and_validation(client: TestClient, core: App) -> None:
    current = client.get("/api/settings").json()
    values = current["values"]
    assert values["target_format"] == "mp3"
    values["ffmpeg_quality"] = 0
    values["bandcamp_folder"] = ""
    saved = client.put("/api/settings", json=values, headers=HEADERS)
    assert saved.status_code == 200
    assert saved.json()["values"]["ffmpeg_quality"] == 0
    assert "ffmpeg_quality = 0" in core.home.config_file.read_text()
    values["target_format"] = "ogg"
    assert client.put("/api/settings", json=values, headers=HEADERS).status_code == 422


def test_tag_mapping_edit(client: TestClient, core: App) -> None:
    mapping = client.get("/api/settings/tag-mapping").json()
    assert "Genre" in mapping["emoji_to_mytag_mapping"]
    mapping["emoji_to_mytag_mapping"]["Genre"]["🧪"] = "Lab"
    response = client.put("/api/settings/tag-mapping", json=mapping, headers=HEADERS)
    assert response.status_code == 200
    stored = json.loads(core.home.tag_mapping_file.read_text())
    assert stored["emoji_to_mytag_mapping"]["Genre"]["🧪"] == "Lab"
    assert client.get("/api/settings").json()["tag_mapping_in_use"] == str(
        core.home.tag_mapping_file
    )
    bad = client.put("/api/settings/tag-mapping", json={"x": 1}, headers=HEADERS)
    assert bad.status_code == 422


def test_tidal_login_endpoints(
    client: TestClient, core: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/api/auth/tidal").json() == {
        "logged_in": False,
        "state": "idle",
        "url": None,
        "user_code": None,
        "expires_at": None,
        "error": None,
    }
    start = LoginStart(
        url="https://link.tidal.com/ABC", user_code="ABC", expires_at=1.0
    )
    monkeypatch.setattr(core.auth, "start_login", lambda: start)
    body = client.post("/api/auth/tidal", headers=HEADERS).json()
    assert (body["state"], body["url"], body["user_code"]) == (
        "pending",
        "https://link.tidal.com/ABC",
        "ABC",
    )

    # After a page reload the UI gets the same link back.
    monkeypatch.setattr(core.auth, "login_state", lambda: ("pending", None))
    monkeypatch.setattr(core.auth, "pending_login", lambda: start)
    again = client.get("/api/auth/tidal").json()
    assert (again["state"], again["url"], again["user_code"]) == (
        "pending",
        "https://link.tidal.com/ABC",
        "ABC",
    )


def test_backups_list_and_restore(client: TestClient, core: App) -> None:
    offline_sync(client, core)
    backups = client.get("/api/backups").json()
    assert backups and backups[0]["kind"] == "db"
    response = client.post(f"/api/backups/{backups[0]['id']}/restore", headers=HEADERS)
    assert response.status_code == 202
    assert wait_job(core, response.json())["status"] == "succeeded"
    missing = client.post(
        "/api/backups/20260101-000000-00-nope/restore", headers=HEADERS
    )
    assert missing.status_code == 404


def test_plan_lists_are_required_in_the_schema(client: TestClient) -> None:
    schemas = client.get("/api/openapi.json").json()["components"]["schemas"]
    assert {"groups", "warnings", "new_folders"} <= set(schemas["Plan"]["required"])
    assert "changes" in schemas["PlanGroup"]["required"]


def test_ui_fallback(
    core: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "dist"
    monkeypatch.setattr(api_module, "web_dist", lambda: dist)
    unbuilt = TestClient(create_app(core, 8765, extra_hosts={"testserver"}))
    assert "make ui" in unbuilt.get("/").text
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    app = TestClient(create_app(App.open(), 8765, extra_hosts={"testserver"}))
    assert app.get("/playlists/3").text == "<html>app</html>"
    assert app.get("/assets/app.js").text == "console.log(1)"
    assert app.get("/../secret").text == "<html>app</html>"
    assert app.get("/api/nothing").status_code == 404


def test_scan_sticks_and_show_them_per_track(
    client: TestClient, core: App, no_mounted_sticks: Path, write_export: Any
) -> None:
    assert client.get("/api/sticks").json() == []
    empty = client.post("/api/sticks/scan", headers=HEADERS).json()
    assert empty == {"scanned": [], "problems": [], "sticks": []}

    offline_sync(client, core)
    one = core.settings.music_folder / "Playlists" / "Peak 🏢" / "A - One.mp3"
    write_export(
        no_mounted_sticks / "S1" / "PIONEER" / "rekordbox" / "export.pdb",
        [
            ExportTrack(
                title="One",
                artist="A",
                isrc="",
                file_name=one.name,
                file_path=f"/Contents/A/{one.name}",
                file_size=one.stat().st_size,
            )
        ],
    )
    (no_mounted_sticks / "S2" / "PIONEER" / "rekordbox").mkdir(parents=True)

    response = client.post("/api/sticks/scan", headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["scanned"]) == 1 and body["problems"][0].startswith("S2: ")
    (s1,) = body["sticks"]
    assert (s1["name"], s1["mounted"], s1["tracks_total"], s1["tracks_matched"]) == (
        "S1",
        True,
        1,
        1,
    )

    playlists = client.get("/api/playlists").json()
    peak = next(p for p in playlists if p["name"] == "Peak 🏢")
    (track,) = client.get(f"/api/playlists/{peak['id']}").json()["tracks"]
    assert track["sticks"] == [{"id": s1["id"], "name": "S1", "state": "present"}]
    party = next(p for p in playlists if p["name"] != "Peak 🏢")
    (other,) = client.get(f"/api/playlists/{party['id']}").json()["tracks"]
    assert other["sticks"] == []

    # Gone from Peak's Sources: still wanted while Party has it, unsynced after
    with core.db.session() as session:
        row = session.scalars(
            select(PlaylistTrack).where(PlaylistTrack.track_id == track["id"])
        ).one()
        row.in_local = False
        session.add(
            PlaylistTrack(playlist_id=party["id"], track_id=track["id"], in_local=True)
        )

    def peak_sticks() -> Any:
        (row,) = client.get(f"/api/playlists/{peak['id']}").json()["tracks"]
        return [s["state"] for s in row["sticks"]]

    assert peak_sticks() == ["present"]
    with core.db.session() as session:
        session.execute(
            delete(PlaylistTrack).where(PlaylistTrack.playlist_id == party["id"])
        )
    assert peak_sticks() == ["unsynced"]

    # Unplugged: the last scan stays
    shutil.rmtree(no_mounted_sticks / "S1")
    (kept,) = client.get("/api/sticks").json()
    assert (kept["id"], kept["mounted"], kept["tracks_matched"]) == (s1["id"], False, 1)


def test_stick_scan_waits_for_running_jobs(client: TestClient, core: App) -> None:
    release = threading.Event()
    job = core.runner.start("test", lambda ctx: release.wait(10))
    try:
        response = client.post("/api/sticks/scan", headers=HEADERS)
        assert response.status_code == 409
    finally:
        release.set()
        job.wait(10)
    assert client.post("/api/sticks/scan").status_code == 403  # header required


def test_track_sticks_are_required_in_the_schema(client: TestClient) -> None:
    schemas = client.get("/api/openapi.json").json()["components"]["schemas"]
    assert "sticks" in schemas["TrackOut"]["required"]
