"""패키지 형제 모듈 싱글턴 로더의 동시성 회귀 (2026-08-05 감사 ⑤).

## 왜 이 테스트가 있나 — 실측된 결함

`sys.modules[key] = module` 을 `exec_module` **앞**에 두는 주문이 4개 핸들러에
복붙돼 있었다(youtube·radio·cctv·browser-action). 그 순서 자체는 순환 import 를
견디려는 표준 관용구지만, 싱글턴 조회가 `if key in sys.modules: return` 이면
**동시 호출자가 반쯤 만들어진 모듈을 받는다.**

op fixture 를 6-way 병렬로 돌리다 실제로 터졌다:

    [sense:video]{op:"history"}
    → module 'tool_watch_singleton' has no attribute 'history'

같은 순간의 `feed` 는 성공했다 — 모듈이 feed 까지만 실행된 상태였기 때문이다.
단독 재실행은 정상이라 **재현이 어렵고 원인을 오해하기 쉬운 부류**다. IBL 은 `&`
병렬 연산자를 1급으로 가지므로 이건 이론적 레이스가 아니다.

음성 대조까지 여기 둔다 — 옛 주문이 같은 조건에서 정말 깨지는지 함께 단언해야
이 테스트가 "무엇을 막고 있는지"가 코드로 남는다.
"""
import importlib.util
import os
import sys
import textwrap
import threading
from pathlib import Path

_BACKEND = os.path.dirname(os.path.abspath(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
    import boot_paths  # noqa: F401 — 층 디렉토리 등재 (물리 이동 2026-08-05)

from common.pkg_utils import load_singleton  # noqa: E402

# 실행이 오래 걸리는 모듈 — 앞부분(early)과 뒷부분(late) 사이에 창이 벌어진다
_SLOW = textwrap.dedent("""
    import time
    def early(): return "early"
    time.sleep(0.3)
    def late(): return "late"
""")


def _write(tmp_path, name, body=_SLOW):
    (tmp_path / f"{name}.py").write_text(body, encoding="utf-8")
    return str(tmp_path / "anchor.py")      # 앵커는 존재하지 않아도 된다(부모 폴더만 씀)


def _hammer(fn, n=8):
    ok, err = [], []

    def worker():
        try:
            ok.append(fn().late())
        except Exception as e:                       # noqa: BLE001
            err.append(type(e).__name__)

    ts = [threading.Thread(target=worker) for _ in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return ok, err


def test_concurrent_loaders_never_see_half_built_module(tmp_path):
    anchor = _write(tmp_path, "slowmod_ok")
    ok, err = _hammer(lambda: load_singleton(anchor, "slowmod_ok"))
    assert err == [], err
    assert len(ok) == 8
    # 한 번만 실행되고 모두 같은 인스턴스를 본다
    assert load_singleton(anchor, "slowmod_ok") is sys.modules["slowmod_ok"]


def test_old_pattern_would_have_failed(tmp_path):
    """음성 대조 — 등록이 exec 앞이면 실제로 깨진다(이 테스트가 지키는 대상)."""
    anchor_dir = tmp_path
    (anchor_dir / "slowmod_old.py").write_text(_SLOW, encoding="utf-8")

    def old_load():
        if "slowmod_old" in sys.modules:
            return sys.modules["slowmod_old"]
        spec = importlib.util.spec_from_file_location(
            "slowmod_old", str(anchor_dir / "slowmod_old.py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules["slowmod_old"] = m       # ← exec 전에 공개하는 옛 주문
        spec.loader.exec_module(m)
        return m

    try:
        ok, err = _hammer(old_load)
        assert err, "옛 주문이 안 깨지면 이 회귀 테스트는 아무것도 안 지키고 있다"
        assert set(err) == {"AttributeError"}
    finally:
        sys.modules.pop("slowmod_old", None)


def test_failed_exec_does_not_poison_sys_modules(tmp_path):
    """반쪽 모듈이 눌러앉으면 프로세스 수명 내내 모든 호출이 죽는다."""
    anchor = _write(tmp_path, "boom", "raise RuntimeError('boom')\n")
    for _ in range(2):
        try:
            load_singleton(anchor, "boom")
            raise AssertionError("예외가 전파돼야 한다")
        except RuntimeError as e:
            assert "boom" in str(e)
    assert "boom" not in sys.modules


def test_handlers_use_the_shared_loader():
    """레이스를 고친 4개 핸들러가 인라인 주문으로 되돌아가지 않았는가."""
    root = Path(_BACKEND).parent / "data" / "packages" / "installed" / "tools"
    for pkg in ("youtube", "radio", "cctv", "browser-action"):
        src = (root / pkg / "handler.py").read_text(encoding="utf-8")
        assert "load_singleton" in src, pkg
        assert "sys.modules[" not in src.replace("sys.modules[_", ""), pkg


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
