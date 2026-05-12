"""Environment-variable / settings.env / .env resolution.

Parses ``settings.env`` and ``.env`` files into ``os.environ`` via
``setdefault`` (shell exports always win). Parser is rolled own to
match the ccmux-core family convention (no python-dotenv dependency).
"""

from __future__ import annotations

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
