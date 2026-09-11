"""RED의 적용/검증 수행자. 재기동 판단은 하지 않고 제어자의 작업 영수증만 남긴다."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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
                result = apply_job(spec["base"], spec["state"]["request"]["payload"]["job_path"])
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
