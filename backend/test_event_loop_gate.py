"""이벤트 루프 규율 관문의 회귀 — pytest 수집판.

scripts/check_event_loop.py(직접+간접 블로킹 탐지)와 그 정확도 픽스처를 pytest 그물에도
건다. 훅·CI(seam-guards.yml)는 스크립트를 직접 부르지만, `python3 -m pytest` 한 번으로
"저장소가 지금 규율을 지키는가"까지 같이 보이게 한다(2026-09-03 사진 스캔 사고 `696b8007`
이후 전수 정리 — 재발은 여기서 빨갛게).
"""
import importlib.util
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_guard_fixtures_pass():
    """가드 자체의 오탐/미탐 픽스처(단일 파일 + 두 파일 corpus) 전부 통과."""
    fx = _load("check_event_loop_fixtures")
    assert fx.main() == 0


def test_repo_has_no_blocking_calls_in_async_bodies():
    """저장소 전체(backend/ + 패키지)에 async 본문의 동기 블로킹 호출(직접·간접)이 없다."""
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_event_loop.py")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr


def test_photo_scan_shape_is_caught():
    """사고의 모양 그대로 — lazy import 한 모듈의 os.walk 함수를 async 라우트가 직접 부르면 걸린다."""
    import tempfile
    import textwrap
    cel = _load("check_event_loop")
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "scanner.py").write_text(textwrap.dedent('''
            import os
            def scan_media(path, scan_id, cb=None):
                for r, d, f in os.walk(path):
                    pass
        '''), encoding="utf-8")
        (root / "api_photo.py").write_text(textwrap.dedent('''
            def _get_photo_modules():
                import scanner
                return None, scanner
            async def scan_directory(path):
                photo_db, scanner = _get_photo_modules()
                return scanner.scan_media(path, 1)
        '''), encoding="utf-8")
        corpus = cel.Corpus([root / "scanner.py", root / "api_photo.py"])
        hits = corpus.scan(root / "api_photo.py")
        assert len(hits) == 1 and hits[0][3] == "scan_directory", hits
        assert "os.walk" in hits[0][2], hits


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
