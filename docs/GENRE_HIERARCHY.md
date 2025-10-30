# Genre Hierarchy for Rekordbox

This feature enables hierarchical organization of playlists in Rekordbox by creating top-level category folders (e.g., "House", "Techno", "Disco") with genre-specific subfolders nested underneath.

## Overview

Instead of having all playlists in a flat structure at the root level, you can now organize them into a two-level hierarchy:

```
Rekordbox Playlists
├── House/
│   ├── House Deep/
│   ├── House Disco/
│   ├── House Italo/
│   └── ...
├── Techno/
│   ├── Techno Techno/
│   ├── Techno Dub/
│   └── Hardgroove/
├── Disco/
│   ├── Disco Disco/
│   ├── Disco Classy/
│   └── ...
├── Partys/
│   └── Party/
├── Sets/
│   └── Set/
└── etc/
    └── (uncategorized playlists)
```

## Configuration

The hierarchy is defined in `config/rekordbox_genre_hierarchy.json`:

```json
{
  "genre_hierarchy": {
    "House": [
      "House House",
      "House Italo",
      "House Deep",
      "House Disco",
      "House Chill",
      "House Tool",
      "House Progressive",
      "House Ghetto",
      "House Groove",
      "House LoFi",
      "Groove",
      "Breaks"
    ],
    "Techno": [
      "Techno Techno",
      "Techno Dub",
      "Hardgroove",
      "Techhouse"
    ],
    "Disco": [
      "Disco Disco",
      "Disco Classy",
      "Disco Nu",
      "Disco Synth"
    ],
    "Partys": [
      "Party"
    ],
    "Sets": [
      "Set"
    ],
    "Radio Moafunk": [
      "Moafunk"
    ]
  },
  "default_category": "etc"
}
```

### Structure

- **Top-level categories**: The keys in `genre_hierarchy` (e.g., "House", "Techno")
- **Genre mappings**: The arrays define which genres/tags belong to each category
- **Default category**: Playlists that don't match any mapping go to "etc"

## How It Works

1. **Playlist name parsing**: When syncing a playlist like "☀️🏃🏼‍♂️ Summer Deep House Mix", the emoji parser extracts tags like "House House" and "House Progressive"

2. **Category determination**: The genre hierarchy manager checks which top-level category these tags belong to (in this case, "House")

3. **Folder creation**: Two folders are created/used:
   - Top-level category folder: "House"
   - Genre subfolder: "House House" (first genre tag, alphabetically)

4. **Playlist placement**: The playlist is placed inside the nested structure: `House/House House/`

## Priority Rules

1. **Genre tags take priority**: If a playlist has both genre and party tags, genre tags are used first
2. **First match wins**: If multiple genre tags map to different categories, the first one (alphabetically) is used
3. **Default fallback**: Playlists without any mapped tags go to the "etc" category

## Enabling/Disabling

The hierarchy feature is **automatically enabled** when the configuration file exists at:

- `config/rekordbox_genre_hierarchy.json`

If the file doesn't exist or you remove it, the system falls back to the original flat folder structure (one level of folders based on genre/party tags).

## Examples

### Example 1: House Playlist

- **Playlist name**: `☀️ Summer House`
- **Extracted tag**: "House House" (☀️ emoji)
- **Category mapping**: "House House" → "House"
- **Result**: Playlist placed in `House/House House/`

### Example 2: Techno Playlist

- **Playlist name**: `🏢 Dark Warehouse`
- **Extracted tag**: "Techno Techno" (🏢 emoji)
- **Category mapping**: "Techno Techno" → "Techno"
- **Result**: Playlist placed in `Techno/Techno Techno/`

### Example 3: Party Playlist

- **Playlist name**: `🎉 Birthday Party 2024`
- **Extracted tag**: "Party" (🎉 emoji)
- **Category mapping**: "Party" → "Partys"
- **Result**: Playlist placed in `Partys/Party/`

### Example 4: Uncategorized

- **Playlist name**: `Random Mix`
- **Extracted tags**: None
- **Result**: Playlist placed in `etc/`

## Usage in Code

The feature is automatically used when calling sync methods:

```python
from tidal_cleanup.services import RekordboxService

service = RekordboxService(config)

# Sync a single playlist (hierarchy automatically applied if config exists)
service.sync_playlist_with_mytags("☀️ Summer House")

# Sync all playlists
service.sync_all_playlists_with_diff()
```

## Migration Notes

When you enable this feature for the first time:

1. **Existing playlists**: The sync will automatically move existing playlists into the new hierarchy
2. **Folder creation**: Top-level category folders are created automatically
3. **No data loss**: All tracks and MyTags are preserved during reorganization

## Customizing Categories

To customize the hierarchy, edit `config/rekordbox_genre_hierarchy.json`:

1. **Add a new category**:

```json
"Ambient": [
  "Ambient",
  "Drone"
]
```

2. **Move genres between categories**: Simply change which array they're in

3. **Rename categories**: Change the key name (e.g., "House" → "House Music")

4. **Change default category**: Update the `default_category` value

After editing, the next sync will automatically use the new configuration.

## Troubleshooting

### Playlists are going to "etc" instead of proper categories

Check that:

1. The emoji in the playlist name is correctly mapped in `rekordbox_mytag_mapping.json`
2. The resulting tag name matches exactly what's in `rekordbox_genre_hierarchy.json`
3. Tag names are case-sensitive (e.g., "House Deep" ≠ "house deep")

### Hierarchy is not working

Verify that:

1. The config file exists at `config/rekordbox_genre_hierarchy.json`
2. The JSON is valid (use a JSON validator)
3. You're using the latest version of the sync code

### Testing Your Configuration

Run the test suite to validate your configuration:

```bash
python -m pytest tests/test_genre_hierarchy_manager.py::test_real_config -v
```

This will test all the mappings in your configuration file.
