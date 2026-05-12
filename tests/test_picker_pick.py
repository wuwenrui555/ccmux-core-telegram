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
