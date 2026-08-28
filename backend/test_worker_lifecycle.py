"""유령 워커 봉인 회귀 (2026-08-28, api.py 두 가드)

W1. 고아 감시: multiprocessing spawn 자식에 부모-사망 감시를 심고 부모를 SIGKILL —
    자식이 스스로 죽는다(join sentinel 이벤트 구동). uvicorn reload 워커가 리로더
    사망 때 :8765 를 문 채 고아로 남던 부류(07-19·08-28 실측)의 기제 고정.
W2. 종료 시한: non-daemon 스레드가 종료를 막아도 시한 뒤 os._exit — 스레드 이름 신고.

실행: python3 backend/test_worker_lifecycle.py
"""
import os
import signal
import subprocess
import sys
import textwrap
import time

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401,E402


def test_w1_orphan_watch_kills_child():
    """부모 SIGKILL → 감시 스레드가 자식을 3초 안에 데려간다."""
    parent_src = textwrap.dedent("""
        import multiprocessing as mp, sys, time

        def child_main():
            # api.py 고아 감시 블록과 같은 기제
            import multiprocessing as mp, threading, os, sys
            parent = mp.parent_process()
            assert parent is not None

            def die_with_parent():
                parent.join()
                os._exit(1)

            threading.Thread(target=die_with_parent, daemon=True).start()
            print(os.getpid(), flush=True)     # 부모 스크립트가 stdout 으로 전달
            time.sleep(60)                      # 고아라면 60초 살아 있을 몸

        if __name__ == "__main__":
            mp.set_start_method("spawn")
            p = mp.Process(target=child_main)
            p.start()
            sys.stdout.write(f"CHILD={p.pid}\\n")
            sys.stdout.flush()
            time.sleep(60)                      # 부모는 죽임당할 때까지 대기
    """)
    proc = subprocess.Popen([sys.executable, "-c", parent_src],
                            stdout=subprocess.PIPE, text=True)
    line = proc.stdout.readline().strip()
    assert line.startswith("CHILD="), line
    child_pid = int(line.split("=")[1])
    time.sleep(1.0)                             # 자식의 감시 스레드 기동 여유
    os.kill(proc.pid, signal.SIGKILL)           # 부모 급사 = 유령 발생 조건
    from common.platform_utils import pid_alive   # 생존 판정 단일 소스 (os.kill(pid,0) 금지 관문)
    deadline = time.time() + 3.0
    alive = True
    while time.time() < deadline:
        if not pid_alive(child_pid):
            alive = False
            break
        time.sleep(0.1)
    proc.wait()
    assert not alive, f"자식 {child_pid} 가 부모 사망 후에도 살아 있다 — 고아 감시 불발"


def test_w2_shutdown_deadline_forces_exit():
    """non-daemon 스레드가 살아 있어도 시한 뒤 강제 종료 + 이름 신고."""
    src = textwrap.dedent("""
        import threading, time, os

        threading.Thread(target=lambda: time.sleep(60), name="stuck-poller").start()

        def deadline(grace=1):
            time.sleep(grace)
            blockers = sorted(t.name for t in threading.enumerate()
                              if not t.daemon and t is not threading.main_thread())
            print("BLOCKERS:" + ",".join(blockers), flush=True)
            os._exit(0)

        threading.Thread(target=deadline, daemon=True).start()
        # 메인은 여기서 끝나지만 stuck-poller(non-daemon)가 프로세스를 붙잡는다
    """)
    t0 = time.time()
    proc = subprocess.run([sys.executable, "-c", src],
                          capture_output=True, text=True, timeout=10)
    elapsed = time.time() - t0
    assert proc.returncode == 0, proc.stderr[-300:]
    assert elapsed < 8, f"{elapsed:.1f}초 — 시한 강제 종료 불발(60초 스레드에 붙잡힘)"
    assert "BLOCKERS:stuck-poller" in proc.stdout, proc.stdout


if __name__ == "__main__":
    import pytest as _pytest
    sys.exit(_pytest.main([__file__] + sys.argv[1:]))
