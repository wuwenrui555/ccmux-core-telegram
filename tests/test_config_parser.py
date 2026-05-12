"""Tests for settings.env / .env file parsing."""

from __future__ import annotations

from pathlib import Path

from ccmux_core_telegram.config import _parse_env_file


def test_parse_simple_key_value(tmp_path: Path) -> None:
    f = tmp_path / "settings.env"
    f.write_text("CCMUX_CORE_TELEGRAM_FORWARD_TOOLS=true\n")
    assert _parse_env_file(f) == {"CCMUX_CORE_TELEGRAM_FORWARD_TOOLS": "true"}


def test_parse_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    f = tmp_path / "settings.env"
    f.write_text(
        "# this is a comment\n\nKEY=value\n   # indented comment\nANOTHER=value2\n"
    )
    assert _parse_env_file(f) == {"KEY": "value", "ANOTHER": "value2"}


def test_parse_strips_quotes(tmp_path: Path) -> None:
    f = tmp_path / "settings.env"
    f.write_text("KEY1=\"quoted\"\nKEY2='single'\nKEY3=unquoted\n")
    assert _parse_env_file(f) == {
        "KEY1": "quoted",
        "KEY2": "single",
        "KEY3": "unquoted",
    }


def test_parse_strips_inline_comment_in_unquoted_value(tmp_path: Path) -> None:
    f = tmp_path / "settings.env"
    f.write_text("KEY=value  # inline comment\n")
    assert _parse_env_file(f) == {"KEY": "value"}


def test_parse_missing_file_returns_empty(tmp_path: Path) -> None:
    assert _parse_env_file(tmp_path / "nonexistent.env") == {}


def test_parse_ignores_malformed_lines(tmp_path: Path) -> None:
    f = tmp_path / "settings.env"
    f.write_text("not a key value\nKEY=ok\n123BAD=value\n")
    assert _parse_env_file(f) == {"KEY": "ok"}
