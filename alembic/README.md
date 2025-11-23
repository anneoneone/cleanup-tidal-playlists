# Database Migrations with Alembic

This directory contains Alembic database migrations for the tidal-cleanup project.

## Setup

Alembic is already configured and ready to use. The configuration is in `alembic.ini` at the project root.

## Creating Migrations

### Auto-generate Migration from Model Changes

After modifying models in `src/tidal_cleanup/database/models.py`:

```bash
alembic revision --autogenerate -m "Description of changes"
```

This will create a new migration file in `alembic/versions/`.

### Create Empty Migration

For custom migrations (data migrations, complex changes):

```bash
alembic revision -m "Description of changes"
```

## Applying Migrations

### Upgrade to Latest Version

```bash
alembic upgrade head
```

### Upgrade to Specific Version

```bash
alembic upgrade <revision_id>
```

### Show Current Version

```bash
alembic current
```

### Show Migration History

```bash
alembic history --verbose
```

## Downgrading

### Downgrade One Version

```bash
alembic downgrade -1
```

### Downgrade to Specific Version

```bash
alembic downgrade <revision_id>
```

### Downgrade All (back to empty database)

```bash
alembic downgrade base
```

## Migration for Unified Sync Fields

The initial migration `987ed04d1693_add_unified_sync_fields_for_tidal_.py` includes:

### Track Model

- `download_status` - Track download state (not_downloaded, downloading, downloaded, error)
- `download_error` - Error message if download failed
- `downloaded_at` - When file was successfully downloaded
- `last_verified_at` - Last integrity verification timestamp

### Playlist Model

- `sync_status` - Playlist sync state (in_sync, needs_download, needs_update, needs_removal, unknown)
- `last_updated_tidal` - When playlist was last modified in Tidal
- `last_synced_filesystem` - When playlist was last synced to filesystem

### PlaylistTrack Model

- `is_primary` - True if this playlist has the primary file (not a symlink)
- `symlink_path` - Path to symlink if not primary
- `symlink_valid` - False if symlink is broken
- `sync_status` - Track sync state in playlist (synced, needs_symlink, needs_move, needs_removal, unknown)
- `synced_at` - When this playlist-track relationship was last synced

## Database URL Configuration

The default database URL is set in `alembic.ini`:

```ini
sqlalchemy.url = sqlite:///tidal_cleanup.db
```

You can override this with the `TIDAL_CLEANUP_DB_URL` environment variable:

```bash
export TIDAL_CLEANUP_DB_URL=sqlite:///path/to/custom.db
alembic upgrade head
```

## Troubleshooting

### "Can't locate revision identified by"

This usually means the database's alembic_version table doesn't match the migration files. To reset:

```bash
# Check current version
alembic current

# If stuck, manually set to base
alembic stamp base

# Then upgrade
alembic upgrade head
```

### Migration Conflicts

If you have local changes that conflict with migrations:

1. Check the migration file in `alembic/versions/`
2. Edit if needed (Alembic auto-generate isn't perfect)
3. Test with: `alembic upgrade head --sql` (shows SQL without executing)
4. Apply: `alembic upgrade head`

## Best Practices

1. **Always review auto-generated migrations** - Alembic doesn't catch everything
2. **Test migrations on a copy of your database first**
3. **Never edit old migrations** - Create new ones instead
4. **Keep migrations small and focused** - One logical change per migration
5. **Write descriptive migration messages** - Your future self will thank you

## Related Documentation

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Unified Sync Architecture](../docs/UNIFIED_SYNC_ARCHITECTURE.md)
- [Model Changes Documentation](../docs/MODEL_CHANGES_FOR_SYNC.md)
