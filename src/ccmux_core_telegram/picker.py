"""/start command handler + picker UI + pick/steal/filter callbacks."""

from __future__ import annotations

import logging
from typing import Literal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from . import binding
from .binding import TopicBinding

logger = logging.getLogger(__name__)

FilterMode = Literal["all", "unbound", "bound"]

PICK_PREFIX = "pick:"
STEAL_PREFIX = "steal:"
FILTER_PREFIX = "filter:"


def _build_picker(
    core_bindings: dict,
    topic_bindings: dict[int, TopicBinding],
    filter_mode: FilterMode,
    current_topic_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """Build picker text + InlineKeyboardMarkup.

    Live sessions only (``current_session_id is not None``). Bound
    sessions are labeled with their owning topic_id; the picker
    callback distinguishes pick vs steal by callback_data prefix.
    """
    # Compute live sessions
    live_sessions = [
        (name, entry)
        for name, entry in core_bindings.items()
        if entry.get("current_session_id") is not None
    ]

    # Index bindings by tmux_session for O(1) lookup
    by_session: dict[str, TopicBinding] = {
        b.tmux_session: b for b in topic_bindings.values()
    }

    # Filter by mode
    filtered = []
    for name, entry in live_sessions:
        is_bound = name in by_session
        if filter_mode == "unbound" and is_bound:
            continue
        if filter_mode == "bound" and not is_bound:
            continue
        filtered.append((name, entry, is_bound))

    # Build keyboard rows
    rows: list[list[InlineKeyboardButton]] = []
    rows.append(_tab_row(filter_mode))

    if not filtered:
        text = (
            "No sessions in this view."
            if filter_mode != "all"
            else "No live claude sessions."
        )
        return text, InlineKeyboardMarkup(rows)

    for name, _entry, is_bound in filtered:
        if is_bound:
            owner = by_session[name].topic_id
            if owner == current_topic_id:
                label = f"✅ {name} (current)"
                cb = f"{PICK_PREFIX}{name}"
            else:
                label = f"🔒 {name} → topic {owner}"
                cb = f"{STEAL_PREFIX}{name}"
        else:
            label = f"🖥 {name}"
            cb = f"{PICK_PREFIX}{name}"
        rows.append([InlineKeyboardButton(label, callback_data=cb)])

    return "Pick a tmux session:", InlineKeyboardMarkup(rows)


def _tab_row(active: FilterMode) -> list[InlineKeyboardButton]:
    def label(text: str, mode: FilterMode) -> str:
        return f"【{text}】" if active == mode else text

    return [
        InlineKeyboardButton(
            label("📂 全部", "all"), callback_data=f"{FILTER_PREFIX}all"
        ),
        InlineKeyboardButton(
            label("🖥 未绑定", "unbound"), callback_data=f"{FILTER_PREFIX}unbound"
        ),
        InlineKeyboardButton(
            label("🔒 已绑定", "bound"), callback_data=f"{FILTER_PREFIX}bound"
        ),
    ]


async def on_start(update, context) -> None:
    """Handle ``/start`` — always launch picker, regardless of current binding state."""
    msg = update.message
    if msg.message_thread_id is None:
        await msg.reply_text("Use /start inside a forum topic.")
        return
    topic_id = msg.message_thread_id

    core = _load_core_bindings()
    topic_bindings = binding.load_all()
    text, kb = _build_picker(
        core_bindings=core,
        topic_bindings=topic_bindings,
        filter_mode="all",
        current_topic_id=topic_id,
    )
    await msg.reply_text(text, reply_markup=kb)


def _load_core_bindings() -> dict:
    """Read ccmux-core's bindings.json. Returns {} on missing/malformed."""
    import json

    from . import config

    path = config.ccmux_core_bindings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
