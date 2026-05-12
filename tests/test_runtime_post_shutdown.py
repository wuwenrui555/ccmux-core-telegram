"""Tests for runtime.on_post_shutdown teardown."""
from __future__ import annotations

import asyncio

import pytest

from ccmux_core_telegram import runtime
from ccmux_core_telegram.runtime import RuntimeState


async def test_post_shutdown_cancels_all_tasks(
    monkeypatch, fake_application
) -> None:
    class _SlowBackend:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None
        async def messages(self):
            await asyncio.sleep(1000)  # never yields
            yield  # unreachable
        async def send_prompt(self, text):
            pass
        @property
        def state(self):
            return None

    monkeypatch.setattr(
        "ccmux_core_telegram.runtime.Backend",
        lambda *a, **kw: _SlowBackend(),
    )

    state = RuntimeState()
    fake_application.bot_data["runtime"] = state
    state.tracker = _FakeTracker()

    await runtime.start_binding(fake_application, 42, "s1", "%0", -100)
    await runtime.start_binding(fake_application, 43, "s2", "%1", -100)
    await asyncio.sleep(0)
    assert 42 in state.live_tasks
    assert 43 in state.live_tasks

    await runtime.on_post_shutdown(fake_application)

    # All tasks cancelled and cleaned up
    assert len(state.live_tasks) == 0
    assert state.tracker.exited is True


async def test_post_shutdown_no_tasks_is_ok(fake_application) -> None:
    state = RuntimeState()
    fake_application.bot_data["runtime"] = state
    state.tracker = _FakeTracker()
    await runtime.on_post_shutdown(fake_application)
    assert state.tracker.exited is True


class _FakeTracker:
    def __init__(self):
        self.entered = False
        self.exited = False
    async def __aenter__(self):
        self.entered = True
        return self
    async def __aexit__(self, *exc):
        self.exited = True
