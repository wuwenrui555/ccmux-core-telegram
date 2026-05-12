"""L1 Message → Telegram-bound text + parse_mode.

Pure functions. No PTB types here — we return ``(text, parse_mode)``
tuples that the caller passes to ``bot.send_message``.
"""

from __future__ import annotations

import json
from typing import TypeAlias

from ccmux_core.message import (
    AssistantText,
    Message,
    PermissionRequest,
    ToolCall,
    ToolResult,
    UserPrompt,
)

ParseMode: TypeAlias = str | None

# Telegram per-message text limit (UTF-16 code units; conservative
# byte budget). We trim to this with a margin for the prefix and
# truncation marker.
_MAX_LEN = 4000
_TRUNCATED_MARKER = "\n\n…(truncated)"


def format(msg: Message) -> tuple[str, ParseMode]:
    """Render any L1 Message to (text, parse_mode).

    parse_mode is None for plain-text rendering (MVP). Markdown is
    deferred to a future revision.
    """
    if isinstance(msg, UserPrompt):
        return _format_user_prompt(msg), None
    if isinstance(msg, AssistantText):
        return _format_assistant_text(msg), None
    if isinstance(msg, ToolCall):
        return _format_tool_call(msg), None
    if isinstance(msg, ToolResult):
        return _format_tool_result(msg), None
    if isinstance(msg, PermissionRequest):
        return _format_permission_request(msg), None
    raise ValueError(f"Unknown message type: {type(msg).__name__}")


def _truncate(text: str) -> str:
    if len(text) <= _MAX_LEN:
        return text
    return text[: _MAX_LEN - len(_TRUNCATED_MARKER)] + _TRUNCATED_MARKER


def _format_user_prompt(msg: UserPrompt) -> str:
    return _truncate(f"👤 {msg.text}")


def _format_assistant_text(msg: AssistantText) -> str:
    return _truncate(f"🤖 {msg.text}")


def _format_tool_call(msg: ToolCall) -> str:
    input_summary = json.dumps(msg.tool_input, ensure_ascii=False, indent=2)
    return _truncate(f"🔧 {msg.tool_name}\n{input_summary}")


def _format_tool_result(msg: ToolResult) -> str:
    icon = "❌" if msg.is_error else "✅"
    return _truncate(f"{icon} {msg.tool_name}\n{msg.output}")


def _format_permission_request(msg: PermissionRequest) -> str:
    input_summary = json.dumps(msg.tool_input, ensure_ascii=False, indent=2)
    return _truncate(f"🔐 {msg.tool_name}\n{input_summary}")
