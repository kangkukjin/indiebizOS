#!/usr/bin/env python3
"""부팅 스모크 — 정본 설치 경로(소스 트리)가 이 OS 에서 실제로 뜨는지 증명한다.

import 스모크(ci_import_smoke.py)의 다음 층: import 성공 ≠ 부팅 성공.
실증 2026-08-10 — backend 층 물리 이동 후 폰 번들이 import 는 전부 초록인데
부팅 첫 줄(__file__ 상대경로)에서 죽었다. import 는 이름만 보고, 부팅은 파일
배치·데이터 로드·라우터 조립까지 본다. 그래서 이 스크립트는 실제로 서버를
띄우고 제어자·세대·준비 상태와 /health 의 저장소 루트를 함께 확인한다.

동작: `python backend/api.py` 를 자식 프로세스로 스폰(INDIEBIZ_PRODUCTION=1
= reload 비활성) → remote_boot 의 검증된 부팅 관측 → 종료.
3 OS 공용(bash 없음, stdlib 만) — portability.yml 의 boot-smoke 매트릭스가 실행.

★자식 stdout 은 PIPE 가 아니라 파일로 받는다 — 부팅 로그가 파이프 버퍼(윈도우
~4KB)를 채우는 순간 자식이 쓰기에서 통째로 블록되는 부류(2026-07-20 cloudflared
실증, pitfall: subprocess PIPE 교착). 실패 시 그 파일 꼬리를 출력한다.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from remote_boot import wait_for_boot
from restart_process import alive, identity, signal_owned, tree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_PY = os.path.join(ROOT, "backend", "api.py")


def _python() -> str:
    """bootstrap.py 가 만든 .venv 가 있으면 그걸로 — CI 가 README 레시피 그대로를 증명하게.
    없으면 현재 인터프리터(로컬 편의)."""
    cand = (os.path.join(ROOT, ".venv", "Scripts", "python.exe") if os.name == "nt"
            else os.path.join(ROOT, ".venv", "bin", "python3"))
    return cand if os.path.exists(cand) else sys.executable
PORT = int(os.environ.get("INDIEBIZ_API_PORT", "8799"))  # 기본 8765 를 피해 로컬 실행과 충돌 없음
DEADLINE_S = int(os.environ.get("BOOT_SMOKE_DEADLINE", "240"))  # 첫 부팅은 임포트가 무거움(윈도우 러너 여유)


def tail(path, lines=120):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except OSError as e:
        return f"(로그 읽기 실패: {e})"


def controller_state(base):
    try:
        with open(os.path.join(base, "data/restart_control/state.json"), encoding="utf-8") as f:
            state = json.load(f)
        # 제어 토큰·전체 설정은 진단 출력에 싣지 않는다.
        return {key: state.get(key) for key in ("phase", "controller", "worker", "last_result")}
    except (OSError, ValueError):
        return {}


def boot_diagnostics(base, log_path):
    return (tail(log_path) + "\n[controller] " + json.dumps(controller_state(base), ensure_ascii=False)
            + "\n[worker]\n" + tail(os.path.join(base, "data/backend_runtime.log")))


def main() -> int:
    env = dict(os.environ)
    env["INDIEBIZ_PRODUCTION"] = "1"   # reload/파일감시 없음 = 자식 1프로세스, terminate 로 깨끗이 죽음
    env["INDIEBIZ_API_PORT"] = str(PORT)
    env["PYTHONUTF8"] = "1"            # 윈도우 러너 cp1252 콘솔에서 한글 로그 죽지 않게
    base = env.get("INDIEBIZ_BASE_PATH", ROOT)
    previous = controller_state(base)
    if any(alive(previous.get(key)) for key in ("controller", "worker")):
        print("[boot-smoke] refused: this installation already has a live controller or worker", flush=True)
        return 2

    py = _python()
    log_fd, log_path = tempfile.mkstemp(prefix="boot_smoke_", suffix=".log")
    print(f"[boot-smoke] spawn: {py} api.py (port {PORT}, log={log_path})", flush=True)
    with os.fdopen(log_fd, "wb") as log_f:
        proc = subprocess.Popen(
            [py, API_PY],
            cwd=os.path.join(ROOT, "backend"),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        launched, result = None, {}
        try:
            t0 = time.monotonic()
            launched = identity(proc.pid)
            result = wait_for_boot(base, ROOT, launched, launcher=launched, port=PORT,
                                   timeout=DEADLINE_S, interval=2)
            if result["status"] != "succeeded":
                print("[boot-smoke] FAILED — " + json.dumps(result), flush=True)
                print(boot_diagnostics(base, log_path), flush=True)
                return 1
            took = time.monotonic() - t0
            print(f"[boot-smoke] OK — verified backend in {took:.1f}s: {result}", flush=True)
            return 0

        finally:
            # Terminating just the Windows venv redirector leaves its actual
            # controller/worker behind. Capture and stop only our birth-bound tree.
            owned = tree(launched) if launched else []
            # A redirector can exit after the observer bound its real child.
            for key in ("controller", "worker"):
                for member in tree(result.get(key)):
                    if member not in owned:
                        owned.append(member)
            for member in owned:
                signal_owned(member)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                for member in owned:
                    signal_owned(member, force=True)
                proc.wait(timeout=5)
            for member in owned:
                if alive(member):
                    signal_owned(member, force=True)


if __name__ == "__main__":
    sys.exit(main())
