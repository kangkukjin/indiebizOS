"""선정 관용구의 호출/조합 검증. 실제 파서·함수·파이프·변환자·파일 도구;
외부 웹/AI만 고정 응답, 해마 귀속은 메모리로 격리한다.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
import workflow_store  # 시험 대역도 저장소 소유자에 설치한다.

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from curate_idioms import validate_catalog

CATALOG = json.loads((ROOT / 'data/idioms/curated.json').read_text())
ENTRIES = {e['name']: e for e in CATALOG['idioms']}


def test_catalog_checks_signatures_and_composed_examples():
    assert set(validate_catalog(CATALOG)) == set(ENTRIES)
    broken = json.loads(json.dumps(CATALOG))
    broken['idioms'][0]['example'] = '[fn:중복빼고추리기]{키: "id"}'
    with pytest.raises(ValueError, match='인자'):
        validate_catalog(broken)


def test_semicolon_body_is_recognized(monkeypatch):
    import fn_recognizer as f
    body = ENTRIES['중복빼고추리기']['body'].replace('\n', '; ')
    monkeypatch.setattr(f, '_aliased_shapes', lambda: {f.shape(body): '중복빼고추리기'})
    assert len(f.statements(body)) == 2
    assert f.fn_hint_for(body)['alias'] == '중복빼고추리기'
    assert len(f.statements('[self:read]{path: "a;b"}')) == 1


def test_prompt_shows_executable_call_and_composition():
    from ibl_access import _idiom_lines
    from workflow_contract import call_signature
    e = ENTRIES['중복빼고추리기']
    row = (e['when'], e['body'], 0, 0, e['topic'], e['name'], 'items', ' '.join(call_signature(e['body'])))
    card = '\n'.join(_idiom_lines(row, e))
    assert '[fn:중복빼고추리기]{키: "…", 개수: "…"}' in card
    assert '앞 통화: items' in card and e['example'] in card


















if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
