from tidal_cleanup.config import Config
from tidal_cleanup.database.service import DatabaseService

config = Config()
db_service = DatabaseService(db_path=config.database_path)

track_ids = [24, 1338]
for track_id in track_ids:
    track = db_service.get_track_by_id(track_id)
    if not track:
        print(f"Track {track_id} not found")
        continue
    print(f"Track {track_id}: {track.artist} - {track.title}")
    print(f"  File paths: {track.file_paths}")
