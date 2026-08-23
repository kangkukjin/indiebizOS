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


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
