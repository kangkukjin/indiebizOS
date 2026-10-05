"""18회차 합성 입력과 독립 기준(oracle). 과제 해법이 아니다."""
import csv, json, random
from pathlib import Path
from collections import defaultdict
ROOT = Path(__file__).resolve().parent.parent
rnd = random.Random(18)
OWNERS = [f"팀{c}" for c in "가나다라마바사아자차카타"]
tasks, deps = [], []
for p in range(1, 61):
    pid = f"P{p:03d}"
    for j in range(40):
        tasks.append({"id": f"{pid}-T{j+1:02d}", "project": pid, "name": f"작업{j+1}", "duration": rnd.randint(1, 15), "owner": rnd.choice(OWNERS)})
        L = j // 5
        if L == 0 or rnd.random() < 0.1:
            continue
        pool = [i for i in range(40) if i // 5 == L - 1]
        if L >= 2 and rnd.random() < 0.3:
            pool += [i for i in range(40) if i // 5 == L - 2]
        for i in rnd.sample(pool, rnd.randint(1, 3)):
            deps.append({"project": pid, "task": f"{pid}-T{j+1:02d}", "depends_on": f"{pid}-T{i+1:02d}"})
T = {t["id"]: t for t in tasks}
def bad(tid, v): T[tid]["duration"] = v
bad("P007-T13", ""); bad("P019-T05", "미정"); bad("P019-T22", "")
bad("P038-T09", None); bad("P052-T03", 0); bad("P052-T30", -3); bad("P044-T17", None)
def dep(p, a, b): deps.append({"project": p, "task": f"{p}-T{a:02d}", "depends_on": f"{p}-T{b:02d}"})
# 순환: P044(기간 오류와 겹침), P026(없는 선행과 겹침), P004, P029(자기 의존), P048
def downstream(p, src):
    succ = defaultdict(set)
    for d in deps:
        if d["project"] == p: succ[d["depends_on"]].add(d["task"])
    seen, st = set(), [src]
    while st:
        x = st.pop()
        for y in succ[x]:
            if y not in seen: seen.add(y); st.append(y)
    return sorted(seen)
for p, a in (("P044", 6), ("P026", 8), ("P004", 3), ("P048", 12)):
    ds = downstream(p, f"{p}-T{a:02d}")
    far = [d for d in ds if int(d[-2:]) > 20][0]
    deps.append({"project": p, "task": f"{p}-T{a:02d}", "depends_on": far})
dep("P029", 14, 14)
for p, a, x in (("P011", 20, 77), ("P033", 5, 99), ("P033", 31, 98), ("P057", 40, 41), ("P026", 2, 55)):
    deps.append({"project": p, "task": f"{p}-T{a:02d}", "depends_on": f"{p}-T{x:02d}"})
ok_deps = [d for d in deps if d["project"] in ("P001", "P002", "P015", "P030", "P045", "P060")]
for d in rnd.sample(ok_deps, 6): deps.append(dict(d))
deps.append(dict([d for d in deps if d["project"] == "P004"][0]))
rnd.shuffle(deps)
a = [t for t in tasks if int(t["project"][1:]) <= 30]
b = [dict(t) for t in tasks if int(t["project"][1:]) > 30]
for t in b:
    if isinstance(t["duration"], int) and t["duration"] > 0 and rnd.random() < 0.2: t["duration"] = str(t["duration"])
(ROOT / "inputs").mkdir(exist_ok=True)
with open(ROOT / "inputs/tasks_a.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, ["id", "project", "name", "duration", "owner"]); w.writeheader(); w.writerows(a)
(ROOT / "inputs/tasks_b.json").write_text(json.dumps(b, ensure_ascii=False, indent=0), encoding="utf-8")
with open(ROOT / "inputs/deps.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, ["project", "task", "depends_on"]); w.writeheader(); w.writerows(deps)
# 변형 입력: 지연
delays = []
ids = [t["id"] for t in tasks]
for tid in rnd.sample(ids, 170): delays.append({"task": tid, "extra_days": rnd.randint(1, 9), "reason": rnd.choice(["자재", "인력", "날씨", "승인"])})
for d in rnd.sample(delays, 6): delays.append({"task": d["task"], "extra_days": rnd.randint(1, 4), "reason": "추가"})
for x in ("P003-T88", "P061-T01", "P020-T00", "X999"): delays.append({"task": x, "extra_days": 3, "reason": "자재"})
rnd.shuffle(delays)
(ROOT / "variant_inputs").mkdir(exist_ok=True)
with open(ROOT / "variant_inputs/delays.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, ["task", "extra_days", "reason"]); w.writeheader(); w.writerows(delays)

def num(v):
    try:
        x = float(v)
        return int(x) if x == int(x) else x
    except (TypeError, ValueError):
        return None
def solve(extra):
    byp = defaultdict(list)
    for t in tasks: byp[t["project"]].append(t)
    uniq = sorted({(d["project"], d["task"], d["depends_on"]) for d in deps})
    excluded, rt, rp = [], [], []
    for pid in sorted(byp):
        ts = byp[pid]; idset = {t["id"] for t in ts}
        dur = {t["id"]: num(t["duration"]) for t in ts}
        nb = sum(1 for v in dur.values() if v is None or v <= 0)
        e = [(t_, d_) for (p_, t_, d_) in uniq if p_ == pid]
        if nb: excluded.append({"project": pid, "reason": "bad_duration", "detail_count": nb}); continue
        nm = sum(1 for t_, d_ in e if d_ not in idset or t_ not in idset)
        if nm: excluded.append({"project": pid, "reason": "missing_dep", "detail_count": nm}); continue
        dur = {k: v + extra.get(k, 0) for k, v in dur.items()}
        preds, succs = defaultdict(set), defaultdict(set)
        for t_, d_ in e: preds[t_].add(d_); succs[d_].add(t_)
        es, done, left = {}, set(), set(idset)
        while True:
            ready = [x for x in left if preds[x] <= done]
            if not ready: break
            for x in ready: es[x] = max([es[q] + dur[q] for q in preds[x]], default=0)
            done |= set(ready); left -= set(ready)
        if left: excluded.append({"project": pid, "reason": "cycle", "detail_count": len(left)}); continue
        D = max(es[x] + dur[x] for x in idset)
        ls = {}
        for x in sorted(idset, key=lambda x: -es[x]):
            ls[x] = min([ls[s] for s in succs[x]], default=D) - dur[x]
        crit = 0
        for t in ts:
            x = t["id"]; sl = ls[x] - es[x]; crit += sl == 0
            rt.append({"id": x, "project": pid, "owner": t["owner"], "es": es[x], "ef": es[x] + dur[x], "slack": sl, "critical": sl == 0})
        rp.append({"project": pid, "duration": D, "task_count": len(ts), "critical_count": crit})
    own = defaultdict(lambda: [0, 0])
    for r in rt: own[r["owner"]][0] += 1; own[r["owner"]][1] += r["critical"]
    owners = [{"owner": o, "task_count": own[o][0], "critical_count": own[o][1]} for o in sorted(own)]
    top = sorted(rp, key=lambda r: (-r["duration"], r["project"]))[:10]
    out_tasks = [{k: r[k] for k in ("id", "project", "es", "ef", "slack", "critical")} for r in rt]
    summary = {"task_count": len(tasks), "project_count": len(byp), "computable_projects": len(rp), "excluded_projects": len(excluded),
               "dep_count_raw": len(deps), "dep_count_unique": len(uniq), "critical_task_count": sum(r["critical"] for r in rt),
               "longest_duration": top[0]["duration"]}
    return {"summary": summary, "excluded": excluded, "tasks": out_tasks, "projects": rp, "top10": top, "owners": owners}
base = solve({})
ex = {e["project"]: e["reason"] for e in base["excluded"]}
extra, not_applied = defaultdict(int), []
for d in delays:
    tid = d["task"]
    if tid not in T: not_applied.append({"task": tid, "reason": "unknown_task"}); continue
    if T[tid]["project"] in ex: not_applied.append({"task": tid, "reason": "excluded_project"}); continue
    extra[tid] += d["extra_days"]
var = solve(extra)
bp = {r["project"]: r for r in base["projects"]}
changed = [{"project": r["project"], "old_duration": bp[r["project"]]["duration"], "new_duration": r["duration"], "diff": r["duration"] - bp[r["project"]]["duration"]}
           for r in var["projects"] if r["duration"] != bp[r["project"]]["duration"]]
dp = {T[t]["project"] for t in extra}
absorbed = sorted(dp - {c["project"] for c in changed})
bc = {r["id"] for r in base["tasks"] if r["critical"]}; vc = {r["id"] for r in var["tasks"] if r["critical"]}
na = sorted({(n["task"], n["reason"]) for n in not_applied})
delta = {"applied_task_count": len(extra), "changed_projects": changed, "absorbed_projects": absorbed,
         "not_applied": [{"task": t, "reason": r} for t, r in na],
         "newly_critical": sorted(vc - bc), "no_longer_critical": sorted(bc - vc)}
(ROOT / "harness/expected_base.json").write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
(ROOT / "harness/expected_variant.json").write_text(json.dumps(var, ensure_ascii=False), encoding="utf-8")
(ROOT / "harness/expected_delta.json").write_text(json.dumps(delta, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"base": base["summary"], "excluded": base["excluded"], "variant": var["summary"],
  "delta": {k: (len(v) if isinstance(v, list) else v) for k, v in delta.items()}, "delay_rows": len(delays), "top3": base["top10"][:3]}, ensure_ascii=False, indent=1))
