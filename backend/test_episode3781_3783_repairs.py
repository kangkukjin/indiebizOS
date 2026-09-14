"""Regression cases from the three architecture runs, without model/network calls."""
import asyncio
import base64
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401
from supervision_store import TurnStore


@pytest.fixture
def view(tmp_path, monkeypatch):
    import model_result_view
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr(model_result_view, 'evidence_store', lambda: store)
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda *a, **k: None)
    return model_result_view


@pytest.mark.parametrize('pipeline', [False, True])
@pytest.mark.parametrize('shape', ['image_base64', 'image_data', 'images'])
def test_large_image_survives_preview_native_and_mcp(view, monkeypatch, pipeline, shape):
    import mcp_server
    from system_tools import _harvest_images
    from mcp.server.fastmcp import Image
    blob = base64.b64encode(b'large-image' * 20000).decode()
    photo = {'success': True, 'file_path': '/image.jpg'}
    if shape == 'image_base64':
        photo.update(image_base64=blob, mime_type='image/jpeg')
    elif shape == 'image_data':
        photo['image_data'] = {'b64': blob, 'media_type': 'image/jpeg'}
    else:
        photo['images'] = [{'base64': blob, 'media_type': 'image/jpeg'}]
    raw = ({'success': True, 'results': [{'step': 1, 'result': json.dumps(photo)}],
            'final_result': json.dumps(photo)} if pipeline else photo)
    original = json.dumps(raw)
    projected = view.project_result(raw)
    serialized = json.dumps(projected)
    text, images = _harvest_images(serialized)
    assert len(images) == 1 and images[0]['base64'] == blob
    assert images[0]['media_type'] == 'image/jpeg'
    assert blob not in text
    # Display extraction never mutates the source or discards stored bytes.
    assert json.dumps(raw) == original
    evidence = view.evidence_store().read_evidence(projected['result_ref']['id'], 0, None)
    assert json.loads(evidence['text']) == raw
    monkeypatch.setattr(mcp_server, '_post_backend', lambda *a, **k: serialized)
    monkeypatch.setattr(mcp_server, '_repeat_advisory', lambda *a: '')
    delivered = asyncio.run(mcp_server.execute_ibl(code='[limbs:browser]{op:"vision"}'))
    assert isinstance(delivered, list) and len(delivered) == 2
    assert isinstance(delivered[1], Image)
    assert delivered[1].data == base64.b64decode(blob)
    assert blob not in delivered[0]


def test_image_limit_is_explicit_and_original_remains_recoverable(view):
    blob = base64.b64encode(b'large-image' * 1000).decode()
    raw = {'images': [{'base64': blob, 'media_type': 'image/png'} for _ in range(5)]}
    result = view.project_result(raw)
    assert len(result['images']) == 4
    assert result['images_omitted'] == 1
    saved = view.evidence_store().read_evidence(result['result_ref']['id'], 0, None)
    assert len(json.loads(saved['text'])['images']) == 5


def test_projection_counts_image_bytes_separately_from_model_text(view, monkeypatch):
    events = []
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda kind, data: events.append((kind, data)))
    blob = base64.b64encode(b'large-image' * 20000).decode()
    view.project_result({'image_base64': blob, 'mime_type': 'image/jpeg'})
    metrics = next(data for kind, data in events if kind == 'context.result_projected')
    assert metrics['image_count'] == 1
    assert metrics['model_chars'] < 5000 < metrics['raw_chars']


def test_result_pages_remain_json_with_real_repeat_guard(view, monkeypatch):
    import mcp_server
    import repeat_guard
    repeat_guard.reset_all()
    source = {'text': '본문' * 300}
    ref = view.project_result({'text': '본문' * 50000})['result_ref']
    monkeypatch.setattr(mcp_server, '_post_backend', lambda route, body, timeout:
                        json.dumps(view.read_result(body['read_result'])) if 'read_result' in body
                        else json.dumps(source))
    # Old MCP keyed all code="" page reads alike and appended non-JSON at page 3.
    for offset in range(0, 6000, 1000):
        text = asyncio.run(mcp_server.execute_ibl(code='', read_result={
            'id': ref['id'], 'path': ['text'], 'offset': offset, 'limit': 1000}))
        page = json.loads(text)
        assert page['offset'] == offset and '_model_advisory' not in page
    for _ in range(3):
        text = asyncio.run(mcp_server.execute_ibl(code='[sense:search]{query:"x"}'))
    assert '반복 감지' in json.loads(text)['_model_advisory']
    repeat_guard.reset_all()


def finish_tool(controller, payload, error=False):
    key = controller._start('execute_ibl', payload)
    controller._finish(key, {'success': not error}, error)


def test_recovered_failure_does_not_invoke_review(supervisor, monkeypatch):
    monkeypatch.setattr('supervisor_runtime.invoke', lambda *a, **k: pytest.fail('unnecessary model call'))
    for code in ['bad iteration', 'bad projection']:
        finish_tool(supervisor, {'code': code}, error=True)
    assert supervisor.trigger == 'repeated_failure'
    finish_tool(supervisor, {'code': 'correct projection'})
    assert not supervisor.trigger
    # A tick that already captured the old reason must revalidate it too.
    supervisor.review('repeated_failure')
    assert supervisor.reviews == 0
    assert any(issue['open'] for issue in supervisor.issues.values())  # no fabricated resolution


def test_evidence_read_does_not_disguise_failure_or_trigger_repeat(supervisor, monkeypatch):
    calls = []
    monkeypatch.setattr('supervisor_runtime.invoke', lambda *a, **k:
                        calls.append(k) or '{"status":"CONTINUE","reason":"inspect failure"}')
    for code in ['bad one', 'bad two']:
        finish_tool(supervisor, {'code': code}, error=True)
    for offset in range(4):
        finish_tool(supervisor, {'code': '', 'read_result': {'id': 'saved', 'offset': offset}})
    assert supervisor.failures == 2 and supervisor.trigger == 'repeated_failure'
    supervisor.review('repeated_failure')
    assert len(calls) == 1  # unresolved failures still get supervision


def test_snapshot_numeric_ax_value_is_readable(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    file = root / 'data/packages/installed/tools/browser-action/browser_snapshot.py'
    monkeypatch.setitem(sys.modules, 'browser_session', SimpleNamespace(BrowserSession=None, ensure_active=None))
    spec = importlib.util.spec_from_file_location('snapshot_regression', file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    session = SimpleNamespace(add_ref=lambda item: 'r1')
    for number in [0, 97, 97.5]:
        nodes = [{'role': {'value': 'slider'}, 'name': {'value': 'Seek'}, 'value': {'value': number}}]
        result = mod._finalize_snapshot(mod._extract_elements(nodes, session), 'https://example.org', 'video')
        assert result['success']
        assert result['snapshot'][0]['value'] == str(number)


def test_quoted_query_and_each_guidance_parse_without_extra_round():
    from ibl_parser import parse
    code = "[sense:search]{query:'\"정확한 구절\" 추가어'}"
    assert parse(code)[0]['params']['query'] == '"정확한 구절" 추가어'
    parsed = parse('[table:each]{items:[{url:"x"}],do:"[sense:crawl]{url:$it.url}"}')
    assert parsed


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
