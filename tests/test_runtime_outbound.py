"""Tests for runtime._run_binding outbound pumping behavior."""

from __future__ import annotations

import asyncio
import contextlib

from ccmux_core.message import (
    AssistantText,
    PermissionRequest,
    ToolCall,
    ToolResult,
    UserPrompt,
)
from ccmux_core.state import Dead, Idle
from telegram.error import RetryAfter

from ccmux_core_telegram import runtime
from ccmux_core_telegram.runtime import RuntimeState


async def test_pumps_all_l1_kinds(
    monkeypatch, fake_application, fake_backend, mock_bot
) -> None:
    # Defensive: clear forward/allowlist env in case earlier tests polluted them.
    monkeypatch.delenv("CCMUX_CORE_TELEGRAM_FORWARD_TOOLS", raising=False)
    monkeypatch.delenv("CCMUX_CORE_TELEGRAM_TOOL_ALLOWLIST", raising=False)
    msgs = [
        UserPrompt(text="hi", timestamp=1.0),
        AssistantText(text="hello", timestamp=2.0),
        ToolCall(tool_name="Bash", tool_input={"c": "ls"}, timestamp=3.0),
        ToolResult(tool_name="Bash", output="ok", is_error=False, timestamp=4.0),
        PermissionRequest(tool_name="Bash", tool_input={"c": "rm"}, timestamp=5.0),
    ]
    fake = fake_backend(msgs=msgs, state=Idle(reason="stop"))
    monkeypatch.setattr("ccmux_core_telegram.runtime.Backend", lambda *a, **kw: fake)
    state = RuntimeState()
    fake_application.bot_data["runtime"] = state

    await runtime.start_binding(fake_application, 42, "ccmux", "%0", -100)
    task = state.live_tasks.get(42)
    if task is not None:
        await task

    assert mock_bot.send_message.call_count == 5
    for call in mock_bot.send_message.call_args_list:
        assert call.kwargs["chat_id"] == -100
        assert call.kwargs["message_thread_id"] == 42


async def test_filters_tool_when_forward_tools_false(
    monkeypatch, fake_application, fake_backend, mock_bot
) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_FORWARD_TOOLS", "false")
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_TOOL_ALLOWLIST", "Skill")
    msgs = [
        UserPrompt(text="hi", timestamp=1.0),  # kept
        ToolCall(tool_name="Bash", tool_input={}, timestamp=2.0),  # dropped
        ToolResult(
            tool_name="Bash", output="x", is_error=False, timestamp=3.0
        ),  # dropped
        ToolCall(tool_name="Skill", tool_input={}, timestamp=4.0),  # allowlist
    ]
    fake = fake_backend(msgs=msgs, state=Idle(reason="stop"))
    monkeypatch.setattr("ccmux_core_telegram.runtime.Backend", lambda *a, **kw: fake)
    state = RuntimeState()
    fake_application.bot_data["runtime"] = state

    await runtime.start_binding(fake_application, 42, "ccmux", "%0", -100)
    task = state.live_tasks.get(42)
    if task is not None:
        await task

    # UserPrompt + Skill ToolCall = 2 sends
    assert mock_bot.send_message.call_count == 2


async def test_dead_state_sends_death_notice(
    monkeypatch, fake_application, fake_backend, mock_bot
) -> None:
    fake = fake_backend(msgs=[], state=Dead(reason="session_end", detail="clean"))
    monkeypatch.setattr("ccmux_core_telegram.runtime.Backend", lambda *a, **kw: fake)
    state = RuntimeState()
    fake_application.bot_data["runtime"] = state

    await runtime.start_binding(fake_application, 42, "ccmux", "%0", -100)
    task = state.live_tasks.get(42)
    if task is not None:
        await task

    assert mock_bot.send_message.called
    last = mock_bot.send_message.call_args_list[-1]
    assert "🪦" in last.kwargs["text"]
    assert "session_end" in last.kwargs["text"]


async def test_cancel_does_not_send_death_notice(
    monkeypatch, fake_application, fake_backend, mock_bot
) -> None:
    """Voluntary cancel leaves b.state non-Dead → no death notice."""

    # SlowBackend subclass: messages() sleeps forever until cancelled.
    # Easier than monkey-patching an instance method.
    FakeBackendClass = fake_backend

    class SlowBackend(FakeBackendClass):
        async def messages(self):
            await asyncio.sleep(100)
            yield  # unreachable

    fake = SlowBackend(msgs=[], state=Idle(reason="stop"))
    monkeypatch.setattr("ccmux_core_telegram.runtime.Backend", lambda *a, **kw: fake)
    state = RuntimeState()
    fake_application.bot_data["runtime"] = state

    await runtime.start_binding(fake_application, 42, "ccmux", "%0", -100)
    await asyncio.sleep(0)  # let task start
    task = state.live_tasks.get(42)
    assert task is not None
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # No notice sent (state was Idle, not Dead)
    assert mock_bot.send_message.call_count == 0


async def test_rate_limit_drops_message_and_sends_placeholder(
    monkeypatch, fake_application, fake_backend, mock_bot
) -> None:
    msgs = [UserPrompt(text="hi", timestamp=1.0)]
    fake = fake_backend(msgs=msgs, state=Idle(reason="stop"))
    monkeypatch.setattr("ccmux_core_telegram.runtime.Backend", lambda *a, **kw: fake)
    state = RuntimeState()
    fake_application.bot_data["runtime"] = state

    call_count = {"n": 0}

    async def flaky_send(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RetryAfter(retry_after=5)
        return None

    mock_bot.send_message.side_effect = flaky_send

    await runtime.start_binding(fake_application, 42, "ccmux", "%0", -100)
    task = state.live_tasks.get(42)
    if task is not None:
        await task

    # 2 calls: first the dropped one (raised), second the placeholder
    assert call_count["n"] == 2
    placeholder_call = mock_bot.send_message.call_args_list[-1]
    assert "dropped" in placeholder_call.kwargs["text"].lower()
