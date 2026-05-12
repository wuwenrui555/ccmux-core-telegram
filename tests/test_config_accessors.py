"""Tests for config env-var accessors."""

from __future__ import annotations

from pathlib import Path

import pytest

from ccmux_core_telegram import config


def test_ccmux_core_telegram_dir_default(monkeypatch) -> None:
    monkeypatch.delenv("CCMUX_CORE_TELEGRAM_DIR", raising=False)
    expected = Path("~/.ccmux-core-telegram").expanduser()
    assert config.ccmux_core_telegram_dir() == expected


def test_ccmux_core_telegram_dir_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(tmp_path))
    assert config.ccmux_core_telegram_dir() == tmp_path


def test_bot_token_required(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(config.ConfigError):
        config.bot_token()


def test_bot_token_returns_value(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234:abc")
    assert config.bot_token() == "1234:abc"


def test_allowed_users_required(monkeypatch) -> None:
    monkeypatch.delenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", raising=False)
    with pytest.raises(config.ConfigError):
        config.allowed_users()


def test_allowed_users_parses_ids(monkeypatch) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "100,200, 300 ")
    assert config.allowed_users() == frozenset({100, 200, 300})


def test_forward_tools_default(monkeypatch) -> None:
    monkeypatch.delenv("CCMUX_CORE_TELEGRAM_FORWARD_TOOLS", raising=False)
    assert config.forward_tools() is True


def test_forward_tools_false(monkeypatch) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_FORWARD_TOOLS", "false")
    assert config.forward_tools() is False


def test_tool_allowlist_default(monkeypatch) -> None:
    monkeypatch.delenv("CCMUX_CORE_TELEGRAM_TOOL_ALLOWLIST", raising=False)
    assert config.tool_allowlist() == frozenset({"Skill"})


def test_tool_allowlist_custom(monkeypatch) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_TOOL_ALLOWLIST", "Skill,Read,Bash")
    assert config.tool_allowlist() == frozenset({"Skill", "Read", "Bash"})


def test_log_file_default(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(tmp_path))
    monkeypatch.delenv("CCMUX_CORE_TELEGRAM_LOG_FILE", raising=False)
    assert config.log_file() == tmp_path / "ccmux-core-telegram.log"


def test_log_file_override(monkeypatch, tmp_path) -> None:
    custom = tmp_path / "custom.log"
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_LOG_FILE", str(custom))
    assert config.log_file() == custom


def test_log_level_default(monkeypatch) -> None:
    monkeypatch.delenv("CCMUX_CORE_TELEGRAM_LOG_LEVEL", raising=False)
    assert config.log_level() == "DEBUG"


def test_bootstrap_retries_default(monkeypatch) -> None:
    monkeypatch.delenv("CCMUX_CORE_TELEGRAM_BOOTSTRAP_RETRIES", raising=False)
    assert config.bootstrap_retries() == -1


def test_bootstrap_retries_int(monkeypatch) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_BOOTSTRAP_RETRIES", "5")
    assert config.bootstrap_retries() == 5


def test_topic_bindings_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(tmp_path))
    assert config.topic_bindings_path() == tmp_path / "topic_bindings.json"


def test_ccmux_core_bindings_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(tmp_path))
    assert (
        config.ccmux_core_bindings_path() == tmp_path / "ccmux-core" / "bindings.json"
    )


def test_validate_required_env_ok(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    config.validate_required_env()  # should not raise


def test_validate_required_env_raises_missing_token(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    with pytest.raises(config.ConfigError):
        config.validate_required_env()
