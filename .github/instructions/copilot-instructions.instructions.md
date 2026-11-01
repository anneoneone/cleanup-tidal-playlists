<!-- markdownlint-disable MD041 MD003 -->
---

applyTo: "**"
---

# Cratekeeper

Cratekeeper (v2 of tidal-cleanup) keeps a Rekordbox library in line with Tidal and
Bandcamp playlists: Refresh → Download → Plan → Apply, with a CLI (`cratekeeper`)
and a local web UI (FastAPI + React).

Read before changing code:

- `CONTEXT.md` – domain words (Source, Playlist, Local track, Plan, Apply, Backup …)
- `docs/architecture.md` – modules, data model, matching, Apply rules
- `docs/naming.md` – emoji → Playlist tag → Folder placement
- `CONTRIBUTING.md` – checks and commit rules

Rules:

- Python 3.12, mypy strict, black/isort/flake8; tests in the same change.
- Never write to Rekordbox outside the Plan/applier path.
- Tests must not touch real data or the network (see `tests/conftest.py`).
- After API changes: `python scripts/export_openapi.py`, then `npm run gen:api` in
  `frontend/`.
