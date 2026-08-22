r"""소스 경로의 몸 = .venv 하나 — 진입점 고정 가드 (2026-08-22)

세 진입점(start.sh · scripts/backend_keeper.sh · frontend/electron/backend-process.js)이
전부 `PY="python3"` 를 먼저 깔고 .venv 가 있으면 덮어쓰는 모양이었다. .venv 가 없으면
**조용히 다른 인터프리터로 백엔드가 떴다.**

fastapi 부재처럼 시끄럽게 죽는 결함은 그나마 낫다. 나쁜 것은 *버전이 다르게 깔린*
의존이다 — 시스템 파이썬의 playwright 1.58 은 이 저장소가 받아 둔 크로미움 빌드
(1234)를 못 찾아 브라우저 단계만 조용히 죽는다. /health 는 초록이다.
(ep1394 [sense:crawl] 실패 조사에서 드러난 부류 — f30d083 참조.)

포장(설치본)의 임베디드·번들 파이썬은 **의도된 다른 몸**이라 이 가드의 소관이 아니다.

실행: python3 backend/test_venv_pinned.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent


def _read(rel):
    p = ROOT / rel
    assert p.exists(), "진입점이 사라졌다(이름이 바뀌었나?): %s" % rel
    return p.read_text(encoding="utf-8")


def test_start_sh_refuses_without_venv():
    t = _read("start.sh")
    assert not re.search(r'^\s*PY="python3"\s*$', t, re.M), \
        "조용한 폴백이 되살아났다: PY=\"python3\""
    assert ".venv/bin/python3" in t and "exit 1" in t, "거절 경로가 없다"


def test_keeper_refuses_without_venv():
    t = _read("scripts/backend_keeper.sh")
    assert not re.search(r'^\s*PY="python3"\s*$', t, re.M), \
        "keeper 에 조용한 폴백이 되살아났다"
    # 되살릴 수 없으면 되살리지 않고 신고해야 한다 — 거절이 기동보다 앞에 있어야 한다
    assert "재기동 보류" in t, "keeper 가 .venv 부재를 신고하지 않는다"
    guard_at = t.index("재기동 보류")
    launch_at = t.index('nohup "$PY" api.py')
    assert guard_at < launch_at, "거절이 기동 뒤에 있다 — 잘못된 몸으로 이미 떴다"
    assert "return 1" in t[guard_at:launch_at], "신고만 하고 그대로 되살린다"


def test_electron_dev_pins_venv():
    t = _read("frontend/electron/backend-process.js")
    dev = t[t.index("if (isDev)"):t.index("// 프로덕션")]
    assert ".venv" in dev, "개발 분기가 .venv 를 보지 않는다"
    assert "throw new Error" in dev, "개발 분기에 거절 경로가 없다"
    assert not re.search(r"pythonPath = process\.platform === 'win32' \? 'python' : 'python3';", dev), \
        "조용한 폴백이 되살아났다"


def test_packaged_paths_untouched():
    """포장은 임베디드/번들 파이썬을 쓴다 — 이 가드가 그걸 막으면 안 된다."""
    t = _read("frontend/electron/backend-process.js")
    prod = t[t.index("// 프로덕션"):]
    assert "runtime" in prod and "python" in prod, "포장 경로의 번들 파이썬이 사라졌다"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for fn in fns:
        try:
            fn()
            print("  ✓ %s" % fn.__name__)
        except Exception as e:
            fails += 1
            print("  ✗ %s — %s" % (fn.__name__, e))
    print("\n%d/%d 통과" % (len(fns) - fails, len(fns)))
    sys.exit(1 if fails else 0)
