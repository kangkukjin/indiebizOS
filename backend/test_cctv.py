"""CCTV 대상의 통합 op·공급처·작업공간 계약."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from common.pkg_utils import load_sibling

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def handler():
    return load_sibling(str(ROOT / 'data/packages/installed/tools/cctv/capture.py'), 'handler')


@pytest.mark.parametrize('source,radius', [('auto', 5), ('windy', 50)])
def test_nearby_source_preserves_provider_radius_and_limit(handler, monkeypatch, source, radius):
    calls = []
    def auto(lat, lng, **kw):
        calls.append(('auto', lat, lng, kw))
        return {'items': [{'name': 'road'}]}
    def windy(**kw):
        calls.append(('windy', kw.pop('lat'), kw.pop('lon'), kw))
        return {'items': [{'title': 'landscape'}]}
    monkeypatch.setattr(handler, 'nearby', auto)
    monkeypatch.setattr(handler, 'load_module', lambda name: SimpleNamespace(get_nearby_webcam=windy))
    result = handler.execute({'op':'nearby', 'source':source, 'lat':0, 'lng':0, 'limit':2}, SimpleNamespace(tool_name='cctv_op'))
    assert result['items']
    assert calls[0][:3] == (source, 0, 0)
    assert calls[0][3]['radius_km'] == radius and calls[0][3]['count'] == 2


def test_invalid_source_never_silently_falls_back(handler, monkeypatch):
    monkeypatch.setattr(handler, 'nearby', lambda *a, **kw: pytest.fail('unexpected source fallback'))
    assert not json.loads(handler._cctv_op(op='nearby', lat=1, lng=2, source='typo'))['success']
    assert not json.loads(handler._cctv_op(op='search', query='x', source='windy'))['success']


def test_capture_keeps_callers_workspace(handler, monkeypatch, tmp_path):
    calls = []
    def capture(url, _project_path=None):
        calls.append((url, _project_path))
        return {'success':True}
    monkeypatch.setitem(handler._OP_DISPATCHERS['cctv_op'], 'capture', capture)
    assert handler.execute({'op':'capture', 'url':'https://example.test/live'}, SimpleNamespace(tool_name='cctv_op', project_path=str(tmp_path)))['success']
    assert calls == [('https://example.test/live', str(tmp_path))]


def test_public_cctv_read_ops_remain_composable():
    from ibl_ops import op_returns, op_side_effect
    declaration = yaml.safe_load((ROOT/'data/packages/installed/tools/cctv/ibl_actions.yaml').read_text())
    assert set(declaration['nodes']) == {'limbs'}
    cfg = declaration['nodes']['limbs']['actions']['cctv']
    for op in ('search','nearby','stats'):
        assert op_returns(cfg,op) == 'items' and not op_side_effect(cfg,op)
    for op in ('open','capture','refresh'):
        assert op_side_effect(cfg,op)
    assert 'webcam' not in cfg['ops']['values']


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


def test_installed_registry_does_not_resurrect_retired_media_names():
    from ibl_registry import load_nodes_installed
    nodes=load_nodes_installed()['nodes']
    for node, name in [('sense','cctv'),('sense','radio'),('sense','webcam'),('self','cctv'),('limbs','radio_favorite')]:
        assert name not in nodes[node]['actions']
    assert 'cctv' in nodes['limbs']['actions'] and 'radio' in nodes['limbs']['actions']
