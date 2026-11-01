"""사전 고정 기준을 수동 판정·실측 비용에 적용한다. 의미 판정을 대신하지 않는다."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def read(name):
    return json.loads((HERE / name).read_text())

review = read('review.json')
evidence = read('evidence.json')
cases = read('cases.json')
rows = {(r['case'], r['arm']): r for r in review['rows']}
ranks = {'미충족': 0, '부분': 1, '충족': 2}
result = {}
for label, before, after, token_limit, time_limit in [
    ('B_vs_A', 'A', 'B', 1.25, 1.3),
    ('C_vs_B', 'B', 'C', 2.0, 2.0),
    ('C_vs_A', 'A', 'C', None, None),
]:
    changes = []
    for case in cases:
        cid = case['id']
        a, b = rows[(cid, before)], rows[(cid, after)]
        old = {x['id'] for x in a['defects']}
        new = {x['id'] for x in b['defects']}
        regression = [i + 1 for i, (x, y) in enumerate(zip(a['checks'], b['checks'])) if ranks[y] < ranks[x]]
        changes.append({'case': cid, 'kind': case['kind'], 'removed': sorted(old-new), 'added': sorted(new-old),
                        'check_regression': regression, 'improved': bool(old-new) and not new-old and not regression})
    p, q = evidence['paths'][before], evidence['paths'][after]
    tokens = lambda v: v['usage']['input'] + v['usage']['output']
    token_ratio = tokens(q) / tokens(p)
    time_ratio = q['median_seconds'] / p['median_seconds']
    gates = {
        'improved_at_least_two': sum(c['improved'] for c in changes) >= 2,
        'improved_at_least_one_new': any(c['improved'] and c['kind'] in {'new', 'control_new'} for c in changes),
        'no_new_defect_or_check_regression': not any(c['added'] or c['check_regression'] for c in changes),
        'token_limit': token_ratio <= token_limit if token_limit else None,
        'time_limit': time_ratio <= time_limit if time_limit else None,
    }
    result[label] = {'cases': changes, 'input_output_ratio': token_ratio, 'median_time_ratio': time_ratio, 'gates': gates,
                     'decision': 'reject' if any(v is False for v in gates.values()) else 'eligible_pending_review_audit_and_confirmation'}
result['adoption'] = 'none' if result['B_vs_A']['decision'] == 'reject' and result['C_vs_B']['decision'] == 'reject' else 'manual_confirmation_required'
result['limits'] = '각 사례 한 번의 비맹검 수동 판정이다. 일반 성공률·통계적 우월성·달러 비용으로 환산하지 않는다. C_vs_A에는 새 비용 한도를 사후 도입하지 않았다.'
(HERE / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(result, ensure_ascii=False, indent=2))
