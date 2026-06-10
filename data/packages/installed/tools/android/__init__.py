"""
Android Phone Control 패키지 (얇은 센터피스)
ADB(uiautomator)로 폰 화면 독해·터치·입력. [limbs:android]{op}
"""

import sys
from pathlib import Path

_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from adb_core import find_adb, run_adb  # noqa: F401

__all__ = ["find_adb", "run_adb"]
