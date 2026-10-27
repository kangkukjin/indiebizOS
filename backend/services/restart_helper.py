"""RED의 적용/검증 수행자. 재기동 판단은 하지 않고 제어자의 작업 영수증만 남긴다.

제어자와 같은 기반(이 파일이 사는 트리)의 프로토콜·restart_red 를 쓰고, 그 밖의 코드(red_apply·수리
패키지 handler 등)는 INDIEBIZ_CODE_ROOT(현역 세대, 없으면 정본)에서 읽는다. 적용 대상 저장소는
INDIEBIZ_SOURCE_ROOT(정본)다 — 수행자가 어느 사본에서 뜨든 쓰기·커밋은 정본으로 간다.
"""
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "base"))
try:
    import control_base as _cb
    _support = os.environ.get("INDIEBIZ_CODE_ROOT") or os.environ.get("INDIEBIZ_SOURCE_ROOT") or str(_HERE.parent)
    _cb.install_support_path(_HERE.parent, _support)
except Exception:
    pass
import boot_paths  # noqa: E402,F401
from restart_process import identity
from restart_protocol import OwnerLock, atomic_json, read_json


def main(path):
    path = Path(path)
    spec = read_json(path)
    lock = OwnerLock(path.with_suffix(".lock"))
    if not lock.acquire():
        return 3
    try:
        if path.with_suffix(".done").exists():
            return 0
        receipt = path.with_suffix(".process")
        if receipt.exists():
            return 4  # 이전 수행자가 도중에 죽었다. 효과를 재실행하지 않는다.
        atomic_json(receipt, identity(os.getpid()))
        try:
            from restart_red import apply_job, verify_after_boot
            if spec["action"] == "apply":
                payload = spec["state"]["request"]["payload"]
                result = apply_job(spec["base"], payload["job_path"], payload.get("reservation"))
            else:
                result = {"verified": verify_after_boot(spec["base"], spec["state"])}
            atomic_json(path.with_suffix(".done"), {"ok": True, "result": result})
        except BaseException as exc:
            atomic_json(path.with_suffix(".done"), {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return 1
        return 0
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
