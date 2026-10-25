"""심층기억 입구 관문 (2026-09-17 기억 재고 감사).

심층기억은 *주인이 직접 한 말*에서만 자란다. 두 관문을 고정한다.

① 발화자 축 — 인지 파이프라인의 모든 진입점은 `utterance_author` 를 **명시**한다(fail-closed).
   "owner" 가 아니면(에이전트 위임문·보고 회수·예약 주입문·회원) 심층 증류를 돌지 않는다.
   실측: 시스템 AI 위임문의 하네스 안내("[중요: 파일 경로 원칙] …")가 프로젝트 에이전트의
   `사용자선호` 로 저장됐다(건축 #7, ep3832). 진입점을 사람이 골라 고치면 샌다 — AST 로 전수 센다.
② 지시 대상은 원문 문맥으로 판단한다. 접속사로 저장을 거부하지 않고 필요한 단위를 함께 보존한다.
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


def test_context_is_preserved_without_connective_veto():
    from memory_evidence import durable_source_units, select_units
    text = "아내의 생일은 11월 18일입니다. 그래서 그날 선물을 드립니다. 그리고 저는 채식을 합니다."
    units = durable_source_units(text)
    assert all(u["eligible"] for u in units)
    assert select_units([1, 2], units) == units[:2]
    assert text[units[2]["start"]:units[2]["end"]] == "그리고 저는 채식을 합니다."


if __name__ == '__main__':
    import sys, pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
