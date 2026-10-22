import boot_paths  # noqa: F401
import pytest
from task_tree_budget import Tree, scope, start_round, finish_round, observe, MODELS


def test_estimates_reserve_once_and_usage_settles_without_double_counting():
    tree = Tree(limit=100)
    first, second = {'_token_estimate': 60}, {'_token_estimate': 60}
    before = MODELS.active
    with scope(tree):
        start_round(first)
        with pytest.raises(RuntimeError, match='예산'):
            start_round(second)
        observe(30)
        finish_round(first)
        start_round(second)
        observe(50)
        finish_round(second)
        finish_round(second)
    assert tree.used == 80 and tree.reserved == 0
    assert MODELS.active == before


def test_native_cli_observation_does_not_claim_internal_round_admission():
    tree = Tree(limit=10)
    call = {'_native_tools': True}
    with scope(tree):
        start_round(call)
        assert '_model_lease' not in call
        observe(12)
        assert tree.reason()['kind'] == 'task_budget'


def test_single_shot_call_boundary_reserves_and_releases_without_round_hook():
    from types import SimpleNamespace
    from model_call_context import call_scope
    from providers.base import ProviderMetrics
    provider = SimpleNamespace(metrics=ProviderMetrics(), max_tokens=20, model='test')
    tree = Tree(limit=30)
    before = MODELS.active
    with scope(tree), call_scope(provider):
        assert MODELS.active == before + 1
        assert tree.reserved == 20
        provider.metrics.record_request(1, 5, 2)
        assert tree.used == 7 and tree.reserved == 0
    assert MODELS.active == before


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
