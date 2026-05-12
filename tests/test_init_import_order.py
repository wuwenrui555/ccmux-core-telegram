"""Smoke test: __init__.py imports config before _version.

Verifies the import-order contract via static inspection of
``__init__.py`` rather than runtime ``sys.modules`` wiping. Reloading
the package at test runtime would corrupt module references held by
other test files' top-level imports (e.g. ``from ccmux_core_telegram
import runtime``), causing later tests to bind ``Backend`` against a
stale runtime module and silently fall back to the real ccmux-core
Backend — which then hangs.
"""
from __future__ import annotations

from pathlib import Path

import ccmux_core_telegram


def test_init_imports_config_before_version() -> None:
    """config must be imported before _version so the facade setdefault runs first."""
    src = Path(ccmux_core_telegram.__file__).read_text(encoding="utf-8")
    config_pos = src.find("from . import config")
    version_pos = src.find("from ._version")
    assert config_pos >= 0, "expected 'from . import config' in __init__.py"
    assert version_pos >= 0, "expected 'from ._version' in __init__.py"
    assert config_pos < version_pos, "config must be imported before _version"
