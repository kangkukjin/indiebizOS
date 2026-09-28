"""Research publication counts and crawl barriers, without external/model calls."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from common.pkg_utils import load_sibling
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'data/packages/installed/tools/web/handler.py'
BARRIER = ('Prove your humanity\n\nWe’re committed to safety and security. But not for bots. '
           'Complete the challenge below and let us know you’re a real person.\n\n'
           'Reddit, Inc. © "2026". All rights reserved.\n\n'
           'User Agreement Privacy Policy Content Policy Help')


@pytest.fixture(scope='module')
def registry():
    from ibl_v2_adapters import load_registry
    return load_registry(str(ROOT))


def row(id='one', **changes):
    return dict(event_id=id, verified=True, label='NEW', date='2026-09-24', **changes)


@pytest.mark.parametrize('rows,expected', [
    ([], 0),
    ([row()], 1),
    ([row(), row()], 1),
    ([{**row(), 'verified': False}], 0),
    ([{**row(), 'label': 'CHANGED'}], 0),
    ([{**row(), 'date': '2026-09-13'}, {**row('future'), 'date': '2026-09-29'}], 0),
    ([{**row('lower'), 'date': '2026-09-14'}, {**row('upper'), 'date': '2026-09-28'}], 2),
    ([row(str(i)) for i in range(5)] + [row('0')], 5),
])
def test_actual_guide_gate_counts_rows_and_date_window(registry, rows, expected):
    text = (ROOT / 'data/guides/ai_trend_report.md').read_text()
    code = next(code for code in re.findall(r'```ibl\n(.*?)```', text, re.S) if '$선별=' in code)
    inputs = {'사건들': rows, '하한': '2026-09-14', '오늘': '2026-09-28'}
    plan = compile_program(code, registry, inputs=inputs)
    out = Runtime(plan, inputs=inputs).run()
    assert out['success'], out
    assert out['value']['new_count'] == len(out['value']['events']) == expected
    assert out['value']['publish'] is (expected > 0)
    assert not any(w['code'] == 'RECORD_LENGTH' for w in plan.report()['warnings'])


def test_missing_date_is_failure_not_a_valid_empty_scan(registry):
    text = (ROOT / 'data/guides/ai_trend_report.md').read_text()
    code = next(code for code in re.findall(r'```ibl\n(.*?)```', text, re.S) if '$선별=' in code)
    item = row()
    item.pop('date')
    inputs = {'사건들': [item], '하한': '2026-09-14', '오늘': '2026-09-28'}
    out = Runtime(compile_program(code, registry, inputs=inputs), inputs=inputs).run()
    assert not out['success']


@pytest.mark.parametrize('bad', [{}, {'event_id': ''}])
def test_missing_or_empty_event_id_cannot_be_counted(registry, bad):
    text = (ROOT / 'data/guides/ai_trend_report.md').read_text()
    code = next(code for code in re.findall(r'```ibl\n(.*?)```', text, re.S) if '$선별=' in code)
    item = row()
    item.pop('event_id')
    item.update(bad)
    inputs = {'사건들': [row(), item], '하한': '2026-09-14', '오늘': '2026-09-28'}
    out = Runtime(compile_program(code, registry, inputs=inputs), inputs=inputs).run()
    assert not out['success']


def test_unsafe_gate_warns_before_execution_and_retains_record_len(registry, monkeypatch, tmp_path):
    from supervision_store import TurnStore
    from ibl_result_transport import provider_tool_result
    import model_result_view as view
    monkeypatch.setattr(view, 'evidence_store', lambda: TurnStore(tmp_path))
    code = ('$x=$rows >> [table:filter]{where:($r)=>$r.verified} >> [table:dedup]{by:"event_id"}; '
            'return {wrong:len($x),gate:len($x)>0,actual:len($x.items)}')
    plan = compile_program(code, registry, inputs={'rows': []})
    warnings = plan.report()['warnings']
    assert any(w['code'] == 'RECORD_LENGTH' and 'len(값.items)' in w['hint'] for w in warnings)
    out = Runtime(plan, inputs={'rows': []}).run()
    assert out['success'] and out['value'] == {'wrong': 3, 'gate': True, 'actual': 0}
    delivered = json.loads(provider_tool_result(json.dumps(view.project_v2_result(out), ensure_ascii=False)))
    assert any(w['code'] == 'RECORD_LENGTH' for w in delivered['precheck_warnings'])


@pytest.mark.parametrize('value,expected,warns', [
    ({'items': [], 'count': 0, 'success': True}, 3, True),
    ({'items': 'a field named items', 'other': 2}, 2, True),
    ({'a': 1}, 1, True), ([], 0, False), ('hello', 5, False),
])
def test_length_semantics_and_warning_scope(value, expected, warns):
    plan = compile_program('return len($x)', {}, inputs={'x': value})
    assert not plan.issues
    assert bool(plan.report()['warnings']) is warns
    assert Runtime(plan, inputs={'x': value}).run()['value'] == expected


def test_human_challenge_escalates_and_is_not_cached(monkeypatch, tmp_path):
    crawler = load_sibling(WEB, 'tool_webcrawl')
    from common import spill
    monkeypatch.setattr(spill, '_root', lambda: str(tmp_path))
    requests = []
    def get(url):
        requests.append(url)
        html = '<html><title>Reddit</title><body>' + BARRIER + '</body></html>'
        return SimpleNamespace(status_code=200, url=url, content=html.encode(),
                               headers={'content-type': 'text/html'}, encoding='utf-8')
    monkeypatch.setattr(crawler, '_http_get', get)
    monkeypatch.setattr(crawler, '_get_chrome_driver', lambda: None)
    monkeypatch.setattr(crawler, '_get_browser_session', lambda: None)
    for _ in range(2):
        out = crawler.crawl_website('https://example.test/thread')
        assert out['success'] is False and out['reason'] == 'bot_blocked'
        assert 'source_ref' not in out
    assert len(requests) == 2


@pytest.mark.parametrize('body', [
    'An article quotes "Prove your humanity" and "Complete the challenge" for a real person. ' * 3,
    'Prove your humanity\n\nA short essay about being kind to others. ' * 5,
    BARRIER + '\nAn actual long discussion about human verification. ' * 30,
])
def test_challenge_topic_is_not_a_barrier(body):
    crawler = load_sibling(WEB, 'tool_webcrawl')
    assert crawler._diagnose(200, 'https://x.test', 'https://x.test', body, 'Article') is None


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
