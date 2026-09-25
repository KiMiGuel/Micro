# STATUS — MicroVault

Current as of 2026-09-24.

## Published
- PyPI: `microvault` v1.2 (https://pypi.org/project/microvault/)
- GitHub release: v1.2 (https://github.com/KiMiGuel/MicroVault/releases/tag/v1.2)
- Landing page live: https://kimiguel.github.io/MicroVault/ (served from `docs/`, `.nojekyll` set so Pages skips Jekyll processing)

## Local install
- `microvault` on PATH is an **editable install** (`pip install -e .`) pointing directly at this repo (`/home/KaliMa/MicroVault/microvault/__init__.py`) — local edits are live immediately, no reinstall needed. `pip show microvault` prints a stale version string; that's cached dist-info metadata only, cosmetic, doesn't affect behavior.

## Features
- Interactive vault opens directly into an arrow-key selection menu; the redundant text-input-then-menu loop was removed.
- Added visible `Profiles` menu with view, create/update, and delete actions.
- Core vault: add/get/list/update/delete/import/backup/restore/alias, `microvault env [service]`, `microvault run svc -- cmd`, Python API (`from microvault import vault`).
- Profiles (added 2026-09-24): `microvault profile <name> <service...>`, `microvault env --profile <name> [--json]`, `vault.profile_services()`/`vault.env_profile()` — scopes what a calling tool sees to a named subset instead of the whole vault. `--json` batches a whole profile into one password prompt instead of one per key.

## Known integrations
- MeXiCOSINT: auto-detects MicroVault on launch (no flag needed) and requires the `mexicosint` profile (`geoapify`, `opencage_api`, `ipgs`, `numverify_api`, `abstract_api`). It fetches that profile in one call via `microvault env --profile mexicosint --json`.

## Standalone product

MicroVault is a standalone local vault. MeXiCOSINT is an optional external consumer of its public profile/env API; MicroVault does not depend on or manage any other Micro project.
