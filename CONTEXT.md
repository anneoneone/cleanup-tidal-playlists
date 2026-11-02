# Cratekeeper

Cratekeeper keeps a DJ's Rekordbox library in line with the playlists they curate on Tidal and in Bandcamp folders.

## Language

### Where music comes from

**Source**:
A place that defines playlists and their tracks: **Tidal**, **Bandcamp** or the **Library**.
_Avoid_: provider, service, origin

**Tidal**:
The streaming **Source**. Its playlists are read through the Tidal API, and its tracks are fetched by a **Download**.

**Bandcamp**:
The **Source** of purchased files: a folder tree where each sub-folder is one **Playlist**.
_Avoid_: local playlists, local-only tracks

**Music folder**:
The folder on disk that holds the audio files for **Tidal** tracks, with one sub-folder per **Playlist**. A Playlist keeps its sub-folder when it is renamed.
_Avoid_: mp3 directory

**Library**:
The **Source** of files you put into the **Music folder** yourself: every file there that matches no **Tidal** track.
_Avoid_: local (the v1 word)

**Library playlist**:
A **Music folder** sub-folder that belongs to no **Tidal** playlist (e.g. a party or radio set put together by hand). All its files are **Library tracks**.
_Avoid_: local playlist, custom playlist

**Library track**:
An audio file in a **Playlist**'s **Music folder** sub-folder that matches no **Tidal** track. It belongs to that Playlist like any other **Track**. A Tidal track is never a Library track.
_Avoid_: local track, orphan file

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
The **Tracks** a **Playlist** should have in Rekordbox: those currently in the Tidal playlist that have a file, plus its **Bandcamp** files, plus its **Library tracks**. A Track removed from Tidal leaves the Rekordbox playlist; its file stays on disk.

**Unsynced**:
A **Track** that was removed from every **Source** of a **Playlist** but is still on disk or still in the Rekordbox playlist. On a **USB stick**, a Track is unsynced when no Playlist has it in a Source any more, because a stick holds tracks, not playlists.

**USB stick**:
A USB stick or SD card with a Rekordbox export (`PIONEER/rekordbox/export.pdb`) for DJ players. Known by its volume ID, shown by its volume name (S1, S2, …). A **Track** is on a stick when the export has the same file (name and size) or the same ISRC, else the same artist and title.
_Avoid_: device, drive, export (alone)

**Stick scan**:
Reading the export of every plugged-in **USB stick** into Cratekeeper's database. Never writes to a stick. A stick that is not plugged in keeps its last scan.

**File missing**:
A **Track** that should have a file and had one, but the file is gone (e.g. deleted by hand).

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
- `in_local` in v1 meant "Bandcamp file", "Local track" and "has a file somewhere". Cratekeeper keeps these apart: **Bandcamp** files, **Library tracks**, and Tracks with a file.
- "Library" alone means the **Source**. Rekordbox's own collection is always called the "Rekordbox library".

## Example dialogue

> **Dev:** When I add a track to "🏢⬆️ Peak Time" on Tidal, what happens on the next sync?
> **DJ:** The **Refresh** sees the new **Track** in that **Playlist**. The **Download** fetches its file into the Playlist's **Music folder** sub-folder.
> **Dev:** And Rekordbox?
> **DJ:** The **Plan** lists "add track to Peak Time". Its **Folder placement** is Genre → Techno, from the 🏢 **Playlist emoji**. I check the Plan, then **Apply** it, and a **Backup** is taken first.
> **Dev:** And if I drop a file into that sub-folder by hand?
> **DJ:** It matches no Tidal track, so it becomes a **Library track** of Peak Time and joins its **Rekordbox membership**.
