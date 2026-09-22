"""
MicroVault — a local, offline, encrypted vault for API keys.

Public API (for programmatic use from other Python tools):

    from microvault import vault

    key = vault.get("github")
    env = vault.env_name("github")
    all_keys = vault.list()

CLI entry point:

    microvault                 Interactive vault shell
    microvault env [service]   Export keys as shell env vars
    microvault run svc -- cmd  Run a command with a key injected
"""

from . import vault  # noqa: F401 — re-export so `from microvault import vault` works


def main():
    from .cli import main as _cli_main
    _cli_main()
