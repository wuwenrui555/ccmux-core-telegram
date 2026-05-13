# /start Rebind UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship cct#2 (self-rebind bug fix) + cct#6 (`/start` header line) as a single PR, release as v0.1.1.

**Architecture:** Surgical edits to `src/ccmux_core_telegram/picker.py`: add a header-line prefix inside `_build_picker` (so all callers — `on_start`, `on_filter_callback` — inherit it), and weaken the cross-topic guard in `on_pick_callback` so the current topic can re-bind a session it already owns. TDD throughout. Version bump + CHANGELOG bootstrap in the same PR.

**Tech Stack:** Python 3.11/3.12, python-telegram-bot 21.x, pytest (asyncio mode auto), uv, ruff, pre-commit, hatchling, gh CLI.

**Branch:** Already on `feat/start-rebind-ux` (created from `main`, spec already committed). Single PR direct to `main` (this repo uses single-main-branch model, not git-flow).

**Spec:** [`docs/superpowers/specs/2026-05-13-start-rebind-ux-design.md`](../specs/2026-05-13-start-rebind-ux-design.md). The spec is the source of truth for design decisions; this plan is the execution path.

---

## Task 1: Header line in `_build_picker`

**Files:**
- Modify: `src/ccmux_core_telegram/picker.py` (function `_build_picker`, lines 23-83)
- Modify: `tests/test_picker_keyboard.py` (append 3 new tests)

- [ ] **Step 1: Add the three failing tests to `tests/test_picker_keyboard.py`**

Append to the bottom of the file:

```python
def test_build_picker_header_live_binding() -> None:
    """When current topic is bound to a live session, header is prepended."""
    from ccmux_core_telegram.binding import TopicBinding

    core = {
        "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
    }
    topic_bindings = {
        42: TopicBinding(
            topic_id=42,
            tmux_session="ccmux",
            group_chat_id=-100,
            bound_at="2026-05-13T00:00:00Z",
        ),
    }
    text, _kb = picker._build_picker(
        core_bindings=core,
        topic_bindings=topic_bindings,
        filter_mode="all",
        current_topic_id=42,
    )
    assert text.startswith("Currently bound to: ccmux\n\n")
    assert "Pick a tmux session:" in text


def test_build_picker_header_dead_binding() -> None:
    """When current topic is bound but session ended in core, header has '(no longer live)' suffix."""
    from ccmux_core_telegram.binding import TopicBinding

    core = {
        # Present in core but ended (current_session_id=None).
        "ccmux": {"current_session_id": None, "pane_id": "%0"},
    }
    topic_bindings = {
        42: TopicBinding(
            topic_id=42,
            tmux_session="ccmux",
            group_chat_id=-100,
            bound_at="2026-05-13T00:00:00Z",
        ),
    }
    text, _kb = picker._build_picker(
        core_bindings=core,
        topic_bindings=topic_bindings,
        filter_mode="all",
        current_topic_id=42,
    )
    assert text.startswith("Currently bound to: ccmux (no longer live)\n\n")


def test_build_picker_no_header_when_unbound() -> None:
    """When current topic has no binding, no header is prepended (regression guard)."""
    core = {
        "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
    }
    text, _kb = picker._build_picker(
        core_bindings=core,
        topic_bindings={},  # current topic 42 not in bindings
        filter_mode="all",
        current_topic_id=42,
    )
    assert "Currently bound to:" not in text
    assert text == "Pick a tmux session:"
```

- [ ] **Step 2: Run the 3 new tests, verify they fail**

```bash
cd ~/ccmux/ccmux-core-telegram
uv run pytest tests/test_picker_keyboard.py::test_build_picker_header_live_binding tests/test_picker_keyboard.py::test_build_picker_header_dead_binding tests/test_picker_keyboard.py::test_build_picker_no_header_when_unbound -v
```

Expected: 2 failures (header_live_binding asserts text starts with header; no_header_when_unbound asserts text is exactly `"Pick a tmux session:"`). The dead_binding test will also fail because no header is rendered. Confirm at least one is a real assertion failure (not a collection/import error).

- [ ] **Step 3: Implement the header in `_build_picker`**

Edit `src/ccmux_core_telegram/picker.py`. Inside `_build_picker`, immediately after the docstring (before `# Compute live sessions`), insert:

```python
    # Header: if current topic is already bound, show binding state above picker.
    header = ""
    current = topic_bindings.get(current_topic_id)
    if current is not None:
        entry = core_bindings.get(current.tmux_session)
        is_live = entry is not None and entry.get("current_session_id") is not None
        suffix = "" if is_live else " (no longer live)"
        header = f"Currently bound to: {current.tmux_session}{suffix}\n\n"
```

Then prepend `header` to every returned text. Three return sites need updating:

1. The empty-state return (around line 62-67):

   ```python
       if not filtered:
           text = (
               "No sessions in this view."
               if filter_mode != "all"
               else "No live claude sessions."
           )
           return header + text, InlineKeyboardMarkup(rows)
   ```

2. The final return (line 83):

   ```python
       return header + "Pick a tmux session:", InlineKeyboardMarkup(rows)
   ```

- [ ] **Step 4: Run the 3 new tests, verify they pass**

```bash
uv run pytest tests/test_picker_keyboard.py::test_build_picker_header_live_binding tests/test_picker_keyboard.py::test_build_picker_header_dead_binding tests/test_picker_keyboard.py::test_build_picker_no_header_when_unbound -v
```

Expected: 3 passed.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
uv run pytest -q
```

Expected: all tests pass. The existing `test_picker_keyboard.py` tests don't seed `topic_bindings` for `current_topic_id=42`, so they still get `header == ""` and behavior is unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/ccmux_core_telegram/picker.py tests/test_picker_keyboard.py
git commit -m "feat(picker): show 'Currently bound to' header in /start (cct#6)

When the current topic already owns a session, prepend a header line
above the picker so users see binding state before clicking. Suffix
'(no longer live)' is added when the bound session has ended in
ccmux-core. Lives inside _build_picker so on_filter_callback inherits
it across tab switches.

Refs #6"
```

---

## Task 2: Self-rebind fix in `on_pick_callback`

**Files:**
- Modify: `src/ccmux_core_telegram/picker.py` (function `on_pick_callback`, lines 163-198)
- Modify: `tests/test_picker_pick.py` (append 2 new tests)

- [ ] **Step 1: Add the two failing tests to `tests/test_picker_pick.py`**

Append to the bottom of the file:

```python
async def test_pick_self_rebind_succeeds(
    monkeypatch, state_dir, fake_application, fake_backend, make_update_fixture
) -> None:
    """When the current topic already owns the session, picking it again succeeds (cct#2)."""
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    fake = fake_backend(msgs=[], state=Idle(reason="stop"))
    monkeypatch.setattr(
        "ccmux_core_telegram.runtime.Backend",
        lambda *a, **kw: fake,
    )
    fake_application.bot_data["runtime"] = RuntimeState()
    _write_core(
        state_dir,
        {
            "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
        },
    )
    # Seed the topic binding: topic 42 already owns "ccmux".
    binding.put(topic_id=42, tmux_session="ccmux", group_chat_id=-100)

    update = make_update_fixture(
        callback_data="pick:ccmux",
        message_thread_id=42,
        chat_id=-100,
        user_id=1,
    )
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_pick_callback(update, context)

    # Binding still present (overwritten, not removed).
    b = binding.get(42)
    assert b is not None
    assert b.tmux_session == "ccmux"
    # Task started for the (re-)bound topic.
    state = fake_application.bot_data["runtime"]
    assert 42 in state.live_tasks
    # No "bound elsewhere" rejection.
    edit_calls = update.callback_query.edit_message_text.call_args_list
    assert all(
        "bound elsewhere" not in (call.args[0] if call.args else "")
        for call in edit_calls
    )


async def test_pick_cross_topic_still_rejected(
    monkeypatch, state_dir, fake_application, make_update_fixture
) -> None:
    """When another topic owns the session, /start pick is still rejected."""
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_ALLOWED_USERS", "1")
    fake_application.bot_data["runtime"] = RuntimeState()
    _write_core(
        state_dir,
        {
            "ccmux": {"current_session_id": "sid", "pane_id": "%0"},
        },
    )
    # Seed: topic 99 owns "ccmux"; we'll click pick from topic 42.
    binding.put(topic_id=99, tmux_session="ccmux", group_chat_id=-100)

    update = make_update_fixture(
        callback_data="pick:ccmux",
        message_thread_id=42,
        chat_id=-100,
        user_id=1,
    )
    context = type("Ctx", (), {"application": fake_application})()
    await picker.on_pick_callback(update, context)

    # Topic 42 was NOT bound.
    assert binding.get(42) is None
    # Topic 99 still owns it (untouched).
    assert binding.get(99) is not None
    # Rejection text was shown.
    update.callback_query.edit_message_text.assert_called_once()
    args, _kw = update.callback_query.edit_message_text.call_args
    assert "bound elsewhere" in args[0]
```

- [ ] **Step 2: Run the 2 new tests, verify behavior**

```bash
uv run pytest tests/test_picker_pick.py::test_pick_self_rebind_succeeds tests/test_picker_pick.py::test_pick_cross_topic_still_rejected -v
```

Expected: `test_pick_self_rebind_succeeds` FAILS — current code rejects with "bound elsewhere" because the guard doesn't distinguish self-ownership. `test_pick_cross_topic_still_rejected` PASSES (it documents existing behavior we must preserve).

- [ ] **Step 3: Apply the self-rebind fix to `on_pick_callback`**

In `src/ccmux_core_telegram/picker.py`, locate this block in `on_pick_callback` (currently around lines 182-186):

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

When `owner[0] == topic_id` (same topic re-binding its own session), control falls through to the existing `binding.put(...)` which atomically overwrites the row, then `runtime.start_binding(...)` spawns a fresh task.

- [ ] **Step 4: Run the 2 new tests, verify they pass**

```bash
uv run pytest tests/test_picker_pick.py::test_pick_self_rebind_succeeds tests/test_picker_pick.py::test_pick_cross_topic_still_rejected -v
```

Expected: 2 passed.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -q
```

Expected: all tests pass. The existing `test_pick_persists_binding_and_starts_task` covers the unbound-session path and stays green (no prior `binding.put` for topic 42 → `find_by_tmux_session` returns None → guard skipped, fall through).

- [ ] **Step 6: Commit**

```bash
git add src/ccmux_core_telegram/picker.py tests/test_picker_pick.py
git commit -m "fix(picker): allow self-rebind in current topic (cct#2)

The 'bound elsewhere' guard in on_pick_callback rejected even when
the owner was the current topic, blocking the daily recovery flow:
session dies -> revives -> user clicks 'X (current)' to re-bind.
Now the guard only fires when owner[0] != topic_id; same-topic
re-binds fall through to binding.put which atomically overwrites.

Hang-task leak warned about in the original issue is already fixed
upstream (ccmux-core#13 in v0.3.1, cct pinned to v0.3.2).

Refs #2"
```

---

## Task 3: Version bump + CHANGELOG bootstrap

**Files:**
- Modify: `src/ccmux_core_telegram/_version.py`
- Modify: `pyproject.toml` (line 3)
- Create: `CHANGELOG.md`

- [ ] **Step 1: Bump `_version.py` to 0.1.1**

Edit `src/ccmux_core_telegram/_version.py`. Replace `__version__ = "0.1.0"` with:

```python
__version__ = "0.1.1"
```

- [ ] **Step 2: Bump `pyproject.toml` version to 0.1.1**

Edit `pyproject.toml` line 3. Change `version = "0.1.0"` to `version = "0.1.1"`.

- [ ] **Step 3: Create `CHANGELOG.md` at repo root**

Create the file with this exact content:

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

- [ ] **Step 4: Run pre-commit on the staged files to confirm clean**

```bash
git add src/ccmux_core_telegram/_version.py pyproject.toml CHANGELOG.md
uv run pre-commit run --files src/ccmux_core_telegram/_version.py pyproject.toml CHANGELOG.md
```

Expected: ruff/format skipped or pass on `_version.py`/`pyproject.toml`; markdownlint passes on `CHANGELOG.md`. If markdownlint complains about anything (e.g. line-length on the long `[#2]` link), shorten the line within the bullet rather than adding ignores.

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: bump version to 0.1.1 + bootstrap CHANGELOG

Patch release for cct#2 (self-rebind fix) + cct#6 (start header).
First in-repo CHANGELOG file; backfilled 0.1.0 with one-line entry."
```

---

## Task 4: Push branch + open PR

**Files:** none (git/gh operations only).

- [ ] **Step 1: Push the feature branch**

```bash
cd ~/ccmux/ccmux-core-telegram
git push -u origin feat/start-rebind-ux
```

Expected: branch published to origin.

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "feat: /start rebind UX (cct#2 + cct#6) + v0.1.1" --body "$(cat <<'EOF'
## Summary

- Fix cct#2: `on_pick_callback` now allows the current topic to re-bind
  a session it already owns. The previous guard rejected with
  "bound elsewhere" even when `owner == topic_id`, blocking the daily
  recovery flow (session dies, user re-binds from same topic).
- Implement cct#6 Option A: `/start` shows a `Currently bound to: <session>`
  header line above the picker when the current topic is already bound.
  Suffix `(no longer live)` is added when the bound session has ended.
- Bump to v0.1.1 + bootstrap `CHANGELOG.md`.

## Design

Spec: `docs/superpowers/specs/2026-05-13-start-rebind-ux-design.md`.

Header rendering lives inside `_build_picker` so all callers
(`on_start`, `on_filter_callback`, `on_pick_callback`'s edit-text path)
inherit it for free across tab switches.

## Test plan

- [x] 3 new keyboard tests: header rendered for live binding / for dead
  binding / absent for unbound topic
- [x] 2 new pick tests: self-rebind succeeds, cross-topic still rejected
- [x] Full suite (pytest 3.11/3.12) green
- [x] pre-commit clean
- [ ] E2E hand-test on binks: `/start` in bound topic shows header;
  self-rebind path (kill claude → revive → click `current`) succeeds
EOF
)"
```

Expected: PR URL printed. Capture it.

- [ ] **Step 3: Report PR URL to the user and pause for hand-test**

After printing the PR URL, stop. The user will:

1. Confirm the 3 required checks (pytest 3.11, pytest 3.12, pre-commit) all pass on the PR.
2. Run the E2E hand-test on this machine (binks):
   - **(a) Header rendering.** In a Telegram topic that's already bound to a live session, run `/start`. First line of reply should be `Currently bound to: <session>` followed by a blank line and the picker.
   - **(b) Self-rebind.** Bind topic to a claude session. Kill claude in that session. Wait for ccmux-core to detect Idle. Restart claude. Run `/start` in the same topic, click the `✅ <session> (current)` row. Expect `✅ Bound to <session>.` reply (no "bound elsewhere" rejection).

Once the user confirms both pass, proceed to Task 5.

---

## Task 5: Merge + tag + release + close issues

**Files:** none (git/gh operations only).

- [ ] **Step 1: Merge the PR (squash, default)**

```bash
gh pr merge --squash --delete-branch
```

Expected: PR merged; local branch deleted; remote branch deleted.

- [ ] **Step 2: Sync local main**

```bash
git checkout main && git pull --ff-only
```

Expected: local main fast-forwards to the merge commit.

- [ ] **Step 3: Tag v0.1.1 and push**

```bash
git tag -a v0.1.1 -m "v0.1.1 — /start rebind UX fixes (cct#2 + cct#6)"
git push origin v0.1.1
```

Expected: annotated tag pushed.

- [ ] **Step 4: Create the GitHub release**

```bash
gh release create v0.1.1 --title "v0.1.1 — /start rebind UX fixes" --notes "$(cat <<'EOF'
### Fixed
- `/start` in a topic that already owns a session now allows re-binding to that same session (previously rejected with "bound elsewhere"). Restores the daily recovery flow when a bound claude session dies and is restarted. (#2)

### Changed
- `/start` now shows a header line `Currently bound to: <session>` above the picker when the current topic is already bound. Suffix `(no longer live)` is added when the bound session has ended in ccmux-core. (#6)

Full changelog: see `CHANGELOG.md`.
EOF
)"
```

Expected: release URL printed.

- [ ] **Step 5: Close cct#2 and cct#6 with verification comments**

```bash
gh issue close 2 --comment "Fixed in v0.1.1. on_pick_callback now allows self-rebind when owner[0] == topic_id; cross-topic guard still fires. Verified by tests/test_picker_pick.py::test_pick_self_rebind_succeeds + ::test_pick_cross_topic_still_rejected and by E2E hand-test (kill+revive claude in bound topic, click 'current')."

gh issue close 6 --comment "Implemented in v0.1.1. /start now shows 'Currently bound to: <session>' header above the picker (with '(no longer live)' suffix when the bound session has ended). Header is rendered inside _build_picker, so it persists across tab switches. Verified by tests/test_picker_keyboard.py::test_build_picker_header_live_binding / _header_dead_binding / _no_header_when_unbound and by E2E hand-test."
```

Expected: both issues closed with the verification comment.

- [ ] **Step 6: Final report to user**

Print the release URL, the closed issue numbers, and confirm the workflow is complete.

---

## Self-review checklist (post-execution)

- All tests in `tests/test_picker_keyboard.py` and `tests/test_picker_pick.py` pass.
- `_build_picker` returns identical text for the unbound-current-topic case (no header) — `test_build_picker_no_header_when_unbound` is the regression guard.
- Cross-topic rejection text unchanged: still `"'<session>' was just bound elsewhere. /start again."`.
- `CHANGELOG.md` lists both issue links and a one-line `[0.1.0]` backfill.
- v0.1.1 appears in `_version.py`, `pyproject.toml`, `CHANGELOG.md`, the git tag, and the GitHub release title.
