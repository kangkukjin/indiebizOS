"""T1 개통 준비 검토 — 독립 검토는 병렬, 의존 검토는 합류 뒤 실행.
사용: python3 -I review.py <inputs_dir> <out_dir>
"""
import hashlib, json, os, sys, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

IN, OUT = sys.argv[1], sys.argv[2]
FILES = ["README.txt", "project.json", "options.json", "receipts.json", "records.json", "tasks.json"]
LOG = []
LOCK = threading.Lock()
RESULTS = {}

def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="microseconds")

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

def load(name):
    return json.load(open(os.path.join(IN, name), encoding="utf-8"))

def write(name, obj):
    p = os.path.join(OUT, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return p

INPUT_VERSIONS = {f: sha(os.path.join(IN, f)) for f in FILES}

def run_job(job_id, inputs, fn, after=None):
    """작업 하나를 실행하고 입력 판본·시작·종료·산출물 지문을 기록한다. 실패는 격리한다."""
    rec = {"job": job_id, "inputs": {f: INPUT_VERSIONS[f] for f in inputs},
           "upstream": after or [], "thread": threading.current_thread().name,
           "started_at": now(), "t0": time.perf_counter()}
    try:
        missing = [u for u in (after or []) if RESULTS.get(u, {}).get("status") != "ok"]
        if missing:
            raise RuntimeError(f"선행 검토 실패: {missing}")
        result = fn()
        result["job"] = job_id
        result["input_versions"] = rec["inputs"]
        if after:
            result["upstream_outputs"] = {u: RESULTS[u]["output_sha256"] for u in after}
        out = f"{job_id}.json"
        write(out, result)
        rec.update(status="ok", output=out, output_sha256=sha(os.path.join(OUT, out)))
    except Exception as e:
        rec.update(status="failed", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc(limit=3))
    rec["ended_at"] = now()
    rec["duration_ms"] = round((time.perf_counter() - rec.pop("t0")) * 1000, 3)
    with LOCK:
        LOG.append(rec)
        RESULTS[job_id] = rec
    return rec

# ---------- A. 자료 사용 가능 여부 ----------
GATES = [("consent", "동의 확인", lambda v: v == "yes", lambda v: v == "no"),
         ("checksum", "체크섬 일치", lambda v: v == "pass", lambda v: v == "fail"),
         ("searchable", "검색 가능", lambda v: v is True, lambda v: v is False),
         ("accessible", "접근성 통과", lambda v: v is True, lambda v: v is False)]

def gate_state(field, v, ok, bad):
    if v is None or v == "missing" or v == "":
        return "unknown"
    if ok(v): return "pass"
    if bad(v): return "fail"
    return "unknown"

def review_records():
    proj, data = load("project.json"), load("records.json")
    items = data["items"]
    ids = [r.get("id") for r in items]
    expected = [f"D{i:04d}" for i in range(1, proj["expected_records"] + 1)]
    dup = sorted({i for i in ids if ids.count(i) > 1}) if len(set(ids)) != len(ids) else []
    gate_summary, per = {}, []
    for field, label, ok, bad in GATES:
        c = {"pass": [], "fail": [], "unknown": []}
        for r in items:
            c[gate_state(field, r.get(field), ok, bad)].append(r["id"])
        gate_summary[field] = {"label": label, "pass": len(c["pass"]), "fail": len(c["fail"]),
                               "unknown": len(c["unknown"]), "fail_ids": c["fail"], "unknown_ids": c["unknown"],
                               "raw_values": sorted({repr(r.get(field)) for r in items})}
    for r in items:
        st = {f: gate_state(f, r.get(f), ok, bad) for f, _, ok, bad in GATES}
        fails = [f for f, s in st.items() if s == "fail"]
        unk = [f for f, s in st.items() if s == "unknown"]
        verdict = "usable" if not fails and not unk else ("not_usable" if fails else "unconfirmed")
        per.append({"id": r["id"], "collection": r.get("collection"), "verdict": verdict, "failed": fails, "unknown": unk})
    by = {v: [p for p in per if p["verdict"] == v] for v in ("usable", "not_usable", "unconfirmed")}
    coll = {}
    for p in per:
        c = coll.setdefault(p["collection"], {"usable": 0, "not_usable": 0, "unconfirmed": 0})
        c[p["verdict"]] += 1
    multi = [p for p in per if len(p["failed"]) + len(p["unknown"]) > 1]
    return {
        "review": "A_records", "status": "ok",
        "rule": "네 조건 모두 필수. 명시적 실패(fail/false)는 실패, 'missing' 등 누락은 미확인(실패로 단정하지 않음).",
        "data_version": data.get("version"),
        "integrity": {"expected": proj["expected_records"], "actual": len(items), "unique_ids": len(set(ids)),
                      "duplicates": dup, "missing_ids": sorted(set(expected) - set(ids)),
                      "unexpected_ids": sorted(set(ids) - set(expected))},
        "gates": gate_summary,
        "record_verdicts": {"usable": len(by["usable"]), "not_usable": len(by["not_usable"]),
                            "unconfirmed_only": len(by["unconfirmed"])},
        "records_with_multiple_issues": [{"id": p["id"], "failed": p["failed"], "unknown": p["unknown"]} for p in multi],
        "by_collection": coll,
        "not_usable": [{"id": p["id"], "failed": p["failed"], "unknown": p["unknown"]} for p in by["not_usable"]],
        "unconfirmed_ids": [p["id"] for p in by["unconfirmed"]],
        "all_records_pass": len(by["usable"]) == proj["expected_records"] and len(items) == proj["expected_records"],
        "verdict": "충족" if len(by["usable"]) == proj["expected_records"] else "미충족",
    }

# ---------- B. 예산 ----------
def review_budget():
    proj, tasks, opts = load("project.json"), load("tasks.json")["items"], load("options.json")
    total = sum(t["cost"] for t in tasks)
    req = sum(t["cost"] for t in tasks if not t["optional"])
    optc = sum(t["cost"] for t in tasks if t["optional"])
    streams = {}
    for t in tasks:
        streams[t["stream"]] = streams.get(t["stream"], 0) + t["cost"]
    osum = sum(o["cost"] for o in opts["items"])
    return {
        "review": "B_budget", "status": "ok",
        "rule": "tasks.cost 합계가 정본. options.cost는 작업원가에 포함된 비교 정보로 다시 더하지 않음.",
        "budget": proj["budget"], "tasks_total_cost": total, "required_tasks_cost": req, "optional_tasks_cost": optc,
        "by_stream": streams, "remaining": proj["budget"] - total, "utilization_pct": round(total / proj["budget"] * 100, 2),
        "options_cost_double_counted": False,
        "options_reference": [{"id": o["id"], "name": o["name"], "cost": o["cost"]} for o in opts["items"]],
        "observation": (f"선택안 견적 합 {osum:,}원이 tasks 총액 {total:,}원보다 크므로 세 선택안이 모두 작업원가에 "
                        "동시에 들어 있다고 볼 수는 없다. 어떤 선택안이 어느 작업에 대응하는지는 입력에 없어 매핑은 미확인."),
        "verdict": "충족" if total <= proj["budget"] else "초과",
    }

# ---------- C1. 작업 그래프 ----------
def review_graph():
    tasks = load("tasks.json")["items"]
    ids = {t["id"]: t for t in tasks}
    dangling = [{"task": t["id"], "missing": d} for t in tasks for d in t["depends"] if d not in ids]
    indeg = {i: 0 for i in ids}
    succ = {i: [] for i in ids}
    for t in tasks:
        for d in t["depends"]:
            if d in ids:
                indeg[t["id"]] += 1; succ[d].append(t["id"])
    order, q = [], sorted(i for i, n in indeg.items() if n == 0)
    while q:
        n = q.pop(0); order.append(n)
        for s in sorted(succ[n]):
            indeg[s] -= 1
            if indeg[s] == 0: q.append(s)
    cyclic = sorted(set(ids) - set(order))
    def cp(subset):
        ef, prev = {}, {}
        for n in order:
            if n not in subset: continue
            ps = [d for d in ids[n]["depends"] if d in subset]
            best = max(ps, key=lambda d: ef[d]) if ps else None
            ef[n] = (ef[best] if best else 0) + ids[n]["hours"]; prev[n] = best
        end = max(ef, key=ef.get); path = []
        while end: path.append(end); end = prev[end]
        return path[::-1], max(ef.values()), ef
    req = {i for i, t in ids.items() if not t["optional"]}
    path_all, len_all, ef_all = cp(set(ids))
    path_req, len_req, _ = cp(req)
    stream_hours = {}
    for t in tasks:
        stream_hours[t["stream"]] = stream_hours.get(t["stream"], 0) + t["hours"]
    fan = sorted(((i, len(s)) for i, s in succ.items() if len(s) > 1), key=lambda x: -x[1])
    return {
        "review": "C1_graph", "status": "ok",
        "task_count": len(tasks), "roots": sorted(i for i, t in ids.items() if not t["depends"]),
        "dangling_dependencies": dangling, "cycle_members": cyclic, "is_dag": not cyclic and not dangling,
        "topological_order": order,
        "successors": succ,
        "stream_hours": stream_hours,
        "critical_path_required": {"path": path_req, "hours": len_req},
        "critical_path_all": {"path": path_all, "hours": len_all,
                              "tied_chains": [s for s, h in stream_hours.items() if h == len_all]},
        "multi_successor_nodes": fan,
        "structure_note": "6개 흐름(W1~W6)이 각각 12개 작업의 단일 직렬 사슬이며 흐름 사이 선행관계는 없다.",
        "hours_note": "hours는 순수 작업시간 합. 달력·인력 가용시간이 없어 기한(2026-11-20) 준수는 확정하지 않는다.",
    }

# ---------- R. 완료 판정 ----------
def review_receipts():
    tasks = load("tasks.json")["items"]
    rc = load("receipts.json")["items"]
    rmap = {r["task_id"]: r for r in rc}
    orphan = [r["task_id"] for r in rc if r["task_id"] not in {t["id"] for t in tasks}]
    rows = []
    for t in tasks:
        r = rmap.get(t["id"])
        if r is None: st, why = "not_done", "영수증 없음"
        elif r.get("reported_done") and r.get("verified"): st, why = "done", f"보고+검증({r.get('receipt')})"
        elif r.get("reported_done"): st, why = "reported_unverified", f"보고만 있고 verified=false({r.get('receipt')})"
        else: st, why = "not_done", "완료 보고 없음"
        rows.append({"task": t["id"], "state": st, "reason": why, "listed_status": t["status"]})
    cnt = {}
    for r in rows: cnt[r["state"]] = cnt.get(r["state"], 0) + 1
    return {"review": "R_receipts", "status": "ok",
            "rule": "reported_done과 verified가 모두 참일 때만 완료.",
            "receipts_count": len(rc), "orphan_receipts": orphan, "counts": cnt,
            "done": [r["task"] for r in rows if r["state"] == "done"],
            "reported_unverified": [r for r in rows if r["state"] == "reported_unverified"],
            "tasks": rows,
            "listed_status_note": "tasks.json의 status는 72건 모두 'planned'로 영수증(11건 완료)과 다르다. 완료 판정은 영수증 기준."}

# ---------- C2. 실행 가능·차단 전파 (C1+R 합류 뒤) ----------
def review_schedule():
    g = json.load(open(os.path.join(OUT, "C1_graph.json"), encoding="utf-8"))
    r = json.load(open(os.path.join(OUT, "R_receipts.json"), encoding="utf-8"))
    tasks = {t["id"]: t for t in load("tasks.json")["items"]}
    done = set(r["done"])
    state = {}
    for n in g["topological_order"]:
        if n in done: state[n] = "done"; continue
        deps = tasks[n]["depends"]
        state[n] = "ready" if all(d in done for d in deps) else "blocked"
    blocked_by = {}
    for n in g["topological_order"]:
        if state[n] == "blocked":
            src = [d for d in tasks[n]["depends"] if state[d] != "done"]
            roots = set()
            for d in src:
                roots |= ({d} if state[d] == "ready" else set(blocked_by[d]))
            blocked_by[n] = sorted(roots)
    rem = {}
    for n in g["topological_order"]:
        if state[n] == "done": continue
        rem[n] = tasks[n]["hours"] + max([rem.get(d, 0) for d in tasks[n]["depends"]] or [0])
    by_stream = {}
    for n, t in tasks.items():
        s = by_stream.setdefault(t["stream"], {"optional": t["optional"], "done": 0, "ready": [], "blocked": 0, "remaining_hours": 0})
        if state[n] == "done": s["done"] += 1
        elif state[n] == "ready": s["ready"].append(n)
        else: s["blocked"] += 1
        if state[n] != "done": s["remaining_hours"] += t["hours"]
    req_rem = {k: v["remaining_hours"] for k, v in by_stream.items() if not v["optional"]}
    longest = max(req_rem.values())
    w4 = r["reported_unverified"]
    return {
        "review": "C2_schedule", "status": "ok",
        "rule": "선행 작업이 모두 영수증 완료일 때만 ready. 미완료에 의존하면 전이적으로 blocked.",
        "counts": {k: sum(1 for v in state.values() if v == k) for k in ("done", "ready", "blocked")},
        "ready": sorted(n for n, v in state.items() if v == "ready"),
        "blocked_count_by_root": {k: sum(1 for v in blocked_by.values() if k in v) for k in sorted({x for v in blocked_by.values() for x in v})},
        "task_states": [{"task": n, "state": state[n], "optional": tasks[n]["optional"], "blocked_by_root": blocked_by.get(n, [])} for n in g["topological_order"]],
        "by_stream": by_stream,
        "remaining_critical_path_required": {"hours": longest, "streams": [k for k, v in req_rem.items() if v == longest]},
        "bottleneck": {
            "unverified_report": w4,
            "explanation": ("W4-02는 완료 보고는 있으나 verified=false라 완료가 아니다. W4-03~W4-12(10건)가 이 한 건에 막혀 있고, "
                            "접근성 흐름 잔여 순수작업시간이 필수 흐름 중 최장이다. 각 흐름이 담당자 1명의 직렬 사슬이라 흐름 내부 병렬화는 불가능하며, "
                            "흐름별 담당자 가용시간이 실질 병목이 된다."),
        },
        "deadline": {"deadline": load("project.json")["deadline"], "determinable": False,
                     "needed": ["담당자별 일일·주간 가용시간과 투입 시작일", "근무 달력(휴일·주말)",
                                "W4-02 재검증 소요기간", "검증 영수증 발급 소요기간", "작업 간 대기·인계 시간"]},
    }

# ---------- D. 운영 조건 ----------
def review_operations():
    proj, opts, tasks = load("project.json"), load("options.json")["items"], load("tasks.json")["items"]
    conds = [
        {"condition": "publication=draft_only (초안만, 실제 발송·배포 금지)", "verdict": "충족",
         "evidence": f"project.publication={proj['publication']!r}; 이번 검토는 지정 출력 폴더에 초안 파일만 작성, 발송·배포·운영 변경 없음"},
        {"condition": "외부 SaaS 사용 허용 여부", "verdict": "기준 미제시",
         "evidence": "options에 external_saas 속성은 있으나 project·README에 허용/금지 기준이 없음. O2만 external_saas=true"},
        {"condition": "얼굴 자동 분류 허용 여부", "verdict": "기준 미제시",
         "evidence": "options에 face 속성은 있으나 허용/금지 기준이 없음. O3만 face=true"},
        {"condition": "선택안 채택 결정", "verdict": "미확인",
         "evidence": "어떤 선택안(O1~O3)을 채택했는지, 어느 작업과 대응하는지 입력에 없음"},
        {"condition": "선택기능 흐름(W6, optional) 진행", "verdict": "개통 필수 아님",
         "evidence": "W6-01~12 optional=true. 영수증상 W6-01·02 완료. acceptance는 '필수 작업' 완료만 요구"},
        {"condition": "개통 인수 기준(acceptance)", "verdict": "C·A 결과에 의존(종합에서 판정)",
         "evidence": proj["acceptance"]},
    ]
    return {"review": "D_operations", "status": "ok", "conditions": conds,
            "options": [{**o, "conflicts_with_stated_rule": None, "rule_status": "기준 미제시" if (o["external_saas"] or o["face"]) else "제약 속성 없음"} for o in opts],
            "note": "external_saas·face에 대한 정책 기준이 주어지면 O2·O3의 적합성을 재판정해야 한다(이 검토만 재실행 대상)."}

# ---------- S. 종합 ----------
def synthesize():
    A = json.load(open(os.path.join(OUT, "A_records.json"), encoding="utf-8"))
    B = json.load(open(os.path.join(OUT, "B_budget.json"), encoding="utf-8"))
    C2 = json.load(open(os.path.join(OUT, "C2_schedule.json"), encoding="utf-8"))
    C1 = json.load(open(os.path.join(OUT, "C1_graph.json"), encoding="utf-8"))
    D = json.load(open(os.path.join(OUT, "D_operations.json"), encoding="utf-8"))
    req_states = [t for t in C2["task_states"] if not t["optional"]]
    req_done = sum(1 for t in req_states if t["state"] == "done")
    g = A["gates"]
    actions = [
        {"priority": 1, "area": "자료", "action": f"체크섬 불일치 {g['checksum']['fail']}건 원본 재수집·재해시", "evidence": "A_records.gates.checksum.fail_ids"},
        {"priority": 1, "area": "자료", "action": f"접근성 미통과 {g['accessible']['fail']}건 보정 후 재검사", "evidence": "A_records.gates.accessible.fail_ids"},
        {"priority": 1, "area": "자료", "action": f"검색 불가 {g['searchable']['fail']}건 색인 보정", "evidence": "A_records.gates.searchable.fail_ids"},
        {"priority": 1, "area": "자료", "action": f"동의 'missing' {g['consent']['unknown']}건 동의 여부 확인(미확인 → 확정)", "evidence": "A_records.gates.consent.unknown_ids"},
        {"priority": 1, "area": "작업", "action": "W4-02 검증 영수증 확보(verified=false) — W4-03~W4-12 차단 해소", "evidence": "R_receipts.reported_unverified; C2_schedule.blocked_count_by_root"},
        {"priority": 2, "area": "작업", "action": "즉시 착수 가능한 필수 작업 착수: " + ", ".join(t for t in C2["ready"] if not t.startswith("W6")), "evidence": "C2_schedule.ready"},
        {"priority": 2, "area": "일정", "action": "담당자 가용시간·근무 달력 확보 후 기한(2026-11-20) 준수 판정", "evidence": "C2_schedule.deadline.needed"},
        {"priority": 3, "area": "운영", "action": "외부 SaaS·얼굴 자동 분류 허용 기준과 채택 선택안 결정", "evidence": "D_operations.conditions"},
        {"priority": 3, "area": "예산", "action": "선택안 견적과 작업원가의 대응관계 확인(견적 합이 작업 총액 초과)", "evidence": "B_budget.observation"},
    ]
    blocked_reviews = [r["job"] for r in LOG if r["status"] != "ok"]
    return {
        "review": "S_synthesis", "status": "ok",
        "project": load("project.json")["project"],
        "summary": {
            "records": {"verdict": A["verdict"], "usable": A["record_verdicts"]["usable"], "not_usable": A["record_verdicts"]["not_usable"],
                        "unconfirmed_only": A["record_verdicts"]["unconfirmed_only"], "expected": A["integrity"]["expected"]},
            "budget": {"verdict": B["verdict"], "total": B["tasks_total_cost"], "budget": B["budget"], "remaining": B["remaining"]},
            "tasks": {"required_total": len(req_states), "required_done": req_done, "ready": C2["ready"],
                      "counts_all": C2["counts"], "critical_path_hours_required": C1["critical_path_required"]["hours"],
                      "remaining_critical_hours": C2["remaining_critical_path_required"]},
            "operations": {c["condition"]: c["verdict"] for c in D["conditions"]},
        },
        "acceptance_rule": load("project.json")["acceptance"],
        "final_verdict": {
            "open_ready": False,
            "label": "개통 불가(미충족)",
            "reasons": [f"자료 {A['integrity']['expected']}건 중 네 조건 전부 충족 {A['record_verdicts']['usable']}건뿐",
                        f"필수 작업 {len(req_states)}건 중 영수증 완료 {req_done}건",
                        "W4-02 보고만 있고 미검증"],
            "distinction": "이 판정은 '인수 검토 완료'이며 실제 개통 완료가 아니다. publication=draft_only로 아무것도 배포하지 않았다.",
        },
        "priority_actions": actions,
        "blocked_or_failed_reviews": blocked_reviews,
        "observations": ["README에 '88회차'로 표기되어 있으나 폴더는 89회차(기록만, 판정 영향 없음)",
                         C1["structure_note"], R_NOTE[0]],
    }
R_NOTE = ["tasks.json status는 72건 모두 'planned'로 영수증과 불일치 — 완료는 영수증 기준으로 판정"]

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    run_started = now()
    # 1단계: 서로 독립인 검토 5개를 실제 병렬 실행
    stage1 = [("A_records", ["project.json", "records.json"], review_records),
              ("B_budget", ["project.json", "tasks.json", "options.json"], review_budget),
              ("C1_graph", ["tasks.json"], review_graph),
              ("R_receipts", ["tasks.json", "receipts.json"], review_receipts),
              ("D_operations", ["project.json", "options.json", "tasks.json", "README.txt"], review_operations)]
    barrier = threading.Barrier(len(stage1))
    def gated(j):
        barrier.wait(timeout=10)  # 동시에 출발시켜 병렬 구간을 기록으로 확인할 수 있게 한다
        return run_job(*j)
    with ThreadPoolExecutor(max_workers=len(stage1), thread_name_prefix="stage1") as ex:
        list(ex.map(gated, stage1))
    join1 = now()
    # 2단계: C1·R 합류 뒤 실행 가능·차단 전파
    run_job("C2_schedule", ["tasks.json", "project.json"], review_schedule, after=["C1_graph", "R_receipts"])
    join2 = now()
    # 3단계: 전체 합류 뒤 종합
    run_job("S_synthesis", FILES, synthesize, after=["A_records", "B_budget", "C2_schedule", "D_operations"])
    s1 = [r for r in LOG if r["job"] in {j[0] for j in stage1}]
    overlap = max(r["started_at"] for r in s1) < min(r["ended_at"] for r in s1)
    write("run_log.json", {
        "turn": "T1", "run_started_at": run_started, "run_ended_at": now(),
        "input_dir": IN, "input_versions": INPUT_VERSIONS,
        "stages": [
            {"stage": 1, "mode": "parallel(ThreadPoolExecutor, barrier start)", "jobs": [j[0] for j in stage1],
             "all_started_before_first_end": overlap, "join_at": join1},
            {"stage": 2, "mode": "after join(C1_graph, R_receipts)", "jobs": ["C2_schedule"], "join_at": join2},
            {"stage": 3, "mode": "after join(A, B, C2, D)", "jobs": ["S_synthesis"]},
        ],
        "jobs": LOG,
        "reuse_map": {"records.json": ["A_records", "S_synthesis"], "receipts.json": ["R_receipts", "C2_schedule", "S_synthesis"],
                      "tasks.json": ["B_budget", "C1_graph", "R_receipts", "C2_schedule", "D_operations", "S_synthesis"],
                      "options.json": ["B_budget", "D_operations", "S_synthesis"],
                      "project.json": ["A_records", "B_budget", "C2_schedule", "D_operations", "S_synthesis"],
                      "README.txt": ["D_operations", "S_synthesis"]},
        "reuse_note": "후속 턴에서 바뀐 입력의 sha256을 이 판본과 비교해 reuse_map에 걸린 작업만 재실행하고 나머지 결과는 지문으로 이어 쓴다.",
    })
    print(json.dumps([{k: r.get(k) for k in ("job", "status", "started_at", "ended_at", "duration_ms", "error")} for r in LOG], ensure_ascii=False, indent=1))
