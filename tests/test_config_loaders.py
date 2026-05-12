"""Tests for settings.env / .env file loaders + facade setdefault."""

from __future__ import annotations

import os

import pytest

from ccmux_core_telegram import config

_DIRTY_VARS = (
    "CCMUX_CORE_TELEGRAM_DIR",
    "CCMUX_CORE_TELEGRAM_FORWARD_TOOLS",
    "CCMUX_CORE_DIR",
    "TELEGRAM_BOT_TOKEN",
    "KEY_X",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip relevant env vars before AND after each test.

    The loader tests call ``config._load_settings_env_files`` /
    ``_load_dotenv_files`` which write to ``os.environ`` via
    ``setdefault``. ``setdefault`` writes are NOT tracked by
    monkeypatch, so without a post-test scrub the vars leak to
    subsequent tests in the suite. Yield-then-pop ensures isolation.
    """
    for var in _DIRTY_VARS:
        monkeypatch.delenv(var, raising=False)
    yield
    for var in _DIRTY_VARS:
        os.environ.pop(var, None)


def test_load_settings_env_global(monkeypatch, tmp_path) -> None:
    d = tmp_path / "global"
    d.mkdir()
    (d / "settings.env").write_text("CCMUX_CORE_TELEGRAM_FORWARD_TOOLS=false\n")
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(d))
    monkeypatch.chdir(tmp_path)  # cwd has no settings.env
    config._load_settings_env_files()
    assert os.environ["CCMUX_CORE_TELEGRAM_FORWARD_TOOLS"] == "false"


def test_load_settings_env_cwd_overrides_global(monkeypatch, tmp_path) -> None:
    d = tmp_path / "global"
    d.mkdir()
    (d / "settings.env").write_text("KEY_X=from_global\n")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "settings.env").write_text("KEY_X=from_cwd\n")
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(d))
    monkeypatch.chdir(cwd)
    config._load_settings_env_files()
    assert os.environ["KEY_X"] == "from_cwd"


def test_shell_export_wins_over_settings_env(monkeypatch, tmp_path) -> None:
    d = tmp_path / "global"
    d.mkdir()
    (d / "settings.env").write_text("CCMUX_CORE_TELEGRAM_FORWARD_TOOLS=false\n")
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(d))
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_FORWARD_TOOLS", "true")
    monkeypatch.chdir(tmp_path)
    config._load_settings_env_files()
    assert os.environ["CCMUX_CORE_TELEGRAM_FORWARD_TOOLS"] == "true"


def test_load_dotenv_files(monkeypatch, tmp_path) -> None:
    d = tmp_path / "global"
    d.mkdir()
    (d / ".env").write_text("TELEGRAM_BOT_TOKEN=secret\n")
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(d))
    monkeypatch.chdir(tmp_path)
    config._load_dotenv_files()
    assert os.environ["TELEGRAM_BOT_TOKEN"] == "secret"


def test_setdefault_ccmux_core_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(tmp_path))
    config._setdefault_upstream_dir()
    assert os.environ["CCMUX_CORE_DIR"] == str(tmp_path / "ccmux-core")


def test_setdefault_respects_shell_export(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(tmp_path))
    monkeypatch.setenv("CCMUX_CORE_DIR", "/custom/path")
    config._setdefault_upstream_dir()
    assert os.environ["CCMUX_CORE_DIR"] == "/custom/path"
