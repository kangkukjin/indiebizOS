"""단일 워커 bootstrap. 코드 import 전에 신원을 영속화하고 제어자의 허가를 기다린다."""
import os
import runpy
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import boot_paths  # noqa: E402,F401
from restart_protocol import OwnerLock, atomic_json, control_dir, read_json
from restart_process import identity


def main():
    base = Path(os.environ["INDIEBIZ_BASE_PATH"])
    home = control_dir(base)
    nonce = os.environ["INDIEBIZ_RUNTIME_GENERATION"]
    lock = OwnerLock(home / "worker.lock")
    if not lock.acquire():
        return 3
    try:
        ident = identity(os.getpid())
        ident.update(nonce=nonce, generation=nonce)
        atomic_json(home / "workers" / (nonce + ".json"), ident)
        # 제어자 사망 창: 재실행 제어자가 이 영수증을 채택한 뒤 같은 permit을 쓴다.
        deadline = time.monotonic() + 300
        while not read_json(home / "permits" / (nonce + ".json")):
            if (base / "data/.intentional_shutdown").exists() or time.monotonic() > deadline:
                return 4
            time.sleep(0.1)
        # worker.lock은 프로세스 종료까지 열린 상태로 유지한다.
        runpy.run_path(str(Path(__file__).resolve().parents[1] / "api.py"), run_name="__main__")
        return 0
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
