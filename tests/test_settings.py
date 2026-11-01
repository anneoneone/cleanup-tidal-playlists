from pathlib import Path

import pytest

from cratekeeper.home import Home
from cratekeeper.settings import Settings, SettingsError, default_tag_mapping_path


@pytest.fixture
def home(tmp_path: Path) -> Home:
    return Home(root=tmp_path / "ck").ensure()


def test_home_resolves_from_env(tmp_path: Path) -> None:
    assert Home.resolve().root == tmp_path / "cratekeeper-home"


def test_defaults_without_config_file(home: Home, isolated_home: Path) -> None:
    settings = Settings.load(home)
    assert settings.music_folder == isolated_home / "Music" / "Tidal" / "mp3"
    assert settings.bandcamp_folder is None
    assert settings.target_format == "mp3"
    assert settings.prune_tracks is True
    assert not home.config_file.exists()


def test_load_from_toml_expands_user(home: Home, isolated_home: Path) -> None:
    home.config_file.write_text(
        'music_folder = "~/dj/mp3"\nbandcamp_folder = "/Volumes/HDD/Bandcamp"\n'
        "ffmpeg_quality = 0\n"
    )
    settings = Settings.load(home)
    assert settings.music_folder == isolated_home / "dj" / "mp3"
    assert settings.bandcamp_folder == Path("/Volumes/HDD/Bandcamp")
    assert settings.ffmpeg_quality == 0


def test_env_overrides_file(home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
    home.config_file.write_text("port = 9000\n")
    monkeypatch.setenv("CRATEKEEPER_PORT", "9100")
    monkeypatch.setenv("CRATEKEEPER_PRUNE_TRACKS", "false")
    settings = Settings.load(home)
    assert settings.port == 9100
    assert settings.prune_tracks is False


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        ('target_format = "ogg"\n', "target_format"),
        ("unknown_key = 1\n", "unknown_key"),
        ("port = [\n", "config.toml"),
    ],
)
def test_invalid_settings_raise(home: Home, content: str, fragment: str) -> None:
    home.config_file.write_text(content)
    with pytest.raises(SettingsError, match=fragment):
        Settings.load(home)


def test_save_round_trip_skips_unset_values(home: Home) -> None:
    settings = Settings(music_folder=Path("/music"), backups_keep_full=5)
    settings.save(home)
    text = home.config_file.read_text()
    assert 'music_folder = "/music"' in text
    assert "bandcamp_folder" not in text
    assert Settings.load(home) == settings


def test_tag_mapping_path_order(home: Home, tmp_path: Path) -> None:
    settings = Settings()
    assert settings.tag_mapping_path(home) == default_tag_mapping_path()
    assert default_tag_mapping_path().exists()

    home.tag_mapping_file.write_text("{}")
    assert settings.tag_mapping_path(home) == home.tag_mapping_file

    custom = tmp_path / "mine.json"
    settings.tag_mapping = custom
    assert settings.tag_mapping_path(home) == custom
