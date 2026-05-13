# cct#1 — DeadError catch in `on_inbound_text` (v0.1.2)

**Date:** 2026-05-13
**Issue:** [cct#1](https://github.com/wuwenrui555/ccmux-core-telegram/issues/1)
**Target release:** v0.1.2
**Scope:** Defense-in-depth bugfix. Single file change in production code, single new test.

## Problem

`runtime.on_inbound_text` calls `b.send_prompt(text)` without catching `ccmux_core.error.DeadError`. If the Backend has transitioned to `Dead` state but its `_run_binding` task has not yet finished its `finally` block (i.e. the `state.backend_handles[topic_id]` entry is still present), the inbound-text path raises `DeadError` to PTB's top-level Application. Result: no reply in the Telegram topic, plus a "No error handlers are registered" traceback in the daemon log.

The window narrowed after ccmux-core#13 (in cct via pin `ccmux-core>=0.3.2`), because a Dead Backend's task now exits and pops `backend_handles[topic_id]` promptly. But the race is not eliminated: if inbound text arrives between Backend transition and task `finally`, the exception still escapes. This spec adds belt-and-suspenders handling.

## Out of scope

- Other `send_prompt` exception types (`BlockedError`, `BackendError`, etc.). These are not on cct's hot path today; if they appear in the future, model them then.
- Extracting the dead-hint reply text to a module-level constant.
- Adding a PTB global error handler.
- Any change outside `runtime.on_inbound_text` and its tests.

## Architecture

No structural change. A `try` / `except DeadError` wraps the existing `b.send_prompt` call inside the "live backend" branch of `on_inbound_text`. The except branch routes to the same `reply_text` call that the existing "bound-but-no-live-backend" branch uses, so the user-visible experience is identical regardless of which race window the inbound text falls into.

## Production code change

**File:** `src/ccmux_core_telegram/runtime.py`

1. Add import near the existing `from ccmux_core.state import Dead`:

   ```python
   from ccmux_core.error import DeadError
   ```

2. Replace the live-backend branch body in `on_inbound_text` (current lines 148–152):

   ```python
   if topic_id in state.backend_handles:
       b = state.backend_handles[topic_id]
       try:
           await b.send_prompt(msg.text)
           logger.debug("inbound: topic=%d text=%r", topic_id, msg.text)
       except DeadError:
           await msg.reply_text(
               "Session is dead. /start to rebind to a different session."
           )
       return
   ```

The reply text matches the existing dead-binding branch (`runtime.py:157`) byte-for-byte, so the two race outcomes are indistinguishable to the user.

## Testing

**File:** `tests/test_runtime_inbound.py`

Add one test, `test_inbound_dead_error_replies_hint`, using a 3-line subclass of the existing `FakeBackend`:

```python
class _DeadOnSend(FakeBackend):
    async def send_prompt(self, text):
        raise DeadError("test")
```

Assertions:

- `update.message.reply_text` is called exactly once.
- The reply text contains "dead" or "rebind" (matching the pattern used by `test_inbound_dead_topic_replies_hint`).
- The call does not raise.

`tests/conftest.py` is **not** modified. The existing `FakeBackend` stays as-is — we do not add a `raise_on_send` kwarg because we have no second use case for it today (CLAUDE.md §2 Simplicity First).

The normal (non-exception) path is already covered by `test_inbound_routes_to_live_backend`; no cross-test is added.

## Verification gates

- `pytest` passes (existing 3 inbound tests + the new one).
- `pre-commit run --all-files` clean (ruff, ruff-format, markdownlint).
- The branch's GitHub CI passes all three required checks (pytest py3.11, pytest py3.12, pre-commit).

## End-to-end smoke (manual, post-merge, on binks)

1. Restart the `__cct__` tmux daemon to load v0.1.2 code:

   ```text
   tmux send-keys -t __cct__ C-c
   # wait, then in the session:
   uv run ccmux-core-telegram
   ```

2. In a Telegram topic that is already bound to a live claude session, kill claude inside that session (e.g. `Ctrl+C` twice or `/exit`).
3. Wait for the spinner to switch to Idle in the status bar.
4. Send any text in the bound topic.
5. **Expected:** the bot replies "Session is dead. /start to rebind to a different session." within ~1 second.
6. Check `~/.ccmux-core-telegram/ccmux-core-telegram.log` — no `DeadError` traceback, no "No error handlers are registered" line.

## Ship plumbing (v0.1.2)

- Bump `src/ccmux_core_telegram/_version.py` from `0.1.1` → `0.1.2`.
- `CHANGELOG.md`: under `## [0.1.2] - 2026-05-13`, a `### Fixed` entry referencing cct#1.
- PR opens against `main` from `fix/cct1-deaderror-catch`. Title: `fix: catch DeadError in on_inbound_text (cct#1) + v0.1.2`.
- Squash-merge after all three required checks pass.
- After merge: `git tag v0.1.2 && git push origin v0.1.2`.
- Close cct#1.
- Update memory entry `[cct v0.1.1 on GitHub]` → v0.1.2 with new state.

## Risk

Very low. The change is additive (a new `except` branch), preserves the existing happy-path control flow, and the new reply text is already shipped via the parallel branch in `on_inbound_text`. Worst-case rollback: revert the squash commit and re-tag.
