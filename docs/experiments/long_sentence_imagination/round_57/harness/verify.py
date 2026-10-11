"""Read saved outputs and compare them to the original read-only ledger."""
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-11_57회차'
FIELDS = ('input', 'output', 'cache_read', 'cache_create', 'reasoning')


def read(path):
    return json.loads((OUT / path).read_text())


def main():
    base = read('trainer/base/result.json')
    after = read('trainer/after/result.json')
    ai = read('ai/base/trace_analysis_4595_4597.json')['runs']
    conn = sqlite3.connect((ROOT / 'data/world_pulse.db').as_uri() + '?mode=ro', uri=True)
    conn.execute('PRAGMA query_only=ON')
    summary = []
    for old, new, independent in zip(base, after, ai, strict=True):
        eid = old['episode_id']
        assert eid == new['episode_id'] == independent['episode_id']
        ids = lambda row: {event['source_record_id'] for event in row['events']}
        assert ids(old) == ids(new)
        assert len(ids(new)) == len(new['events']) == independent['events']['unique_rows']
        raw = [(kind, json.loads(data)) for kind, data in conn.execute(
            'SELECT kind,data FROM trajectory_event WHERE episode_id=? ORDER BY rowid', (eid,))]
        usage_rows = [data for kind, data in raw if kind == 'model.usage' and data.get('accounting') == 'billable_usage']
        expected = {key: sum(row.get(key, 0) for row in usage_rows) for key in FIELDS}
        assert expected == new['usage']['measured'] == independent['usage']['last_page_measured']
        assert len(usage_rows) == new['usage']['records']
        actual = Counter(e['kind'] for e in new['events'] if e['source'] == 'trajectory')
        assert actual == Counter(kind for kind, _ in raw)
        if new['failures']:
            original = conn.execute('SELECT log FROM episode_log WHERE id=?', (eid,)).fetchone()[0]
            assert new['log'] == original
        else:
            assert new['log'] == ''
        assert new['state']['goal_evaluations'][0]['status'] == {
            4595: 'achieved', 4596: 'not_evaluated', 4597: 'unknown'}[eid]
        summary.append({'episode_id': eid, 'events': len(new['events']), 'usage': expected,
                        'failures': len(new['failures']), 'candidates': len(new['candidates']),
                        'evidence_links': len(new['evidence'])})
    small = read('trainer/after_small/result.json')[0]
    assert ids(small) == ids(after[1])
    assert small['usage'] == after[1]['usage']
    assert read('trainer/after_empty/result.json') == []
    status = read('runs/ai_base_status.json')
    assert status['state'] == 'succeeded'
    billable = [json.loads(r[0]) for r in conn.execute(
        "SELECT data FROM trajectory_event WHERE episode_id=4606 AND kind='model.usage'")]
    billable = [r for r in billable if r.get('accounting') == 'billable_usage']
    ai_usage = {k: sum(r.get(k, 0) for r in billable) for k in FIELDS}
    elapsed = conn.execute('SELECT total_ms FROM episode_log WHERE id=4606').fetchone()[0]
    result = {'verified': True, 'runs': summary, 'independent_ai': {
        'episode_id': 4606, 'total_ms': elapsed, 'usage': ai_usage,
        'models': sorted({str(r.get('provider')) + '/' + str(r.get('model')) for r in billable})}}
    (OUT / 'runs/verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
