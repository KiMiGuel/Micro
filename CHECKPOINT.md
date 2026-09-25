# Checkpoint — 2026-09-24
Status: COMPLETE
Task: MicroVault landing page + MeXiCOSINT integration polish

## Done
- Built MicroVault's landing page (docs/index.html) from the provided banner, cyan/amber/black theme; published to GitHub Pages, fixed a stale Jekyll build error (.nojekyll)
- Added `microvault profile` feature: named non-secret key groups, `env --profile [--json]`, Python API (`vault.profile_services()`/`vault.env_profile()`)
- MeXiCOSINT: auto-detects MicroVault (no `--microvault` flag required), added `--no-microvault`, uses the new profile + batched fetch (one password prompt instead of up to six)
- Hid `--dummy-test` from public docs/help across MeXiCOSINT (still functional internally)
- Fixed stale/wrong MeXiCOSINT service names across both repos' docs
- Published MicroVault v1.2 and MeXiCOSINT v2.7.0 to PyPI via GitHub Releases; bumped MeXiCOSINT's landing page version badge to match

## Next (immediate execution for next session)
1. Enumerate which Indepentest projects actually need an update-check feature. Confirmed in-scope so far: MicroVault and MeXiCOSINT. Discover the remaining repositories before implementing.
2. Design: automatic (not opt-in-gated) check against each package's PyPI JSON API on startup, comparing the installed version to latest, printing a one-line update nudge if outdated. User explicitly approved this being automatic even for MicroVault despite its "no phone-home" positioning — keep it lightweight (non-blocking, fail silently on network error, never break offline use).
3. Implement per-project, then bump + publish a release for each the same way as this session (commit → push → `gh release create`, which triggers the existing PyPI-publish workflow).
