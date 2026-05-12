"""/start command handler + picker UI + pick/steal/filter callbacks."""

from __future__ import annotations

import contextlib
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


async def on_filter_callback(update, context) -> None:
    """Tab switch — re-render picker with new filter mode."""
    from . import config

    query = update.callback_query
    await query.answer()
    if query.from_user.id not in config.allowed_users():
        return

    mode_str = query.data[len(FILTER_PREFIX) :]
    if mode_str not in ("all", "unbound", "bound"):
        return
    mode: FilterMode = mode_str  # type: ignore[assignment]

    topic_id = query.message.message_thread_id
    core = _load_core_bindings()
    topic_bindings = binding.load_all()
    text, kb = _build_picker(
        core_bindings=core,
        topic_bindings=topic_bindings,
        filter_mode=mode,
        current_topic_id=topic_id,
    )
    await query.edit_message_text(text, reply_markup=kb)


async def on_pick_callback(update, context) -> None:
    """Bind the chosen unbound session to the current topic."""
    from . import config, runtime

    query = update.callback_query
    await query.answer()
    if query.from_user.id not in config.allowed_users():
        return

    tmux_session = query.data[len(PICK_PREFIX) :]
    topic_id = query.message.message_thread_id
    group_chat_id = query.message.chat.id

    # Re-validate (picker render → click race window)
    core = _load_core_bindings()
    c = core.get(tmux_session)
    if c is None or c.get("current_session_id") is None:
        await query.edit_message_text(f"'{tmux_session}' no longer live. /start again.")
        return
    if binding.find_by_tmux_session(tmux_session) is not None:
        await query.edit_message_text(
            f"'{tmux_session}' was just bound elsewhere. /start again."
        )
        return

    # If this topic was previously bound (e.g., Dead state), remove old entry
    if binding.get(topic_id) is not None:
        binding.remove(topic_id)

    binding.put(topic_id, tmux_session, group_chat_id)
    await runtime.start_binding(
        context.application,
        topic_id=topic_id,
        tmux_session=tmux_session,
        pane_id=c["pane_id"],
        group_chat_id=group_chat_id,
    )
    await query.edit_message_text(f"✅ Bound to `{tmux_session}`.")


async def on_steal_callback(update, context) -> None:
    """Transfer an already-bound session from its current topic to this one."""
    from . import config, runtime

    query = update.callback_query
    await query.answer()
    if query.from_user.id not in config.allowed_users():
        return

    tmux_session = query.data[len(STEAL_PREFIX) :]
    new_topic_id = query.message.message_thread_id
    new_group_chat_id = query.message.chat.id

    state = runtime.get_state(context.application)
    old = binding.find_by_tmux_session(tmux_session)
    if old is None:
        # No longer bound (race) — fall back to ordinary pick
        update.callback_query.data = f"{PICK_PREFIX}{tmux_session}"
        await on_pick_callback(update, context)
        return
    old_topic_id, old_group_chat_id = old

    if old_topic_id == new_topic_id:
        await query.edit_message_text(
            f"✅ Already bound to `{tmux_session}`. No change."
        )
        return

    # 1. Notify old topic before cancelling its task
    with contextlib.suppress(Exception):
        await context.application.bot.send_message(
            chat_id=old_group_chat_id,
            message_thread_id=old_topic_id,
            text=(
                f"🔄 Session `{tmux_session}` was claimed by another topic. "
                f"This topic is no longer connected. /start to rebind."
            ),
        )

    # 2. Cancel old task (finally clears state.live_tasks/handles)
    old_task = state.live_tasks.get(old_topic_id)
    if old_task is not None:
        old_task.cancel()

    # 3. Remove old entry from disk
    binding.remove(old_topic_id)

    # 4. If new topic had a prior entry, remove it
    if binding.get(new_topic_id) is not None:
        binding.remove(new_topic_id)

    # 5. Re-validate session is still live, write + start
    core = _load_core_bindings()
    c = core.get(tmux_session)
    if c is None or c.get("current_session_id") is None:
        await query.edit_message_text(f"'{tmux_session}' no longer live. /start again.")
        return
    binding.put(new_topic_id, tmux_session, new_group_chat_id)
    await runtime.start_binding(
        context.application,
        topic_id=new_topic_id,
        tmux_session=tmux_session,
        pane_id=c["pane_id"],
        group_chat_id=new_group_chat_id,
    )
    await query.edit_message_text(
        f"✅ Bound to `{tmux_session}` (stolen from topic {old_topic_id})."
    )
    logger.info(
        "steal: tmux=%s old_topic=%d new_topic=%d",
        tmux_session,
        old_topic_id,
        new_topic_id,
    )
