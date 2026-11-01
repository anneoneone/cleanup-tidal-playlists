"""Create a demo Cratekeeper home with music files and an empty Rekordbox library.

Use it to try the UI without touching real data:

    python scripts/make_demo_home.py /tmp/ck-demo
    CRATEKEEPER_HOME=/tmp/ck-demo/home cratekeeper ui

Then run a sync with "offline" on: the Music folder sub-folders become Local
playlists and the Plan creates them in the demo Rekordbox library.
"""

import sys
from datetime import datetime
from pathlib import Path

from mutagen.id3 import ID3, TALB, TIT2, TPE1
from pyrekordbox.db6 import tables
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import Session

FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413
XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<MASTER_PLAYLIST Version="1.0.0" AutomaticSync="0">'
    '<PRODUCT Name="rekordbox" Version="6.8.0" Company="AlphaTheta"/>'
    "<PLAYLISTS/></MASTER_PLAYLIST>\n"
)
MUSIC = {
    "Peak Time 🏢⬆️": [("Rødhåd", "Target"), ("DVS1", "Pressure"), ("Kobosil", "Heat")],
    "Deep Nights 🌃": [("Kerri Chandler", "Rain"), ("Moodymann", "Shades")],
    "24-08-31 Openair 🎉": [
        ("Purple Disco Machine", "Hypnotized"),
        ("Folamour", "Joy"),
    ],
    "Italo Box 🇮🇹❓": [("Gazebo", "Lunatic"), ("Klein & MBO", "Dirty Talk")],
}
BANDCAMP = {
    "Peak Time 🏢⬆️": [("Dax J", "Offender")],
    "Dub Lab 🐋": [("Deepchord", "Vantage")],
}


def write_mp3(path: Path, artist: str, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(FRAME * 20)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text="Demo"))
    tags.save(path)


def make_library(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    db_path = folder / "master.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    for table in tables.Base.metadata.sorted_tables:
        copy = table.to_metadata(metadata)
        for column in copy.columns:
            if not column.primary_key:
                column.nullable = True
    metadata.create_all(engine)
    now = datetime.now()

    def filled(row):  # type: ignore[no-untyped-def]
        for column in row.__table__.columns:
            if getattr(row, column.key) is None and type(column.type).__name__ == (
                "DateTime"
            ):
                setattr(row, column.key, now)
        return row

    with Session(engine) as session:
        session.add(
            filled(tables.AgentRegistry(registry_id="localUpdateCount", int_1=1))
        )
        session.add(filled(tables.DjmdMenuItems(ID="1", Class=0, Name="TRACK")))
        session.add(filled(tables.DjmdDevice(ID="dev1", MasterDBID="m1", Name="demo")))
        session.commit()
    engine.dispose()
    (folder / "masterPlaylists6.xml").write_text(XML)
    return db_path


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ck-demo").resolve()
    if root.exists() and any(root.iterdir()):
        sys.exit(f"{root} is not empty")
    music = root / "music"
    for playlist, tracks in MUSIC.items():
        for artist, title in tracks:
            write_mp3(
                music / "Playlists" / playlist / f"{artist} - {title}.mp3",
                artist,
                title,
            )
    bandcamp = root / "bandcamp"
    for playlist, tracks in BANDCAMP.items():
        for artist, title in tracks:
            write_mp3(bandcamp / playlist / f"{artist} - {title}.mp3", artist, title)
    library = make_library(root / "rekordbox")
    home = root / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        f'music_folder = "{music}"\nbandcamp_folder = "{bandcamp}"\n'
        f'rekordbox_db = "{library}"\n'
    )
    print(f"Demo ready. Start it with:\n  CRATEKEEPER_HOME={home} cratekeeper ui")


if __name__ == "__main__":
    main()
