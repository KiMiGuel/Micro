# MicroVault

A local, offline, encrypted command-line vault for API keys. No server,
no account, no cloud sync — your keys live in one encrypted file on your
own machine, unlocked with a master password you choose.

> **Status:** pre-release. Not yet published to PyPI.

## How it works

- One master password derives an encryption key via PBKDF2-SHA256
  (600,000 iterations) with a random salt.
- Keys are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256 —
  tamper-evident).
- The vault file is written atomically (temp file + rename) so a crash
  mid-write can't corrupt it, and it's locked to `0600` permissions.
- Your master password is never stored anywhere. If you lose it, the
  vault cannot be recovered.

## Install

```bash
pip install microvault
```

(Or, from a local checkout: `pip install -e .`)

## Usage

```bash
microvault
```

Prompts for your master password (creating a new vault on first run),
then drops you into a command loop:

| Command  | Does |
|----------|------|
| `add`    | Store a new API key under a service name you type yourself — any name, no fixed list |
| `get`    | Print a stored key |
| `list`   | List services with keys masked (`sk-t...abcd`) |
| `update` | Replace a stored key |
| `delete` | Remove a stored key |
| `mint`   | Mint a [MicroStacks](../MicroStacks/) token for a stored service |
| `tokens` | List MicroStacks tokens and their usage |
| `revoke` | Revoke a MicroStacks token |
| `exit`   | Quit |

API key values are entered with hidden input (like a password prompt) —
they never echo to your screen or land in shell history.

## Shell integration

To use a stored key from your shell without ever putting the plaintext
key in a dotfile:

```bash
eval "$(microvault env)"       # exports every stored key as SERVICE_API_KEY
eval "$(microvault env openai)" # exports just one
```

This prompts for your master password (on stderr, so it doesn't pollute
the `eval`), then prints `export SERVICE_API_KEY=...` lines to stdout
only. Add a shell function like this to unlock on demand:

```bash
mv-unlock() {
  local out
  out=$(microvault env) || return 1
  eval "$out"
  echo "MicroVault: keys loaded into this shell."
}
```

Once exported, the key is plaintext in that shell's environment for the
duration of the session — that's inherent to how any env-var-based
credential works, not specific to MicroVault.

## Storage location

By default, data is stored under `~/.microvault/`. Override with the
`MICROVAULT_HOME` environment variable to use a different location.

## License

Apache License 2.0 — see the repository root [LICENSE](../LICENSE).
