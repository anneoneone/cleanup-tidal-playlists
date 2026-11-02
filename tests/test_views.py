from typing import Any, Optional

import pytest

from cratekeeper.api.views import track_state
from cratekeeper.db import PlaylistTrack, Track


def make(
    *,
    tidal_id: Optional[str] = "t1",
    in_tidal: bool = False,
    in_bandcamp: bool = False,
    in_local: bool = False,
    in_rekordbox: bool = False,
    downloaded: bool = False,
) -> tuple[PlaylistTrack, Track]:
    track = Track(
        tidal_id=tidal_id,
        title="T",
        artist="A",
        download_status="downloaded" if downloaded else "not_downloaded",
    )
    row = PlaylistTrack(
        in_tidal=in_tidal,
        in_bandcamp=in_bandcamp,
        in_local=in_local,
        in_rekordbox=in_rekordbox,
    )
    return row, track


@pytest.mark.parametrize(
    ("kwargs", "has_file", "expected"),
    [
        # In Tidal, not downloaded yet
        ({"in_tidal": True}, False, (["tidal"], "absent", "absent")),
        # Downloaded and in Rekordbox
        (
            {"in_tidal": True, "in_rekordbox": True, "downloaded": True},
            True,
            (["tidal"], "present", "present"),
        ),
        # Downloaded once, file gone, still in Rekordbox
        (
            {"in_tidal": True, "in_rekordbox": True, "downloaded": True},
            False,
            (["tidal"], "missing", "present"),
        ),
        # Removed from Tidal, file and Rekordbox entry still there
        (
            {"in_rekordbox": True, "downloaded": True},
            True,
            ([], "unsynced", "unsynced"),
        ),
        # Removed from Tidal and file gone: nothing left to report
        ({"downloaded": True}, False, ([], "absent", "absent")),
        # v1 marked a Tidal track as local: it is never a Library track
        ({"in_tidal": True, "in_local": True}, True, (["tidal"], "present", "absent")),
        # Library track (no Tidal ID)
        (
            {"tidal_id": None, "in_local": True},
            True,
            (["library"], "present", "absent"),
        ),
        # Bandcamp track in Rekordbox
        (
            {"tidal_id": None, "in_bandcamp": True, "in_rekordbox": True},
            True,
            (["bandcamp"], "present", "present"),
        ),
    ],
)
def test_track_state(
    kwargs: dict[str, Any], has_file: bool, expected: tuple[Any, ...]
) -> None:
    row, track = make(**kwargs)
    state = track_state(row, track, has_file)
    assert (state.sources, state.download, state.rekordbox) == expected


def test_track_state_on_sticks() -> None:
    sticks = [(1, "S1"), (2, "S2")]
    row, track = make(in_tidal=True, downloaded=True)
    state = track_state(row, track, True, sticks)
    assert [(s.name, s.state) for s in state.sticks] == [
        ("S1", "present"),
        ("S2", "present"),
    ]

    row, track = make(downloaded=True)  # removed from the Playlist's Sources
    state = track_state(row, track, True, sticks[:1])
    assert [(s.id, s.state) for s in state.sticks] == [(1, "unsynced")]
    assert track_state(row, track, True).sticks == []
