# Tidal-dl-ng Configuration Reference

This document describes all available configuration options for the tidal-dl-ng download feature.

## Configuration File Location

`config/tidal_dl_ng.json`

## Audio Quality Options

The `quality_audio` setting accepts the following values (from tidalapi):

| Value | Description | Bitrate/Format |
|-------|-------------|----------------|
| `LOW` | Low quality (96k) | ~96 kbps AAC |
| `HIGH` | High quality (320k) | ~320 kbps AAC |
| `LOSSLESS` | CD quality lossless | 16-bit/44.1kHz FLAC |
| `HI_RES_LOSSLESS` | High-resolution lossless | 24-bit/96kHz+ FLAC (MQA) |

**Recommendation**: Use `HI_RES_LOSSLESS` for DJ use to ensure maximum quality.

## Video Quality Options

The `quality_video` setting accepts:

| Value | Description |
|-------|-------------|
| `LOW` | Low resolution |
| `MEDIUM` | Medium resolution |
| `HIGH` | High resolution |
| `AUDIO_ONLY` | Extract audio only |

Or numeric values like `"480"`, `"720"`, `"1080"` for specific resolutions.

## All Configuration Options

### Core Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `download_base_path` | string | `"./m4a"` | Base directory for downloads |
| `skip_existing` | boolean | `true` | Skip files that already exist |
| `path_binary_ffmpeg` | string | `"/opt/homebrew/bin/ffmpeg"` | Path to ffmpeg binary |

### Quality Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `quality_audio` | string | `"HI_RES_LOSSLESS"` | Audio quality (see table above) |
| `quality_video` | string | `"480"` | Video quality/resolution |

### Video Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `video_download` | boolean | `false` | Enable video downloads |
| `video_convert_mp4` | boolean | `false` | Convert videos to MP4 format |

### Lyrics Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `lyrics_embed` | boolean | `false` | Embed lyrics in audio files |
| `lyrics_file` | boolean | `false` | Save lyrics as separate .lrc files |

### Download Control

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `download_delay` | boolean | `true` | Add delay between downloads |
| `download_delay_sec_min` | float | `3.0` | Minimum delay in seconds |
| `download_delay_sec_max` | float | `5.0` | Maximum delay in seconds |
| `downloads_concurrent_max` | integer | `3` | Max concurrent downloads |
| `downloads_simultaneous_per_track_max` | integer | `20` | Max simultaneous track segments |

**Note**: The download delays help avoid rate limiting from Tidal's servers.

### File Naming Templates

All templates support the following variables:

**Common Variables**:

- `{artist_name}` - Track artist name
- `{track_title}` - Track title
- `{album_artist}` - Album artist name
- `{album_title}` - Album title
- `{album_track_num}` - Track number (padded)
- `{track_volume_num_optional}` - Volume number (if multi-disc)
- `{track_explicit}` / `{album_explicit}` - Explicit marker (if enabled)

**Playlist/Mix Variables**:

- `{playlist_name}` - Playlist name
- `{mix_name}` - Mix name

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `format_album` | string | See below | Album track filename template |
| `format_playlist` | string | `"Playlists/{playlist_name}/{artist_name} - {track_title}"` | Playlist track filename template |
| `format_mix` | string | `"Mix/{mix_name}/{artist_name} - {track_title}"` | Mix track filename template |
| `format_track` | string | `"Tracks/{artist_name} - {track_title}{track_explicit}"` | Individual track filename template |
| `format_video` | string | `"Videos/{artist_name} - {track_title}{track_explicit}"` | Video filename template |

**Default `format_album`**:

```
Albums/{album_artist} - {album_title}{album_explicit}/{track_volume_num_optional}{album_track_num}. {artist_name} - {track_title}{album_explicit}
```

### Metadata Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `metadata_cover_dimension` | integer | `320` | Album art size in pixels |
| `metadata_cover_embed` | boolean | `true` | Embed album art in files |
| `metadata_replay_gain` | boolean | `false` | Calculate and write ReplayGain tags |
| `metadata_write_url` | boolean | `true` | Write Tidal URL to metadata |
| `metadata_delimiter_artist` | string | `", "` | Delimiter for multiple artists in metadata |
| `metadata_delimiter_album_artist` | string | `", "` | Delimiter for multiple album artists |
| `metadata_target_upc` | string | `"UPC"` | UPC target field name |

### Filename Delimiters

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `filename_delimiter_artist` | string | `", "` | Delimiter for multiple artists in filenames |
| `filename_delimiter_album_artist` | string | `", "` | Delimiter for multiple album artists in filenames |

### Additional Options

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `mark_explicit` | boolean | `false` | Add explicit markers to filenames |
| `cover_album_file` | boolean | `true` | Save album art as separate file |
| `extract_flac` | boolean | `false` | Extract FLAC from MQA containers |
| `album_track_num_pad_min` | integer | `1` | Minimum padding for track numbers |
| `symlink_to_track` | boolean | `false` | Create symlinks to tracks |
| `playlist_create` | boolean | `false` | Create M3U playlist files |

## Example Configurations

### DJ Setup (High Quality)

```json
{
  "quality_audio": "HI_RES_LOSSLESS",
  "skip_existing": true,
  "download_delay": true,
  "metadata_cover_embed": true,
  "cover_album_file": true,
  "format_playlist": "Playlists/{playlist_name}/{artist_name} - {track_title}"
}
```

### Minimal Storage (Lower Quality)

```json
{
  "quality_audio": "HIGH",
  "metadata_cover_dimension": 160,
  "cover_album_file": false
}
```

### Full Album Collection

```json
{
  "quality_audio": "HI_RES_LOSSLESS",
  "format_album": "Albums/{album_artist}/{album_title}/{album_track_num}. {track_title}",
  "metadata_replay_gain": true,
  "lyrics_file": true
}
```

## Notes

- The configuration file is automatically created with sensible defaults on first run
- Changes to the config file take effect on the next CLI run
- Boolean values must be lowercase (`true`/`false`) in JSON
- Numeric values for quality can be strings (like `"480"`) or match enum values
- Template variables are case-sensitive
- Invalid template variables will be left as-is in the filename

## See Also

- [Download Feature Documentation](DOWNLOAD_FEATURE.md)
- [tidal-dl-ng Repository](https://github.com/exislow/tidal-dl-ng)
