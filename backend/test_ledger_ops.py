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
    monkeypatch.setattr(LG, "get_base_path", lambda: tmp_path)
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


@pytest.mark.parametrize('repair', [False, True])
@pytest.mark.parametrize('form', ['relative', 'absolute', 'workspace'])
def test_data_owner_is_independent_of_generation_and_project(tmp_path, monkeypatch, repair, form):
    live, copy, generation = (tmp_path / name for name in ('live', 'copy', 'generation'))
    for root in (live, copy, generation):
        root.mkdir()
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(live))
    monkeypatch.setenv('INDIEBIZ_CODE_ROOT', str(generation))
    monkeypatch.setattr('thread_context.get_repair_workspace', lambda: str(copy) if repair else None)
    owner = copy if repair else live
    (owner / 'items.json').write_text('[{"id":"owned"}]')
    (live / 'ledger.json').write_text('[{"id":"live"}]')
    args = {'path': {'relative': 'new/ledger.json', 'absolute': str(owner / 'new/ledger.json'),
                     'workspace': '~workspace/new/ledger.json'}[form],
            'items_file': '~workspace/items.json'}
    result = LG.op_append(args)
    assert result['success'], result
    assert json.loads((owner / 'new/ledger.json').read_text()) == [{'id': 'owned'}]
    assert json.loads((live / 'ledger.json').read_text()) == [{'id': 'live'}]
    assert not LG.op_select({'path': str(generation / 'items.json')})['success']
    if repair:
        assert not LG.op_select({'path': str(live / 'ledger.json')})['success']


@pytest.mark.parametrize('field', ['path', 'items_file'])
def test_symlink_and_new_parent_escape_remain_rejected(tmp_path, monkeypatch, field):
    owner, outside = tmp_path / 'owner', tmp_path / 'outside'
    owner.mkdir(); outside.mkdir()
    monkeypatch.setattr(LG, 'get_base_path', lambda: owner)
    (owner / 'escape').symlink_to(outside, target_is_directory=True)
    (outside / 'items.json').write_text('[{"id":1}]')
    args = {'path': 'ledger.json', 'items': [{'id': 1}], field: 'escape/items.json'}
    result = LG.op_append(args)
    assert not result['success']
    assert not (owner / 'ledger.json').exists()
    assert json.loads((outside / 'items.json').read_text()) == [{'id': 1}]
