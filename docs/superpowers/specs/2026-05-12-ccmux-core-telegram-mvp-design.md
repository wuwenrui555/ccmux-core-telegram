<!-- markdownlint-disable MD024 -->

# ccmux-core-telegram MVP — Telegram bridge over ccmux-core L2

- **Date**: 2026-05-12
- **Repo**: `ccmux-core-telegram` (new, not a fork of legacy `ccmux-telegram`)
- **Status**: design draft, awaiting user review
- **Targets**: ccmux-core-telegram v0.1.0
- **Builds on**:
  - `ccmux-core` v0.3.0 — [bindings tracker design](../../../../ccmux-core/docs/superpowers/specs/2026-05-12-bindings-tracker-design.md)
  - `ccmux-core` v0.2 L2 — [L2 API design](../../../../ccmux-core/docs/superpowers/specs/2026-05-12-ccmux-core-l2-design.md)

## Context

`ccmux-core-telegram` (abbreviated **cct** throughout this doc) is a thin
Telegram bot that bridges ccmux-core's L2 API to Telegram forum topics.
Each Telegram topic is bound 1:1 to a tmux session running Claude Code;
outbound L1 messages from that backend forward to the topic, and inbound
text from the topic dispatches to `Backend.send_prompt()`.

The legacy `ccmux-telegram` package targets the old `ccmux-backend` and
covers a much larger scope (~28 modules: voice transcription, status
bar capture, full command suite, permission callbacks). cct is a
ground-up MVP rewrite targeting the L2 contract from ccmux-core, with
scope deliberately narrowed to the smallest useful surface.

Out of scope: everything except outbound forwarding, inbound text →
prompt, and a `/start` picker for binding. See [Scope](#scope) for the
full out-of-scope list.

## Scope

### IN

- **Multi-session orchestration**: one bot process runs N `Backend`
  instances inside a single asyncio loop. ccmux-core is
  single-Backend-per-instance; in-process pluralism is cct's
  contribution.
- **Outbound forwarding**: each `Backend.messages()` L1 stream → its
  bound Telegram topic, all 5 L1 kinds (`UserPrompt`, `AssistantText`,
  `ToolCall`, `ToolResult`, `PermissionRequest`).
- **Inbound**: plain text from a bound topic → `b.send_prompt(text)`
  for that backend.
- **`/start` command flow**: enters a tmux-session picker UI (3 tabs:
  全部 / 未绑定 / 已绑定). Selecting an unbound session binds; selecting
  a bound session steals it from the previous owner.
- **Binding state persistence**: `topic_bindings.json` survives bot
  restart.
- **Stale-binding handling**: at startup and on Backend death, the
  topic is notified and binding metadata is preserved on disk.

### OUT (defer to future specs)

- All other bot commands (`/esc`, `/bar`, `/text`, `/clear`,
  `/compact`, `/cost`, `/help`, `/memory`, `/model`, `/sweep`,
  `/history`, `/unbind`, `/rebind_*`, `/usage`).
- Permission callbacks (Blocked → ask user → forward decision via
  decision-socket).
- Voice transcription, image / video / document / sticker inbound.
- Status bar capture / rendering.
- Automatic sweep / auto-unbind of stale bindings (steal is in via
  `/start` picker; standalone unbind / rebind commands are out).
- Rich markdown rendering (`telegramify-markdown` etc.).
- History / usage queries.
- Multi-chat deployment, nested topic topologies.

## Architecture

Single-process, single-asyncio-loop. PTB v21's `Application` is the
sole event loop driver. ccmux-core's `BindingsTracker` runs as an
in-process async task in the same loop, keeping its derived cache
(`~/.ccmux-core-telegram/ccmux-core/bindings.json`) fresh without a
separate daemon.

```text
ccmux-core-telegram process (single asyncio loop)
│
├── PTB Application (singleton)
│   ├── inbound handlers
│   │   ├── CommandHandler("/start") → picker.on_start
│   │   ├── MessageHandler(filters.TEXT & filters.User(allowed)) → runtime.on_inbound_text
│   │   └── CallbackQueryHandler(pattern=r"^(pick|steal|filter):") → picker.*
│   └── AIORateLimiter(max_retries=5)
│
├── BindingsTracker (ccmux_core.bindings)
│   └── background task: tail events.jsonl → atomic-write
│       ~/.ccmux-core-telegram/ccmux-core/bindings.json
│
├── per-binding tasks (one per active binding)
│   └── async with Backend(tmux_session, pane_id) as b:
│           async for msg in b.messages():
│               await bot.send_message(chat_id, message_thread_id, text)
│
└── persistent state (on disk, ~/.ccmux-core-telegram/)
    ├── topic_bindings.json        ← cct's own
    ├── settings.env                ← cct config (cwd → global)
    ├── .env                        ← secrets (cwd → global)
    ├── ccmux-core-telegram.log     ← log
    └── ccmux-core/                 ← dependency state, transparent to user
        ├── bindings.json
        └── bindings.json.lock
```

### Process invariants

1. **One binding = one task = one Backend instance.** `live_tasks: dict[int, asyncio.Task]` is the source of truth for "running". A task exits ⇔ Backend exits its `async with` block ⇔ binding is no longer live.
2. **`topic_bindings.json` is persistent intent; `live_tasks` is the running subset.** The two may differ by a stale set (after startup recovery) or a recently-Dead set (mid-run).
3. **cct is the user-facing surface; ccmux-core is a library.** All user-facing env vars are `CCMUX_CORE_TELEGRAM_*`. All state files live in `~/.ccmux-core-telegram/`. ccmux-core's runtime cache is a subdirectory inside cct's dir, hidden from the user. cct persists only what ccmux-core doesn't already track (the `topic_id ↔ tmux_session` mapping); `pane_id` and Backend state come from ccmux-core at runtime.
4. **Inbound accepts only text + `/start` command.** Replies, files, voice, photos, edits — all silently dropped.

## Repo layout

```text
ccmux-core-telegram/
├── pyproject.toml
├── README.md
├── LICENSE                              ← Apache 2.0 (match family)
├── .github/workflows/ci.yml             ← matrix py3.11/3.12 + lint job
├── .pre-commit-config.yaml              ← ruff + ruff-format + markdownlint
├── docs/superpowers/specs/
│   └── 2026-05-12-ccmux-core-telegram-mvp-design.md   ← this doc
├── src/ccmux_core_telegram/
│   ├── __init__.py        ← enforces import order: config first
│   ├── _version.py
│   ├── main.py            ← entry; logging, build Application, run_polling
│   ├── config.py          ← settings.env + .env parser; env accessors; facade setdefault
│   ├── binding.py         ← TopicBinding dataclass + topic_bindings.json atomic I/O
│   ├── runtime.py         ← RuntimeState; _run_binding task body; on_post_init/_shutdown; on_inbound_text
│   ├── picker.py          ← /start handler + keyboard builder + pick/steal/filter callbacks
│   ├── render.py          ← pure: L1 Message → Telegram text/markup
│   └── handler.py         ← PTB handler registration
└── tests/
    ├── conftest.py        ← state_dir, mock_bot, FakeBackend, fake_application fixtures
    ├── test_config.py
    ├── test_binding.py
    ├── test_render.py
    ├── test_picker_keyboard.py
    ├── test_runtime_task.py
    ├── test_runtime_handlers.py
    └── test_picker_callbacks.py
```

Module names are singular per family convention (cf. ccmux-core's
`state.py`, `error.py`). Each module has one clear purpose; cross-module
imports form a DAG with `config` as the only leaf and `main` as the
only top.

### Module dependency graph

```text
main → config, handler
handler → picker, runtime
picker → binding, runtime, render, ccmux_core
runtime → binding, render, config, ccmux_core
binding → config
render → (pure)
config → (stdlib only)
```

### Dependencies

```toml
[project]
name = "ccmux-core-telegram"
version = "0.1.0"
description = "Telegram bridge over ccmux-core L2 API"
requires-python = ">=3.11"
license = { file = "LICENSE" }
dependencies = [
    "ccmux-core>=0.3.0",
    "python-telegram-bot[rate-limiter]>=21.0,<22",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8.0",
]

[tool.uv.sources]
ccmux-core = { path = "../ccmux-core", editable = true }

[project.scripts]
ccmux-core-telegram = "ccmux_core_telegram.main:main"
```

`python-dotenv` is **not** a dependency: cct rolls its own `settings.env`
/ `.env` parser (~30 lines), matching the convention established by
ccmux-core / ccmux-spinner / claude-tap to keep runtime dependencies
minimal.

## State files

### `topic_bindings.json` — cct's own

Path: `${CCMUX_CORE_TELEGRAM_DIR}/topic_bindings.json` (default
`~/.ccmux-core-telegram/topic_bindings.json`).

```json
{
  "12345": {
    "tmux_session": "ccmux",
    "group_chat_id": -1001234567890,
    "bound_at": "2026-05-12T10:00:00Z"
  },
  "67890": {
    "tmux_session": "demo",
    "group_chat_id": -1001234567890,
    "bound_at": "2026-05-12T11:15:00Z"
  }
}
```

Top-level key is `topic_id` as string (JSON limitation; parsed to int on
read). Value carries everything PTB needs for outbound
(`bot.send_message(chat_id=group_chat_id, message_thread_id=topic_id)`)
plus an audit timestamp. `pane_id` is intentionally **not** stored
here; it lives in ccmux-core's `bindings.json` and is looked up at
Backend instantiation time.

#### Atomic write

```python
def _atomic_write(path: Path, lock_path: Path, data: dict) -> None:
    serialized = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            tmp.write_bytes(serialized)
            os.replace(tmp, path)
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)
```

Pattern duplicated from ccmux-core's `bindings._atomic_write` (not
imported, to keep module boundaries clean — same convention ccmux-core
applies to its claude-tap parser).

Readers do not lock; `os.replace` is atomic on the same filesystem, so
readers always observe either the old or new file completely.

### `ccmux-core/bindings.json` — dependency state (transparent)

Path: `${CCMUX_CORE_TELEGRAM_DIR}/ccmux-core/bindings.json`. Owned by
ccmux-core's `BindingsTracker`, which cct embeds in its own asyncio
loop. cct redirects `CCMUX_CORE_DIR` here via `os.environ.setdefault`
before importing `ccmux_core`. Schema is ccmux-core's own (see its
[bindings tracker design](../../../../ccmux-core/docs/superpowers/specs/2026-05-12-bindings-tracker-design.md));
cct only reads it.

## Configuration

### `settings.env` (non-secret operational toggles)

Path: `${CCMUX_CORE_TELEGRAM_DIR}/settings.env`; `./settings.env` in
cwd overrides global. Format: `KEY=value`, `#` comments, optional
single/double quotes.

| Key | Default | Effect |
|---|---|---|
| `CCMUX_CORE_TELEGRAM_DIR` | `~/.ccmux-core-telegram` | state directory (root of everything) |
| `CCMUX_CORE_TELEGRAM_FORWARD_TOOLS` | `true` | when `false`, skip `ToolCall` / `ToolResult` outbound |
| `CCMUX_CORE_TELEGRAM_TOOL_ALLOWLIST` | `Skill` | comma-separated tool names that still forward when `FORWARD_TOOLS=false` |
| `CCMUX_CORE_TELEGRAM_LOG_FILE` | `${DIR}/ccmux-core-telegram.log` | file handler path |
| `CCMUX_CORE_TELEGRAM_LOG_LEVEL` | `DEBUG` | `ccmux_core_telegram` package logger level |
| `CCMUX_CORE_TELEGRAM_BOOTSTRAP_RETRIES` | `-1` | PTB `run_polling(bootstrap_retries=)`; `-1` = infinite |

### `.env` (secrets)

Path: `${CCMUX_CORE_TELEGRAM_DIR}/.env`; `./.env` in cwd overrides
global. Same parser.

| Key | Required | Effect |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | bot token from @BotFather |
| `CCMUX_CORE_TELEGRAM_ALLOWED_USERS` | yes | comma-separated Telegram user IDs (whitelist) |

After `Config` reads these at startup, `main.scrub_sensitive_env()`
pops them from `os.environ` so subprocesses (e.g., tmux invocations
from ccmux-core) never inherit them.

### Facade setdefaults

The `config.py` module performs exactly one upstream-facing
`os.environ.setdefault` on import:

```python
os.environ.setdefault(
    "CCMUX_CORE_DIR",
    str(ccmux_core_telegram_dir() / "ccmux-core"),
)
```

This redirects ccmux-core's state into a subdirectory of cct's dir.
`setdefault` semantics mean a shell-exported `CCMUX_CORE_DIR` still
wins (escape hatch for power users who want a shared `~/.ccmux-core/`).

Other ccmux-core / claude-tap / ccmux-spinner knobs (poll intervals,
spinner grace, etc.) are **not** facaded under `CCMUX_CORE_TELEGRAM_*`.
Power users export those directly. Adding more facade keys is reserved
for future scope when concrete demand exists.

### Load order

```text
1. import ccmux_core_telegram
2. → __init__.py runs `from . import config as _config`
3. → config.py module body runs:
     a. _load_settings_env_files()   # cwd → global, setdefault
     b. _load_dotenv_files()         # cwd → global, setdefault
     c. os.environ.setdefault("CCMUX_CORE_DIR", str(.../ccmux-core))
4. Other modules import ccmux_core lazily (from runtime / picker)
5. → ccmux_core.config runs, reads the now-redirected CCMUX_CORE_DIR
```

This ordering is enforced by `__init__.py` placing the config import
first. Tests that import `ccmux_core` before `ccmux_core_telegram`
will see the un-redirected default; cct's own tests always go through
the package, so this is acceptable.

## Runtime state

```python
# runtime.py
@dataclass
class RuntimeState:
    live_tasks: dict[int, asyncio.Task] = field(default_factory=dict)
    backend_handles: dict[int, Backend] = field(default_factory=dict)
    tracker: BindingsTracker | None = None

def get_state(application: Application) -> RuntimeState:
    return application.bot_data["runtime"]
```

Stored at `application.bot_data["runtime"]` (PTB-idiomatic), so its
lifecycle is bound to the `Application` instance. Tests build a fresh
`Application` and get fresh state for free.

### `start_binding`

```python
async def start_binding(
    application: Application,
    topic_id: int,
    tmux_session: str,
    pane_id: str,
    group_chat_id: int,
) -> None:
    """Create and register a per-binding task. Idempotent only on fresh
    topic_id; caller must ensure no live task already owns it."""
    state = get_state(application)
    task = asyncio.create_task(
        _run_binding(application, topic_id, tmux_session, pane_id, group_chat_id)
    )
    state.live_tasks[topic_id] = task
```

Single entry point for task creation. Called from `on_post_init` (one
per recovered binding) and from `picker.on_pick_callback` /
`on_steal_callback` (one per new binding). The task registers itself
in `state.live_tasks` synchronously, so a subsequent
`state.live_tasks[topic_id]` read in the same coroutine sees the entry.

## Data flows

### Startup (`main.main()` + `runtime.on_post_init`)

```python
def main() -> None:
    setup_logging()
    config.validate_required_env()      # ConfigError exits early if missing
    app = handler.build_application(
        token=config.bot_token(),
        allowed_users=config.allowed_users(),
    )
    main.scrub_sensitive_env()
    app.post_init = runtime.on_post_init
    app.post_shutdown = runtime.on_post_shutdown
    app.run_polling(
        allowed_updates=["message", "callback_query"],
        bootstrap_retries=config.bootstrap_retries(),
    )

async def on_post_init(application: Application) -> None:
    state = RuntimeState()
    application.bot_data["runtime"] = state

    state.tracker = BindingsTracker()
    await state.tracker.__aenter__()

    core = load_core_bindings()
    for topic_id, b in binding.load_all().items():
        c = core.get(b.tmux_session)
        if c is None or c["current_session_id"] is None:
            # stale: notify + skip + retain file
            with contextlib.suppress(Exception):
                await application.bot.send_message(
                    chat_id=b.group_chat_id, message_thread_id=topic_id,
                    text=f"⚠️ binding stale: '{b.tmux_session}' not found/ended. "
                         f"Delete from topic_bindings.json and /start to rebind.",
                )
            logger.warning("stale binding skipped: topic=%d tmux=%s",
                           topic_id, b.tmux_session)
            continue
        await start_binding(application, topic_id, b.tmux_session,
                            c["pane_id"], b.group_chat_id)
```

### Outbound (per-binding task body)

```python
async def _run_binding(application, topic_id, tmux_session, pane_id, group_chat_id):
    bot = application.bot
    state = get_state(application)
    b: Backend | None = None
    try:
        async with Backend(tmux_session, pane_id) as b:
            state.backend_handles[topic_id] = b
            async for msg in b.messages():
                if not _should_forward(msg):
                    continue
                text, parse_mode = render.format(msg)
                try:
                    await bot.send_message(
                        chat_id=group_chat_id, message_thread_id=topic_id,
                        text=text, parse_mode=parse_mode,
                    )
                except RetryAfter:
                    logger.warning(
                        "rate-limit dropped: topic=%d kind=%s",
                        topic_id, type(msg).__name__,
                    )
                    with contextlib.suppress(Exception):
                        await bot.send_message(
                            chat_id=group_chat_id, message_thread_id=topic_id,
                            text="⚠️ dropped one message (rate limit)",
                        )
    finally:
        state.backend_handles.pop(topic_id, None)
        state.live_tasks.pop(topic_id, None)
        # Send death notice only on natural Backend Dead. Voluntary
        # cancel leaves b.state in its pre-cancel value (not Dead),
        # so the check naturally distinguishes the two.
        if b is not None and isinstance(b.state, Dead):
            with contextlib.suppress(Exception):
                await bot.send_message(
                    chat_id=group_chat_id, message_thread_id=topic_id,
                    text=f"🪦 session ended ({b.state.reason}"
                         + (f": {b.state.detail}" if b.state.detail else "") + ")",
                )
```

`_should_forward(msg)`:

- `UserPrompt` / `AssistantText` / `PermissionRequest` → always `True`
- `ToolCall` / `ToolResult` → `forward_tools()` OR `msg.tool_name in tool_allowlist()`

### Inbound text

```python
async def on_inbound_text(update: Update, context):
    msg = update.message
    if msg.message_thread_id is None:
        return                                  # not in a topic, silent
    topic_id = msg.message_thread_id
    state = get_state(context.application)

    if topic_id in state.backend_handles:
        b = state.backend_handles[topic_id]
        await b.send_prompt(msg.text)
        logger.debug("inbound: topic=%d text=%r", topic_id, msg.text)
        return

    # No live backend for this topic
    if binding.get(topic_id) is None:
        return                                  # unbound, silent
    # Bound but Dead → reply each time
    await msg.reply_text(
        "Session is dead. /start to rebind to a different session."
    )
```

Handler is registered with
`filters.User(allowed_users) & filters.TEXT & ~filters.COMMAND`, so
non-whitelisted users never reach the body.

### `/start` picker

Three handlers, distinguished by callback-data prefix:

```text
/start                  → picker.on_start
"filter:<all|unbound|bound>" → picker.on_filter_callback
"pick:<tmux_session>"   → picker.on_pick_callback
"steal:<tmux_session>"  → picker.on_steal_callback
```

`on_start` always launches the picker, regardless of the current
topic's binding status. The picker is the unified entry point for all
binding actions.

```python
async def on_start(update: Update, context):
    msg = update.message
    if msg.message_thread_id is None:
        await msg.reply_text("Use /start inside a forum topic.")
        return
    topic_id = msg.message_thread_id
    text, kb = _build_picker(filter_mode="all", current_topic_id=topic_id)
    await msg.reply_text(text, reply_markup=kb)
```

`_build_picker` queries `load_core_bindings()` (live sessions only),
joins with `binding.load_all()` to compute bound/unbound classification,
and builds the keyboard. Active tab is bracketed (`【全部】 | 未绑定 | 已绑定`).
Each session entry:

- unbound → `[🖥 ccmux]` callback `pick:ccmux`
- bound (other topic) → `[🔒 demo → topic 12345]` callback `steal:demo`
- bound (current topic) → `[✅ ccmux (current)]` callback `pick:ccmux`
  (clicking re-binds to self, treated as no-op confirmation)

`on_filter_callback` re-renders the picker with the new tab filter,
editing the same message.

`on_pick_callback` writes the new binding and starts the task:

```python
async def on_pick_callback(update, context):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in config.allowed_users():
        return
    tmux_session = query.data[len("pick:"):]
    topic_id = query.message.message_thread_id
    group_chat_id = query.message.chat.id

    # Re-validate (picker render → click race window)
    core = load_core_bindings()
    c = core.get(tmux_session)
    if c is None or c["current_session_id"] is None:
        await query.edit_message_text(f"'{tmux_session}' no longer live. /start again.")
        return
    state = get_state(context.application)
    if binding.find_by_tmux_session(tmux_session) is not None:
        await query.edit_message_text(
            f"'{tmux_session}' was just bound elsewhere. /start again."
        )
        return

    # If this topic was previously bound (e.g., Dead state), remove old entry
    if binding.get(topic_id) is not None:
        binding.remove(topic_id)

    binding.put(topic_id, tmux_session, group_chat_id)
    await runtime.start_binding(
        context.application, topic_id, tmux_session,
        c["pane_id"], group_chat_id,
    )
    await query.edit_message_text(f"✅ Bound to `{tmux_session}`.")
```

`on_steal_callback` is the meaningful difference:

```python
async def on_steal_callback(update, context):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in config.allowed_users():
        return
    tmux_session = query.data[len("steal:"):]
    new_topic_id = query.message.message_thread_id
    new_group_chat_id = query.message.chat.id

    state = get_state(context.application)
    old = binding.find_by_tmux_session(tmux_session)
    if old is None:
        # No longer bound (race); fall through to ordinary pick logic
        return await on_pick_callback(update, context)
    old_topic_id, old_group_chat_id = old
    if old_topic_id == new_topic_id:
        await query.edit_message_text(f"✅ Already bound to `{tmux_session}`. No change.")
        return

    # 1. Notify old topic BEFORE cancelling its task
    with contextlib.suppress(Exception):
        await context.application.bot.send_message(
            chat_id=old_group_chat_id, message_thread_id=old_topic_id,
            text=f"🔄 Session `{tmux_session}` was claimed by another topic. "
                 f"This topic is no longer connected. /start to rebind.",
        )
    # 2. Cancel old task (its `finally` clears state.live_tasks/handles).
    old_task = state.live_tasks.get(old_topic_id)
    if old_task is not None:
        old_task.cancel()
    # 3. Remove old entry from disk
    binding.remove(old_topic_id)
    # 4. If new topic had a prior (Dead) entry, remove it
    if binding.get(new_topic_id) is not None:
        binding.remove(new_topic_id)

    # 5. Validate session is still live, write new entry, start new task
    core = load_core_bindings()
    c = core.get(tmux_session)
    if c is None or c["current_session_id"] is None:
        await query.edit_message_text(f"'{tmux_session}' no longer live. /start again.")
        return
    binding.put(new_topic_id, tmux_session, new_group_chat_id)
    await runtime.start_binding(
        context.application, new_topic_id, tmux_session,
        c["pane_id"], new_group_chat_id,
    )
    await query.edit_message_text(
        f"✅ Bound to `{tmux_session}` (stolen from topic {old_topic_id})."
    )
    logger.info("steal: tmux=%s old_topic=%d new_topic=%d",
                tmux_session, old_topic_id, new_topic_id)
```

### Dead handling

Already covered by the outbound task body's `finally` block. Key
properties:

- Backend exit is observable as `async for msg in b.messages()`
  terminating.
- `b.state` at exit distinguishes natural Dead (notice sent) from
  voluntary cancel (no notice).
- `topic_bindings.json` is never modified on Dead. The user can `/start`
  to rebind (the new picker model handles this automatically).

### Shutdown

```python
async def on_post_shutdown(application: Application) -> None:
    state = get_state(application)
    tasks = list(state.live_tasks.values())
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    if state.tracker is not None:
        await state.tracker.__aexit__(None, None, None)
```

PTB handles SIGINT / SIGTERM and invokes `post_shutdown` automatically
during graceful shutdown.

## Logging

```python
def setup_logging() -> None:
    log_file = config.log_file()
    log_level = getattr(logging, config.log_level().upper(), logging.DEBUG)

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.WARNING,            # root: minimal third-party noise
    )

    logging.getLogger("ccmux_core_telegram").setLevel(log_level)
    logging.getLogger("ccmux_core").setLevel(log_level)
    logging.getLogger("telegram.ext.AIORateLimiter").setLevel(logging.INFO)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(log_level)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    logging.getLogger().addHandler(fh)
```

stderr handler is created by `basicConfig`; file handler is added on
top. Both receive everything the package logger emits.

| Event | Level | Format |
|---|---|---|
| Startup binding recovered | INFO | `started binding: topic=%d tmux=%s pane=%s` |
| Startup stale binding | WARNING | `stale binding skipped: topic=%d tmux=%s` |
| Binding ends | INFO | `binding ended: topic=%d reason=%s` |
| Outbound message | DEBUG | `outbound: topic=%d kind=%s text=%r` |
| Inbound message | DEBUG | `inbound: topic=%d text=%r` |
| Rate-limit drop | WARNING | `rate-limit dropped: topic=%d kind=%s` |
| Steal | INFO | `steal: tmux=%s old_topic=%d new_topic=%d` |
| Fatal exit | ERROR | `fatal: %s` + traceback |

Per the locked decision (Q5), DEBUG includes message bodies — both
inbound text and outbound rendered content. Privacy implication: log
file readers can see conversation content. The log file lives inside
`~/.ccmux-core-telegram/` which is user-owned; users running cct on
shared servers should set appropriate filesystem permissions.

## Error handling matrix

| Failure | Detection | Recovery |
|---|---|---|
| Telegram token invalid | PTB raises at `run_polling()` | log ERROR; process exits non-zero |
| Telegram network outage | PTB internal retry | `bootstrap_retries=-1` → infinite retry; logs at WARNING |
| Telegram rate limit (FloodWait) | `AIORateLimiter` retries up to 5 | drop on exhaust; placeholder sent to topic |
| Backend Dead mid-run | `b.messages()` terminates + `b.state` is `Dead` | death notice; `topic_bindings.json` unchanged; user `/start`s to rebind |
| Backend pane lost | Same as Dead with `reason='pane_lost'` | same |
| tmux session missing at startup | `core_bindings.get(...)` returns None | stale notification; task not started; `topic_bindings.json` retained |
| Telegram chat removed | `send_message` raises | wrap in `suppress(Exception)`; log; task continues attempting subsequent messages |
| `topic_bindings.json` corrupt | JSON parse error on read | raise loud (no silent recovery); user inspects |
| `ccmux-core/bindings.json` stale | Stale at point-in-time only; tracker catches up on EOF tail | accepted; user can run `ccmux-core bindings snapshot` manually for a full rebuild |
| Power loss during atomic write | `os.replace` is atomic; `flock` serializes writers | readers always observe complete old or new file; no corruption window |

## Testing strategy

Following ccmux-core's pattern: synthetic data, no network / tmux /
claude required in CI. e2e smoke tests with a real bot token are
manual, pre-release only.

### Test files

| File | Coverage | Key cases |
|---|---|---|
| `test_config.py` | settings.env / .env parsing + accessors | comments, quoted values, blank lines, missing required raises, `setdefault` respects shell exports, facade sets `CCMUX_CORE_DIR` |
| `test_binding.py` | `topic_bindings.json` I/O | put/get/remove roundtrip, `find_by_tmux_session`, empty file → `{}`, atomic-write integrity under simulated mid-write failure, malformed JSON raises |
| `test_render.py` | L1 Message → Telegram text | one case per L1 kind, ToolResult truncation at 4096 chars, `is_error` rendering, empty fields |
| `test_picker_keyboard.py` | picker UI builder (pure) | 3-tab active highlighting, all-unbound / all-bound / mixed lists, "no free sessions" empty-state |
| `test_runtime_task.py` | `_run_binding` async | fake Backend pumps 5 message kinds → mock bot receives; Dead state triggers notice; cancel does not trigger notice; rate-limit exhaust drops + placeholder; `FORWARD_TOOLS=false` filters tool messages but allowlist override works |
| `test_runtime_handlers.py` | on_inbound_text / on_post_init / on_post_shutdown | route to live backend; Dead topic replies hint; unbound topic silent; startup recovers + notifies stale; shutdown cancels all tasks |
| `test_picker_callbacks.py` | pick / steal / filter handlers | always-enter picker; self-steal no-op; full steal flow (notify + cancel + remove old + write new + start new); filter tab switching; picker render → click race resolves cleanly |

### Test infrastructure

```python
# tests/conftest.py
@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    d = tmp_path / "ccmux-core-telegram"
    d.mkdir()
    monkeypatch.setenv("CCMUX_CORE_TELEGRAM_DIR", str(d))
    return d

@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot

class FakeBackend:
    """Duck-typed stand-in for ccmux_core.Backend."""
    def __init__(self, msgs: list[Message], state: State | None = None):
        self._msgs = msgs
        self._state = state
        self.sent_prompts: list[str] = []
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None
    async def messages(self):
        for m in self._msgs:
            yield m
    async def send_prompt(self, text):
        self.sent_prompts.append(text)
    @property
    def state(self): return self._state

@pytest.fixture
def fake_application():
    app = MagicMock()
    app.bot_data = {}
    app.bot = AsyncMock()
    return app
```

Tests that exercise `runtime._run_binding` monkey-patch the `Backend`
reference at its import site:

```python
def test_run_binding_dead_triggers_notice(monkeypatch, fake_application):
    fake = FakeBackend(msgs=[...], state=Dead(reason="session_end"))
    monkeypatch.setattr(
        "ccmux_core_telegram.runtime.Backend",
        lambda *a, **kw: fake,
    )
    # ... assert mock_bot.send_message called with death notice text
```

This is dependency injection via the import system; the spec
deliberately avoids passing a `Backend` factory argument to keep the
production code path simple (one fewer parameter, one fewer indirection).

### CI

Same template as ccmux-core (`.github/workflows/ci.yml`):

- Matrix: `python-version: ["3.11", "3.12"]` on `ubuntu-latest`.
- Pre-test step: `pip install git+https://github.com/wuwenrui555/ccmux-core.git@v0.3.0`
  (ccmux-core not on PyPI yet).
- `pip install -e '.[dev]'` → `pytest tests/ -v`.
- Separate lint job: `pre-commit run --all-files`.

### Coverage targets

MVP does not enforce coverage percentage. **Required coverage** (the
paths whose absence would break user expectations):

- Each of the 5 L1 message kinds renders to text (render.py).
- Steal end-to-end (notify + cancel + remove + start).
- Dead notice fires on natural Dead; does not fire on cancel.
- Startup notifies stale bindings and skips task creation.
- Atomic write leaves old file intact on simulated interrupt.

Branch coverage on filter callback, keyboard builder, config parser is
nice-to-have but not gated.

## Decisions log

For audit / future reconsideration:

- **`/start` is the only binding command in MVP.** No `/unbind`,
  `/rebind`, `/sweep`. Steal is bundled into the picker. Adding
  separate commands later is non-breaking; bundling is the simpler
  initial surface.
- **1:1 binding maintained via steal.** Selecting a bound session in
  the picker transfers ownership atomically. Many-to-one is never a
  state, so cct never needs to reason about partial routing.
- **Dead notice from `finally` block.** Same code path handles natural
  Dead and voluntary cancel; the `isinstance(b.state, Dead)` check
  distinguishes them. No separate Dead watcher task.
- **`bot_data["runtime"]: RuntimeState` over module-level globals.**
  PTB-idiomatic, lifecycle-bound to `Application`, per-test isolation
  for free.
- **`BindingsTracker` via `post_init` / `post_shutdown`.** Async
  context manager spanning `run_polling()` requires explicit hooks;
  alternative `async def amain()` wrapping is uglier.
- **Roll-own settings.env parser.** Matches ccmux-core / ccmux-spinner
  / claude-tap convention; avoids `python-dotenv` dependency.
- **Subdirectory `ccmux-core/` not `core/`.** Naming consistency with
  the parent `~/.ccmux-core-telegram/` (full name throughout).
- **Stale bindings not shown in picker.** Picker filters to live tmux
  sessions only. Stale entries are reachable only via inbound text
  hint or manual file edit. Avoids picker becoming a full binding
  management surface.
- **Inbound on Dead topic replies every time.** No de-dup state. The
  user notices and acts; if they keep typing, the hint keeps coming.
  Simpler internal state.
- **Single facade `CCMUX_CORE_DIR` setdefault.** Other upstream knobs
  are left to direct shell export. Adding more facades is reserved
  until concrete demand exists.
- **Log file name full (`ccmux-core-telegram.log`).** Aligns with
  package name; no shorthand in user-visible paths.
- **`bootstrap_retries=-1` default but configurable.** Matches legacy
  ccmux-telegram behavior; configurable for users who prefer bounded
  retry counts.

## Open questions

None. All design decisions are locked.

## Rollout

1. Land this spec on `dev`.
2. Invoke `superpowers:writing-plans` to produce a detailed
   implementation plan.
3. Invoke `bootstrapping-python-repo` during plan execution to
   scaffold the repo (pyproject, CI, pre-commit, LICENSE, README).
4. Implement modules per the plan with `executing-plans-test-first`.
5. Cut release as ccmux-core-telegram v0.1.0.
6. Update memory entries to reflect the locked design (see below).

## Memory updates required

After this spec is approved:

- **Update** `project_cct_mvp_locked_decisions.md`:
  - Remove the "/start in bound topic → show current binding, no
    rebind (manual delete to change)" line; replace with "/start
    always enters picker; bound sessions are stealable; manual file
    edit no longer required for rebind".
  - Promote "Topic binding state file" section from "proposal" to
    "locked" with the schema from this spec.
  - Remove the "Open for the brainstorm" section entirely (all
    closed).
- **Add** a new memory entry pointing to this spec file path so future
  sessions resume from "spec written, plan pending".
