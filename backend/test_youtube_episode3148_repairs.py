"""ep3148 실제 실패 경로: 바깥 변수→지연 do, 자막→근거→시간, 식 오류 처방."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from ibl_boundary_probe import probe
from ibl_boundary_cases import literal as q
from ibl_boundary_cases_round3 import each


@pytest.mark.parametrize('value', [
    "'그 음성이 말한 문장'을 함께 넣어라 (ref_text)", 'say "yes"',
    '첫줄\n다음줄\\경로', '$it.missing', '{{_step_0_result.items}}',
    0, False, None, {'v': ["a'b", '$child.id']}, ['서울', '007'],
])
@pytest.mark.parametrize('shape', ['single', 'double', 'unquoted', 'nested_list'])
def test_outer_pipeline_data_is_safe_in_delayed_code(value, shape):
    ref = '${기존.items.*.tip}'
    if shape in ('single', 'nested_list'):
        ref = "'" + ref + "'"
    elif shape == 'double':
        ref = '"' + ref + '"'
    body = '[table:take]{items:[{known:' + ref + '}],n:1}'
    if shape == 'nested_list':
        body = each([{}], [body])
    code = '$기존=[table:take]{items:' + q([{'tip': value}]) + ',n:1}\n' + each([{}], body)
    r = probe(dict(id='outer_data', code=code, expected=[{'known': [value]}], error=False, contains=None))
    assert r['ok'], r


def test_outer_data_inside_prose_keeps_string_and_current_row():
    body = '[table:take]{items:[{v:"앞 ${기존.items.*.tip} 끝",id:$it.id}],n:1}'
    value = "'quote' $it.id"
    code = '$기존=[table:take]{items:' + q([{'tip': value}]) + ',n:1}\n' + each([{'id': 9}], body)
    expected = [{'v': '앞 ' + json.dumps([value], ensure_ascii=False) + ' 끝', 'id': 9}]
    r = probe(dict(id='outer_prose', code=code, expected=expected, error=False, contains=None))
    assert r['ok'], r


def test_numeric_each_alias_cannot_shadow_a_compiled_step_index():
    body = each([{}], '[table:take]{items:[{v:"${기존.items.0.tip}"}],n:1}', **{'as': '0'})
    code = '$기존=[table:take]{items:[{tip:"outer"}],n:1}\n' + each([{}], body)
    r = probe(dict(id='numeric_alias', code=code, expected=[{'v': 'outer'}], error=False, contains=None))
    assert r['ok'], r


@pytest.fixture
def struct(monkeypatch):
    import oneshot_facade
    handler = ROOT / 'data/packages/installed/tools/ai-ops/handler.py'
    spec = importlib.util.spec_from_file_location('_ep3148_struct', handler)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    calls = []

    def run(params, rows):
        def model(prompt, system, **kw):
            calls.append((prompt, system))
            return [dict(r) for r in rows], None
        monkeypatch.setattr(oneshot_facade, 'oneshot_json', model)
        return json.loads(mod._struct({'schema': 'tip, timestamp(MM:SS)', 'grounded': True, **params}))
    return mod, run, calls


@pytest.mark.parametrize('entry', ['inline', 'file', 'envelope_file', 'external', 'spill'])
def test_timestamp_is_recovered_from_source_without_model_timestamp(struct, tmp_path, monkeypatch, entry):
    mod, run, calls = struct
    text = '도입이다. 설정을 바꾸면 지연이 줄어든다. 마지막 설명이다.'
    segments = [{'start': 0, 'text': '도입이다.'},
                {'start': 12.8, 'text': '설정을 바꾸면 지연이 줄어든다.'},
                {'start': 70, 'text': '마지막 설명이다.'}]
    env = {'transcript': text, 'segments': segments, 'items': segments}
    path = tmp_path / 'transcript.txt'
    path.write_text('# 제목\n[00:00] 도입이다.\n[00:12] 설정을 바꾸면 지연이 줄어든다.\n[01:10] 마지막 설명이다.\n')
    if entry == 'file':
        params = {'file': str(path)}
    elif entry in ('external', 'envelope_file'):
        env = {'saved_to_file': True, 'file_path': str(path), 'preview': '짧은 미리보기'}
        if entry == 'envelope_file':
            envelope = tmp_path / 'source.json'
            envelope.write_text(json.dumps(env))
            params = {'file': str(envelope)}
        else:
            params = {'_prev_result': env}
    elif entry == 'spill':
        from common import spill
        monkeypatch.setattr(spill, '_root', lambda: str(tmp_path))
        params = {'_prev_result': spill.spill_write(json.dumps(env))}
    else:
        params = {'_prev_result': env}
    out = run(params, [{'tip': '설정 변경', '_quote': '설정을 바꾸면', 'timestamp': '99:59'}])
    assert out['success'], out
    assert out['items'][0]['timestamp'] == '00:12'
    assert out['timestamp_grounded'] == 1 and len(calls) == 1


@pytest.mark.parametrize('segments,quote,expected,reason', [
    ([(12, '첫 구절'), (20, '둘째 구절')], '첫 구절 둘째', '00:12', None),
    ([(12, '같은 말'), (20, '같은 말')], '같은 말', None, 'ambiguous_quote'),
    ([(12, '같은 말 같은 말')], '같은 말', '00:12', None),
    ([(12, '있는 말')], '없는 말', None, 'unmatched_quote'),
    ([], '있는 말', None, 'no_source_time'),
    ([(3661, '시간 넘긴 구절')], '시간 넘긴', '61:01', None),
])
def test_timestamp_never_guesses_an_ambiguous_location(struct, segments, quote, expected, reason):
    mod, _, _ = struct
    rows = [{'_quote': quote, 'timestamp': '00:00'}]
    mod._ground_timestamps(rows, segments)
    assert rows[0]['timestamp'] == expected
    assert rows[0].get('_timestamp_error') == reason


def test_missing_source_time_is_explicit_and_does_not_drop_record(struct):
    _, run, _ = struct
    out = run({'text': '설정을 바꾸면 지연이 줄어든다.'}, [{'tip': '설정 변경', '_quote': '설정을 바꾸면'}])
    assert out['success'] and out['count'] == 1 and out['missing_timestamp'] == 1
    assert out['items'][0]['timestamp'] is None
    assert out['items'][0]['_timestamp_error'] == 'no_source_time'


def test_compute_contains_prescription_executes():
    code = '[table:compute]{items:[{tip:"툴 콜 상한"},{tip:"다른 팁"}],set:{v:"contains(tip, \'툴 콜\')"}}'
    expected = [{'tip': '툴 콜 상한', 'v': True}, {'tip': '다른 팁', 'v': False}]
    assert probe(dict(id='contains', code=code, expected=expected, error=False, contains=None))['ok']


@pytest.mark.parametrize('expr,hint', [("'툴 콜' in tip", 'contains('), ("{'id': 1}", 'self:script')])
def test_compute_rejects_unsupported_syntax_with_specific_remedy(expr, hint):
    from common.safe_expr import compile_expr
    with pytest.raises(ValueError, match=__import__('re').escape(hint)):
        compile_expr(expr)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
