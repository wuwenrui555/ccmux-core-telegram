# cct#1 — DeadError catch + v0.1.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a defense-in-depth `try/except DeadError` around `b.send_prompt` in `runtime.on_inbound_text` so that the narrow race between Backend Dead transition and `_run_binding` finally replies a friendly hint instead of escaping to PTB's top-level. Ship as v0.1.2.

**Architecture:** No structural change. Single try/except in one existing function. New test uses the same subclass-via-fixture pattern already used by `test_runtime_outbound.py` (`FakeBackendClass = fake_backend`).

**Tech Stack:** Python ≥3.11, pytest, pytest-asyncio, ruff, pre-commit. Production dep already pinned: `ccmux-core>=0.3.2`.

**Spec:** `docs/superpowers/specs/2026-05-13-cct1-deaderror-catch-design.md`

**Branch:** `fix/cct1-deaderror-catch` (already created and active)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/ccmux_core_telegram/runtime.py` | Modify | Add `DeadError` import; wrap `b.send_prompt(...)` in try/except inside `on_inbound_text` |
| `tests/test_runtime_inbound.py` | Modify | Add one test `test_inbound_dead_error_replies_hint` that triggers `DeadError` via a subclassed `FakeBackend` |
| `src/ccmux_core_telegram/_version.py` | Modify | `0.1.1` → `0.1.2` |
| `CHANGELOG.md` | Modify | Add `## [0.1.2] - 2026-05-13` section with one `### Fixed` entry referencing cct#1 |

No new files. No `tests/conftest.py` changes.

---

## Task 1: Add failing test for DeadError path

**Files:**
- Test: `tests/test_runtime_inbound.py`

### Step 1.1: Append the new test to `tests/test_runtime_inbound.py`

- [ ] **Step 1.1 — write the test (paste at end of file, after the existing last test)**

```python
async def test_inbound_dead_error_replies_hint(
    state_dir, fake_application, fake_backend, make_update_fixture
) -> None:
    """DeadError from send_prompt is caught and replied with the dead-hint."""
    from ccmux_core.error import DeadError

    FakeBackendClass = fake_backend

    class _DeadOnSend(FakeBackendClass):
        async def send_prompt(self, text: str) -> None:
            raise DeadError("test")

    fake = _DeadOnSend(msgs=[])
    state = RuntimeState()
    state.backend_handles[42] = fake
    fake_application.bot_data["runtime"] = state

    update = make_update_fixture(text="hello", message_thread_id=42)
    context = type("Ctx", (), {"application": fake_application})()
    await runtime.on_inbound_text(update, context)

    update.message.reply_text.assert_called_once()
    args, _kwargs = update.message.reply_text.call_args
    assert "dead" in args[0].lower() or "rebind" in args[0].lower()
```

Notes:
- `from ccmux_core.error import DeadError` is local to the test function to keep file-level imports unchanged.
- The subclass-via-fixture pattern (`FakeBackendClass = fake_backend; class _DeadOnSend(FakeBackendClass)`) matches `test_runtime_outbound.py:104-106` exactly.
- The assertion regex (`"dead" in ... or "rebind" in ...`) matches the existing `test_inbound_dead_topic_replies_hint` style so the two race-window tests stay symmetric.

- [ ] **Step 1.2 — run the new test, confirm it FAILS**

Run: `uv run pytest tests/test_runtime_inbound.py::test_inbound_dead_error_replies_hint -v`

Expected: FAIL. The exception `ccmux_core.error.DeadError: test` propagates out of `on_inbound_text` because no `try/except` wraps `b.send_prompt`. Pytest reports `DeadError` raised; `reply_text` was not called.

Do NOT proceed if it passes — that means either the import path is wrong or the fixture wiring is off.

- [ ] **Step 1.3 — confirm the other 4 inbound tests still pass**

Run: `uv run pytest tests/test_runtime_inbound.py -v`

Expected: 4 passed, 1 failed (the new one). If anything else fails, stop and inspect.

---

## Task 2: Implement the fix in `runtime.py`

**Files:**
- Modify: `src/ccmux_core_telegram/runtime.py`

### Step 2.1: Add the `DeadError` import

- [ ] **Step 2.1 — add import**

The current imports near the top of `runtime.py` (lines 14-16):

```python
from ccmux_core import Backend
from ccmux_core.bindings import BindingsTracker
from ccmux_core.state import Dead
```

After the `from ccmux_core.state import Dead` line, add:

```python
from ccmux_core.error import DeadError
```

Result (lines 14-17):

```python
from ccmux_core import Backend
from ccmux_core.bindings import BindingsTracker
from ccmux_core.state import Dead
from ccmux_core.error import DeadError
```

### Step 2.2: Wrap `b.send_prompt` in try/except

- [ ] **Step 2.2 — replace the live-backend branch**

In `on_inbound_text`, the current live-backend branch (lines 148-152):

```python
    if topic_id in state.backend_handles:
        b = state.backend_handles[topic_id]
        await b.send_prompt(msg.text)
        logger.debug("inbound: topic=%d text=%r", topic_id, msg.text)
        return
```

Replace with:

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

Reply-text string MUST match the existing dead-binding branch (`runtime.py:157`) byte-for-byte. Verify by comparing.

### Step 2.3: Run the new test, confirm it PASSES

- [ ] **Step 2.3 — run new test**

Run: `uv run pytest tests/test_runtime_inbound.py::test_inbound_dead_error_replies_hint -v`

Expected: PASS.

### Step 2.4: Run the full inbound suite, confirm no regressions

- [ ] **Step 2.4 — run inbound suite**

Run: `uv run pytest tests/test_runtime_inbound.py -v`

Expected: 5 passed.

### Step 2.5: Run the full test suite, confirm no regressions anywhere

- [ ] **Step 2.5 — run full suite**

Run: `uv run pytest -v`

Expected: all tests pass (no regressions). If anything fails outside the changed files, stop and inspect.

---

## Task 3: Pre-commit + commit the fix

**Files:**
- Modify: `src/ccmux_core_telegram/runtime.py` (staged)
- Modify: `tests/test_runtime_inbound.py` (staged)

### Step 3.1: Run pre-commit

- [ ] **Step 3.1 — pre-commit**

Run: `uv run pre-commit run --all-files`

Expected: all hooks pass (ruff, ruff-format, markdownlint).

If ruff/ruff-format makes changes, re-stage the modified files and re-run pre-commit until clean.

### Step 3.2: Commit

- [ ] **Step 3.2 — commit the fix**

```bash
git add src/ccmux_core_telegram/runtime.py tests/test_runtime_inbound.py
git commit -m "$(cat <<'EOF'
fix: catch DeadError in on_inbound_text (cct#1)

Defense-in-depth: when the Backend has transitioned to Dead but
_run_binding's finally hasn't yet popped backend_handles[topic_id],
b.send_prompt raises DeadError. Previously this escaped to PTB's
top-level and the user saw no reply; now we route to the same
dead-hint reply that the existing "bound but no live backend"
branch uses.

Closes #1

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds, pre-commit hook passes again (it'll be a no-op since we already ran it).

---

## Task 4: Version bump + CHANGELOG

**Files:**
- Modify: `src/ccmux_core_telegram/_version.py`
- Modify: `CHANGELOG.md`

### Step 4.1: Bump version

- [ ] **Step 4.1 — bump `_version.py`**

Change `src/ccmux_core_telegram/_version.py`:

```python
"""Package version. Bumped at release time."""

__version__ = "0.1.2"
```

(only the version string changes from `"0.1.1"` to `"0.1.2"`)

### Step 4.2: Update CHANGELOG.md

- [ ] **Step 4.2 — prepend new section**

Insert a new section between the header block (ending at line 7) and the existing `## [0.1.1] - 2026-05-13` section (line 8). The new section:

```markdown
## [0.1.2] - 2026-05-13

### Fixed

- `on_inbound_text` now catches `DeadError` from `b.send_prompt` and replies
  with `Session is dead. /start to rebind to a different session.` instead of
  letting the exception escape to PTB's top-level. Closes the narrow race
  window between Backend Dead transition and `_run_binding`'s finally block.
  ([#1](https://github.com/wuwenrui555/ccmux-core-telegram/issues/1))

```

Full resulting file head (for reference — do not paste this whole block, just insert the new section):

```markdown
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
...
```

### Step 4.3: Pre-commit on the bump files

- [ ] **Step 4.3 — pre-commit**

Run: `uv run pre-commit run --all-files`

Expected: clean.

### Step 4.4: Commit the bump

- [ ] **Step 4.4 — commit**

```bash
git add src/ccmux_core_telegram/_version.py CHANGELOG.md
git commit -m "$(cat <<'EOF'
chore: bump version to 0.1.2

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Final verification before handoff

### Step 5.1: Full test suite once more

- [ ] **Step 5.1**

Run: `uv run pytest -v`

Expected: all tests pass.

### Step 5.2: Git log + status

- [ ] **Step 5.2 — confirm branch state**

Run:

```bash
git log --oneline main..HEAD
git status
```

Expected:
- `git log` shows 3 commits on the branch: spec doc, fix, version bump.
- `git status` shows working tree clean, on `fix/cct1-deaderror-catch`.

### Step 5.3: Stop here — DO NOT push, DO NOT open PR, DO NOT restart daemon

- [ ] **Step 5.3 — hand off to user**

The user will:
1. Manually e2e test against the running daemon (kill claude in a bound topic, send text, expect the dead-hint reply, check log for no traceback).
2. Push the branch and open the PR themselves.
3. After CI passes + squash-merge + tag, restart the `__cct__` daemon.

Report back to the user:
- "Implementation done on branch `fix/cct1-deaderror-catch`."
- "3 commits: spec, fix, version bump."
- "All tests pass; pre-commit clean."
- "Ready for your e2e test, then PR."
