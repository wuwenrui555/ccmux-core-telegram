"""Tests for picker.on_pick_callback (selecting an unbound session)."""

from __future__ import annotations

import json

from ccmux_core.state import Idle

from ccmux_core_telegram import binding, picker
from ccmux_core_telegram.runtime import RuntimeState


def _write_core(state_dir, data: dict) -> None:
    p = state_dir / "ccmux-core" / "bindings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


async def test_pick_persists_binding_and_starts_task(
    monkeypatch, state_dir, fake_application, fake_backend, make_update_fixture
) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    fake = fake_backend(msgs=[], state=Idle(reason="stop"))
    monkeypatch.setattr(
        "ccmux_core_telegram.runtime.Backend",
        lambda *a, **kw: fake,
    )
    fake_application.bot_data["runtime"] = RuntimeState()
    _write_core(
        state_dir,
        {
            "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
        },
    )

    update = make_update_fixture(
        callback_data="pick:ccmux",
        message_thread_id=42,
        chat_id=-100,
        user_id=1,
    )
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_pick_callback(update, context)

    # Binding persisted
    b = binding.get(42)
    assert b is not None
    assert b.tmux_session == "ccmux"
    # Task started
    state = fake_application.bot_data["runtime"]
    assert 42 in state.live_tasks


async def test_pick_rejects_non_allowed_user(
    monkeypatch, state_dir, fake_application, make_update_fixture
) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    fake_application.bot_data["runtime"] = RuntimeState()
    update = make_update_fixture(
        callback_data="pick:ccmux",
        message_thread_id=42,
        user_id=999,  # not in allowlist
    )
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_pick_callback(update, context)
    assert binding.get(42) is None


async def test_pick_handles_session_no_longer_live(
    monkeypatch, state_dir, fake_application, make_update_fixture
) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    fake_application.bot_data["runtime"] = RuntimeState()
    _write_core(state_dir, {})  # session vanished
    update = make_update_fixture(
        callback_data="pick:gone",
        message_thread_id=42,
        user_id=1,
    )
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_pick_callback(update, context)
    update.callback_query.edit_message_text.assert_called_once()
    args, _kw = update.callback_query.edit_message_text.call_args
    assert "no longer live" in args[0].lower() or "/start" in args[0]
    assert binding.get(42) is None


async def test_pick_self_rebind_succeeds(
    monkeypatch, state_dir, fake_application, fake_backend, make_update_fixture
) -> None:
    """When the current topic already owns the session, picking it again succeeds (cct#2)."""
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    fake = fake_backend(msgs=[], state=Idle(reason="stop"))
    monkeypatch.setattr(
        "ccmux_core_telegram.runtime.Backend",
        lambda *a, **kw: fake,
    )
    fake_application.bot_data["runtime"] = RuntimeState()
    _write_core(
        state_dir,
        {
            "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
        },
    )
    # Seed the topic binding: topic 42 already owns "ccmux".
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)

    update = make_update_fixture(
        callback_data="pick:ccmux",
        message_thread_id=42,
        chat_id=-100,
        user_id=1,
    )
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_pick_callback(update, context)

    # Binding still present (overwritten, not removed).
    b = binding.get(42)
    assert b is not None
    assert b.tmux_session == "ccmux"
    # Task started for the (re-)bound topic.
    state = fake_application.bot_data["runtime"]
    assert 42 in state.live_tasks
    # No "bound elsewhere" rejection.
    edit_calls = update.callback_query.edit_message_text.call_args_list
    assert all(
        "bound elsewhere" not in (call.args[0] if call.args else "")
        for call in edit_calls
    )


async def test_pick_cross_topic_still_rejected(
    monkeypatch, state_dir, fake_application, make_update_fixture
) -> None:
    """When another topic owns the session, /start pick is still rejected."""
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    fake_application.bot_data["runtime"] = RuntimeState()
    _write_core(
        state_dir,
        {
            "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
        },
    )
    # Seed: topic 99 owns "ccmux"; we'll click pick from topic 42.
    binding.put(topic_id=99, tmux_session="ccmux", group_chat_id=-100)

    update = make_update_fixture(
        callback_data="pick:ccmux",
        message_thread_id=42,
        chat_id=-100,
        user_id=1,
    )
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_pick_callback(update, context)

    # Topic 42 was NOT bound.
    assert binding.get(42) is None
    # Topic 99 still owns it (untouched).
    assert binding.get(99) is not None
    # Rejection text was shown.
    update.callback_query.edit_message_text.assert_called_once()
    args, _kw = update.callback_query.edit_message_text.call_args
    assert "bound elsewhere" in args[0]
