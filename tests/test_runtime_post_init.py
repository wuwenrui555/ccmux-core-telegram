"""Tests for runtime.on_post_init startup binding recovery."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ccmux_core.state import Idle

from ccmux_core_telegram import binding, runtime
from ccmux_core_telegram.runtime import RuntimeState


def _write_core_bindings(state_dir: Path, data: dict) -> None:
    """Write the ccmux-core/bindings.json fixture file."""
    p = state_dir / "ccmux-core" / "bindings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


async def test_post_init_starts_tasks_for_live_bindings(
    monkeypatch, state_dir, fake_application, fake_backend
) -> None:
    # cct has 1 binding; ccmux-core says the session is live
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
    _write_core_bindings(state_dir, {
        "ccmux": {
            "pane_id": "%0",
            "window_id": "@0",
            "current_session_id": "sid-1",
            "session_id_history": ["sid-1"],
            "first_seen_at": "2026-05-12T00:00:00Z",
            "last_event_at": "2026-05-12T00:00:00Z",
            "ended_at": None,
        }
    })

    fake = fake_backend(msgs=[], state=Idle(reason="stop"))
    monkeypatch.setattr(
        "ccmux_core_telegram.runtime.Backend",
        lambda *a, **kw: fake,
    )
    # Replace BindingsTracker with a no-op
    monkeypatch.setattr(
        "ccmux_core_telegram.runtime.BindingsTracker",
        _FakeTracker,
    )

    await runtime.on_post_init(fake_application)

    state = fake_application.bot_data["runtime"]
    assert 42 in state.live_tasks
    assert state.tracker is not None


async def test_post_init_notifies_stale_and_skips(
    monkeypatch, state_dir, fake_application, fake_backend, mock_bot
) -> None:
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
    # ccmux-core/bindings.json missing or has no entry
    _write_core_bindings(state_dir, {})

    monkeypatch.setattr(
        "ccmux_core_telegram.runtime.BindingsTracker",
        _FakeTracker,
    )

    await runtime.on_post_init(fake_application)

    state = fake_application.bot_data["runtime"]
    assert 42 not in state.live_tasks
    # Stale notification sent
    mock_bot.send_message.assert_called_once()
    notice = mock_bot.send_message.call_args.kwargs
    assert notice["chat_id"] == -100
    assert notice["message_thread_id"] == 42
    assert "stale" in notice["text"].lower()


async def test_post_init_skips_ended_sessions(
    monkeypatch, state_dir, fake_application, mock_bot
) -> None:
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
    _write_core_bindings(state_dir, {
        "ccmux": {
            "pane_id": "%0",
            "window_id": "@0",
            "current_session_id": None,  # ended
            "session_id_history": ["sid-1"],
            "first_seen_at": "2026-05-12T00:00:00Z",
            "last_event_at": "2026-05-12T00:00:00Z",
            "ended_at": "2026-05-12T01:00:00Z",
        }
    })

    monkeypatch.setattr(
        "ccmux_core_telegram.runtime.BindingsTracker",
        _FakeTracker,
    )

    await runtime.on_post_init(fake_application)

    state = fake_application.bot_data["runtime"]
    assert 42 not in state.live_tasks
    mock_bot.send_message.assert_called_once()


class _FakeTracker:
    """Stand-in for ccmux_core.bindings.BindingsTracker."""
    def __init__(self, *a, **kw) -> None:
        self.entered = False
        self.exited = False
    async def __aenter__(self) -> "_FakeTracker":
        self.entered = True
        return self
    async def __aexit__(self, *exc) -> None:
        self.exited = True
