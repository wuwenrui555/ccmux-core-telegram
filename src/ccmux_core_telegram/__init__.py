"""ccmux-core-telegram: Telegram bridge over ccmux-core L2.

Import order contract: ``config`` must be imported first so that its
module-level ``_load_settings_env_files`` / ``_load_dotenv_files`` /
``_setdefault_upstream_dir`` run BEFORE any other module imports
``ccmux_core``. If a sibling consumer imports ``ccmux_core`` directly
before ``ccmux_core_telegram``, the setdefault is too late — but cct's
own tests always go through the package, so this is acceptable for MVP.
"""

from __future__ import annotations

# Side-effect import: loads settings.env/.env, setdefaults CCMUX_CORE_DIR.
from . import config as _config  # noqa: F401
from ._version import __version__

__all__ = ["__version__"]
