"""Approval notices are static observations, never grants or tool execution."""
import boot_paths  # noqa: F401
from pathlib import Path

import pytest
from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program


POLICY = {'requires': {'ops': {'erase': {'human_confirm': True}}},
          'ops': {'values': {'list': '', 'erase': ''}, 'default': 'list'}}


def registry(policy=None, **extensions):
    contract = {'version': 1, 'params': {'op': 'Text', 'id': 'Text'}, 'required': [],
                'result': 'Text', 'effects': ['write_external'],
                'analysis': {'approval_policy': policy or POLICY}, **extensions}
    def forbidden(*args, **kwargs):
        pytest.fail('preflight invoked an effect')
    return {'custom:resource': Adapter(contract, forbidden)}


def checked(source, *, inputs=None, reg=None, **kwargs):
    result = compile_program(source, reg or registry(), inputs, **kwargs).report()
    assert result['ok'], result
    assert result['preflight']['status'] != 'abstained', result
    return result


def notices(result):
    return [w for w in result['warnings'] if w['code'] == 'HUMAN_CONFIRM']


def test_two_static_calls_show_locations_and_do_not_reveal_arguments():
    result = checked('[custom:resource]{op:"erase",id:"secret-one"}\n'
                     '[custom:resource]{op:"erase",id:"secret-two"}')
    warnings = notices(result)
    assert len(warnings) == 2
    assert all(w['facts']['requirement'] == 'declared' and w['facts']['op'] == 'erase' for w in warnings)
    assert warnings[0]['location'] != warnings[1]['location']
    assert 'secret-' not in str(warnings)
    assert result['executed'] is False and not result['issues']
    assert all('resume' in w['hint'] and '승인' in w['message'] for w in warnings)


@pytest.mark.parametrize('source,inputs', [
    ('[custom:resource]{}', None),
    ('[custom:resource]{op:"list"}', None),
    ('$mode="list"; [custom:resource]{op:$mode}', None),
    ('[custom:resource]{op:$mode}', {'mode': 'list'}),
    ('[if:false]{[custom:resource]{op:"erase"}}', None),
    ('[] >> [table:each]{[custom:resource]{op:"erase"}}', None),
    ('[repeat:0]{[custom:resource]{op:"erase"}}', None),
    ('[repeat:while false]{[custom:resource]{op:"erase"}}', None),
    ('[def:unused](){[custom:resource]{op:"erase"}}; return 1', None),
    ('return 1; [custom:resource]{op:"erase"}', None),
])
def test_no_notice_for_known_read_or_unreachable_call(source, inputs):
    assert notices(checked(source, inputs=inputs)) == []


def test_aliases_defaults_and_explicit_override_use_effective_policy():
    assert notices(checked('[custom:resource]{operation:"erase"}', reg=registry(aliases={'operation':'op'})))[0]['facts']['op'] == 'erase'
    assert notices(checked('[custom:resource]{}', reg=registry(defaults={'op': 'erase'})))[0]['facts']['op'] == 'erase'
    policy = {'requires': {'human_confirm': True, 'ops': {'list': {'human_confirm': False}}},
              'ops': POLICY['ops']}
    assert not notices(checked('[custom:resource]{op:"list"}', reg=registry(policy)))
    assert notices(checked('[custom:resource]{op:"erase"}', reg=registry(policy)))
    assert notices(checked('[custom:resource]{}', reg=registry({'requires': {'human_confirm': True}})))


@pytest.mark.parametrize('source', [
    '[custom:resource]{op:$mode}',
    '[custom:resource]{op:"list",**$args}',
    '[custom:resource]{**$args}',
])
def test_unresolved_selector_or_spread_is_possible_not_approved(source):
    from ibl_v2_types import TEXT, UNKNOWN
    result = checked(source, input_types={'mode': TEXT, 'args': UNKNOWN})
    warning, = notices(result)
    assert warning['facts']['requirement'] == 'possible' and warning['facts']['op'] is None
    assert warning['facts']['approval_ops'] == ['erase']


def test_explicit_selector_after_unknown_spread_is_still_known():
    from ibl_v2_types import UNKNOWN
    result = checked('[custom:resource]{**$args,op:"list"}', input_types={'args': UNKNOWN})
    assert not notices(result)


def test_unknown_spread_can_override_default_and_loop_mutation_is_not_frozen():
    from ibl_v2_types import UNKNOWN
    result = checked('[custom:resource]{**$args}', reg=registry(defaults={'op': 'list'}),
                     input_types={'args': UNKNOWN})
    assert notices(result)[0]['facts']['requirement'] == 'possible'
    result = checked('$mode="list"; [repeat:2]{[custom:resource]{op:$mode}; $mode="erase"}')
    warning, = notices(result)
    assert warning['facts']['requirement'] == 'possible'
    assert warning['facts']['visits_upper_bound'] == 2


def test_repeated_function_calls_keep_their_call_sites():
    result = checked('[def:remove](){[custom:resource]{op:"erase"}}\n[fn:remove]{}\n[fn:remove]{}')
    warnings = notices(result)
    assert len(warnings) == 2
    assert warnings[0]['facts']['callers'] != warnings[1]['facts']['callers']


def test_pipe_and_fixed_adapter_selector_match_the_gate():
    assert not notices(checked('"list" >> [custom:resource]{}', reg=registry(pipe_input='op')))
    assert notices(checked('"erase" >> [custom:resource]{}', reg=registry(pipe_input='op')))[0]['facts']['op'] == 'erase'
    result = checked('[custom:resource]{op:"list"}',
                     reg=registry(adapter={'fixed_params': {'op': 'erase'}}))
    assert notices(result)[0]['facts']['op'] == 'erase'


def test_saved_function_body_is_observed_only_when_called():
    definitions = {'remove': '[def:remove]($id){[custom:resource]{op:"erase",id:$id}}'}
    result = checked('[fn:remove]{id:"A"}', definitions=definitions)
    warning, = notices(result)
    assert warning['facts']['action'] == 'custom:resource'
    assert warning['facts']['callers']


def test_function_arguments_and_loops_keep_static_policy_and_uncertain_count():
    source = '[def:remove]($mode="erase"){[custom:resource]{op:$mode}}\n'
    result = checked(source + '["a","b"] >> [table:each]{[fn:remove]{}}')
    warning, = notices(result)
    assert warning['facts']['requirement'] == 'declared'
    assert warning['facts']['visits_upper_bound'] == 2
    from ibl_v2_types import BOOL, UNKNOWN
    result = checked(source + '[if:$flag]{$rows >> [table:each]{[fn:remove]{}}}',
                     input_types={'flag': BOOL, 'rows': UNKNOWN})
    warning, = notices(result)
    assert warning['facts']['conditional'] is True
    assert warning['facts']['visits_upper_bound'] is None


def test_warnings_remain_bounded_and_report_omissions():
    result = checked('\n'.join('[custom:resource]{op:"erase"}' for _ in range(40)))
    assert len(notices(result)) == 32
    assert result['preflight']['warnings_omitted'] == 8


def test_original_round28_check_has_two_call_bound_without_any_gate_or_tool(tmp_path, monkeypatch):
    import action_requires
    import approval_tokens
    import ibl_engine
    from ibl_v2_entry import handle_request
    def forbidden(*args, **kwargs):
        pytest.fail('check executed a tool, target lookup, or approval operation')
    for module, name in [(action_requires, 'gate'), (action_requires, '_target_missing'),
                         (approval_tokens, 'issue'), (approval_tokens, 'consume'), (ibl_engine, 'execute_ibl')]:
        monkeypatch.setattr(module, name, forbidden)
    root = Path(__file__).resolve().parents[1]
    source = (root / 'docs/experiments/long_sentence_imagination/round_28/drafts/start_v0.ibl').read_text()
    inputs = {'agent': 'unused', 'message': 'never sent', 'first_wait': 1,
              'switch_ids': ['A', 'B'], 'out': str(tmp_path / 'report.json')}
    result = handle_request({'code': source, 'inputs': inputs, 'check': True}, str(tmp_path))
    assert result['ok'], result
    warning, = notices(result)
    assert warning['facts']['action'] == 'self:switch' and warning['facts']['op'] == 'delete'
    assert warning['facts']['visits_upper_bound'] == 2
    assert not (tmp_path / 'report.json').exists()


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
