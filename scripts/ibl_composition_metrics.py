#!/usr/bin/env python3
"""IBL 조합률 측정 — episode_log 의 execute_ibl 호출 원문에서 조합 문법 사용·연속 동일 액션 반복을 센다 (2026-08-21).
기준선(08-16~21, 220 에피소드): 조합 15% · 연속 동일 액션 ≈700 · ?? 0 · if 1 · each 1 · $변수 1 · 파이프 중앙값 2.
docs/IBL_PROGRAM_GRADE_DESIGN.md §5 의 측정기. 사용: python3 scripts/ibl_composition_metrics.py [N에피소드=220]
"""
import sqlite3, re, json, collections, sys
import pathlib
ROOT=pathlib.Path(__file__).resolve().parent.parent
DB=str(ROOT/"data"/"world_pulse.db")
OUT=str(ROOT/"data"/"ibl_composition_metrics.json")
N=int(sys.argv[1]) if len(sys.argv)>1 else 220
con=sqlite3.connect(DB)
rows=con.execute("SELECT id, started_at, agent, user_message, log FROM episode_log ORDER BY id DESC LIMIT ?", (N,)).fetchall()
TOOL=re.compile(r"\] tool_use (\S+) (\{.*)")
stats=[]
for eid, ts, agent, msg, log in rows:
    if not log: continue
    tools=collections.Counter()
    ibl=[]
    for line in log.splitlines():
        m=TOOL.search(line)
        if not m: continue
        name=m.group(1); tools[name]+=1
        if "execute_ibl" in name:
            raw=m.group(2)
            # try parse code field
            c=re.search(r'"code"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            ibl.append(c.group(1) if c else raw[:200])
    stats.append(dict(id=eid, ts=ts, agent=agent, msg=(msg or "")[:70].replace("\n"," "),
                      n_tools=sum(tools.values()), tools=dict(tools), ibl=ibl))
json.dump(stats, open(OUT,"w"), ensure_ascii=False, indent=1)
# summary
print("episodes:", len(stats))
agg=collections.Counter()
for s in stats:
    for k,v in s["tools"].items(): agg[k]+=v
for k,v in agg.most_common(25): print(f"{v:5d}  {k}")
print("\n--- IBL 호출 수 상위 에피소드 ---")
for s in sorted(stats, key=lambda x: -len(x["ibl"]))[:25]:
    print(f'{s["id"]}  {s["agent"]:<10} ibl={len(s["ibl"]):2d} tools={s["n_tools"]:2d}  {s["msg"]}')

# ── 조합 패턴 분석 ──
S=stats

HEAD=re.compile(r'\[([a-z_]+):([a-z_0-9]+)\]')
def head(c):
    m=HEAD.search(c or "")
    return f"{m.group(1)}:{m.group(2)}" if m else "?"
def steps(c):
    return HEAD.findall(c or "")

runs=collections.Counter()      # 연속 같은 액션 반복 (팬아웃 갭)
dupes=collections.Counter()
compose=collections.Counter()   # 조합 연산자 사용
single=0; total=0
readonly_runs=collections.Counter()
examples=collections.defaultdict(list)

for s in S:
    codes=s["ibl"]
    total+=len(codes)
    prev=None; runlen=1
    seen=collections.Counter()
    for c in codes:
        for op,name in (('>>','pipe'),('&','par'),('??','fallback'),('[table:each]','each'),('[if:','if'),('[case:','case'),('goal:','goal')):
            if op in (c or ""): compose[name]+=1
        if '>>' not in (c or '') and '&' not in (c or ''): single+=1
        seen[c]+=1
        h=head(c)
        if h==prev:
            runlen+=1
        else:
            if runlen>=2 and prev:
                runs[prev]+=runlen
                if len(examples[prev])<4: examples[prev].append((s["id"], runlen, s["msg"]))
            prev=h; runlen=1
    if runlen>=2 and prev:
        runs[prev]+=runlen
        if len(examples[prev])<4: examples[prev].append((s["id"], runlen, s["msg"]))
    for c,n in seen.items():
        if n>=2: dupes[head(c)]+=n-1

print(f"총 IBL 호출 {total}  (단일 액션만={single}, {single/total:.0%})")
print("조합 문법 사용:", dict(compose))
print("\n=== 연속 동일 액션 반복(한 문장으로 접힐 수 있었던 자리) 상위 ===")
for k,v in runs.most_common(20):
    ex="; ".join(f"ep{a}×{b}" for a,b,_ in examples[k][:3])
    print(f"{v:4d}  {k:<22} {ex}")
print("\n=== 완전 동일 코드 재호출 상위 ===")
for k,v in dupes.most_common(12): print(f"{v:4d}  {k}")
