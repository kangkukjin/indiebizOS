#!/usr/bin/env python3
"""check_event_loop.py 자체의 정확도 회귀 — 오탐/미탐 픽스처.

왜 가드에 가드가 필요한가: 이 부류의 가드는 **오탐 한 번이면 꺼진다**. 정석 패턴
(async 안에 sync 함수를 정의해 executor 로 넘기기)을 잡아버리면 개발자는 가드를
우회하거나 지우고, 그러면 미탐도 같이 사라진다. 실제로 2026-07-25 에 나이브 스캔이
backend/api_nodes.py 의 모범 사례를 "블로킹"으로 지목해 잘못된 진단을 낳았다 —
그 케이스가 아래 ①이다.

음성(통과해야 함)이 미탐보다 중요하다. 애매하면 통과시키고 BLOCKING 집합을 좁혀라.

2026-09-03 간접 추적 추가: 사진 스캔 사고(`696b8007`)는 async 라우트가 부른 *sync 헬퍼*
안의 os.walk 였다 — 원시 호출만 보는 가드는 통과시켰다. 아래 §2(같은 파일 간접)·
§3(두 파일 corpus — 사고와 같은 모양) 이 그 회귀다.
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


# ── §1·§2 단일 파일 픽스처 — (이름, 코드, 걸려야 하는가) ──
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

    # ── 원시 집합 확장(2026-09-03): 디스크 순회·복사 ──
    ("async 본문 직접 os.walk", '''
        import os
        async def scan(path):
            for root, dirs, files in os.walk(path):
                pass
    ''', True),

    ("async 본문 직접 Path.rglob", '''
        from pathlib import Path
        async def count(d):
            return sum(1 for p in Path(d).rglob("*") if p.is_file())
    ''', True),

    ("async 본문 직접 shutil.copytree", '''
        import shutil
        async def install(src, dst):
            shutil.copytree(src, dst)
    ''', True),

    # ── §2 간접(같은 파일) ──
    ("간접: sync 헬퍼(os.walk)를 async 가 직접 호출 — 사진 스캔 사고 모양", '''
        import os
        def _scan(path):
            n = 0
            for root, dirs, files in os.walk(path):
                n += len(files)
            return n
        async def scan_route(path):
            return _scan(path)
    ''', True),

    ("간접: 같은 헬퍼를 to_thread 로 넘김 (정석)", '''
        import os, asyncio
        def _scan(path):
            for root, dirs, files in os.walk(path):
                pass
        async def scan_route(path):
            return await asyncio.to_thread(_scan, path)
    ''', False),

    ("간접 2단: a → b → subprocess.run", '''
        import subprocess
        def _probe(p):
            return subprocess.run(["ffprobe", p], capture_output=True)
        def _meta(p):
            return {"probe": _probe(p)}
        async def route(p):
            return _meta(p)
    ''', True),

    ("간접: 헬퍼 안 원시에 eventloop-ok 사유 → 전파 원천에서 빠짐", '''
        import subprocess
        _CACHE = None
        def _sysctl(k):
            global _CACHE
            if _CACHE is None:
                _CACHE = subprocess.run(["sysctl", k])  # eventloop-ok: 프로세스당 1회 캐시
            return _CACHE
        async def ping():
            return _sysctl("hw.model")
    ''', False),

    ("간접: 헬퍼가 블로킹을 중첩 def 로 스레드에 넘김 → 헬퍼는 비블로킹", '''
        import threading, time
        def _spawn():
            def _work():
                time.sleep(10)
            threading.Thread(target=_work, daemon=True).start()
        async def route():
            _spawn()
    ''', False),

    ("간접: self.method 해소", '''
        import subprocess
        class Svc:
            def _run(self):
                return subprocess.run(["ls"])
            async def handle(self):
                return self._run()
    ''', True),

    ("간접: 수신자 타입 미상 메서드는 미해소 = 통과", '''
        async def route(obj):
            return obj.scan_media("/x")
    ''', False),

    ("간접: async 헬퍼 호출은 대상 아님(await 로 양보)", '''
        import asyncio
        async def _inner():
            await asyncio.sleep(1)
        async def route():
            return await _inner()
    ''', False),
]


# ── §3 두 파일 corpus — 사고(`696b8007`)와 같은 모양: 헬퍼가 lazy import 한 모듈의
#    함수를 async 라우트가 직접 호출. (파일명, 코드)... 뒤에 (걸려야 하는 파일명 집합)
MULTI_FIXTURES = [
    ("cross-module: 함수 안 lazy `import scanner` + scanner.scan_media() 직접 호출", {
        "scanner.py": '''
            import os, hashlib
            def scan_media(path, scan_id):
                for root, dirs, files in os.walk(path):
                    pass
        ''',
        "api_photo.py": '''
            import sys
            def _get_modules():
                import scanner
                return scanner
            async def scan_directory(path):
                scanner = _get_modules()
                return scanner.scan_media(path, 1)
            async def preview(path):
                import asyncio
                scanner = _get_modules()
                return await asyncio.to_thread(scanner.scan_media, path, 1)
        ''',
    }, {"api_photo.py": 1}),

    ("cross-module: `from mod import fn` 벌거벗은 호출", {
        "storage_db.py": '''
            import os
            def scan_directory(path):
                for r, d, f in os.walk(path):
                    pass
        ''',
        "api_pc.py": '''
            from storage_db import scan_directory
            async def route(path):
                return scan_directory(path)
        ''',
    }, {"api_pc.py": 1}),

    ("cross-module: stem 충돌(handler.py 둘) → 모호 = 통과", {
        "a/handler.py": '''
            import subprocess
            def run():
                return subprocess.run(["x"])
        ''',
        "b/handler.py": '''
            def run():
                return 1
        ''',
        "api_x.py": '''
            import handler
            async def route():
                return handler.run()
        ''',
    }, {}),

    ("cross-module: stem 충돌이어도 같은 폴더 후보는 해소", {
        "a/handler.py": '''
            import subprocess
            def run():
                return subprocess.run(["x"])
        ''',
        "a/api_a.py": '''
            import handler
            async def route():
                return handler.run()
        ''',
        "b/handler.py": '''
            def run():
                return 1
        ''',
    }, {"a/api_a.py": 1}),
]


def _run_single(name, code, expect_hit):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(textwrap.dedent(code))
        path = pathlib.Path(fh.name)
    try:
        hits = _cel.scan_file(path)
    finally:
        os.unlink(path)
    return hits


def _run_multi(files: dict) -> dict:
    """{상대경로: 코드} 를 임시 폴더에 펼쳐 Corpus 로 대조. 반환 {상대경로: 건수}(0건 제외)."""
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        paths = []
        for rel, code in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(textwrap.dedent(code), encoding="utf-8")
            paths.append(p)
        corpus = _cel.Corpus(paths)
        out = {}
        for p in paths:
            hits = corpus.scan(p)
            if hits:
                out[str(p.relative_to(root))] = len(hits)
        return out


def main() -> int:
    failures = []
    for name, code, expect_hit in FIXTURES:
        hits = _run_single(name, code, expect_hit)
        got_hit = bool(hits)
        ok = got_hit == expect_hit
        kind = "미탐" if expect_hit else "오탐"
        print(f"  [{'PASS' if ok else 'FAIL'}] {'걸림' if expect_hit else '통과'} 기대 — {name} ({len(hits)}건)")
        if not ok:
            failures.append((name, kind, hits))

    for name, files, expect in MULTI_FIXTURES:
        got = _run_multi(files)
        ok = got == expect
        print(f"  [{'PASS' if ok else 'FAIL'}] corpus — {name} (기대 {expect or '통과'}, 실제 {got or '통과'})")
        if not ok:
            failures.append((name, "미탐" if expect and not got else "오탐", [got]))

    total = len(FIXTURES) + len(MULTI_FIXTURES)
    if failures:
        print(f"\n[FAIL] 가드 정확도 회귀 {len(failures)}건:")
        for name, kind, hits in failures:
            print(f"  · {name} — {kind}")
            for h in hits:
                print(f"      {h}")
        print("\n오탐이면 BLOCKING 집합을 좁히거나 허용 규칙을 넓혀라 — 오탐 한 번이면 가드가 꺼진다.")
        return 1

    print(f"[OK] 가드 정확도 픽스처 {total}건 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
