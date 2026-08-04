#!/usr/bin/env python3
"""백엔드 import 스모크 — 윈도우 임베디드 파이썬 등가 조건의 부팅 등가 검사.

api.py 가 라우터 25개 + 코어 모듈 전부를 import 하므로 api.py 톱레벨 실행 한 방이
곧 부팅 등가 검사다. 유닉스 전용 import(fcntl 부류)·문법 오류·순환 import 가
새면 여기서 죽는다.

★임베디드 등가 조건: 배포 임베디드 파이썬(python311._pth, isolated)은 스크립트
폴더·cwd 를 sys.path 에 넣지 않는다 — api.py 는 스스로 sys.path.insert 를 하기
전까지 backend 로컬 모듈을 import 할 수 없다. 옛 스모크는 이 스크립트가 backend 를
sys.path 에 먼저 넣고 `import api` 를 해서 그 조건이 재현되지 않았다(v1.3.6 의
sys.path.insert 앞 `import mime_compat` 이 CI 를 통과하고 윈도우 설치앱에서만
죽은 이유). 지금은:

  * 워크플로가 `python -I`(isolated)로 실행 — 스크립트 폴더·cwd 미포함 + PYTHON*
    환경변수 무시 = 임베디드 등가. (-I 가 -E 를 포함해 PYTHONUTF8 이 무시되므로
    인코딩은 명령줄 `-X utf8` 로 지정 — portability.yml 참조)
  * backend 를 sys.path 에 넣지 않고 api.py 를 파일 경로로 exec — api.py 가
    스스로 부트스트랩해야만 모듈 그래프가 로드된다.

모듈명이 "api"(≠ __main__)라 uvicorn 기동 블록은 안 돈다. 임포트 시점에
백그라운드 스레드가 생겨도 CI 잡이 안 매달리게 os._exit 로 종료.
"""
import importlib.util
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_PY = os.path.join(ROOT, "backend", "api.py")
# cwd 는 옛 스모크와 동일하게 backend — -I 라 sys.path 에는 안 들어가므로
# 임베디드 등가성은 유지되고, 상대경로 파일 I/O 만 기존 조건과 같아진다.
os.chdir(os.path.join(ROOT, "backend"))

if not sys.flags.isolated:
    print("[smoke] 경고: -I(isolated) 없이 실행 중 — 임베디드 등가 조건이 보장되지 않음", flush=True)

try:
    spec = importlib.util.spec_from_file_location("api", API_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["api"] = mod
    spec.loader.exec_module(mod)
except BaseException:
    traceback.print_exc()
    print("[smoke] backend import FAILED", flush=True)
    os._exit(1)

print("[smoke] backend import OK", flush=True)
os._exit(0)
