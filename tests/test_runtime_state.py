"""Tests for RuntimeState dataclass + start_binding registration."""
from __future__ import annotations

import asyncio

from ccmux_core_telegram import runtime
from ccmux_core_telegram.runtime import RuntimeState, get_state


def test_runtime_state_defaults() -> None:
    s = RuntimeState()
    assert s.live_tasks == {}
    assert s.backend_handles == {}
    assert s.tracker is None


def test_get_state_reads_from_bot_data(fake_application) -> None:
    s = RuntimeState()
    fake_application.bot_data["runtime"] = s
    assert get_state(fake_application) is s


async def test_start_binding_registers_task(monkeypatch, fake_application, fake_backend) -> None:
    """start_binding creates an asyncio task and stores it in live_tasks."""
    fake = fake_backend(msgs=[])
    monkeypatch.setattr(
        "ccmux_core_telegram.runtime.Backend",
        lambda *a, **kw: fake,
    )
    state = RuntimeState()
    fake_application.bot_data["runtime"] = state

    await runtime.start_binding(
        application=fake_application,
        topic_id=42,
        tmux_session="ccmux",
        pane_id="%0",
        group_chat_id=-100,
    )
    assert 42 in state.live_tasks
    assert isinstance(state.live_tasks[42], asyncio.Task)
    # Capture task before await (finally pop will remove it from dict)
    task = state.live_tasks[42]
    await task
    # After finally cleanup: task removed
    assert 42 not in state.live_tasks
