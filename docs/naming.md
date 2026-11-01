# Playlist names, Playlist tags and Folder placement

Cratekeeper reads emojis in playlist names. Each emoji stands for one **Playlist
tag** in one of four groups. The mapping is a JSON file: the built-in one is
`src/cratekeeper/defaults/tag_mapping.json`; edit your own on the Settings page.

| Group | Example | Used for |
| --- | --- | --- |
| Genre | 🏢 → Techno, 🌃 → House Deep | folder, track genre |
| Energy | ⬆️ → High | Rekordbox name |
| Status | ❓ → Recherche, 💾 → Archived | folder, Rekordbox name |
| Party | 🎉 → Partys, 🎙️ → Radio Moafunk | Events folder |

Skin tones and other emoji variants count as the base emoji.

## Rekordbox name

Emojis are removed, then the first Energy tag and the first Status tag are added
(the default Status, "Archived", is left out):

| Playlist | Rekordbox name |
| --- | --- |
| `Peak Time 🏢⬆️` | `Peak Time High` |
| `Peak Time 🏢⬆️❓` | `Peak Time High Recherche` |
| `Deep 🌃💾` | `Deep` |

## Folder placement

First rule that applies:

1. **Genre** tag → `Genre / <category> / <status>`. The category comes from
   `folder_structure.genre_categories` ("Other Genres" if the genre is not listed);
   the status is the first Status tag or "Archived".
2. **Party** tag → `Events / <party> / <year>`. The year is a 4-digit year in the
   name, or the year of a leading `YY-MM-DD` date, else "Misc".
3. Only a **Status** tag → `Genre / Uncategorized / <status>`.
4. No tag → `Genre / Uncategorized / Archived`.

| Playlist | Folder |
| --- | --- |
| `Peak Time 🏢⬆️` | `Genre/Techno/Archived` |
| `Italo 🇮🇹❓` | `Genre/House/Recherche` |
| `24-08-31 Openair 🎉` | `Events/Partys/2024` |
| `Old stuff 👵🏻` | `Genre/Uncategorized/Old` |

When a name changes (e.g. ❓ → 💾), the Plan renames and moves the existing
Rekordbox playlist instead of creating a new one.

## Genre of a track

A track gets the first genre (alphabetically) of all the playlists it is in, so it
has the same genre everywhere. Playlists without a Genre tag do not set a genre.
