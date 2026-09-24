# STATUS — MicroVault

Current as of 2026-09-24.

## Published
- PyPI: `microvault` v1.2 (https://pypi.org/project/microvault/)
- GitHub release: v1.2 (https://github.com/KiMiGuel/MicroVault/releases/tag/v1.2)
- Landing page live: https://kimiguel.github.io/MicroVault/ (served from `docs/`, `.nojekyll` set so Pages skips Jekyll processing)

## Local install
- `microvault` on PATH is an **editable install** (`pip install -e .`) pointing directly at this repo (`/home/KaliMa/MicroVault/microvault/__init__.py`) — local edits are live immediately, no reinstall needed. `pip show microvault` prints a stale version string; that's cached dist-info metadata only, cosmetic, doesn't affect behavior.

## Features
- Core vault: add/get/list/update/delete/import/backup/restore/alias, `microvault env [service]`, `microvault run svc -- cmd`, Python API (`from microvault import vault`).
- Profiles (added 2026-09-24): `microvault profile <name> <service...>`, `microvault env --profile <name> [--json]`, `vault.profile_services()`/`vault.env_profile()` — scopes what a calling tool sees to a named subset instead of the whole vault. `--json` batches a whole profile into one password prompt instead of one per key.
- MicroStacks (separate encrypted store, `mint`/`tokens`/`revoke`) — pre-existing, not touched this session.

## Known integrations
- MeXiCOSINT: auto-detects MicroVault on launch (no flag needed), uses a `mexicosint` profile (`geoapify`, `opencage_api`, `ipgs`, `numverify_api`, `abstract_api`) when defined, batched single-password-prompt fetch via `microvault env --profile mexicosint --json`. Falls back to per-service fetch if the profile isn't set up.

## Part of a larger vision
User is building a connected "Micro" ecosystem (MicroVault, MicroStacks, MeXiCOSINT, future Indepentest tools) — see the `indepentest_micro_ecosystem_vision` Claude Code memory. The profile feature is the reusable per-tool scoping pattern for future tools joining the vault.
