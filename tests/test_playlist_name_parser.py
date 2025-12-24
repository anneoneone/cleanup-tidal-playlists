"""Tests for PlaylistNameParser fallbacks and event handling."""

import json
from pathlib import Path
from typing import Dict, Optional

from tidal_cleanup.core.rekordbox.playlist_parser import PlaylistNameParser


def write_config(
    tmp_path: Path, mapping: Optional[Dict[str, Dict[str, str]]] = None
) -> Path:
    base_config = {
        "emoji_to_mytag_mapping": mapping or {"Genre": {}, "Party": {}},
        "folder_structure": {
            "genre_uncategorized": "Uncategorized",
            "events_misc": "Misc",
        },
        "no_genre_tag": {"group": "Genre", "value": "NoGenre"},
    }
    config_path = tmp_path / "mapping.json"
    config_path.write_text(json.dumps(base_config), encoding="utf-8")
    return config_path


def test_falls_back_to_uncategorized_when_no_tags(tmp_path: Path):
    config_path = write_config(tmp_path)
    parser = PlaylistNameParser(config_path)

    metadata = parser.parse_playlist_name("My Plain Playlist")

    assert metadata.genre_tags == {"Uncategorized"}
    assert metadata.party_tags == set()
    assert metadata.event_year is None


def test_event_year_defaults_to_misc_when_missing(tmp_path: Path):
    mapping = {"Genre": {}, "Party": {"🎉": "Partys"}}
    config_path = write_config(tmp_path, mapping)
    parser = PlaylistNameParser(config_path)

    metadata = parser.parse_playlist_name("Party Vibes 🎉")

    assert metadata.party_tags == {"Partys"}
    assert metadata.event_year == "Misc"
    assert metadata.genre_tags == set()


def test_event_year_extracted_from_name(tmp_path: Path):
    mapping = {"Genre": {}, "Party": {"🎉": "Partys"}}
    config_path = write_config(tmp_path, mapping)
    parser = PlaylistNameParser(config_path)

    metadata = parser.parse_playlist_name("Festival 2024 🎉")

    assert metadata.party_tags == {"Partys"}
    assert metadata.event_year == "2024"
    assert metadata.genre_tags == set()


def test_status_tags_resolve_with_skin_tone_variants(tmp_path: Path):
    mapping = {
        "Genre": {"☀️": "House"},
        "Status": {"👵🏻": "Old", "❓": "Recherche"},
    }
    config_path = write_config(tmp_path, mapping)
    parser = PlaylistNameParser(config_path)

    metadata = parser.parse_playlist_name("House ☀️👵")

    assert metadata.genre_tags == {"House"}
    assert metadata.status_tags == {"Old"}


def test_status_only_playlists_stay_categorized(tmp_path: Path):
    mapping = {"Status": {"❓": "Recherche"}}
    config_path = write_config(tmp_path, mapping)
    parser = PlaylistNameParser(config_path)

    metadata = parser.parse_playlist_name("Needs tracks ❓")

    assert metadata.genre_tags == {"Uncategorized"}
    assert metadata.status_tags == {"Recherche"}


def test_discogs_status_from_optical_disc(tmp_path: Path):
    mapping = {"Genre": {"🎭": "Techhouse"}, "Status": {"📀": "Discogs"}}
    config_path = write_config(tmp_path, mapping)
    parser = PlaylistNameParser(config_path)

    metadata = parser.parse_playlist_name("Techhouse 🎭📀")

    assert metadata.genre_tags == {"Techhouse"}
    assert metadata.status_tags == {"Discogs"}
