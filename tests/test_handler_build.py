"""Tests for handler.build_application — handler registration."""

from __future__ import annotations

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
)

from ccmux_core_telegram import handler


def test_build_application_returns_application() -> None:
    app = handler.build_application(token="123:fake", allowed_users=frozenset({1}))
    assert isinstance(app, Application)


def test_build_application_registers_start_command() -> None:
    app = handler.build_application(token="123:fake", allowed_users=frozenset({1}))
    handlers_flat = [h for group in app.handlers.values() for h in group]
    command_handlers = [h for h in handlers_flat if isinstance(h, CommandHandler)]
    assert any("start" in getattr(h, "commands", set()) for h in command_handlers)


def test_build_application_registers_text_handler() -> None:
    app = handler.build_application(token="123:fake", allowed_users=frozenset({1}))
    handlers_flat = [h for group in app.handlers.values() for h in group]
    text_handlers = [h for h in handlers_flat if isinstance(h, MessageHandler)]
    assert len(text_handlers) >= 1


def test_build_application_registers_callback_handlers() -> None:
    app = handler.build_application(token="123:fake", allowed_users=frozenset({1}))
    handlers_flat = [h for group in app.handlers.values() for h in group]
    cbq = [h for h in handlers_flat if isinstance(h, CallbackQueryHandler)]
    assert len(cbq) >= 3  # pick / steal / filter
