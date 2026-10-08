#!/usr/bin/env python3
"""A/B 인터페이스 실험 분석 — design.json 사전등록 규칙 그대로.
사용: python3 -I analyze.py <base> <out>
"""
import csv, hashlib, json, math, os, sys, datetime

BASE, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
SCRIPT = os.path.abspath(__file__)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def r(x, k=4):
    return None if x is None else round(x, k)


design = json.load(open(os.path.join(BASE, 'design.json'), encoding='utf-8'))
tcj = json.load(open(os.path.join(BASE, 't_critical.json'), encoding='utf-8'))
cols = tcj['columns']
TCRIT = {int(row[cols.index('df')]): {'p05': row[cols.index('p05')], 'p0125': row[cols.index('p0125')]} for row in tcj['rows']}
ALPHA = design['correction']['alpha_adjusted']
MIN_N = design['min_n_per_condition']
EX = design['exclusion']
REV = design['survey']['reverse']
ITEMS = design['survey']['items']
LO, HI = design['survey']['scale']

run_ts = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
RUN_ID = f"{run_ts}-{sha(SCRIPT)[:12]}"

# ---- 참가자 명부
with open(os.path.join(BASE, 'participants.csv'), encoding='utf-8', newline='') as f:
    participants = list(csv.DictReader(f))
GROUP = {p['id']: p['group'] for p in participants}
PIDS = [p['id'] for p in participants]

# ---- trial 제외
trial_dir = os.path.join(BASE, 'trials')
trial_files = sorted(fn for fn in os.listdir(trial_dir) if fn.endswith('.json'))
excluded, valid = [], []
total_trials = 0
per_part = {}
group_mismatch = []
missing_records = []  # 설계상 과제별 4회인데 파일에 기록이 없는 trial(제외가 아닌 결측)
for fn in trial_files:
    d = json.load(open(os.path.join(trial_dir, fn), encoding='utf-8'))
    pid, grp = d.get('participant'), d.get('group')
    if GROUP.get(pid) != grp:
        group_mismatch.append({'file': fn, 'participant': pid, 'file_group': grp, 'roster_group': GROUP.get(pid)})
    seen = set()
    cnt = {'total': 0, 'valid': 0, 'excluded': 0}
    slots = {(t.get('task_type'), t.get('rep')) for t in d.get('trials', [])}
    for tk in ('T1', 'T2', 'T3'):
        for rp in range(1, 5):
            if (tk, rp) not in slots:
                missing_records.append({'file': fn, 'participant': pid, 'task_type': tk, 'rep': rp})
    for t in d.get('trials', []):
        total_trials += 1
        cnt['total'] += 1
        tid = t.get('trial_id')
        reasons = []
        if tid in seen:
            reasons.append('duplicate_trial_id')
        seen.add(tid)
        dur, err = t.get('duration_s'), t.get('errors')
        if not is_num(dur):
            reasons.append('duration_not_numeric')
        elif dur <= EX['duration_min_exclusive']:
            reasons.append('duration_le_0')
        elif dur > EX['duration_max_inclusive']:
            reasons.append('duration_gt_600')
        if EX.get('errors_must_be_numeric') and not is_num(err):
            reasons.append('errors_not_numeric')
        if reasons:
            cnt['excluded'] += 1
            excluded.append({'file': fn, 'participant': pid, 'trial_id': tid, 'task_type': t.get('task_type'),
                             'reason': reasons[0], 'all_reasons': reasons,
                             'duration_s': dur, 'errors': err})
        else:
            cnt['valid'] += 1
            valid.append({'participant': pid, 'group': GROUP.get(pid, grp), 'task': t.get('task_type'),
                          'duration_s': dur})
    per_part[pid] = cnt

reason_counts = {k: 0 for k in ('duplicate_trial_id', 'duration_not_numeric', 'duration_le_0', 'duration_gt_600', 'errors_not_numeric')}
for e in excluded:
    reason_counts[e['reason']] = reason_counts.get(e['reason'], 0) + 1

# ---- 분석 단위: 참가자×과제 평균
units = {}
for v in valid:
    units.setdefault((v['group'], v['task'], v['participant']), []).append(v['duration_s'])
unit_mean = {k: sum(x) / len(x) for k, x in units.items()}
TASKS = sorted({v['task'] for v in valid})
GROUPS = sorted(set(GROUP.values()))
unit_counts = {pid: {t: len(units.get((GROUP[pid], t, pid), [])) for t in TASKS} for pid in PIDS}


def desc(xs):
    n = len(xs)
    m = sum(xs) / n if n else None
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n >= 2 else None
    out = {'n': n, 'mean': m, 'sd': sd, 'ci_low': None, 'ci_high': None, 't_p05': None, 'df': n - 1 if n else None}
    if n >= 2:
        tc = TCRIT[n - 1]['p05']
        half = tc * sd / math.sqrt(n)
        out.update(ci_low=m - half, ci_high=m + half, t_p05=tc, half_width=half)
    return out


cond_vals = {(g, t): [unit_mean[(g, t, p)] for p in PIDS if (g, t, p) in unit_mean] for g in GROUPS for t in TASKS}
conditions = []
for g in GROUPS:
    for t in TASKS:
        d = desc(cond_vals[(g, t)])
        conditions.append({'condition': f'{g}-{t}', 'group': g, 'task': t, **{k: r(v) for k, v in d.items()}})
low_n = [c['condition'] for c in conditions if c['n'] < MIN_N]

# ---- 설문
with open(os.path.join(BASE, 'survey.csv'), encoding='utf-8', newline='') as f:
    srows = list(csv.DictReader(f))
survey_by = {}
survey_issues = []
for row in srows:
    pid = row['participant'].strip()
    vals, bad = [], []
    for q in ITEMS:
        raw = (row.get(q) or '').strip()
        try:
            x = float(raw)
            if not (LO <= x <= HI):
                bad.append(f'{q}={raw}(범위밖)')
                x = None
        except ValueError:
            bad.append(f'{q}={raw!r}')
            x = None
        vals.append(x)
    if pid in survey_by:
        survey_issues.append({'participant': pid, 'issue': 'duplicate_row_ignored'})
        continue
    if bad:
        survey_issues.append({'participant': pid, 'issue': 'invalid_items', 'detail': bad})
        if all(v is None for v in vals):
            continue
    if any(v is None for v in vals):
        continue  # 7문항 평균을 만들 수 없음 → 만족도 결측
    adj = [(LO + HI - v) if q in REV else v for q, v in zip(ITEMS, vals)]
    survey_by[pid] = sum(adj) / len(adj)
no_survey = [p for p in PIDS if p not in survey_by]
unknown_survey = sorted({row['participant'].strip() for row in srows} - set(PIDS))
sat_vals = {g: [survey_by[p] for p in PIDS if GROUP[p] == g and p in survey_by] for g in GROUPS}
satisfaction = []
for g in GROUPS:
    d = desc(sat_vals[g])
    satisfaction.append({'group': g, **{k: r(v) for k, v in d.items()}})


# ---- 가설 검정
def welch(a, b, direction):
    nA, nB = len(a), len(b)
    res = {'nA': nA, 'nB': nB}
    if nA < MIN_N or nB < MIN_N:
        res['verdict'] = '검정 불가'
        res['reason'] = f'n<{MIN_N}'
        return res
    dA, dB = desc(a), desc(b)
    vA, vB = dA['sd'] ** 2 / nA, dB['sd'] ** 2 / nB
    se = math.sqrt(vA + vB)
    diff = dB['mean'] - dA['mean']
    t = diff / se
    df_raw = (vA + vB) ** 2 / (vA ** 2 / (nA - 1) + vB ** 2 / (nB - 1))
    df = math.floor(df_raw)
    crit = TCRIT[df]['p0125']
    sp = math.sqrt(((nA - 1) * dA['sd'] ** 2 + (nB - 1) * dB['sd'] ** 2) / (nA + nB - 2))
    dval = diff / sp
    sig = abs(t) > crit
    expected_sign = -1 if direction == 'B<A' else 1
    match = (t * expected_sign) > 0
    if sig and match:
        verdict = '지지'
    elif sig:
        verdict = '불지지(반대 방향 유의)'
    else:
        verdict = '불지지(차이 없음 입증 아님)'
    res.update(mA=dA['mean'], sdA=dA['sd'], mB=dB['mean'], sdB=dB['sd'], diff_BminusA=diff, se=se, t=t,
               df_welch=df_raw, df=df, crit_p0125=crit, abs_t_gt_crit=sig, pooled_sd=sp, d=dval,
               expected_sign='음(t<0)' if expected_sign < 0 else '양(t>0)', direction_match=match, verdict=verdict)
    return {k: (r(v) if isinstance(v, float) else v) for k, v in res.items()}


hyps = []
for h in design['hypotheses']:
    if h['measure'] == 'duration':
        a, b = cond_vals[('A', h['task'])], cond_vals[('B', h['task'])]
        src = f"조건 A-{h['task']} vs B-{h['task']} (참가자별 유효 trial 평균 완료시간, 초)"
    else:
        a, b = sat_vals['A'], sat_vals['B']
        src = '집단별 만족도(Q3·Q6 역문항 반전 후 7문항 평균, 설문 미응답 제외)'
    hyps.append({'id': h['id'], 'text': h['text'], 'measure': h['measure'], 'task': h['task'],
                 'direction': h['direction'], 'compares': src, **welch(a, b, h['direction'])})

# ---- quality.json
quality = {
    'run_id': RUN_ID,
    'total_trials': total_trials,
    'valid_trials': len(valid),
    'excluded_trials': len(excluded),
    'check_total_eq_valid_plus_excluded': total_trials == len(valid) + len(excluded),
    'excluded_by_reason': reason_counts,
    'expected_trials_by_design': len(PIDS) * 12,
    'missing_trial_records': missing_records,
    'missing_note': '파일에 아예 없는 trial 은 제외가 아니라 결측이며 total_trials 에 포함되지 않는다',
    'reason_rule': '여러 사유가 겹치면 첫 사유(중복→완료시간→errors 순)로 1회만 계수, all_reasons 에 전부 기록',
    'excluded': excluded,
    'per_participant': [{'participant': p, 'group': GROUP[p], **per_part.get(p, {'total': 0, 'valid': 0, 'excluded': 0}),
                         'valid_by_task': unit_counts[p]} for p in PIDS],
    'participants_without_trial_file': [p for p in PIDS if p not in per_part],
    'participants_with_no_valid_trial_in_task': [{'participant': p, 'task': t} for p in PIDS for t in TASKS if unit_counts[p][t] == 0],
    'group_mismatch_file_vs_roster': group_mismatch,
    'survey_missing_participants': no_survey,
    'survey_issues': survey_issues,
    'survey_unknown_participants': unknown_survey,
    'min_n_per_condition': MIN_N,
    'conditions_n': {c['condition']: c['n'] for c in conditions},
    'conditions_below_min_n': low_n,
}
json.dump(quality, open(os.path.join(OUT, 'quality.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

stats = {
    'run_id': RUN_ID,
    'alpha': design['alpha'], 'alpha_adjusted': ALPHA, 'min_n': MIN_N,
    'rounding': '모든 실수는 소수 4자리 반올림 저장, 판정은 반올림 전 값으로 수행',
    'conditions': conditions,
    'satisfaction': satisfaction,
    'hypotheses': hyps,
}
json.dump(stats, open(os.path.join(OUT, 'stats.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---- 저장본 재독(이후 그림·보고서는 저장본 값만 사용)
S = json.load(open(os.path.join(OUT, 'stats.json'), encoding='utf-8'))
Q = json.load(open(os.path.join(OUT, 'quality.json'), encoding='utf-8'))

# ---- 그림
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.family'] = ['AppleGothic', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
FIG1, FIG2 = 'fig1_duration_by_condition.png', 'fig2_satisfaction_by_group.png'
colors = {'A': '#4C72B0', 'B': '#DD8452'}
fig, ax = plt.subplots(figsize=(7, 4.5))
w = 0.35
for i, g in enumerate(GROUPS):
    cs = [c for c in S['conditions'] if c['group'] == g]
    xs = [TASKS.index(c['task']) + (i - 0.5) * w for c in cs]
    ms = [c['mean'] for c in cs]
    err = [[c['mean'] - c['ci_low'] for c in cs], [c['ci_high'] - c['mean'] for c in cs]]
    ax.bar(xs, ms, w, yerr=err, capsize=4, color=colors.get(g), label=f'인터페이스 {g}')
    for x, c in zip(xs, cs):
        ax.text(x, c['ci_high'], f"n={c['n']}", ha='center', va='bottom', fontsize=8)
ax.set_xticks(range(len(TASKS)))
ax.set_xticklabels(TASKS)
ax.set_ylabel('평균 완료시간 (초)')
ax.set_title('조건별 평균 완료시간과 95% 신뢰구간')
ax.legend()
fig.tight_layout()
fig.savefig(os.path.join(OUT, FIG1), dpi=150)
plt.close(fig)

fig, ax = plt.subplots(figsize=(5, 4.5))
for i, s in enumerate(S['satisfaction']):
    g = s['group']
    pts = sat_vals[g]
    ax.scatter([i + (k % 7 - 3) * 0.025 for k in range(len(pts))], pts, s=12, alpha=0.5, color=colors.get(g))
    ax.errorbar(i + 0.25, s['mean'], yerr=[[s['mean'] - s['ci_low']], [s['ci_high'] - s['mean']]], fmt='o',
                color='black', capsize=5)
    ax.text(i + 0.3, s['mean'], f" {s['mean']:.4f}\n n={s['n']}", va='center', fontsize=8)
ax.set_xticks(range(len(GROUPS)))
ax.set_xticklabels([f'인터페이스 {g}' for g in GROUPS])
ax.set_ylim(LO - 0.2, HI + 0.2)
ax.set_xlim(-0.5, len(GROUPS) - 0.2)
ax.set_ylabel('만족도 (7문항 평균, Q3·Q6 반전)')
ax.set_title('집단별 만족도: 참가자 점수와 평균 ± 95% CI')
fig.tight_layout()
fig.savefig(os.path.join(OUT, FIG2), dpi=150)
plt.close(fig)


# ---- report.md (숫자는 저장본 S·Q 의 값을 그대로)
def f(x):
    return '—' if x is None else (f'{x}' if not isinstance(x, float) else repr(x))


C = {c['condition']: c for c in S['conditions']}
H = {h['id']: h for h in S['hypotheses']}
SAT = {s['group']: s for s in S['satisfaction']}
L = []
A = L.append
A(f"# {design['title']} — 연구 보고서\n")
A(f"실행 식별자: `{S['run_id']}` · 수치 출처: `stats.json`, `quality.json` (소수 4자리 반올림 값)\n")
A('## 초록\n')
sup = [h['id'] for h in S['hypotheses'] if h['verdict'] == '지지']
abst = (f"60명({', '.join(f'{g} {sum(1 for p in PIDS if GROUP[p]==g)}명' for g in GROUPS)})이 인터페이스 A 또는 B로 과제 T1~T3을 각 4회 수행했다. "
        f"전체 {Q['total_trials']}개 trial 중 {Q['excluded_trials']}개를 사전등록 제외 규칙으로 제외하고 {Q['valid_trials']}개를 분석했다. "
        f"Bonferroni 보정 유의수준 α={S['alpha_adjusted']}에서 Welch t 검정을 수행한 결과, ")
parts = []
for h in S['hypotheses']:
    if h['verdict'] == '검정 불가':
        parts.append(f"{h['id']}는 검정 불가(n<{S['min_n']})")
    else:
        parts.append(f"{h['id']}는 {h['verdict']}(t={f(h['t'])}, df={h['df']}, 임계값 {f(h['crit_p0125'])}, d={f(h['d'])})")
abst += '; '.join(parts) + '. '
abst += ('지지된 가설: ' + ', '.join(sup) + '.') if sup else '지지된 가설은 없다.'
A(abst + '\n')

A('## 방법\n')
A(f"- 설계: 참가자 간 2집단(인터페이스 A/B) × 과제 3종(T1·T2·T3), 과제당 4회 반복. 집단 배정은 `participants.csv` 의 group.")
A(f"- 제외 규칙(design.json): 완료시간 ≤ {EX['duration_min_exclusive']}초 또는 > {EX['duration_max_inclusive']}초, errors 가 수가 아님(수치가 아닌 문자열·null·불리언 포함), 같은 파일 안 중복 trial_id 는 첫 trial 만 유효. 여러 사유가 겹친 trial 은 한 번만 세고 첫 사유(중복→완료시간→errors 순)로 분류했다. 완료시간이 수가 아닌 trial 도 완료시간 규칙으로 제외한다. `completed` 필드는 제외 규칙에 없어 사용하지 않았다.")
A(f"- 분석 단위: {design['unit_of_analysis']}. 조건당 최소 n={S['min_n']}.")
A(f"- 기술통계: n, 평균, 표본 표준편차(n−1), 95% CI = 평균 ± t(p05, n−1)·sd/√n. 임계값은 `t_critical.json` 에서 조회.")
A(f"- 검정: Welch t = (m_B − m_A)/√(s_A²/n_A + s_B²/n_B), 자유도 Welch–Satterthwaite 내림, 양측 임계값 `t_critical.json` p0125 (α={S['alpha']}, Bonferroni {design['correction']['tests']}회 → {S['alpha_adjusted']}). |t| > 임계값이면 유의.")
A("- 방향: H1~H3 은 'B<A'(B 가 더 빠름)이므로 t<0 이 방향 일치, H4 는 'B>A' 이므로 t>0 이 방향 일치.")
A("- 효과크기: Cohen's d = (m_B − m_A)/s_pooled, s_pooled = √(((n_A−1)s_A² + (n_B−1)s_B²)/(n_A+n_B−2)). 부호는 t 와 같다.")
A("- 판정: 유의하고 방향 일치=지지 / 유의하지만 반대=불지지(반대 방향 유의) / 비유의=불지지(차이 없음 입증 아님) / 어느 집단이든 n<8=검정 불가.")
A(f"- 만족도: Q3·Q6 을 6−x 로 반전한 뒤 Q1~Q7 평균. 설문 응답이 없는 참가자(또는 7문항 중 결측·범위 밖 값이 있는 참가자)는 H4 에서 제외.")
A("- 사용자 지시와 design.json 사이에 규칙 차이는 발견되지 않았다.\n")

A('## 결과\n')
A('### 자료 품질\n')
A(f"전체 trial {Q['total_trials']}개 = 유효 {Q['valid_trials']}개 + 제외 {Q['excluded_trials']}개. 설계상 기대 trial 은 {Q['expected_trials_by_design']}개이며, 파일에 기록 자체가 없는 결측 trial 은 {len(Q['missing_trial_records'])}개다" + (': ' + ', '.join(f"{m['file']} {m['task_type']} rep {m['rep']}" for m in Q['missing_trial_records']) if Q['missing_trial_records'] else '') + '(제외 건수에 넣지 않음).\n')
A('| 제외 사유 | 건수 |\n|---|---|')
for k, v in Q['excluded_by_reason'].items():
    A(f'| {k} | {v} |')
A('\n| 파일 | trial_id | 과제 | 사유 | duration_s | errors |\n|---|---|---|---|---|---|')
for e in Q['excluded']:
    A(f"| {e['file']} | {e['trial_id']} | {e['task_type']} | {', '.join(e['all_reasons'])} | {json.dumps(e['duration_s'], ensure_ascii=False)} | {json.dumps(e['errors'], ensure_ascii=False)} |")
A('\n참가자별 유효 trial 수(전체 12개 중; 12개 미만인 참가자만 표기, 나머지는 12개 전부 유효):\n')
A('| 참가자 | 집단 | 유효/전체 | 과제별 유효 |\n|---|---|---|---|')
for p in Q['per_participant']:
    if p['valid'] != p['total'] or p['total'] != 12:
        A(f"| {p['participant']} | {p['group']} | {p['valid']}/{p['total']} | {', '.join(f'{t}:{n}' for t, n in p['valid_by_task'].items())} |")
full = sum(1 for p in Q['per_participant'] if p['valid'] == p['total'] == 12)
A(f"\n유효 trial 12개 전부인 참가자: {full}명. 전체 목록은 `quality.json` 의 per_participant.")
nz = Q['participants_with_no_valid_trial_in_task']
A(f"- 특정 과제의 유효 trial 이 0개여서 그 조건의 분석 단위에서 빠진 참가자: {', '.join(x['participant']+'('+x['task']+')' for x in nz) if nz else '없음'}.")
A(f"- 설문 응답 없는 참가자: {', '.join(Q['survey_missing_participants']) if Q['survey_missing_participants'] else '없음'} ({len(Q['survey_missing_participants'])}명).")
if Q['survey_issues']:
    A(f"- 설문 이상값: {json.dumps(Q['survey_issues'], ensure_ascii=False)}")
if Q['group_mismatch_file_vs_roster']:
    A(f"- 파일과 명부의 집단 불일치: {json.dumps(Q['group_mismatch_file_vs_roster'], ensure_ascii=False)} (명부 group 사용)")
A(f"- n<{S['min_n']} 인 조건: {', '.join(Q['conditions_below_min_n']) if Q['conditions_below_min_n'] else '없음'}.\n")

A('### 조건별 기술통계 (완료시간, 초; 분석 단위 = 참가자별 유효 trial 평균)\n')
A('| 조건 | n | 평균 | sd | t(p05, n−1) | 95% CI 하한 | 95% CI 상한 |\n|---|---|---|---|---|---|---|')
for c in S['conditions']:
    A(f"| {c['condition']} | {c['n']} | {f(c['mean'])} | {f(c['sd'])} | {f(c['t_p05'])} | {f(c['ci_low'])} | {f(c['ci_high'])} |")
A('\n### 만족도 기술통계 (Q3·Q6 반전 후 7문항 평균)\n')
A('| 집단 | n | 평균 | sd | t(p05, n−1) | 95% CI 하한 | 95% CI 상한 |\n|---|---|---|---|---|---|---|')
for s in S['satisfaction']:
    A(f"| {s['group']} | {s['n']} | {f(s['mean'])} | {f(s['sd'])} | {f(s['t_p05'])} | {f(s['ci_low'])} | {f(s['ci_high'])} |")
A('\n### 가설 검정 (Welch t, α=' + f"{S['alpha_adjusted']}" + ')\n')
A('| 가설 | 방향 | n_A | m_A | sd_A | n_B | m_B | sd_B | t | df(내림) | 임계값 p0125 | Cohen d | 판정 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|')
for h in S['hypotheses']:
    A(f"| {h['id']} | {h['direction']} | {h['nA']} | {f(h.get('mA'))} | {f(h.get('sdA'))} | {h['nB']} | {f(h.get('mB'))} | {f(h.get('sdB'))} | {f(h.get('t'))} | {f(h.get('df'))} | {f(h.get('crit_p0125'))} | {f(h.get('d'))} | {h['verdict']} |")
A('\n### 그림\n')
A(f"- 그림 1 `{FIG1}`: 조건별 평균 완료시간과 95% 신뢰구간(오차막대).\n\n![그림 1]({FIG1})\n")
A(f"- 그림 2 `{FIG2}`: 집단별 만족도 — 참가자 점수(점)와 평균 ± 95% CI.\n\n![그림 2]({FIG2})\n")

A('## 가설별 결론\n')
for h in S['hypotheses']:
    if h['verdict'] == '검정 불가':
        A(f"- **{h['id']}** ({h['text']}): 검정 불가 — n_A={h['nA']}, n_B={h['nB']} 로 최소 n={S['min_n']} 미달.")
        continue
    dirn = '방향 일치' if h['direction_match'] else '방향 반대'
    s = (f"- **{h['id']}** ({h['text']}): m_B − m_A = {f(h['diff_BminusA'])}, t={f(h['t'])}, df={h['df']}, |t| {'>' if h['abs_t_gt_crit'] else '≤'} 임계값 {f(h['crit_p0125'])}, d={f(h['d'])} ({dirn}). 판정: **{h['verdict']}**.")
    if h['verdict'].startswith('불지지(차이'):
        s += ' 보정 유의수준에서 차이를 검출하지 못했다는 뜻이며, 두 인터페이스가 같다는 증거는 아니다.'
    elif h['verdict'].startswith('불지지(반대'):
        s += ' 가설과 반대 방향의 차이가 보정 유의수준에서 유의했다.'
    A(s)

A('\n## 한계\n')
A('- p 값은 계산하지 않고 t_critical.json 임계값과의 비교로만 유의성을 판정했다(사전등록 규칙).')
A('- 분석 단위를 참가자별 평균으로 접어 반복 측정 내 변동과 학습 효과(rep)는 모형화하지 않았다. 제외로 참가자마다 평균에 들어간 trial 수가 다르다.')
A('- errors·completed·age_band·experience 는 사전등록 가설에 없어 분석하지 않았다. completed=false 인 trial 도 제외 규칙에 해당하지 않으면 포함했다.')
A('- 비유의 결과는 차이가 없다는 것을 입증하지 않는다(동등성 검정 미수행). Bonferroni 보정은 보수적이어서 검정력이 낮아질 수 있다.')
A('- 만족도는 설문 응답자만으로 계산했으며 미응답이 무작위가 아니면 편향될 수 있다.')
A('- 이전 실행의 out 폴더가 주어지지 않은 첫 실행이어서 changelog.md 는 만들지 않았다.')
open(os.path.join(OUT, 'report.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')

# ---- manifest.json
inputs = [os.path.join(BASE, x) for x in ('design.json', 'participants.csv', 'survey.csv', 't_critical.json')] + \
         [os.path.join(trial_dir, fn) for fn in trial_files]
manifest = {
    'run_id': RUN_ID,
    'run_id_rule': '실행 시각(로컬, %Y%m%dT%H%M%S) + 분석 스크립트 sha256 앞 12자',
    'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
    'script': {'path': SCRIPT, 'sha256': sha(SCRIPT)},
    'python': sys.version.split()[0], 'matplotlib': matplotlib.__version__,
    'inputs': [{'path': os.path.relpath(p, BASE), 'sha256': sha(p), 'bytes': os.path.getsize(p)} for p in inputs],
    'input_count': len(inputs),
    'artifacts': [
        {'name': '자료 품질표', 'file': 'quality.json', 'sources': ['trials/P01.json~P60.json', 'participants.csv', 'survey.csv', 'design.json'],
         'rule': 'design.json exclusion: duration ≤0 또는 >600, errors 비수치, 파일 내 중복 trial_id 둘째 이후 제외; 참가자별 유효 수; 설문 미응답; 조건 n<min_n'},
        {'name': '조건 표', 'file': 'stats.json#conditions', 'sources': ['trials/*.json', 'participants.csv', 't_critical.json', 'design.json'],
         'rule': '참가자×과제 유효 trial 평균 → 조건별 n·평균·표본 sd·평균±t(p05,n−1)·sd/√n'},
        {'name': '만족도 표', 'file': 'stats.json#satisfaction', 'sources': ['survey.csv', 'participants.csv', 't_critical.json', 'design.json'],
         'rule': 'Q3·Q6 → 6−x 반전, 7문항 평균, 미응답 제외, 집단별 n·평균·sd·95% CI'},
        {'name': '가설 표', 'file': 'stats.json#hypotheses', 'sources': ['stats.json#conditions', 'stats.json#satisfaction', 't_critical.json', 'design.json'],
         'rule': 'Welch t=(mB−mA)/√(sA²/nA+sB²/nB), df Welch–Satterthwaite 내림, |t|>p0125 임계값, Cohen d pooled sd, 4단계 판정(n<8 검정 불가)'},
        {'name': '그림 1', 'file': FIG1, 'sources': ['stats.json#conditions'], 'rule': '조건별 평균 막대 + 95% CI 오차막대'},
        {'name': '그림 2', 'file': FIG2, 'sources': ['stats.json#satisfaction', 'survey.csv'], 'rule': '참가자별 만족도 점 + 집단 평균 ± 95% CI'},
        {'name': '보고서', 'file': 'report.md', 'sources': ['stats.json', 'quality.json', FIG1, FIG2], 'rule': '저장된 stats.json·quality.json 을 다시 읽어 값 그대로 기재'},
    ],
    'outputs': [{'file': x, 'sha256': sha(os.path.join(OUT, x))} for x in ('quality.json', 'stats.json', 'report.md', FIG1, FIG2)],
    'changelog': '이전 실행 out 미제공 — 비교 대상 없음, changelog.md 미생성',
}
json.dump(manifest, open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps({'run_id': RUN_ID, 'total': total_trials, 'valid': len(valid), 'excluded': len(excluded),
                  'reasons': reason_counts, 'low_n': low_n, 'no_survey': no_survey,
                  'hyp': [(h['id'], h.get('t'), h.get('df'), h.get('crit_p0125'), h.get('d'), h['verdict']) for h in hyps]},
                 ensure_ascii=False))
