# Contributing to Cratekeeper

## Setup

Needs Python 3.12+, Node.js 22+ (for the web UI) and Git.

```bash
git clone https://github.com/anneoneone/cleanup-tidal-playlists.git
cd cleanup-tidal-playlists
make install-dev
```

Read [CONTEXT.md](CONTEXT.md) (domain words) and
[docs/architecture.md](docs/architecture.md) first.

## Checks

Run before every commit (CI runs the same):

```bash
make check        # black, isort, flake8, mypy (strict), pytest with coverage
make ui-check     # eslint, tsc, vitest, vite build
```

Pre-commit hooks run on every commit. Run them by hand with
`pre-commit run --all-files`.

## Rules

- Python: black (88), isort (black profile), flake8 with docstrings, bugbear,
  simplify and bandit; mypy strict.
- New behaviour gets a test in the same change; a bug fix gets a regression test.
- Tests never touch real data: `tests/conftest.py` points `HOME` and
  `CRATEKEEPER_HOME` at temp folders and blocks the network. Rekordbox tests use the
  `rekordbox_library` fixture (a real, empty, unencrypted library).
- Anything that writes to Rekordbox goes through a Plan and the applier.
- Schema changes need a migration in `src/cratekeeper/db/migrations/versions`.
- After an API change, run `python scripts/export_openapi.py` and `npm run gen:api`
  in `frontend/`.
- Use the words from `CONTEXT.md` in code, UI and docs.

## Commits and pull requests

- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`,
  `ci:`, `build:`), imperative mood, subject up to 72 characters.
- One feature per commit; keep its code and tests together.
- Never commit to `main`; open a pull request from a branch.
- Write titles and bodies in short, plain English and say exactly what changes.
