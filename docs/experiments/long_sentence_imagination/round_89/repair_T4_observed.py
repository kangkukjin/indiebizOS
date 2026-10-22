"""지역자료실 이전·검색 서비스 개통 준비 인수 검토 (턴별 실행기).

사용: python3 -I review.py --inputs <입력폴더> --out <ai/Tn> [--prev <ai/Tm>] [--conditions <조건.json>]
- T2 추가: --conditions 로 사용자 변경 조건(예산·제외 스트림·제외 선택안)을 받는다. 조건은 해당 검토의
  입력 조각(conditions#...)으로 지문에 들어가므로, 조건을 쓰지 않는 검토(data_gates)는 지문이 같아 재사용된다.
- 독립 검토 4개(data_gates·budget·schedule·operations)를 스레드로 동시 실행한다.
- 각 검토는 자기가 쓰는 입력 조각의 지문(sha256)을 남긴다. --prev 의 원장에서
  같은 검토의 지문이 같으면 결과 파일을 재사용(reused)하고, 다르면 재수행한다.
- 합류(merge)는 네 검토가 모두 끝난 뒤 시작하며, 실패한 검토는 blocked 로 남긴다.
- T3 추가: 미확인 사유(레코드 없음·필드 없음·값 missing/이상)를 나눠 집계하고, 직전 턴 대비 ID 단위 판정 차이와
  입력 지문 기반 재사용/재수행 사유를 원장에 남긴다. 자료 검토 실패 시 자료 판정은 보류(직전 결과는 참고만).
입력 폴더에는 쓰지 않는다.
"""
import argparse, concurrent.futures as cf, hashlib, json, os, shutil, sys, threading, time, traceback
from datetime import datetime, timezone

KST_NOTE = "시각은 UTC ISO8601(마이크로초)"
COND = {}  # --conditions 로 채움(사용자 변경 조건). 비면 T1과 같은 동작


def in_scope(tid):
    return not any(tid.startswith(p + "-") for p in COND.get("excluded_streams", []))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    with open(p, "rb") as f:
        return sha_bytes(f.read())


def canon(v):
    return sha_bytes(json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


# ---------------------------------------------------------------- 입력 적재
def load_inputs(d):
    files = {}
    for name in ["README.txt", "project.json", "options.json", "receipts.json", "records.json", "tasks.json"]:
        p = os.path.join(d, name)
        ent = {"path": p}
        try:
            raw = open(p, "rb").read()
            ent["sha256"] = sha_bytes(raw)
            ent["bytes"] = len(raw)
            if name.endswith(".json"):
                ent["data"] = json.loads(raw.decode("utf-8"))
            else:
                ent["data"] = raw.decode("utf-8")
            ent["status"] = "ok"
        except Exception as e:  # 읽기 실패는 파일 단위로 가둔다
            ent["status"] = "read_failed"
            ent["error"] = f"{type(e).__name__}: {e}"
        files[name] = ent
    return files


def need(files, name):
    ent = files[name]
    if ent["status"] != "ok":
        raise RuntimeError(f"입력 {name} 읽기 실패: {ent.get('error')}")
    return ent["data"]


# ---------------------------------------------------------------- 검토 정의
# 각 검토: (사용 입력 조각 추출 함수, 실행 함수, 의존 검토)
GATES = [("consent", "동의 확인"), ("checksum", "체크섬 일치"), ("searchable", "검색 가능"), ("accessible", "접근성 통과")]


def gate_state(field, v):
    """한 자료의 한 조건 판정: pass / fail / unknown(누락·이상값)."""
    if field == "consent":
        if v == "yes":
            return "pass"
        if v in ("no", "denied", "refused"):
            return "fail"
        return "unknown"  # 'missing'·누락·기타 = 동의 기록 없음 → 미확인
    if field == "checksum":
        return {"pass": "pass", "fail": "fail"}.get(v, "unknown")
    if v is True:
        return "pass"
    if v is False:
        return "fail"
    return "unknown"


def slice_data_gates(files):
    p = need(files, "project.json")
    return {"records.json": need(files, "records.json"),
            "project.json#expected_records,gates": {"expected_records": p.get("expected_records"), "gates": p.get("gates")}}


def run_data_gates(sl):
    rec = sl["records.json"]
    exp_n = sl["project.json#expected_records,gates"]["expected_records"]
    items = rec.get("items", [])
    expected_ids = [f"D{i:04d}" for i in range(1, (exp_n or 0) + 1)]
    seen, dup, malformed = {}, [], []
    for idx, it in enumerate(items):
        if not isinstance(it, dict) or "id" not in it:
            malformed.append({"index": idx, "reason": "객체 아님 또는 id 없음"})
            continue
        if it["id"] in seen:
            dup.append(it["id"])
        else:
            seen[it["id"]] = it
    missing_ids = [i for i in expected_ids if i not in seen]
    unexpected_ids = sorted(i for i in seen if i not in set(expected_ids))
    per_gate = {}
    overall = {"pass": [], "fail": [], "unknown": []}
    per_record = []
    for f, label in GATES:
        per_gate[f] = {"label": label, "pass": [], "fail": [], "unknown": [], "missing_field": []}
    unknown_reason = {"record_absent": [], "field_absent": {f: [] for f, _ in GATES}, "value_missing_or_invalid": {f: [] for f, _ in GATES}}
    for rid in expected_ids:
        it = seen.get(rid)
        if it is None:
            overall["unknown"].append(rid)
            unknown_reason["record_absent"].append(rid)
            for f, _ in GATES:
                per_gate[f]["unknown"].append(rid)
            per_record.append({"id": rid, "verdict": "unknown", "reason": "레코드 없음(파일에 행이 없음)",
                               "failed": [], "unknown": [f for f, _ in GATES], "unknown_cause": "record_absent"})
            continue
        states = {}
        for f, _ in GATES:
            if f not in it:
                per_gate[f]["missing_field"].append(rid)
                unknown_reason["field_absent"][f].append(rid)
                s = "unknown"
            else:
                s = gate_state(f, it[f])
                if s == "unknown":
                    unknown_reason["value_missing_or_invalid"][f].append(rid)
            per_gate[f][s].append(rid)
            states[f] = s
        if all(s == "pass" for s in states.values()):
            v = "pass"
        elif any(s == "fail" for s in states.values()):
            v = "fail"  # 하나라도 확정 불충족이면 사용 불가
        else:
            v = "unknown"
        overall[v].append(rid)
        if v != "pass":
            per_record.append({"id": rid, "collection": it.get("collection"), "verdict": v,
                               "failed": [f for f, s in states.items() if s == "fail"],
                               "unknown": [f for f, s in states.items() if s == "unknown"],
                               "raw": {f: it.get(f, "<누락>") for f, _ in GATES}})
    # 컬렉션별 집계
    by_coll = {}
    for rid in expected_ids:
        it = seen.get(rid) or {}
        c = it.get("collection", "<없음>")
        b = by_coll.setdefault(c, {"total": 0, "pass": 0, "fail": 0, "unknown": 0})
        b["total"] += 1
    for v in ("pass", "fail", "unknown"):
        for rid in overall[v]:
            c = (seen.get(rid) or {}).get("collection", "<없음>")
            by_coll[c][v] += 1
    # 불충족 조건 조합
    combos = {}
    for r in per_record:
        key = "fail:" + "+".join(r.get("failed", [])) + "|unknown:" + "+".join(r.get("unknown", []))
        if r.get("unknown_cause") == "record_absent":
            key = "unknown:record_absent"
        combos[key] = combos.get(key, 0) + 1
    gates_out = {f: {"label": g["label"], "pass": len(g["pass"]), "fail": len(g["fail"]), "unknown": len(g["unknown"]),
                     "unknown_record_absent": len(unknown_reason["record_absent"]),
                     "unknown_field_absent": len(unknown_reason["field_absent"][f]),
                     "unknown_value": len(unknown_reason["value_missing_or_invalid"][f]),
                     "fail_ids": g["fail"], "unknown_ids": g["unknown"], "missing_field_ids": g["missing_field"],
                     "unknown_value_ids": unknown_reason["value_missing_or_invalid"][f]}
                 for f, g in per_gate.items()}
    total = len(expected_ids)
    counts = {k: len(v) for k, v in overall.items()}
    assert sum(counts.values()) == total, "전체 판정 합이 기대 건수와 다름"
    return {
        "review": "data_gates",
        "rules": {"consent": "yes=충족, no류=미충족, 'missing'·누락·기타=미확인(README: 누락 항목은 미확인)",
                  "checksum": "pass=충족, fail=미충족, 그 외=미확인",
                  "searchable/accessible": "true=충족, false=미충족, 그 외=미확인",
                  "record_absent": "기대 ID(D0001~expected_records)에 해당하는 행이 파일에 없으면 네 조건 모두 미확인(사용 불가 아님)",
                  "overall": "네 조건 모두 충족=사용 가능, 하나라도 미충족=사용 불가, 미충족 없이 미확인 포함=미확인"},
        "records_version": rec.get("version"),
        "expected_records": total, "rows_in_file": len(items),
        "integrity": {"duplicate_ids": dup, "missing_ids": missing_ids, "unexpected_ids": unexpected_ids, "malformed_rows": malformed},
        "per_gate": gates_out,
        "overall": {"usable": counts["pass"], "not_usable": counts["fail"], "unknown": counts["unknown"],
                    "unknown_breakdown": {"record_absent": len(unknown_reason["record_absent"]),
                                          "present_but_unconfirmed": counts["unknown"] - len(unknown_reason["record_absent"])},
                    "not_usable_ids": overall["fail"], "unknown_ids": overall["unknown"],
                    "unknown_record_absent_ids": unknown_reason["record_absent"]},
        "unknown_reasons": {"record_absent": unknown_reason["record_absent"],
                            "field_absent": unknown_reason["field_absent"],
                            "value_missing_or_invalid": unknown_reason["value_missing_or_invalid"],
                            "note": "미확인 = 레코드 없음 / 필드 없음 / 값이 missing·이상값. 사용 불가 = 값이 fail·false·no류로 확정된 경우만. 파일 읽기·파싱 실패는 이 검토 자체가 실패(판정 보류)로 원장에 남는다."},
        "by_collection": by_coll,
        "issue_combinations": combos,
        "nonpass_records": per_record,
        "gate_met": counts["pass"] == total,
    }


def slice_budget(files):
    p = need(files, "project.json")
    t = need(files, "tasks.json")
    o = need(files, "options.json")
    return {"tasks.json#id,cost,optional": [{"id": x["id"], "cost": x.get("cost"), "optional": x.get("optional"), "stream": x.get("stream")} for x in t["items"]],
            "project.json#budget": p.get("budget"),
            "options.json#items,cost_note": {"items": o.get("items"), "cost_note": o.get("cost_note")},
            **({"conditions#budget,excluded_streams,excluded_options": {k: COND.get(k) for k in ("budget", "excluded_streams", "excluded_options")}} if COND else {})}


def run_budget(sl):
    all_tasks = sl["tasks.json#id,cost,optional"]
    c = sl.get("conditions#budget,excluded_streams,excluded_options") or {}
    budget_input = sl["project.json#budget"]
    budget = c.get("budget") or budget_input
    excl = [x for x in all_tasks if not in_scope(x["id"])]
    excl_req = [x["id"] for x in excl if not x["optional"]]
    if excl_req:  # 필수 작업은 범위에서 뺄 수 없다
        raise RuntimeError(f"제외 스트림에 필수 작업이 있음: {excl_req}")
    tasks = [x for x in all_tasks if in_scope(x["id"])]
    bad = [x["id"] for x in tasks if not isinstance(x["cost"], (int, float)) or isinstance(x["cost"], bool)]
    ok = [x for x in tasks if x["id"] not in bad]
    req = sum(x["cost"] for x in ok if not x["optional"])
    opt = sum(x["cost"] for x in ok if x["optional"])
    total = req + opt
    by_stream = {}
    for x in ok:
        s = by_stream.setdefault(x["stream"], {"cost": 0, "tasks": 0, "optional": x["optional"]})
        s["cost"] += x["cost"]
        s["tasks"] += 1
    opts = sl["options.json#items,cost_note"]
    shortfall = max(0, req - budget)
    scope = {"budget_input": budget_input, "budget_applied": budget,
             "budget_source": "conditions.json(사용자 T2 지시)" if c.get("budget") else "project.json",
             "excluded_streams": c.get("excluded_streams") or [], "excluded_tasks": [x["id"] for x in excl],
             "excluded_cost": sum(x["cost"] for x in excl if isinstance(x["cost"], (int, float))),
             "excluded_options": c.get("excluded_options") or [],
             "excluded_options_cost_effect": "없음 — options.cost는 tasks.cost에 이미 포함된 비교 정보라 제외해도 tasks 합계가 따로 줄지 않는다(options.cost_note)",
             "required_shortfall": shortfall,
             "within_budget_note": ("필수 작업만으로 예산 초과. 필수 작업을 취소하거나 검증 기준을 낮추는 방식으로 맞추지 않는다." if shortfall else "필수 작업 범위가 예산 이내."),
             "alternatives_need_approval": ([
                 {"id": "B-1", "option": f"부족분 {shortfall:,}원 추가 예산 승인(총 {req:,}원)", "effect": "범위·검증 기준 유지, 승인 즉시 해소"},
                 {"id": "B-2", "option": f"필수 작업 재견적·단가 협상으로 {shortfall:,}원 이상 절감", "effect": "범위·검증 기준 유지가 조건. 절감 확정 전까지 미충족"},
                 {"id": "B-3", "option": "B-2 재견적 후 남는 차액만 B-1로 추가 승인", "effect": "범위·검증 기준 유지"}] if shortfall else []),
             "not_proposed": "필수 작업(W1~W5) 취소·축소, 검증 기준 하향, 전량 검증을 표본 검증으로 대체 — 사용자 금지 조건"}
    return {
        "review": "budget",
        "scope_change": scope,
        "basis": "tasks.cost 합계가 정본. options.cost는 작업원가에 포함된 비교 정보이므로 합산하지 않음(options.cost_note)",
        "budget": budget,
        "tasks_counted": len(ok), "tasks_cost_invalid": bad,
        "required_cost": req, "optional_cost": opt, "total_cost": total,
        "surplus_total": budget - total, "surplus_required_only": budget - req,
        "within_budget_total": total <= budget, "within_budget_required_only": req <= budget,
        "shortfall_total": max(0, total - budget),
        "by_stream": by_stream,
        "options_reference_not_added": [{"id": o["id"], "name": o["name"], "cost": o["cost"]} for o in opts["items"]],
        "options_cost_sum_reference": sum(o["cost"] for o in opts["items"]),
        "cost_note": opts["cost_note"],
        "blocked": bool(bad),
    }


def slice_schedule(files):
    p = need(files, "project.json")
    return {"tasks.json": need(files, "tasks.json"), "receipts.json": need(files, "receipts.json"),
            "project.json#deadline,status_rule": {"deadline": p.get("deadline"), "status_rule": p.get("status_rule")},
            **({"conditions#excluded_streams,kept": {"excluded_streams": COND.get("excluded_streams"), "kept": COND.get("kept")}} if COND else {})}


def run_schedule(sl):
    all_tasks = sl["tasks.json"]["items"]
    excl_tasks = [t["id"] for t in all_tasks if not in_scope(t["id"])]
    tasks = [t for t in all_tasks if in_scope(t["id"])]
    all_rcpt = {r["task_id"]: r for r in sl["receipts.json"]["items"]}
    rcpt = {k: v for k, v in all_rcpt.items() if in_scope(k)}
    excl_rcpt = sorted(k for k in all_rcpt if not in_scope(k))
    T = {t["id"]: t for t in tasks}
    dup = [t["id"] for i, t in enumerate(tasks) if t["id"] in [u["id"] for u in tasks[:i]]]
    cross_scope = [{"task": t["id"], "excluded_dep": d} for t in tasks for d in t["depends"] if d in excl_tasks]
    dangling = [{"task": t["id"], "missing_dep": d} for t in tasks for d in t["depends"] if d not in T and d not in excl_tasks]
    orphan_receipts = [k for k in rcpt if k not in T]
    # 위상 정렬(Kahn) — 없는 선행은 그래프에서 제외하고 막힘 기록
    indeg = {k: 0 for k in T}
    succ = {k: [] for k in T}
    for t in tasks:
        for d in t["depends"]:
            if d in T:
                indeg[t["id"]] += 1
                succ[d].append(t["id"])
    order, q = [], [k for k in T if indeg[k] == 0]
    q.sort()
    deg = dict(indeg)
    while q:
        n = q.pop(0)
        order.append(n)
        for s in sorted(succ[n]):
            deg[s] -= 1
            if deg[s] == 0:
                q.append(s)
        q.sort()
    cyclic = sorted(k for k in T if k not in order)
    # CPM (순환 밖 노드)
    ES, EF = {}, {}
    for n in order:
        ES[n] = max([EF[d] for d in T[n]["depends"] if d in EF] or [0])
        EF[n] = ES[n] + T[n]["hours"]

    def cpm(nodes):
        nodes = [n for n in order if n in nodes]
        es, ef = {}, {}
        for n in nodes:
            es[n] = max([ef[d] for d in T[n]["depends"] if d in ef] or [0])
            ef[n] = es[n] + T[n]["hours"]
        proj = max(ef.values()) if ef else 0
        lf, ls = {}, {}
        for n in reversed(nodes):
            ss = [s for s in succ[n] if s in es]
            lf[n] = min([ls[s] for s in ss] or [proj])
            ls[n] = lf[n] - T[n]["hours"]
        slack = {n: ls[n] - es[n] for n in nodes}
        crit = [n for n in nodes if slack[n] == 0]
        # 임계 사슬 분해(시작 노드 별)
        chains = []
        for n in crit:
            if not [d for d in T[n]["depends"] if d in crit and EFd(ef, d) == es[n]]:
                ch, cur = [n], n
                while True:
                    nx = [s for s in succ[cur] if s in crit and es[s] == ef[cur]]
                    if not nx:
                        break
                    cur = sorted(nx)[0]
                    ch.append(cur)
                chains.append(ch)
        return proj, es, ef, slack, crit, chains

    def EFd(ef, d):
        return ef.get(d)

    all_ids = set(order)
    req_ids = {n for n in all_ids if not T[n]["optional"]}
    proj_all, es, ef, slack, crit_all, chains_all = cpm(all_ids)
    proj_req, es_r, ef_r, slack_r, crit_req, chains_req = cpm(req_ids)
    # 영수증 기준 상태
    status = {}
    for n in sorted(T):
        r = rcpt.get(n)
        if r and r.get("reported_done") is True and r.get("verified") is True:
            status[n] = "done"
    for n in sorted(T):
        if n in status:
            continue
        r = rcpt.get(n)
        deps = T[n]["depends"]
        deps_blocked = [d for d in deps if d not in T]
        deps_done = all(status.get(d) == "done" for d in deps if d in T) and not deps_blocked and n not in cyclic
        if r and r.get("reported_done") is True and r.get("verified") is not True:
            status[n] = "reported_unverified"  # 완료 아님: 검증 영수증 필요
        elif deps_done:
            status[n] = "ready"
        else:
            status[n] = "waiting"
    # 미완료 작업이 막는 후속 수(전이 폐포)
    def downstream(n):
        seen, st = set(), [n]
        while st:
            c = st.pop()
            for s in succ[c]:
                if s not in seen:
                    seen.add(s); st.append(s)
        return seen
    blockers = []
    for n in sorted(T):
        if status[n] in ("ready", "reported_unverified"):
            ds = downstream(n)
            blockers.append({"task": n, "status": status[n], "optional": T[n]["optional"], "blocks_count": len(ds),
                             "blocks_hours": sum(T[d]["hours"] for d in ds) + T[n]["hours"],
                             "on_critical_path": slack.get(n) == 0})
    blockers.sort(key=lambda b: (-b["blocks_hours"], b["task"]))
    remaining = {n for n in T if status[n] != "done"}
    rem_req = {n for n in remaining if not T[n]["optional"]}
    # 남은 작업의 최장 경로(완료 작업 0h)
    def remaining_longest(nodes):
        es2, ef2 = {}, {}
        for n in order:
            if n not in nodes:
                continue
            es2[n] = max([ef2[d] for d in T[n]["depends"] if d in ef2] or [0])
            ef2[n] = es2[n] + T[n]["hours"]
        return max(ef2.values()) if ef2 else 0
    fan_in = sorted(({"task": n, "depends_count": len(T[n]["depends"])} for n in T), key=lambda x: (-x["depends_count"], x["task"]))[:5]
    by_stream = {}
    for n in sorted(T):
        s = by_stream.setdefault(T[n]["stream"], {"tasks": 0, "hours": 0, "done": 0, "optional": T[n]["optional"], "first": n})
        s["tasks"] += 1; s["hours"] += T[n]["hours"]; s["done"] += status[n] == "done"
    return {
        "review": "schedule",
        "scope_change": {"excluded_streams": (sl.get("conditions#excluded_streams,kept") or {}).get("excluded_streams") or [],
                         "excluded_tasks": excl_tasks, "excluded_receipts_not_counted": excl_rcpt,
                         "in_scope_depends_on_excluded": cross_scope,
                         "note": "제외 스트림 작업은 그래프·상태·임계경로 계산에서 뺐다. 범위 안 작업이 제외 작업에 의존하면 위 목록에 남긴다(빈 목록=의존 없음)."},
        "rules": {"done": "receipts의 reported_done과 verified가 모두 true일 때만 (project.status_rule)",
                  "ready": "선행 작업이 모두 done이고 자신은 미완료",
                  "reported_unverified": "완료 보고만 있고 검증 영수증 없음 → 미완료, 재검증 필요",
                  "waiting": "선행 작업 미완료 → 실행 가능으로 표시하지 않음",
                  "tasks.status": "모든 작업이 'planned'로 기재되어 있어 진행 판정에 쓰지 않고 영수증을 따름"},
        "integrity": {"task_count": len(T), "duplicate_ids": dup, "dangling_depends": dangling, "cycle_nodes": cyclic,
                      "receipts_for_unknown_tasks": orphan_receipts},
        "topological_order": order,
        "cpm_all": {"project_hours": proj_all, "critical_tasks": crit_all, "critical_chains": chains_all,
                    "slack": slack, "note": f"범위 안 {len({T[n]['stream'] for n in T})}개 스트림이 독립 12단계 사슬이며 길이가 같아 동률 임계경로가 여러 개"},
        "cpm_required": {"project_hours": proj_req, "critical_chains": chains_req},
        "status_counts": {k: sum(1 for v in status.values() if v == k) for k in ("done", "reported_unverified", "ready", "waiting")},
        "status": status,
        "done": sorted(n for n in T if status[n] == "done"),
        "reported_unverified": sorted(n for n in T if status[n] == "reported_unverified"),
        "ready": sorted(n for n in T if status[n] == "ready"),
        "waiting_count": sum(1 for v in status.values() if v == "waiting"),
        "bottlenecks": blockers,
        "fan_in_top": fan_in,
        "remaining": {"tasks_all": len(remaining), "tasks_required": len(rem_req),
                      "hours_sum_all": sum(T[n]["hours"] for n in remaining),
                      "hours_sum_required": sum(T[n]["hours"] for n in rem_req),
                      "longest_path_hours_all": remaining_longest(remaining),
                      "longest_path_hours_required": remaining_longest(rem_req)},
        "by_stream": by_stream,
        "deadline": {"date": sl["project.json#deadline,status_rule"]["deadline"], "verdict": "미확정",
                     "kept_by_user": bool(sl.get("conditions#excluded_streams,kept")),
                     "reason": "hours는 순수 작업시간이며 달력·인력 가용시간이 주어지지 않음(T2 조건 변경에도 달력·인력 정보는 새로 주어지지 않음). W6는 필수 사슬과 선행관계가 없어 제외해도 필수 최장 경로가 줄지 않는다",
                     "needed": ["담당자별 주당 가용시간·휴무일", "스트림 간 병렬 투입 가능 인원", "W4-02 재검증 소요 시간",
                                "작업 착수 가능일(기준일)", "검증 영수증 발급 소요 시간", "개통 전 리허설·인수 일정"]},
        "blocked": bool(dangling or cyclic or dup or cross_scope),
    }


def slice_operations(files):
    p = need(files, "project.json")
    o = need(files, "options.json")
    t = need(files, "tasks.json")
    return {"project.json#publication,acceptance,status_rule,gates": {k: p.get(k) for k in ("publication", "acceptance", "status_rule", "gates")},
            "options.json#items": o.get("items"),
            "tasks.json#id,stream,optional,status": [{k: x.get(k) for k in ("id", "stream", "optional", "status")} for x in t["items"]],
            **({"conditions#excluded_options,excluded_streams,kept": {k: COND.get(k) for k in ("excluded_options", "excluded_streams", "kept")}} if COND else {})}


def run_operations(sl):
    p = sl["project.json#publication,acceptance,status_rule,gates"]
    opts = sl["options.json#items"]
    tk = sl["tasks.json#id,stream,optional,status"]
    cc = sl.get("conditions#excluded_options,excluded_streams,kept") or {}
    xo = set(cc.get("excluded_options") or [])
    xs = cc.get("excluded_streams") or []
    conds = []
    conds.append({"id": "OP-1", "condition": "공개 범위 publication=draft_only",
                  "verdict": "충족(검토 단계)" if p["publication"] == "draft_only" else "미확인",
                  "evidence": f"project.publication={p['publication']!r}",
                  "implication": "이번 산출물은 초안이며 공개·발송·배포를 하지 않음. 정식 공개 승인 절차는 입력에 없음 → 개통 시 공개 승인 근거 미확인"})
    conds.append({"id": "OP-2", "condition": "상태 규칙(status_rule) 적용",
                  "verdict": "적용함", "evidence": p["status_rule"],
                  "implication": "tasks.status(전부 planned)는 진행 근거로 쓰지 않고 receipts로 판정"})
    ext = [o for o in opts if o.get("external_saas")]
    face = [o for o in opts if o.get("face")]
    if ext and all(o["id"] in xo for o in ext):
        conds.append({"id": "OP-3", "condition": "외부 SaaS 사용 여부(O2 상용 외부 검색)",
                      "verdict": "충족(범위 제외)",
                      "evidence": {"excluded_by_user": sorted(o["id"] for o in ext), "source": "conditions.json excluded_options"},
                      "implication": "외부 SaaS를 쓰지 않으므로 외부 위탁 정책 확인이 이번 범위에서 필요 없다. 개인정보(동의 확인) 조건은 자료 게이트에서 그대로 유지"})
    else:
      conds.append({"id": "OP-3", "condition": "외부 SaaS 사용 여부(O2 상용 외부 검색)",
                  "verdict": "미확인",
                  "evidence": [{"id": o["id"], "name": o["name"], "external_saas": True} for o in ext],
                  "implication": "외부 SaaS 허용·개인정보 위탁 정책이 입력에 없음. 어느 검색안을 택했는지도 입력에 없음 → 선택안 확정과 정책 확인 필요"})
    if face and all(o["id"] in xo for o in face):
        conds.append({"id": "OP-4", "condition": "얼굴 처리 기능 여부(O3 얼굴 자동 분류)",
                      "verdict": "충족(범위 제외)",
                      "evidence": {"excluded_by_user": sorted(o["id"] for o in face), "source": "conditions.json excluded_options"},
                      "implication": "얼굴 자동 분류를 하지 않으므로 생체정보 처리 근거 확인이 이번 범위에서 필요 없다"})
    else:
      conds.append({"id": "OP-4", "condition": "얼굴 처리 기능 여부(O3 얼굴 자동 분류)",
                  "verdict": "미확인",
                  "evidence": [{"id": o["id"], "name": o["name"], "face": True} for o in face],
                  "implication": "생체정보(얼굴) 처리 허용 근거·동의 범위가 입력에 없음. 선택기능 스트림(W6)과 O3의 대응도 입력에 명시 없음"})
    sel = [x for x in tk if x["optional"]]
    sel_out = [x["id"] for x in sel if not in_scope(x["id"])]
    req_out = [x["id"] for x in tk if not x["optional"] and not in_scope(x["id"])]
    conds.append({"id": "OP-5", "condition": "선택 작업(optional) 분리" + (" 및 W6 범위 제외" if xs else ""),
                  "verdict": ("미충족(필수 작업이 제외됨)" if req_out else "충족(범위 제외)") if xs else "확인됨",
                  "evidence": {"optional_tasks": [x["id"] for x in sel], "streams": sorted({x["stream"] for x in sel}),
                               "excluded_by_user": sel_out, "required_tasks_excluded": req_out},
                  "implication": ("선택기능(W6) 12개 전부 선택 작업이며 사용자 지시로 이번 범위에서 제외. 필수 작업 제외 0건" if xs and not req_out
                                  else "선택기능(W6) 12개는 개통 필수 판정에서 제외. 채택 여부는 입력에 없음")})
    conds.append({"id": "OP-6", "condition": "인수 기준(acceptance): 1800건 전량 네 조건 충족 + 필수 작업 증거 완료",
                  "verdict": "합류 단계에서 판정", "evidence": p["acceptance"],
                  "implication": "자료 게이트·일정 검토 결과가 필요 → merge 단계에서 판정"})
    left = [o for o in opts if o["id"] not in xo and not o.get("face")]
    if xo and len(left) == 1:
        conds.append({"id": "OP-7", "condition": "선택안(검색 방식) 결정",
                      "verdict": f"미확인({left[0]['id']}가 남은 유일안 — 채택 기록 필요)",
                      "evidence": {"remaining": [o["id"] for o in left], "excluded_by_user": sorted(xo)},
                      "implication": f"O2·O3 제외로 입력의 검색 선택안은 {left[0]['id']}({left[0]['name']})만 남는다. 사용자가 {left[0]['id']} 채택을 명시하지는 않았으므로 채택 결정을 기록해야 확정. 비용은 tasks.cost에 이미 포함되어 따로 더하지 않음"})
    else:
        conds.append({"id": "OP-7", "condition": "선택안(검색 방식) 결정",
                  "verdict": "미확인", "evidence": [o["id"] for o in opts],
                  "implication": "O1(내부)·O2(외부) 중 채택안이 입력에 없음"})
    if cc.get("kept"):
        conds.append({"id": "OP-8", "condition": "유지 조건(개인정보·접근성·전량 검증·기한)",
                      "verdict": "적용함(유지)", "evidence": cc["kept"],
                      "implication": "자료 네 조건과 1800건 전량 인수 기준은 T1과 같다. 기준 하향 없음"})
    return {"review": "operations",
            "basis": "입력에 명시된 조건만 판정(project.gates·acceptance·status_rule·publication, options.external_saas·face, tasks.optional·status). 입력에 없는 정책은 미확인",
            "conditions": conds,
            "counts": {v: sum(1 for c in conds if c["verdict"].startswith(v)) for v in ("충족", "미충족", "미확인", "적용함", "확인됨", "합류")},
            "blocked": False}


REVIEWS = {
    "data_gates": (slice_data_gates, run_data_gates),
    "budget": (slice_budget, run_budget),
    "schedule": (slice_schedule, run_schedule),
    "operations": (slice_operations, run_operations),
}


# ---------------------------------------------------------------- 실행
def run_one(name, files, out, prev_ledger, prev_dir):
    ent = {"review": name, "thread": None, "depends_on_reviews": [], "parallel_group": "independent_reviews"}
    ent["started_at"] = now()
    ent["thread"] = threading.current_thread().name
    t0 = time.perf_counter()
    try:
        sl_fn, run_fn = REVIEWS[name]
        sl = sl_fn(files)
        ent["input_fingerprints"] = {k: canon(v) for k, v in sl.items()}
        ent["input_files"] = sorted({k.split("#")[0] for k in sl if k.split("#")[0] in files})
        ent["input_file_sha256"] = {f: files[f]["sha256"] for f in ent["input_files"]}
        if any(k.startswith("conditions#") for k in sl):
            ent["conditions_used"] = sorted(k for k in sl if k.startswith("conditions#"))
        outp = os.path.join(out, "reviews", f"{name}.json")
        prev = (prev_ledger or {}).get("reviews", {}).get(name)
        if prev and prev.get("status") in ("ok", "reused") and prev.get("input_fingerprints") == ent["input_fingerprints"]:
            src = os.path.join(prev_dir, "reviews", f"{name}.json")
            if sha_file(src) == prev.get("output_sha256"):
                shutil.copyfile(src, outp)
                ent["status"] = "reused"
                ent["reused_from"] = {"path": src, "sha256": prev["output_sha256"], "reason": "입력 조각 지문 동일"}
        if ent.get("status") != "reused":
            res = run_fn(sl)
            with open(outp, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
            ent["status"] = "ok" if not res.get("blocked") else "ok_with_blocked_parts"
        ent["output"] = outp
        ent["output_sha256"] = sha_file(outp)
    except Exception as e:
        ent["status"] = "failed"
        ent["error"] = f"{type(e).__name__}: {e}"
        ent["traceback"] = traceback.format_exc()
    ent["ended_at"] = now()
    ent["duration_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    return name, ent


def data_diff(prev_path, cur):
    """직전 턴 data_gates 결과와 ID 단위로 비교."""
    try:
        pv = json.load(open(prev_path, encoding="utf-8"))
    except Exception as e:
        return {"status": "prev_unreadable", "error": f"{type(e).__name__}: {e}"}

    def verdicts(d):
        m = {}
        for v, key in (("fail", "not_usable_ids"), ("unknown", "unknown_ids")):
            for i in d["overall"][key]:
                m[i] = v
        return m

    pm, cm = verdicts(pv), verdicts(cur)
    ids = [f"D{i:04d}" for i in range(1, cur["expected_records"] + 1)]
    changed = []
    for i in ids:
        a, b = pm.get(i, "pass"), cm.get(i, "pass")
        if a != b:
            changed.append({"id": i, "prev": a, "now": b})
    gate_changes = {}
    for f in cur["per_gate"]:
        pg, cg = pv["per_gate"][f], cur["per_gate"][f]
        gate_changes[f] = {"label": cg["label"],
                           "fail": {"prev": pg["fail"], "now": cg["fail"],
                                    "left": sorted(set(pg["fail_ids"]) - set(cg["fail_ids"])),
                                    "new": sorted(set(cg["fail_ids"]) - set(pg["fail_ids"]))},
                           "unknown": {"prev": pg["unknown"], "now": cg["unknown"],
                                       "left": sorted(set(pg["unknown_ids"]) - set(cg["unknown_ids"])),
                                       "new": sorted(set(cg["unknown_ids"]) - set(pg["unknown_ids"]))}}
    po, co = pv["overall"], cur["overall"]
    return {"status": "ok", "prev_output": prev_path, "prev_records_version": pv.get("records_version"),
            "now_records_version": cur.get("records_version"),
            "rows_in_file": {"prev": pv.get("rows_in_file"), "now": cur.get("rows_in_file")},
            "missing_ids": {"prev": pv["integrity"]["missing_ids"], "now": cur["integrity"]["missing_ids"]},
            "overall": {k: {"prev": po[k], "now": co[k], "delta": co[k] - po[k]} for k in ("usable", "not_usable", "unknown")},
            "verdict_changed_ids": changed,
            "verdict_change_counts": {f"{a}->{b}": sum(1 for c in changed if c["prev"] == a and c["now"] == b)
                                      for a in ("pass", "fail", "unknown") for b in ("pass", "fail", "unknown") if a != b},
            "per_gate": gate_changes}


def merge(out, ledger, files):
    R = {}
    for n, e in ledger["reviews"].items():
        if e["status"] in ("ok", "ok_with_blocked_parts", "reused"):
            R[n] = json.load(open(e["output"], encoding="utf-8"))
    blocked = [n for n, e in ledger["reviews"].items() if e["status"] == "failed"]
    dg, bu, sc, op = R.get("data_gates"), R.get("budget"), R.get("schedule"), R.get("operations")
    findings, actions = [], []
    # 자료
    if dg:
        o = dg["overall"]
        g = dg["per_gate"]
        absent = o.get("unknown_record_absent_ids", [])
        if absent:
            actions.append({"priority": 1, "area": "자료", "action": "누락 레코드 재수령·네 조건 검증(현재 판본에 행 없음 → 미확인)",
                            "target_count": len(absent), "targets": absent,
                            "evidence": "reviews/data_gates.json#unknown_reasons.record_absent"})
        cu = g["consent"].get("unknown_value_ids", [i for i in g["consent"]["unknown_ids"] if i not in absent])
        actions.append({"priority": 1, "area": "자료", "action": "동의 기록 누락(consent=missing) 자료의 동의 확인·회수",
                        "target_count": len(cu), "evidence": "reviews/data_gates.json#per_gate.consent.unknown_value_ids",
                        "ids_sample": cu[:10]})
        actions.append({"priority": 1, "area": "자료", "action": "체크섬 불일치 자료 재이관·재검증",
                        "target_count": g["checksum"]["fail"], "evidence": "reviews/data_gates.json#per_gate.checksum.fail_ids",
                        "ids_sample": g["checksum"]["fail_ids"][:10]})
        actions.append({"priority": 2, "area": "자료", "action": "검색 불가 자료 색인 보완",
                        "target_count": g["searchable"]["fail"], "evidence": "reviews/data_gates.json#per_gate.searchable.fail_ids",
                        "ids_sample": g["searchable"]["fail_ids"][:10]})
        actions.append({"priority": 2, "area": "자료", "action": "접근성 미통과 자료 보정(대체텍스트 등)·재검사",
                        "target_count": g["accessible"]["fail"], "evidence": "reviews/data_gates.json#per_gate.accessible.fail_ids",
                        "ids_sample": g["accessible"]["fail_ids"][:10]})
    # 일정
    if sc:
        for u in sc["reported_unverified"]:
            b = next((x for x in sc["bottlenecks"] if x["task"] == u), {})
            actions.insert(0, {"priority": 1, "area": "작업", "action": f"{u} 검증 영수증 확보(완료 보고만 있고 verified=false)",
                               "target_count": 1, "evidence": f"inputs/receipts.json task_id={u}; reviews/schedule.json#bottlenecks",
                               "blocks_tasks": b.get("blocks_count"), "blocks_hours": b.get("blocks_hours")})
        req_ready = [x for x in sc["ready"] if not x.startswith("W6")]
        actions.append({"priority": 2, "area": "작업", "action": "선행이 완료되어 착수 가능한 필수 작업 착수",
                        "targets": req_ready, "evidence": "reviews/schedule.json#ready"})
        actions.append({"priority": 3, "area": "일정", "action": "기한 판정용 달력·인력 정보 수집",
                        "targets": sc["deadline"]["needed"], "evidence": "reviews/schedule.json#deadline"})
    if bu and bu.get("scope_change", {}).get("required_shortfall"):
        sh = bu["scope_change"]["required_shortfall"]
        actions.append({"priority": 1, "area": "예산", "action": f"필수 작업비 부족 {sh:,}원 해소안 결정(추가 예산 또는 범위·기준 유지 재견적) — 사용자 승인 필요",
                        "targets": [a_["id"] + " " + a_["option"] for a_ in bu["scope_change"]["alternatives_need_approval"]],
                        "evidence": "reviews/budget.json#scope_change"})
    if op:
        oc = {c["id"]: c for c in op["conditions"]}
        if oc.get("OP-3", {}).get("verdict") == "미확인":
            actions.append({"priority": 2, "area": "운영", "action": "검색 선택안(O1 내부/O2 외부 SaaS) 확정과 외부 SaaS 허용 정책 확인",
                            "evidence": "reviews/operations.json#OP-3,OP-7"})
        elif oc.get("OP-7", {}).get("verdict", "").startswith("미확인"):
            actions.append({"priority": 2, "area": "운영", "action": "검색 방식 O1(내부 서버 기본 검색) 채택 결정 기록",
                            "evidence": "reviews/operations.json#OP-7"})
        if oc.get("OP-4", {}).get("verdict") == "미확인":
            actions.append({"priority": 3, "area": "운영", "action": "얼굴 자동 분류(O3)·선택기능(W6) 채택 여부와 생체정보 처리 근거 확인",
                            "evidence": "reviews/operations.json#OP-4,OP-5"})
    for n in blocked:
        actions.insert(0, {"priority": 0, "area": "검토 실패", "action": f"{n} 검토 재수행(입력·실행 오류 해소)",
                           "evidence": ledger["reviews"][n].get("error")})
    prev_ref = None
    if "data_gates" in blocked and ledger.get("prev"):
        pp = os.path.join(ledger["prev"], "reviews", "data_gates.json")
        if os.path.exists(pp):
            prev_ref = {"path": pp, "sha256": sha_file(pp),
                        "note": "직전 턴의 자료 검토 결과(이전 판본). 현재 판본 판정이 아니므로 판정에 쓰지 않고 참고로만 둔다."}
    actions.sort(key=lambda a: a["priority"])
    for i, a in enumerate(actions, 1):
        a["rank"] = i
    # 인수 판정
    data_ok = dg["gate_met"] if dg else None
    req_done = None
    req_ids, req_done_n = [], None
    if sc:
        # optional 판정은 tasks에서
        tk = {t["id"]: t for t in files["tasks.json"]["data"]["items"]} if files["tasks.json"]["status"] == "ok" else {}
        req_ids = [k for k in sc["status"] if tk and not tk[k]["optional"] and in_scope(k)]
        req_done_n = sum(1 for k in req_ids if sc["status"][k] == "done")
        req_done = req_done_n == len(req_ids)
    budget_ok = bu["within_budget_total"] if bu else None
    budget_req_ok = bu["within_budget_required_only"] if bu else None
    acceptance = {
        "data_all_four_gates": {"met": data_ok, "detail": dg and {"usable": dg["overall"]["usable"], "not_usable": dg["overall"]["not_usable"], "unknown": dg["overall"]["unknown"], "expected": dg["expected_records"]}},
        "required_tasks_done_with_receipts": {"met": req_done, "detail": sc and {"required": len(req_ids), "done": req_done_n}},
        "budget": {"met": budget_ok, "required_only_met": budget_req_ok,
                   "detail": bu and {"total_cost": bu["total_cost"], "required_cost": bu["required_cost"], "budget": bu["budget"],
                                     "surplus": bu["surplus_total"], "shortfall": bu.get("shortfall_total", 0),
                                     "excluded_streams": bu.get("scope_change", {}).get("excluded_streams", [])}},
        "operations_open_items": [c["id"] for c in op["conditions"] if c["verdict"].startswith("미확인")] if op else None,
    }
    if blocked:
        verdict = "보류(검토 일부 실패)"
    elif data_ok and req_done and budget_ok is False:
        verdict = "개통 불가(현시점) — 예산 미충족"
    elif data_ok and req_done:
        verdict = "개통 가능(인수 기준 충족) — 운영 미확인 항목 확인 필요"
    else:
        verdict = "개통 불가(현시점)"
    reasons = []
    if "data_gates" in blocked:
        reasons.append("자료 검토 실패 — 자료 판정 보류(미확인)")
    if data_ok is False:
        reasons.append("자료 1800건 전량 네 조건 미충족")
    if req_done is False:
        reasons.append(f"필수 작업 증거 완료 {req_done_n}/{len(req_ids)}")
    if budget_ok is False:
        reasons.append(f"예산 {bu.get('shortfall_total', 0):,}원 부족")
    blockers = []
    if dg and data_ok is False:
        o_ = dg["overall"]
        blockers.append({"id": "B-DATA", "area": "자료", "status": "미충족",
                         "detail": f"1800건 중 사용 가능 {o_['usable']}, 사용 불가 {o_['not_usable']}, 미확인 {o_['unknown']}",
                         "evidence": "reviews/data_gates.json#overall"})
    if sc and req_done is False:
        blockers.append({"id": "B-TASKS", "area": "필수 작업", "status": "미완료",
                         "detail": f"필수 {len(req_ids)}개 중 reported_done·verified 모두 참 {req_done_n}개; 완료 보고만 있고 검증 없음: {', '.join(sc['reported_unverified']) or '없음'}",
                         "evidence": "reviews/schedule.json#status,bottlenecks; inputs/receipts.json"})
    if bu and budget_ok is False:
        blockers.append({"id": "B-BUDGET", "area": "예산", "status": "부족",
                         "detail": f"필수 작업비 {bu['required_cost']:,}원 / 예산 {bu['budget']:,}원 → {bu.get('shortfall_total', 0):,}원 부족. 해소안은 제안일 뿐 미승인",
                         "evidence": "reviews/budget.json#scope_change"})
    dl = sc["deadline"] if sc else {"verdict": "미확정"}
    if dl.get("verdict") != "충족":
        blockers.append({"id": "B-DEADLINE", "area": "기한", "status": dl.get("verdict", "미확정"),
                         "detail": "2026-11-20 준수 여부는 달력·인력 정보가 없어 확정 불가(미준수 판정이 아님)",
                         "evidence": "reviews/schedule.json#deadline"})
    if op:
        for c in op["conditions"]:
            if c["verdict"].startswith("미확인"):
                blockers.append({"id": f"B-{c['id']}", "area": "운영", "status": c["verdict"],
                                 "detail": c.get("name") or c.get("condition") or c.get("item") or c["id"],
                                 "evidence": f"reviews/operations.json#{c['id']}"})
    for n in blocked:
        blockers.append({"id": f"B-REVIEW-{n}", "area": "검토 실패", "status": "판정 보류", "detail": str(ledger["reviews"][n].get("error")), "evidence": "run_ledger.json#reviews"})
    review_work = {
        "completed": not blocked,
        "status": "완료" if not blocked else "일부 실패(판정 보류)",
        "meaning": "네 검토(자료·예산·일정·운영)와 합류가 현재 입력 판본과 조건으로 끝났는지에 대한 판정이다. 개통 가능 여부와 별개다.",
        "reviews": {n: e["status"] for n, e in ledger["reviews"].items()},
        "merge_after_all_reviews": ledger.get("parallel_evidence", {}).get("merge_after_all_reviews"),
    }
    launch_readiness = {
        "launchable_now": (False if blockers else (None if blocked else True)),
        "status": ("개통 불가(현시점)" if blockers else "개통 가능(인수 기준 충족)"),
        "meaning": "인수 기준(자료 네 조건 전량·필수 작업 증거 완료·예산·기한·운영 조건) 충족 여부다. 실제 개통은 수행하지 않았으며 개통 완료가 아니다.",
        "remaining_blockers": blockers,
        "criteria_kept": "필수 작업 취소·검증 기준 하향 없음(T2 조건 그대로)",
    }
    review = {
        "review_work": review_work,
        "launch_readiness": launch_readiness,
        "verdict_reasons": reasons,
        "project": files["project.json"]["data"].get("project") if files["project.json"]["status"] == "ok" else None,
        "turn": os.path.basename(out.rstrip("/")),
        "generated_at": now(),
        "verdict": verdict,
        "verdict_scope": "검토 완료는 실제 개통 완료가 아니다. 이 판정은 입력 판본 기준의 준비 상태 판정이며, 공개·배포·운영 변경은 하지 않았다(publication=draft_only).",
        "acceptance_check": acceptance,
        "deadline": sc["deadline"] if sc else {"verdict": "미확정", "reason": "schedule 검토 실패"},
        "priority_actions": actions,
        "blocked_reviews": blocked,
        "data_gates_prev_reference": prev_ref,
        "data_diff_vs_prev": ledger.get("data_diff_vs_prev"),
        "review_outputs": {n: {"path": e.get("output"), "sha256": e.get("output_sha256"), "status": e["status"]} for n, e in ledger["reviews"].items()},
        "conditions": COND or None,
        "change_impact": ledger.get("change_impact"),
        "summaries": {
            "data_gates": dg and {k: dg.get(k) for k in ("records_version", "expected_records", "rows_in_file", "integrity", "overall", "by_collection", "issue_combinations")} | {"unknown_reasons_counts": {"record_absent": len(dg["unknown_reasons"]["record_absent"]), "field_absent": {f: len(v) for f, v in dg["unknown_reasons"]["field_absent"].items()}, "value_missing_or_invalid": {f: len(v) for f, v in dg["unknown_reasons"]["value_missing_or_invalid"].items()}}, "per_gate_counts": {f: {k: v.get(k) for k in ("label", "pass", "fail", "unknown", "unknown_record_absent", "unknown_field_absent", "unknown_value")} for f, v in dg["per_gate"].items()}},
            "budget": bu and {k: bu.get(k) for k in ("basis", "budget", "required_cost", "optional_cost", "total_cost", "surplus_total", "surplus_required_only", "shortfall_total", "within_budget_total", "within_budget_required_only", "scope_change", "options_reference_not_added", "options_cost_sum_reference")},
            "schedule": sc and {k: sc.get(k) for k in ("scope_change", "integrity", "status_counts", "done", "reported_unverified", "ready", "bottlenecks", "remaining")} | {"cpm_all": {k: sc["cpm_all"][k] for k in ("project_hours", "critical_chains", "note")}, "cpm_required": sc["cpm_required"]},
            "operations": op and op["conditions"],
        },
    }
    return review


def md_report(rv, ledger):
    s = rv["summaries"]; L = []
    a = L.append
    a(f"# 인수 검토서 — {rv['project']} ({rv['turn']})\n")
    a(f"- 생성: {rv['generated_at']} (UTC)\n- **판정: {rv['verdict']}**" + (f" — 사유: {'; '.join(rv['verdict_reasons'])}" if rv.get("verdict_reasons") else "") + f"\n- 범위: {rv['verdict_scope']}\n")
    rw, lr = rv.get("review_work"), rv.get("launch_readiness")
    if rw and lr:
        a("## 검토 작업 완료와 개통 가능 여부(별도 판정)\n")
        a("| 구분 | 판정 | 의미 |\n|---|---|---|")
        a(f"| 검토 작업 | **{rw['status']}** | {rw['meaning']} |")
        a(f"| 개통 가능 여부 | **{lr['status']}** | {lr['meaning']} |\n")
        if lr["remaining_blockers"]:
            a("남은 차단 요인:\n")
            a("| ID | 영역 | 상태 | 내용 | 근거 |\n|---|---|---|---|---|")
            for b_ in lr["remaining_blockers"]:
                a(f"| {b_['id']} | {b_['area']} | {b_['status']} | {b_['detail']} | `{b_['evidence']}` |")
            a("")
        a(f"- {lr['criteria_kept']}\n")
    ci = rv.get("change_impact")
    if ci:
        a("## 0. 이번 턴의 조건 변경과 영향 분석\n")
        a("| 변경 | 이전 | 이번 |\n|---|---|---|")
        for ch in ci["changes"]:
            a(f"| {ch['item']} | {ch['before']} | {ch['after']} |")
        a("\n| 검토 | 처리 | 근거 |\n|---|---|---|")
        for n, x in ci["reviews"].items():
            a(f"| {n} | {x['decision']} | {x['reason']} |")
        a(f"| merge(합류·조치·검토서) | {ci['merge']} | 검토 결과 해시 변화에 따름 |")
        a(f"\n- 입력 판본 대조: {ci['input_version_check']}.")
        for n, x in ci["reviews"].items():
            if x.get("reused_from"):
                a(f"- {n}: `{x['reused_from']['path']}`를 복사했고 sha256 `{x['reused_from']['sha256'][:12]}…`가 같다.")
        a("")
    dd = rv.get("data_diff_vs_prev")
    if dd and dd.get("status") == "ok":
        a("### 직전 턴 대비 자료 판정 차이\n")
        a(f"- records.json 판본 {dd['prev_records_version']} → {dd['now_records_version']}, 파일 행 {dd['rows_in_file']['prev']} → {dd['rows_in_file']['now']}, 누락 ID {dd['missing_ids']['prev'] or '없음'} → {', '.join(dd['missing_ids']['now']) or '없음'}.")
        for c in dd["verdict_changed_ids"]:
            if c["prev"] == "fail" and c["now"] == "unknown" and c["id"] in dd["missing_ids"]["now"]:
                a(f"- {c['id']}: 이전 판본에서는 검사값이 실패(사용 불가)였으나 새 판본에는 행이 없다. 결함이 고쳐졌다는 증거가 아니므로 통과로 보지 않고 **미확인**으로 옮겼다(재수령·재검증 필요).")
        a("")
        a("| 구분 | 이전 | 이번 | 증감 |\n|---|---:|---:|---:|")
        for k, lab in (("usable", "사용 가능"), ("not_usable", "사용 불가"), ("unknown", "미확인")):
            x = dd["overall"][k]
            a(f"| {lab} | {x['prev']} | {x['now']} | {x['delta']:+d} |")
        a("\n| 조건 | 미충족 이전→이번 | 미충족에서 빠진 ID | 미확인 이전→이번 | 미확인에서 빠진 ID | 미확인에 새로 든 ID |\n|---|---|---|---|---|---|")
        for f, x in dd["per_gate"].items():
            a(f"| {x['label']} | {x['fail']['prev']}→{x['fail']['now']} | {', '.join(x['fail']['left']) or '—'} | {x['unknown']['prev']}→{x['unknown']['now']} | {', '.join(x['unknown']['left']) or '—'} | {', '.join(x['unknown']['new']) or '—'} |")
        a("\n- 전체 판정이 바뀐 ID: " + ("; ".join(f"{c['id']} {c['prev']}→{c['now']}" for c in dd["verdict_changed_ids"]) or "없음") + "\n")
    if rv.get("data_gates_prev_reference"):
        pr = rv["data_gates_prev_reference"]
        a(f"- ⚠ 자료 검토 실패로 현재 판본 자료 판정은 보류했다. 직전 결과 `{pr['path']}`(sha256 {pr['sha256'][:12]}…)는 이전 판본이라 판정에 쓰지 않았다.\n")
    if rv["blocked_reviews"]:
        a(f"- ⚠ 실패한 검토: {', '.join(rv['blocked_reviews'])} — 확인된 다른 결과는 보존함\n")
    ac = rv["acceptance_check"]
    a("## 1. 인수 기준 대조\n")
    a("| 기준 | 판정 | 근거 |\n|---|---|---|")
    d = ac["data_all_four_gates"]["detail"] or {}
    dm = ac['data_all_four_gates']['met']
    a(f"| 1800건 전량 네 조건 충족 | {'충족' if dm else '판정 보류(자료 검토 실패)' if dm is None else '미충족'} | " + (f"사용 가능 {d.get('usable')} / 불가 {d.get('not_usable')} / 미확인 {d.get('unknown')} (기대 {d.get('expected')})" if d else "현재 판본 자료 검토 결과 없음") + " |")
    t = ac["required_tasks_done_with_receipts"]["detail"] or {}
    a(f"| 필수 작업 증거 완료 | {'충족' if ac['required_tasks_done_with_receipts']['met'] else '미충족'} | 필수 {t.get('required')}개 중 영수증 완료 {t.get('done')}개 |")
    b = ac["budget"]["detail"] or {}
    if b.get("shortfall"):
        a(f"| 예산 | **미충족** | 범위 내 tasks.cost 합(필수만) {b.get('total_cost'):,}원 / 예산 {b.get('budget'):,}원 → **{b.get('shortfall'):,}원 부족** |")
    else:
        a(f"| 예산 | 충족 | tasks.cost 합 {b.get('total_cost'):,}원 / 예산 {b.get('budget'):,}원, 잔액 {b.get('surplus'):,}원 |")
    a(f"| 운영 미확인 | — | {', '.join(ac['operations_open_items'] or [])} |\n")
    ci = rv.get("change_impact")
    if s["data_gates"]:
        g = s["data_gates"]
        a("## 2. 자료 사용 가능 여부 (D0001~D1800)" + (" — 직전 결과 재사용" if ci and ci["reviews"]["data_gates"]["decision"].startswith("재사용") else " — 현재 판본으로 재수행") + "\n")
        a(f"records.json version {g.get('records_version')}.")
        a(f"파일 행 {g['rows_in_file']} / 기대 {g['expected_records']}, 중복 ID {len(g['integrity']['duplicate_ids'])}, 누락 ID {len(g['integrity']['missing_ids'])}, 형식 오류 행 {len(g['integrity']['malformed_rows'])}.\n")
        a("| 조건 | 충족 | 미충족(실패) | 미확인 계 | └ 레코드 없음 | └ 필드 없음 | └ 값 missing·이상 |\n|---|---:|---:|---:|---:|---:|---:|")
        for f, v in g["per_gate_counts"].items():
            a(f"| {v['label']} ({f}) | {v['pass']} | {v['fail']} | {v['unknown']} | {v.get('unknown_record_absent')} | {v.get('unknown_field_absent')} | {v.get('unknown_value')} |")
        o = g["overall"]
        ub = o.get("unknown_breakdown", {})
        a(f"| **전체(네 조건 모두)** | **{o['usable']}** | **{o['not_usable']}** | **{o['unknown']}** | {ub.get('record_absent')} | — | {ub.get('present_but_unconfirmed')} (행은 있으나 미확인) |\n")
        if o.get("unknown_record_absent_ids"):
            a(f"- **레코드 없음 {len(o['unknown_record_absent_ids'])}건({', '.join(o['unknown_record_absent_ids'])})**: 새 판본 파일에 행이 없다. 검사 결과가 아니므로 사용 불가가 아니라 **미확인**으로 셌고, 네 조건 모두 미확인으로 잡았다.")
        a("- 동의 `consent=\"missing\"`은 동의 기록이 없는 것이므로 README 규칙(누락 항목=미확인)에 따라 **미확인**으로 셌다. 미충족이 아니지만 통과도 아니다.")
        a("- 전체 판정: 하나라도 미충족이면 사용 불가, 미충족 없이 미확인이 있으면 미확인.")
        a("- 문제 조합: " + "; ".join(f"`{k}` {v}건" for k, v in g["issue_combinations"].items()))
        a("- 컬렉션별: " + "; ".join(f"{c} 가능 {v['pass']}/불가 {v['fail']}/미확인 {v['unknown']}" for c, v in sorted(g["by_collection"].items())))
        a("- 전체 ID 목록: `reviews/data_gates.json`의 `per_gate.*.fail_ids/unknown_ids`, `nonpass_records`\n")
    if s["budget"]:
        b = s["budget"]
        a("## 3. 예산\n")
        a(f"- 기준: {b['basis']}")
        scb = b.get("scope_change") or {}
        if scb.get("excluded_streams"):
            a(f"- 적용 예산 {b['budget']:,}원({scb['budget_source']}; 입력 project.budget {scb['budget_input']:,}원).")
            a(f"- 범위 제외: {', '.join(scb['excluded_streams'])} 작업 {len(scb['excluded_tasks'])}개(전부 선택 작업, 작업비 {scb['excluded_cost']:,}원). 외부 SaaS(O2)·얼굴 분류(O3) 제외의 비용 효과: {scb['excluded_options_cost_effect']}.")
        if b.get("shortfall_total"):
            a(f"- 범위 내 작업비 = 필수 {b['required_cost']:,}원 + 선택 {b['optional_cost']:,}원 = **{b['total_cost']:,}원**, 예산 {b['budget']:,}원 → **{b['shortfall_total']:,}원 부족. 예산 미충족.**")
            a(f"- {scb.get('within_budget_note', '')}")
            a("- 승인이 필요한 대안(사용자 결정 전에는 어느 것도 적용하지 않음):")
            for x in scb.get("alternatives_need_approval", []):
                a(f"  - {x['id']}: {x['option']} — {x['effect']}")
            a(f"- 제안하지 않은 방식: {scb.get('not_proposed')}")
        else:
            a(f"- 필수 작업비 {b['required_cost']:,}원 + 선택 작업비 {b['optional_cost']:,}원 = **{b['total_cost']:,}원**, 예산 {b['budget']:,}원 → 잔액 **{b['surplus_total']:,}원** (필수만이면 잔액 {b['surplus_required_only']:,}원). **예산 충족.**")
        a(f"- options 견적(O1~O3 합 {b['options_cost_sum_reference']:,}원)은 비교 정보로만 두고 합산하지 않았다.\n")
    if s["schedule"]:
        c = s["schedule"]
        scs = c.get("scope_change") or {}
        a(f"## 4. 작업 순서·병목·완료 상태 ({c['integrity']['task_count']}개)\n")
        if scs.get("excluded_tasks"):
            a(f"- 범위 제외: {', '.join(scs['excluded_streams'])} 작업 {len(scs['excluded_tasks'])}개는 계산에서 뺐다. 그 영수증({', '.join(scs['excluded_receipts_not_counted'])})은 완료 수에 넣지 않았다. 범위 안 작업이 제외 작업에 의존하는 경우: {len(scs['in_scope_depends_on_excluded'])}건.")
        i = c["integrity"]
        a(f"- 그래프 무결성: 작업 {i['task_count']}개, 중복 ID {len(i['duplicate_ids'])}, 없는 선행 {len(i['dangling_depends'])}, 순환 {len(i['cycle_nodes'])}.")
        nstr = len(c["by_stream"]) if c.get("by_stream") else i["task_count"] // 12
        a(f"- 구조: 스트림 {nstr}개가 각각 독립 12단계 직렬 사슬(W*-01→…→W*-12), 스트림 간 선행 없음. 위상 정렬 전체 순서는 `reviews/schedule.json#topological_order`.")
        a(f"- 임계경로: 범위 전체 {c['cpm_all']['project_hours']}시간, 필수만 {c['cpm_required']['project_hours']}시간. {nstr}개 사슬이 모두 42시간으로 동률이라 각 스트림 사슬 전체가 임계경로(여유 0). {c['cpm_all']['note']}.")
        sc_ = c["status_counts"]
        a(f"- 영수증 기준 상태: 완료 {sc_['done']} · 보고만·미검증 {sc_['reported_unverified']} · 실행 가능 {sc_['ready']} · 대기 {sc_['waiting']}")
        a(f"  - 완료: {', '.join(c['done'])}")
        a(f"  - 미검증(완료 아님): {', '.join(c['reported_unverified'])}")
        a(f"  - 실행 가능: {', '.join(c['ready'])}" + (" (W6-03은 선택기능)" if "W6-03" in c["ready"] else ""))
        a("- 병목(미완료 선두 작업이 막는 후속):\n")
        a("| 작업 | 상태 | 선택 | 막는 후속 수 | 남은 사슬 시간(h) |\n|---|---|---|---:|---:|")
        for x in c["bottlenecks"]:
            a(f"| {x['task']} | {x['status']} | {'예' if x['optional'] else '아니오'} | {x['blocks_count']} | {x['blocks_hours']} |")
        r = c["remaining"]
        a(f"\n- 핵심 병목: **W4-02**(접근성) — 완료 보고는 있으나 verified=false라 W4-03~W4-12(10개)가 대기, 남은 사슬이 다른 스트림보다 4시간 길어 남은 일정의 최장 경로(필수 {r['longest_path_hours_required']}h)를 정한다.")
        a(f"- 남은 작업: 전체 {r['tasks_all']}개 / 필수 {r['tasks_required']}개, 작업시간 합 필수 {r['hours_sum_required']}h(전체 {r['hours_sum_all']}h), 병렬 최장 경로 필수 {r['longest_path_hours_required']}h.")
        a("- fan-in(선행 수) 최댓값 1 — 합류형 병목 작업은 없다.\n")
    dl = rv["deadline"]
    a("## 5. 기한 (" + str(dl.get("date")) + ")\n")
    a(f"- 판정: **{dl['verdict']}** — {dl['reason']}.")
    if dl.get("needed"):
        a("- 필요한 정보: " + "; ".join(dl["needed"]) + "\n")
    if s["operations"]:
        a("## 6. 운영 조건\n")
        a("| ID | 조건 | 판정 | 근거·함의 |\n|---|---|---|---|")
        for c in s["operations"]:
            ev = c["evidence"] if isinstance(c["evidence"], str) else json.dumps(c["evidence"], ensure_ascii=False)
            a(f"| {c['id']} | {c['condition']} | {c['verdict']} | {ev} — {c['implication']} |")
        if COND.get("excluded_options"):
            a("\n외부 SaaS(O2)·얼굴 자동 분류(O3)는 사용자 지시로 범위에서 빠져 해당 정책 확인이 불필요해졌다. O1 채택 자체는 사용자가 명시하지 않아 기록이 필요하다. 공개 승인 절차는 여전히 입력에 없다.\n")
        else:
            a("\n입력에 없는 정책(외부 SaaS 허용, 얼굴 처리 근거, 공개 승인 절차)은 지어내지 않고 미확인으로 두었다.\n")
    a("## 7. 우선 조치 목록\n")
    a("| 순위 | 우선도 | 영역 | 조치 | 대상 | 근거 |\n|---:|---:|---|---|---|---|")
    for x in rv["priority_actions"]:
        tgt = x.get("target_count", "")
        if x.get("targets"):
            tgt = ", ".join(x["targets"])
        if x.get("blocks_tasks") is not None:
            tgt = f"1건(후속 {x['blocks_tasks']}개 차단)"
        a(f"| {x['rank']} | P{x['priority']} | {x['area']} | {x['action']} | {tgt} | `{x['evidence']}` |")
    a("\n## 8. 실행 원장 요약(병렬·합류)\n")
    a("| 검토 | 상태 | 스레드 | 시작(UTC) | 종료(UTC) | 입력 파일 | 산출물 sha256(앞 12) |\n|---|---|---|---|---|---|---|")
    for n, e in ledger["reviews"].items():
        a(f"| {n} | {e['status']}{' (직전 턴에서 복사)' if e['status'] == 'reused' else ''} | {e.get('thread')} | {e['started_at']} | {e['ended_at']} | {', '.join(e.get('input_files', []))} | {(e.get('output_sha256') or '')[:12]} |")
    m = ledger["merge"]
    a(f"| merge | — | main | {m['started_at']} | (원장 기록 후) | reviews/*.json | 아래 파일 |")
    ov = ledger["parallel_evidence"]
    ov_pairs = ", ".join(f"{k.replace('|', '↔')} {'겹침' if v else '겹침 없음'}" for k, v in ov["pairwise_overlap"].items())
    a(f"\n- 동시 제출 {ov['submitted_at']} ({ov['executor']}). 네 검토 공통 겹침: {'있음 ' + ov['common_window'] if ov['all_four_overlap'] else '없음'}.")
    a(f"- 쌍별 실행 구간 겹침: {ov_pairs}.")
    a(f"- {ov['note']}")
    a(f"- 합류 시작 {m['started_at']} ≥ 마지막 검토 종료 {ov['last_review_end']}: {ov['merge_after_all_reviews']}.")
    a("- 다음 턴은 `tools/review.py --prev <이 폴더>`로 실행하면 검토별 입력 조각 지문이 같은 검토는 재사용하고, 바뀐 검토와 합류만 다시 한다. 상세: `run_ledger.json`.\n")
    a("## 9. 한계\n- 합성 입력 판본 기준이며 실제 개통·공개·발송·구매·운영 변경은 하지 않았다.\n- 자료 조건은 입력 값 그대로 판정했고 원본 파일의 체크섬을 다시 계산하지는 않았다.\n- 기한·인력 배치는 정보가 없어 판정하지 않았다.")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prev")
    ap.add_argument("--fail", default="", help="시험용: 지정 검토를 강제 실패")
    ap.add_argument("--conditions", help="사용자 변경 조건 JSON(예산·excluded_streams·excluded_options·kept)")
    a = ap.parse_args()
    if a.conditions:
        COND.update(json.load(open(a.conditions, encoding="utf-8")))
    out = os.path.abspath(a.out)
    if os.path.abspath(a.inputs) in out:
        sys.exit("출력이 입력 폴더 안에 있음")
    os.makedirs(os.path.join(out, "reviews"), exist_ok=True)
    prev_ledger = json.load(open(os.path.join(a.prev, "run_ledger.json"))) if a.prev else None
    ledger = {"turn": os.path.basename(out), "run_started_at": now(), "time_note": KST_NOTE,
              "script": {"path": os.path.abspath(__file__), "sha256": sha_file(__file__)},
              "prev": a.prev, "inputs_dir": os.path.abspath(a.inputs),
              "conditions": a.conditions and {"path": os.path.abspath(a.conditions), "sha256": sha_file(a.conditions), "data": COND}}
    load_s = now()
    files = load_inputs(a.inputs)
    ledger["load"] = {"started_at": load_s, "ended_at": now(),
                      "files": {k: {kk: v.get(kk) for kk in ("path", "sha256", "bytes", "status", "error")} for k, v in files.items()}}
    for f in [x for x in a.fail.split(",") if x]:
        REVIEWS[f] = (REVIEWS[f][0], lambda sl, f=f: (_ for _ in ()).throw(RuntimeError(f"시험용 강제 실패: {f}")))
    ledger["reviews"] = {}
    submitted_at = now()
    with cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="review") as ex:
        futs = [ex.submit(run_one, n, files, out, prev_ledger, a.prev) for n in REVIEWS]
        for fu in cf.as_completed(futs):
            n, e = fu.result()
            ledger["reviews"][n] = e
    ledger["reviews"] = {n: ledger["reviews"][n] for n in REVIEWS}
    merge_start = now()
    ends = [e["ended_at"] for e in ledger["reviews"].values()]
    starts = [e["started_at"] for e in ledger["reviews"].values()]
    rv_ = ledger["reviews"]
    names = list(rv_)
    pairs = {f"{x}|{y}": rv_[x]["started_at"] < rv_[y]["ended_at"] and rv_[y]["started_at"] < rv_[x]["ended_at"]
             for i, x in enumerate(names) for y in names[i + 1:]}
    ledger["parallel_evidence"] = {
        "executor": "ThreadPoolExecutor(max_workers=4), 네 검토를 한 번에 제출(submitted_at)",
        "submitted_at": submitted_at,
        "max_start": max(starts), "min_end": min(ends), "last_review_end": max(ends),
        "all_four_overlap": max(starts) < min(ends),
        "common_window": f"{max(starts)} ~ {min(ends)}" if max(starts) < min(ends) else None,
        "pairwise_overlap": pairs,
        "note": "기록상 겹침을 만들려는 시작 장벽은 넣지 않았다. 짧은 검토는 다른 검토 시작 전에 끝날 수 있으며, 그 경우 겹침 없음으로 그대로 기록한다. 스레드는 GIL을 공유하므로 CPU 동시 실행이 아니라 동시 제출·교차 실행이다.",
        "merge_after_all_reviews": merge_start >= max(ends),
    }
    if prev_ledger:
        pf = {k: v.get("sha256") for k, v in prev_ledger["load"]["files"].items()}
        cf_ = {k: v.get("sha256") for k, v in ledger["load"]["files"].items()}
        same = pf == cf_
        prev_turn = os.path.basename(os.path.normpath(a.prev))
        changed_files = sorted(k for k in cf_ if pf.get(k) != cf_[k])
        prev_cond_sha = (prev_ledger.get("conditions") or {}).get("sha256")
        cur_cond_sha = ledger["conditions"]["sha256"] if ledger.get("conditions") else None

        def why_of(n, e):
            pe = prev_ledger["reviews"].get(n, {})
            fc = sorted(k for k in set(e.get("input_fingerprints", {})) | set(pe.get("input_fingerprints", {}))
                        if e.get("input_fingerprints", {}).get(k) != pe.get("input_fingerprints", {}).get(k))
            if e["status"] == "failed":
                return f"실행 실패: {e.get('error')}"
            if e["status"] == "reused":
                return f"입력 조각 지문 {len(e.get('input_fingerprints', {}))}개가 {prev_turn}과 모두 같음({', '.join(e.get('input_fingerprints', {}))}) — 바뀐 파일({', '.join(changed_files) or '없음'})을 쓰지 않음"
            return f"입력 조각 지문이 바뀜: {', '.join(fc) or '(직전 결과 없음/불일치)'}"
        ledger["change_impact"] = {
            "input_version_check": (f"현재 입력 6개 파일 sha256이 {prev_turn} 원장과 모두 일치" if same
                                    else f"{prev_turn} 원장 대비 sha256이 바뀐 파일: {', '.join(changed_files)}; 나머지 {len(cf_) - len(changed_files)}개는 동일"),
            "input_files_identical_to_prev": same,
            "changed_files": {k: {"prev_sha256": pf.get(k), "now_sha256": cf_[k], "now_status": ledger["load"]["files"][k]["status"]} for k in changed_files},
            "unchanged_files": sorted(k for k in cf_ if k not in changed_files),
            "conditions_same_as_prev": prev_cond_sha == cur_cond_sha,
            "changes": [{"item": f"입력 {k}", "before": f"sha256 {(pf.get(k) or '')[:12]}…", "after": f"sha256 {(cf_[k] or '읽기 실패')[:12]}…"} for k in changed_files]
                       + [{"item": "정책 조건", "before": f"{prev_turn} conditions.json sha256 {(prev_cond_sha or '')[:12]}…",
                           "after": ("동일(변경 없음)" if prev_cond_sha == cur_cond_sha else f"sha256 {(cur_cond_sha or '')[:12]}…")}],
            "reviews": {n: {"decision": (f"재사용({prev_turn} 결과 복사)" if e["status"] == "reused" else "재수행" if e["status"] != "failed" else "실패(판정 보류)"),
                            "reason": why_of(n, e), "reused_from": e.get("reused_from"),
                            "fingerprints_changed": sorted(k for k in set(e.get("input_fingerprints", {})) | set(prev_ledger["reviews"].get(n, {}).get("input_fingerprints", {}))
                                                           if e.get("input_fingerprints", {}).get(k) != prev_ledger["reviews"].get(n, {}).get("input_fingerprints", {}).get(k))}
                        for n, e in ledger["reviews"].items()},
            "merge": "재수행 — 검토 결과 해시가 바뀐 검토: " + (", ".join(n for n, e in ledger["reviews"].items() if e.get("output_sha256") != prev_ledger["reviews"].get(n, {}).get("output_sha256")) or "없음"),
        }
        dg_e = ledger["reviews"].get("data_gates", {})
        if dg_e.get("status") in ("ok", "ok_with_blocked_parts"):
            ledger["data_diff_vs_prev"] = data_diff(os.path.join(a.prev, "reviews", "data_gates.json"),
                                                    json.load(open(dg_e["output"], encoding="utf-8")))
    ledger["merge"] = {"started_at": merge_start, "depends_on_reviews": list(REVIEWS),
                       "inputs": {n: e.get("output_sha256") for n, e in ledger["reviews"].items()}}
    rv = merge(out, ledger, files)
    jp = os.path.join(out, "acceptance_review.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(rv, f, ensure_ascii=False, indent=2)
    mp = os.path.join(out, "인수검토서.md")
    open(mp, "w", encoding="utf-8").write(md_report(rv, ledger))
    ledger["merge"]["ended_at"] = now()
    ledger["merge"]["outputs"] = {"acceptance_review.json": sha_file(jp), "인수검토서.md": sha_file(mp)}
    ledger["run_ended_at"] = now()
    with open(os.path.join(out, "run_ledger.json"), "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
    print(json.dumps({"verdict": rv["verdict"], "reviews": {n: e["status"] for n, e in ledger["reviews"].items()},
                      "parallel": ledger["parallel_evidence"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
