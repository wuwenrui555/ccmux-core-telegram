"""PTB handler registration. Builds the singleton Application."""

from __future__ import annotations

import logging

from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from . import picker, runtime

logger = logging.getLogger(__name__)


def build_application(token: str, allowed_users: frozenset[int]) -> Application:
    """Build and configure the PTB Application with all handlers attached."""
    app = (
        ApplicationBuilder()
        .token(token)
        .rate_limiter(AIORateLimiter(max_retries=5))
        .build()
    )

    user_filter = filters.User(user_id=list(allowed_users))

    # /start command (in allowed users only)
    app.add_handler(CommandHandler("start", picker.on_start, filters=user_filter))

    # Inbound text (allowed users only, no commands)
    app.add_handler(
        MessageHandler(
            user_filter & filters.TEXT & ~filters.COMMAND,
            runtime.on_inbound_text,
        )
    )

    # Callback queries — user filtering done inside handler bodies
    app.add_handler(
        CallbackQueryHandler(picker.on_pick_callback, pattern=rf"^{picker.PICK_PREFIX}")
    )
    app.add_handler(
        CallbackQueryHandler(
            picker.on_steal_callback, pattern=rf"^{picker.STEAL_PREFIX}"
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            picker.on_filter_callback, pattern=rf"^{picker.FILTER_PREFIX}"
        )
    )

    return app
