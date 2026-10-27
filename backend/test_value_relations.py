"""Episode 5557: a current row selection cannot hide behind stale source prose."""
import boot_paths  # noqa: F401
import copy
import pytest
from common.value_relations import mirrored_text_fields, invalidate_display_relations
from common.expression_ir import pack, unpack
from model_result_view import _fold_twin_fields
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


def page():
    return {'text': 'first\n\nselected\n\nlast',
            'items': [{'text': t, 'source': 'A', 'position': i} for i, t in enumerate(['first', 'selected', 'last'])],
            '_display': {'mirror_fields': ['text']}, 'source': 'A'}


@pytest.mark.parametrize('change', ['empty', 'subset', 'reverse', 'edit', 'wrong_mirror', 'oversize'])
def test_relations_are_rechecked_after_value_changes(change):
    value = page()
    assert mirrored_text_fields(value) == ('text',)
    if change == 'empty':
        value['items'] = []
    elif change == 'subset':
        value['items'] = value['items'][1:2]
    elif change == 'reverse':
        value['items'] = value['items'][::-1]
    elif change == 'edit':
        value['items'][1]['text'] = 'changed'
    elif change == 'wrong_mirror':
        value['_display']['mirror_fields'] = ['source']
    else:
        value['items'][0]['text'] = 'x' * 200001
    before = copy.deepcopy(value)
    assert mirrored_text_fields(value) == ()
    shown = _fold_twin_fields(value, [], [])
    assert shown['items'] == value['items']
    assert value == before
    assert invalidate_display_relations(value)['_display']['mirror_fields'] == []


def test_verified_display_duplicate_keeps_rows_and_does_not_certify_origin():
    value = page()
    value['items'][1]['source'] = 'B'
    shown = _fold_twin_fields(value, [], [])
    assert shown['text'] == {'$model_mirror_of': 'items'}
    assert shown['items'][1]['source'] == 'B'
    assert 'completion' not in shown


@pytest.mark.parametrize('depth', [1, 3, 6, 10, 14, 30])
def test_selection_wrap_promote_transport_display_is_non_lossy(depth):
    definitions = {'f0': '[def:f0]($page){return {**$page,items:filter($page.items,($r)=>$r.text=="selected")}}'}
    for i in range(1, depth + 1):
        definitions[f'f{i}'] = f'[def:f{i}]($page){{return [fn:f{i-1}]{{page:$page}}}}'
    source = f'return [fn:f{depth}]{{page:$page}}'
    plan = compile_program(source, inputs={'page': page()}, definitions=definitions)
    assert not plan.issues, plan.report()
    out = Runtime(plan, {'page': page()}).run()
    assert out['success'], out
    transported = unpack(pack(out['value']))
    shown = _fold_twin_fields(transported, [], [])
    assert shown['items'] == [page()['items'][1]]
    assert shown['text'] == page()['text']
    assert list(shown)[0] == 'items'


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
