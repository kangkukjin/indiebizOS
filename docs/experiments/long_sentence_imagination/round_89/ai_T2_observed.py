"""T2 조건 변경 재검토 — 예산 3,200,000원, W6 전체·외부 SaaS·얼굴 자동 분류 범위 제외.
입력 해시가 T1 판본과 같고 조건 변경의 영향을 받지 않는 검토(A_records, R_receipts)는 재사용하고,
영향을 받는 검토(B, C1, C2, D, S)만 다시 계산한다.
사용: python3 -I review_t2.py <inputs_dir> <T1_dir> <T2_dir>
"""
import hashlib, json, os, shutil, sys, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

IN, T1, OUT = sys.argv[1:4]
FILES = ["README.txt", "project.json", "options.json", "receipts.json", "records.json", "tasks.json"]
CHANGE = {
    "turn": "T2", "source": "사용자 지시(2026-10-22 13:31)",
    "budget": 3200000,
    "excluded_streams": ["선택기능"], "excluded_task_prefix": "W6-",
    "excluded_option_attrs": {"external_saas": True, "face": True},
    "kept": ["개인정보(동의 확인)", "접근성", "1800건 전량 검증", "기한 2026-11-20"],
    "prohibited": ["필수 작업 임의 취소", "검증 기준 하향"],
}
LOG, LOCK, RESULTS = [], threading.Lock(), {}

def now(): return datetime.now(timezone.utc).astimezone().isoformat(timespec="microseconds")
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def load(n): return json.load(open(os.path.join(IN, n), encoding="utf-8"))
def jread(d, n): return json.load(open(os.path.join(d, n), encoding="utf-8"))
def write(n, o):
    with open(os.path.join(OUT, n), "w", encoding="utf-8") as f: json.dump(o, f, ensure_ascii=False, indent=2)

INPUT_VERSIONS = {f: sha(os.path.join(IN, f)) for f in FILES}
T1_LOG = jread(T1, "run_log.json")
SAME_INPUTS = {f: INPUT_VERSIONS[f] == T1_LOG["input_versions"][f] for f in FILES}

def run_job(job_id, inputs, fn, mode, after=None):
    rec = {"job": job_id, "mode": mode, "inputs": {f: INPUT_VERSIONS[f] for f in inputs},
           "upstream": after or [], "thread": threading.current_thread().name,
           "started_at": now(), "t0": time.perf_counter()}
    try:
        bad = [u for u in (after or []) if RESULTS.get(u, {}).get("status") != "ok"]
        if bad: raise RuntimeError(f"선행 검토 실패: {bad}")
        res = fn()
        if mode == "recomputed":
            res.update(job=job_id, input_versions=rec["inputs"], condition_change=CHANGE)
            if after: res["upstream_outputs"] = {u: RESULTS[u]["output_sha256"] for u in after}
            write(f"{job_id}.json", res)
        rec.update(status="ok", output=f"{job_id}.json", output_sha256=sha(os.path.join(OUT, f"{job_id}.json")))
        if mode == "reused": rec["reuse_evidence"] = res
    except Exception as e:
        rec.update(status="failed", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc(limit=3))
    rec["ended_at"] = now(); rec["duration_ms"] = round((time.perf_counter() - rec.pop("t0")) * 1000, 3)
    with LOCK: LOG.append(rec); RESULTS[job_id] = rec
    return rec

def reuse(job_id, inputs, reason):
    """T1 산출물을 그대로 가져온다. 입력 해시가 같고 T1 산출물 지문이 T1 기록과 일치할 때만."""
    def fn():
        changed = [f for f in inputs if not SAME_INPUTS[f]]
        if changed: raise RuntimeError(f"입력 변경으로 재사용 불가: {changed}")
        t1rec = next(j for j in T1_LOG["jobs"] if j["job"] == job_id)
        src = os.path.join(T1, f"{job_id}.json")
        if sha(src) != t1rec["output_sha256"]: raise RuntimeError("T1 산출물 지문 불일치")
        shutil.copyfile(src, os.path.join(OUT, f"{job_id}.json"))
        return {"from": src, "t1_output_sha256": t1rec["output_sha256"],
                "t1_input_versions": t1rec["inputs"], "inputs_unchanged": {f: SAME_INPUTS[f] for f in inputs},
                "why_unaffected": reason}
    return fn

def in_scope(t): return not t["id"].startswith(CHANGE["excluded_task_prefix"])

# ---------- B. 예산(재계산) ----------
def review_budget():
    tasks, opts = load("tasks.json")["items"], load("options.json")["items"]
    done = set(jread(OUT, "R_receipts.json")["done"]) if os.path.exists(os.path.join(OUT, "R_receipts.json")) else set()
    scope = [t for t in tasks if in_scope(t)]
    excl = [t for t in tasks if not in_scope(t)]
    total = sum(t["cost"] for t in scope)
    by_stream = {}
    for t in scope: by_stream[t["stream"]] = by_stream.get(t["stream"], 0) + t["cost"]
    excl_done = [t for t in excl if t["id"] in done]
    gap = CHANGE["budget"] - total
    excl_done_cost = sum(t["cost"] for t in excl_done)
    return {
        "review": "B_budget", "status": "ok",
        "rule": "tasks.cost가 정본. 범위 안 작업만 합산. options.cost는 다시 더하지도 빼지도 않음.",
        "budget": CHANGE["budget"], "prior_budget_T1": load("project.json")["budget"],
        "in_scope_task_count": len(scope), "in_scope_cost": total, "by_stream": by_stream,
        "excluded_tasks": [t["id"] for t in excl], "excluded_cost": sum(t["cost"] for t in excl),
        "difference": gap, "verdict": "충족" if gap >= 0 else "미충족(부족)",
        "shortfall": max(0, -gap),
        "options_handling": {
            "double_counted": False,
            "excluded_options": [o["id"] for o in opts if o["external_saas"] or o["face"]],
            "note": "O2(외부 SaaS)·O3(얼굴 분류)는 범위에서 제외했지만 어느 작업에 대응하는지 입력에 없다. "
                    "그래서 이 두 선택안을 이유로 작업비를 추가로 빼지 않았다(추정 차감은 근거 없는 감액).",
        },
        "excluded_but_already_done": {
            "tasks": [t["id"] for t in excl_done], "cost": excl_done_cost,
            "note": "W6-01·W6-02는 검증 영수증이 있는 완료 작업이다. 이 비용이 이미 지출됐는지는 입력에 없어 미확인이다. "
                    f"지출됐다면 실제 부담은 {total + excl_done_cost:,}원, 부족액은 {total + excl_done_cost - CHANGE['budget']:,}원이 된다.",
        },
        "basis": {
            "applied": "총 예산 기준 — T1의 6,000,000원과 같은 방식으로 범위 안 전체 작업비와 비교",
            "alternative_if_remaining_budget": {
                "remaining_in_scope_cost": sum(t["cost"] for t in scope if t["id"] not in done),
                "verdict": "충족" if sum(t["cost"] for t in scope if t["id"] not in done) <= CHANGE["budget"] else "미충족",
                "note": "3,200,000원이 '남은 작업 예산'이라면 결과가 달라진다. 지시문만으로는 어느 뜻인지 확정할 수 없어 확인이 필요하다.",
            },
        },
        "cannot_close_by": "필수 작업 취소·검증 기준 하향은 금지되어 감액 수단이 입력 안에 없음",
    }

# ---------- C1. 그래프(범위 반영 재계산) ----------
def review_graph():
    tasks = {t["id"]: t for t in load("tasks.json")["items"] if in_scope(t)}
    dangling = [{"task": i, "dep": d} for i, t in tasks.items() for d in t["depends"] if d not in tasks]
    indeg = {i: sum(1 for d in t["depends"] if d in tasks) for i, t in tasks.items()}
    succ = {i: [] for i in tasks}
    for i, t in tasks.items():
        for d in t["depends"]:
            if d in tasks: succ[d].append(i)
    order, q = [], sorted(i for i, n in indeg.items() if n == 0)
    while q:
        n = q.pop(0); order.append(n)
        for s in sorted(succ[n]):
            indeg[s] -= 1
            if indeg[s] == 0: q.append(s)
    ef, prev = {}, {}
    for n in order:
        ps = tasks[n]["depends"]; b = max(ps, key=lambda d: ef[d]) if ps else None
        ef[n] = (ef[b] if b else 0) + tasks[n]["hours"]; prev[n] = b
    sh = {}
    for t in tasks.values(): sh[t["stream"]] = sh.get(t["stream"], 0) + t["hours"]
    return {"review": "C1_graph", "status": "ok", "task_count": len(tasks),
            "dangling_dependencies_after_exclusion": dangling,
            "is_dag": len(order) == len(tasks) and not dangling,
            "excluded_dependency_check": "W6 작업에 의존하는 범위 안 작업이 없어 제외해도 끊기는 선행관계가 없다." if not dangling else "끊긴 선행관계 있음",
            "topological_order": order, "stream_hours": sh,
            "critical_path_planned": {"hours": max(ef.values()), "tied_streams": [s for s, h in sh.items() if h == max(ef.values())]},
            "optional_in_scope": [i for i, t in tasks.items() if t["optional"]]}

# ---------- C2. 일정·차단(재계산, C1+R 합류 뒤) ----------
def review_schedule():
    g, r = jread(OUT, "C1_graph.json"), jread(OUT, "R_receipts.json")
    tasks = {t["id"]: t for t in load("tasks.json")["items"] if in_scope(t)}
    done = set(r["done"]) & set(tasks)
    st, roots = {}, {}
    for n in g["topological_order"]:
        if n in done: st[n] = "done"; continue
        deps = tasks[n]["depends"]
        st[n] = "ready" if all(d in done for d in deps) else "blocked"
        if st[n] == "blocked":
            rs = set()
            for d in deps:
                if st[d] == "ready": rs.add(d)
                elif st[d] == "blocked": rs |= set(roots[d])
            roots[n] = sorted(rs)
    bs = {}
    for n, t in tasks.items():
        s = bs.setdefault(t["stream"], {"done": 0, "ready": [], "blocked": 0, "remaining_hours": 0, "remaining_cost": 0, "owner": t["owner"]})
        if st[n] == "done": s["done"] += 1
        else:
            s["remaining_hours"] += t["hours"]; s["remaining_cost"] += t["cost"]
            if st[n] == "ready": s["ready"].append(n)
            else: s["blocked"] += 1
    longest = max(v["remaining_hours"] for v in bs.values())
    unver = [x for x in r["reported_unverified"] if x["task"] in tasks]
    return {"review": "C2_schedule", "status": "ok",
            "counts": {k: sum(1 for v in st.values() if v == k) for k in ("done", "ready", "blocked")},
            "ready": sorted(n for n, v in st.items() if v == "ready"),
            "ready_note": "W4-02는 새로 착수할 작업이 아니라 재검증이 필요한 작업(보고는 있고 verified=false).",
            "blocked_count_by_root": {k: sum(1 for v in roots.values() if k in v) for k in sorted({x for v in roots.values() for x in v})},
            "task_states": [{"task": n, "state": st[n], "blocked_by_root": roots.get(n, [])} for n in g["topological_order"]],
            "by_stream": bs,
            "remaining_hours_total": sum(v["remaining_hours"] for v in bs.values()),
            "remaining_cost_total": sum(v["remaining_cost"] for v in bs.values()),
            "remaining_critical_path": {"hours": longest, "streams": [k for k, v in bs.items() if v["remaining_hours"] == longest]},
            "bottleneck": {"unverified_report": unver,
                           "explanation": "접근성 흐름(담당4)이 남은 시간 39h로 가장 길고, 그 출발점인 W4-02가 검증되지 않아 W4-03~W4-12가 막혀 있다. 각 흐름은 담당자 1명의 직렬 사슬이다."},
            "change_vs_T1": "W6 12건 제외로 범위가 72건에서 60건이 됐다. 필수 흐름의 임계경로·병목은 T1과 같다(W6은 원래 임계 아님).",
            "deadline": {"deadline": "2026-11-20", "kept": True, "determinable": False,
                         "needed": ["담당자별 가용시간과 투입 시작일", "근무 달력(휴일)", "W4-02 재검증 소요기간",
                                    "검증 영수증 발급 소요기간", "작업 간 인계 대기시간",
                                    "자료 보정(체크섬·접근성·검색·동의) 소요기간 — 작업 목록과의 대응 미확인"]}}

# ---------- D. 운영 조건(재판정) ----------
def review_operations():
    proj, opts = load("project.json"), load("options.json")["items"]
    A = jread(OUT, "A_records.json")
    g = A["gates"]
    conds = [
        {"condition": "publication=draft_only", "verdict": "충족", "changed_from_T1": False,
         "evidence": "출력 폴더에 초안 파일만 작성했고 발송·배포·운영 변경은 없음"},
        {"condition": "외부 SaaS", "verdict": "범위 제외(사용자 결정)", "changed_from_T1": "기준 미제시 → 제외로 해소",
         "evidence": "O2(external_saas=true)를 이번 범위에서 제외. 대응 작업이 입력에 없어 작업 취소는 하지 않음"},
        {"condition": "얼굴 자동 분류", "verdict": "범위 제외(사용자 결정)", "changed_from_T1": "기준 미제시 → 제외로 해소",
         "evidence": "O3(face=true)를 이번 범위에서 제외. 대응 작업이 입력에 없어 작업 취소는 하지 않음"},
        {"condition": "검색 선택안 채택", "verdict": "미확인", "changed_from_T1": "후보가 O1 하나로 좁혀짐",
         "evidence": "남은 후보는 O1(내부 서버 기본 검색)뿐이다. 채택하겠다는 명시는 없어 확정하지 않음"},
        {"condition": "선택기능 W6", "verdict": "범위 제외(사용자 결정)", "changed_from_T1": "개통 필수 아님 → 범위 제외",
         "evidence": "W6-01~W6-12 optional=true. 필수 작업이 아니므로 임의 취소에 해당하지 않음"},
        {"condition": "개인정보(동의 확인) 전량", "verdict": "미충족", "changed_from_T1": False,
         "evidence": f"동의 yes {g['consent']['pass']}건, missing(미확인) {g['consent']['unknown']}건 — 기준 유지"},
        {"condition": "접근성 전량", "verdict": "미충족", "changed_from_T1": False,
         "evidence": f"접근성 통과 {g['accessible']['pass']}건, 실패 {g['accessible']['fail']}건. 접근성 작업 흐름도 W4-02 미검증으로 막힘"},
        {"condition": "1800건 전량 검증", "verdict": "미충족", "changed_from_T1": False,
         "evidence": f"네 조건 모두 충족 {A['record_verdicts']['usable']}건 / 1800건"},
    ]
    return {"review": "D_operations", "status": "ok", "conditions": conds,
            "standards_lowered": False, "acceptance_rule": proj["acceptance"]}

# ---------- S. 종합 ----------
def synthesize():
    A, Bd, C2, D, R = (jread(OUT, f"{n}.json") for n in ("A_records", "B_budget", "C2_schedule", "D_operations", "R_receipts"))
    g = A["gates"]
    req_states = C2["task_states"]
    req_done = C2["counts"]["done"]
    actions = [
        {"priority": 1, "area": "예산", "action": f"예산 부족 {Bd['shortfall']:,}원을 해소할 결정 요청 — 증액이나 단가 재협상. 필수 작업 취소·기준 하향은 쓸 수 없는 수단", "evidence": "B_budget.difference"},
        {"priority": 1, "area": "예산", "action": "W6-01·W6-02(완료, 103,000원)의 지출 여부 확인 — 지출됐다면 부족액이 293,000원", "evidence": "B_budget.excluded_but_already_done"},
        {"priority": 1, "area": "작업", "action": "W4-02 검증 영수증 확보 — 접근성 흐름 10건(임계 39h)의 차단 해소", "evidence": "C2_schedule.bottleneck"},
        {"priority": 1, "area": "자료", "action": f"체크섬 불일치 {g['checksum']['fail']}건 재수집·재해시", "evidence": "A_records.gates.checksum.fail_ids"},
        {"priority": 1, "area": "자료", "action": f"접근성 미통과 {g['accessible']['fail']}건 보정·재검사", "evidence": "A_records.gates.accessible.fail_ids"},
        {"priority": 1, "area": "자료", "action": f"검색 불가 {g['searchable']['fail']}건 색인 보정", "evidence": "A_records.gates.searchable.fail_ids"},
        {"priority": 1, "area": "자료", "action": f"동의 missing {g['consent']['unknown']}건 동의 여부 확정", "evidence": "A_records.gates.consent.unknown_ids"},
        {"priority": 2, "area": "작업", "action": "즉시 착수 가능: " + ", ".join(t for t in C2["ready"] if t != "W4-02"), "evidence": "C2_schedule.ready"},
        {"priority": 2, "area": "일정", "action": "담당자 가용시간·근무 달력·자료 보정 기간을 확보해 11-20 기한 판정", "evidence": "C2_schedule.deadline.needed"},
        {"priority": 3, "area": "운영", "action": "검색 선택안으로 O1 채택 여부 확정, O1에 대응하는 작업 명시", "evidence": "D_operations.conditions"},
    ]
    return {"review": "S_synthesis", "status": "ok",
            "summary": {
                "records": {"verdict": A["verdict"], "usable": A["record_verdicts"]["usable"], "not_usable": A["record_verdicts"]["not_usable"],
                            "unconfirmed_only": A["record_verdicts"]["unconfirmed_only"], "reused_from_T1": True},
                "budget": {"verdict": Bd["verdict"], "in_scope_cost": Bd["in_scope_cost"], "budget": Bd["budget"], "shortfall": Bd["shortfall"]},
                "tasks": {"in_scope": len(req_states), "done": req_done, "ready": C2["ready"], "blocked": C2["counts"]["blocked"],
                          "remaining_hours_total": C2["remaining_hours_total"], "remaining_cost_total": C2["remaining_cost_total"],
                          "remaining_critical_path": C2["remaining_critical_path"]},
                "operations": {c["condition"]: c["verdict"] for c in D["conditions"]},
            },
            "final_verdict": {"open_ready": False, "label": "개통 불가(미충족)",
                              "reasons": [f"자료 전량 충족 아님({A['record_verdicts']['usable']}/1800)",
                                          f"범위 안 필수 작업 {len(req_states)}건 중 완료 {req_done}건",
                                          f"범위 축소 후에도 예산 {Bd['shortfall']:,}원 부족", "W4-02 미검증"],
                              "distinction": "인수 검토 완료이며 실제 개통 완료가 아님. 초안만 작성."},
            "integrity_of_change": {"required_tasks_cancelled": [], "standards_lowered": False,
                                    "excluded_by_user": Bd["excluded_tasks"] + ["O2", "O3"],
                                    "note": "제외는 사용자가 명시한 W6·O2·O3뿐. 필수 작업 60건은 모두 범위에 남아 있다."},
            "priority_actions": actions,
            "blocked_or_failed_reviews": [j["job"] for j in LOG if j["status"] != "ok"],
            "observations": ["README '88회차' 표기와 폴더 89회차 불일치(기록만)",
                             "tasks.json status는 모두 planned — 완료 판정은 영수증 기준"]}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    started = now()
    # 1단계(병렬): 재사용 2건 + 서로 독립인 재계산 1건(C1). B·D는 A/R 결과를 읽으므로 2단계.
    stage1 = [
        ("A_records", ["project.json", "records.json"], reuse("A_records", ["project.json", "records.json"],
            "자료 검증은 records와 네 조건으로만 정해진다. 예산·범위 변경과 무관하고 기준도 유지된다."), "reused"),
        ("R_receipts", ["tasks.json", "receipts.json"], reuse("R_receipts", ["tasks.json", "receipts.json"],
            "완료 판정은 영수증 규칙으로만 정해진다. 범위 제외는 C2에서 반영한다."), "reused"),
        ("C1_graph", ["tasks.json"], review_graph, "recomputed"),
    ]
    bar = threading.Barrier(len(stage1))
    def go(j): bar.wait(timeout=10); return run_job(*j)
    with ThreadPoolExecutor(max_workers=len(stage1), thread_name_prefix="stage1") as ex: list(ex.map(go, stage1))
    join1 = now()
    # 2단계(병렬): B(R 필요)·D(A 필요)·C2(C1+R 필요)
    stage2 = [("B_budget", ["tasks.json", "options.json", "project.json"], review_budget, "recomputed", ["R_receipts"]),
              ("D_operations", ["project.json", "options.json", "README.txt"], review_operations, "recomputed", ["A_records"]),
              ("C2_schedule", ["tasks.json", "project.json"], review_schedule, "recomputed", ["C1_graph", "R_receipts"])]
    bar2 = threading.Barrier(len(stage2))
    def go2(j): bar2.wait(timeout=10); return run_job(*j)
    with ThreadPoolExecutor(max_workers=len(stage2), thread_name_prefix="stage2") as ex: list(ex.map(go2, stage2))
    join2 = now()
    run_job("S_synthesis", FILES, synthesize, "recomputed", ["A_records", "B_budget", "C2_schedule", "D_operations", "R_receipts"])
    def overlap(names):
        s = [r for r in LOG if r["job"] in names]
        return max(r["started_at"] for r in s) < min(r["ended_at"] for r in s)
    write("run_log.json", {
        "turn": "T2", "run_started_at": started, "run_ended_at": now(), "condition_change": CHANGE,
        "input_versions": INPUT_VERSIONS, "inputs_same_as_T1": SAME_INPUTS,
        "t1_run_log_sha256": sha(os.path.join(T1, "run_log.json")),
        "stages": [
            {"stage": 1, "mode": "parallel", "jobs": [j[0] for j in stage1], "all_started_before_first_end": overlap({j[0] for j in stage1}), "join_at": join1},
            {"stage": 2, "mode": "parallel after join 1", "jobs": [j[0] for j in stage2], "all_started_before_first_end": overlap({j[0] for j in stage2}), "join_at": join2},
            {"stage": 3, "mode": "after join 2", "jobs": ["S_synthesis"]}],
        "reused": [j["job"] for j in LOG if j["mode"] == "reused" and j["status"] == "ok"],
        "recomputed": [j["job"] for j in LOG if j["mode"] == "recomputed"],
        "jobs": LOG})
    print(json.dumps([{k: r.get(k) for k in ("job", "mode", "status", "thread", "started_at", "ended_at", "output_sha256", "error")} for r in LOG], ensure_ascii=False, indent=1))
