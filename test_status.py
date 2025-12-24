from pathlib import Path

from src.tidal_cleanup.core.rekordbox.playlist_parser import PlaylistNameParser

parser = PlaylistNameParser(Path("config/rekordbox_mytag_mapping.json"))

# Genre categories from config
genre_categories = {
    "Deep House": ["House Deep", "House Chill", "House LoFi", "Lounge", "Ambient"],
    "House": [
        "House House",
        "House Groove",
        "House Italo",
        "House Disco",
        "House Progressive",
        "House Tool",
        "House Ghetto",
        "Groove",
    ],
    "Techno": ["Techno", "Techhouse", "Hardgroove", "Techno Dub"],
    "Disco": ["Disco", "Disco Classy", "Disco Nu", "Disco Synth"],
    "Other Genres": [
        "Breaks",
        "Beach",
        "Downbeat",
        "Jazz",
        "Jungle",
        "NDW",
        "UK Garage",
    ],
}


def get_genre_category(genre):
    for category, genres in genre_categories.items():
        if genre in genres:
            return category
    return "Other Genres"


def get_folder_path_segments(metadata):
    genre_tags = getattr(metadata, "genre_tags", None)

    # Check if playlist has actual genre tags (not just "Uncategorized")
    if (
        genre_tags
        and genre_tags != {"Uncategorized"}
        and "Uncategorized" not in genre_tags
    ):
        genre = sorted(genre_tags)[0]
        status = (
            sorted(metadata.status_tags)[0]
            if getattr(metadata, "status_tags", None)
            else "Archived"
        )
        # Include genre category in path - always include status folder
        category = get_genre_category(genre)
        segments = ["Genre", category, status]
        return segments

    if getattr(metadata, "party_tags", None):
        event = sorted(metadata.party_tags)[0]
        year = getattr(metadata, "event_year", None) or "Misc"
        return ["Events", event, year]

    # No genre/party tags - goes to Uncategorized with default status
    return ["Genre", "Uncategorized", "Archived"]


test_names = [
    "House House ☀️❓",
    "House House ☀️👵🏻",
    "House House ☀️💾",
    "House House ☀️",  # No status
    "House House ☀️↗️❓",  # With energy and status
]

for name in test_names:
    metadata = parser.parse_playlist_name(name)
    segments = get_folder_path_segments(metadata)
    print(f"{name}")
    print(f"  status_tags: {metadata.status_tags}")
    print(f"  segments: {segments}")
    print()
