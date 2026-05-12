"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from ccmux_core.message import Message
from ccmux_core.state import State


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated CCMUX_CORE_TELEGRAM_DIR per test."""
    d = tmp_path / "ccmux-core-telegram"
    d.mkdir()
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(d))
    return d


@pytest.fixture
def mock_bot() -> AsyncMock:
    """Mock PTB Bot — send_message, edit_message_text, etc."""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.edit_message_text = AsyncMock()
    return bot


@pytest.fixture
def fake_application(mock_bot: AsyncMock) -> MagicMock:
    """Minimal PTB Application surface."""
    app = MagicMock()
    app.bot_data = {}
    app.bot = mock_bot
    return app


class FakeBackend:
    """Duck-typed stand-in for ``ccmux_core.Backend``.

    Implements only what cct's runtime / tests need:
    ``__aenter__`` / ``__aexit__`` / ``messages()`` / ``send_prompt()``
    / ``state`` property.
    """

    def __init__(
        self,
        msgs: list[Message] | None = None,
        state: State | None = None,
    ) -> None:
        self._msgs = msgs or []
        self._state = state
        self.sent_prompts: list[str] = []
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> FakeBackend:
        self.entered = True
        return self

    async def __aexit__(self, *exc) -> None:
        self.exited = True

    async def messages(self) -> AsyncIterator[Message]:
        for m in self._msgs:
            yield m

    async def send_prompt(self, text: str) -> None:
        self.sent_prompts.append(text)

    @property
    def state(self) -> State | None:
        return self._state


@pytest.fixture
def fake_backend() -> type[FakeBackend]:
    """Factory: tests do `b = fake_backend(msgs=[...], state=...)`."""
    return FakeBackend


def make_update(
    *,
    text: str | None = None,
    message_thread_id: int | None = None,
    chat_id: int = -100,
    user_id: int = 1,
    callback_data: str | None = None,
) -> MagicMock:
    """Build a minimal fake PTB Update for handler tests.

    For text messages: pass ``text`` + ``message_thread_id``.
    For callback queries: pass ``callback_data``.
    """
    update = MagicMock()
    if callback_data is not None:
        update.message = None
        update.callback_query = MagicMock()
        update.callback_query.data = callback_data
        update.callback_query.from_user = MagicMock()
        update.callback_query.from_user.id = user_id
        update.callback_query.message = MagicMock()
        update.callback_query.message.message_thread_id = message_thread_id
        update.callback_query.message.chat = MagicMock()
        update.callback_query.message.chat.id = chat_id
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
    else:
        update.callback_query = None
        update.message = MagicMock()
        update.message.text = text
        update.message.message_thread_id = message_thread_id
        update.message.chat = MagicMock()
        update.message.chat.id = chat_id
        update.message.from_user = MagicMock()
        update.message.from_user.id = user_id
        update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update


@pytest.fixture
def make_update_fixture():
    return make_update
