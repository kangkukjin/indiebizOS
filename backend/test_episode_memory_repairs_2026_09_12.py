"""ep3592~3595: 데이터 속 호출 계수·전달문 귀속·긴 실행 원문 노출·items/표 이중 봉투."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401 — 직접 실행에서도 층 경로를 등록한다.
from cognitive_trace import ibl_call_cost
from memory_evidence import durable_source_units, grounded_fact
from memory_provenance import source_summary
import hippo_tree
from ibl_usage_rag import IBLUsageRAG, _top_for_execution


def test_call_metrics_ignore_sql_report_comments_and_deferred_strings():
    code = ('[self:query]{sql:"select count(*) where code like \'%[fn:%\'"}\n'
            '[self:write]{content:"[fn:引用] >> [table:take]"}\n'
            '# [fn:comment]\n[fn:실제]{}')
    c = ibl_call_cost([{"tool_name": "execute_ibl", "input": {"code": code}}])
    assert c["fn_calls"] == 1 and c["single"] == 0
    c = ibl_call_cost([{"tool_name": "execute_ibl", "input": {
        "code": '[self:query]{sql:"select \'[fn:demo]\'"}'}}])
    assert c["fn_calls"] == 0 and c["single"] == 1


def test_forwarded_answer_cannot_become_user_preference():
    text = '맞습니다. **새로운 설계와 좋은 구현은 다른 평가 대상입니다.**\n\n' + ('기초를 평가해야 합니다. ' * 45)
    text += '\n\n앞으로 비교에서 먼저 물어야 할 것은 이것입니다.'
    units = durable_source_units(text)
    assert units and not any(u["eligible"] for u in units)
    for u in units:
        assert grounded_fact({"source_ids": [u["id"]], "retention": "user_preference",
                              "future_use": "향후 비교 기준"}, units, '{}', durable_only=True) is None


def test_quote_fence_and_explicit_user_adoption():
    units = durable_source_units('> 나는 중고를 사지 않는다.\n\n```text\n나는 신품만 산다.\n```\n\n나는 이 제안을 채택해서 앞으로 신품만 사겠다.')
    eligible = [u for u in units if u["eligible"]]
    assert len(eligible) == 1 and eligible[0]["text"].startswith('나는 이 제안을')
    own = durable_source_units('나는 앞으로도 중고 제품은 사지 않을 거야.')
    assert own[0]["eligible"]
    assert source_summary({"evidence": [{"role": "user", "attribution": "quoted"}]})["status"] == 'external_record'


def test_long_single_artifact_is_hidden_but_source_is_preserved():
    code = '[self:write]{path:"report.md",content:' + json.dumps('과거 결론 ' * 400, ensure_ascii=False) + '}'
    ex = SimpleNamespace(id=123, intent='보고서 작성', score=.99, ibl_code=code,
                         success_rate=-1, topic='연구', alias='')
    rag = IBLUsageRAG.__new__(IBLUsageRAG)
    xml = rag._format_references([ex])
    assert '과거 결론' not in xml and 'expand: "#123"' in xml and 'node: "연구"' in xml
    assert 'body_omitted="true"' in xml
    assert _top_for_execution([ex]) == (.8, '')
    assert ex.ibl_code == code  # 명시 expand를 위한 원본은 그대로
    hidden = hippo_tree._hide_body({"id": 123, "ibl_code": code})
    assert '과거 결론' not in hidden['ibl_code']
    ex.ibl_code = '[table:take]{n:3}'
    assert ex.ibl_code in rag._format_references([ex])
    assert _top_for_execution([ex]) == (.99, ex.ibl_code)


def _ops():
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/data-ops/handler.py'
    spec = importlib.util.spec_from_file_location('_episode_dataops', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_items_win_over_translated_display_table():
    ops = _ops()
    dual = {"items": [{"name": "a.md", "path": "/a.md", "mtime": "2026-09-12", "size": 3}],
            "table": {"columns": ["이름", "경로", "수정일", "크기"], "rows": [["a.md", "/a.md", "2026-09-12", 3]]}}
    bad = ops._op_select(dual, {"columns": ["path", "name", "modified", "size"]})
    assert bad['success'] is False and 'mtime' in bad['error'] and 'modified' in bad['error']
    good = ops._op_select(dual, {"columns": ["path", "name", "mtime", "size"]})
    assert good['items'] == dual['items']
    assert not ops._explicit_table({"items": [], "table": dual['table']})
    assert ops._explicit_table({"table": dual['table']})
    table = ops._op_select({"table": dual['table']}, {"columns": ["이름"]})
    assert table['table']['columns'] == ['이름']


def test_filter_expression_error_teaches_working_recovery():
    ops = _ops()
    data = {"items": [{"text": 'x' * 201}, {"text": 'x'}]}
    bad = ops._op_filter(data, {"where": "len(text)>200"})
    assert bad['success'] is False and 'compute' in bad['error']
    computed = ops._op_compute(data, {"set": {"문자수": "len(text)"}})
    good = ops._op_filter(computed, {"where": "문자수 > 200"})
    assert len(good['items']) == 1 and good['items'][0]['문자수'] == 201


def test_forage_owner_requires_user_evidence(monkeypatch):
    from cognitive_distill import CognitiveDistillMixin
    saved = []
    monkeypatch.setattr('runtime_utils.detect_body', lambda: {"profile": "pc"})
    monkeypatch.setitem(sys.modules, 'forage_memory', SimpleNamespace(
        recall=lambda **kw: {"map": [], "owner": []},
        note_owner=lambda **kw: saved.append(kw) or {"success": True, "action": "added"}))
    monkeypatch.setattr('consciousness_agent.oneshot_ai_call', lambda **kw: json.dumps({
        "space": "mac", "map": [], "owner": [
            {"facet": "identity", "value": "검증을 중시하는 연구자"},
            {"facet": "habit", "value": "모델이 재작성한 추측", "source_ids": [1]}]}))
    own = '나는 자료를 연도별 폴더로 정리한다.'
    CognitiveDistillMixin()._distill_forage_memory(own, '/tmp/papers 폴더를 확인했습니다.', assume_forage=True)
    assert len(saved) == 1 and saved[0]['value'] == own
    assert saved[0]['provenance']['evidence'][0]['text'] == own
    CognitiveDistillMixin()._distill_forage_memory('> ' + own, '/tmp/papers 폴더를 확인했습니다.', assume_forage=True)
    assert len(saved) == 1


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


# ── 2026-09-16 ep3813: 전달문 귀속 — 주인에게 말을 거는 글은 저자가 누구든 주인의 자기 진술이 아니다 ──
_EP3813_HEAD = ('직접 보고 말씀드리겠습니다. 사이트를 열어 보겠습니다.\n\n'
                '전부 열어 봤습니다. 홈, 뉴스, 학교, 커뮤니티까지 확인했습니다.\n\n'
                '먼저 결론입니다. content-shop 에서 스스로 짚으신 문제를 정확히 뒤집었습니다. '
                '출처와 발행일을 모르면 미확인이라고 적는 정직함도 좋습니다.')


def test_addressed_document_is_conveyed_not_owner_evidence():
    units = durable_source_units(_EP3813_HEAD)
    assert units and not any(u["eligible"] for u in units)
    assert {u["attribution"] for u in units} == {"conveyed"}
    assert {u["basis"] for u in units} == {"addressed_to_owner"}
    # 전달문 뒤에 붙인 짧은 채택 선언만 주인의 목소리로 남는다.
    mixed = durable_source_units(_EP3813_HEAD + '\n\n나는 이 평가에 동의해. 앞으로 책 카드는 빼겠어.')
    assert [u["text"] for u in mixed if u["eligible"]] == ['나는 이 평가에 동의해.', '앞으로 책 카드는 빼겠어.']
    assert all(u["basis"] == "user_statement" for u in mixed if u["eligible"])
    assert source_summary({"evidence": [{"role": "user", "attribution": "conveyed"}]})["status"] == 'external_record'


def test_long_formal_document_is_unresolved_but_short_own_words_stay():
    doc = ('사이트 구조를 살펴본 결과입니다.\n\n'
           + '첫째 축은 질문입니다. 둘째 축은 매체입니다. 셋째로 저자 이름은 바이라인으로 내려갑니다. ' * 12
           + '\n\n결론은 재구성이 필요하다는 것입니다.')
    assert len(doc) >= 600
    units = durable_source_units(doc)
    assert units and not any(u["eligible"] for u in units)
    assert {u["basis"] for u in units} == {"formal_document"}
    own = durable_source_units('컨텐츠도 필요하지만 사이트를 잘 만드는 것도 필요하지. 지금은 일단 사이트 개발이 첫째라고 봐.')
    assert all(u["eligible"] and u["basis"] == "user_statement" for u in own)
