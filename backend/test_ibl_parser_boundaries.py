"""공통 스캐너 도입 전 결과를 고정한 합성 경계 코퍼스. 실사용 코드·모델 호출 없음."""
import boot_paths  # noqa: F401
import importlib
import json
from pathlib import Path
import re

import pytest
from ibl_code_ir import CAPTURE

CASES = json.loads((Path(__file__).parent / 'testdata/ibl_parser_boundaries.json').read_text())
MODULES = {
    '_split_pipeline': 'ibl_parser', '_split_by_operator': 'ibl_parser',
    '_block_header': 'ibl_parser_blocks', '_find_top_level_key': 'ibl_parser_blocks',
    '_extract_bracket_raw': 'ibl_parser_blocks', '_scan_line_state': 'ibl_parser_values',
    '_strip_line_comment': 'ibl_parser_values', '_parse_params': 'ibl_parser_values',
    '_extract_bracket': 'ibl_parser_values',
}


def normalize(value):
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [normalize(item) for item in value]
    if isinstance(value, str) and hasattr(value, 'quoted'):
        return {'source': str(value), 'quoted': value.quoted}
    return value


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['function'] + ('-capture' if c['capture'] else ''))
def test_before_refactor_boundary_contract(case):
    fn = getattr(importlib.import_module(MODULES[case['function']]), case['function'])
    args = list(case['args'])
    if case['function'] == '_block_header':
        args[1] = re.compile(args[1])
    token = CAPTURE.set(case['capture'])
    try:
        try:
            result = {'value': normalize(fn(*args))}
        except Exception as exc:
            result = {'error': type(exc).__name__, 'message': str(exc)}
    finally:
        CAPTURE.reset(token)
    assert result == case['expected']


def test_json_fallback_and_capture_bypass_do_not_depend_on_optional_json5(monkeypatch):
    import pyjson5
    import ibl_parser_values as values
    calls = []

    def unavailable(text):
        calls.append(text)
        raise ImportError('optional decoder unavailable')

    monkeypatch.setattr(pyjson5, 'loads', unavailable)
    assert values._parse_params('{"a": [1, null]}') == {'a': [1, None]}
    assert values._extract_bracket('[1, true]', 0, '[', ']') == ([1, True], 9)
    assert calls == ['{"a": [1, null]}', '[1, true]']
    calls.clear()
    assert values._parse_params(r'{pattern:"\d+"}') == {'pattern': r'\d+'}
    token = CAPTURE.set(True)
    try:
        result = values._parse_params('{v:$item, literal:"$item"}')
        assert result['v'].quoted is False and result['literal'].quoted is True
    finally:
        CAPTURE.reset(token)
    # CAPTURE는 컨테이너 자동 해석을 우회하지만 인용된 단일 값의 디코딩은 유지한다.
    assert calls == ['"$item"']


@pytest.mark.parametrize('mode,count', [('until', 1), ('while', 2)])
@pytest.mark.parametrize('literal', [r'"a\",b"', r"'a\',b'"])
def test_repeat_header_preserves_escaped_quote_and_comma(mode, count, literal):
    from ibl_parser import parse
    from ibl_code_ir import compile_code
    from ibl_parser_blocks import _repeat_options
    header = f'{mode} {literal} == {literal}, max: 2, collect: true'
    options = _repeat_options(header)
    assert options['condition'] == f'{literal} == {literal}'
    assert options['max'] == 2 and options['collect'] is True
    code = '[repeat: ' + header + ']{[table:take]{items:[{n:1}],n:1}}'
    assert parse(code)[0]['condition'] == options['condition']
    assert compile_code(code).tree[0]['condition'] == options['condition']
    # 실제 제어 흐름까지 확인하되 도구는 외부 통신 없는 table:take만 사용한다.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from ibl_boundary_probe import probe
    result = probe(dict(id='repeat_escaped_quote', code=code, expected=[{'n': 1}] * count,
                        error=False, contains=None))
    assert result['ok'], (result.get('actual'), result.get('error_text'))


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
