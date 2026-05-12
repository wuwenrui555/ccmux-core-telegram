"""Environment-variable / settings.env / .env resolution.

Parses ``settings.env`` and ``.env`` files into ``os.environ`` via
``setdefault`` (shell exports always win). Parser is rolled own to
match the ccmux-core family convention (no python-dotenv dependency).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a settings.env or .env file into a dict.

    Returns ``{}`` if the file is missing or unreadable. Ignores blank
    lines, lines starting with ``#``, and malformed lines (no leading
    letter, missing ``=``).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _KEY_VALUE_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        # Strip inline # comment in unquoted values
        if value and not (value.startswith('"') or value.startswith("'")):
            if "#" in value:
                value = value.split("#", 1)[0].strip()
        # Strip matching surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        out[key] = value
    return out


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_DIR = "~/.ccmux-core-telegram"
DEFAULT_LOG_LEVEL = "DEBUG"
DEFAULT_FORWARD_TOOLS = True
DEFAULT_TOOL_ALLOWLIST = frozenset({"Skill"})
DEFAULT_BOOTSTRAP_RETRIES = -1


# ---------------------------------------------------------------------------
# Path accessors
# ---------------------------------------------------------------------------


def ccmux_core_telegram_dir() -> Path:
    raw = os.environ.get("CCMUX_CORE_TELEGRAM_DIR", DEFAULT_DIR)
    return Path(raw).expanduser()


def topic_bindings_path() -> Path:
    return ccmux_core_telegram_dir() / "topic_bindings.json"


def ccmux_core_bindings_path() -> Path:
    return ccmux_core_telegram_dir() / "ccmux-core" / "bindings.json"


def settings_env_path() -> Path:
    return ccmux_core_telegram_dir() / "settings.env"


def dotenv_path() -> Path:
    return ccmux_core_telegram_dir() / ".env"


def log_file() -> Path:
    raw = os.environ.get("CCMUX_CORE_TELEGRAM_LOG_FILE")
    if raw:
        return Path(raw).expanduser()
    return ccmux_core_telegram_dir() / "ccmux-core-telegram.log"


# ---------------------------------------------------------------------------
# Value accessors
# ---------------------------------------------------------------------------


def bot_token() -> str:
    raw = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not raw:
        raise ConfigError("TELEGRAM_BOT_TOKEN required (set in .env)")
    return raw


def allowed_users() -> frozenset[int]:
    raw = os.environ.get("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "")
    if not raw:
        raise ConfigError(
            "CCMUX_CORE_TELEGRAM_ALLOWED_USERS required (comma-separated Telegram user IDs)"
        )
    try:
        return frozenset(int(s.strip()) for s in raw.split(",") if s.strip())
    except ValueError as e:
        raise ConfigError(
            f"CCMUX_CORE_TELEGRAM_ALLOWED_USERS contains non-numeric: {e}"
        ) from e


def forward_tools() -> bool:
    raw = os.environ.get("CCMUX_CORE_TELEGRAM_FORWARD_TOOLS")
    if raw is None:
        return DEFAULT_FORWARD_TOOLS
    return raw.lower() != "false"


def tool_allowlist() -> frozenset[str]:
    raw = os.environ.get("CCMUX_CORE_TELEGRAM_TOOL_ALLOWLIST")
    if raw is None:
        return DEFAULT_TOOL_ALLOWLIST
    names = {s.strip() for s in raw.split(",") if s.strip()}
    return frozenset(names) if names else DEFAULT_TOOL_ALLOWLIST


def log_level() -> str:
    return os.environ.get("CCMUX_CORE_TELEGRAM_LOG_LEVEL", DEFAULT_LOG_LEVEL)


def bootstrap_retries() -> int:
    raw = os.environ.get("CCMUX_CORE_TELEGRAM_BOOTSTRAP_RETRIES")
    if raw is None or not raw.strip():
        return DEFAULT_BOOTSTRAP_RETRIES
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_BOOTSTRAP_RETRIES


def validate_required_env() -> None:
    """Raise ConfigError if any required env var is missing.

    Reads (and discards) bot_token() and allowed_users() so a missing
    value surfaces at startup, not at first use.
    """
    bot_token()
    allowed_users()


# ---------------------------------------------------------------------------
# File loaders + facade setdefault (run at import time, see bottom)
# ---------------------------------------------------------------------------

_SETTINGS_ENV_FILENAME = "settings.env"
_DOTENV_FILENAME = ".env"


def _load_settings_env_files() -> None:
    """Source settings.env into os.environ via setdefault.

    Order (later wins among files; shell exports always win via
    ``setdefault``):
      1. ``./settings.env`` (cwd) — loaded first, so its values take
         precedence over global since later setdefault is a no-op.
      2. ``$CCMUX_CORE_TELEGRAM_DIR/settings.env`` (global)
    """
    for path in [Path(_SETTINGS_ENV_FILENAME), settings_env_path()]:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        for key, val in _parse_env_file(path).items():
            os.environ.setdefault(key, val)


def _load_dotenv_files() -> None:
    """Source .env into os.environ via setdefault. Same order as settings.env."""
    for path in [Path(_DOTENV_FILENAME), dotenv_path()]:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        for key, val in _parse_env_file(path).items():
            os.environ.setdefault(key, val)


def _setdefault_upstream_dir() -> None:
    """Redirect ``CCMUX_CORE_DIR`` into cct's state tree (subdir).

    ``setdefault`` semantics: a shell-exported ``CCMUX_CORE_DIR`` still
    wins, giving power users an escape hatch to share ``~/.ccmux-core/``
    across multiple consumers.
    """
    os.environ.setdefault(
        "CCMUX_CORE_DIR",
        str(ccmux_core_telegram_dir() / "ccmux-core"),
    )


# Module-import side effect: load files + facade setdefault.
_load_settings_env_files()
_load_dotenv_files()
_setdefault_upstream_dir()
