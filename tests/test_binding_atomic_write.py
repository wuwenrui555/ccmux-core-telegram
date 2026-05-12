"""Tests for binding._atomic_write (duplicated from ccmux-core)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from ccmux_core_telegram.binding import _atomic_write


def test_atomic_write_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "test.json"
    lock = tmp_path / "test.json.lock"
    _atomic_write(target, lock, {"key": "value"})
    assert json.loads(target.read_text()) == {"key": "value"}


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "test.json"
    lock = tmp_path / "test.json.lock"
    target.write_text('{"old": true}')
    _atomic_write(target, lock, {"new": True})
    assert json.loads(target.read_text()) == {"new": True}


def test_atomic_write_survives_mid_write_failure(tmp_path: Path) -> None:
    target = tmp_path / "test.json"
    lock = tmp_path / "test.json.lock"
    target.write_text('{"old": "data"}')
    with mock.patch("os.replace", side_effect=RuntimeError("crash")):
        with pytest.raises(RuntimeError):
            _atomic_write(target, lock, {"new": "data"})
    # Old file intact
    assert json.loads(target.read_text()) == {"old": "data"}


def test_atomic_write_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "subdir" / "test.json"
    lock = tmp_path / "subdir" / "test.json.lock"
    _atomic_write(target, lock, {"k": "v"})
    assert target.exists()
