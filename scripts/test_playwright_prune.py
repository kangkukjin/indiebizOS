r"""--prune 안전 가드 회귀 (2026-08-22)

`--prune` 은 지우는 명령이다. 지우면 안 되는 것을 지우지 않는지 매번 확인한다.
가짜 브라우저 주소(PLAYWRIGHT_BROWSERS_PATH)를 만들어 스크립트를 실제로 돌린다.

    P1. 기대 빌드는 절대 지우지 않는다
    P2. 옛 빌드만 지운다
    P3. --prune 없이는 아무것도 안 지운다 (기본은 알리기만)
    P4. stale 이 없으면 멱등

실행: python3 scripts/test_playwright_prune.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_playwright_browsers.py"


def _run(browsers: Path, *flags):
    env = dict(os.environ)
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
    proc = subprocess.run([sys.executable, str(SCRIPT), "--json", *flags],
                          cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120)
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith("@@PLAYWRIGHT_BROWSERS_JSON@@"):
            return json.loads(line.split("@@PLAYWRIGHT_BROWSERS_JSON@@")[1])
    raise AssertionError("요약 마커 없음: %s / %s" % (proc.stdout[-300:], proc.stderr[-300:]))


def _seed(browsers: Path, expected_names):
    """기대 빌드 + 옛 빌드 하나를 심는다."""
    for name in expected_names:
        d = browsers / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "표식").write_text("기대 빌드", encoding="utf-8")
    old = browsers / "chromium-1000"
    old.mkdir(parents=True, exist_ok=True)
    (old / "표식").write_text("옛 빌드", encoding="utf-8")
    return old


def _expected_names(browsers: Path):
    """이 인터프리터의 playwright 가 기대하는 빌드 이름들.

    요약 마커는 expected 를 싣지 않으므로(사람용 출력에만 있다) runtime_utils 를
    직접 부른다 — 별도 프로세스에서 env 를 박아 부작용 없이.
    """
    code = (
        "import os,sys,json;"
        "os.environ['PLAYWRIGHT_BROWSERS_PATH']=%r;"
        "sys.path.insert(0,%r);"
        "import boot_paths;"
        "from runtime_utils import check_playwright_browsers as c;"
        "print(json.dumps([e['name']+'-'+str(e['revision']) for e in c()['expected']]))"
        % (str(browsers), str(ROOT / "backend"))
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=60)
    try:
        return json.loads((proc.stdout or "").strip().splitlines()[-1])
    except Exception:
        raise AssertionError("기대 빌드 목록을 못 읽었다: %s / %s"
                             % (proc.stdout[-200:], proc.stderr[-200:]))


def test_prune_safety():
    with tempfile.TemporaryDirectory() as td:
        browsers = Path(td) / "ms-playwright"
        browsers.mkdir(parents=True)

        names = _expected_names(browsers)
        assert names, "기대 빌드가 하나도 없다 — 시험이 무의미해진다(조용히 건너뛰지 않는다)"
        old = _seed(browsers, names)

        # P3: --prune 없이는 아무것도 안 지운다
        r = _run(browsers)
        assert old.exists(), "P3: --prune 없이 지웠다"
        assert any(Path(p).name == "chromium-1000" for p in r["stale"]), \
            "P3: 옛 빌드를 stale 로 보지도 못한다: %r" % r["stale"]

        # P1·P2: --prune 은 옛 것만
        r = _run(browsers, "--prune")
        assert not old.exists(), "P2: 옛 빌드가 남았다"
        for name in names:
            assert (browsers / name).exists(), "P1: ★기대 빌드를 지웠다: %s" % name
        assert r["stale"] == [], "P2: 지운 뒤에도 stale 이 남았다: %r" % r["stale"]

        # P4: 멱등
        r2 = _run(browsers, "--prune")
        assert r2["stale"] == []
        for name in names:
            assert (browsers / name).exists(), "P4: 두 번째 호출이 기대 빌드를 지웠다"


if __name__ == "__main__":
    try:
        test_prune_safety()
        print("  ✓ test_prune_safety")
        print("\n1/1 통과")
    except Exception as e:
        print("  ✗ test_prune_safety — %s" % e)
        print("\n0/1 통과")
        sys.exit(1)
