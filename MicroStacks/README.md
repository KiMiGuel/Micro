# MicroStacks

A token registry and usage-accounting layer for [MicroVault](../MicroVault/).
It mints opaque, revocable bearer tokens that stand in for a real API key
stored in MicroVault, and tracks usage against each one.

> **Status:** early / registry-only. Not yet published anywhere. The
> mechanism that makes a minted token actually resolve to a real key at
> request time (a local proxy or call-wrapper) is not built yet — see
> "What's not built" below before depending on this for anything live.

## What it does today

- **Mint**: given a service already stored in MicroVault, generate a
  token like `mstk_openai_4f9a1c2b8e7d`.
- **List / revoke**: see all minted tokens with their usage, or delete
  one.
- **Usage accounting**: each token carries a `tokens_used` counter,
  displayed in MicroStacks units — 1 MicroStack = 1,000 underlying LLM
  tokens (a display unit, not a currency).

All of this is driven through MicroVault's CLI (`mint` / `tokens` /
`revoke` commands) — MicroStacks doesn't have its own interface yet.

## What's not built

A minted token is currently just a registry entry — nothing resolves
`mstk_...` back to the real key at request time. The intended mechanism:
a local proxy that a client points at via a base-URL override, which
validates the token, substitutes the real key, forwards the request, and
increments usage from the response. Also not built: token expiry
(time- or usage-based).

## Storage location

Data is stored independently from MicroVault, encrypted with its own
salt/key derived from the same master password. By default:
`~/.microstacks/`. Override with the `MICROSTACKS_HOME` environment
variable.

## License

Apache License 2.0 — see the repository root [LICENSE](../LICENSE).
