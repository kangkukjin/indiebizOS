#!/usr/bin/env python3
"""IBL 조합률 측정 — 총량이 아니라 **성분**을 잰다 (2026-08-21 신설 / 2026-08-22 성분 분리).

왜 총량을 믿지 않는가: 08-21~22 실측에서 조합률이 12.0%→29.2% 로 뛰었는데, 오른 것은
표 꼬리(`소스 >> table:*`) 한 칸뿐이고 팬아웃은 오히려 내려갔으며 다단 파이프는 불변(1.3%)이었다.
총 조합률 하나로는 이 셋이 구분되지 않는다. 그래서 이 측정기는 네 층 × 일곱 칸으로 가른다.

  4층 — 교재(코퍼스) → 회상(프롬프트 주입 ref) → 실행(execute_ibl) → 표면(계기판 파싱)
        층 사이 낙차가 병목의 위치다. 세 층이 평평하면 병목은 맨 위(교재)다.
  7칸 — 단일 / 표꼬리 / 다단 / 팬아웃(동일)·(이종) / 제어 / 변수
        같은 '조합'이라도 표꼬리·팬아웃은 아래 칸, 다단·제어·변수가 프로그램 칸이다.

★기준선(2026-08-22 갈아 끼움) — 개입(08-21 조합 결핍 배치 `a473151`~`abf7aa9` · 08-22 M1~M6)이
옛 기준선 창(08-16~21) **안에서** 일어나, 옛 "조합 15%" 는 두 체제의 평균이었다. 대조군으로 못 쓴다.
날짜로 못 박는다(슬라이딩 N 창은 기준선이 될 수 없다 — 개입일이 창 안으로 들어온다):

  배치 전 2026-08-16~20 (n=818):  조합 12.0% (system_ai 8.9%)
      표꼬리 3.2% · 다단 1.3% · 팬아웃 7.8% · 제어 0.0%(0건) · 변수 0.0%(0건)
  배치 직후 2026-08-21~22 (n=469):  조합 29.2% (system_ai 29.7%)
      표꼬리 18.8% · 다단 1.3% · 팬아웃 6.6% · 제어 1.7%(8건) · 변수 1.7%(8건)
      ※ 08-22 는 진행 중인 날이라 확정치가 아니다.

착시가 아님을 확인한 방법(재측정 때도 같이 볼 것): ①system_ai 단독으로도 같은 계단이 난다
(8.9→29.7) → 주체 구성 착시 아님 ②배치 후 파이프 99건이 서로 다른 50가지 모양 → 한 습관의
반복 아님 ③팬아웃은 오히려 하락 → "무엇이든 붙이는 버릇"이 는 게 아니라 붙이는 자리가 옮겨간 것.

감시 대상은 총 조합률이 아니라 **다단·제어·변수 세 칸**이다. 총 조합률은 표꼬리 하나가
흔들어 놓아 신호가 약하다. 제어·변수는 0 을 벗어난 것 자체가 사건이므로 비율보다 건수를 본다.

정의(핀 고정 — 바꾸면 과거 수치와 비교 불가, 반드시 이 줄을 함께 고칠 것):
  조합 = `>>` | `} & [` | `??` | `[if:` | `[case:` | `[repeat:` | `[table:each]` | `goal:`
  ※ `&` 는 **액션 경계**(`} & [`)만 센다. 문자열 안의 `&` 를 세던 옛 판은 1,264건 중 11건을
     조합으로 오검출했다(≈0.9p 과대). 이 판의 수치는 옛 판보다 그만큼 낮게 나온다.
  표꼬리 = `>>` 이고 첫 스텝 이후가 전부 `table:*` / 다단 = 그 밖의 `>>`
  한 호출이 여러 칸에 겹쳐 셀 수 있다(단일만 배타적) — 칸 합계는 100% 를 넘을 수 있다.

★관측의 한계(silent-clamp 부류) — episode_log 는 tool_use 인자를 **약 300자에서 자른다**.
그래서 긴 호출 25%(1,685건 중 421건)는 앞 ~280자만 보인다. 잘린 뒤의 `>>`·`&` 는 셀 수 없으므로
**절단분은 분모에서 빼고**(완전 관측분만 집계) 건수만 따로 신고한다. 절단분은 대개
`[self:edit]`·`[self:patch]` 의 긴 payload 라 조합이 아니라 내용이 길다. 로거의 절단 폭이 바뀌면
이 수치의 분모도 바뀐다 — 재측정 때 절단 건수를 먼저 볼 것.

docs/IBL_PROGRAM_GRADE_DESIGN.md §5 의 측정기.
사용: python3 scripts/ibl_composition_metrics.py [시작일=2026-08-16 | N에피소드] [분할일=2026-08-21]
      기본값이 날짜인 이유: 슬라이딩 N 창은 개입일을 창 안으로 끌어들여 기준선을 오염시킨다.
"""
import sqlite3, re, json, collections, sys
import pathlib
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = str(ROOT/"data"/"world_pulse.db")
CORPUS = str(ROOT/"data"/"ibl_usage.db")
OUT = str(ROOT/"data"/"ibl_composition_metrics.json")
# 첫 인자: 날짜(YYYY-MM-DD)면 "그날 이후 전부", 숫자면 "최근 N 에피소드".
# ★기본값은 날짜다 — 슬라이딩 N 창은 기준선을 재현하지 못한다(창이 밀리면 분모가 바뀐다).
ARG1 = sys.argv[1] if len(sys.argv) > 1 else "2026-08-16"
SINCE = ARG1 if re.match(r"^\d{4}-\d{2}-\d{2}$", ARG1) else None
N = None if SINCE else int(ARG1)
SPLIT = sys.argv[2] if len(sys.argv) > 2 else "2026-08-21"   # 이 날짜부터 '배치 후'

TOOL = re.compile(r"\] tool_use (\S+) (\{.*)")
CODE = re.compile(r'"code"\s*:\s*"((?:[^"\\]|\\.)*)"')
HEAD = re.compile(r'\[([a-z_]+):([a-z_0-9]+)\]')
PAR = re.compile(r'\}\s*&\s*\[')            # 액션 경계의 & 만 — 문자열 안 & 제외
VAR = re.compile(r'\$\{?[가-힣A-Za-z_]\w*')  # 표기 두 형태(`$이름`·`${이름}`)
CTRL_OPS = ('??', '[if:', '[case:', '[repeat:', '[table:each]', 'goal:')
KINDS = ['단일', '표꼬리', '다단', '팬아웃(동일)', '팬아웃(이종)', '제어', '변수']
PROGRAM_KINDS = ['다단', '제어', '변수']     # ★감시 대상


def head(c):
    m = HEAD.search(c or "")
    return f"{m.group(1)}:{m.group(2)}" if m else "?"


def classify(code):
    """한 호출 원문 → 칸 집합. 겹쳐 셀 수 있고, '단일'만 배타적."""
    c = code or ""
    ks = set()
    if any(o in c for o in CTRL_OPS):
        ks.add('제어')
    if VAR.search(c):
        ks.add('변수')
    if PAR.search(c):
        acts = HEAD.findall(c)
        ks.add('팬아웃(동일)' if len(set(acts)) == 1 else '팬아웃(이종)')
    if '>>' in c:
        acts = [f"{a}:{b}" for a, b in HEAD.findall(c)]
        tail_only = len(acts) >= 2 and all(a.startswith('table:') for a in acts[1:])
        ks.add('표꼬리' if tail_only else '다단')
    return ks or {'단일'}


def composed(code):
    return '단일' not in classify(code)


def shape(code):
    """파이프의 모양(액션 열) — 한 습관의 반복인지 진짜 다양성인지 가른다."""
    return " >> ".join(f"{a}:{b}" for a, b in HEAD.findall(code or ""))


def tally(codes):
    t = collections.Counter()
    for c in codes:
        t['n'] += 1
        for k in classify(c):
            t[k] += 1
    return t


def fmt(t, label="", width=16):
    n = t['n']
    if not n:
        return f"{label:<{width}}      0"
    comp = n - t['단일']
    cells = "".join(f"{t[k]/n:>9.1%}" for k in KINDS[1:])
    return f"{label:<{width}}{n:>6}{comp/n:>8.1%}{cells}"


HDR = f"{'':<16}{'n':>6}{'조합':>8}" + "".join(f"{k:>9}" for k in KINDS[1:])

# ─────────────────────────── 실행층 (episode_log) ───────────────────────────
con = sqlite3.connect(DB)
# 시험 유래 주행 제외(B18-2) — 지표는 실사용 파이프만 센다.
if SINCE:
    rows = con.execute("SELECT id, started_at, agent, user_message, log FROM episode_log "
                       "WHERE COALESCE(source, 'usage') <> 'test' AND started_at >= ? "
                       "ORDER BY id DESC", (SINCE,)).fetchall()
else:
    rows = con.execute("SELECT id, started_at, agent, user_message, log FROM episode_log "
                       "WHERE COALESCE(source, 'usage') <> 'test' ORDER BY id DESC LIMIT ?",
                       (N,)).fetchall()

REF_ATTR = re.compile(r"<ref\s+intent=\"(?:.*?)\"\s+code='(.*)'\s+score=")     # 수리 전 형식
REF_CDATA = re.compile(r"<ref\s+[^>]*?><!\[CDATA\[(.*?)\]\]></ref>", re.S)     # 수리 후 형식
BLOCK = re.compile(r"<ibl_references\b.*?</ibl_references>", re.S)

stats = []
blocks_total = blocks_dead = 0
trunc_total = 0
for eid, ts, agent, msg, log in rows:
    if not log:
        continue
    tools = collections.Counter()
    ibl = []
    trunc = 0
    for line in log.splitlines():
        m = TOOL.search(line)
        if not m:
            continue
        name = m.group(1)
        tools[name] += 1
        if "execute_ibl" in name:
            c = CODE.search(m.group(2))
            if c:
                ibl.append(c.group(1))
            else:
                trunc += 1   # 로그가 ~300자에서 잘랐다 — 뒤에 숨은 조합을 셀 수 없어 분모에서 뺀다
    trunc_total += trunc
    # 회상층 — 이 턴의 프롬프트에 실제로 주입된 용례
    refs = REF_ATTR.findall(log) + [m.group(1) for m in REF_CDATA.finditer(log)]
    # 표면층 — 계기판(ManualMode.tsx)은 이 블록을 DOMParser 로 진짜 파싱한다.
    # 비적합이면 예외가 아니라 **빈 목록** → '번역 근거' 패널이 조용히 사라진다.
    for b in BLOCK.findall(log):
        blocks_total += 1
        try:
            ET.fromstring(b)
        except ET.ParseError:
            blocks_dead += 1
    stats.append(dict(id=eid, ts=ts, agent=agent, msg=(msg or "")[:70].replace("\n", " "),
                      n_tools=sum(tools.values()), tools=dict(tools), ibl=ibl,
                      truncated=trunc, refs=refs))

exec_codes = [c for s in stats for c in s["ibl"]]
recall_codes = [c for s in stats for c in s["refs"]]

# ─────────────────────────── 교재층 (코퍼스) ───────────────────────────
corpus_codes = []
try:
    corpus_codes = [r[0] for r in sqlite3.connect(CORPUS).execute("SELECT ibl_code FROM ibl_examples")]
except sqlite3.Error as e:
    print(f"[경고] 코퍼스 읽기 실패 — 교재층 생략: {e}")

# ─────────────────────────── 출력 ───────────────────────────
win = [s["ts"] for s in stats if s["ts"]]
print(f"에피소드 {len(stats)}건  창: {min(win)[:16]} ~ {max(win)[:16]}" if win else f"에피소드 {len(stats)}건")
print(f"IBL 호출 {len(exec_codes) + trunc_total}건 중 완전 관측 {len(exec_codes)}건 · "
      f"로그 절단 {trunc_total}건({trunc_total/(len(exec_codes)+trunc_total):.0%}) — 절단분은 분모에서 뺐다")

print("\n=== ① 4층 조합률 — 층 사이 낙차가 병목의 위치 ===")
print(HDR)
for label, codes in (("교재(코퍼스)", corpus_codes), ("회상(주입 ref)", recall_codes), ("실행(호출)", exec_codes)):
    if codes:
        print(fmt(tally(codes), label))
if blocks_total:
    print(f"{'표면(계기판)':<16}{blocks_total:>6}  참조 블록 중 XML 파싱 실패(패널 빈 목록) "
          f"{blocks_dead}건 = {blocks_dead/blocks_total:.0%}")

print("\n=== ② 배치 전/후 — 옛 기준선 15% 는 두 체제의 평균이라 쓰지 않는다 ===")
print(HDR)
for label, pred in ((f"~{SPLIT} 전", lambda t: t < SPLIT), (f"{SPLIT}~ 후", lambda t: t >= SPLIT)):
    codes = [c for s in stats if s["ts"] and pred(s["ts"]) for c in s["ibl"]]
    if codes:
        print(fmt(tally(codes), label))

print("\n=== ③ 일자별 (주체 구성 착시 검출용 — system_ai 단독과 함께 본다) ===")
day = collections.defaultdict(list)
day_sys = collections.defaultdict(list)
for s in stats:
    d = (s["ts"] or "")[:10]
    day[d] += s["ibl"]
    if s["agent"] == "system_ai":
        day_sys[d] += s["ibl"]
print(HDR)
for d in sorted(day):
    if day[d]:
        print(fmt(tally(day[d]), d))
print("  — system_ai 단독 —")
for d in sorted(day_sys):
    if day_sys[d]:
        print(fmt(tally(day_sys[d]), d))

print("\n=== ④ 주체별 (실행 / 회상) ===")
by_ag = collections.defaultdict(list)
by_ag_ref = collections.defaultdict(list)
for s in stats:
    by_ag[s["agent"] or "?"] += s["ibl"]
    by_ag_ref[s["agent"] or "?"] += s["refs"]
for a, codes in sorted(by_ag.items(), key=lambda x: -len(x[1])):
    if not codes:
        continue
    t = tally(codes)
    r = by_ag_ref.get(a) or []
    rc = sum(1 for x in r if composed(x))
    rs = f"회상 {rc}/{len(r)} = {rc/len(r):.1%}" if r else "회상 0"
    print(f"{a:<14} 실행 {t['n']-t['단일']:>4}/{t['n']:<5} = {(t['n']-t['단일'])/t['n']:>6.1%}   {rs}")

print("\n=== ⑤ 모양 다양성 — 한 습관의 반복인가, 일반화인가 ===")
for label, pred in ((f"~{SPLIT} 전", lambda t: t < SPLIT), (f"{SPLIT}~ 후", lambda t: t >= SPLIT)):
    sh = collections.Counter()
    for s in stats:
        if not (s["ts"] and pred(s["ts"])):
            continue
        for c in s["ibl"]:
            if '>>' in (c or ""):
                sh[shape(c)] += 1
    if sh:
        top = sh.most_common(1)[0]
        print(f"{label}: 파이프 {sum(sh.values())}건 / 서로 다른 모양 {len(sh)}가지 "
              f"(최다 {top[1]}건 = {top[1]/sum(sh.values()):.0%}: {top[0]})")

print("\n=== ⑥ ★감시 대상 — 프로그램 칸(다단·제어·변수)의 건수 ===")
t_all = tally(exec_codes)
for k in PROGRAM_KINDS:
    print(f"  {k:<6} {t_all[k]:4d}건  {t_all[k]/t_all['n']:.1%}")
print("  (제어·변수는 08-20 까지 매일 정확히 0 이었다 — 비율보다 '0 을 벗어났는가'를 본다)")

# ── 접힐 수 있었던 자리 — 연속 동일 액션·동일 코드 재호출 ──
runs = collections.Counter()
dupes = collections.Counter()
examples = collections.defaultdict(list)
for s in stats:
    prev = None
    runlen = 1
    seen = collections.Counter()
    for c in s["ibl"]:
        seen[c] += 1
        h = head(c)
        if h == prev:
            runlen += 1
        else:
            if runlen >= 2 and prev:
                runs[prev] += runlen
                if len(examples[prev]) < 4:
                    examples[prev].append((s["id"], runlen, s["msg"]))
            prev = h
            runlen = 1
    if runlen >= 2 and prev:
        runs[prev] += runlen
        if len(examples[prev]) < 4:
            examples[prev].append((s["id"], runlen, s["msg"]))
    for c, n in seen.items():
        if n >= 2:
            dupes[head(c)] += n - 1

print("\n=== ⑦ 연속 동일 액션 반복(한 문장으로 접힐 수 있었던 자리) 상위 ===")
for k, v in runs.most_common(15):
    ex = "; ".join(f"ep{a}×{b}" for a, b, _ in examples[k][:3])
    print(f"{v:4d}  {k:<22} {ex}")
print("\n=== ⑧ 완전 동일 코드 재호출 상위 ===")
for k, v in dupes.most_common(10):
    print(f"{v:4d}  {k}")

json.dump(dict(
    window=dict(episodes=len(stats), since=SINCE, last_n=N, first=(min(win) if win else None), last=(max(win) if win else None),
                split=SPLIT, calls_observed=len(exec_codes), calls_truncated=trunc_total),
    layers={lab: dict(tally(c)) for lab, c in
            (("corpus", corpus_codes), ("recall", recall_codes), ("exec", exec_codes)) if c},
    surface=dict(blocks=blocks_total, unparseable=blocks_dead),
    by_day={d: dict(tally(v)) for d, v in day.items() if v},
    by_day_system_ai={d: dict(tally(v)) for d, v in day_sys.items() if v},
    by_agent={a: dict(tally(v)) for a, v in by_ag.items() if v},
    episodes=stats,
), open(OUT, "w"), ensure_ascii=False, indent=1)
print(f"\n원장: {OUT}")
