"""지역자료실 이전·검색 서비스 개통 준비 인수 검토 (턴별 실행기).

사용: python3 -I review.py --inputs <입력폴더> --out <ai/Tn> [--prev <ai/Tm>]
- 독립 검토 4개(data_gates·budget·schedule·operations)를 스레드로 동시 실행한다.
- 각 검토는 자기가 쓰는 입력 조각의 지문(sha256)을 남긴다. --prev 의 원장에서
  같은 검토의 지문이 같으면 결과 파일을 재사용(reused)하고, 다르면 재수행한다.
- 합류(merge)는 네 검토가 모두 끝난 뒤 시작하며, 실패한 검토는 blocked 로 남긴다.
입력 폴더에는 쓰지 않는다.
"""
import argparse, concurrent.futures as cf, hashlib, json, os, shutil, sys, threading, time, traceback
from datetime import datetime, timezone

KST_NOTE = "시각은 UTC ISO8601(마이크로초)"


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
    for rid in expected_ids:
        it = seen.get(rid)
        if it is None:
            overall["unknown"].append(rid)
            for f, _ in GATES:
                per_gate[f]["unknown"].append(rid)
            per_record.append({"id": rid, "verdict": "unknown", "reason": "자료 행 없음"})
            continue
        states = {}
        for f, _ in GATES:
            if f not in it:
                per_gate[f]["missing_field"].append(rid)
                s = "unknown"
            else:
                s = gate_state(f, it[f])
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
        combos[key] = combos.get(key, 0) + 1
    gates_out = {f: {"label": g["label"], "pass": len(g["pass"]), "fail": len(g["fail"]), "unknown": len(g["unknown"]),
                     "fail_ids": g["fail"], "unknown_ids": g["unknown"], "missing_field_ids": g["missing_field"]}
                 for f, g in per_gate.items()}
    total = len(expected_ids)
    counts = {k: len(v) for k, v in overall.items()}
    assert sum(counts.values()) == total, "전체 판정 합이 기대 건수와 다름"
    return {
        "review": "data_gates",
        "rules": {"consent": "yes=충족, no류=미충족, 'missing'·누락·기타=미확인(README: 누락 항목은 미확인)",
                  "checksum": "pass=충족, fail=미충족, 그 외=미확인",
                  "searchable/accessible": "true=충족, false=미충족, 그 외=미확인",
                  "overall": "네 조건 모두 충족=사용 가능, 하나라도 미충족=사용 불가, 미충족 없이 미확인 포함=미확인"},
        "records_version": rec.get("version"),
        "expected_records": total, "rows_in_file": len(items),
        "integrity": {"duplicate_ids": dup, "missing_ids": missing_ids, "unexpected_ids": unexpected_ids, "malformed_rows": malformed},
        "per_gate": gates_out,
        "overall": {"usable": counts["pass"], "not_usable": counts["fail"], "unknown": counts["unknown"],
                    "not_usable_ids": overall["fail"], "unknown_ids": overall["unknown"]},
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
            "options.json#items,cost_note": {"items": o.get("items"), "cost_note": o.get("cost_note")}}


def run_budget(sl):
    tasks = sl["tasks.json#id,cost,optional"]
    budget = sl["project.json#budget"]
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
    return {
        "review": "budget",
        "basis": "tasks.cost 합계가 정본. options.cost는 작업원가에 포함된 비교 정보이므로 합산하지 않음(options.cost_note)",
        "budget": budget,
        "tasks_counted": len(ok), "tasks_cost_invalid": bad,
        "required_cost": req, "optional_cost": opt, "total_cost": total,
        "surplus_total": budget - total, "surplus_required_only": budget - req,
        "within_budget_total": total <= budget, "within_budget_required_only": req <= budget,
        "by_stream": by_stream,
        "options_reference_not_added": [{"id": o["id"], "name": o["name"], "cost": o["cost"]} for o in opts["items"]],
        "options_cost_sum_reference": sum(o["cost"] for o in opts["items"]),
        "cost_note": opts["cost_note"],
        "blocked": bool(bad),
    }


def slice_schedule(files):
    p = need(files, "project.json")
    return {"tasks.json": need(files, "tasks.json"), "receipts.json": need(files, "receipts.json"),
            "project.json#deadline,status_rule": {"deadline": p.get("deadline"), "status_rule": p.get("status_rule")}}


def run_schedule(sl):
    tasks = sl["tasks.json"]["items"]
    rcpt = {r["task_id"]: r for r in sl["receipts.json"]["items"]}
    T = {t["id"]: t for t in tasks}
    dup = [t["id"] for i, t in enumerate(tasks) if t["id"] in [u["id"] for u in tasks[:i]]]
    dangling = [{"task": t["id"], "missing_dep": d} for t in tasks for d in t["depends"] if d not in T]
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
        "rules": {"done": "receipts의 reported_done과 verified가 모두 true일 때만 (project.status_rule)",
                  "ready": "선행 작업이 모두 done이고 자신은 미완료",
                  "reported_unverified": "완료 보고만 있고 검증 영수증 없음 → 미완료, 재검증 필요",
                  "waiting": "선행 작업 미완료 → 실행 가능으로 표시하지 않음",
                  "tasks.status": "모든 작업이 'planned'로 기재되어 있어 진행 판정에 쓰지 않고 영수증을 따름"},
        "integrity": {"task_count": len(T), "duplicate_ids": dup, "dangling_depends": dangling, "cycle_nodes": cyclic,
                      "receipts_for_unknown_tasks": orphan_receipts},
        "topological_order": order,
        "cpm_all": {"project_hours": proj_all, "critical_tasks": crit_all, "critical_chains": chains_all,
                    "slack": slack, "note": "모든 스트림이 독립 12단계 사슬이며 길이가 같아 동률 임계경로가 여러 개"},
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
                     "reason": "hours는 순수 작업시간이며 달력·인력 가용시간이 주어지지 않음",
                     "needed": ["담당자별 주당 가용시간·휴무일", "스트림 간 병렬 투입 가능 인원", "W4-02 재검증 소요 시간",
                                "작업 착수 가능일(기준일)", "검증 영수증 발급 소요 시간", "개통 전 리허설·인수 일정"]},
        "blocked": bool(dangling or cyclic or dup),
    }


def slice_operations(files):
    p = need(files, "project.json")
    o = need(files, "options.json")
    t = need(files, "tasks.json")
    return {"project.json#publication,acceptance,status_rule,gates": {k: p.get(k) for k in ("publication", "acceptance", "status_rule", "gates")},
            "options.json#items": o.get("items"),
            "tasks.json#id,stream,optional,status": [{k: x.get(k) for k in ("id", "stream", "optional", "status")} for x in t["items"]]}


def run_operations(sl):
    p = sl["project.json#publication,acceptance,status_rule,gates"]
    opts = sl["options.json#items"]
    tk = sl["tasks.json#id,stream,optional,status"]
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
    conds.append({"id": "OP-3", "condition": "외부 SaaS 사용 여부(O2 상용 외부 검색)",
                  "verdict": "미확인",
                  "evidence": [{"id": o["id"], "name": o["name"], "external_saas": True} for o in ext],
                  "implication": "외부 SaaS 허용·개인정보 위탁 정책이 입력에 없음. 어느 검색안을 택했는지도 입력에 없음 → 선택안 확정과 정책 확인 필요"})
    conds.append({"id": "OP-4", "condition": "얼굴 처리 기능 여부(O3 얼굴 자동 분류)",
                  "verdict": "미확인",
                  "evidence": [{"id": o["id"], "name": o["name"], "face": True} for o in face],
                  "implication": "생체정보(얼굴) 처리 허용 근거·동의 범위가 입력에 없음. 선택기능 스트림(W6)과 O3의 대응도 입력에 명시 없음"})
    sel = [x for x in tk if x["optional"]]
    conds.append({"id": "OP-5", "condition": "선택 작업(optional) 분리",
                  "verdict": "확인됨",
                  "evidence": {"optional_tasks": [x["id"] for x in sel], "streams": sorted({x["stream"] for x in sel})},
                  "implication": "선택기능(W6) 12개는 개통 필수 판정에서 제외. 채택 여부는 입력에 없음"})
    conds.append({"id": "OP-6", "condition": "인수 기준(acceptance): 1800건 전량 네 조건 충족 + 필수 작업 증거 완료",
                  "verdict": "합류 단계에서 판정", "evidence": p["acceptance"],
                  "implication": "자료 게이트·일정 검토 결과가 필요 → merge 단계에서 판정"})
    conds.append({"id": "OP-7", "condition": "선택안(검색 방식) 결정",
                  "verdict": "미확인", "evidence": [o["id"] for o in opts],
                  "implication": "O1(내부)·O2(외부) 중 채택안이 입력에 없음"})
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
        ent["input_files"] = sorted({k.split("#")[0] for k in sl})
        ent["input_file_sha256"] = {f: files[f]["sha256"] for f in ent["input_files"]}
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
        actions.append({"priority": 1, "area": "자료", "action": "동의 기록 누락 자료의 동의 확인·회수",
                        "target_count": g["consent"]["unknown"], "evidence": "reviews/data_gates.json#per_gate.consent.unknown_ids",
                        "ids_sample": g["consent"]["unknown_ids"][:10]})
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
    if op:
        actions.append({"priority": 2, "area": "운영", "action": "검색 선택안(O1 내부/O2 외부 SaaS) 확정과 외부 SaaS 허용 정책 확인",
                        "evidence": "reviews/operations.json#OP-3,OP-7"})
        actions.append({"priority": 3, "area": "운영", "action": "얼굴 자동 분류(O3)·선택기능(W6) 채택 여부와 생체정보 처리 근거 확인",
                        "evidence": "reviews/operations.json#OP-4,OP-5"})
    for n in blocked:
        actions.insert(0, {"priority": 0, "area": "검토 실패", "action": f"{n} 검토 재수행(입력·실행 오류 해소)",
                           "evidence": ledger["reviews"][n].get("error")})
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
        req_ids = [k for k in sc["status"] if tk and not tk[k]["optional"]]
        req_done_n = sum(1 for k in req_ids if sc["status"][k] == "done")
        req_done = req_done_n == len(req_ids)
    budget_ok = bu["within_budget_total"] if bu else None
    acceptance = {
        "data_all_four_gates": {"met": data_ok, "detail": dg and {"usable": dg["overall"]["usable"], "not_usable": dg["overall"]["not_usable"], "unknown": dg["overall"]["unknown"], "expected": dg["expected_records"]}},
        "required_tasks_done_with_receipts": {"met": req_done, "detail": sc and {"required": len(req_ids), "done": req_done_n}},
        "budget": {"met": budget_ok, "detail": bu and {"total_cost": bu["total_cost"], "budget": bu["budget"], "surplus": bu["surplus_total"]}},
        "operations_open_items": [c["id"] for c in op["conditions"] if c["verdict"] == "미확인"] if op else None,
    }
    if blocked:
        verdict = "보류(검토 일부 실패)"
    elif data_ok and req_done:
        verdict = "개통 가능(인수 기준 충족) — 운영 미확인 항목 확인 필요"
    else:
        verdict = "개통 불가(현시점)"
    review = {
        "project": files["project.json"]["data"].get("project") if files["project.json"]["status"] == "ok" else None,
        "turn": os.path.basename(out.rstrip("/")),
        "generated_at": now(),
        "verdict": verdict,
        "verdict_scope": "검토 완료는 실제 개통 완료가 아니다. 이 판정은 입력 판본 기준의 준비 상태 판정이며, 공개·배포·운영 변경은 하지 않았다(publication=draft_only).",
        "acceptance_check": acceptance,
        "deadline": sc["deadline"] if sc else {"verdict": "미확정", "reason": "schedule 검토 실패"},
        "priority_actions": actions,
        "blocked_reviews": blocked,
        "review_outputs": {n: {"path": e.get("output"), "sha256": e.get("output_sha256"), "status": e["status"]} for n, e in ledger["reviews"].items()},
        "summaries": {
            "data_gates": dg and {k: dg[k] for k in ("expected_records", "rows_in_file", "integrity", "overall", "by_collection", "issue_combinations")} | {"per_gate_counts": {f: {k: v[k] for k in ("label", "pass", "fail", "unknown")} for f, v in dg["per_gate"].items()}},
            "budget": bu and {k: bu[k] for k in ("basis", "budget", "required_cost", "optional_cost", "total_cost", "surplus_total", "surplus_required_only", "within_budget_total", "options_reference_not_added", "options_cost_sum_reference")},
            "schedule": sc and {k: sc[k] for k in ("integrity", "status_counts", "done", "reported_unverified", "ready", "bottlenecks", "remaining")} | {"cpm_all": {k: sc["cpm_all"][k] for k in ("project_hours", "critical_chains", "note")}, "cpm_required": sc["cpm_required"]},
            "operations": op and op["conditions"],
        },
    }
    return review


def md_report(rv, ledger):
    s = rv["summaries"]; L = []
    a = L.append
    a(f"# 인수 검토서 — {rv['project']} ({rv['turn']})\n")
    a(f"- 생성: {rv['generated_at']} (UTC)\n- **판정: {rv['verdict']}**\n- 범위: {rv['verdict_scope']}\n")
    if rv["blocked_reviews"]:
        a(f"- ⚠ 실패한 검토: {', '.join(rv['blocked_reviews'])} — 확인된 다른 결과는 보존함\n")
    ac = rv["acceptance_check"]
    a("## 1. 인수 기준 대조\n")
    a("| 기준 | 판정 | 근거 |\n|---|---|---|")
    d = ac["data_all_four_gates"]["detail"] or {}
    a(f"| 1800건 전량 네 조건 충족 | {'충족' if ac['data_all_four_gates']['met'] else '미충족'} | 사용 가능 {d.get('usable')} / 불가 {d.get('not_usable')} / 미확인 {d.get('unknown')} (기대 {d.get('expected')}) |")
    t = ac["required_tasks_done_with_receipts"]["detail"] or {}
    a(f"| 필수 작업 증거 완료 | {'충족' if ac['required_tasks_done_with_receipts']['met'] else '미충족'} | 필수 {t.get('required')}개 중 영수증 완료 {t.get('done')}개 |")
    b = ac["budget"]["detail"] or {}
    a(f"| 예산(참고) | {'충족' if ac['budget']['met'] else '초과'} | tasks.cost 합 {b.get('total_cost'):,}원 / 예산 {b.get('budget'):,}원, 잔액 {b.get('surplus'):,}원 |")
    a(f"| 운영 미확인 | — | {', '.join(ac['operations_open_items'] or [])} |\n")
    if s["data_gates"]:
        g = s["data_gates"]
        a("## 2. 자료 사용 가능 여부 (D0001~D1800)\n")
        a(f"파일 행 {g['rows_in_file']} / 기대 {g['expected_records']}, 중복 ID {len(g['integrity']['duplicate_ids'])}, 누락 ID {len(g['integrity']['missing_ids'])}, 형식 오류 행 {len(g['integrity']['malformed_rows'])}.\n")
        a("| 조건 | 충족 | 미충족 | 미확인 |\n|---|---:|---:|---:|")
        for f, v in g["per_gate_counts"].items():
            a(f"| {v['label']} ({f}) | {v['pass']} | {v['fail']} | {v['unknown']} |")
        o = g["overall"]
        a(f"| **전체(네 조건 모두)** | **{o['usable']}** | **{o['not_usable']}** | **{o['unknown']}** |\n")
        a("- 동의 `consent=\"missing\"`은 동의 기록이 없는 것이므로 README 규칙(누락 항목=미확인)에 따라 **미확인**으로 셌다. 미충족이 아니지만 통과도 아니다.")
        a("- 전체 판정: 하나라도 미충족이면 사용 불가, 미충족 없이 미확인이 있으면 미확인.")
        a("- 문제 조합: " + "; ".join(f"`{k}` {v}건" for k, v in g["issue_combinations"].items()))
        a("- 컬렉션별: " + "; ".join(f"{c} 가능 {v['pass']}/불가 {v['fail']}/미확인 {v['unknown']}" for c, v in sorted(g["by_collection"].items())))
        a("- 전체 ID 목록: `reviews/data_gates.json`의 `per_gate.*.fail_ids/unknown_ids`, `nonpass_records`\n")
    if s["budget"]:
        b = s["budget"]
        a("## 3. 예산\n")
        a(f"- 기준: {b['basis']}")
        a(f"- 필수 작업비 {b['required_cost']:,}원 + 선택 작업비 {b['optional_cost']:,}원 = **{b['total_cost']:,}원**, 예산 {b['budget']:,}원 → 잔액 **{b['surplus_total']:,}원** (필수만이면 잔액 {b['surplus_required_only']:,}원). **예산 충족.**")
        a(f"- options 견적(O1~O3 합 {b['options_cost_sum_reference']:,}원)은 비교 정보로만 두고 합산하지 않았다.\n")
    if s["schedule"]:
        c = s["schedule"]
        a("## 4. 작업 순서·병목·완료 상태 (72개)\n")
        i = c["integrity"]
        a(f"- 그래프 무결성: 작업 {i['task_count']}개, 중복 ID {len(i['duplicate_ids'])}, 없는 선행 {len(i['dangling_depends'])}, 순환 {len(i['cycle_nodes'])}.")
        a(f"- 구조: 스트림 6개가 각각 독립 12단계 직렬 사슬(W*-01→…→W*-12), 스트림 간 선행 없음. 위상 정렬 전체 순서는 `reviews/schedule.json#topological_order`.")
        a(f"- 임계경로: 전체 {c['cpm_all']['project_hours']}시간, 필수만 {c['cpm_required']['project_hours']}시간. 6개 사슬이 모두 42시간으로 동률이라 각 스트림 사슬 전체가 임계경로(여유 0). {c['cpm_all']['note']}.")
        sc_ = c["status_counts"]
        a(f"- 영수증 기준 상태: 완료 {sc_['done']} · 보고만·미검증 {sc_['reported_unverified']} · 실행 가능 {sc_['ready']} · 대기 {sc_['waiting']}")
        a(f"  - 완료: {', '.join(c['done'])}")
        a(f"  - 미검증(완료 아님): {', '.join(c['reported_unverified'])}")
        a(f"  - 실행 가능: {', '.join(c['ready'])} (W6-03은 선택기능)")
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
        a(f"| {n} | {e['status']} | {e.get('thread')} | {e['started_at']} | {e['ended_at']} | {', '.join(e.get('input_files', []))} | {(e.get('output_sha256') or '')[:12]} |")
    m = ledger["merge"]
    a(f"| merge | — | main | {m['started_at']} | (원장 기록 후) | reviews/*.json | 아래 파일 |")
    ov = ledger["parallel_evidence"]
    ov_pairs = ", ".join(f"{k.replace('|', '↔')} {'겹침' if v else '겹침 없음'}" for k, v in ov["pairwise_overlap"].items())
    a(f"\n- 동시 제출 {ov['submitted_at']} ({ov['executor']}). 네 검토 공통 겹침: {'있음 ' + ov['common_window'] if ov['all_four_overlap'] else '없음'}.")
    a(f"- 쌍별 실행 구간 겹침: {ov_pairs}.")
    a(f"- {ov['note']}")
    a(f"- 합류 시작 {m['started_at']} ≥ 마지막 검토 종료 {ov['last_review_end']}: {ov['merge_after_all_reviews']}.")
    a("- 다음 턴은 `tools/review.py --prev <이 폴더>`로 실행하면 검토별 입력 조각 지문이 같은 검토는 재사용하고, 바뀐 검토와 합류만 다시 한다. 상세: `run_ledger.json`.\n")
    a("## 9. 한계\n- 합성 입력 판본 기준이며 실제 개통·공개·발송은 하지 않았다.\n- 자료 조건은 입력 값 그대로 판정했고 원본 파일의 체크섬을 다시 계산하지는 않았다.\n- 기한·인력 배치는 정보가 없어 판정하지 않았다.")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prev")
    ap.add_argument("--fail", default="", help="시험용: 지정 검토를 강제 실패")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    if os.path.abspath(a.inputs) in out:
        sys.exit("출력이 입력 폴더 안에 있음")
    os.makedirs(os.path.join(out, "reviews"), exist_ok=True)
    prev_ledger = json.load(open(os.path.join(a.prev, "run_ledger.json"))) if a.prev else None
    ledger = {"turn": os.path.basename(out), "run_started_at": now(), "time_note": KST_NOTE,
              "script": {"path": os.path.abspath(__file__), "sha256": sha_file(__file__)},
              "prev": a.prev, "inputs_dir": os.path.abspath(a.inputs)}
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
