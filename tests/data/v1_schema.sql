CREATE TABLE tracks (
	id INTEGER NOT NULL,
	tidal_id VARCHAR(255),
	title VARCHAR(500) NOT NULL,
	artist VARCHAR(500) NOT NULL,
	album VARCHAR(500),
	album_artist VARCHAR(500),
	year INTEGER,
	genre VARCHAR(100),
	duration INTEGER,
	isrc VARCHAR(20),
	track_number INTEGER,
	volume_number INTEGER,
	explicit BOOLEAN,
	popularity INTEGER,
	copyright TEXT,
	tidal_release_date DATETIME,
	audio_quality VARCHAR(50),
	audio_modes VARCHAR(100),
	version VARCHAR(200),
	album_upc VARCHAR(50),
	album_release_date DATETIME,
	album_cover_url VARCHAR(500),
	normalized_name VARCHAR(1000) NOT NULL,
	file_paths JSON,
	file_size_bytes INTEGER,
	file_format VARCHAR(10),
	file_hash VARCHAR(64),
	file_last_modified DATETIME,
	download_status VARCHAR(20) NOT NULL,
	download_error TEXT,
	downloaded_at DATETIME,
	last_verified_at DATETIME,
	tidal_unavailable BOOLEAN NOT NULL,
	rekordbox_content_id VARCHAR(255),
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	last_seen_in_tidal DATETIME,
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_tracks_tidal_id ON tracks (tidal_id);
CREATE INDEX ix_tracks_tidal_unavailable ON tracks (tidal_unavailable);
CREATE INDEX ix_tracks_download_status ON tracks (download_status);
CREATE INDEX idx_normalized_name ON tracks (normalized_name);
CREATE INDEX ix_tracks_normalized_name ON tracks (normalized_name);
CREATE INDEX idx_artist_title ON tracks (artist, title);
CREATE TABLE playlists (
	id INTEGER NOT NULL,
	tidal_id VARCHAR(255),
	source VARCHAR(20) NOT NULL,
	name VARCHAR(500) NOT NULL,
	description TEXT,
	creator_name VARCHAR(200),
	creator_id VARCHAR(100),
	duration INTEGER,
	num_tracks INTEGER,
	num_videos INTEGER,
	popularity INTEGER,
	public BOOLEAN,
	picture_url VARCHAR(500),
	square_picture_url VARCHAR(500),
	created DATETIME,
	last_updated DATETIME,
	last_item_added_at DATETIME,
	share_url VARCHAR(500),
	listen_url VARCHAR(500),
	local_folder_path VARCHAR(1000),
	rekordbox_playlist_id VARCHAR(255),
	sync_status VARCHAR(20) NOT NULL,
	last_updated_tidal DATETIME,
	last_synced_filesystem DATETIME,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	last_synced_at DATETIME,
	last_seen_in_tidal DATETIME,
	track_count_tidal INTEGER NOT NULL,
	track_count_local INTEGER NOT NULL,
	track_count_rekordbox INTEGER NOT NULL,
	PRIMARY KEY (id)
);
CREATE INDEX ix_playlists_sync_status ON playlists (sync_status);
CREATE INDEX ix_playlists_name ON playlists (name);
CREATE UNIQUE INDEX ix_playlists_tidal_id ON playlists (tidal_id);
CREATE INDEX ix_playlists_source ON playlists (source);
CREATE TABLE sync_snapshots (
	id INTEGER NOT NULL,
	snapshot_type VARCHAR(20) NOT NULL,
	snapshot_data TEXT NOT NULL,
	playlist_count INTEGER,
	track_count INTEGER,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);
CREATE INDEX idx_type_created ON sync_snapshots (snapshot_type, created_at);
CREATE TABLE rekordbox_folders (
	id INTEGER NOT NULL,
	folder_path VARCHAR(500) NOT NULL,
	rekordbox_folder_id VARCHAR(255) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_rekordbox_folders_folder_path ON rekordbox_folders (folder_path);
CREATE TABLE playlist_tracks (
	id INTEGER NOT NULL,
	playlist_id INTEGER NOT NULL,
	track_id INTEGER NOT NULL,
	position INTEGER,
	in_tidal BOOLEAN NOT NULL,
	in_local BOOLEAN NOT NULL,
	in_rekordbox BOOLEAN NOT NULL,
	sync_status VARCHAR(20) NOT NULL,
	synced_at DATETIME,
	added_to_tidal DATETIME,
	added_to_local DATETIME,
	added_to_rekordbox DATETIME,
	removed_from_tidal DATETIME,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_playlist_track UNIQUE (playlist_id, track_id),
	FOREIGN KEY(playlist_id) REFERENCES playlists (id) ON DELETE CASCADE,
	FOREIGN KEY(track_id) REFERENCES tracks (id) ON DELETE CASCADE
);
CREATE INDEX idx_playlist ON playlist_tracks (playlist_id);
CREATE INDEX idx_sync_state ON playlist_tracks (in_tidal, in_local, in_rekordbox);
CREATE INDEX idx_track ON playlist_tracks (track_id);
CREATE INDEX ix_playlist_tracks_sync_status ON playlist_tracks (sync_status);
CREATE TABLE sync_operations (
	id INTEGER NOT NULL,
	operation_type VARCHAR(50) NOT NULL,
	status VARCHAR(20) NOT NULL,
	playlist_id INTEGER,
	track_id INTEGER,
	action VARCHAR(50),
	source VARCHAR(20),
	target VARCHAR(20),
	details TEXT,
	error_message TEXT,
	created_at DATETIME NOT NULL,
	started_at DATETIME,
	completed_at DATETIME,
	PRIMARY KEY (id),
	FOREIGN KEY(playlist_id) REFERENCES playlists (id) ON DELETE CASCADE,
	FOREIGN KEY(track_id) REFERENCES tracks (id) ON DELETE CASCADE
);
CREATE INDEX ix_sync_operations_created_at ON sync_operations (created_at);
CREATE INDEX ix_sync_operations_operation_type ON sync_operations (operation_type);
CREATE INDEX ix_sync_operations_status ON sync_operations (status);
CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL,
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
