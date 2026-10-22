"""T4 — records.json 누락 복구 판본 반영, 최종 인수 검토. 정책은 T2 그대로.
바뀐 레코드만 증분 갱신(A) → 의존 결과(D 3개 조건, S) 갱신 → 나머지(R, C1, B, C2)는 T3 산출물 보존.
사용: python3 -I review_t4.py <inputs_dir> <ai_dir>
"""
import hashlib, json, os, shutil, sys, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

IN, AI = sys.argv[1:3]
T1, T2, T3, OUT = (os.path.join(AI, t) for t in ("T1", "T2", "T3", "T4"))
FILES = ["README.txt", "project.json", "options.json", "receipts.json", "records.json", "tasks.json"]
LOG, LOCK, RESULTS = [], threading.Lock(), {}

def now(): return datetime.now(timezone.utc).astimezone().isoformat(timespec="microseconds")
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def load(n): return json.load(open(os.path.join(IN, n), encoding="utf-8"))
def jread(d, n): return json.load(open(os.path.join(d, n), encoding="utf-8"))
def write(n, o):
    with open(os.path.join(OUT, n), "w", encoding="utf-8") as f: json.dump(o, f, ensure_ascii=False, indent=2)

def prior_manifests():
    """T1~T3 산출물이 기록된 지문 그대로 남아 있는지(삭제·덮어쓰기 없음) 확인."""
    out = {}
    for t, d in (("T1", T1), ("T2", T2), ("T3", T3)):
        m = jread(d, "manifest.json")["artifacts"]
        out[t] = {"files": len(m), "missing": [f for f in m if not os.path.exists(os.path.join(d, f))],
                  "changed": [f for f in m if os.path.exists(os.path.join(d, f)) and sha(os.path.join(d, f)) != m[f]]}
        out[t]["intact"] = not out[t]["missing"] and not out[t]["changed"]
    return out

PRIOR_BEFORE = prior_manifests()
INPUT_VERSIONS = {f: sha(os.path.join(IN, f)) for f in FILES}
T3_LOG = jread(T3, "run_log.json")
CHANGED = sorted(f for f in FILES if INPUT_VERSIONS[f] != T3_LOG["input_versions"][f])
POLICY = T3_LOG["policy"]

def run_job(job_id, inputs, fn, mode, after=None):
    rec = {"job": job_id, "mode": mode, "inputs": {f: INPUT_VERSIONS[f] for f in inputs},
           "upstream": after or [], "thread": threading.current_thread().name,
           "started_at": now(), "t0": time.perf_counter()}
    try:
        bad = [u for u in (after or []) if RESULTS.get(u, {}).get("status") != "ok"]
        if bad: raise RuntimeError(f"선행 검토 실패: {bad}")
        res = fn()
        if mode == "updated":
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
        t3rec = next(j for j in T3_LOG["jobs"] if j["job"] == job_id)
        src = os.path.join(T3, f"{job_id}.json")
        if sha(src) != t3rec["output_sha256"]: raise RuntimeError("T3 산출물 지문 불일치")
        shutil.copyfile(src, os.path.join(OUT, f"{job_id}.json"))
        return {"from": src, "t3_output_sha256": t3rec["output_sha256"], "inputs_unchanged": inputs,
                "t3_mode": t3rec["mode"], "why_unaffected": reason}
    return fn

GATES = [("consent", "동의 확인", lambda v: v == "yes", lambda v: v == "no"),
         ("checksum", "체크섬 일치", lambda v: v == "pass", lambda v: v == "fail"),
         ("searchable", "검색 가능", lambda v: v is True, lambda v: v is False),
         ("accessible", "접근성 통과", lambda v: v is True, lambda v: v is False)]
FIELDS = [g[0] for g in GATES]
def gstate(v, ok, bad):
    if v is None or v == "missing" or v == "": return "unknown"
    return "pass" if ok(v) else ("fail" if bad(v) else "unknown")
def states_of(r): return {f: gstate(r.get(f), ok, bad) for f, _, ok, bad in GATES}
def verdict(st):
    if st is None: return "unconfirmed"
    fl = [f for f, s in st.items() if s == "fail"]; uk = [f for f, s in st.items() if s == "unknown"]
    return "usable" if not fl and not uk else ("not_usable" if fl else "unconfirmed")

def t3_states():
    """T3(v2) 산출물에서 레코드별 상태 복원. v2에 없던 레코드는 None."""
    A3 = jread(T3, "A_records.json")
    absent = set(A3["version_comparison"]["removed_ids"])
    ids = [f"D{i:04d}" for i in range(1, A3["coverage"]["expected"] + 1)]
    st = {i: (None if i in absent else {f: "pass" for f in FIELDS}) for i in ids}
    for f, g in A3["gates"].items():
        for i in g["fail_ids"]: st[i][f] = "fail"
        for i in g["unknown_ids"]: st[i][f] = "unknown"
    return A3, st

# ---------- A: 바뀐 레코드만 증분 갱신 ----------
def review_records():
    proj, data = load("project.json"), load("records.json")
    A3, prev = t3_states()
    items = data["items"]
    ids = [r["id"] for r in items]
    expected = [f"D{i:04d}" for i in range(1, proj["expected_records"] + 1)]
    cur = {r["id"]: states_of(r) for r in items}
    absent = sorted(set(expected) - set(cur)); extra = sorted(set(cur) - set(expected))
    dup = sorted({i for i in ids if ids.count(i) > 1}) if len(set(ids)) != len(ids) else []
    changed = [i for i in expected if prev.get(i) != cur.get(i)]
    # 증분: T3 상태에서 시작해 바뀐 레코드만 교체
    st = dict(prev)
    for i in changed: st[i] = cur.get(i)
    # 교차 확인: 전체 재계산과 일치하는지
    full = {i: cur.get(i) for i in expected}
    incremental_matches_full = st == full
    per = {i: verdict(st[i]) for i in expected}
    cnt = {v: sum(1 for x in per.values() if x == v) for v in ("usable", "not_usable", "unconfirmed")}
    gates = {}
    for f, label, *_ in GATES:
        c = {"pass": [], "fail": [], "unknown": []}
        for i in expected:
            if st[i] is not None: c[st[i][f]].append(i)
        gates[f] = {"label": label, "pass": len(c["pass"]), "fail": len(c["fail"]),
                    "unknown_value_missing": len(c["unknown"]), "unknown_not_in_version": len(absent),
                    "fail_ids": c["fail"], "unknown_ids": c["unknown"], "not_in_version_ids": absent}
    v1_state = next((p["v1_states"] for p in A3["preserved_prior_findings"] if p["id"] == "D1800"), None)
    rv3 = A3["record_verdicts"]
    return {
        "review": "A_records", "status": "ok",
        "rule": "네 조건 모두 필수(기준 유지). 명시적 위반=실패, 값 누락·판본에 없음=미확인. 미확인은 통과·실패로 접지 않는다.",
        "version_comparison": {
            "v1": jread(T3, "A_records.json")["version_comparison"]["v1"],
            "v2": A3["version_comparison"]["v2"],
            "v3": {"sha256": INPUT_VERSIONS["records.json"], "version": data.get("version"), "records": len(items)},
            "fields_same": all(sorted(r.keys()) == ["accessible", "checksum", "collection", "consent", "id", "searchable"] for r in items),
            "changed_vs_v2": [{"id": i, "v2": prev.get(i), "v3": cur.get(i)} for i in changed],
            "unchanged_vs_v2": len(expected) - len(changed),
            "added_ids": [i for i in changed if prev.get(i) is None and cur.get(i) is not None],
            "removed_ids": absent, "unexpected_ids": extra, "duplicates": dup,
            "restored_matches_v1_record": {"id": "D1800", "v1": v1_state, "v3": cur.get("D1800"), "same": v1_state == cur.get("D1800")},
            "raw_files_note": "v1·v2 원본 파일은 입력 폴더에서 교체되어 남아 있지 않다. 각 판본의 해시와 레코드별 상태는 T1·T3 산출물에 보존되어 있다.",
        },
        "method": {"incremental": f"T3 판정 {len(expected) - len(changed)}건 재사용 + 바뀐 {len(changed)}건만 다시 판정",
                   "cross_check_full_recompute_equal": incremental_matches_full},
        "coverage": {"expected": proj["expected_records"], "in_version": len(items), "complete": not absent and not dup and not extra},
        "gates": gates,
        "record_verdicts": {"usable": cnt["usable"], "not_usable_confirmed_fail": cnt["not_usable"], "unconfirmed": cnt["unconfirmed"],
                            "unconfirmed_breakdown": {"value_missing_only": cnt["unconfirmed"] - len(absent), "record_absent": len(absent)}},
        "delta_vs_T3": {"usable": cnt["usable"] - rv3["usable"], "not_usable": cnt["not_usable"] - rv3["not_usable_confirmed_fail"],
                        "unconfirmed": cnt["unconfirmed"] - rv3["unconfirmed"]},
        "changed_record_verdicts": [{"id": i, "T3": verdict(prev.get(i)), "T4": per[i], "states": st[i]} for i in changed],
        "not_usable": [{"id": i, "failed": [f for f, s in st[i].items() if s == "fail"], "unknown": [f for f, s in st[i].items() if s == "unknown"]} for i in expected if per[i] == "not_usable"],
        "unconfirmed": [{"id": i, "unknown": ["record_absent"] if st[i] is None else [f for f, s in st[i].items() if s == "unknown"]} for i in expected if per[i] == "unconfirmed"],
        "all_records_pass": cnt["usable"] == proj["expected_records"],
        "verdict": "미충족" if cnt["not_usable"] else ("미확인" if cnt["unconfirmed"] else "충족"),
    }

# ---------- D: 자료 수치 의존 조건만 갱신 ----------
def review_operations():
    D3, A = jread(T3, "D_operations.json"), jread(OUT, "A_records.json")
    g, rv = A["gates"], A["record_verdicts"]
    upd = {
        "개인정보(동의 확인) 전량": f"동의 yes {g['consent']['pass']}건, 값 missing {g['consent']['unknown_value_missing']}건(미확인), 판본에 없음 {g['consent']['unknown_not_in_version']}건",
        "접근성 전량": f"통과 {g['accessible']['pass']}건, 실패 {g['accessible']['fail']}건, 판본에 없음 {g['accessible']['unknown_not_in_version']}건. W4 흐름은 W4-02 미검증으로 막힘",
        "1800건 전량 검증": f"판본 범위 {A['coverage']['in_version']}/1800 완전. 충족 {rv['usable']}건, 실패 {rv['not_usable_confirmed_fail']}건, 미확인 {rv['unconfirmed']}건",
    }
    out = []
    for c in D3["conditions"]:
        k = c["condition"]
        if k in upd: out.append({**{x: y for x, y in c.items() if x not in ("reprocessed_T3", "preserved_from")}, "verdict": "미충족", "evidence": upd[k], "updated_T4": True})
        else: out.append({**{x: y for x, y in c.items() if x not in ("reprocessed_T3", "preserved_from")}, "updated_T4": False, "preserved_from": "T3(=T2)"})
    return {"review": "D_operations", "status": "ok", "conditions": out, "standards_lowered": False}

# ---------- S: 최종 인수 검토 ----------
def synthesize():
    A, Bd, C2, D, R = (jread(OUT, f"{n}.json") for n in ("A_records", "B_budget", "C2_schedule", "D_operations", "R_receipts"))
    S3 = jread(T3, "S_synthesis.json")
    g, rv = A["gates"], A["record_verdicts"]
    actions = []
    for a in S3["priority_actions"]:
        if "D1800" in a["action"]:
            continue  # 복구로 해소
        a = {k: v for k, v in a.items() if k != "updated_T3"}
        if a["area"] == "자료":
            key = a["evidence"].split(".")[2]
            n = g[key]["fail"] if key != "consent" else g[key]["unknown_value_missing"]
            a["action"] = {"checksum": f"체크섬 불일치 {n}건 재수집·재해시", "accessible": f"접근성 미통과 {n}건 보정·재검사",
                           "searchable": f"검색 불가 {n}건 색인 보정", "consent": f"동의 missing {n}건 동의 여부 확정"}[key]
            a["updated_T4"] = True
        actions.append(a)
    review_jobs_ok = all(j["status"] == "ok" for j in LOG)
    return {"review": "S_synthesis", "status": "ok",
            "review_completion": {"status": "검토 완료" if review_jobs_ok else "검토 일부 실패",
                                  "all_review_jobs_ok": review_jobs_ok,
                                  "meaning": "네 검토(자료·예산·작업·운영)를 현재 입력과 조건으로 모두 판정했다는 뜻. 개통 가능 여부와 별개다."},
            "open_readiness": {"open_ready": False, "label": "개통 불가(미충족)",
                               "acceptance_rule": load("project.json")["acceptance"],
                               "failed_criteria": [
                                   f"자료: 1800건 중 네 조건 충족 {rv['usable']}건 — 실패 확인 {rv['not_usable_confirmed_fail']}건, 미확인 {rv['unconfirmed']}건(동의 값 누락)",
                                   f"작업: 범위 안 필수 60건 중 검증 완료 {C2['counts']['done']}건, W4-02 미검증",
                                   f"예산: 범위 안 {Bd['in_scope_cost']:,}원 > {Bd['budget']:,}원 ({Bd['shortfall']:,}원 부족, 총예산 해석 기준)"],
                               "not_determinable": ["11-20 기한 준수(가용시간·달력 없음)", "검색 선택안 O1 채택 여부"],
                               "distinction": "실제 개통이나 배포는 하지 않았다(publication=draft_only)."},
            "summary": {
                "records": {"verdict": A["verdict"], "coverage": A["coverage"], "usable": rv["usable"], "confirmed_fail": rv["not_usable_confirmed_fail"],
                            "unconfirmed": rv["unconfirmed"], "delta_vs_T3": A["delta_vs_T3"], "gates": {k: {x: v[x] for x in ("pass", "fail", "unknown_value_missing", "unknown_not_in_version")} for k, v in g.items()}},
                "budget": {"verdict": Bd["verdict"], "in_scope_cost": Bd["in_scope_cost"], "budget": Bd["budget"], "shortfall": Bd["shortfall"],
                           "alternative_if_remaining_budget": Bd["basis"]["alternative_if_remaining_budget"], "options_double_counted": False},
                "tasks": {"counts": C2["counts"], "ready": C2["ready"], "remaining_critical_path": C2["remaining_critical_path"], "deadline": C2["deadline"]},
                "operations": {c["condition"]: c["verdict"] for c in D["conditions"]},
            },
            "integrity_of_change": {**S3["integrity_of_change"]},
            "priority_actions": actions,
            "resolved_since_T3": ["D1800 누락 — 복구 판본에 포함되어 해소(현재 판정: 실패 확인)"],
            "blocked_or_failed_reviews": [j["job"] for j in LOG if j["status"] != "ok"],
            "observations": [o for o in S3["observations"] if "1799" not in o] + ["records.json v3에서 1800건 범위 복구"]}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    started = now()
    stage1 = [
        ("A_records", ["project.json", "records.json"], review_records, "updated", None),
        ("R_receipts", ["tasks.json", "receipts.json"], preserve("R_receipts", ["tasks.json", "receipts.json"], "영수증·작업 입력 불변, 자료와 무관"), "preserved", None),
        ("C1_graph", ["tasks.json"], preserve("C1_graph", ["tasks.json"], "작업 입력·범위 정책 불변"), "preserved", None),
        ("B_budget", ["tasks.json", "options.json", "project.json"], preserve("B_budget", ["tasks.json", "options.json", "project.json"], "예산은 tasks.cost와 정책으로만 정해짐"), "preserved", None),
        ("C2_schedule", ["tasks.json", "project.json"], preserve("C2_schedule", ["tasks.json", "project.json"], "일정·차단은 작업·영수증으로만 정해짐"), "preserved", None),
    ]
    bar = threading.Barrier(len(stage1))
    def go(j): bar.wait(timeout=10); return run_job(*j)
    with ThreadPoolExecutor(max_workers=len(stage1), thread_name_prefix="stage1") as ex: list(ex.map(go, stage1))
    join1 = now()
    run_job("D_operations", ["project.json", "options.json", "README.txt", "records.json"], review_operations, "updated", ["A_records"])
    run_job("S_synthesis", FILES, synthesize, "updated", ["A_records", "B_budget", "C1_graph", "C2_schedule", "D_operations", "R_receipts"])
    s1 = [r for r in LOG if r["job"] in {j[0] for j in stage1}]
    write("run_log.json", {
        "turn": "T4", "run_started_at": started, "run_ended_at": now(), "policy": POLICY, "policy_note": "T2 정책 그대로",
        "input_versions": INPUT_VERSIONS, "changed_inputs_vs_T3": CHANGED,
        "t3_run_log_sha256": sha(os.path.join(T3, "run_log.json")),
        "prior_outputs_intact_before": PRIOR_BEFORE, "prior_outputs_intact_after": prior_manifests(),
        "stages": [{"stage": 1, "mode": "parallel", "jobs": [j[0] for j in stage1],
                    "all_started_before_first_end": max(r["started_at"] for r in s1) < min(r["ended_at"] for r in s1), "join_at": join1},
                   {"stage": 2, "mode": "after A_records", "jobs": ["D_operations"]},
                   {"stage": 3, "mode": "after all", "jobs": ["S_synthesis"]}],
        "updated": [j["job"] for j in LOG if j["mode"] == "updated"],
        "preserved": [j["job"] for j in LOG if j["mode"] == "preserved" and j["status"] == "ok"],
        "jobs": LOG})
    print(json.dumps([{k: r.get(k) for k in ("job", "mode", "status", "thread", "started_at", "ended_at", "output_sha256", "error")} for r in LOG], ensure_ascii=False))
