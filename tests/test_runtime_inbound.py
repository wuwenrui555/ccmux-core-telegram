"""Tests for runtime.on_inbound_text dispatch behavior."""

from __future__ import annotations

from ccmux_core.state import Idle

from ccmux_core_telegram import binding, runtime
from ccmux_core_telegram.runtime import RuntimeState


async def test_inbound_routes_to_live_backend(
    state_dir, fake_application, fake_backend, make_update_fixture
) -> None:
    fake = fake_backend(msgs=[], state=Idle(reason="stop"))
    state = RuntimeState()
    state.backend_handles[42] = fake
    fake_application.bot_data["runtime"] = state

    update = make_update_fixture(text="hello", message_thread_id=42)
    context = type("Ctx", (), {"application": fake_application})()
    await runtime.on_inbound_text(update, context)

    assert fake.sent_prompts == ["hello"]


async def test_inbound_outside_topic_silent(
    state_dir, fake_application, fake_backend, make_update_fixture
) -> None:
    fake = fake_backend(msgs=[], state=Idle(reason="stop"))
    state = RuntimeState()
    state.backend_handles[42] = fake
    fake_application.bot_data["runtime"] = state

    update = make_update_fixture(text="hello", message_thread_id=None)
    context = type("Ctx", (), {"application": fake_application})()
    await runtime.on_inbound_text(update, context)

    assert fake.sent_prompts == []
    update.message.reply_text.assert_not_called()


async def test_inbound_unbound_topic_silent(
    state_dir, fake_application, make_update_fixture
) -> None:
    state = RuntimeState()
    fake_application.bot_data["runtime"] = state

    update = make_update_fixture(text="hello", message_thread_id=99)
    context = type("Ctx", (), {"application": fake_application})()
    await runtime.on_inbound_text(update, context)

    update.message.reply_text.assert_not_called()


async def test_inbound_dead_topic_replies_hint(
    state_dir, fake_application, make_update_fixture
) -> None:
    # File has a binding, but no live task / backend handle
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
    state = RuntimeState()
    fake_application.bot_data["runtime"] = state

    update = make_update_fixture(text="hello", message_thread_id=42)
    context = type("Ctx", (), {"application": fake_application})()
    await runtime.on_inbound_text(update, context)

    update.message.reply_text.assert_called_once()
    args, _kwargs = update.message.reply_text.call_args
    assert "dead" in args[0].lower() or "rebind" in args[0].lower()


async def test_inbound_dead_error_replies_hint(
    state_dir, fake_application, fake_backend, make_update_fixture
) -> None:
    """DeadError from send_prompt is caught and replied with the dead-hint."""
    from ccmux_core.error import DeadError

    FakeBackendClass = fake_backend

    class _DeadOnSend(FakeBackendClass):
        async def send_prompt(self, text: str) -> None:
            raise DeadError("test")

    fake = _DeadOnSend(msgs=[])
    state = RuntimeState()
    state.backend_handles[42] = fake
    fake_application.bot_data["runtime"] = state

    update = make_update_fixture(text="hello", message_thread_id=42)
    context = type("Ctx", (), {"application": fake_application})()
    await runtime.on_inbound_text(update, context)

    update.message.reply_text.assert_called_once()
    args, _kwargs = update.message.reply_text.call_args
    assert "dead" in args[0].lower() or "rebind" in args[0].lower()
