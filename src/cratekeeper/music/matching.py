"""Match audio files in a playlist folder to the playlist's Tidal tracks.

Order: stored path, ISRC tag, Tidal URL tag, then file name. A name match must be
unambiguous. tidal-dl-ng names files "<all artists> - <title incl. version>",
while the database keeps the main artist and the bare title, so name rules allow
extra artists and a version suffix.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .metadata import FileTags
from .paths import nfc, simplify


@dataclass(frozen=True)
class Candidate:
    """A Tidal track that may own a file in the folder."""

    track_id: int
    tidal_id: Optional[str]
    artist: str
    title: str
    version: Optional[str] = None
    isrc: Optional[str] = None
    stored_paths: frozenset[str] = field(default_factory=frozenset)


@dataclass
class MatchResult:
    """Which file belongs to which track, and how it was found."""

    matches: dict[Path, int] = field(default_factory=dict)
    reasons: dict[Path, str] = field(default_factory=dict)
    unmatched: list[Path] = field(default_factory=list)


TagReader = Callable[[Path], Optional[FileTags]]


def match_files(
    files: Iterable[Path],
    candidates: list[Candidate],
    stored_path_of: Callable[[Path], str],
    read_tags: TagReader,
) -> MatchResult:
    """Assign each file to at most one candidate, and each candidate one file."""
    result = MatchResult()
    by_stored: dict[str, Candidate] = {p: c for c in candidates for p in c.stored_paths}
    taken: set[int] = set()
    pending: list[Path] = []

    for path in files:
        candidate = by_stored.get(stored_path_of(path))
        if candidate is not None and candidate.track_id not in taken:
            _assign(result, taken, path, candidate, "stored path")
        else:
            pending.append(path)

    for path in pending:
        free = [c for c in candidates if c.track_id not in taken]
        candidate, reason = _match_one(path, free, read_tags)
        if candidate is None:
            result.unmatched.append(path)
        else:
            _assign(result, taken, path, candidate, reason)
    return result


def _assign(
    result: MatchResult, taken: set[int], path: Path, candidate: Candidate, why: str
) -> None:
    result.matches[path] = candidate.track_id
    result.reasons[path] = why
    taken.add(candidate.track_id)


def _match_one(
    path: Path, free: list[Candidate], read_tags: TagReader
) -> tuple[Optional[Candidate], str]:
    if not free:
        return None, ""
    tags = read_tags(path)
    if tags is not None:
        if tags.isrc:
            hits = [c for c in free if c.isrc and c.isrc.upper() == tags.isrc]
            if len(hits) == 1:
                return hits[0], "ISRC tag"
        if tags.tidal_id:
            hits = [c for c in free if c.tidal_id == tags.tidal_id]
            if len(hits) == 1:
                return hits[0], "Tidal URL tag"
    return _match_by_name(path.stem, free)


def expected_stems(candidate: Candidate) -> list[str]:
    """Return file stems tidal-dl-ng would likely produce, lower-cased."""
    stems = [f"{candidate.artist} - {candidate.title}"]
    if candidate.version:
        stems.append(f"{candidate.artist} - {candidate.title} ({candidate.version})")
    return [nfc(s).casefold() for s in stems]


def _match_by_name(stem: str, free: list[Candidate]) -> tuple[Optional[Candidate], str]:
    lowered = nfc(stem).casefold()
    hits = [c for c in free if lowered in expected_stems(c)]
    if len(hits) == 1:
        return hits[0], "file name"

    simple_stem = simplify(stem)
    hits = [c for c in free if simple_stem in {simplify(s) for s in expected_stems(c)}]
    if len(hits) == 1:
        return hits[0], "simplified file name"

    def loose(c: Candidate) -> bool:
        artist, title = simplify(c.artist), simplify(c.title)
        if not artist or not title or not simple_stem.startswith(artist):
            return False
        rest = simple_stem[len(artist) :]
        return title in rest and (not c.version or simplify(c.version) in rest)

    hits = [c for c in free if loose(c)]
    if len(hits) == 1:
        return hits[0], "file name with extra artists"
    return None, ""
