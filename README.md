<p align="center">
  <img src="assets/logo.svg" alt="MicroVault" width="600" />
</p>

<p align="center">
  <b>Your API keys, encrypted, offline, on your terms.</b>
</p>

<p align="center">
  <a href="https://pypi.org/project/microvault/"><img src="https://img.shields.io/pypi/v/microvault.svg" alt="PyPI version" /></a>
  <a href="https://pypi.org/project/microvault/"><img src="https://img.shields.io/pypi/pyversions/microvault.svg" alt="Python versions" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License" /></a>
</p>

---

Let's be honest: you've probably got API keys scattered everywhere. 🫠 A few in a `.env` file. One or two pasted straight into a shell script you meant to clean up. Maybe one sitting in your `.zshrc` in plain text, right where anyone glancing at your screen (or anything that gets its hands on your dotfiles) can read it.

MicroVault fixes that with the simplest thing that could possibly work: one encrypted file, one password only you know, and a CLI that gets your keys in and out without ever leaving them lying around.

No account to create. No server to trust. No cloud sync to worry about getting breached. It's just you, your terminal, and a vault that only opens for you.

## 🔐 What's actually happening under the hood

- Your master password runs through **PBKDF2-SHA256 with 600,000 iterations** to derive an encryption key — that's deliberately expensive, so brute-forcing it isn't cheap either.
- Every key is encrypted at rest with **Fernet** (AES-128-CBC + HMAC-SHA256), which means the vault file isn't just unreadable without the password — it's tamper-evident too.
- Writes are **atomic**. If your machine crashes or loses power mid-save, you get the old file or the new file, never a corrupted mess in between.
- Every save **auto-snapshots a backup**, so "oops, I didn't mean to delete that" is a `restore` away, not a disaster.
- Your master password is **never written anywhere**. Not to disk, not to a log, not to memory longer than it has to be. If you forget it, nobody — including us — can get your keys back. That's the deal: real security means real consequences for losing the password.

## ✨ Why you'll actually want to use this

- **Add a key without it ever touching your screen.** API key entry is a hidden prompt, same as typing a password — it never echoes, never lands in your shell history.
- **Name your services whatever you want.** `openai`, `aws`, `that-weird-internal-tool`, doesn't matter — there's no fixed list to fight with.
- **Bulk import from an existing file.** Already have a pile of keys in a text file? MicroVault's importer handles `NAME=value`, `NAME: value`, `NAME value`, even `export NAME=value` — and it shows you exactly what it parsed *before* touching your vault.
- **Pull keys straight into your shell**, on demand, without ever putting a plaintext secret in your `.zshrc`:

  ```bash
  eval "$(microvault env)"
  ```

  One line, and every stored key becomes a real environment variable for that session — gone the moment you close the terminal.
- **Other tools can call their APIs straight from what's in MicroVault** — no copy-pasting a key into a separate config file somewhere else. A lot of real tools expect a specific environment-variable name that isn't the obvious one (WPScan wants `WPSCAN_API_TOKEN`, VirusTotal's CLI wants the genuinely odd `VTCLI_APIKEY`, `gh` wants `GH_TOKEN`). The interactive **Configure an environment alias** action sets the exact name a tool expects once, and `microvault env` exports it correctly from then on:

  ```text
  Choose a command: Configure an environment alias
  Service name to set an alias for: wpscan
  Export name for wpscan (suggested: WPSCAN_API_TOKEN — press Enter to accept):
  wpscan will now export as WPSCAN_API_TOKEN.
  ```

  MicroVault recognizes a handful of common tools and suggests the right name, but the alias prompt always accepts anything you type, so this works for literally any tool, known or not.
- **An arrow-key selection menu.** The interactive vault opens directly into the menu; choose an action with ↑/↓ and Enter. Service names, aliases, file paths, and profiles are requested by focused prompts after selecting an action.
- **Colorful, readable output** — because staring at a wall of monochrome CLI text all day is nobody's idea of a good time.

## 🚀 Try it

```bash
pip install microvault
microvault
```

That's it. On first run, MicroVault asks whether to create a vault with your master password, then opens the arrow-key menu:

```text
Choose a command: Add a key
Service name (e.g., openai, aws): openai
API Key (input hidden): ••••••••••••••••••••••
Saved openai.
```

Vault actions are selected from the interactive menu. The standalone CLI also supports these non-interactive commands:

```bash
microvault env                         # export every key for shell eval
microvault env openai                  # export one key
microvault env --profile mexicosint    # export one profile
microvault env --profile mexicosint --json
microvault profile                     # list profiles
microvault profile <name> <service...> # create or replace a profile
microvault profile delete <name>       # delete a profile
microvault run <service> -- <command>  # run a command with one key injected
```

Use `microvault --help` for the complete command reference.

## 🔌 Using a stored key with any tool

Same four steps, every time, no matter what the tool is:

**1. Store it.** Run `microvault`, choose **Add a key**, and enter the service name followed by the hidden key prompt.

```text
Choose a command: Add a key
Service name (e.g., openai, aws): servicename
API Key (input hidden): [paste the key]
Saved servicename.
```

**2. If the tool expects a specific env var name, alias it.** Most tools that auto-read a key from the environment have their own convention — check that tool's docs for the exact name it looks for. If you don't know it, just skip this step; the default (`SERVICENAME_API_KEY`) works fine for anything that lets you pass the key as a flag instead. To set an alias, run `microvault` and choose **Configure an environment alias**.

```text
Choose a command: Configure an environment alias
Service name to set an alias for: servicename
Export name for servicename (suggested: ..., or type your own):
servicename will now export as WHATEVER_THE_TOOL_EXPECTS.
```

**3. Load it into your shell.**

```bash
eval "$(microvault env servicename)"
```

**4. Run the tool.** If it auto-reads the env var, you're done — nothing else to type. If it takes the key as a flag instead, pass it explicitly:

```bash
sometool --api-key "$WHATEVER_THE_TOOL_EXPECTS"
```

Worked example, using [WPScan](https://github.com/wpscanteam/wpscan) — which auto-reads `WPSCAN_API_TOKEN`, not the default MicroVault would generate:

```bash
# in the MicroVault menu, add wpscan_api, then configure an alias for it
# and accept the suggested WPSCAN_API_TOKEN

eval "$(microvault env wpscan_api)"
wpscan --url https://your-authorized-target.com
```

No `--api-token` flag needed — WPScan finds `WPSCAN_API_TOKEN` in the environment on its own. Same pattern works for any tool with any env var convention; the alias is what bridges MicroVault's naming to whatever that specific tool actually expects.

### The shortcut: `microvault run`

If you don't want the two-step `eval` + run dance, there's a one-liner that does both — unlocks the vault, injects the key, and replaces itself with the real command:

```bash
microvault run github -- npx -y @modelcontextprotocol/server-github
```

The `--` separates the service name from the command. Everything after it runs as a child process with the key in its environment. The key is never written to disk, never shown on screen, and lives only as long as the process does.

This is especially useful for MCP servers and other tools that get spawned as subprocesses — they don't inherit your shell's exports, but they *do* inherit their parent's environment, and `run` *is* the parent.

## 🐍 Python API

MicroVault isn't just a CLI — it's a Python package you can import. If you're building a tool that needs API keys and don't want to deal with `.env` files or config parsing, just ask MicroVault directly:

```python
from microvault import vault

key = vault.get("openai")          # prompts for password once, then caches
env  = vault.env_name("github")    # "GH_TOKEN" (respects your aliases)
all  = vault.list()                 # {"openai": "sk-...a3f", "github": "ghp_..."}
```

No server, no network, no daemon — it reads the same encrypted vault file the CLI uses. The password prompt fires once per process; subsequent calls reuse the in-memory session.

This is how other Python tools (and yours) can pull keys from MicroVault without shelling out to `microvault env` and parsing stdout. One import, one call, done.

## 📦 Storage

Everything lives at `~/.microvault/` by default: the encrypted `vault.enc`, non-secret alias/profile metadata, and a rolling encrypted backup under `backups/`. Want it somewhere else? Set `MICROVAULT_HOME` and it follows you there.

## 📄 License

Apache License 2.0 — see [LICENSE](LICENSE).

---

## ¿Usas MeXiCOSINT? 🇲🇽

Si usas [MeXiCOSINT](https://github.com/KiMiGuel/MeXiCOSINT) para investigación OSINT de números telefónicos mexicanos, guarda sus API keys directamente en MicroVault. MeXiCOSINT requiere el perfil `mexicosint` para el enriquecimiento normal.

### Configuración

Ejecuta `microvault` y elige **Add a key** cinco veces para guardar:

- `geoapify`
- `opencage_api`
- `ipgs`
- `numverify_api`
- `abstract_api`

Esos son los nombres exactos que MeXiCOSINT busca en la bóveda — no `opencage`, `ipqualityscore`, etc.

### Perfil (recomendado)

Agrupa esas cinco keys en un perfil para que MeXiCOSINT solo vea sus propias keys — nunca el resto de tu bóveda, aunque tengas otros servicios guardados ahí:

```bash
microvault profile mexicosint geoapify opencage_api ipgs numverify_api abstract_api
```

MeXiCOSINT detecta MicroVault automáticamente al ejecutarse — no necesita una flag — y requiere el perfil compatible `mexicosint`, pidiendo tu contraseña maestra una sola vez para las cinco keys. MicroVault se conecta a MeXiCOSINT mediante ese perfil aislado y consulta el perfil una sola vez. La configuración de credenciales se hace únicamente en MicroVault.

Para más detalles, consulta el [README de MeXiCOSINT](https://github.com/KiMiGuel/MeXiCOSINT).

Las palabras `svc1` y `svc2` que aparecen en la ayuda son marcadores de ejemplo, no nombres obligatorios. `Services` significa los nombres exactos de las claves almacenadas en MicroVault. Para verlas sin exponerlas, abre MicroVault y elige **List stored keys**; para actualizar un perfil existente, usa **Profiles → Update an existing profile** o vuelve a ejecutar el comando `microvault profile mexicosint ...` con la lista completa de servicios.
