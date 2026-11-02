from datetime import datetime, timezone

import pytest

from cratekeeper.rekordbox.naming import NameRules, added_date, clean_name
from cratekeeper.settings import default_tag_mapping_path


@pytest.fixture(scope="module")
def rules() -> NameRules:
    return NameRules.from_file(default_tag_mapping_path())


def test_no_tags_falls_back_to_uncategorized(rules: NameRules) -> None:
    tags = rules.parse("My Plain Playlist")
    assert tags.genre == {"Uncategorized"}
    assert rules.folder_path(tags) == ["Genre", "Uncategorized", "Archived"]
    assert rules.genre(tags) is None


@pytest.mark.parametrize(
    ("name", "year"),
    [
        ("Party Vibes 🎉", "Misc"),
        ("Festival 2024 🎉", "2024"),
        ("25-07-19 Feel 🎉", "2025"),
    ],
)
def test_event_year(rules: NameRules, name: str, year: str) -> None:
    tags = rules.parse(name)
    assert tags.party == {"Partys"}
    assert rules.folder_path(tags) == ["Events", "Partys", year]


def test_genre_energy_status_name_and_folder(rules: NameRules) -> None:
    tags = rules.parse("Peak Time 🏢⬆️❓")
    assert rules.rekordbox_name(tags) == "Peak Time High Recherche"
    assert rules.rekordbox_name(tags, include_status=False) == "Peak Time High"
    assert rules.folder_path(tags) == ["Genre", "Techno", "Recherche"]
    assert rules.genre(tags) == "Techno"


def test_default_status_is_not_in_the_name(rules: NameRules) -> None:
    tags = rules.parse("Deep 🌃💾")
    assert rules.rekordbox_name(tags) == "Deep"
    assert rules.folder_path(tags) == ["Genre", "Deep House", "Archived"]


def test_status_only_and_unlisted_genre(rules: NameRules) -> None:
    assert rules.folder_path(rules.parse("Old stuff 👵🏽")) == [
        "Genre",
        "Uncategorized",
        "Old",
    ]
    custom = NameRules(
        {
            "emoji_to_mytag_mapping": {"Genre": {"🧪": "Lab"}},
            "folder_structure": {"genre_categories": {"House": ["House House"]}},
        }
    )
    assert custom.folder_path(custom.parse("Test 🧪")) == [
        "Genre",
        "Other Genres",
        "Archived",
    ]


def test_clean_name_collapses_spaces() -> None:
    assert clean_name("A  🏢  B ⬆️") == "A B"


def test_added_date_order() -> None:
    tidal = datetime(2024, 1, 1, tzinfo=timezone.utc)
    local = datetime(2023, 1, 1)
    assert added_date(tidal, local, None) == datetime(2024, 1, 1)
    assert added_date(None, local, None) == local
    assert added_date(None, None, None) == datetime(1970, 1, 1)
