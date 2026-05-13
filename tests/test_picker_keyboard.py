"""Tests for picker._build_picker keyboard rendering."""

from __future__ import annotations

from telegram import InlineKeyboardMarkup

from ccmux_core_telegram import picker


def test_build_picker_no_sessions() -> None:
    text, kb = picker._build_picker(
        core_bindings={},
        topic_bindings={},
        filter_mode="all",
        current_topic_id=42,
    )
    assert "No" in text or "no" in text


def test_build_picker_all_unbound() -> None:
    core = {
        "session_a": {"current_session_id": "sid", "pane_id": "%0"},
        "session_b": {"current_session_id": "sid", "pane_id": "%1"},
    }
    text, kb = picker._build_picker(
        core_bindings=core,
        topic_bindings={},
        filter_mode="all",
        current_topic_id=42,
    )
    assert isinstance(kb, InlineKeyboardMarkup)
    # tabs row + 2 session rows
    rows = kb.inline_keyboard
    assert len(rows) >= 3  # tabs + 2 sessions
    # Find pick: buttons
    callbacks = [btn.callback_data for row in rows for btn in row]
    assert "pick:session_a" in callbacks
    assert "pick:session_b" in callbacks


def test_build_picker_one_bound_by_other_topic() -> None:
    core = {
        "session_a": {"current_session_id": "sid", "pane_id": "%0"},
    }
    from ccmux_core_telegram.binding import TopicBinding

    topic_bindings = {
        99: TopicBinding(
            topic_id=99,
            tmux_session="session_a",
            group_chat_id=-100,
            bound_at="2026-05-12T00:00:00Z",
        ),
    }
    text, kb = picker._build_picker(
        core_bindings=core,
        topic_bindings=topic_bindings,
        filter_mode="all",
        current_topic_id=42,
    )
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "steal:session_a" in callbacks


def test_filter_unbound_hides_bound() -> None:
    core = {
        "session_a": {"current_session_id": "sid", "pane_id": "%0"},
        "session_b": {"current_session_id": "sid", "pane_id": "%1"},
    }
    from ccmux_core_telegram.binding import TopicBinding

    topic_bindings = {
        99: TopicBinding(99, "session_b", -100, "2026-05-12T00:00:00Z"),
    }
    text, kb = picker._build_picker(
        core_bindings=core,
        topic_bindings=topic_bindings,
        filter_mode="unbound",
        current_topic_id=42,
    )
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "pick:session_a" in callbacks
    assert "steal:session_b" not in callbacks
    assert "pick:session_b" not in callbacks


def test_active_tab_bracketed() -> None:
    core = {}
    text, kb = picker._build_picker(
        core_bindings=core,
        topic_bindings={},
        filter_mode="unbound",
        current_topic_id=42,
    )
    labels = [btn.text for btn in kb.inline_keyboard[0]]
    assert any("【" in lbl and "未绑定" in lbl for lbl in labels)


def test_skips_ended_sessions() -> None:
    core = {
        "live": {"current_session_id": "sid", "pane_id": "%0"},
        "ended": {"current_session_id": None, "pane_id": "%1"},
    }
    text, kb = picker._build_picker(
        core_bindings=core,
        topic_bindings={},
        filter_mode="all",
        current_topic_id=42,
    )
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "pick:live" in callbacks
    assert "pick:ended" not in callbacks


def test_build_picker_header_live_binding() -> None:
    """When current topic is bound to a live session, header is prepended."""
    from ccmux_core_telegram.binding import TopicBinding

    core = {
        "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
    }
    topic_bindings = {
        42: TopicBinding(
            topic_id=42,
            tmux_session="ccmux",
            group_chat_id=-100,
            bound_at="2026-05-13T00:00:00Z",
        ),
    }
    text, _kb = picker._build_picker(
        core_bindings=core,
        topic_bindings=topic_bindings,
        filter_mode="all",
        current_topic_id=42,
    )
    assert text.startswith("Currently bound to: ccmux\n\n")
    assert "Pick a tmux session:" in text


def test_build_picker_header_dead_binding() -> None:
    """When current topic is bound but session ended in core, header has '(no longer live)' suffix."""
    from ccmux_core_telegram.binding import TopicBinding

    core = {
        # Present in core but ended (current_session_id=None).
        "ccmux": {"current_session_id": None, "pane_id": "%0"},
    }
    topic_bindings = {
        42: TopicBinding(
            topic_id=42,
            tmux_session="ccmux",
            group_chat_id=-100,
            bound_at="2026-05-13T00:00:00Z",
        ),
    }
    text, _kb = picker._build_picker(
        core_bindings=core,
        topic_bindings=topic_bindings,
        filter_mode="all",
        current_topic_id=42,
    )
    assert text.startswith("Currently bound to: ccmux (no longer live)\n\n")


def test_build_picker_no_header_when_unbound() -> None:
    """When current topic has no binding, no header is prepended (regression guard)."""
    core = {
        "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
    }
    text, _kb = picker._build_picker(
        core_bindings=core,
        topic_bindings={},  # current topic 42 not in bindings
        filter_mode="all",
        current_topic_id=42,
    )
    assert "Currently bound to:" not in text
    assert text == "Pick a tmux session:"
