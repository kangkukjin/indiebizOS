"""Complete current source selection and isolated distillation harness."""
import json
import sys
import types
import pytest
import boot_paths
from ibl_distill_gates import select_distill_source


def completed_call(source, **extra):
    from ibl_edition import explicit_source
    return {'tool_name': 'execute_ibl', 'input': {'code': explicit_source(source, 2)},
            'success': True, 'result': {'success': True, 'executed': True,
                                      'source_complete': True, 'edition': 2}, **extra}


def _arm(monkeypatch, tmp_path, replies):
    import ibl_usage_db
    import ibl_usage_rag as rag
    import hippo_tree
    import thread_context

    import ibl_distill_value
    monkeypatch.setattr(ibl_distill_value, "known_examples", lambda db: [])
    stored, requested, runs = [], [], []
    class DB:
        @classmethod
        def hippo_disabled(cls):
            return False

        def add_example(self, **kw):
            stored.append(kw)
            return 1

    monkeypatch.setattr(ibl_usage_db, "IBLUsageDB", DB)
    monkeypatch.setattr(thread_context, "get_goal_eval_outcome", lambda: {"achieved": True, "severity": 0})
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
        return json.dumps({"decision": "keep", "benefit": "검증된 조합으로 반복 탐색 생략",
                           "applicability": "같은 입력 구조의 자료 조회", **next(outputs)}, ensure_ascii=False)
    monkeypatch.setitem(sys.modules, "consciousness_agent", types.SimpleNamespace(oneshot_ai_call=ask))
    return rag, stored, requested, runs

@pytest.mark.parametrize('ids', [None, '1', [0], [2], [True], [1.0], [1, 1]])
def test_bad_selection_is_not_interpreted(ids):
    code, why = select_distill_source({'call_ids': ids}, ['#!ibl edition=2\nreturn 1'])
    assert code is None and why


def test_complete_source_is_selected_without_rewriting():
    source = '#!ibl edition=2\n$x=1\nreturn $x + 2'
    assert select_distill_source({'call_ids':[1]}, [source])[0] == source


def test_sources_are_not_spliced_to_recover_implicit_state():
    code, why = select_distill_source({'call_ids':[2]},
        ['#!ibl edition=2\n$x=1', '#!ibl edition=2\nreturn $x'])
    assert code is None and why
    assert select_distill_source({'call_ids':[1,2]}, ['return 1','return 2'])[0] is None


def test_selected_source_reaches_storage_and_training(monkeypatch,tmp_path):
    source = '#!ibl edition=2\n[table:take]{items:[{x:1},{x:2}],n:1}'
    rag,saved,asked,runs = _arm(monkeypatch,tmp_path,[{'intent':'목록 첫 행', 'source_ids':[1]}])
    assert rag.distill_experience('첫 행', [completed_call(source)], 0)
    assert len(saved)==len(asked)==1 and saved[0]['ibl_code']==source
    assert json.loads((tmp_path/'data/training/ibl_distilled.json').read_text())[0]['ibl_code']==source


@pytest.mark.parametrize('field', ['success','executed','source_complete'])
def test_missing_execution_evidence_never_calls_model(monkeypatch,tmp_path,field):
    rag,saved,asked,_ = _arm(monkeypatch,tmp_path,[])
    call=completed_call('return 1');call['result'].pop(field)
    assert not rag.distill_experience('x',[call],0)
    assert saved==asked==[]


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
