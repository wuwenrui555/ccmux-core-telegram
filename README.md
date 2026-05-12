# ccmux-core-telegram

Telegram bridge over the `ccmux-core` L2 API. Each Telegram forum
topic binds 1:1 to a tmux session running Claude Code; outbound L1
messages forward to the topic, and inbound text dispatches to
`Backend.send_prompt()`.

## Installation

```bash
pip install ccmux-core-telegram
```

## Setup

Create `~/.ccmux-core-telegram/.env` with:

```text
TELEGRAM_BOT_TOKEN=...
CCMUX_CORE_TELEGRAM_ALLOWED_USERS=123456789
```

Then run:

```bash
ccmux-core-telegram
```

In any Telegram forum topic the bot has access to, send `/start`
to bind it to a tmux session.

## Design

See [`docs/superpowers/specs/`](docs/superpowers/specs/) for the full design spec.
