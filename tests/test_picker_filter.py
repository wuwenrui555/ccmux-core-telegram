"""Tests for picker.on_filter_callback tab switching."""

from __future__ import annotations

import json

from ccmux_core_telegram import picker
from ccmux_core_telegram.runtime import RuntimeState


def _write_core(state_dir, data: dict) -> None:
    p = state_dir / "ccmux-core" / "bindings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


async def test_filter_re_renders_with_new_mode(
    monkeypatch, state_dir, fake_application, make_update_fixture
) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    fake_application.bot_data["runtime"] = RuntimeState()
    _write_core(
        state_dir,
        {
            "live1": {"current_session_id": "sid", "pane_id": "%0"},
        },
    )
    update = make_update_fixture(
        callback_data="filter:unbound",
        message_thread_id=42,
        chat_id=-100,
        user_id=1,
    )
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_filter_callback(update, context)
    update.callback_query.edit_message_text.assert_called_once()
    _args, kwargs = update.callback_query.edit_message_text.call_args
    assert "reply_markup" in kwargs
