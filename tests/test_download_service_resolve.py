from pathlib import Path

from tidal_cleanup.core.tidal.download_service import TidalDownloadService


def make_service() -> TidalDownloadService:
    return TidalDownloadService.__new__(TidalDownloadService)


def test_resolves_extension_mismatch(tmp_path: Path):
    """Reported .flac path resolves to the .m4a actually written to disk."""
    svc = make_service()
    real = tmp_path / "North 90 - Shogun.m4a"
    real.write_bytes(b"audio")

    reported = tmp_path / "North 90 - Shogun.flac"
    assert not reported.exists()

    assert svc._resolve_downloaded_file(reported) == real


def test_returns_none_when_no_sibling(tmp_path: Path):
    svc = make_service()
    reported = tmp_path / "Missing - Track.flac"

    assert svc._resolve_downloaded_file(reported) is None


def test_returns_none_when_directory_missing(tmp_path: Path):
    svc = make_service()
    reported = tmp_path / "no-such-dir" / "Track.flac"

    assert svc._resolve_downloaded_file(reported) is None


def test_prefers_extension_order(tmp_path: Path):
    """When multiple siblings exist, flac wins per preference order."""
    svc = make_service()
    (tmp_path / "Track.m4a").write_bytes(b"a")
    (tmp_path / "Track.flac").write_bytes(b"b")

    reported = tmp_path / "Track.mp3"
    assert svc._resolve_downloaded_file(reported) == tmp_path / "Track.flac"
