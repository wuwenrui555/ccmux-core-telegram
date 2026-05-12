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

    On Backend Dead → send a death notice. On voluntary cancel
    (task.cancel()) → suppress notice. On rate-limit exhaust → log
    and send a placeholder.
    """
    from telegram.error import RetryAfter

    from . import render
    from .config import forward_tools, tool_allowlist

    bot = application.bot
    state = get_state(application)
    b: Backend | None = None
    try:
        async with Backend(tmux_session, pane_id) as b:
            state.backend_handles[topic_id] = b
            async for msg in b.messages():
                if not _should_forward(msg, forward_tools(), tool_allowlist()):
                    continue
                text, parse_mode = render.format(msg)
                try:
                    await bot.send_message(
                        chat_id=group_chat_id,
                        message_thread_id=topic_id,
                        text=text,
                        parse_mode=parse_mode,
                    )
                    logger.debug(
                        "outbound: topic=%d kind=%s",
                        topic_id,
                        type(msg).__name__,
                    )
                except RetryAfter:
                    logger.warning(
                        "rate-limit dropped: topic=%d kind=%s",
                        topic_id,
                        type(msg).__name__,
                    )
                    with contextlib.suppress(Exception):
                        await bot.send_message(
                            chat_id=group_chat_id,
                            message_thread_id=topic_id,
                            text="⚠️ dropped one message (rate limit)",
                        )
    finally:
        state.backend_handles.pop(topic_id, None)
        state.live_tasks.pop(topic_id, None)
        if b is not None and isinstance(b.state, Dead):
            with contextlib.suppress(Exception):
                detail = f": {b.state.detail}" if b.state.detail else ""
                await bot.send_message(
                    chat_id=group_chat_id,
                    message_thread_id=topic_id,
                    text=f"🪦 session ended ({b.state.reason}{detail})",
                )
            logger.info(
                "binding ended: topic=%d reason=%s",
                topic_id,
                b.state.reason,
            )


def _should_forward(
    msg, forward_tools_enabled: bool, allowlist: frozenset[str]
) -> bool:
    """Apply FORWARD_TOOLS + TOOL_ALLOWLIST filter to outbound messages."""
    from ccmux_core.message import ToolCall, ToolResult

    if not isinstance(msg, (ToolCall, ToolResult)):
        return True
    if forward_tools_enabled:
        return True
    return msg.tool_name in allowlist


async def on_inbound_text(update, context) -> None:
    """Route inbound text to the bound Backend.

    - In a topic with a live backend → ``b.send_prompt(text)``
    - In a topic that is bound but has no live backend (Dead) → reply hint
    - In an unbound topic (or non-topic) → silent
    """
    from . import binding

    msg = update.message
    if msg is None or msg.message_thread_id is None:
        return
    topic_id = msg.message_thread_id
    state = get_state(context.application)

    if topic_id in state.backend_handles:
        b = state.backend_handles[topic_id]
        await b.send_prompt(msg.text)
        logger.debug("inbound: topic=%d text=%r", topic_id, msg.text)
        return

    if binding.get(topic_id) is None:
        return  # unbound, silent

    await msg.reply_text("Session is dead. /start to rebind to a different session.")


async def on_post_init(application) -> None:
    """PTB post_init hook: start BindingsTracker + recover bindings.

    For each persisted topic binding:
      - tmux_session live in ccmux-core/bindings.json → start task
      - tmux_session missing or ``current_session_id is None`` →
        notify topic; do NOT start a task; retain the file entry
    """
    from . import binding

    state = RuntimeState()
    application.bot_data["runtime"] = state

    state.tracker = BindingsTracker()
    await state.tracker.__aenter__()

    core = _load_core_bindings()
    for topic_id, b in binding.load_all().items():
        c = core.get(b.tmux_session)
        if c is None or c.get("current_session_id") is None:
            with contextlib.suppress(Exception):
                await application.bot.send_message(
                    chat_id=b.group_chat_id,
                    message_thread_id=topic_id,
                    text=(
                        f"⚠️ binding stale: '{b.tmux_session}' not found/ended. "
                        f"Delete from topic_bindings.json and /start to rebind."
                    ),
                )
            logger.warning(
                "stale binding skipped: topic=%d tmux=%s",
                topic_id, b.tmux_session,
            )
            continue
        await start_binding(
            application,
            topic_id=topic_id,
            tmux_session=b.tmux_session,
            pane_id=c["pane_id"],
            group_chat_id=b.group_chat_id,
        )
        logger.info(
            "started binding: topic=%d tmux=%s pane=%s",
            topic_id, b.tmux_session, c["pane_id"],
        )


def _load_core_bindings() -> dict:
    """Read ccmux-core's bindings.json. Returns {} if missing."""
    import json

    from . import config

    path = config.ccmux_core_bindings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("ccmux-core/bindings.json malformed; treating as empty")
        return {}
