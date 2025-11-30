# Event Playlist Handling

## Overview

Event playlists represent specific parties, sets, or radio shows. Each event playlist creates:

1. A unique Event MyTag (e.g., `Event::Party::23-04-04 carlparty selection`)
2. An intelligent playlist under the appropriate Events subfolder
3. Tags all tracks in the MP3 playlist with the event tag

## Event Types

Based on `rekordbox_mytag_mapping.json`, there are three event types:

| Emoji | Event Type      | Folder Name    |
|-------|-----------------|----------------|
| 🎉    | Party           | Partys         |
| 🎶    | Set             | Sets           |
| 🎙️    | Radio Moafunk   | Radio Moafunk  |

## Playlist Naming Convention

Event playlists follow the pattern:

```
<event-name> <EVENT-EMOJI> [ENERGY-EMOJI] [STATUS-EMOJI]
```

Examples:

- `23-04-04 carlparty selection 🎉` → Party event
- `Summer Vibes Set 🎶⬆️` → Set event with High energy
- `Radio Moafunk Episode 1 🎙️` → Radio Moafunk event

## Sync Behavior

When `TrackTagSyncService` processes an event playlist:

### 1. Detection

- Checks if playlist has party tags (event emojis)
- `_is_event_playlist()` returns `True` if party tags exist

### 2. Event Tag Creation

- Extracts clean event name (without emojis)
- Creates MyTag in the event type category
- **Category**: Event type (Party, Set, or Radio Moafunk)
- **Tag Value**: Event name (e.g., "23-04-04 carlparty selection")

Examples:

- `23-04-04 carlparty selection 🎉` → MyTag: `Party::23-04-04 carlparty selection`
- `Summer Vibes Set 🎶` → MyTag: `Set::Summer Vibes Set`
- `25-04-05 Brunchtime 🎙️` → MyTag: `Radio Moafunk::25-04-05 Brunchtime`

### 3. Track Tagging

- Scans all MP3 files in the playlist directory
- Adds each track to Rekordbox (if not exists)
- Tags each track with the event tag

### 4. Intelligent Playlist Creation

- Creates intelligent playlist under `Events/<event-folder>/<event-name>`
- Query condition: MyTag CONTAINS event tag
- Structure:

  ```
  Events/
    Partys/
      23-04-04 carlparty selection (smart playlist)
    Sets/
      Summer Vibes Set (smart playlist)
    Radio Moafunk/
      Radio Moafunk Episode 1 (smart playlist)
  ```

## Implementation Details

### Key Methods

**`_sync_event_playlist(playlist_name, metadata)`**

- Main event playlist sync handler
- Creates event tag and intelligent playlist
- Tags all tracks

**`_get_event_type(metadata)`**

- Maps party tag to event type
- Returns: "Party", "Set", or "Radio Moafunk"

**`_create_event_intelligent_playlist(event_type, event_name, event_tag)`**

- Creates smart playlist under correct event folder
- Uses SmartList with MyTag CONTAINS condition

### Event Tag Format

Event tags use a simple category-value structure:

```
<EventType>::<EventName>
```

Examples:

- `Party::23-04-04 carlparty selection`
- `Set::Summer Vibes Set`
- `Radio Moafunk::25-04-05 Brunchtime`

This creates three MyTag categories (Party, Set, Radio Moafunk), each containing multiple event tags.

## Differences from Track Playlists

| Aspect | Track Playlists | Event Playlists |
|--------|-----------------|-----------------|
| Detection | Has genre tags | Has party tags (event emojis) |
| Tag Group | Genre, Status, Energy, Source | Event only |
| Default Tags | Archived, Tidal | None |
| Playlist Location | Not created | Events/<type>/<name> |
| Tag Format | Multiple groups | Single hierarchical tag |

## Usage Example

### Create Event Playlist

1. Create MP3 playlist directory:

   ```
   mp3-playlists/23-04-04 carlparty selection 🎉/
     ├── track1.mp3
     ├── track2.mp3
     └── track3.mp3
   ```

2. Run sync:

   ```python
   from tidal_cleanup.services.track_tag_sync_service import TrackTagSyncService

   service = TrackTagSyncService(db, mp3_playlists_root, mytag_mapping_path)
   result = service.sync_playlist("23-04-04 carlparty selection 🎉")
   ```

3. Result:
   - MyTag created: `Event::Party::23-04-04 carlparty selection`
   - Intelligent playlist: `Events/Partys/23-04-04 carlparty selection`
   - All tracks tagged with event tag

### Query Event Tracks

To find all tracks from a specific event:

```python
# The intelligent playlist automatically filters by event tag
# Or query directly:
event_tag = mytag_manager.create_or_get_tag(
    "Party::23-04-04 carlparty selection",
    "Event"
)
tracks = mytag_manager.get_content_with_tag(event_tag)
```

## Testing

Use `scripts/test_event_playlists.py` to verify:

- Event playlist name parsing
- Event type detection
- Current event structure in Rekordbox

```bash
python scripts/test_event_playlists.py
```

## Benefits

1. **Organization**: Events organized by type (Partys, Sets, Radio)
2. **Unique Tracking**: Each event gets its own tag
3. **Easy Access**: Intelligent playlists for quick event access
4. **Historical Record**: All event playlists preserved with dates
5. **Flexible Querying**: Can find all tracks from specific events

## Future Enhancements

- [ ] Support for event date extraction and sorting
- [ ] Event series grouping (e.g., all Radio Moafunk episodes)
- [ ] Venue/location tagging
- [ ] Event artwork/cover images
- [ ] Cross-event track analysis
