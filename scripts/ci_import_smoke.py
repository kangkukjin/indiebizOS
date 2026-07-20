#!/usr/bin/env python3
"""백엔드 import 스모크 — 모듈 그래프가 이 플랫폼에서 로드되는가.

api.py 가 라우터 25개 + 코어 모듈 전부를 import 하므로 `import api` 한 방이
곧 부팅 등가 검사다. 유닉스 전용 import(fcntl 부류)·문법 오류·순환 import 가
새면 여기서 죽는다. 윈도우 CI(portability.yml)에서 PYTHONUTF8=1 로 실행.

임포트 시점에 백그라운드 스레드가 생겨도 CI 잡이 안 매달리게 os._exit 로 종료.
"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

try:
    import api  # noqa: F401
except BaseException:
    traceback.print_exc()
    print("[smoke] backend import FAILED", flush=True)
    os._exit(1)

print("[smoke] backend import OK", flush=True)
os._exit(0)
