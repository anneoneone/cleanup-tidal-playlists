from tidal_cleanup.database.service import DatabaseService

tidal_id = 5

db = DatabaseService()  # defaults to ~/.tidal-cleanup/sync.db
track = db.get_track_by_id(tidal_id)  # replace with your track ID
print(f"Before: {track}")
db.add_file_path_to_track(tidal_id, "/full/path/to/file.flac")
db.close()
