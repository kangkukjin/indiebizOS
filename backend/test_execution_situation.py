"""Observation ordering, delivery ownership, and incomplete effects are independent contracts."""
import boot_paths  # noqa: F401
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from execution_situation import Situation, fingerprint


@pytest.fixture
def situation():
    events = []
    value = Situation('owner', 'task', lambda kind, **row: events.append((kind, row)),
                      lambda row: {'id': fingerprint(row), 'chars': len(str(row))})
    value.events = events
    return value


def observe(s, version, cursor, subject=None, **kw):
    return s.observe(subject or {'kind': 'file', 'device': 'a', 'path': '/x'},
                     'version', version, subject_revision=version, source='producer',
                     source_cursor=cursor, **kw)


def test_out_of_order_duplicate_and_conflict_preserve_first(situation):
    s = situation
    observe(s, 'v1', 1)
    observe(s, 'v3', 3)
    rev = s.revision
    observe(s, 'v3', 3)
    assert s.revision == rev
    observe(s, 'v2', 2)
    row = s.snapshot()['observations'][0]
    assert row['first']['value'] == 'v1'
    assert row['latest']['value'] == 'v3' and row['late']['value'] == 'v2'
    observe(s, 'different-v3', 3)
    assert s.snapshot()['observations'][0]['availability'] == 'conflict'


def test_receive_time_does_not_make_older_observation_current(situation):
    observe(situation, 'new', None, observed_at='2026-10-31T10:00:00+00:00')
    observe(situation, 'old', None, observed_at='2026-10-31T09:00:00+00:00')
    assert situation.snapshot()['observations'][0]['latest']['value'] == 'new'


def test_returning_to_previous_content_is_a_new_observation(situation):
    observe(situation, 'A', None, observed_at=1)
    observe(situation, 'B', None, observed_at=2)
    observe(situation, 'A', None, observed_at=3)
    row = situation.snapshot()['observations'][0]
    assert row['latest']['value'] == 'A' and row['latest']['observed_at'] == 3
    assert row['first']['observed_at'] == 1
    revision = situation.revision
    observe(situation, 'A', None, observed_at=4)
    assert situation.revision == revision  # unchanged polling is not progress


def test_conflicting_sources_and_different_hosts(situation):
    subject = {'kind': 'file', 'device': 'a', 'path': '/x'}
    observe(situation, 'a1', 1, subject)
    observe(situation, 'b1', 1, {**subject, 'device': 'b'})
    situation.observe(subject, 'version', 'a2', source='different', source_cursor=2)
    rows = situation.snapshot()['observations']
    assert len(rows) == 3
    assert [r['availability'] for r in rows].count('conflict') == 2


def test_conflicting_revisions_are_visible_even_with_same_summary(situation):
    subject = {'kind': 'file', 'path': '/same'}
    for source, revision in [('writer', 'v1'), ('reader', 'v2')]:
        situation.observe(subject, 'version', {}, source=source, subject_revision=revision)
    assert all(r['availability'] == 'conflict' for r in situation.snapshot()['observations'])


def test_validation_is_bound_to_exact_input_and_returns_in_change_delta(situation):
    s = situation
    source = {'kind': 'file', 'device': 'a', 'path': '/csv'}
    other = {**source, 'path': '/other'}
    observe(s, 'v1', 1, source)
    s.observe({'kind': 'analysis', 'id': 'totals'}, 'validation', 'passed', source='calculator',
              relation=[{'subject': source, 'revision': 'v1'}])
    first = s.prepare('executor')
    s.acknowledge('executor', first)
    observe(s, 'o2', 1, other)
    assert all(r['availability'] != 'needs_recheck' for r in s.snapshot()['observations'])
    observe(s, 'v2', 2, source)
    delta = s.prepare('executor', retained=[first['delivery_id']], budget=8000)
    assert delta['mode'] == 'delta'
    check = next(r for r in delta['observations'] if r['latest']['facet'] == 'validation')
    assert check['availability'] == 'needs_recheck' and check['latest']['value'] == 'passed'


def test_failed_delivery_independent_consumers_and_compaction(situation):
    observe(situation, 'v1', 1)
    first = situation.prepare('execution')
    assert not situation.cursors
    retry = situation.prepare('execution', retained=[first['delivery_id']])
    assert retry['mode'] == 'baseline'
    situation.acknowledge('execution', first)  # superseded request is not an acknowledgement of retry
    assert not situation.cursors
    situation.acknowledge('execution', retry)
    assert situation.prepare('execution', retained=[retry['delivery_id']]) is None
    assert situation.prepare('review')['mode'] == 'baseline'
    assert situation.prepare('execution', retained=[])['mode'] == 'baseline'


def test_budget_reports_omission_with_readable_reference(situation):
    for i in range(30):
        observe(situation, 'v' + str(i), i, {'kind': 'file', 'path': str(i)})
    payload = situation.prepare('execution', budget=2000)
    assert payload['omitted']['count'] > 0
    assert payload['read_result']['id']
    assert len(json.dumps(payload, ensure_ascii=False).encode()) <= 2000
    assert payload['size_method'] == 'utf8_bytes_limit_not_token_measurement'


def test_cancel_and_close_do_not_poll_or_deliver(situation):
    calls = []
    situation.watch('local', lambda: calls.append(1))
    situation.cancel_check = lambda: True
    assert situation.prepare('execution') is None and not calls
    situation.close()
    assert not situation.refreshers and not situation.pending
    before = situation.revision
    observe(situation, 'late', 1)
    assert situation.revision == before


def test_concurrent_results_keep_source_order(situation):
    observe(situation, 'first', 0)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda i: observe(situation, str(i), i), reversed(range(1, 50))))
    row = situation.snapshot()['observations'][0]
    assert row['first']['value'] == 'first' and row['latest']['source_cursor'] == 49


def test_unknown_effect_and_masked_data(situation):
    situation.tool_started('call', 'send', {'to': 'destination'})
    situation.tool_finished('call', {'exception': 'TimeoutError'}, unknown=True)
    row = situation.snapshot()['observations'][0]
    assert row['latest']['value']['state'] == 'result_missing'
    assert row['latest']['value']['effect'] == 'unknown'
    situation.observe({'kind': 'reply'}, 'data', {'api_key': 'do-not-publish'}, source='producer')
    assert 'do-not-publish' not in json.dumps(situation.snapshot())


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
