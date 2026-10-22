import boot_paths  # noqa: F401
from threading import Barrier, Lock
import json

import pytest

from tool_batch import execute, _eligibility, prepared_plan


READ = {'name': 'read', 'execution': {'concurrency': 'reentrant', 'effects': ['read_external']}}


def test_reads_overlap_but_writes_and_unknown_calls_are_barriers():
    barrier = Barrier(2)
    finished = []
    def invoke(call):
        i = call['input']['i']
        if call['name'] == 'read':
            barrier.wait(2)
        else:
            assert sorted(finished) == [0, 1]
        finished.append(i)
        return {'content': str(i), 'images': [{'base64': str(i)}], 'details': {'id': i}}
    calls = [{'name': name, 'input': {'i': i}, 'id': f'call-{i}'}
             for i, name in enumerate(['read', 'read', 'write', 'read', 'read'])]
    results = list(execute(calls, [READ], invoke))
    assert [c['id'] for c, _ in results] == [f'call-{i}' for i in range(5)]
    assert [o.raw['images'][0]['base64'] for _, o in results] == list(map(str, range(5)))


@pytest.mark.parametrize('failure', [RuntimeError('failed'), '[[APPROVAL_REQUESTED]]approve', '{"success":false,"error":"failed"}'])
def test_failed_or_approval_barrier_never_starts_later_call(failure):
    started = []
    def invoke(call):
        started.append(call['name'])
        if isinstance(failure, Exception):
            raise failure
        return failure
    results = list(execute([{'name': n, 'input': {}} for n in ['write', 'read']], [READ], invoke))
    assert started == ['write']
    assert results[1][1].started is False
    assert json.loads(results[1][1].unwrap())['execution_status'] == 'not_started'


def test_program_classification_follows_effects_and_reentrancy(monkeypatch):
    from test_ibl_v2_core import adapter
    import ibl_v2_adapters
    import ibl_v2_store
    read = adapter(lambda rt, a: 1, result='Number')
    read.contract['execution'] = {'concurrency': 'reentrant'}
    registry = {'test:read': read,
                'test:unknown': adapter(lambda rt, a: 1, result='Number', effects=['unknown'])}
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: registry)
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    schema = {'execution': {'protocol': 'ibl-program/2'}}
    assert _eligibility(schema, {'code': '[test:read]{}'}, '.', None)[0]
    assert not _eligibility(schema, {'code': '[test:unknown]{}'}, '.', None)[0]
    assert not _eligibility(schema, {'code': '$checked:opaque'}, '.', None)[0]
    read.contract.pop('execution')
    assert not _eligibility(schema, {'code': '[test:read]{}'}, '.', None)[0]


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
