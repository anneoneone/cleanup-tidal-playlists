# Cratekeeper

Cratekeeper keeps your Rekordbox library in line with the playlists you curate on
Tidal and in Bandcamp folders. It reads your playlists, downloads missing Tidal
tracks, and shows you a **Plan** of every change it would make to Rekordbox. You
review the Plan per playlist and **Apply** what you want. A **Backup** is taken
before every Apply.

Cratekeeper is v2 of `tidal-cleanup`. The words used here are defined in
[CONTEXT.md](CONTEXT.md).

## What it does

1. **Refresh** – reads your Tidal playlists, your Bandcamp folder and your Music
   folder into its own database. Rekordbox is not touched.
2. **Download** – fetches Tidal tracks that have no file yet (needs `tidal-dl-ng`
   and `ffmpeg`).
3. **Plan** – compares what each playlist should look like in Rekordbox with what
   is there: create, rename or move playlists, import, add or remove tracks, set
   the genre. Nothing is written.
4. **Apply** – writes the chosen groups of the Plan to Rekordbox, one playlist at a
   time. A failed playlist is rolled back and the others still apply.

Playlist names carry emojis that decide the Rekordbox folder and the genre, e.g.
`Peak Time 🏢⬆️` becomes `Peak Time High` in `Genre/Techno/Archived`. See
[docs/naming.md](docs/naming.md).

## Install

Needs macOS, Python 3.12+ and Rekordbox 6 or 7.

```bash
pip install -e .
```

Optional, for downloads: `ffmpeg` (`brew install ffmpeg`) and `tidal-dl-ng` 0.31.
`tidal-dl-ng` is no longer on PyPI; install it into the same environment from a
wheel or source you trust. Without it, Cratekeeper still syncs everything else and
tells you how many tracks need a download.

Build the web UI once (needs Node.js 22+):

```bash
make ui
```

## First start

Coming from `tidal-cleanup`? Import your data and settings once. Your v1 files stay
untouched.

```bash
cratekeeper migrate --env-file config/.env-Tidal
```

New install? Log in to Tidal and set your folders on the Settings page (or in
`~/.cratekeeper/config.toml`):

```bash
cratekeeper login
```

Then check that everything is found:

```bash
cratekeeper status
```

## Daily use

Open the web UI:

```bash
cratekeeper ui
```

- **Dashboard** – health checks, counts, last sync, "Sync now".
- **Sync** – live progress of Refresh, Download and Plan; then review the Plan per
  playlist and Apply.
- **Playlists** – every playlist with its Sources, Folder placement and track
  counts; drill down to see each track in Tidal, Bandcamp, on disk and in Rekordbox.
- **Settings** – folders and options, the Playlist tag mapping, Tidal login.
- **History** and **Backups** – past runs with their Plans, and one-click restore.

Or from the terminal:

```bash
cratekeeper sync                 # refresh, download, plan, ask, apply
cratekeeper sync --plan-only     # stop after the plan
cratekeeper sync --offline       # no Tidal refresh, no downloads (re-plan)
cratekeeper sync -p "Peak Time 🏢⬆️"
cratekeeper backups              # list; `backups restore <ID>` restores
```

`sync` flags: `--yes` (no prompt), `--no-download`, `--delete-playlists` (also apply
the deletion group), `--full` (fetch every Tidal playlist again), `--allow-shrink`
(accept that Tidal lists far fewer playlists than before).

## Safety

- The Plan is built on a copy of the Rekordbox library and writes nothing.
- Apply refuses while Rekordbox is running, and when the library changed after the
  Plan was made. A Plan can only be applied once, and only while it is the newest
  one.
- A full Backup (Cratekeeper's database plus Rekordbox's `master.db`, `local.db`
  and `masterPlaylists6.xml`) is taken before every Apply; a database Backup before
  every Refresh.
- If the Music folder or the Bandcamp folder is missing (drive unplugged),
  Cratekeeper stops instead of treating the files as deleted.
- Deleting Rekordbox playlists is its own group in the Plan and is off by default.
- Cratekeeper never deletes or renames your audio files.

## Settings

`~/.cratekeeper/config.toml` (or the Settings page). Every key can be overridden
with an environment variable `CRATEKEEPER_<KEY>`; `CRATEKEEPER_HOME` moves the whole
folder.

| Key | Default | Meaning |
| --- | --- | --- |
| `music_folder` | `~/Music/Tidal/mp3` | Folder with one sub-folder per playlist under `Playlists/` |
| `bandcamp_folder` | – | Folder with one sub-folder per Bandcamp playlist |
| `rekordbox_db` | auto | Rekordbox `master.db` |
| `tag_mapping` | built-in | Playlist tag mapping file (emoji → tag, folders) |
| `target_format` | `mp3` | Format downloads are converted to |
| `ffmpeg_quality` | `2` | ffmpeg `-q:a` for MP3 (0 = best) |
| `download_quality` | `LOSSLESS` | Tidal quality for downloads |
| `prune_tracks` | `true` | Remove tracks from Rekordbox playlists that are not in the playlist any more |
| `backups_keep_full` | `20` | Full Backups to keep |
| `backups_keep_db` | `10` | Database Backups to keep |
| `port` | `8765` | Port of `cratekeeper ui` |

Files in `~/.cratekeeper/`: `config.toml`, `cratekeeper.db`, `tidal_session.json`,
`tag_mapping.json` (if edited), `backups/`, `logs/`, `tidal-dl-ng/`.

## Development

```bash
make install-dev   # editable install with tools and pre-commit hooks
make check         # black, isort, flake8, mypy, pytest (same as CI)
make ui            # build the web UI
make ui-dev        # Vite dev server; run `cratekeeper ui --dev` next to it
```

Try the UI on demo data without touching real files:

```bash
python scripts/make_demo_home.py /tmp/ck-demo
CRATEKEEPER_HOME=/tmp/ck-demo/home cratekeeper ui
```

How it fits together: [docs/architecture.md](docs/architecture.md). Contribution
rules: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
