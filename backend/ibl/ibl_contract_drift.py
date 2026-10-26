"""선언 반환 계약 ↔ 실측 값 대조 — 검사기의 해소 결과를 그대로 기준으로 쓴다.

계약은 사람이 쓰고 실제 반환과 대조하는 자동 경로가 없었다. 31ea17f0 이전의 판정관용구는
실제로 {items, count}를 돌려주는데 계약은 필드 없는 Record였고, 그 Record가 본문에서찾기의
반환형이 되어 행 자리(>> [table:*])에서 정상 조합이 거절됐다 — 사람이 손으로 찾은 결함이다.

기준 타입은 따로 해석하지 않는다. 표본 프로그램을 검사기로 컴파일해 얻은 Plan.result_type이
변이(variants)·관측 모양·스크립트/관용구 특수화를 모두 거친 '검사기가 실제로 믿는 타입'이다.
비교도 검사기의 infer/compatible/rows_type만 쓴다(독자 타입 비교 없음).

판정:
- type_mismatch: 실측이 선언과 호환되지 않음(검사기가 허용한 조합이 실행에서 깨질 자리)
- over_declared: 선언한 칸이 실측에 없음(type_mismatch의 한 종류 — 칸 경로를 따로 남긴다)
- under_declared: 실측은 행 목록으로 쓸 수 있는데 선언은 행 자리에서 거절됨(정상 조합이 막힐 자리)
선언 밖 칸(open Record의 여분 칸)은 검사기 동작을 바꾸지 않으므로 판정이 아니라 참고(undeclared)다.

실행은 검사기가 효과 없음(pure)으로 판정한 표본만 한다. 그 밖은 실행하지 않고 대조 불가로 사유를 남긴다.
"""
import json

from ibl_v2_types import Type, UNKNOWN, infer, compatible, rows_type

ROWS = Type("List", item=UNKNOWN)
RUNNABLE_EFFECTS = frozenset({"pure"})
FAILING = ("type_mismatch", "over_declared", "under_declared")


def _missing_fields(expected, actual, path):
    if expected.kind != "Record" or actual.kind != "Record" or expected.observed:
        return []
    fields, out = dict(actual.fields), []
    for key, typ in expected.fields:
        if key not in fields:
            out.append(f"{path}.{key}")
        else:
            out += _missing_fields(typ, fields[key], f"{path}.{key}")
    return out


def _rows_gaps(expected, actual, path):
    """실측은 행 목록으로 해소되는데 선언은 행 자리에서 거절되는 경로(검사기의 rows_type 기준)."""
    if rows_type(actual).kind == "List" and not compatible(rows_type(expected), ROWS):
        return [path]
    if expected.kind != "Record" or actual.kind != "Record":
        return []
    fields, out = dict(actual.fields), []
    for key, typ in expected.fields:
        if key in fields:
            out += _rows_gaps(typ, fields[key], f"{path}.{key}")
    return out


def compare(expected, value):
    """검사기 타입(expected)과 실측 값(value)의 대조 결과."""
    actual = infer(value)
    report = {"declared": str(expected), "actual": str(actual)}
    if expected.kind == "Record" and actual.kind == "Record" and not expected.observed:
        known = {k for k, _ in expected.fields}
        extra = [k for k, _ in actual.fields if k not in known]
        if extra:
            report["undeclared"] = extra
    if not compatible(actual, expected):
        missing = _missing_fields(expected, actual, "$")
        verdict = "over_declared" if missing else "type_mismatch"
        return {**report, "verdict": verdict, "paths": missing}
    gaps = _rows_gaps(expected, actual, "$")
    if gaps:
        return {**report, "verdict": "under_declared", "paths": gaps}
    return {**report, "verdict": "ok", "paths": []}


def probe(plan, run):
    """컴파일된 표본 하나를 대조한다. run(plan)은 실행 결과 봉투(success·value·error)를 돌려준다."""
    if plan.issues:
        issue = plan.issues[0]
        return {"verdict": "check_failed", "reason": f"{issue.get('code')}: {issue.get('message')}"[:200]}
    effects = set(plan.effects)
    if not effects <= RUNNABLE_EFFECTS:
        return {"verdict": "not_comparable",
                "reason": "효과 " + ",".join(sorted(effects - RUNNABLE_EFFECTS)) + " — 무인 점검에서 실행하지 않음"}
    out = run(plan)
    if not out.get("success"):
        error = out.get("error") or {}
        code = error.get("code") if isinstance(error, dict) else None
        message = error.get("message") if isinstance(error, dict) else str(error)
        if code in ("TYPE_CONTRACT", "ADAPTER_SHAPE"):
            # 실행 경계의 계약 검사가 실측을 거절했다 — 선언과 실측의 어긋남이다.
            return {"verdict": "type_mismatch", "declared": str(plan.result_type),
                    "reason": f"{code}: {message}"[:200], "paths": []}
        return {"verdict": "error", "reason": f"{code or 'RUN'}: {message}"[:200]}
    return compare(plan.result_type, out.get("value"))


def _literal(value):
    # JSON 문서는 IBL 값 리터럴이다(따옴표 키·true/false/null).
    return json.dumps(value, ensure_ascii=False)


def collect(samples, scripts, compile_fn, run_fn):
    """계약을 선언한 등록 스크립트 전부와 표본이 있는 관용구를 대조한다.

    samples = {"scripts": {id: [args, …]}, "idioms": {이름: [인자, …]}} (data/ibl_contract_samples.json).
    scripts = data/scripts/registry.yaml 의 내용. 효과가 pure 가 아닌 스크립트는 표본이 있어도
    실행하지 않는다(최종 판정은 컴파일된 표본의 효과로 한 번 더 한다).
    """
    rows = []

    def run_case(target, code):
        try:
            row = probe(compile_fn(code), run_fn)
        except Exception as exc:
            row = {"verdict": "error", "reason": f"대조 예외: {exc}"[:200]}
        rows.append({"target": target, **row})

    script_samples = samples.get("scripts") or {}
    for sid, entry in sorted((scripts or {}).items()):
        contract = (entry or {}).get("callable_contract") if isinstance(entry, dict) else None
        if not contract:
            continue
        effects = sorted(set(contract.get("effects") or ["unknown"]))
        cases = script_samples.get(sid) or []
        if not set(effects) <= RUNNABLE_EFFECTS:
            rows.append({"target": f"script:{sid}", "verdict": "not_comparable",
                         "reason": "선언 효과 " + ",".join(effects) + " — 무인 점검에서 실행하지 않음"})
            continue
        if not cases:
            rows.append({"target": f"script:{sid}", "verdict": "no_sample",
                         "reason": "pure 스크립트인데 표본이 없음(data/ibl_contract_samples.json)"})
        for args in cases:
            op = args.get("op") if isinstance(args, dict) else None
            run_case(f"script:{sid}" + (f"#{op}" if op else ""),
                     f"return [self:script]{{id:{_literal(sid)},args:{_literal(args)}}}")
    for name, cases in sorted((samples.get("idioms") or {}).items()):
        for index, args in enumerate(cases or []):
            fields = ",".join(f"{_literal(k)}:{_literal(v)}" for k, v in args.items())
            run_case(f"fn:{name}" + (f"#{index + 1}" if len(cases) > 1 else ""),
                     f"return [fn:{name}]{{{fields}}}")
    return rows


def describe(summary):
    """원장·로그 한 줄. 어긋남·오류·대조 불가의 대상과 사유를 함께 적는다."""
    if summary.get("error"):
        return f"대조 실행 실패: {summary['error']}"[:400]
    parts = [f"대조 {summary.get('compared', 0)}", f"어긋남 {len(summary.get('drift') or [])}"]
    drift = "; ".join(f"{d['target']} {d['verdict']}({','.join(d.get('paths') or []) or d.get('reason') or ''})"
                      for d in (summary.get("drift") or [])[:5])
    if drift:
        parts[-1] += f" — {drift}"
    errors = summary.get("errors") or []
    if errors:
        parts.append(f"오류 {len(errors)} — " + "; ".join(f"{e['target']}: {e['reason']}" for e in errors[:3]))
    skipped = summary.get("not_comparable") or []
    if skipped:
        reasons = {}
        for row in skipped:
            reasons[row.get("reason") or "?"] = reasons.get(row.get("reason") or "?", 0) + 1
        parts.append(f"대조 불가 {len(skipped)} — "
                     + "; ".join(f"{n}건 {r}" for r, n in sorted(reasons.items(), key=lambda kv: -kv[1])))
    return " · ".join(parts)[:600]


def healthy(summary):
    """대조가 실제로 있었고 어긋남·오류가 없다. 대조 0건은 건강이 아니다(아무것도 재지 않았다)."""
    return (not summary.get("error") and summary.get("compared", 0) > 0
            and not summary.get("drift") and not summary.get("errors"))


def ledger_events(summary):
    """점검 스크립트 요약 → self_checks 행. 대조 불가 수·사유는 성공 행에도 남긴다 — 무엇을 재지
    않았는지가 빠지면 'GREEN'이 범위를 숨긴다. 요약이 없으면(옛 스크립트) 행을 만들지 않는다."""
    if not isinstance(summary, dict):
        return []
    ok = healthy(summary)
    quality = "ok" if ok else ("error" if summary.get("error") or summary.get("errors")
                               or not summary.get("compared") else "contract_drift")
    return [{"node": "__ibl_health__", "action": "contract_drift", "success": ok,
             "response_ms": 0, "data_quality": quality, "error_message": describe(summary)}]


def summarize(rows):
    """표본별 판정 → 원장용 요약. 대조 불가·오류는 숨기지 않고 수와 사유를 남긴다."""
    counts = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    drift = [r for r in rows if r["verdict"] in FAILING]
    errors = [r for r in rows if r["verdict"] in ("error", "check_failed")]
    skipped = [r for r in rows if r["verdict"] in ("not_comparable", "no_sample")]
    return {"counts": counts, "compared": sum(counts.get(v, 0) for v in ("ok",) + FAILING),
            "drift": [{"target": r["target"], "verdict": r["verdict"], "paths": r.get("paths", []),
                       "declared": r.get("declared"), "actual": r.get("actual"), "reason": r.get("reason")}
                      for r in drift],
            "errors": [{"target": r["target"], "reason": r.get("reason")} for r in errors],
            "not_comparable": [{"target": r["target"], "reason": r.get("reason")} for r in skipped]}
