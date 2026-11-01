# Cratekeeper

Cratekeeper keeps a DJ's Rekordbox library in line with the playlists they curate on Tidal and in Bandcamp folders.

## Language

### Where music comes from

**Source**:
A place that defines playlists: **Tidal** or **Bandcamp**.
_Avoid_: provider, service, origin

**Tidal**:
The streaming **Source**. Its playlists are read through the Tidal API, and its tracks are fetched by a **Download**.

**Bandcamp**:
The local **Source**: a folder tree where each sub-folder is one **Playlist** of purchased audio files.
_Avoid_: local playlists, local-only tracks

**Music folder**:
The folder on disk that holds the audio files for **Tidal** tracks, with one sub-folder per **Playlist**. A Playlist keeps its sub-folder when it is renamed.
_Avoid_: mp3 directory, library

**Local playlist**:
A **Music folder** sub-folder that belongs to no **Tidal** playlist (e.g. a party or radio set put together by hand). All its files are **Local tracks**.
_Avoid_: local-only playlist, custom playlist

**Local track**:
An audio file in a **Playlist**'s **Music folder** sub-folder that matches no **Tidal** track. It belongs to that Playlist like any other **Track**.
_Avoid_: local-only track, orphan file

### What is kept in sync

**Playlist**:
A named, ordered list of **Tracks** from one or both **Sources**. A Tidal and a Bandcamp playlist with the same name are one Playlist.
_Avoid_: crate (that is the product name, not a domain term)

**Track**:
One piece of music, known by its Tidal ID and/or its audio file(s).

**Playlist emoji**:
An emoji in a **Playlist** name that stands for one **Playlist tag**.

**Playlist tag**:
The value a **Playlist emoji** stands for, in one of four groups: Genre, Energy, Status, Party.
_Avoid_: MyTag (Cratekeeper does not write Rekordbox MyTags), tag (file metadata is "file tags")

**Folder placement**:
The Rekordbox folder a **Playlist** lands in, derived from its **Playlist tags** (Genre tree or Events tree).

**Rekordbox membership**:
The **Tracks** a **Playlist** should have in Rekordbox: those currently in the Tidal playlist that have a file, plus its **Bandcamp** files, plus its **Local tracks**. A Track removed from Tidal leaves the Rekordbox playlist; its file stays on disk.

### How a sync runs

**Refresh**:
Reading the **Sources** and the **Music folder** into Cratekeeper's own database. Never touches Rekordbox.

**Download**:
Fetching **Tidal** tracks that have no audio file yet into the **Music folder**.

**Plan**:
The full list of changes a sync would make to Rekordbox (create, rename, move or delete playlists; add or remove tracks), computed without writing anything. Grouped per **Playlist**.
_Avoid_: dry run, preview, diff

**Apply**:
Executing the chosen groups of one **Plan** against Rekordbox. Always preceded by a **Backup**.

**Backup**:
A copy of Cratekeeper's database, plus the Rekordbox library files when taken right before an **Apply**.

## Flagged ambiguities

- "dry run" in v1 meant a partial simulation that still wrote to the database and skipped track removals. In Cratekeeper it is replaced by **Plan**, which writes nothing and lists every change.
- "sync" in v1 named three different commands. In Cratekeeper, sync means **Refresh** → **Download** → **Plan** → **Apply**.
- `in_local` in v1 meant "Bandcamp file", "Local track" and "has a file somewhere". Cratekeeper keeps these apart: **Bandcamp** files, **Local tracks**, and Tracks with a file.

## Example dialogue

> **Dev:** When I add a track to "🏢⬆️ Peak Time" on Tidal, what happens on the next sync?
> **DJ:** The **Refresh** sees the new **Track** in that **Playlist**. The **Download** fetches its file into the Playlist's **Music folder** sub-folder.
> **Dev:** And Rekordbox?
> **DJ:** The **Plan** lists "add track to Peak Time". Its **Folder placement** is Genre → Techno, from the 🏢 **Playlist emoji**. I check the Plan, then **Apply** it, and a **Backup** is taken first.
> **Dev:** And if I drop a file into that sub-folder by hand?
> **DJ:** It matches no Tidal track, so it becomes a **Local track** of Peak Time and joins its **Rekordbox membership**.
