from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from cratekeeper.cli.main import cli
from cratekeeper.db import Database, Playlist
from cratekeeper.home import Home


@pytest.fixture
def configured(tmp_path: Path, rekordbox_library: Path, make_mp3: Any) -> Path:
    music = tmp_path / "music"
    make_mp3(music / "Playlists" / "Set 🎉" / "A - B.mp3")
    home = Home.resolve().ensure()
    home.config_file.write_text(
        f'music_folder = "{music}"\nrekordbox_db = "{rekordbox_library}"\n'
    )
    return music


def invoke(*args: str, input: str = "") -> Any:
    return CliRunner().invoke(cli, list(args), input=input, catch_exceptions=False)


def test_status_shows_paths_and_counts(configured: Path) -> None:
    result = invoke("status")
    assert result.exit_code == 0
    assert str(configured) in "".join(result.output.split())
    assert "Tidal login" in result.output


def test_offline_plan_only_then_apply(configured: Path) -> None:
    plan = invoke("sync", "--offline", "--plan-only")
    assert plan.exit_code == 0, plan.output
    assert "Set" in plan.output and "create" in plan.output

    applied = invoke("sync", "--offline", "--yes")
    assert applied.exit_code == 0, applied.output
    assert "applied" in applied.output

    again = invoke("sync", "--offline", "--plan-only")
    assert "up to date" in again.output

    backups = invoke("backups")
    assert "before-apply" in backups.output


def test_declining_the_prompt_applies_nothing(configured: Path) -> None:
    result = invoke("sync", "--offline", input="n\n")
    assert result.exit_code == 0
    assert "Nothing applied" in result.output


def test_bad_settings_give_a_clear_error(configured: Path) -> None:
    Home.resolve().config_file.write_text('target_format = "ogg"\n')
    result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 1
    assert "target_format" in result.output


def test_restore_unknown_backup_fails(configured: Path) -> None:
    result = CliRunner().invoke(cli, ["backups", "restore", "nope", "--yes"])
    assert result.exit_code == 1
    assert "Invalid backup ID" in result.output


def test_migrate_without_v1_data_fails(configured: Path) -> None:
    result = CliRunner().invoke(cli, ["migrate"])
    assert result.exit_code == 1
    assert "No v1 database" in result.output


def test_status_hints_at_migrate(configured: Path, isolated_home: Path) -> None:
    v1 = isolated_home / ".tidal-cleanup" / "sync.db"
    v1.parent.mkdir()
    Database(v1).prepare()
    with Database(v1).session() as s:
        s.add(Playlist(name="x"))
    home_db = Home.resolve().db_file
    home_db.unlink(missing_ok=True)
    assert "cratekeeper migrate" in invoke("status").output
