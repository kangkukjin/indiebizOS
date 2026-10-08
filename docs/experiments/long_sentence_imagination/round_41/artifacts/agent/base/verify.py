#!/usr/bin/env python3
"""저장된 산출물 검산: ① 제외+유효=전체 ② 조건 n = 가설 n ③ 판정 규칙 ④ 보고서 숫자 ⊆ stats/quality 값.
raw 자료에서 독립 재계산(제외·조건 평균·Welch)도 한다."""
import json, math, os, re, sys, csv, hashlib, statistics as st
BASE, OUT = sys.argv[1], sys.argv[2]
Q = json.load(open(os.path.join(OUT, 'quality.json'), encoding='utf-8'))
S = json.load(open(os.path.join(OUT, 'stats.json'), encoding='utf-8'))
M = json.load(open(os.path.join(OUT, 'manifest.json'), encoding='utf-8'))
R = open(os.path.join(OUT, 'report.md'), encoding='utf-8').read()
D = json.load(open(os.path.join(BASE, 'design.json'), encoding='utf-8'))
T = {int(r[0]): r for r in json.load(open(os.path.join(BASE, 't_critical.json')))['rows']}
res = {}
# ①
n_ex = len(Q['excluded'])
res['1_total_eq'] = Q['total_trials'] == Q['valid_trials'] + Q['excluded_trials'] and n_ex == Q['excluded_trials'] \
    and sum(Q['excluded_by_reason'].values()) == n_ex and sum(p['valid'] for p in Q['per_participant']) == Q['valid_trials']
# 독립 재계산: raw
grp = {r['id']: r['group'] for r in csv.DictReader(open(os.path.join(BASE, 'participants.csv'), encoding='utf-8'))}
units, tot, ex = {}, 0, 0
for fn in sorted(os.listdir(os.path.join(BASE, 'trials'))):
    d = json.load(open(os.path.join(BASE, 'trials', fn)))
    seen = set()
    for t in d['trials']:
        tot += 1
        dup = t['trial_id'] in seen; seen.add(t['trial_id'])
        du, er = t['duration_s'], t['errors']
        ok = (not dup) and type(du) in (int, float) and 0 < du <= 600 and type(er) in (int, float)
        if not ok:
            ex += 1; continue
        units.setdefault((grp[d['participant']], t['task_type']), {}).setdefault(d['participant'], []).append(du)
res['1_raw_recount'] = (tot, ex) == (Q['total_trials'], Q['excluded_trials'])
C = {c['condition']: c for c in S['conditions']}
ok2 = True
for (g, tk), u in units.items():
    xs = [sum(v) / len(v) for v in u.values()]
    c = C[f'{g}-{tk}']
    ok2 &= c['n'] == len(xs) and abs(c['mean'] - st.mean(xs)) < 1e-3 and abs(c['sd'] - st.stdev(xs)) < 1e-3
    h = T[len(xs) - 1][1] * st.stdev(xs) / math.sqrt(len(xs))
    ok2 &= abs(c['ci_low'] - (st.mean(xs) - h)) < 1e-3
res['2_conditions_recomputed'] = ok2
# ②
SAT = {s['group']: s for s in S['satisfaction']}
ok = True
for h in S['hypotheses']:
    if h['measure'] == 'duration':
        a, b = C[f"A-{h['task']}"], C[f"B-{h['task']}"]
    else:
        a, b = SAT['A'], SAT['B']
    ok &= (h['nA'], h['nB']) == (a['n'], b['n'])
    if 'mA' in h:
        ok &= (h['mA'], h['mB'], h['sdA'], h['sdB']) == (a['mean'], b['mean'], a['sd'], b['sd'])
res['2_n_match'] = ok
# ③
ok = True
for h in S['hypotheses']:
    if min(h['nA'], h['nB']) < S['min_n']:
        ok &= h['verdict'] == '검정 불가'; continue
    va, vb = h['sdA'] ** 2 / h['nA'], h['sdB'] ** 2 / h['nB']
    t = (h['mB'] - h['mA']) / math.sqrt(va + vb)
    df = math.floor((va + vb) ** 2 / (va ** 2 / (h['nA'] - 1) + vb ** 2 / (h['nB'] - 1)))
    crit = T[df][2]
    sp = math.sqrt(((h['nA'] - 1) * h['sdA'] ** 2 + (h['nB'] - 1) * h['sdB'] ** 2) / (h['nA'] + h['nB'] - 2))
    want = -1 if h['direction'] == 'B<A' else 1
    v = '지지' if abs(t) > crit and t * want > 0 else '불지지(반대 방향 유의)' if abs(t) > crit else '불지지(차이 없음 입증 아님)'
    ok &= df == h['df'] and crit == h['crit_p0125'] and abs(t - h['t']) < 1e-3 and abs((h['mB'] - h['mA']) / sp - h['d']) < 1e-3 and v == h['verdict']
res['3_verdicts'] = ok
# 설문 독립 재계산
sv = {}
for r in csv.DictReader(open(os.path.join(BASE, 'survey.csv'), encoding='utf-8')):
    sv[r['participant']] = st.mean([(6 - int(r[q])) if q in ('Q3', 'Q6') else int(r[q]) for q in D['survey']['items']])
ok = True
for g in ('A', 'B'):
    xs = [sv[p] for p in grp if grp[p] == g and p in sv]
    ok &= SAT[g]['n'] == len(xs) and abs(SAT[g]['mean'] - st.mean(xs)) < 1e-3
res['4_survey_recomputed'] = ok and sorted(set(grp) - set(sv)) == Q['survey_missing_participants']
# ④ 보고서 소수점 숫자 ⊆ 저장 값
vals = set()
def walk(x):
    if isinstance(x, dict): [walk(v) for v in x.values()]
    elif isinstance(x, list): [walk(v) for v in x]
    elif isinstance(x, (int, float)) and not isinstance(x, bool): vals.add(repr(x)); vals.add(repr(float(x)))
walk(S); walk(Q)
nums = re.findall(r'(?<![\w.])-?\d+\.\d+', R.split('## 방법')[0] + R.split('## 결과')[1])
bad = [n for n in nums if n not in vals]
res['4_report_numbers_in_json'] = not bad
res['4_bad_numbers'] = bad
res['report_refs_figs'] = all(f in R for f in ('fig1_duration_by_condition.png', 'fig2_satisfaction_by_group.png'))
res['no_proof_of_null_claim'] = '차이 없음을 입증' not in R.replace('차이가 없다는 것을 입증하지 않는다', '')
res['sections'] = all(s in R for s in ('## 초록', '## 방법', '## 결과', '### 자료 품질', '### 조건별', '### 가설 검정', '### 그림', '## 가설별 결론', '## 한계'))
# manifest
inputs = ['design.json', 'participants.csv', 'survey.csv', 't_critical.json'] + ['trials/' + f for f in sorted(os.listdir(os.path.join(BASE, 'trials')))]
mh = {i['path']: i['sha256'] for i in M['inputs']}
res['manifest_inputs'] = len(mh) == len(inputs) and all(mh.get(p) == hashlib.sha256(open(os.path.join(BASE, p), 'rb').read()).hexdigest() for p in inputs)
res['manifest_outputs'] = all(o['sha256'] == hashlib.sha256(open(os.path.join(OUT, o['file']), 'rb').read()).hexdigest() for o in M['outputs'])
res['run_id_consistent'] = M['run_id'] == S['run_id'] == Q['run_id']
res['ALL_OK'] = all(v for k, v in res.items() if k != '4_bad_numbers')
print(json.dumps(res, ensure_ascii=False))
