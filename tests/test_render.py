"""Tests for L1 Message → Telegram text rendering."""

from __future__ import annotations

from ccmux_core.message import (
    AssistantText,
    PermissionRequest,
    ToolCall,
    ToolResult,
    UserPrompt,
)

from ccmux_core_telegram import render


def test_format_user_prompt() -> None:
    msg = UserPrompt(text="hello world", timestamp=1234567890.0)
    text, parse_mode = render.format(msg)
    assert "hello world" in text
    assert "👤" in text


def test_format_assistant_text() -> None:
    msg = AssistantText(text="I can help", timestamp=1234567890.0)
    text, parse_mode = render.format(msg)
    assert "I can help" in text
    assert "🤖" in text


def test_format_tool_call() -> None:
    msg = ToolCall(
        tool_name="Bash",
        tool_input={"command": "ls -la"},
        timestamp=1234567890.0,
    )
    text, parse_mode = render.format(msg)
    assert "Bash" in text
    assert "🔧" in text


def test_format_tool_result_success() -> None:
    msg = ToolResult(
        tool_name="Bash",
        output="file1\nfile2",
        is_error=False,
        timestamp=1234567890.0,
    )
    text, parse_mode = render.format(msg)
    assert "Bash" in text
    assert "file1" in text
    assert "✅" in text


def test_format_tool_result_error() -> None:
    msg = ToolResult(
        tool_name="Bash",
        output="command not found",
        is_error=True,
        timestamp=1234567890.0,
    )
    text, parse_mode = render.format(msg)
    assert "❌" in text


def test_format_permission_request() -> None:
    msg = PermissionRequest(
        tool_name="Bash",
        tool_input={"command": "rm -rf /"},
        timestamp=1234567890.0,
    )
    text, parse_mode = render.format(msg)
    assert "Bash" in text
    assert "🔐" in text


def test_truncates_long_tool_result() -> None:
    long_output = "x" * 10000
    msg = ToolResult(
        tool_name="Bash",
        output=long_output,
        is_error=False,
        timestamp=1234567890.0,
    )
    text, parse_mode = render.format(msg)
    # Telegram limit is 4096; we leave room for the prefix.
    assert len(text) <= 4096
    assert "…" in text or "truncated" in text.lower()
