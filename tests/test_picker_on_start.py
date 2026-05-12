"""Tests for picker.on_start command handler."""

from __future__ import annotations

import json

from ccmux_core_telegram import picker
from ccmux_core_telegram.runtime import RuntimeState


def _write_core(state_dir, data: dict) -> None:
    p = state_dir / "ccmux-core" / "bindings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


async def test_on_start_outside_topic_replies(
    state_dir, fake_application, make_update_fixture
) -> None:
    fake_application.bot_data["runtime"] = RuntimeState()
    update = make_update_fixture(text="/start", message_thread_id=None)
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_start(update, context)
    update.message.reply_text.assert_called_once()
    args, _kw = update.message.reply_text.call_args
    assert "topic" in args[0].lower()


async def test_on_start_in_topic_renders_picker(
    state_dir, fake_application, make_update_fixture
) -> None:
    fake_application.bot_data["runtime"] = RuntimeState()
    _write_core(
        state_dir,
        {
            "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
        },
    )
    update = make_update_fixture(text="/start", message_thread_id=42)
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_start(update, context)
    update.message.reply_text.assert_called_once()
    _args, kwargs = update.message.reply_text.call_args
    assert "reply_markup" in kwargs  # picker keyboard attached
