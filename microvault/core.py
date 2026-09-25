"""
Core primitives shared by the CLI, the public API module, and any future
integrations.  This file is import-safe — it never prompts for a password,
never prints banners, and never calls sys.exit on its own.

Everything lives here so the package can split CLI vs. API without
duplicating crypto, storage, or alias logic.
"""

import json
import os
import re
import shutil
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

# ── paths ────────────────────────────────────────────────────────────────

MICROVAULT_HOME = os.environ.get(
    "MICROVAULT_HOME", os.path.expanduser("~/.microvault")
)
VAULT_FILE = os.path.join(MICROVAULT_HOME, "vault.enc")
ALIASES_FILE = os.path.join(MICROVAULT_HOME, "aliases.json")
PROFILES_FILE = os.path.join(MICROVAULT_HOME, "profiles.json")

# ── crypto constants ─────────────────────────────────────────────────────

SALT_SIZE = 16
PBKDF2_ITERATIONS = 600_000


# ── crypto helpers ───────────────────────────────────────────────────────

def derive_key(password: str, salt: bytes) -> bytes:
    """Derives a 256-bit Fernet key from the master password and salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


# ── store I/O ────────────────────────────────────────────────────────────

def load_store(path: str, password: str):
    """Load and decrypt an encrypted JSON store.  Returns (data, salt, key),
    or (None, None, None) on wrong password / corrupted file, or a fresh
    ({}, salt, key) if the file doesn't exist yet."""
    if not os.path.exists(path):
        salt = os.urandom(SALT_SIZE)
        return {}, salt, derive_key(password, salt)

    with open(path, "rb") as f:
        raw = f.read()

    if len(raw) <= SALT_SIZE:
        return None, None, None

    salt, ciphertext = raw[:SALT_SIZE], raw[SALT_SIZE:]
    key = derive_key(password, salt)

    try:
        data = json.loads(Fernet(key).decrypt(ciphertext).decode("utf-8"))
        return data, salt, key
    except (InvalidToken, ValueError):
        return None, None, None


def save_store(path: str, data: dict, salt: bytes, key: bytes):
    """Encrypt and atomically write a store to disk, reusing the session
    salt/key."""
    ciphertext = Fernet(key).encrypt(json.dumps(data).encode("utf-8"))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(salt + ciphertext)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def snapshot_backup(path: str):
    """Copies a just-written store to a single rolling backup file in its
    own backups/ subfolder."""
    backup_dir = os.path.join(os.path.dirname(path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    name = os.path.splitext(os.path.basename(path))[0]
    backup_path = os.path.join(backup_dir, f"{name}-backup.enc")
    shutil.copy2(path, backup_path)
    os.chmod(backup_path, 0o600)


# ── vault-specific wrappers ──────────────────────────────────────────────

def load_vault(password: str):
    return load_store(VAULT_FILE, password)


def save_vault(data: dict, salt: bytes, key: bytes):
    save_store(VAULT_FILE, data, salt, key)
    snapshot_backup(VAULT_FILE)



# ── display helpers ──────────────────────────────────────────────────────

def mask_key(key: str) -> str:
    """Returns a masked version of the key for display."""
    if len(key) > 10:
        return key[:4] + "..." + key[-4:]
    return "***"


# ── env-var name logic ───────────────────────────────────────────────────

def env_var_name(service: str) -> str:
    """Maps a service name to a default shell env var, e.g. 'openai' ->
    'OPENAI_API_KEY'.  Strips a trailing _api/_key/_api_key from the service
    name first, so a name like 'shodan_api' produces 'SHODAN_API_KEY'
    instead of doubling up as 'SHODAN_API_API_KEY'."""
    name = service.strip()
    name = re.sub(r"(?i)_api_key$", "", name)
    name = re.sub(r"(?i)_key$", "", name)
    name = re.sub(r"(?i)_api$", "", name)
    name = name.strip("_")
    sanitized = re.sub(r"[^A-Za-z0-9]", "_", name)
    return f"{sanitized.upper()}_API_KEY"


# A convenience nudge only — 'alias' always accepts a fully custom name
# regardless of whether a service is in this table, so this list being
# incomplete never blocks anyone.
KNOWN_ALIASES = {
    "github": "GITHUB_PERSONAL_ACCESS_TOKEN",
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
    """Loose substring match against KNOWN_ALIASES.  Returns None when
    nothing matches — the service just uses the default name."""
    key = re.sub(r"[^a-z0-9]", "", service.lower())
    for pattern, env_name in KNOWN_ALIASES.items():
        if pattern in key:
            return env_name
    return None


# ── aliases I/O (plain JSON, not encrypted — they're just names) ─────────

def load_aliases() -> dict:
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


# ── profiles I/O (plain JSON, not encrypted — just service-name lists) ───
# A profile scopes `microvault env --profile <name>` (and the matching
# Python API call) to a named subset of services, so a specific tool only
# ever sees the keys it actually uses instead of every key in the vault.
# Profile membership is not secret — it's the same kind of metadata as
# aliases.json — so, like aliases, it never requires the master password.

def load_profiles() -> dict:
    if not os.path.exists(PROFILES_FILE):
        return {}
    try:
        with open(PROFILES_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_profiles(profiles: dict):
    os.makedirs(os.path.dirname(PROFILES_FILE), exist_ok=True)
    tmp_path = PROFILES_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(profiles, f, indent=2, sort_keys=True)
    os.replace(tmp_path, PROFILES_FILE)


# ── key file import parser ───────────────────────────────────────────────

def parse_key_file(path: str):
    """Parses a text file of API keys into {service: key} pairs."""
    entries = {}
    failed_lines = []
    with open(path, "r") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            line = re.sub(r"^export\s+", "", line, flags=re.IGNORECASE)

            sep = re.search(r"[:=]", line)
            if sep:
                name, value = line[: sep.start()], line[sep.end() :]
            else:
                match = re.match(r"^(\S+)\s+(\S+)$", line)
                if not match:
                    failed_lines.append(lineno)
                    continue
                name, value = match.group(1), match.group(2)

            name = name.strip().strip("\"'")
            value = value.strip().strip("\"'")
            if not name or not value:
                failed_lines.append(lineno)
                continue
            name = re.sub(r"(?i)_api_key$", "", name)
            name = re.sub(r"(?i)_key$", "", name)
            name = re.sub(r"\s+", "_", name.strip("_"))
            name = name.lower()
            entries[name] = value
    return entries, failed_lines
