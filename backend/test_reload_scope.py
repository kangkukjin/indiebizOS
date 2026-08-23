"""리로드 감시 범위 — 서버는 자기가 import 하지 않는 파일로 재기동하지 않는다 (2026-08-23)

실측 사고(runtime log, 그대로 옮김):

    [08/23/26 08:12:38] INFO  1 change detected
    WARNING: WatchFiles detected changes in 'test_each_envelope_remedy.py'. Reloading...
    [SystemAIRunner] 시스템 AI 중지됨

다른 세션이 `backend/` 에 **시험 파일 하나를 새로 쓴 것**만으로 라이브 백엔드가 재기동했고,
그 순간 20분째 돌고 있던 30회차 상상훈련 턴이 종료 기록도 못 남기고 끊겼다
(episode 1627 = `[Episode ORPHAN]`). 회차의 수리 자체는 지연 적용 프로세스가 죽음을 넘어
완주시켰지만(설계대로), 사용자에게 갈 보고와 GoalEval 은 영영 사라졌다.

이미 `reload_delay=2.0` 이 "자기 컨텍스트를 잃는 자해 패턴"을 막으려 서 있었지만 이 사건은
못 막는다 — 편집이 한 번뿐이라 디바운스가 묶을 게 없었다. 참인 처방은 감시 자체를 좁히는
것이다: 시험 파일과 conftest 는 app 의 import 그래프에 **없다**. 감시할 이유가 애초에 없다.

★이 몸의 규약은 "backend 편집은 RED 격리→지연 적용으로 턴을 안 끊는다" 인데, 그 규약은
*시스템 안쪽*에만 적용된다. 바깥(하네스·다른 세션)에서 들어오는 편집에는 강제력이 없으므로,
방어는 서버 쪽에 서 있어야 한다.

실행: .venv/bin/python -m pytest backend/test_reload_scope.py
"""
import ast
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_API = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api.py")


def _uvicorn_kwargs():
    """api.py 의 uvicorn.run(...) 호출 인자를 소스에서 읽는다.

    import 하지 않는 이유: api 모듈을 부르면 앱 전체가 뜬다(무거울 뿐 아니라 시험이
    라이브 상태를 건드릴 수 있다). 이 가드가 묻는 것은 **선언**이므로 소스로 충분하다.
    """
    tree = ast.parse(open(_API, encoding="utf-8").read())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "uvicorn"):
            return {kw.arg: kw.value for kw in node.keywords}
    pytest.fail("api.py 에서 uvicorn.run 호출을 찾지 못했다 — 기동 지점이 옮겨갔나?")


def _reload_excludes_const():
    tree = ast.parse(open(_API, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "RELOAD_EXCLUDES":
                    return [e.value for e in node.value.elts]
    pytest.fail("RELOAD_EXCLUDES 상수가 없다")


def test_L1_리로드가_제외_목록을_실제로_받는다():
    kw = _uvicorn_kwargs()
    assert "reload_excludes" in kw, "uvicorn.run 이 reload_excludes 를 안 받는다 — 감시가 전 범위다"
    assert isinstance(kw["reload_excludes"], ast.Name)
    assert kw["reload_excludes"].id == "RELOAD_EXCLUDES", "제외 목록이 선언과 따로 놀면 드리프트한다"


def test_L2_시험_파일이_제외된다():
    """이 사건을 일으킨 바로 그 모양(`test_*.py` 신규 생성)이 걸러지는지."""
    import fnmatch
    pats = _reload_excludes_const()
    for name in ("test_each_envelope_remedy.py", "test_reload_scope.py", "conftest.py"):
        assert any(fnmatch.fnmatch(name, p) for p in pats), f"{name} 이 감시에 남아 있다: {pats}"


def test_L3_서버가_실제로_안_읽는_것만_뺀다():
    """제외는 '안 읽는 것'에만 정당하다 — 산 배관을 빼면 편집이 조용히 반영 안 된다.

    backend/*.py 중 app 이 import 하는 이름이 제외 패턴에 걸리면 안 된다.
    """
    import fnmatch
    pats = _reload_excludes_const()
    here = os.path.dirname(os.path.abspath(__file__))
    live = [f for f in os.listdir(here)
            if f.endswith(".py") and not f.startswith("test_") and f != "conftest.py"]
    assert live, "backend 에 산 모듈이 없다고? 경로가 틀렸다"
    caught = [f for f in live if any(fnmatch.fnmatch(f, p) for p in pats)]
    assert not caught, f"산 모듈이 감시에서 빠졌다 — 편집이 조용히 반영 안 된다: {caught}"


def test_L4_디바운스는_그대로_있다():
    """이 수리는 reload_delay 를 대체하지 않는다 — 둘은 다른 사건을 막는다
    (연쇄 편집 vs 안 읽는 파일). 하나를 넣으며 다른 하나를 지우지 않았는지 본다."""
    kw = _uvicorn_kwargs()
    assert "reload_delay" in kw, "연쇄 편집 디바운스가 사라졌다"


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다(28회차).
    raise SystemExit(pytest.main([__file__] + __import__("sys").argv[1:]))
