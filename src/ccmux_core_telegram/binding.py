"""TopicBinding persistence — owns topic_bindings.json.

Schema (top-level dict keyed by topic_id-as-string):

    {
      "12345": {
        "tmux_session": "ccmux",
        "group_chat_id": -1001234567890,
        "bound_at": "2026-05-12T10:00:00Z"
      }
    }

``pane_id`` is deliberately not stored here — it lives in ccmux-core's
``bindings.json`` and is looked up at Backend instantiation time.
"""

from __future__ import annotations

import fcntl
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import config


@dataclass(frozen=True)
class TopicBinding:
    """One row in topic_bindings.json.

    Carries everything PTB needs for outbound dispatch + an audit
    timestamp. Read-only by design; updates go through ``put()``.
    """

    topic_id: int
    tmux_session: str
    group_chat_id: int
    bound_at: str


# ---------------------------------------------------------------------------
# Internal: atomic write
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, lock_path: Path, data: dict) -> None:
    """Write ``data`` to ``path`` atomically, serialized through ``lock_path``.

    Pattern duplicated from ccmux-core's ``bindings._atomic_write`` (not
    imported, to keep module boundaries clean — same convention
    ccmux-core uses for its claude-tap parser).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            tmp.write_bytes(serialized)
            os.replace(tmp, path)
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _bindings_path() -> Path:
    return config.topic_bindings_path()


def _lock_path() -> Path:
    return config.topic_bindings_path().with_suffix(".json.lock")


def load_all() -> dict[int, TopicBinding]:
    """Read topic_bindings.json from disk.

    Returns ``{}`` if the file is missing or empty. Raises
    ``json.JSONDecodeError`` if the file is malformed (loud failure;
    no silent recovery).
    """
    path = _bindings_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[int, TopicBinding] = {}
    for topic_id_str, entry in raw.items():
        topic_id = int(topic_id_str)
        out[topic_id] = TopicBinding(
            topic_id=topic_id,
            tmux_session=entry["tmux_session"],
            group_chat_id=entry["group_chat_id"],
            bound_at=entry["bound_at"],
        )
    return out


def get(topic_id: int) -> TopicBinding | None:
    """Return the binding for ``topic_id``, or None if unbound."""
    return load_all().get(topic_id)


def put(topic_id: int, tmux_session: str, group_chat_id: int) -> TopicBinding:
    """Insert or overwrite a binding. Persists immediately. Returns the new binding."""
    current = load_all()
    bound_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    b = TopicBinding(
        topic_id=topic_id,
        tmux_session=tmux_session,
        group_chat_id=group_chat_id,
        bound_at=bound_at,
    )
    current[topic_id] = b
    _persist(current)
    return b


def remove(topic_id: int) -> None:
    """Remove a binding. No-op if missing."""
    current = load_all()
    if topic_id not in current:
        return
    del current[topic_id]
    _persist(current)


def find_by_tmux_session(tmux_session: str) -> tuple[int, int] | None:
    """Return ``(topic_id, group_chat_id)`` for the binding that owns
    ``tmux_session``, or None if no topic owns it.
    """
    for b in load_all().values():
        if b.tmux_session == tmux_session:
            return (b.topic_id, b.group_chat_id)
    return None


def _persist(bindings: dict[int, TopicBinding]) -> None:
    serializable = {
        str(b.topic_id): {
            "tmux_session": b.tmux_session,
            "group_chat_id": b.group_chat_id,
            "bound_at": b.bound_at,
        }
        for b in bindings.values()
    }
    _atomic_write(_bindings_path(), _lock_path(), serializable)
