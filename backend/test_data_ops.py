"""Data transform contracts through the public IBL execution boundary."""
import boot_paths  # noqa: F401
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('key', ['author', ['title', 'author']])
def test_dedup_documented_alias_selects_the_same_keys(key):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from thread_context import actor_context
    inputs = {'rows': [{'title': 'Shared', 'author': 'A'},
                       {'title': 'Shared', 'author': 'B'},
                       {'title': 'Shared', 'author': 'a'}], 'key': key}
    results = []
    for argument in ('by', 'key'):
        plan = compile_program('$rows >> [table:dedup]{' + argument + ':$key}',
                               load_registry(str(ROOT)), inputs)
        assert not plan.issues, plan.issues
        with actor_context(origin='training'):
            result = Runtime(plan, inputs).run()
        assert result['success'], result.get('diagnostic')
        results.append(result['value']['items'])
    assert results[0] == results[1] == inputs['rows'][:2]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
