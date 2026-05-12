"""Application entry point.

Sequence:

1. ``setup_logging()`` — stderr + file handler, levels per config.
2. ``config.validate_required_env()`` — fail fast on missing secrets.
3. ``handler.build_application(...)`` — register all handlers.
4. ``scrub_sensitive_env()`` — drop token/allowed_users from os.environ.
5. Wire ``post_init`` / ``post_shutdown`` to runtime hooks.
6. ``app.run_polling(...)``.
"""

from __future__ import annotations

import logging
import os
import sys

from . import config, handler, runtime

logger = logging.getLogger(__name__)

SENSITIVE_VARS: frozenset[str] = frozenset(
    {
        "TELEGRAM_BOT_TOKEN",
        "CCMUX_CORE_TELEGRAM_ALLOWED_USERS",
    }
)


def setup_logging() -> None:
    """stderr + file handler, levels per CCMUX_CORE_TELEGRAM_LOG_LEVEL."""
    log_file = config.log_file()
    log_level_str = config.log_level().upper()
    log_level = getattr(logging, log_level_str, logging.DEBUG)

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.WARNING,
    )

    logging.getLogger("ccmux_core_telegram").setLevel(log_level)
    logging.getLogger("ccmux_core").setLevel(log_level)
    logging.getLogger("telegram.ext.AIORateLimiter").setLevel(logging.INFO)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(log_level)
    fh.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logging.getLogger().addHandler(fh)
    logger.info("Logging to %s (level=%s)", log_file, log_level_str)


def scrub_sensitive_env() -> None:
    """Pop secrets from os.environ after they've been read into config."""
    for var in SENSITIVE_VARS:
        os.environ.pop(var, None)


def main() -> None:
    setup_logging()
    try:
        config.validate_required_env()
    except config.ConfigError as e:
        sys.stderr.write(f"Error: {e}\n\n")
        sys.stderr.write(
            f"Create {config.dotenv_path()} with:\n"
            "  TELEGRAM_BOT_TOKEN=your_token_here\n"
            "  CCMUX_CORE_TELEGRAM_ALLOWED_USERS=your_user_id\n\n"
            "Get a bot token from @BotFather on Telegram.\n"
            "Get your user ID from @userinfobot.\n"
        )
        sys.exit(1)

    token = config.bot_token()
    allowed = config.allowed_users()
    logger.info("Allowed users: %s", sorted(allowed))

    app = handler.build_application(token=token, allowed_users=allowed)
    scrub_sensitive_env()

    app.post_init = runtime.on_post_init
    app.post_shutdown = runtime.on_post_shutdown

    logger.info("Starting bot polling...")
    app.run_polling(
        allowed_updates=["message", "callback_query"],
        bootstrap_retries=config.bootstrap_retries(),
    )


if __name__ == "__main__":
    main()
