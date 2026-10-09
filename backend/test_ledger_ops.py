"""Explicit root-shape diagnostics preserve JSON ledgers on rejected writes."""
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from common.pkg_utils import load_sibling

LG = load_sibling(str(Path(__file__).resolve().parents[1] /
    'data/packages/installed/tools/system_essentials/handler.py'), 'ledger_ops')


@pytest.mark.parametrize('op', ['select', 'append', 'upsert'])
@pytest.mark.parametrize('root,target,expected', [
    ([{'id': 'a'}], 'items', 'array'), ({'items': [{'id': 'a'}], 'count': 1}, None, 'object')])
def test_mismatched_root_reports_shape_without_mutation(tmp_path, monkeypatch, op, root, target, expected):
    monkeypatch.setattr(LG, '_ROOT', tmp_path)
    path = tmp_path / 'ledger.json'
    path.write_text(json.dumps(root))
    before = path.read_bytes()
    out = getattr(LG, 'op_' + op)({'path': str(path), 'target': target, 'key': 'id', 'item': {'id': 'a', 'v': 2}})
    assert out['success'] is False and out['root_type'] == expected
    assert 'target' in out['hint']
    assert path.read_bytes() == before
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault
    with pytest.raises(Fault) as caught:
        decode_envelope(out, {})
    assert caught.value.details['root_type'] == expected
    args = {'path': str(path), 'key': 'id', 'item': {'id': 'a', 'v': 2}}
    if expected == 'object':
        args['target'] = 'items'
    fixed = getattr(LG, 'op_' + op)(args)
    assert fixed['success'], fixed
    assert isinstance(json.loads(path.read_text()), type(root))


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
