"""Tests for binding.py public API."""

from __future__ import annotations

import json

import pytest

from ccmux_core_telegram import binding


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """Isolated CCMUX_CORE_TELEGRAM_DIR per test."""
    d = tmp_path / "ccmux-core-telegram"
    d.mkdir()
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(d))
    return d


def test_load_all_empty_returns_empty_dict(state_dir) -> None:
    assert binding.load_all() == {}


def test_put_then_load(state_dir) -> None:
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
    loaded = binding.load_all()
    assert 42 in loaded
    assert loaded[42].tmux_session == "ccmux"
    assert loaded[42].group_chat_id == -100
    assert loaded[42].bound_at  # ISO timestamp set


def test_get_returns_binding(state_dir) -> None:
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
    b = binding.get(42)
    assert b is not None
    assert b.tmux_session == "ccmux"


def test_get_missing_returns_none(state_dir) -> None:
    assert binding.get(999) is None


def test_remove_existing(state_dir) -> None:
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
    binding.remove(42)
    assert binding.get(42) is None
    assert binding.load_all() == {}


def test_remove_missing_is_noop(state_dir) -> None:
    binding.remove(999)  # should not raise
    assert binding.load_all() == {}


def test_find_by_tmux_session_returns_match(state_dir) -> None:
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
    binding.put(topic_id=99, tmux_session="other", group_chat_id=-100)
    found = binding.find_by_tmux_session("ccmux")
    assert found == (42, -100)


def test_find_by_tmux_session_returns_none(state_dir) -> None:
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
    assert binding.find_by_tmux_session("nope") is None


def test_put_overwrites_existing_topic(state_dir) -> None:
    binding.put(topic_id=42, tmux_session="old", group_chat_id=-100)
    binding.put(topic_id=42, tmux_session="new", group_chat_id=-200)
    b = binding.get(42)
    assert b.tmux_session == "new"
    assert b.group_chat_id == -200


def test_malformed_json_raises(state_dir) -> None:
    from ccmux_core_telegram.config import topic_bindings_path

    topic_bindings_path().write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        binding.load_all()
