"""Tests for picker.on_steal_callback (claiming a session from another topic)."""

from __future__ import annotations

import asyncio
import json

from ccmux_core.state import Idle

from ccmux_core_telegram import binding, picker
from ccmux_core_telegram.runtime import RuntimeState


def _write_core(state_dir, data: dict) -> None:
    p = state_dir / "ccmux-core" / "bindings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


async def test_steal_transfers_ownership(
    monkeypatch,
    state_dir,
    fake_application,
    mock_bot,
    fake_backend,
    make_update_fixture,
) -> None:
    """Stealing notifies old topic, cancels old task, removes old entry, starts new."""
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    fake = fake_backend(msgs=[], state=Idle(reason="stop"))
    monkeypatch.setattr(
        "ccmux_core_telegram.runtime.Backend",
        lambda *a, **kw: fake,
    )
    _write_core(
        state_dir,
        {
            "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
        },
    )

    # Setup: topic 99 currently owns "ccmux"
    binding.put(topic_id=99, tmux_session="ccmux", group_chat_id=-100)
    state = RuntimeState()
    fake_application.bot_data["runtime"] = state

    # Simulate an old task in state.live_tasks
    async def _stub():
        await asyncio.sleep(100)

    old_task = asyncio.create_task(_stub())
    state.live_tasks[99] = old_task

    # New topic 42 steals ccmux
    update = make_update_fixture(
        callback_data="steal:ccmux",
        message_thread_id=42,
        chat_id=-100,
        user_id=1,
    )
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_steal_callback(update, context)

    # Old topic notified
    notice_calls = [
        c
        for c in mock_bot.send_message.call_args_list
        if c.kwargs.get("message_thread_id") == 99
    ]
    assert len(notice_calls) == 1
    assert "claimed" in notice_calls[0].kwargs["text"].lower()

    # Old entry removed
    assert binding.get(99) is None
    # New entry written
    new = binding.get(42)
    assert new is not None
    assert new.tmux_session == "ccmux"
    # New task started
    assert 42 in state.live_tasks
    # Old task was cancelled (cancel() called; transition may be pending)
    assert old_task.cancelled() or old_task.done() or old_task.cancelling()


async def test_self_steal_is_noop(
    monkeypatch, state_dir, fake_application, mock_bot, make_update_fixture
) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    _write_core(state_dir, {"ccmux": {"current_session_id": "sid", "pane_id": "%0"}})
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
    fake_application.bot_data["runtime"] = RuntimeState()

    update = make_update_fixture(
        callback_data="steal:ccmux",
        message_thread_id=42,
        chat_id=-100,
        user_id=1,
    )
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_steal_callback(update, context)

    # Already-bound message, no transfer
    update.callback_query.edit_message_text.assert_called_once()
    args, _kw = update.callback_query.edit_message_text.call_args
    assert "already" in args[0].lower() or "no change" in args[0].lower()
