"""Historical long-program migrations and external failure completeness."""
import boot_paths  # noqa: F401
import importlib.util
from pathlib import Path
import tempfile

import pytest

from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'docs/experiments/legacy_long_replay_2026_09_25/replay.py'
spec = importlib.util.spec_from_file_location('historical_replay_fixture', PATH)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


@pytest.fixture(scope='module')
def registry():
    with tempfile.TemporaryDirectory(prefix='ibl-replay-test-', dir=ROOT / 'outputs') as tmp:
        yield load_registry(tmp), tmp


CASES = [(name, variant) for name in replay.NAMES
         for variant in (['normal', 'empty'] if name == 'ledger'
                         else ['normal', 'empty', 'failure'])]
CASES.append(('news', 'optional_failure'))


@pytest.mark.parametrize('name,variant', CASES)
def test_historical_rewrite(registry, name, variant):
    base, tmp = registry
    result = replay.evaluate(name, variant, base, tmp)
    assert result['passed'], result.get('error')


def failure_registry(effect, exception, calls):
    def fail(rt, args):
        calls.append('call')
        if isinstance(exception, Fault):
            raise Fault(exception.code, str(exception), kind=exception.kind)
        raise type(exception)(str(exception))
    return {'fixture:read': Adapter({
        'version': 1, 'params': {}, 'result': 'Record',
        'effects': [effect],
    }, fail)}


@pytest.mark.parametrize('effect', ['read_external', 'model', 'unknown', 'write_external'])
@pytest.mark.parametrize('error', [Fault('TOOL', 'unavailable'), ValueError('bad envelope')])
@pytest.mark.parametrize('code', [
    '[fixture:read]{}',
    '[try]{[fixture:read]{}}[catch]{return []}',
    '[fixture:read]{} ?? []',
])
def test_external_failure_and_receipt_replay_remain_incomplete(effect, error, code):
    calls = []
    plan = compile_program(code, failure_registry(effect, error, calls))
    first = Runtime(plan).run()
    assert not first['source_complete'], first
    assert len(first['recordings']) == 1
    second = Runtime(plan, recordings=first['recordings'], replay=True).run()
    assert calls == ['call']
    assert second['success'] == first['success']
    assert not second['source_complete'], second
    for result in (first, second):
        assert any(e['kind'] == 'tool_failure' and e['incomplete']
                   for e in result['evidence'])
    if first['success']:
        assert first['value'] == second['value'] == []


def test_pure_arithmetic_recovery_does_not_claim_missing_sources():
    result = Runtime(compile_program('[try]{1/0}[catch]{return 0}')).run()
    assert result['success'] and result['source_complete']
    assert result['value'] == 0


def test_pure_adapter_failure_is_not_a_missing_external_source():
    calls = []
    plan = compile_program('[fixture:read]{} ?? []',
                           failure_registry('pure', Fault('VALUE', 'bad input'), calls))
    result = Runtime(plan).run()
    assert result['success'] and result['source_complete']
    assert result['value'] == []


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
