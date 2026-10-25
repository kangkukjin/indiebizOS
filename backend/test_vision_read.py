"""진단이 달라도 같은 화면이 실제 검수에 도달하는지 확인한다."""
import base64
import json

import pytest
from PIL import Image

from test_render_prescreen_contract import gv, ra, needs_browser


@needs_browser
def test_identical_pixels_with_console_diagnostic_reach_vision(ra, gv, tmp_path, monkeypatch):
    calls = []
    def inspect(prompt, **kwargs):
        calls.append((prompt, kwargs['images']))
        return json.dumps({'passed': True, 'score': 9, 'issues': [], 'notes': '읽음'})
    monkeypatch.setattr(gv, '_ai_call', inspect)
    rows = []
    for index, script in enumerate(['', "<script>console.error('Optional analytics disabled')</script>"]):
        source = tmp_path / f'{index}.html'
        source.write_text('<body><h1>Report</h1><p>Revenue 100</p>' + script + '</body>')
        result = json.loads(ra.render_op_html({'path': str(source), 'viewports': ['800x600']},
                                            output_base=str(tmp_path)))
        row = result['items'][0]
        rows.append(row)
        outcome = gv.critique_image({'path': row['path'], 'intent': 'Report and Revenue 100',
                                     'prescreen': row['prescreen']}, str(tmp_path))
        assert outcome['passed'] is True and outcome['tier'] == 'vision'
    assert not rows[0]['prescreen'] and rows[1]['prescreen']
    with Image.open(rows[0]['path']) as left, Image.open(rows[1]['path']) as right:
        assert left.convert('RGB').tobytes() == right.convert('RGB').tobytes()
    assert len(calls) == 2
    assert 'Optional analytics disabled' in calls[1][0]
    for _, images in calls:
        assert base64.b64decode(images[0]['base64'])


@pytest.mark.parametrize('content', [None, b'not an image'])
def test_unreadable_image_is_not_a_quality_verdict(gv, tmp_path, monkeypatch, content):
    path = tmp_path / 'bad.png'
    if content is not None:
        path.write_bytes(content)
    monkeypatch.setattr(gv, '_ai_call', lambda *a, **k: pytest.fail('unreadable image sent to model'))
    result = json.loads(gv.critique_image({'path': str(path), 'intent': '검수',
                                          'prescreen': '콘솔 오류'}, str(tmp_path)))
    assert result['success'] is False and result['error']
    assert 'score' not in result and 'passed' not in result


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
