"""T3 — records.json 새 판본 반영. 정책은 T2 그대로.
판본 대조 → 영향받는 검토만 재처리(A, D, S) → 나머지(R, B, C1, C2)는 T2 산출물을 지문 확인 후 보존.
사용: python3 -I review_t3.py <inputs_dir> <T1_dir> <T2_dir> <T3_dir>
"""
import hashlib, json, os, shutil, sys, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

IN, T1, T2, OUT = sys.argv[1:5]
FILES = ["README.txt", "project.json", "options.json", "receipts.json", "records.json", "tasks.json"]
LOG, LOCK, RESULTS = [], threading.Lock(), {}

def now(): return datetime.now(timezone.utc).astimezone().isoformat(timespec="microseconds")
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def load(n): return json.load(open(os.path.join(IN, n), encoding="utf-8"))
def jread(d, n): return json.load(open(os.path.join(d, n), encoding="utf-8"))
def write(n, o):
    with open(os.path.join(OUT, n), "w", encoding="utf-8") as f: json.dump(o, f, ensure_ascii=False, indent=2)

INPUT_VERSIONS = {f: sha(os.path.join(IN, f)) for f in FILES}
T2_LOG = jread(T2, "run_log.json")
CHANGED = sorted(f for f in FILES if INPUT_VERSIONS[f] != T2_LOG["input_versions"][f])
POLICY = T2_LOG["condition_change"]  # T2 정책 그대로

def run_job(job_id, inputs, fn, mode, after=None):
    rec = {"job": job_id, "mode": mode, "inputs": {f: INPUT_VERSIONS[f] for f in inputs},
           "upstream": after or [], "thread": threading.current_thread().name,
           "started_at": now(), "t0": time.perf_counter()}
    try:
        bad = [u for u in (after or []) if RESULTS.get(u, {}).get("status") != "ok"]
        if bad: raise RuntimeError(f"선행 검토 실패: {bad}")
        res = fn()
        if mode == "reprocessed":
            res.update(job=job_id, input_versions=rec["inputs"], policy=POLICY)
            if after: res["upstream_outputs"] = {u: RESULTS[u]["output_sha256"] for u in after}
            write(f"{job_id}.json", res)
        else:
            rec["preserve_evidence"] = res
        rec.update(status="ok", output=f"{job_id}.json", output_sha256=sha(os.path.join(OUT, f"{job_id}.json")))
    except Exception as e:
        rec.update(status="failed", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc(limit=3))
    rec["ended_at"] = now(); rec["duration_ms"] = round((time.perf_counter() - rec.pop("t0")) * 1000, 3)
    with LOCK: LOG.append(rec); RESULTS[job_id] = rec
    return rec

def preserve(job_id, inputs, reason):
    def fn():
        changed = [f for f in inputs if f in CHANGED]
        if changed: raise RuntimeError(f"입력 변경으로 보존 불가: {changed}")
        t2rec = next(j for j in T2_LOG["jobs"] if j["job"] == job_id)
        src = os.path.join(T2, f"{job_id}.json")
        if sha(src) != t2rec["output_sha256"]: raise RuntimeError("T2 산출물 지문 불일치")
        shutil.copyfile(src, os.path.join(OUT, f"{job_id}.json"))
        return {"from": src, "t2_output_sha256": t2rec["output_sha256"], "inputs_unchanged": inputs,
                "upstream_preserved": t2rec.get("upstream", []), "why_unaffected": reason}
    return fn

# ---------- 판본 대조 + A 재검증 ----------
GATES = [("consent", "동의 확인", lambda v: v == "yes", lambda v: v == "no"),
         ("checksum", "체크섬 일치", lambda v: v == "pass", lambda v: v == "fail"),
         ("searchable", "검색 가능", lambda v: v is True, lambda v: v is False),
         ("accessible", "접근성 통과", lambda v: v is True, lambda v: v is False)]
def gstate(v, ok, bad):
    if v is None or v == "missing" or v == "": return "unknown"
    return "pass" if ok(v) else ("fail" if bad(v) else "unknown")

def prior_states():
    """T1(v1) 산출물에서 레코드별·조건별 상태를 복원한다(v1 원본은 교체되어 입력에 없음)."""
    A1 = jread(T1, "A_records.json")
    ids = [f"D{i:04d}" for i in range(1, A1["integrity"]["actual"] + 1)]
    st = {i: {f: "pass" for f, *_ in GATES} for i in ids}
    for f, g in A1["gates"].items():
        for i in g["fail_ids"]: st[i][f] = "fail"
        for i in g["unknown_ids"]: st[i][f] = "unknown"
    return A1, st

def review_records():
    proj, data = load("project.json"), load("records.json")
    items = data["items"]
    A1, old = prior_states()
    ids = [r.get("id") for r in items]
    expected = [f"D{i:04d}" for i in range(1, proj["expected_records"] + 1)]
    seen = set(ids)
    dup = sorted({i for i in ids if ids.count(i) > 1}) if len(seen) != len(ids) else []
    absent = sorted(set(expected) - seen)
    new = {r["id"]: {f: gstate(r.get(f), ok, bad) for f, _, ok, bad in GATES} for r in items}
    # 판본 대조
    changed_records = [{"id": i, "v1": old[i], "v2": new[i]} for i in sorted(seen & set(old)) if old[i] != new[i]]
    # 조건별 집계(범위 안 레코드) + 범위 밖(판본에 없음) 미확인
    gates = {}
    for f, label, *_ in GATES:
        c = {"pass": [], "fail": [], "unknown": []}
        for i in expected:
            if i in new: c[new[i][f]].append(i)
        gates[f] = {"label": label, "pass": len(c["pass"]), "fail": len(c["fail"]),
                    "unknown_value_missing": len(c["unknown"]), "unknown_not_in_version": len(absent),
                    "unknown_total": len(c["unknown"]) + len(absent),
                    "fail_ids": c["fail"], "unknown_ids": c["unknown"], "not_in_version_ids": absent}
    per = []
    for i in expected:
        if i not in new:
            per.append({"id": i, "verdict": "unconfirmed", "failed": [], "unknown": ["record_absent_in_v2"]}); continue
        fl = [f for f, s in new[i].items() if s == "fail"]; uk = [f for f, s in new[i].items() if s == "unknown"]
        per.append({"id": i, "verdict": "usable" if not fl and not uk else ("not_usable" if fl else "unconfirmed"), "failed": fl, "unknown": uk})
    cnt = {v: sum(1 for p in per if p["verdict"] == v) for v in ("usable", "not_usable", "unconfirmed")}
    old_usable = A1["record_verdicts"]["usable"]
    return {
        "review": "A_records", "status": "ok",
        "rule": "네 조건 모두 필수(T2 정책 유지). 명시적 위반=실패. 값 누락(missing)·판본에 레코드 없음=미확인. 미확인은 통과·실패 어느 쪽으로도 접지 않는다.",
        "version_comparison": {
            "v1": {"sha256": jread(T1, "run_log.json")["input_versions"]["records.json"], "version": A1["data_version"], "records": A1["integrity"]["actual"]},
            "v2": {"sha256": INPUT_VERSIONS["records.json"], "version": data.get("version"), "records": len(items)},
            "fields_same": sorted(set().union(*[r.keys() for r in items])) == ["accessible", "checksum", "collection", "consent", "id", "searchable"],
            "removed_ids": absent, "added_ids": sorted(seen - set(old)), "duplicates_v2": dup,
            "records_with_changed_gate_values": changed_records,
            "unchanged_records": len(seen & set(old)) - len(changed_records),
            "v1_reconstruction": "v1 원본은 교체되어 입력에 없다. T1 A_records.json의 조건별 fail_ids·unknown_ids에서 레코드별 상태를 복원해 대조했다.",
        },
        "coverage": {"expected": proj["expected_records"], "in_version": len(items), "complete": not absent and not dup,
                     "note": "새 판본은 1800건 중 1799건만 담고 있다. 검증 범위가 불완전하다." if absent else "범위 완전"},
        "gates": gates,
        "record_verdicts": {"usable": cnt["usable"], "not_usable_confirmed_fail": cnt["not_usable"], "unconfirmed": cnt["unconfirmed"],
                            "unconfirmed_breakdown": {"value_missing_only": cnt["unconfirmed"] - len(absent), "record_absent": len(absent)}},
        "delta_vs_T1": {"usable": cnt["usable"] - old_usable,
                        "not_usable": cnt["not_usable"] - A1["record_verdicts"]["not_usable"],
                        "unconfirmed": cnt["unconfirmed"] - A1["record_verdicts"]["unconfirmed_only"]},
        "preserved_prior_findings": [{"id": i, "v1_states": old[i], "status_now": "v2에 없음 → 현재 판정 미확인(과거 v1 근거로 보존, 현재 실패로 확정하지 않음)"} for i in absent],
        "not_usable": [p for p in per if p["verdict"] == "not_usable"],
        "unconfirmed": [p for p in per if p["verdict"] == "unconfirmed"],
        "all_records_pass": cnt["usable"] == proj["expected_records"],
        "verdict": "미충족" if cnt["not_usable"] else ("미확인" if cnt["unconfirmed"] else "충족"),
    }

# ---------- D 운영 조건(A 결과 수치 반영 재처리) ----------
def review_operations():
    D2 = jread(T2, "D_operations.json")
    A = jread(OUT, "A_records.json"); g = A["gates"]
    upd = {
        "개인정보(동의 확인) 전량": ("미충족", f"동의 yes {g['consent']['pass']}건, 값 missing {g['consent']['unknown_value_missing']}건, 판본에 없음 {g['consent']['unknown_not_in_version']}건(모두 미확인)"),
        "접근성 전량": ("미충족", f"통과 {g['accessible']['pass']}건, 실패 {g['accessible']['fail']}건, 판본에 없음 {g['accessible']['unknown_not_in_version']}건(미확인). W4 흐름은 W4-02 미검증으로 막힘"),
        "1800건 전량 검증": ("미충족", f"충족 {A['record_verdicts']['usable']}건, 실패 {A['record_verdicts']['not_usable_confirmed_fail']}건, 미확인 {A['record_verdicts']['unconfirmed']}건. 새 판본이 1799건만 담음"),
    }
    out = []
    for c in D2["conditions"]:
        k = c["condition"]
        if k in upd:
            out.append({**c, "verdict": upd[k][0], "evidence": upd[k][1], "reprocessed_T3": True})
        else:
            out.append({**c, "reprocessed_T3": False, "preserved_from": "T2"})
    return {"review": "D_operations", "status": "ok", "conditions": out, "standards_lowered": False,
            "note": "자료 수치에 의존하는 세 조건만 새 판본으로 다시 판정했다. 나머지(draft_only, 범위 제외, 선택안)는 T2 그대로다."}

# ---------- S 종합 ----------
def synthesize():
    A, Bd, C2, D = (jread(OUT, f"{n}.json") for n in ("A_records", "B_budget", "C2_schedule", "D_operations"))
    S2 = jread(T2, "S_synthesis.json")
    g, rv = A["gates"], A["record_verdicts"]
    actions = []
    for a in S2["priority_actions"]:
        a = dict(a)
        if a["area"] == "자료":
            key = a["evidence"].split(".")[2]
            n = g[key]["fail"] if key != "consent" else g[key]["unknown_value_missing"]
            a["action"] = {"checksum": f"체크섬 불일치 {n}건 재수집·재해시", "accessible": f"접근성 미통과 {n}건 보정·재검사",
                           "searchable": f"검색 불가 {n}건 색인 보정", "consent": f"동의 missing {n}건 동의 여부 확정"}[key]
            a["updated_T3"] = True
        actions.append(a)
    actions.insert(0, {"priority": 1, "area": "자료", "action": "새 판본에서 빠진 D1800 1건을 다시 제출받아 네 조건 검증(v1에서는 네 조건 모두 문제)", "evidence": "A_records.version_comparison.removed_ids", "updated_T3": True})
    return {"review": "S_synthesis", "status": "ok",
            "summary": {
                "records": {"verdict": A["verdict"], "version": A["version_comparison"]["v2"]["version"], "coverage": A["coverage"],
                            "usable": rv["usable"], "confirmed_fail": rv["not_usable_confirmed_fail"], "unconfirmed": rv["unconfirmed"],
                            "unconfirmed_breakdown": rv["unconfirmed_breakdown"], "delta_vs_T1": A["delta_vs_T1"]},
                "budget": {"verdict": Bd["verdict"], "in_scope_cost": Bd["in_scope_cost"], "budget": Bd["budget"], "shortfall": Bd["shortfall"], "preserved_from": "T2"},
                "tasks": {"counts": C2["counts"], "ready": C2["ready"], "remaining_critical_path": C2["remaining_critical_path"], "preserved_from": "T2"},
                "operations": {c["condition"]: c["verdict"] for c in D["conditions"]},
            },
            "final_verdict": {"open_ready": False, "label": "개통 불가(미충족)",
                              "reasons": [f"자료 충족 {rv['usable']}/1800, 확인된 실패 {rv['not_usable_confirmed_fail']}건, 미확인 {rv['unconfirmed']}건(새 판본 1건 누락 포함)",
                                          f"예산 {Bd['shortfall']:,}원 부족(T2 그대로)", "필수 작업 60건 중 완료 9건, W4-02 미검증(T2 그대로)"],
                              "distinction": "인수 검토 완료이며 실제 개통 완료가 아님. 초안만 작성."},
            "integrity_of_change": {**S2["integrity_of_change"], "policy": "T2 그대로"},
            "priority_actions": actions,
            "blocked_or_failed_reviews": [j["job"] for j in LOG if j["status"] != "ok"],
            "observations": S2["observations"] + ["records.json v2 판본은 1799건 — 프로젝트 기대치 1800건과 불일치"]}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    started = now()
    stage1 = [
        ("A_records", ["project.json", "records.json"], review_records, "reprocessed", None),
        ("R_receipts", ["tasks.json", "receipts.json"], preserve("R_receipts", ["tasks.json", "receipts.json"], "영수증·작업 입력 불변, 자료와 무관"), "preserved", None),
        ("C1_graph", ["tasks.json"], preserve("C1_graph", ["tasks.json"], "작업 입력·범위 정책 불변"), "preserved", None),
        ("B_budget", ["tasks.json", "options.json", "project.json"], preserve("B_budget", ["tasks.json", "options.json", "project.json"], "예산은 tasks.cost와 정책으로만 정해짐, 자료와 무관"), "preserved", None),
        ("C2_schedule", ["tasks.json", "project.json"], preserve("C2_schedule", ["tasks.json", "project.json"], "일정·차단은 작업·영수증으로만 정해짐, 자료와 무관"), "preserved", None),
    ]
    bar = threading.Barrier(len(stage1))
    def go(j): bar.wait(timeout=10); return run_job(*j)
    with ThreadPoolExecutor(max_workers=len(stage1), thread_name_prefix="stage1") as ex: list(ex.map(go, stage1))
    join1 = now()
    run_job("D_operations", ["project.json", "options.json", "README.txt", "records.json"], review_operations, "reprocessed", ["A_records"])
    run_job("S_synthesis", FILES, synthesize, "reprocessed", ["A_records", "B_budget", "C2_schedule", "D_operations", "R_receipts", "C1_graph"])
    s1 = [r for r in LOG if r["job"] in {j[0] for j in stage1}]
    write("run_log.json", {
        "turn": "T3", "run_started_at": started, "run_ended_at": now(), "policy": POLICY, "policy_note": "T2 정책 그대로",
        "input_versions": INPUT_VERSIONS, "changed_inputs_vs_T2": CHANGED,
        "t2_run_log_sha256": sha(os.path.join(T2, "run_log.json")),
        "stages": [{"stage": 1, "mode": "parallel", "jobs": [j[0] for j in stage1],
                    "all_started_before_first_end": max(r["started_at"] for r in s1) < min(r["ended_at"] for r in s1), "join_at": join1},
                   {"stage": 2, "mode": "after A_records", "jobs": ["D_operations"]},
                   {"stage": 3, "mode": "after all", "jobs": ["S_synthesis"]}],
        "reprocessed": [j["job"] for j in LOG if j["mode"] == "reprocessed"],
        "preserved": [j["job"] for j in LOG if j["mode"] == "preserved" and j["status"] == "ok"],
        "jobs": LOG})
    print(json.dumps([{k: r.get(k) for k in ("job", "mode", "status", "thread", "started_at", "ended_at", "output_sha256", "error")} for r in LOG], ensure_ascii=False, indent=1))
