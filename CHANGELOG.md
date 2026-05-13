# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-05-13

### Fixed

- `on_inbound_text` now catches `DeadError` from `b.send_prompt` and replies
  with `Session is dead. /start to rebind to a different session.` instead of
  letting the exception escape to PTB's top-level. Closes the narrow race
  window between Backend Dead transition and `_run_binding`'s finally block.
  ([#1](https://github.com/wuwenrui555/ccmux-core-telegram/issues/1))

## [0.1.1] - 2026-05-13

### Fixed

- `/start` in a topic that already owns a session now allows re-binding to that
  same session (previously rejected with "bound elsewhere"). Restores the
  daily recovery flow when a bound claude session dies and is restarted.
  ([#2](https://github.com/wuwenrui555/ccmux-core-telegram/issues/2))

### Changed

- `/start` now shows a header line `Currently bound to: <session>` above the
  picker when the current topic is already bound, so users see context before
  clicking. Suffix `(no longer live)` is added when the bound session has
  ended in ccmux-core.
  ([#6](https://github.com/wuwenrui555/ccmux-core-telegram/issues/6))

## [0.1.0] - 2026-05-12

Initial release. Telegram bridge over ccmux-core L2 API.
