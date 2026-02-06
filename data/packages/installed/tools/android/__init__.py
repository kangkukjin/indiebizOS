"""
Android 관리 도구 패키지
ADB를 통한 안드로이드 기기 관리
"""

import sys
from pathlib import Path

_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from tool_android import use_tool
from adb_core import find_adb, run_adb

__all__ = ['use_tool', 'find_adb', 'run_adb']
