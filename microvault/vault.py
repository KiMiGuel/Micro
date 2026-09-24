"""
Public API for MicroVault — importable from any Python tool.

Usage:

    from microvault import vault

    # first call in a session prompts for the master password;
    # subsequent calls reuse the in-memory session
    key = vault.get("github")
    env = vault.env_name("github")  # respects aliases
    all_keys = vault.list()
"""

import os
import getpass
import shlex
import subprocess

from .core import (
    VAULT_FILE,
    load_vault,
    load_aliases,
    mask_key,
    env_var_name as _default_env_name,
)


class _Session:
    """Holds the decrypted vault in memory for the lifetime of one process.
    The password is prompted once, then discarded."""

    def __init__(self):
        self._data = None
        self._salt = None
        self._key = None
        self._aliases = None
        self._unlocked = False

    def _ensure_unlocked(self):
        if self._unlocked:
            return True
        if not os.path.exists(VAULT_FILE):
            raise FileNotFoundError(
                f"No vault found at {VAULT_FILE}. "
                "Run `microvault` interactively to create one first."
            )
        password = getpass.getpass("MicroVault password: ")
        data, salt, key = load_vault(password)
        if data is None:
            raise PermissionError("Wrong password or corrupted vault.")
        self._data = data
        self._salt = salt
        self._key = key
        self._aliases = load_aliases()
        self._unlocked = True
        return True

    # ── public queries ───────────────────────────────────────────────

    def get(self, service: str) -> str:
        """Decrypt and return the API key for *service*.
        Prompts for the master password on first call per process."""
        self._ensure_unlocked()
        if service not in self._data:
            raise KeyError(
                f"Service '{service}' not in vault. "
                f"Available: {', '.join(self._data) or '(empty)'}"
            )
        return self._data[service]

    def list(self) -> dict:
        """Return {service: masked_key} for every stored service."""
        self._ensure_unlocked()
        return {svc: mask_key(key) for svc, key in self._data.items()}

    def services(self) -> list[str]:
        """Return the list of stored service names."""
        self._ensure_unlocked()
        return [name for name in self._data.keys()]

    def env_name(self, service: str) -> str:
        """Return the env-var name that `microvault env` would export for
        this service (respects aliases)."""
        self._ensure_unlocked()
        return self._aliases.get(service, _default_env_name(service))

    def export_line(self, service: str) -> str:
        """Return a single `export NAME=value` line for shell eval."""
        key = self.get(service)
        name = self.env_name(service)
        return f"export {name}={shlex.quote(key)}"

    # ── subprocess execution ─────────────────────────────────────────

    def run(self, service: str, command: list[str]) -> int:
        """Export *service*'s key into the environment and exec *command*
        in the current process.  The child inherits the key; it is never
        written to disk or shown on screen.

        Returns the process exit code (only if execvp is not available)."""
        self._ensure_unlocked()
        key = self.get(service)
        name = self.env_name(service)

        # Inject into this process's environment — execvp inherits it.
        os.environ[name] = key

        # Prefer execvp — replaces this process entirely (Unix).
        # Falls back to Popen on platforms where execvp isn't available.
        if hasattr(os, "execvp"):
            os.execvp(command[0], command)
            # execvp replaces the process — this line is never reached.
        else:
            result = subprocess.run(command)
            return result.returncode


# Module-level singleton.  Importers get this object directly:
#   from microvault import vault
#   vault.get("openai")
_session = _Session()


def get(service: str) -> str:
    """Get an API key by service name."""
    return _session.get(service)


def list() -> dict:
    """List all services with masked keys."""
    return _session.list()


def services() -> list[str]:
    """List all service names."""
    return _session.services()


def env_name(service: str) -> str:
    """Get the env-var name for a service (respects aliases)."""
    return _session.env_name(service)


def export_line(service: str) -> str:
    """Get a full `export NAME=value` line for a service."""
    return _session.export_line(service)


def run(service: str, command: list[str]) -> int:
    """Run a command with a service's key in the environment."""
    return _session.run(service, command)
