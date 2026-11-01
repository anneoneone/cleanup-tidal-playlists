import json
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import cratekeeper.api.app as api_module
from cratekeeper.api.app import create_app
from cratekeeper.app import App
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
    assert peak["sources"] == ["local"] and peak["folder"] == [
        "Genre",
        "Techno",
        "Archived",
    ]
    detail = client.get(f"/api/playlists/{peak['id']}").json()
    assert detail["tracks"][0]["has_file"] is True
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
