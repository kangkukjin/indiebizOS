"""작성 규칙의 일관성: 실제 엔진·검수기와 저장/추출 경계를 외부 호출 없이 검사."""
import importlib.util
import json
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from test_ibl_expression_revision_2026_09_08 import run
from test_struct_body_seam import aiops  # noqa: F401 — 원샷/원문 추출 스텁
from common.record_schema import schema_fields, records_schema_error
from common.safe_expr import compile_expr, eval_expr
from api_ibl import validate_code

ROOT = Path(__file__).resolve().parents[1]












@pytest.mark.parametrize('expr,expected', [
    ('id', '007'), ('str(id)', '007'), ('[id,n]', ['007', '3']),
    ('{id:id, flags:[true,false,null]}', {'id': '007', 'flags': [True, False, None]}),
    ('n*2', 6), ('col("n")+1', 4), ('[n][0]*2', 6),
    ('"1"+"2"', '12'), ('str(id)+"!"', '007!'),
])
def test_value_copy_and_numeric_observation(expr, expected):
    assert eval_expr(compile_expr(expr)[0], {'id': '007', 'n': '3'}) == expected




@pytest.mark.parametrize('schema,expected', [
    ('tip(한 문장, 쉼표 포함), timestamp(MM:SS)', ['tip', 'timestamp']),
    ('a(설명(중첩, 허용)), b', ['a', 'b']),
    ('finance', None), ('팁(tip)', None), ('설명이 여러 단어, 자연어', None),
])
def test_schema_uses_existing_field_descriptions(schema, expected):
    assert schema_fields(schema) == expected


def test_schema_checks_names_without_guessing_values():
    assert records_schema_error([{'tip': 'x', 'timestamp': None}], 'tip, timestamp') is None
    assert 'timestamp' in records_schema_error([{'tip': 'x'}], 'tip, timestamp')
    with pytest.raises(ValueError, match='두 번'):
        schema_fields('tip(제목), tip(본문)')


def test_schema_static_fields_and_runtime_missing_field(aiops, monkeypatch):
    mod, seen = aiops
    code = '$r = [self:struct]{schema:"tip(제목), when(날짜)",text:"원문"}\n$r.items >> [table:select]{columns:["tip","when"]}'
    check = validate_code('#!ibl edition=2\n'+code)
    assert check['valid'] and not check['issues'], check
    out = json.loads(mod._struct({'schema': 'tip(제목), when(날짜)', 'text': '원문'}))
    assert out['success'] is False and out['error_type'] == 'schema'
    assert 'when' in out['error']
    assert 'null' in seen['system']
    monkeypatch.setattr(sys.modules['oneshot_facade'], 'oneshot_json',
                        lambda *a: ([{'tip': 'x', 'when': None}], None))
    assert json.loads(mod._struct({'schema': 'tip, when', 'text': '원문'}))['success']


def test_ai_schema_applies_after_index_merge(aiops, monkeypatch):
    mod, seen = aiops
    calls = []
    def answer(*args):
        calls.append(args)
        return [{'_i': 0, 'selected': False, 'reason': None}], None
    monkeypatch.setattr(sys.modules['oneshot_facade'], 'oneshot_json', answer)
    params = {'items': [{'id': '007', 'title': 'x'}], 'instruction': '선정',
              'schema': 'id(보존), selected(불리언), reason(사유)'}
    out = json.loads(mod._transform(params))
    assert out['success'] and out['items'][0]['id'] == '007', out
    assert len(calls) == 1
    assert not json.loads(mod._transform({**params, 'fields': ['id']}))['success']
    assert len(calls) == 1  # 모순은 호출 전에 거절
    code = '$r = [table:ai]{items:[{id:"007"}],instruction:"선정",schema:"selected(불리언), reason(사유)"}\n$r.items >> [table:select]{columns:["id","selected","reason"]}'
    assert not validate_code('#!ibl edition=2\n'+code)['issues']


@pytest.fixture
def sink(monkeypatch):
    spec = importlib.util.spec_from_file_location('_learn_sink', ROOT / 'data/packages/installed/tools/system_essentials/sink_ops.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 파일 쓰기 자체만 실물, 운영 쓰기 원장은 이 오프라인 시험에서 남기지 않는다.
    import write_ledger
    monkeypatch.setattr(write_ledger, 'log_write', lambda *a, **k: None)
    def write(prev, path):
        return json.loads(mod.write_sink({'_prev_result': prev, 'format': 'json'}, str(path), str(path), False,
                                        _red_write_prepare=lambda *a: None,
                                        _red_write_finalize=lambda *a: None,
                                        _vocab_enforce=lambda *a: None))
    return write


@pytest.mark.parametrize('shape', ['short', 'long', 'spill'])
def test_source_roundtrip_survives_original_cache_removal(shape, aiops, sink, tmp_path, monkeypatch):
    mod, seen = aiops
    body = '첫 번째 조작 팁은 로그를 확인한다. 둘째 조작 팁은 검증한다.'
    rows = [{'start': 12, 'text': body}]
    prev = {'transcript': body, 'items': rows, 'segments': rows, 'language': 'ko',
            'video_id': '007', 'title': '원문', 'warning': '이전 실행 경고'}
    original = None
    if shape == 'long':
        body += ' 추가 설명도 원문에 그대로 보존한다.' * 600
        rows = [{'start': 12, 'text': body}]
        original = tmp_path / 'original.txt'
        original.write_text('# 제목\n[00:12] ' + body, encoding='utf-8')
        prev = {'saved_to_file': True, 'file_path': str(original), 'items': rows,
                'preview': '일부만', 'language': 'ko', 'video_id': '007'}
    elif shape == 'spill':
        import common.spill as spill
        monkeypatch.setattr(spill, 'spill_dir', lambda: str(tmp_path))
        prev = spill.spill_write(json.dumps(prev, ensure_ascii=False), tag='learn')
        original = Path(prev['ref']['path'])
    saved = tmp_path / 'saved.json'
    assert sink(prev, saved)['success']
    if original:
        original.unlink()
    restored = json.loads(saved.read_text())
    assert restored['language'] == 'ko' and restored['video_id'] == '007'
    assert 'warning' not in restored and 'saved_to_file' not in restored
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('_learn_read', ROOT / 'data/packages/installed/tools/system_essentials/handler.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    read_result = reader.execute({'path': str(saved)}, SimpleNamespace(
        tool_name='read_op', project_path=str(tmp_path), agent_id=None))
    for params in ({'file': str(saved)}, {'_prev_result': read_result}):
        out = json.loads(mod._struct({'schema': 'tip, timestamp(MM:SS)', 'grounded': True, **params}))
        assert out['success'] and body in seen['prompt'], out
        assert '일부만' not in seen['prompt'] and '[00:12]' not in seen['prompt']


def test_missing_source_and_items_only_are_explicit_failures(aiops, sink, tmp_path):
    mod, seen = aiops
    prev = {'saved_to_file': True, 'file_path': str(tmp_path / 'missing.txt'),
            'preview': '조금만 남은 미리보기 ' * 30, 'items': []}
    assert not sink(prev, tmp_path / 'saved.json')['success']
    assert not (tmp_path / 'saved.json').exists()
    assert not json.loads(mod._struct({'schema': 'finance', '_prev_result': prev}))['success']
    assert not json.loads(mod._struct({'schema': 'finance', '_prev_result': {'items': [{'text': 'x'}]}}))['success']
    assert 'prompt' not in seen




def test_oversized_source_fails_before_model(aiops, tmp_path):
    mod, seen = aiops
    out = json.loads(mod._struct({'schema': 'finance', '_prev_result': {'text': '가' * 60001}}))
    assert not out['success'] and out['error_type'] == 'input_size'
    # 실제 원문 추출기의 절단 신고도 보존되는지 별도로 로드해 본다.
    spec = importlib.util.spec_from_file_location('_learn_ingest', ROOT / 'backend/services/ingest_engine.py')
    real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real)
    source = tmp_path / 'large.txt'
    source.write_text('가' * 60001)
    assert real.extract_source(path=str(source))['truncated']
    assert real.extract_source(text='가' * 60001)['source_chars'] == 60001
    assert 'prompt' not in seen


def test_source_without_items_is_also_snapshotted(sink, tmp_path):
    source = tmp_path / 'source.txt'
    source.write_text('파일 전문')
    saved = tmp_path / 'snapshot.json'
    assert sink({'saved_to_file': True, 'file_path': str(source)}, saved)['success']
    source.unlink()
    obj = json.loads(saved.read_text())
    assert obj['text'] == '파일 전문' and 'saved_to_file' not in obj


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
