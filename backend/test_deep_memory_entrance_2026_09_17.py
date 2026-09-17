"""심층기억 입구 관문 (2026-09-17 기억 재고 감사).

심층기억은 *주인이 직접 한 말*에서만 자란다. 두 관문을 고정한다.

① 발화자 축 — 인지 파이프라인의 모든 진입점은 `utterance_author` 를 **명시**한다(fail-closed).
   "owner" 가 아니면(에이전트 위임문·보고 회수·예약 주입문·회원) 심층 증류를 돌지 않는다.
   실측: 시스템 AI 위임문의 하네스 안내("[중요: 파일 경로 원칙] …")가 프로젝트 에이전트의
   `사용자선호` 로 저장됐다(건축 #7, ep3832). 진입점을 사람이 골라 고치면 샌다 — AST 로 전수 센다.
② 지시 대상 관문 — 원문 문장 단위 저장(09-12)의 그림자: "그런데 나는 그 차이가 중요하다고
   생각하는거지." 처럼 떼어 놓으면 무엇에 관한 말인지 알 수 없는 조각. 선행 문장을 함께
   고르지 않은 의존 조각은 기계가 거절한다(판단은 추출 모델, 셀 수 있는 부분만 관문).
"""
import ast
import os
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

BACKEND = os.path.dirname(os.path.abspath(__file__))
ENTRANCES = {"cognitive_stream", "process_system_ai_message"}


def _entrance_calls():
    for root, dirs, files in os.walk(BACKEND):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", "node_modules", ".venv"}]
        for name in files:
            if not name.endswith(".py") or name.startswith("test_"):
                continue
            path = os.path.join(root, name)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                called = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if called in ENTRANCES:
                    yield os.path.relpath(path, BACKEND), node


def test_every_pipeline_entrance_declares_utterance_author():
    calls = list(_entrance_calls())
    assert len(calls) >= 8, "진입점을 못 찾았다 — 이름이 바뀌었으면 ENTRANCES 를 고쳐라"
    missing = [f"{path}:{node.lineno}" for path, node in calls
               if not any(k.arg == "utterance_author" for k in node.keywords)]
    assert not missing, ("발화자 미선언 진입점 — utterance_author 를 명시하라"
                         "(주인이 직접 친 말만 'owner'): " + ", ".join(missing))


def test_only_owner_utterance_reaches_deep_distill(monkeypatch):
    import cognitive_distill as cd

    class Runner(cd.CognitiveDistillMixin):
        project_path = "."
        deep = 0

        def _distill_deep_memory(self, *_a, **_k):
            self.deep += 1

        def _distill_forage_memory(self, *_a, **_k):
            pass

    monkeypatch.setattr(cd, "_principal_owner", lambda: True)
    monkeypatch.setattr("thread_context.get_goal_eval_outcome", lambda: None)
    r = Runner()
    r._after_response("어머니는 1940년생이야.", "네.", write_deep=False, guides_used=[])
    assert r.deep == 0
    r._after_response("어머니는 1940년생이야.", "네.", write_deep=True, guides_used=[])
    assert r.deep == 1


def test_unresolved_reference_gate():
    from memory_evidence import durable_source_units, select_units, unresolved_reference

    text = ("아내에게 선물을 사고 싶은데 플립 스마트폰을 생각하고 있어. "
            "그런데 나는 그 차이가 중요하다고 생각하는거지. "
            "나는 언어가 그런 역할을 한다고 생각해. "
            "나는 앞으로도 중고 제품은 사지 않을 거야.")
    units = durable_source_units(text)
    assert len(units) == 4
    # 단독으로 고른 의존 조각 — 머리 접속·지시어 / 문장 속 지시 관형사
    assert unresolved_reference(select_units([2], units))
    assert unresolved_reference(select_units([3], units))
    # 선행 문장을 함께 고르면 머리가 독립 문장이라 통과
    assert unresolved_reference(select_units([1, 2], units)) is None
    # 독립 문장은 통과 — '그림'·'이사' 같은 낱말의 첫 음절에 걸리지 않는다
    assert unresolved_reference(select_units([1], units)) is None
    assert unresolved_reference(select_units([4], units)) is None
    plain = durable_source_units("그림 그리는 시간을 아침으로 옮겼어. 이사는 11월에 한다.")
    assert unresolved_reference(select_units([1], plain)) is None
    assert unresolved_reference(select_units([2], plain)) is None
    # 여러 단위를 골라도 첫 단위가 의존 머리면 거절
    assert unresolved_reference(select_units([2, 3], units))


if __name__ == '__main__':
    import sys, pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
