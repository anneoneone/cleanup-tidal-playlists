from pathlib import Path

import pytest

from cratekeeper.music.matching import Candidate, match_files
from cratekeeper.music.metadata import FileTags, read_file_tags
from cratekeeper.music.paths import (
    FolderMissingError,
    first_existing_file,
    list_audio_files,
    require_folder,
    simplify,
    to_stored_path,
)


def test_read_mp3_and_flac_tags(tmp_path: Path, make_mp3, make_flac) -> None:
    mp3 = make_mp3(
        tmp_path / "a.mp3",
        title="Song",
        artist="Artist",
        isrc="usabc1234567",
        url="https://tidal.com/browse/track/123",
    )
    flac = make_flac(
        tmp_path / "b.flac",
        title="Other",
        artist="Band",
        isrc="GBXYZ0000001",
        url="https://tidal.com/browse/track/456",
    )
    tags = read_file_tags(mp3)
    assert tags is not None
    assert (tags.title, tags.artist, tags.isrc) == ("Song", "Artist", "USABC1234567")
    assert tags.tidal_id == "123"
    flac_tags = read_file_tags(flac)
    assert flac_tags is not None
    assert (flac_tags.isrc, flac_tags.tidal_id) == ("GBXYZ0000001", "456")


def test_unreadable_file_gives_none(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"nope")
    assert read_file_tags(bad) is None


def test_paths_helpers(tmp_path: Path) -> None:
    music = tmp_path / "music"
    folder = music / "Playlists" / "Café"
    folder.mkdir(parents=True)
    (folder / "x.mp3").write_bytes(b"1")
    (folder / ".hidden.mp3").write_bytes(b"1")
    (folder / "notes.txt").write_text("x")
    assert [p.name for p in list_audio_files(folder)] == ["x.mp3"]
    assert to_stored_path(folder / "x.mp3", music) == "Playlists/Café/x.mp3"
    assert to_stored_path(Path("/elsewhere/y.mp3"), music) == "/elsewhere/y.mp3"
    assert first_existing_file(["missing.mp3", "Playlists/Café/x.mp3"], music) == (
        folder / "x.mp3"
    )
    assert simplify("Ünïcode & Co. (2024)") == "ünïcodeco2024"
    with pytest.raises(FolderMissingError, match="drive connected"):
        require_folder(tmp_path / "unplugged", "Music folder")


def candidate(track_id: int, artist: str, title: str, **kw: object) -> Candidate:
    return Candidate(
        track_id=track_id, tidal_id=str(track_id), artist=artist, title=title, **kw
    )  # type: ignore[arg-type]


def no_tags(path: Path) -> None:
    return None


def test_match_order_stored_path_then_tags_then_names() -> None:
    files = [Path(f"/m/{n}.mp3") for n in ("stored", "by isrc", "Artist A - Title A")]
    candidates = [
        candidate(1, "X", "Y", stored_paths=frozenset({"/m/stored.mp3"})),
        candidate(2, "Q", "R", isrc="ISRC2"),
        candidate(3, "Artist A", "Title A"),
    ]
    tags = {files[1]: FileTags(isrc="ISRC2")}
    result = match_files(files, candidates, str, lambda p: tags.get(p))
    assert result.matches == {files[0]: 1, files[1]: 2, files[2]: 3}
    assert result.reasons[files[1]] == "ISRC tag"
    assert result.unmatched == []


def test_name_rules_allow_extra_artists_and_version() -> None:
    files = [
        Path("/m/Main, Guest - Tune (Extended Mix).mp3"),
        Path("/m/main - tune2.flac"),
    ]
    candidates = [
        candidate(1, "Main", "Tune", version="Extended Mix"),
        candidate(2, "Main", "Tune2"),
    ]
    result = match_files(files, candidates, str, no_tags)
    assert result.matches == {files[0]: 1, files[1]: 2}


def test_ambiguous_or_unknown_files_stay_unmatched() -> None:
    files = [Path("/m/Artist - Song Something.mp3"), Path("/m/Nobody - Nothing.mp3")]
    candidates = [candidate(1, "Artist", "Song"), candidate(2, "Artist", "Something")]
    result = match_files(files, candidates, str, no_tags)
    assert result.matches == {}
    assert result.unmatched == files


def test_each_candidate_gets_one_file() -> None:
    files = [Path("/m/A - B.mp3"), Path("/m/A - B.flac")]
    result = match_files(files, [candidate(1, "A", "B")], str, no_tags)
    assert list(result.matches.values()) == [1]
    assert len(result.unmatched) == 1
