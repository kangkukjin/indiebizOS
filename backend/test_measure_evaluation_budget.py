"""The live comparison fixture is deterministic and never required by offline tests."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from evaluation_input import EvaluationPrompt
from supervision_store import TurnStore


@pytest.fixture
def measurement():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'measure_evaluation_budget.py'
    spec = importlib.util.spec_from_file_location('measure_evaluation_budget', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('incorrect,amount', [(False, 70), (True, 60)])
def test_selected_fixture_retains_middle_counterexample(measurement, tmp_path, incorrect, amount):
    required, rows, criteria = measurement.fixture(TurnStore(tmp_path), incorrect=incorrect)
    provider = SimpleNamespace(model='fixture', CONTEXT_PROVIDER='test', context_window_tokens=128000,
                               request_limits={'chars': 28000}, system_prompt='', tools=[])
    prompt = EvaluationPrompt(required, rows, json.dumps(criteria, ensure_ascii=False))
    shown = prompt.prepare_request(provider)
    assert f'A=120원, B=80원, C={amount}원' in shown
    assert '270원' in required and prompt.metrics['omitted'] > 0
    assert len(prompt.metrics['sections']) == 12
    assert all(r['source_ref'] == r['revision'] for r in rows)


def test_failed_live_arm_never_parses_error_as_verdict_or_invents_usage(measurement, tmp_path, monkeypatch):
    import consciousness_agent as ca
    monkeypatch.setattr(ca, 'call_oneshot_provider', lambda *a, **kw: 'ACHIEVED transport error')
    monkeypatch.setattr(ca, 'oneshot_failure_details', lambda: {'kind': 'transport'})
    store = TurnStore(tmp_path)
    required, rows, criteria = measurement.fixture(store)
    result = measurement.run_arm(SimpleNamespace(request_limits={}), store, required, rows, criteria)
    assert result['status'] == 'UNKNOWN' and len(result['rounds']) == 1
    assert not result['measured'] and all(v is None for v in result['tokens'].values())


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
