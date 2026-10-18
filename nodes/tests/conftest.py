"""Make each node's service and the shared contract importable by its tests."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _part in ("common", "pi4", "pi3a", "pi3b"):
    _path = str(_ROOT / _part)
    if _path not in sys.path:
        sys.path.insert(0, _path)
