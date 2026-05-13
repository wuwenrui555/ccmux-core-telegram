# /start rebind UX — design (cct#2 + cct#6)

**Date:** 2026-05-13
**Status:** approved (brainstorm complete)
**Issues:** [cct#2](https://github.com/wuwenrui555/ccmux-core-telegram/issues/2), [cct#6](https://github.com/wuwenrui555/ccmux-core-telegram/issues/6)
**Target version:** v0.1.1
**Branch model:** single `main`, PR direct to main, 3 required checks (pytest 3.11/3.12 + pre-commit)

## Summary

Single PR to `src/ccmux_core_telegram/picker.py` shipping two related fixes:

1. **cct#2 — self-rebind bug.** `on_pick_callback` rejects `pick:X` when the current topic is *already* the owner of `X`. This blocks the daily recovery flow: when a bound session dies and the user wants to re-bind it from the same topic after revival.
2. **cct#6 — `/start` header.** `_build_picker` always shows the same `"Pick a tmux session:"` text regardless of whether the current topic is already bound. Users have no in-place way to see which session they're currently bound to before clicking.

Bundled because both touch the same file and same `/start` code path. Released as v0.1.1 with bootstrapped `CHANGELOG.md`, tag, and GitHub release.

## Locked decisions (do not re-litigate)

These were decided before this brainstorm or during it; the implementation must follow them:

- **cct#2 fix shape:** four-line diff in `on_pick_callback` — replace the unconditional `find_by_tmux_session is not None` rejection with `owner = ...; if owner is not None and owner[0] != topic_id: reject`.
- **cct#6 approach:** Option A from the issue body — single header line above the picker. B (replace picker), C (no-op), D (separate `/status` command) explicitly rejected and recorded in the issue.
- **Header language:** English, session name only, no `pane_id`. Body strings in `picker.py` are all English; only inline button labels are CN. Pane id is opaque internal plumbing not surfaced anywhere else in the picker.
- **Dead-binding header:** when the current topic has a binding row but the underlying session is no longer live in ccmux-core, render header with `(no longer live)` suffix — not hidden, not bare.
- **Bundling:** one PR, not two.
- **Versioning:** bump v0.1.0 → v0.1.1 in the same PR; tag and create GitHub release after merge.
- **Out of scope:** cct#1 (DeadError defense-in-depth catch) and cct#3 — independent issues, separate PRs.

## Code changes

### 1. `picker.py::_build_picker` — header line

Existing signature already takes `current_topic_id: int` and `topic_bindings: dict[int, TopicBinding]`. No signature change.

At the top of the function (before the `live_sessions` computation), look up the current topic's binding and the live state of its underlying session, then build a header prefix to prepend to the returned text:

```python
header = ""
current = topic_bindings.get(current_topic_id)
if current is not None:
    entry = core_bindings.get(current.tmux_session)
    is_live = entry is not None and entry.get("current_session_id") is not None
    suffix = "" if is_live else " (no longer live)"
    header = f"Currently bound to: {current.tmux_session}{suffix}\n\n"
```

Then prepend `header` to every `text` value the function returns:

- `"No live claude sessions."` → `header + "No live claude sessions."`
- `"No sessions in this view."` → `header + "No sessions in this view."`
- `"Pick a tmux session:"` → `header + "Pick a tmux session:"`

When the current topic is unbound, `header == ""` and behavior is byte-identical to today.

**Why inside `_build_picker` and not in `on_start`:** `on_filter_callback` and the post-bind edit-text in `on_pick_callback` (if it ever re-renders the picker) all funnel through `_build_picker`. Putting the header here makes it sticky across tab switches with zero extra code in callers.

### 2. `picker.py::on_pick_callback` — self-rebind fix

Current code (picker.py:182-186):

```python
if binding.find_by_tmux_session(tmux_session) is not None:
    await query.edit_message_text(
        f"'{tmux_session}' was just bound elsewhere. /start again."
    )
    return
```

Replace with:

```python
owner = binding.find_by_tmux_session(tmux_session)
if owner is not None and owner[0] != topic_id:
    await query.edit_message_text(
        f"'{tmux_session}' was just bound elsewhere. /start again."
    )
    return
```

When `owner[0] == topic_id` (self-rebind), fall through to the existing `binding.put(topic_id, tmux_session, group_chat_id)` call which atomically overwrites the same row, then `runtime.start_binding` spawns a fresh task.

**No leak risk:** the previous task for `topic_id` was already cleared on session death by ccmux-core's hang-task fix in v0.3.1 (issue ccmux-core#13), and this repo is pinned to v0.3.2. The earlier caveat in the issue body about "hang task leak" is obsolete and can be ignored.

### 3. `_version.py` + `pyproject.toml`

- `_version.py`: `__version__ = "0.1.1"`
- `pyproject.toml`: `version = "0.1.1"`

### 4. `CHANGELOG.md` (new file at repo root)

Keep-a-Changelog format. Initial content:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
```

## Test plan

5 new tests, sharing the existing `conftest.py` fixtures (`state_dir`, `fake_application`, `make_update_fixture`, `fake_backend`).

Helper used in pick tests for seeding a topic binding (write through `state_dir`, since conftest sets `CCMUX_CORE_TELEGRAM_DIR`):

```python
from ccmux_core_telegram import binding
binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)
```

### `tests/test_picker_keyboard.py` — 3 new

1. **`test_build_picker_header_live_binding`** — current topic 42 bound to `"ccmux"`, core has `ccmux` with `current_session_id="sid"`. Assert returned text starts with `"Currently bound to: ccmux\n\n"` and contains `"Pick a tmux session:"`.
2. **`test_build_picker_header_dead_binding`** — current topic 42 bound to `"ccmux"`, core has `ccmux` present with `current_session_id=None` (session ended-but-known). Assert text starts with `"Currently bound to: ccmux (no longer live)\n\n"`. The "session entirely absent from core" branch shares the same `is_live=False` code path; not separately tested.
3. **`test_build_picker_no_header_when_unbound`** — current topic 42 not in `topic_bindings`. Assert text does NOT contain `"Currently bound to:"`. (Regression guard against future code that always prepends.)

### `tests/test_picker_pick.py` — 2 new

4. **`test_pick_self_rebind_succeeds`** — seed `binding.put(42, "ccmux", -100)`, write core `{ccmux: {current_session_id, pane_id}}`, dispatch `pick:ccmux` from topic 42 / user 1. Assert `runtime.start_binding` was called (or equivalently `state.live_tasks[42]` is set, mirroring `test_pick_persists_binding_and_starts_task`), and `edit_message_text` was NOT called with the `"bound elsewhere"` string.
5. **`test_pick_cross_topic_still_rejected`** — seed `binding.put(99, "ccmux", -100)`, dispatch `pick:ccmux` from topic 42 / user 1. Assert `edit_message_text` called with text containing `"bound elsewhere"`, and `binding.get(42) is None` (no write happened).

### Coverage rationale

- Tab-switch persistence (`on_filter_callback` re-rendering with the header) is implicit: `_build_picker` is the sole producer of picker text, and `on_filter_callback` already calls it. Not separately tested.
- `on_start` rendering with the header is similarly implicit. The existing `test_on_start_in_topic_renders_picker` keeps passing because it doesn't seed a topic binding for topic 42.
- Dead-binding "session present in core with `current_session_id=None`" vs "session absent from core" share one branch (`is_live` is False in both cases). Test 2 covers it.

## Verification

Pre-merge:

- `uv run pytest -q` — full suite green (existing 21 test files + 5 new tests).
- `pre-commit run --all-files` — clean.
- 3 required main-branch checks pass on PR (pytest 3.11, pytest 3.12, pre-commit).

E2E hand-test on this machine (binks) before merging:

- (a) **Header rendering.** In a topic that's bound to a live session, run `/start` → first line of reply is `Currently bound to: <session>` followed by the picker.
- (b) **Self-rebind.** Bind topic to a claude session. Kill claude in that session. Wait for ccmux-core to detect Idle. Restart claude (or have ccmux-core re-detect a fresh session in that pane). Run `/start` in the same topic, click `✅ <session> (current)`. Expect `✅ Bound to <session>.` (no "bound elsewhere" rejection).

Post-merge:

- `git tag v0.1.1 && git push --tags`
- `gh release create v0.1.1` with notes mirroring the `[0.1.1]` changelog section.
- `gh issue close 2 6` with verification comments referencing the merge commit.

## Risks and non-risks

- **Header-line race.** Between `_build_picker` reading `topic_bindings` and the user clicking, the binding could change (e.g. another concurrent `/start` from a different topic stealing the session). The header would show stale data for one cycle. Mitigation: `on_pick_callback` and `on_steal_callback` already re-validate against `binding.find_by_tmux_session` at click time. Header is purely informational — incorrectness is harmless.
- **Header in tab-switch edit.** When `on_filter_callback` calls `query.edit_message_text(text, ...)`, Telegram allows editing message text freely; no Telegram API limit on length here (header is short). No risk.
- **Memory leak (out of date).** The cct#2 issue body warned about a "hang task leak until ccmux-core#13 lands". That landed in ccmux-core v0.3.1, and this repo is pinned to v0.3.2 (PR #5, merged 2026-05-13). The caveat is obsolete; no separate handling needed.

## Out of scope (explicitly)

- cct#1 (`DeadError` defense-in-depth catch) — separate issue, separate PR.
- cct#3 — separate issue.
- Translating any other body strings to CN, or unifying CN/EN consistency in the picker.
- `pane_id` / `window_name` surfacing anywhere in the UI.
- Refactoring `_build_picker` beyond the header prepend (file is fine).
