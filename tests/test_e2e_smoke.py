"""End-to-end smoke test: full app boot with fakes.

Validates the full handler chain wires through without crashing,
using a Backend that suspends in messages() (so backend_handles
stays populated long enough for the inbound dispatch test).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ccmux_core.state import Idle

from ccmux_core_telegram import binding, handler, runtime


def _write_core(state_dir: Path, data: dict) -> None:
    p = state_dir / "ccmux-core" / "bindings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


async def test_full_boot_and_inbound_dispatch(
    monkeypatch, state_dir, fake_backend, make_update_fixture
) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")

    # SlowBackend's messages() suspends forever — keeps the task alive
    # so backend_handles[42] stays populated. Cancelled by post_shutdown.
    FakeBackendClass = fake_backend

    class SlowBackend(FakeBackendClass):
        async def messages(self):
            await asyncio.sleep(100)
            yield  # unreachable

    fake = SlowBackend(msgs=[], state=Idle(reason="stop"))
    monkeypatch.setattr("ccmux_core_telegram.runtime.Backend", lambda *a, **kw: fake)

    class _StubTracker:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            pass

    monkeypatch.setattr("ccmux_core_telegram.runtime.BindingsTracker", _StubTracker)

    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
    _write_core(state_dir, {
        "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
    })

    app = handler.build_application(token="123:fake", allowed_users=frozenset({1}))
    await runtime.on_post_init(app)
    state = app.bot_data["runtime"]
    assert 42 in state.live_tasks

    # Let the task body run up to the messages() suspend point so
    # backend_handles[42] gets populated.
    await asyncio.sleep(0)
    assert state.backend_handles[42] is fake

    # Now dispatch an inbound text
    update = make_update_fixture(text="hello backend", message_thread_id=42, user_id=1)
    context = type("Ctx", (), {"application": app})()
    await runtime.on_inbound_text(update, context)
    assert fake.sent_prompts == ["hello backend"]

    # Shutdown cleanly (cancels the slow task)
    await runtime.on_post_shutdown(app)
    assert len(state.live_tasks) == 0
