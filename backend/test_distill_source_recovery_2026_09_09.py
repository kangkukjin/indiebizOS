"""ep3219/3223/3224 증류 실패: 성공 원문을 보존해 복구하고 모든 적재 관문을 유지한다."""
import json
import sys
import types

import pytest

import boot_paths  # noqa: F401
from ibl_distill_gates import _recover_distill_selection
from ibl_param_vocab import code_syntax_error


# 에피소드에서 관측한 문법 손상을 재현하되 개인 데이터·보고서 본문은 싣지 않는다.
CASES = [
    (
        '$기억 = [self:memory]{op: "recall", node: "보고서/AI 동향", store: "실행"}\n'
        '$기억.phrases',
        '$기억 = [self:memory]{op: "recall", node: "보고서/AI 동향", store: "실행"}.phrases',
    ),
    (
        '$완산 = [sense:realty]{source: "molit", region_code: "52111", type: "apt", deal: "rent"}\n'
        '$덕진 = [sense:realty]{source: "molit", region_code: "52113", type: "apt", deal: "rent"}\n'
        '($완산 >> [table:groupby]{by: "계약유형", agg: {건수: ["count"]}}) & '
        '($덕진 >> [table:groupby]{by: "계약유형", agg: {건수: ["count"]}}) >> [table:union]',
        '$완산 = [sense:realty]{source: "molit", region_code: "52111", type: "apt", deal: "rent"}\n'
        '($완산 >> [table:groupby]{by: "계약유형", agg: {건수: ["count"]}}) & '
        '($덕진 >> [table:groupby]{by: "계약유형", agg: {건수: ["count"]}}) >> [table:union]',
    ),
    (
        '[table:each]{items: [{vid: "example"}], keep: ["vid"], '
        'do: "[self:struct]{file: \'/tmp/transcripts/${it.vid}.json\', '
        'schema: \'tip,timestamp\', grounded: true}"}',
        '[table:each]{items: [{vid: "example"}], keep: ["vid"], '
        'do: "[self:struct]{file: "/tmp/transcripts/${it.vid}.json", '
        'schema: "tip,timestamp", grounded: true}"}',
    ),
]


@pytest.mark.parametrize("source,broken", CASES, ids=["ep3219", "ep3223", "ep3224"])
def test_three_failures_recover_exact_source(source, broken):
    assert code_syntax_error(broken)
    assert code_syntax_error(source) is None
    requests = []

    def ask(**kw):
        requests.append(kw)
        # 생성 모델이 code를 또 보내도 실행 원문만 사용해야 한다.
        return json.dumps({"call_ids": [1], "code": '[self:delete]{path:"/tmp/x"}'})

    fixed, note = _recover_distill_selection("실행된 핵심 패턴", broken,
                                             code_syntax_error(broken), [source], ask)
    assert fixed == source and note == "호출 1"
    assert len(requests) == 1
    assert code_syntax_error(broken) in requests[0]["prompt"]


@pytest.mark.parametrize("ids", [None, "1", [0], [2], [True], [1.0], [1, 1]])
def test_bad_selection_is_not_interpreted(ids):
    code, why = _recover_distill_selection("x", "broken", "bad", [CASES[0][0]],
        lambda **kw: json.dumps({"call_ids": ids}))
    assert code is None and why


def test_reordered_calls_are_rejected():
    code, why = _recover_distill_selection("x", "broken", "bad", ['[self:time]', '[self:time]'],
        lambda **kw: '{"call_ids": [2, 1]}')
    assert code is None and "실행 순서" in why


def test_no_candidate_or_bad_model_output_does_not_retry():
    for reply in ('{"call_ids": [], "reason": "모델 판단이 필요"}', 'not json', '[]', None):
        seen = []
        def ask(**kw):
            seen.append(kw)
            return reply
        code, why = _recover_distill_selection("x", "broken", "bad", ['[self:time]'], ask)
        assert code is None and why and len(seen) == 1


def test_missing_producer_is_closed_from_successful_source():
    calls = ['$x = [self:time]', '$x >> [table:select]{columns: ["date"]}']
    for ids, expected in [([2], "\n".join(calls)), ([1, 2], "\n".join(calls))]:
        code, _ = _recover_distill_selection("x", "broken", "bad", calls,
            lambda **kw: json.dumps({"call_ids": ids}))
        assert code == expected


@pytest.mark.parametrize("source", [
    '[sense:search]{query: "$외부 맛집"}',
    '[table:each]{items: [{vid:"example"}], '
    'do:"[sense:search]{query: \'$외부 $it.vid\'}"}',
    '[self:write]{path: "/tmp/x", content: "$file:0"}',
])
def test_parameter_dependencies_and_files_are_not_standalone(source):
    # 파싱 성공만으로 닫힌 코드라고 판단하면 변수/첨부파일 의존이 숨어 들어온다.
    assert code_syntax_error(source) is None
    code, why = _recover_distill_selection("x", "broken", "bad", [source],
        lambda **kw: '{"call_ids": [1]}')
    assert code is None and ("외부 변수" in why or "files" in why)


def _arm(monkeypatch, tmp_path, replies):
    import ibl_usage_db
    import ibl_usage_rag as rag
    import hippo_tree
    import thread_context

    stored, requested, runs = [], [], []
    class DB:
        @classmethod
        def hippo_disabled(cls):
            return False

        def add_example(self, **kw):
            stored.append(kw)
            return 1

    monkeypatch.setattr(ibl_usage_db, "IBLUsageDB", DB)
    monkeypatch.setattr(thread_context, "get_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(thread_context, "clear_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(hippo_tree, "map_text", lambda: "- 시험 (3)")
    monkeypatch.setattr(hippo_tree, "settle_topic", lambda topic: (topic, ""))
    monkeypatch.setattr(hippo_tree, "note_run", lambda *a, **kw:
                        runs.append(a) or {"success": True, "sentences": len(a[2])})
    monkeypatch.setattr(rag, "IBLUsageRAG", lambda: types.SimpleNamespace(clear_cache=lambda: None))
    # 학습 JSON도 임시 경로에 — 실사용 메모리·파일에는 접촉하지 않는다.
    monkeypatch.setattr(rag, "__file__", str(tmp_path / "backend/cognition/ibl_usage_rag.py"))
    (tmp_path / "data/training").mkdir(parents=True)
    outputs = iter(replies)
    def ask(**kw):
        requested.append(kw)
        return json.dumps(next(outputs), ensure_ascii=False)
    monkeypatch.setitem(sys.modules, "consciousness_agent", types.SimpleNamespace(oneshot_ai_call=ask))
    return rag, stored, requested, runs


@pytest.mark.parametrize("source,broken", CASES, ids=["ep3219", "ep3223", "ep3224"])
def test_recovery_reaches_db_and_training_file(monkeypatch, tmp_path, source, broken):
    rag, stored, asked, _ = _arm(monkeypatch, tmp_path, [
        {"intent": "실행 원문 패턴", "code": broken, "topic": "시험"}, {"call_ids": [1]},
    ])
    calls = [{"tool_name": "execute_ibl", "input": {"code": source}, "success": True}]
    assert rag.distill_experience("원문 패턴", calls, 0.0)
    assert len(asked) == 2 and len(stored) == 1
    assert stored[0]["ibl_code"] == source
    assert stored[0]["alias"] == ""  # 자동 함수 작명은 계속 중단
    training = json.loads((tmp_path / "data/training/ibl_distilled.json").read_text())
    assert training[0]["ibl_code"] == source


def test_checks_and_failures_never_become_source_or_runs(monkeypatch, tmp_path):
    good, broken = CASES[0]
    rag, stored, asked, runs = _arm(monkeypatch, tmp_path, [
        {"intent": "기억 읽기", "code": broken, "topic": "시험"}, {"call_ids": [1]},
    ])
    calls = [
        {"tool_name": "execute_ibl", "input": {"code": '[self:time]', "check": True}, "success": True},
        {"tool_name": "execute_ibl", "input": {"code": '[self:list]'}, "success": False},
        {"tool_name": "execute_ibl", "input": {"code": good}, "success": True},
        {"tool_name": "execute_ibl", "input": {"code": '[self:time]'}, "success": True},
    ]
    assert rag.distill_experience("기억 읽기", calls, 0.0)
    assert '[self:list]' not in asked[0]["prompt"]
    assert len(runs) == 1 and runs[0][2] == [good, '[self:time]']
    assert stored[0]["ibl_code"] == good


def test_check_only_does_not_call_model(monkeypatch, tmp_path):
    rag, stored, asked, _ = _arm(monkeypatch, tmp_path, [])
    assert not rag.distill_experience("x", [{"tool_name": "execute_ibl",
        "input": {"code": '[self:time]', "check": True}, "success": True}], 0.0)
    assert asked == stored == []


def test_healthy_distill_has_no_extra_model_call(monkeypatch, tmp_path):
    good = '[self:time]'
    rag, stored, asked, _ = _arm(monkeypatch, tmp_path, [{"intent": "현재 시간 확인", "code": good}])
    assert rag.distill_experience("시간", [{"tool_name": "execute_ibl",
        "input": {"code": good}, "success": True}], 0.0)
    assert len(asked) == len(stored) == 1


def test_recovery_preserves_independent_statements_and_parameter_gate(monkeypatch, tmp_path):
    for idx, sources in enumerate([
        ['[sense:search]{query: "x"} >> [table:take]{n: 1}', '[self:read]{path: "/tmp/x"}'],
        ['[sense:search]{made_up_parameter_xyz: "x"}'],
    ]):
        rag, stored, asked, _ = _arm(monkeypatch, tmp_path / str(idx), [
            {"intent": "x", "code": 'broken'}, {"call_ids": list(range(1, len(sources) + 1))},
        ])
        calls = [{"tool_name": "execute_ibl", "input": {"code": c}, "success": True} for c in sources]
        assert bool(rag.distill_experience("x", calls, 0.0)) is (idx == 0)
        assert len(asked) == 2
        assert bool(stored) is (idx == 0)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
