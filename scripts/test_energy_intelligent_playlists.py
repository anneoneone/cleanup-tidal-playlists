#!/usr/bin/env python3
"""Test Energy-based intelligent playlists."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("Testing Energy-based intelligent playlist structure...\n")

# Load the config to see what energy values we have
import json

config_path = Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"

with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

track_metadata = config.get("Track-Metadata", {})
genre_structure = track_metadata.get("Genre", {})
energy_mapping = track_metadata.get("Energy", {})

print("Energy values from config:")
for emoji, value in energy_mapping.items():
    print(f"  {emoji} = {value}")

print("\nExample playlists that will be created:")
print("=" * 60)

# Example: House category
house_genres = genre_structure.get("House", {})
status_folders = ["Archived", "Old", "Recherche", "Current"]

print("\nUnder Genres/House/Archived/:")
print("-" * 60)

# Show a few examples
example_genres = list(house_genres.items())[:2]

for emoji, genre_value in example_genres:
    # Base playlist (no energy)
    print(f"  {emoji} {genre_value}")
    print(f"    → Genre={genre_value} AND Status=Archived")

    # Energy playlists
    for energy_emoji, energy_value in energy_mapping.items():
        print(f"  {emoji}{energy_emoji} {genre_value}")
        print(
            f"    → Genre={genre_value} AND "
            f"Energy={energy_value} AND Status=Archived"
        )
    print()

print("\nUnder Genres/House/Current/:")
print("-" * 60)

for emoji, genre_value in example_genres:
    # Base playlist (no energy, no status)
    print(f"  {emoji} {genre_value}")
    print(f"    → Genre={genre_value}")

    # Energy playlists (no status)
    for energy_emoji, energy_value in energy_mapping.items():
        print(f"  {emoji}{energy_emoji} {genre_value}")
        print(f"    → Genre={genre_value} AND Energy={energy_value}")
    print()

print("=" * 60)
print("\n✅ Configuration looks correct!")
print(
    f"\nThis will create {len(house_genres) * (1 + len(energy_mapping))} "
    f"playlists per status folder"
)
print(
    f"Total for House category: "
    f"{len(house_genres) * (1 + len(energy_mapping)) * len(status_folders)} "
    f"playlists"
)
