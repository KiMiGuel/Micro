import json
import os
import re
import sys
import shlex
import shutil
import secrets
import getpass
from datetime import datetime, timezone
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
from colorama import init as _colorama_init, Fore, Style
import questionary

_colorama_init(autoreset=True)

# Semantic color shortcuts, reused across the CLI's feedback messages.
_OK = Fore.GREEN + Style.BRIGHT
_ERR = Fore.RED + Style.BRIGHT
_WARN = Fore.YELLOW + Style.BRIGHT
_INFO = Fore.CYAN + Style.BRIGHT
_DIM = Style.DIM

WORDMARK = r"""   _____  .__                  ____   ____            .__   __
  /     \ |__| ___________  ___\   \ /   /____   __ __|  |_/  |_
 /  \ /  \|  |/ ___\_  __ \/  _ \   Y   /\__  \ |  |  \  |\   __\
/    Y    \  \  \___|  | \(  <_> )     /  / __ \|  |  /  |_|  |
\____|__  /__|\___  >__|   \____/ \___/  (____  /____/|____/__|
        \/        \/                          \/"""

VAULT_ICON = r"""      _____________________
     /  ___________________  \
    |  |                   |  |
    |  |     _________     |  |
    |  |    /    |    \    |  |
    |  |   |-----+-----|   |  |
    |  |    \____|____/    |  |
    |  |                   |  |
    |  |  (#)  (#)  (#)    |  |
    |  |___________________|  |
     \  ___________________  /
      \_____________________/"""


def _print_block_centered(plain_lines, colored_lines, width: int):
    """Centers a multi-line block as a single unit (one indent for every
    line, based on the block's own max width) so lines of differing length
    within the block — e.g. a figlet letterform's descenders, or a box's
    tapered corners — keep their shape instead of each drifting to its own
    independent center."""
    indent = max(0, (width - max(len(l) for l in plain_lines)) // 2)
    for colored in colored_lines:
        print(" " * indent + colored)


def print_banner():
    print("\033[H\033[2J\033[3J", end="")  # clear screen + scrollback

    wordmark_lines = WORDMARK.splitlines()
    vault_lines = VAULT_ICON.splitlines()
    width = max(len(l) for l in wordmark_lines)

    colored_wordmark = [f"{Fore.CYAN}{Style.BRIGHT}{l}" for l in wordmark_lines]
    _print_block_centered(wordmark_lines, colored_wordmark, width)

    tagline = "Indepentest LLC"
    _print_block_centered([tagline], [f"{Fore.WHITE}{Style.BRIGHT}{tagline}"], width)

    colored_vault = [
        f"{Fore.YELLOW}{Style.BRIGHT}"
        + line.replace("(#)", f"{Fore.RED}(#){Fore.YELLOW}{Style.BRIGHT}")
        for line in vault_lines
    ]
    _print_block_centered(vault_lines, colored_vault, width)

MICROVAULT_HOME = os.environ.get("MICROVAULT_HOME", os.path.expanduser("~/.microvault"))
VAULT_FILE = os.path.join(MICROVAULT_HOME, "vault.enc")
ALIASES_FILE = os.path.join(MICROVAULT_HOME, "aliases.json")

MICROSTACKS_HOME = os.environ.get("MICROSTACKS_HOME", os.path.expanduser("~/.microstacks"))
MICROSTACKS_FILE = os.path.join(MICROSTACKS_HOME, "microstacks.enc")

SALT_SIZE = 16
PBKDF2_ITERATIONS = 600_000
TOKENS_PER_MICROSTACK = 1000  # display unit: 1 MicroStack = 1000 underlying LLM tokens


def derive_key(password: str, salt: bytes) -> bytes:
    """Derives a 256-bit Fernet key from the master password and salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def load_store(path: str, password: str):
    """Load and decrypt an encrypted JSON store. Returns (data, salt, key), or
    (None, None, None) on wrong password / corrupted file, or a fresh ({}, salt, key)
    if the file doesn't exist yet."""
    if not os.path.exists(path):
        salt = os.urandom(SALT_SIZE)
        return {}, salt, derive_key(password, salt)

    with open(path, "rb") as f:
        raw = f.read()

    if len(raw) <= SALT_SIZE:
        return None, None, None

    salt, token = raw[:SALT_SIZE], raw[SALT_SIZE:]
    key = derive_key(password, salt)

    try:
        data = json.loads(Fernet(key).decrypt(token).decode("utf-8"))
        return data, salt, key
    except (InvalidToken, ValueError):
        return None, None, None


def save_store(path: str, data: dict, salt: bytes, key: bytes):
    """Encrypt and atomically write a store to disk, reusing the session salt/key."""
    token = Fernet(key).encrypt(json.dumps(data).encode("utf-8"))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(salt + token)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def snapshot_backup(path: str):
    """Copies a just-written store to a single rolling backup file in its
    own backups/ subfolder — a physically separate file from the live
    store it protects (not nested inside it, which would offer no
    protection against that exact file being lost or corrupted).
    Overwritten on every save: protects your most recent change, not
    deep history — one file, no ambiguity about which one to restore."""
    backup_dir = os.path.join(os.path.dirname(path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    name = os.path.splitext(os.path.basename(path))[0]
    backup_path = os.path.join(backup_dir, f"{name}-backup.enc")
    shutil.copy2(path, backup_path)
    os.chmod(backup_path, 0o600)


def load_vault(password: str):
    return load_store(VAULT_FILE, password)


def save_vault(data: dict, salt: bytes, key: bytes):
    save_store(VAULT_FILE, data, salt, key)
    snapshot_backup(VAULT_FILE)


def load_microstacks(password: str):
    return load_store(MICROSTACKS_FILE, password)


def save_microstacks(data: dict, salt: bytes, key: bytes):
    save_store(MICROSTACKS_FILE, data, salt, key)
    snapshot_backup(MICROSTACKS_FILE)


def mask_key(key: str) -> str:
    """Returns a masked version of the key for display."""
    if len(key) > 10:
        return key[:4] + "..." + key[-4:]
    return "***"


def env_var_name(service: str) -> str:
    """Maps a service name to a default shell env var, e.g. 'openai' ->
    'OPENAI_API_KEY'. Strips a trailing _api/_key/_api_key from the service
    name first, so a name like 'shodan_api' produces 'SHODAN_API_KEY'
    instead of doubling up as 'SHODAN_API_API_KEY'. This is just the
    default — many real tools expect a completely different name (see
    KNOWN_ALIASES / the 'alias' command), which this can't guess on its
    own and isn't meant to."""
    name = service.strip()
    name = re.sub(r'(?i)_api_key$', '', name)
    name = re.sub(r'(?i)_key$', '', name)
    name = re.sub(r'(?i)_api$', '', name)
    name = name.strip('_')
    sanitized = re.sub(r'[^A-Za-z0-9]', '_', name)
    return f"{sanitized.upper()}_API_KEY"


# A convenience nudge only, seeded from researching real tools' actual
# conventions (verified, not guessed — several surprised us, e.g. VirusTotal's
# CLI wants VTCLI_APIKEY, not VT_API_KEY). Matched loosely against the
# service name; 'alias' always accepts a fully custom name regardless of
# whether a service is in this table, so this list being incomplete never
# blocks anyone — it just means no suggestion is offered.
KNOWN_ALIASES = {
    "github": "GH_TOKEN",
    "git": "GH_TOKEN",
    "shodan": "SHODAN_API_KEY",
    "virustotal": "VTCLI_APIKEY",
    "wpscan": "WPSCAN_API_TOKEN",
    "chaos": "PDCP_API_KEY",
    "ipinfo": "IPINFO_TOKEN",
    "kimi": "MOONSHOT_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "serpapi": "SERPAPI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gpt": "OPENAI_API_KEY",
    "numverify": "NUMVERIFY_API_KEY",
}


def suggest_alias(service: str):
    """Loose substring match against KNOWN_ALIASES. Returns None (not a
    guess) when nothing matches — the service just uses the default name."""
    key = re.sub(r'[^a-z0-9]', '', service.lower())
    for pattern, env_name in KNOWN_ALIASES.items():
        if pattern in key:
            return env_name
    return None


def load_aliases() -> dict:
    """Aliases are env-var NAMES, not secrets — plain JSON, no encryption,
    no password needed to read or write them."""
    if not os.path.exists(ALIASES_FILE):
        return {}
    try:
        with open(ALIASES_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_aliases(aliases: dict):
    os.makedirs(os.path.dirname(ALIASES_FILE), exist_ok=True)
    tmp_path = ALIASES_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(aliases, f, indent=2, sort_keys=True)
    os.replace(tmp_path, ALIASES_FILE)


def parse_key_file(path: str):
    """Parses a text file of API keys into {service: key} pairs. Splits each
    line on the first '=' or ':' found anywhere in it (so a stray space
    before the separator, e.g. 'google places_API=xyz', doesn't fool the
    parser); falls back to strict 'name key' whitespace-splitting only when
    the line has no '=' or ':' at all. Also strips a leading shell 'export'
    keyword and a trailing '_API_KEY'/'_KEY' suffix on the name. Blank
    lines and lines starting with '#' are ignored. Returns (parsed_dict,
    [line numbers that failed to parse])."""
    entries = {}
    failed_lines = []
    with open(path, "r") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            line = re.sub(r'^export\s+', '', line, flags=re.IGNORECASE)

            sep = re.search(r'[:=]', line)
            if sep:
                name, value = line[:sep.start()], line[sep.end():]
            else:
                match = re.match(r'^(\S+)\s+(\S+)$', line)
                if not match:
                    failed_lines.append(lineno)
                    continue
                name, value = match.group(1), match.group(2)

            name = name.strip().strip('"\'')
            value = value.strip().strip('"\'')
            if not name or not value:
                failed_lines.append(lineno)
                continue
            name = re.sub(r'(?i)_api_key$', '', name)
            name = re.sub(r'(?i)_key$', '', name)
            name = re.sub(r'\s+', '_', name.strip('_'))
            name = name.lower()
            entries[name] = value
    return entries, failed_lines


def generate_microstack_token(service: str) -> str:
    """Mints an opaque bearer token for a service, e.g. 'mstk_openai_4f9a1c2b8e7d'.
    This is what code/shell would hold instead of the real key once a proxy or
    call-wrapper resolves it back to the real key at request time (not yet built)."""
    sanitized = re.sub(r'[^a-z0-9]', '', service.strip().lower())
    return f"mstk_{sanitized}_{secrets.token_hex(6)}"


def cmd_env(target_service: str = None):
    """Prints `export NAME=value` lines to stdout for shell eval. All other
    output (prompts, errors) goes to stderr so stdout stays eval-safe."""
    if not os.path.exists(VAULT_FILE):
        print("MicroVault: no vault found.", file=sys.stderr)
        sys.exit(1)

    password = getpass.getpass("Enter master password: ")
    vault, salt, key = load_vault(password)
    if vault is None:
        print("MicroVault: wrong password or corrupted vault.", file=sys.stderr)
        sys.exit(1)

    items = vault.items()
    if target_service:
        if target_service not in vault:
            print(f"MicroVault: service '{target_service}' not found.", file=sys.stderr)
            sys.exit(1)
        items = [(target_service, vault[target_service])]

    aliases = load_aliases()
    for service, api_key in items:
        var_name = aliases.get(service, env_var_name(service))
        print(f"export {var_name}={shlex.quote(api_key)}")


MENU_COMMANDS = [
    "add", "get", "list", "update", "delete",
    "import", "backup", "restore", "alias",
    "mint", "tokens", "revoke",
    "help", "exit",
]

HELP_TEXT = """\
MicroVault — a local, offline, encrypted CLI vault for API keys.

USAGE
  microvault                   Launch the interactive vault
  microvault env [service]     Print `export SERVICE_API_KEY=...` lines for
                                shell eval (all keys, or just one service)
  microvault --help            Show this help

INTERACTIVE COMMANDS
  Each command works two ways: type it alone and you'll be prompted for
  its argument, or type the argument inline on the same line.

  add [service]         Store a new key. Service name may be inline
                         (e.g. `add openai`); the key itself is always
                         entered via a separate hidden prompt, never
                         inline, so it's never visible on screen or
                         typed on the same line as a command.
  get [service]          Print a stored key.
                         e.g. `get openai`
  list                   List all services with keys masked.
  update [service]       Replace a stored key (hidden prompt, as with add).
                         e.g. `update openai`
  delete [service]       Remove a stored key.
                         e.g. `delete openai`
  import [path]          Bulk-import from a text file of `name=key` /
                         `name: key` / `name key` / `export name=key`
                         lines (one per line). Shows parsed service names
                         only, never values, before writing.
                         e.g. `import ~/Desktop/keys.txt`
  backup                  Force an extra timestamped snapshot right now
                         (e.g. before something risky) — every add/
                         update/delete/import already auto-snapshots on
                         save, to MICROVAULT_HOME/backups/ and
                         MICROSTACKS_HOME/backups/. Still encrypted with
                         the same master password — no plaintext copies,
                         no cloud, nothing leaves this machine.
  restore [file]          Overwrite the current vault with a backup file.
                         Lists available backups if none given. Exit and
                         relaunch afterward to use the restored vault.
  alias [service]         Override the env var name `env` uses for a
                         service — many real tools expect something other
                         than the default SERVICE_API_KEY (e.g. WPScan
                         wants WPSCAN_API_TOKEN, VirusTotal's CLI wants
                         VTCLI_APIKEY). Suggests a known name when it
                         recognizes the service; always accepts any
                         custom name; blank input clears an existing alias.
                         e.g. `alias wpscan`
  mint [service]         Mint a MicroStacks token for a stored service.
                         e.g. `mint openai`
  tokens                 List MicroStacks tokens and their usage.
  revoke [token]         Revoke a MicroStacks token.
                         e.g. `revoke mstk_openai_4f9a1c2b8e7d`
  exit                   Quit.

SHELL EXAMPLE
  eval "$(microvault env)"        # export every stored key into this shell
  eval "$(microvault env openai)" # export just one
"""


def cli():
    print_banner()
    print()
    password = getpass.getpass("Enter master password: ")

    vault_existed = os.path.exists(VAULT_FILE)
    vault, salt, key = load_vault(password)
    if vault is None:
        print(f"{_ERR}Wrong password, or vault.enc is corrupted.")
        return

    if not vault_existed:
        choice = input("No vault found. Create a new one with this password? (y/n): ").strip().lower()
        if choice != 'y':
            return
        save_vault(vault, salt, key)

    aliases = load_aliases()

    # MicroStacks is a separate encrypted store; only unlock it the first time
    # a mint/tokens/revoke command is actually used, so a problem with it
    # (wrong password against a stray/older file, corruption) can never block
    # plain vault usage.
    microstacks = ms_salt = ms_key = None

    def ensure_microstacks_loaded():
        nonlocal microstacks, ms_salt, ms_key
        if microstacks is not None:
            return True
        existed = os.path.exists(MICROSTACKS_FILE)
        microstacks, ms_salt, ms_key = load_microstacks(password)
        if microstacks is None:
            print(f"{_ERR}MicroStacks: wrong password, or microstacks.enc is corrupted "
                  f"(unrelated to your vault — this only affects mint/tokens/revoke).")
            return False
        if not existed:
            save_microstacks(microstacks, ms_salt, ms_key)
        return True

    while True:
        print(f"\n{_INFO}Commands: {_DIM}add, get, list, update, delete, import, backup,"
              f" restore, alias, mint, tokens, revoke, exit {_INFO}(or hit Enter for a menu)")
        cmd_line = input(f"{_INFO}> {Style.RESET_ALL}").strip()

        if not cmd_line:
            if not sys.stdin.isatty():
                continue
            selected = questionary.select(
                "Choose a command:", choices=MENU_COMMANDS
            ).ask()
            if selected is None:  # Ctrl+C / Esc out of the menu
                continue
            cmd_line = selected

        parts = cmd_line.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else None

        if cmd == 'exit':
            break

        elif cmd == 'help':
            print(HELP_TEXT)

        elif cmd == 'add':
            service = arg or input("Service name (e.g., openai, aws): ").strip()
            api_key = getpass.getpass("API Key (input hidden): ").strip()
            vault[service] = api_key
            save_vault(vault, salt, key)
            print(f"{_OK}Saved {service}.")

        elif cmd == 'get':
            service = arg or input("Service name: ").strip()
            if service in vault:
                print(f"{_INFO}{service}{Style.RESET_ALL}: {vault[service]}")
            else:
                print(f"{_ERR}Key not found.")

        elif cmd == 'list':
            print(f"\n{_INFO}--- Stored Keys ---")
            for service, api_key in vault.items():
                print(f"{_INFO}{service}{Style.RESET_ALL}: {_DIM}{mask_key(api_key)}")
            print(f"{_INFO}-------------------")

        elif cmd == 'update':
            service = arg or input("Service name to update: ").strip()
            if service in vault:
                api_key = getpass.getpass("New API Key (input hidden): ").strip()
                vault[service] = api_key
                save_vault(vault, salt, key)
                print(f"{_OK}Updated.")
            else:
                print(f"{_ERR}Not found.")

        elif cmd == 'delete':
            service = arg or input("Service name to delete: ").strip()
            if service in vault:
                del vault[service]
                save_vault(vault, salt, key)
                print(f"{_OK}Deleted.")
            else:
                print(f"{_ERR}Not found.")

        elif cmd == 'import':
            path = os.path.expanduser(arg or input("Path to key file: ").strip())
            if not os.path.isfile(path):
                print(f"{_ERR}File not found.")
            else:
                entries, failed_lines = parse_key_file(path)
                if failed_lines:
                    print(f"{_WARN}Could not parse line(s): {failed_lines} — skipped.")
                if not entries:
                    print(f"{_WARN}No key/value pairs found.")
                else:
                    print(f"{_INFO}Parsed {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}:")
                    for name in entries:
                        note = f" {_WARN}(overwrites existing)" if name in vault else ""
                        print(f"  - {name}{note}")
                    confirm = input("Import these into the vault? (y/n): ").strip().lower()
                    if confirm == 'y':
                        vault.update(entries)
                        save_vault(vault, salt, key)
                        print(f"{_OK}Imported {len(entries)} key(s).")
                    else:
                        print(f"{_WARN}Cancelled.")

        elif cmd == 'backup':
            # Every add/update/delete/import already auto-snapshots on save;
            # this just forces an extra one on demand (e.g. before something risky).
            snapshot_backup(VAULT_FILE)
            print(f"{_OK}Backed up: {VAULT_FILE}")
            if os.path.exists(MICROSTACKS_FILE):
                snapshot_backup(MICROSTACKS_FILE)
                print(f"{_OK}Backed up: {MICROSTACKS_FILE}")

        elif cmd == 'restore':
            backup_dir = os.path.join(MICROVAULT_HOME, "backups")
            if not os.path.isdir(backup_dir) or not os.listdir(backup_dir):
                print(f"{_ERR}No backups found. Run 'backup' first.")
            else:
                backups = sorted(os.listdir(backup_dir))
                print(f"{_INFO}Available backups:")
                for i, name in enumerate(backups, 1):
                    print(f"  {i}. {name}")
                choice = arg or input("Backup filename (or number) to restore: ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(backups):
                    choice = backups[int(choice) - 1]
                chosen_path = os.path.join(backup_dir, choice)
                if not os.path.isfile(chosen_path):
                    print(f"{_ERR}Backup not found.")
                else:
                    confirm = input(
                        f"This will overwrite your current vault with {choice}. Continue? (y/n): "
                    ).strip().lower()
                    if confirm == 'y':
                        shutil.copy2(chosen_path, VAULT_FILE)
                        print(f"{_OK}Restored. Exit and relaunch MicroVault to use it.")
                    else:
                        print(f"{_WARN}Cancelled.")

        elif cmd == 'alias':
            service = arg or input("Service name to set an alias for: ").strip()
            if service not in vault:
                print(f"{_ERR}Service not found in vault. Add it first.")
            else:
                current = aliases.get(service)
                suggestion = suggest_alias(service)
                prompt = f"Export name for {service}"
                if current:
                    prompt += f" (currently {current}, blank to clear)"
                elif suggestion:
                    prompt += f" (suggested: {suggestion} — press Enter to accept)"
                else:
                    prompt += " (blank to cancel)"
                value = input(f"{prompt}: ").strip()
                if not value and suggestion and not current:
                    value = suggestion
                if not value:
                    if service in aliases:
                        del aliases[service]
                        save_aliases(aliases)
                        print(f"{_OK}Alias cleared for {service} — back to the default name "
                              f"({env_var_name(service)}).")
                    else:
                        print(f"{_WARN}No change.")
                else:
                    aliases[service] = value.upper()
                    save_aliases(aliases)
                    print(f"{_OK}{service} will now export as {aliases[service]}.")

        elif cmd == 'mint':
            if not ensure_microstacks_loaded():
                continue
            service = arg or input("Service name to mint a MicroStack token for: ").strip()
            if service not in vault:
                print(f"{_ERR}Service not found in vault. Add it first.")
            else:
                ms_token = generate_microstack_token(service)
                microstacks[ms_token] = {
                    "service": service,
                    "created": datetime.now(timezone.utc).isoformat(),
                    "tokens_used": 0,
                }
                save_microstacks(microstacks, ms_salt, ms_key)
                print(f"{_OK}Minted for {service}:\n{Style.RESET_ALL}{ms_token}")
                print(f"{_WARN}Save this now — it will only be shown masked from here on.")

        elif cmd == 'tokens':
            if not ensure_microstacks_loaded():
                continue
            print(f"\n{_INFO}--- MicroStacks ---")
            for ms_token, meta in microstacks.items():
                stacks = meta["tokens_used"] / TOKENS_PER_MICROSTACK
                print(f"{_DIM}{mask_key(ms_token)}{Style.RESET_ALL}  "
                      f"service={_INFO}{meta['service']}{Style.RESET_ALL}  "
                      f"created={meta['created']}  "
                      f"usage={_OK}{stacks:.3f} MicroStacks{Style.RESET_ALL} ({meta['tokens_used']} tokens)")
            print(f"{_INFO}-------------------")

        elif cmd == 'revoke':
            if not ensure_microstacks_loaded():
                continue
            ms_token = arg or input("MicroStack token to revoke (full value): ").strip()
            if ms_token in microstacks:
                del microstacks[ms_token]
                save_microstacks(microstacks, ms_salt, ms_key)
                print(f"{_OK}Revoked.")
            else:
                print(f"{_ERR}Not found.")

        else:
            print(f"{_ERR}Unknown command.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(HELP_TEXT)
    elif len(sys.argv) > 1 and sys.argv[1] == "env":
        cmd_env(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        cli()


if __name__ == "__main__":
    main()
