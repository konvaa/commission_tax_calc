"""Per-user data directory shared by the GUI and the CLI.

Not using Qt's ``QStandardPaths`` here keeps the core Qt-free; the locations
match what Qt would choose on each OS closely enough for a small cache.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "commission_tax_calc"


def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_DIR_NAME


def rules_cache_dir() -> Path:
    return user_data_dir() / "rules"
