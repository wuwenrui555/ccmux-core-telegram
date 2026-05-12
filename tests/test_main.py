"""Tests for main.py — setup_logging + scrub_sensitive_env."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from ccmux_core_telegram import main


def test_setup_logging_configures_levels(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_LOG_FILE", str(tmp_path / "test.log"))
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_LOG_LEVEL", "INFO")
    main.setup_logging()
    assert logging.getLogger("ccmux_core_telegram").level == logging.INFO
    assert logging.getLogger("ccmux_core").level == logging.INFO


def test_setup_logging_creates_file_handler(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "test.log"
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_LOG_FILE", str(log_path))
    main.setup_logging()
    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert any(Path(h.baseFilename) == log_path for h in file_handlers)


def test_scrub_sensitive_env(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret")
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1,2,3")
    main.scrub_sensitive_env()
    assert "TELEGRAM_BOT_TOKEN" not in os.environ
    assert "CCMUX_CORE_TELEGRAM_ALLOWED_USERS" not in os.environ
