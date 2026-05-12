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
from pathlib import Path


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
