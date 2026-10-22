"""Benchmark metrics count invocations, not their handoff transport copies."""
import importlib.util
from pathlib import Path

import boot_paths  # noqa: F401


def load_collector():
    path = Path(__file__).resolve().parents[1] / 'scripts/mind2web_collect.py'
    spec = importlib.util.spec_from_file_location('mind2web_collect_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transport_copies_collapse_but_retries_and_unidentified_calls_remain():
    collector = load_collector()
    start = {'type': 'tool_start', 'id': 'call-1', 'name': 'Bash',
             'input': {'command': 'read public-source'}}
    events = [{**start, 'type': 'handoff.tool_start'}, start,
              {**start, 'id': 'call-2'}, {**start, 'id': None},
              {**start, 'id': None}, {**start, 'type': 'tool_result'}]
    count, names, hits = collector.audit_events(events)
    assert count == 4 and names == {'Bash': 4} and hits == []


def test_audit_checks_both_copies_even_when_arguments_disagree():
    collector = load_collector()
    start = {'type': 'tool_start', 'id': 'call-1', 'name': 'Bash', 'input': {}}
    events = [start, {**start, 'type': 'handoff.tool_start',
                      'input': {'command': 'read eval_scripts/answer.py'}}]
    count, names, hits = collector.audit_events(events)
    assert count == 1 and len(hits) == 1


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
