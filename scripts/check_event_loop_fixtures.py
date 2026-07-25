#!/usr/bin/env python3
"""check_event_loop.py 자체의 정확도 회귀 — 오탐/미탐 픽스처.

왜 가드에 가드가 필요한가: 이 부류의 가드는 **오탐 한 번이면 꺼진다**. 정석 패턴
(async 안에 sync 함수를 정의해 executor 로 넘기기)을 잡아버리면 개발자는 가드를
우회하거나 지우고, 그러면 미탐도 같이 사라진다. 실제로 2026-07-25 에 나이브 스캔이
backend/api_nodes.py 의 모범 사례를 "블로킹"으로 지목해 잘못된 진단을 낳았다 —
그 케이스가 아래 ①이다.

음성(통과해야 함)이 미탐보다 중요하다. 애매하면 통과시키고 BLOCKING 집합을 좁혀라.
"""
import importlib.util
import os
import pathlib
import sys
import tempfile
import textwrap

ROOT = pathlib.Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("_cel", ROOT / "scripts" / "check_event_loop.py")
_cel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cel)


# (이름, 코드, 걸려야 하는가)
FIXTURES = [
    ("중첩 sync + run_in_executor (api_nodes 정석)", '''
        async def peer_status():
            def _probe() -> bool:
                import requests
                return requests.get("http://x/ping", timeout=2).status_code == 200
            import asyncio
            return await asyncio.get_event_loop().run_in_executor(None, _probe)
    ''', False),

    ("async 본문 직접 time.sleep", '''
        import time
        async def start_ollama():
            for i in range(20):
                time.sleep(0.5)
    ''', True),

    ("async 본문 직접 subprocess.run", '''
        import subprocess
        async def get_sub():
            result = subprocess.run(["ffmpeg"], capture_output=True)
    ''', True),

    ("람다 본문 (executor 로 넘기는 정석)", '''
        import asyncio, requests
        async def f():
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: requests.get("http://x"))
    ''', False),

    ("asyncio.to_thread 인자로 전달", '''
        import asyncio, time
        async def f():
            await asyncio.to_thread(time.sleep, 1)
    ''', False),

    ("평범한 sync 함수 (async 아님)", '''
        import time
        def helper():
            time.sleep(5)
    ''', False),

    ("from time import sleep — 벌거벗은 이름", '''
        from time import sleep
        async def f():
            sleep(3)
    ''', True),

    ("억제 주석 (사유 포함)", '''
        import time
        async def boot():
            time.sleep(0.1)  # eventloop-ok: 부팅 1회, 요청 경로 아님
    ''', False),

    ("중첩 class 의 sync 메서드", '''
        import time
        async def f():
            class W:
                def run(self): time.sleep(1)
            return W()
    ''', False),

    ("중첩 sync 안에 다시 async def", '''
        import time
        async def outer():
            def maker():
                async def inner():
                    time.sleep(1)
                return inner
            return maker
    ''', True),

    ("동기 HTTP 를 async 라우트에서 직접 (자기교착 부류)", '''
        import requests
        async def peer():
            return requests.get("http://127.0.0.1:8765/ping", timeout=2).status_code
    ''', True),
]


def main() -> int:
    failures = []
    for name, code, expect_hit in FIXTURES:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
            fh.write(textwrap.dedent(code))
            path = pathlib.Path(fh.name)
        try:
            hits = _cel.scan_file(path)
        finally:
            os.unlink(path)
        got_hit = bool(hits)
        ok = got_hit == expect_hit
        kind = "미탐" if expect_hit else "오탐"
        print(f"  [{'PASS' if ok else 'FAIL'}] {'걸림' if expect_hit else '통과'} 기대 — {name} ({len(hits)}건)")
        if not ok:
            failures.append((name, kind, hits))

    if failures:
        print(f"\n[FAIL] 가드 정확도 회귀 {len(failures)}건:")
        for name, kind, hits in failures:
            print(f"  · {name} — {kind}")
            for h in hits:
                print(f"      {h}")
        print("\n오탐이면 BLOCKING 집합을 좁히거나 허용 규칙을 넓혀라 — 오탐 한 번이면 가드가 꺼진다.")
        return 1

    print(f"[OK] 가드 정확도 픽스처 {len(FIXTURES)}건 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
