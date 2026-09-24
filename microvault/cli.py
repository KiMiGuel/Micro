"""
MicroVault CLI — interactive vault shell, env exporter, and process runner.

This module owns all user-facing behavior: the banner, the interactive
command loop, `microvault env`, and `microvault run`.  Core crypto and
storage logic lives in core.py; the public importable API lives in vault.py.
"""

import json
import os
import re
import sys
import shlex
import shutil
import getpass
from datetime import datetime, timezone
from colorama import init as _colorama_init, Fore, Style
import questionary

from .core import (
    MICROVAULT_HOME,
    VAULT_FILE,
    ALIASES_FILE,
    MICROSTACKS_HOME,
    MICROSTACKS_FILE,
    load_vault,
    save_vault,
    snapshot_backup,
    load_microstacks,
    save_microstacks,
    mask_key,
    env_var_name,
    KNOWN_ALIASES,
    suggest_alias,
    load_aliases,
    save_aliases,
    load_profiles,
    save_profiles,
    parse_key_file,
    generate_microstack_token,
    TOKENS_PER_MICROSTACK,
)

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


# ── sub-commands ─────────────────────────────────────────────────────────


def cmd_env(target_service: str = None, profile: str = None, as_json: bool = False):
    """Prints `export NAME=value` lines to stdout for shell eval. All other
    output (prompts, errors) goes to stderr so stdout stays eval-safe.

    With *profile*, only the services listed in that named profile are
    exported — everything else in the vault stays out of the output
    entirely, even though unlocking still decrypts the whole vault file
    in this process (Fernet encrypts it as one blob; a profile scopes what
    crosses back out to the caller, not what gets decrypted in memory).

    With *as_json*, prints `{"service": "key", ...}` instead of export
    lines — one password prompt gets every service's raw value back by its
    vault-native name, keyed the same way regardless of any alias, so a
    calling tool can fetch a whole profile in a single subprocess call
    instead of re-prompting once per service."""
    if not os.path.exists(VAULT_FILE):
        print("MicroVault: no vault found.", file=sys.stderr)
        sys.exit(1)

    if target_service and profile:
        print("MicroVault: pass a service name or --profile, not both.", file=sys.stderr)
        sys.exit(1)

    password = getpass.getpass("Enter master password: ")
    data, salt, key = load_vault(password)
    if data is None:
        print("MicroVault: wrong password or corrupted vault.", file=sys.stderr)
        sys.exit(1)

    if profile:
        profiles = load_profiles()
        if profile not in profiles:
            print(f"MicroVault: profile '{profile}' not found. Create it with: "
                  f"microvault profile {profile} <service1> [service2 ...]", file=sys.stderr)
            sys.exit(1)
        items = [(s, data[s]) for s in profiles[profile] if s in data]
    elif target_service:
        if target_service not in data:
            print(f"MicroVault: service '{target_service}' not found.", file=sys.stderr)
            sys.exit(1)
        items = [(target_service, data[target_service])]
    else:
        items = data.items()

    if as_json:
        print(json.dumps(dict(items)))
        return

    aliases = load_aliases()
    for service, api_key in items:
        var_name = aliases.get(service, env_var_name(service))
        print(f"export {var_name}={shlex.quote(api_key)}")


def cmd_profile(args: list[str]):
    """Manage named, non-secret groups of service names that scope
    `microvault env --profile <name>` to just that subset of the vault."""
    profiles = load_profiles()

    if not args:
        if not profiles:
            print("No profiles defined yet. Create one with: "
                  "microvault profile <name> <service1> [service2 ...]")
            return
        print("Profiles:")
        for name, services in sorted(profiles.items()):
            print(f"  {name}: {', '.join(services) or '(empty)'}")
        return

    if args[0] == "delete":
        if len(args) < 2:
            print(f"{_ERR}Usage: microvault profile delete <name>", file=sys.stderr)
            sys.exit(1)
        name = args[1]
        if name not in profiles:
            print(f"MicroVault: profile '{name}' not found.", file=sys.stderr)
            sys.exit(1)
        del profiles[name]
        save_profiles(profiles)
        print(f"{_OK}Deleted profile '{name}'.")
        return

    name = args[0]
    if len(args) == 1:
        if name not in profiles:
            print(f"MicroVault: profile '{name}' not found.", file=sys.stderr)
            sys.exit(1)
        print(f"{name}: {', '.join(profiles[name]) or '(empty)'}")
        return

    services = args[1:]
    profiles[name] = services
    save_profiles(profiles)
    print(f"{_OK}Saved profile '{name}' ({len(services)} service"
          f"{'s' if len(services) != 1 else ''}).")


def cmd_run(service: str, command: list[str]):
    """Unlock the vault, inject *service*'s key into the environment, and
    replace this process with *command*.  The child inherits the key; it is
    never written to disk or shown on screen."""
    if not command:
        print(f"{_ERR}microvault run: no command given.", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(VAULT_FILE):
        print(f"{_ERR}MicroVault: no vault found. Run `microvault` to create one.",
              file=sys.stderr)
        sys.exit(1)

    password = getpass.getpass("MicroVault password: ")
    data, salt, key = load_vault(password)
    if data is None:
        print(f"{_ERR}Wrong password or corrupted vault.", file=sys.stderr)
        sys.exit(1)

    if service not in data:
        available = ", ".join(data) or "(empty)"
        print(f"{_ERR}Service '{service}' not in vault. Available: {available}",
              file=sys.stderr)
        sys.exit(1)

    aliases = load_aliases()
    var_name = aliases.get(service, env_var_name(service))

    # Inject into this process's environment — execvp inherits it.
    os.environ[var_name] = data[service]

    # execvp replaces the current process entirely (Unix).
    # The key lives in the environment for exactly as long as the child runs.
    os.execvp(command[0], command)


# ── interactive CLI ──────────────────────────────────────────────────────

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
  microvault env --profile P   Print `export` lines for just profile P's
                                services — nothing else in the vault
  microvault profile           List profiles, or manage them (see below)
  microvault run svc -- cmd    Run a command with a service's key injected
                                into its environment (never persisted)
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

PROFILES
  A profile is a named, non-secret list of service names that scopes
  `microvault env` to just that subset — useful when several tools share
  one vault and each should only ever see its own keys.

  microvault profile                          List all profiles.
  microvault profile mexicosint svc1 svc2     Create/overwrite a profile.
  microvault profile mexicosint               Show one profile's services.
  microvault profile delete mexicosint        Remove a profile.

SHELL EXAMPLE
  eval "$(microvault env)"                    # export every stored key
  eval "$(microvault env openai)"             # export just one
  eval "$(microvault env --profile mexicosint)"  # export just a profile
  microvault run github -- npx -y @modelcontextprotocol/server-github
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
    if len(sys.argv) <= 1:
        cli()
        return

    first = sys.argv[1]

    if first in ("--help", "-h"):
        print(HELP_TEXT)

    elif first == "env":
        argv = sys.argv[2:]
        profile = None
        if "--profile" in argv:
            idx = argv.index("--profile")
            if idx + 1 >= len(argv):
                print(f"{_ERR}Usage: microvault env --profile <name> [service]", file=sys.stderr)
                sys.exit(1)
            profile = argv[idx + 1]
            del argv[idx:idx + 2]
        as_json = "--json" in argv
        if as_json:
            argv.remove("--json")
        cmd_env(argv[0] if argv else None, profile=profile, as_json=as_json)

    elif first == "profile":
        cmd_profile(sys.argv[2:])

    elif first == "run":
        # microvault run <service> -- <command> [args...]
        args = sys.argv[2:]
        if "--" not in args:
            print(f"{_ERR}Usage: microvault run <service> -- <command> [args...]",
                  file=sys.stderr)
            sys.exit(1)
        sep = args.index("--")
        if sep == 0:
            print(f"{_ERR}Usage: microvault run <service> -- <command> [args...]",
                  file=sys.stderr)
            sys.exit(1)
        service = args[0]
        command = args[sep + 1:]
        cmd_run(service, command)

    else:
        cli()
