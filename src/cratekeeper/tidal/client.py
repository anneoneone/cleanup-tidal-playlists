"""Read playlists and tracks from Tidal."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def naive_utc(value: Any) -> Optional[datetime]:
    """Convert a datetime (or date) to naive UTC, as stored in SQLite."""
    if isinstance(value, datetime):
        moment: datetime = value
        if moment.tzinfo is not None:
            moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
        return moment
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return None


@dataclass(frozen=True)
class TidalPlaylist:
    """A user playlist on Tidal."""

    id: str
    name: str
    description: Optional[str] = None
    last_updated: Optional[datetime] = None
    created: Optional[datetime] = None
    num_tracks: Optional[int] = None
    num_videos: Optional[int] = None
    duration: Optional[int] = None
    creator_name: Optional[str] = None
    creator_id: Optional[str] = None
    popularity: Optional[int] = None
    public: Optional[bool] = None
    picture_url: Optional[str] = None
    square_picture_url: Optional[str] = None
    share_url: Optional[str] = None
    listen_url: Optional[str] = None
    last_item_added_at: Optional[datetime] = None


@dataclass(frozen=True)
class TidalTrack:
    """A track as listed in a Tidal playlist."""

    id: str
    title: str
    artist: str
    full_title: Optional[str] = None
    version: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    duration: Optional[int] = None
    track_number: Optional[int] = None
    volume_number: Optional[int] = None
    explicit: Optional[bool] = None
    isrc: Optional[str] = None
    copyright: Optional[str] = None
    popularity: Optional[int] = None
    release_date: Optional[datetime] = None
    album_upc: Optional[str] = None
    album_release_date: Optional[datetime] = None
    album_cover_url: Optional[str] = None
    audio_quality: Optional[str] = None
    audio_modes: Optional[str] = None
    date_added: Optional[datetime] = None


@dataclass(frozen=True)
class TrackListing:
    """All tracks of a playlist plus the count Tidal reports."""

    tracks: list[TidalTrack]
    expected_count: int

    @property
    def complete(self) -> bool:
        """Return whether every reported track was received."""
        return len(self.tracks) >= self.expected_count


class TidalClient:
    """Thin wrapper around a logged-in ``tidalapi.Session``."""

    def __init__(self, session: Any) -> None:
        """Wrap ``session``."""
        self.session = session

    def playlists(self) -> list[TidalPlaylist]:
        """Return the playlists the user created (same scope as v1)."""
        return [to_playlist(raw) for raw in self.session.user.playlists()]

    def playlist_tracks(self, playlist_id: str) -> TrackListing:
        """Return all tracks of a playlist, using pagination (no 1000-track cap)."""
        playlist = self.session.playlist(playlist_id)
        expected = int(playlist.get_tracks_count())
        raw_tracks = playlist.tracks_paginated() if expected else []
        tracks = [to_track(raw) for raw in raw_tracks if raw is not None]
        return TrackListing(tracks=tracks, expected_count=expected)


def to_playlist(raw: Any) -> TidalPlaylist:
    """Convert a tidalapi playlist."""
    creator = getattr(raw, "creator", None)

    def text(name: str) -> Optional[str]:
        value = getattr(raw, name, None)
        return str(value) if isinstance(value, (str, int)) else None

    def number(name: str) -> Optional[int]:
        value = getattr(raw, name, None)
        return int(value) if isinstance(value, (int, float)) else None

    picture = getattr(raw, "picture", None)
    square = getattr(raw, "square_picture", None)
    return TidalPlaylist(
        id=str(raw.id),
        name=str(raw.name),
        description=text("description"),
        last_updated=naive_utc(getattr(raw, "last_updated", None)),
        created=naive_utc(getattr(raw, "created", None)),
        num_tracks=number("num_tracks"),
        num_videos=number("num_videos"),
        duration=number("duration"),
        creator_name=getattr(creator, "name", None) if creator else None,
        creator_id=(
            str(creator.id) if creator and getattr(creator, "id", None) else None
        ),
        popularity=number("popularity"),
        public=getattr(raw, "public", None),
        picture_url=_image(picture),
        square_picture_url=_image(square, square=True),
        share_url=text("share_url"),
        listen_url=text("listen_url"),
        last_item_added_at=naive_utc(getattr(raw, "last_item_added_at", None)),
    )


def to_track(raw: Any) -> TidalTrack:
    """Convert a tidalapi track (fields as v1 ``state_fetcher`` stored them)."""
    album = getattr(raw, "album", None)
    artist = getattr(raw, "artist", None)
    album_artist = getattr(album, "artist", None) if album else None
    album_id = getattr(album, "id", None) if album else None
    modes = getattr(raw, "audio_modes", None)

    def value(name: str, kind: type) -> Any:
        found = getattr(raw, name, None)
        return found if isinstance(found, kind) else None

    return TidalTrack(
        id=str(raw.id),
        title=str(raw.name),
        artist=str(getattr(artist, "name", None) or "Unknown"),
        full_title=value("full_name", str),
        version=value("version", str) or None,
        album=getattr(album, "name", None) if album else None,
        album_artist=getattr(album_artist, "name", None) if album_artist else None,
        duration=value("duration", int),
        track_number=value("track_num", int) or value("track_number", int),
        volume_number=value("volume_num", int) or value("volume_number", int),
        explicit=value("explicit", bool),
        isrc=(value("isrc", str) or "").upper() or None,
        copyright=value("copyright", str),
        popularity=value("popularity", int),
        release_date=naive_utc(getattr(raw, "tidal_release_date", None)),
        album_upc=(
            getattr(album, "universal_product_number", None)
            or getattr(album, "upc", None)
            if album
            else None
        ),
        album_release_date=(
            naive_utc(getattr(album, "release_date", None)) if album else None
        ),
        album_cover_url=(
            "https://resources.tidal.com/images/"
            f"{str(album_id).replace('-', '/')}/640x640.jpg"
            if album_id
            else None
        ),
        audio_quality=str(getattr(raw, "audio_quality", "") or "") or None,
        audio_modes=str(modes) if modes else None,
        date_added=naive_utc(getattr(raw, "user_date_added", None)),
    )


def _image(picture_id: Any, square: bool = False) -> Optional[str]:
    if not isinstance(picture_id, str) or not picture_id:
        return None
    size = "640x640" if square else "750x500"
    return (
        f"https://resources.tidal.com/images/{picture_id.replace('-', '/')}/{size}.jpg"
    )
