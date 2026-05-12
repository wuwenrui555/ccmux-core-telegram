"""Per-binding asyncio runtime: state, task lifecycle, dispatchers.

Owns ``live_tasks`` / ``backend_handles`` / ``tracker`` inside a
``RuntimeState`` dataclass stored at ``application.bot_data["runtime"]``.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field

from ccmux_core import Backend
from ccmux_core.bindings import BindingsTracker
from ccmux_core.state import Dead

logger = logging.getLogger(__name__)


@dataclass
class RuntimeState:
    """In-memory runtime state, lifecycle-bound to PTB Application."""

    live_tasks: dict[int, asyncio.Task] = field(default_factory=dict)
    backend_handles: dict[int, Backend] = field(default_factory=dict)
    tracker: BindingsTracker | None = None


def get_state(application) -> RuntimeState:
    """Fetch the RuntimeState from an Application's bot_data."""
    return application.bot_data["runtime"]


async def start_binding(
    application,
    topic_id: int,
    tmux_session: str,
    pane_id: str,
    group_chat_id: int,
) -> None:
    """Create + register a per-binding task. Caller ensures no live task already owns topic_id."""
    state = get_state(application)
    task = asyncio.create_task(
        _run_binding(application, topic_id, tmux_session, pane_id, group_chat_id)
    )
    state.live_tasks[topic_id] = task


async def _run_binding(
    application,
    topic_id: int,
    tmux_session: str,
    pane_id: str,
    group_chat_id: int,
) -> None:
    """Per-binding task body. Pumps Backend.messages() → Telegram.

    Outbound logic (forward filter, rate-limit handling) and Dead notice
    are added in subsequent tasks; this stub keeps the test infrastructure
    working before then.
    """
    state = get_state(application)
    b: Backend | None = None
    try:
        async with Backend(tmux_session, pane_id) as b:
            state.backend_handles[topic_id] = b
            async for _msg in b.messages():
                pass  # Outbound forwarding added in Task 10
    finally:
        state.backend_handles.pop(topic_id, None)
        state.live_tasks.pop(topic_id, None)
        if b is not None and isinstance(b.state, Dead):
            with contextlib.suppress(Exception):
                pass  # Dead notice added in Task 10
