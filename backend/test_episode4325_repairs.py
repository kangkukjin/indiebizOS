"""ep4325 — 보완 증거가 재검수에 닿지 않던 통로와 잘린 관용구 결과의 성공 기록을 검증한다."""
import json
import sys

import pytest
import boot_paths  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401


def test_repair_tool_results_reach_the_recheck_in_full(supervisor):
    from final_evaluator import prepare
    store = supervisor.store
    store.put_response("대조 완료")
    before = store.evidence("보완 전 결과")
    store.log("tool.finished", role="execution", name="execute_ibl", evidence=before, is_error=False)
    supervisor._repair_evidence_since = store.sequence
    table = json.dumps({"success": True, "value": [{"row": i, "pad": "x" * 900} for i in range(8)],
                        "value_wire": {"data": "y" * 9000}}, ensure_ascii=False)
    made = store.evidence(table)
    store.log("tool.finished", role="execution", name="execute_ibl", evidence=made, is_error=False)
    failed = store.evidence("실패한 호출")
    store.log("tool.finished", role="execution", name="execute_ibl", evidence=failed, is_error=True)
    read = store.evidence("작업대 증거 페이지")
    store.log("response.operation", role="execution", operation="evidence", result=read, is_error=False)
    recovered = prepare(supervisor, [])["context"]["recovered_evidence"]
    assert len(recovered) == 2 and recovered[1] == "작업대 증거 페이지"
    assert '"row": 7' in recovered[0] and "value_wire" not in recovered[0]


def test_recovered_evidence_budget_prefers_latest(supervisor):
    from final_evaluator import recovered_pages
    store = supervisor.store
    old, new = store.evidence("a" * 5000), store.evidence("b" * 5000)
    pages = recovered_pages(store, [old["id"], new["id"]], budget=6000)
    assert pages[-1] == "b" * 5000
    assert len(pages[0]) < 5000 and "첨부" in pages[0]


def test_truncated_idiom_result_is_not_scored_as_success(monkeypatch):
    import ibl_function_result as fr
    from function_library import register, record_legacy_call
    from function_store import resolve
    from capability_history import function_statistics
    events = []
    monkeypatch.setattr("episode_logger.record_trajectory_event", lambda kind, row: events.append(row))
    ref = register('result', '$return=1', edition=1)
    row = resolve('result', edition=1)
    cut = {"success": True, "items": [1], "truncated": True,
           "truncations": [{"scope": "source", "reason": "일치 줄 본문 절단"}]}
    assert fr.source_partial(cut)
    record_legacy_call(row, cut)
    assert function_statistics(ref)['success_count'] == 0
    assert events[-1]['source_complete'] is False
    sample = {"success": True, "items": [1], "truncations": [{"scope": "selection", "reason": "limit"}]}
    assert not fr.source_partial(sample)
    record_legacy_call(row, sample)
    assert function_statistics(ref)['success_count'] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
