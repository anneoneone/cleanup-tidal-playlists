"""Read the tracks and playlists of a Rekordbox USB export (``export.pdb``). Read-only.

The file uses Rekordbox's DeviceSQL format. The layout follows the Deep Symmetry
analysis: https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/exports.html
Only the tracks, artists, playlist tree and playlist entries tables are read.
"""

from __future__ import annotations

import struct
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

TRACKS_TABLE = 0
ARTISTS_TABLE = 2
PLAYLIST_TREE_TABLE = 7
PLAYLIST_ENTRIES_TABLE = 8

_TABLES_START = 0x1C  # table pointers in the file header
_ROWS_START = 0x28  # rows follow the page header
_ROW_GROUP = 0x24  # 16 row offsets, a "present" bit field and 2 padding bytes
_PAGE_IS_INDEX = 0x40  # page flag: index page, no rows

# Track row: fixed fields, then 21 string offsets (relative to the row start)
_TRACK_FILE_SIZE = 0x10
_TRACK_ARTIST_ID = 0x44  # followed by the track ID
_TRACK_STRINGS = 0x5E
_ISRC, _TITLE, _FILE_NAME, _FILE_PATH = 0, 17, 19, 20

# Artist row subtypes: name offset as 1 byte at 0x09, or as 2 bytes at 0x0A
_ARTIST_NEAR, _ARTIST_FAR = 0x60, 0x64

# Playlist tree row: parent ID, unknown, sort order, ID, folder flag, then the name.
# Playlist entry row: position in the playlist, track ID, playlist ID.
_TREE_NAME = 0x14


class ExportError(ValueError):
    """Raised when an ``export.pdb`` file cannot be read."""


@dataclass(frozen=True)
class ExportTrack:
    """One track in a USB export."""

    title: str
    artist: str
    isrc: str
    file_name: str
    file_path: str  # on the stick, e.g. "/Contents/Artist/Album/file.mp3"
    file_size: int


@dataclass(frozen=True)
class ExportPlaylist:
    """One playlist in a USB export (folders are not listed)."""

    name: str
    folder: tuple[str, ...]  # folder names from the top, e.g. ("Genre", "House")
    tracks: tuple[ExportTrack, ...]  # in playlist order


@dataclass(frozen=True)
class Export:
    """The tracks and playlists in a USB export."""

    tracks: list[ExportTrack]
    playlists: list[ExportPlaylist]


def read_export(path: Path) -> Export:
    """Return the tracks and playlists in an ``export.pdb`` file.

    Raises:
        ExportError: The file is not a readable export.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ExportError(f"Cannot open {path}: {exc}") from exc
    try:
        return _Reader(data).export()
    except (struct.error, IndexError) as exc:
        raise ExportError(f"{path} is damaged or not an export.pdb file") from exc


class _Reader:
    def __init__(self, data: bytes) -> None:
        if len(data) < _TABLES_START:
            raise ExportError("File is too short for an export.pdb file")
        zero, page_size, table_count = struct.unpack_from("<3I", data, 0)
        if zero != 0 or page_size < 512 or len(data) < page_size:
            raise ExportError("File is not an export.pdb file")
        self.data = data
        self.page_size = page_size
        self.tables: dict[int, tuple[int, int]] = {}
        for index in range(table_count):
            kind, _empty, first, last = struct.unpack_from(
                "<4I", data, _TABLES_START + 16 * index
            )
            self.tables[kind] = (first, last)

    def export(self) -> Export:
        tracks = []
        by_id: dict[int, ExportTrack] = {}
        for track_id, track in self._tracks():
            tracks.append(track)
            by_id[track_id] = track
        return Export(tracks=tracks, playlists=self._playlists(by_id))

    def _tracks(self) -> Iterator[tuple[int, ExportTrack]]:
        artists = dict(self._artists())
        for row in self._rows(TRACKS_TABLE):
            strings = struct.unpack_from("<21H", self.data, row + _TRACK_STRINGS)
            artist_id, track_id = struct.unpack_from(
                "<2I", self.data, row + _TRACK_ARTIST_ID
            )
            (file_size,) = struct.unpack_from("<I", self.data, row + _TRACK_FILE_SIZE)
            yield track_id, ExportTrack(
                title=self._string(row + strings[_TITLE]),
                artist=artists.get(artist_id, ""),
                isrc=self._string(row + strings[_ISRC]),
                file_name=self._string(row + strings[_FILE_NAME]),
                file_path=self._string(row + strings[_FILE_PATH]),
                file_size=file_size,
            )

    def _playlists(self, tracks: dict[int, ExportTrack]) -> list[ExportPlaylist]:
        nodes: dict[int, tuple[int, bool, str]] = {}  # ID: parent ID, folder, name
        for row in self._rows(PLAYLIST_TREE_TABLE):
            parent, _, _, node_id, folder = struct.unpack_from("<5I", self.data, row)
            nodes[node_id] = (parent, folder != 0, self._string(row + _TREE_NAME))
        entries: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for row in self._rows(PLAYLIST_ENTRIES_TABLE):
            position, track_id, node_id = struct.unpack_from("<3I", self.data, row)
            entries[node_id].append((position, track_id))
        playlists = []
        for node_id, (parent, folder, name) in nodes.items():
            if folder:
                continue
            # An entry for a track that is not in the export is skipped
            items = [tracks[t] for _, t in sorted(entries[node_id]) if t in tracks]
            playlists.append(
                ExportPlaylist(
                    name=name, folder=_folder(parent, nodes), tracks=tuple(items)
                )
            )
        return playlists

    def _artists(self) -> Iterator[tuple[int, str]]:
        for row in self._rows(ARTISTS_TABLE):
            subtype, _shift, artist_id = struct.unpack_from("<HHI", self.data, row)
            if subtype == _ARTIST_FAR:
                (offset,) = struct.unpack_from("<H", self.data, row + 0x0A)
            elif subtype == _ARTIST_NEAR:
                offset = self.data[row + 0x09]
            else:
                continue
            yield artist_id, self._string(row + offset)

    def _rows(self, table: int) -> Iterator[int]:
        """Yield the file position of every row in ``table``."""
        if table not in self.tables:
            raise ExportError(f"Table {table} is missing")
        page, last = self.tables[table]
        seen: set[int] = set()
        while page not in seen:
            seen.add(page)
            start = page * self.page_size
            if start + self.page_size > len(self.data):
                raise ExportError(f"Page {page} is outside the file")
            index, kind, next_page = struct.unpack_from("<3I", self.data, start + 4)
            if index != page or kind != table:
                raise ExportError(f"Page {page} is damaged")
            yield from self._page_rows(start)
            if page == last:
                return
            page = next_page

    def _page_rows(self, start: int) -> Iterator[int]:
        flags = self.data[start + 0x1B]
        if flags & _PAGE_IS_INDEX:
            return
        # Lower 13 bits: row offsets in the page (deleted rows included)
        offsets = int.from_bytes(self.data[start + 0x18 : start + 0x1B], "little")
        offsets &= 0x1FFF
        end = start + self.page_size
        for group in range((offsets + 15) // 16):
            base = end - group * _ROW_GROUP
            (present,) = struct.unpack_from("<H", self.data, base - 4)
            for slot in range(min(16, offsets - group * 16)):
                if present >> slot & 1:
                    (offset,) = struct.unpack_from("<H", self.data, base - 6 - 2 * slot)
                    row = start + _ROWS_START + offset
                    if row >= end:
                        raise ExportError("A row points outside its page")
                    yield row

    def _string(self, pos: int) -> str:
        """Decode a DeviceSQL string."""
        kind = self.data[pos]
        if kind & 1:  # short ASCII: length (with this byte) in the upper 7 bits
            return self.data[pos + 1 : pos + (kind >> 1)].decode("ascii", "replace")
        (length,) = struct.unpack_from("<H", self.data, pos + 1)
        raw = self.data[pos + 4 : pos + length]
        if kind == 0x40:
            return raw.decode("ascii", "replace")
        if kind == 0x90:
            if raw[:1] == b"\x03":  # ISRC: a marker byte, ASCII, then a 0 byte
                return raw[1:].split(b"\0", 1)[0].decode("ascii", "replace")
            return raw.decode("utf-16-le", "replace")
        return ""


def _folder(parent: int, nodes: dict[int, tuple[int, bool, str]]) -> tuple[str, ...]:
    """Return the folder names from the top down to ``parent`` (0 is the top)."""
    names: list[str] = []
    while parent != 0:
        if parent not in nodes or len(names) > len(nodes):
            raise ExportError("The playlist tree is damaged")
        parent, _, name = nodes[parent]
        names.append(name)
    return tuple(reversed(names))
