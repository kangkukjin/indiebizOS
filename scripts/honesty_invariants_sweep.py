#!/usr/bin/env python3
"""현행 결과 불변식 검사: 성공 wire의 값·반환 선언·좌표·병렬 실패 전파.

실행 실패와 전송/검사 실패는 checked에 포함하지 않는다. 업무 값의 success,
error, result 같은 키와 산문은 실행 상태로 재해석하지 않는다.
--strict는 위반 또는 미완 검사를 종료 코드로 알린다. --static-only는 도구의
현재 텍스트 실패 규약 분포만 관찰하며 실행 건강을 인증하지 않는다.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from returns_drift_sweep import _load_declarations, _declared_of, _execute  # noqa: E402

from ibl_check_client import value_of as final_of, item_rows


# 좌표 칸 별칭 — show_map(_marker_coords)이 읽는 쌍과 같다. 정본은 lat/lng.
COORD_ALIAS_PAIRS = (("latitude", "longitude"), ("gpsY", "gpsX"), ("lat", "lon"), ("y", "x"))


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def coord_contract_violations(rows) -> list:
    """좌표류 칸을 값으로 가진 행 중 lat/lng 숫자가 없는 행 번호."""
    bad = []
    for i, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        has_alias = any(row.get(a) not in (None, "") and row.get(b) not in (None, "")
                        for a, b in COORD_ALIAS_PAIRS)
        if has_alias and not (_num(row.get("lat")) and _num(row.get("lng"))):
            bad.append(i)
    return bad


def check_variant_empty(name: str, env) -> list:
    """G. 원천 변이(shape_variants, 키에 `@`) 예시의 성공 0행 = 드리프트 의심."""
    if "@" not in name or not isinstance(env, dict) or env.get("items") != []:
        return []
    notes = env.get("empty_notes") or []
    return [("G", "원천 변이 예시가 0행 — 원천 구조·동작 변경 의심"
             + (f" (empty_notes: {str(notes[0])[:60]})" if notes else ""))]


def check_envelope(name: str, declared: str, value) -> list:
    """이미 성공을 확인한 업무 값: 선언된 모양과 좌표만 검사한다."""
    out = []
    if declared == "items":
        rows = item_rows(value)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            out.append(("B", "items 선언은 List 또는 Record.items의 Record 목록이어야 합니다."))
    rows = item_rows(value)
    if rows is not None:
        bad = coord_contract_violations(rows)
        if bad:
            out.append(("F", f"좌표류 칸이 있는데 lat/lng 숫자 없음 — 행 {bad[:5]}"))
    return out


PARALLEL_PROBES = [
    ("병렬_한가지실패", '[1] & (1 / 0)', {"success": False, "code": "VALUE"}),
    ("병렬_전가지실패", '(1 / 0) & (2 / 0)', {"success": False, "code": "VALUE"}),
    ("병렬_정상", '[1] & [2]', {"success": True, "value": [[1], [2]]}),
]


def check_parallel_envelope(env, expect):
    if not isinstance(env, dict) or env.get("executed") is not True:
        return [("E", "병렬 프로그램이 실행되지 않았습니다.")]
    if env.get("success") is not expect["success"]:
        return [("E", f"success={env.get('success')} (기대 {expect['success']})")]
    if expect["success"]:
        try:
            return [] if final_of(env) == expect["value"] else [("E", "병렬 결과 순서·구조 불일치")]
        except ValueError as exc:
            return [("E", str(exc))]
    diagnostic = env.get("diagnostic") or {}
    return [] if diagnostic.get("code") == expect["code"] else [("E", "병렬 실패 진단 불일치")]


# ── D. 정적 정보: 텍스트 계약(접두) 실패 return 자리 ────────────────────────────────────────────
BARE_ERROR_RETURN_RE = re.compile(r"""return\s+f?["'](Error|오류|에러|실패)\s*[:：]""")


def static_bare_error_returns() -> dict:
    """텍스트 계약(접두) 실패 return 자리 — 패키지 핸들러만(backend 의 system_ai_tools·auto_response
    문자열 return 은 IBL 봉투가 아니라 시스템 AI 도구 루프/자동응답의 텍스트라 우주 밖)."""
    hits = {}
    for base in (ROOT / "data" / "packages" / "installed",):
        for p in base.rglob("*.py"):
            if p.name.startswith("test_") or "__pycache__" in p.parts:
                continue
            try:
                n = len(BARE_ERROR_RETURN_RE.findall(p.read_text(encoding="utf-8")))
            except Exception:
                continue
            if n:
                hits[str(p.relative_to(ROOT))] = n
    return hits


def _try(code):
    try:
        result = _execute(code)
        final_of(result)
        return result, None
    except Exception as e:
        return None, e


def main(argv) -> int:
    strict = "--strict" in argv
    static_only = "--static-only" in argv
    violations, failed, retried, checked = [], [], [], 0
    if not static_only:
        decl, decl_op, default_op, _, _ = _load_declarations()
        fx = json.load(open(ROOT / "data" / "ibl_fixtures.json", encoding="utf-8"))
        universe = {**fx["fixtures"], **(fx.get("shape_variants") or {})}   # 변이 축도 같은 불변식
        for name, code in sorted(universe.items()):
            declared, _lvl = _declared_of(name.split("@", 1)[0], decl, decl_op, default_op, code)
            resp, err = _try(code)
            probs = [] if err else check_envelope(name, declared, final_of(resp))
            if err is not None or probs:
                resp2, err2 = _try(code)            # 외부 API 블립 1회 흡수 (returns_drift 선례)
                if err2 is None:
                    probs2 = check_envelope(name, declared, final_of(resp2))
                    if err is not None or len(probs2) < len(probs):
                        retried.append(name)
                    resp, err, probs = resp2, None, probs2
            if err is not None:
                failed.append((name, str(err)[:80]))
                continue
            checked += 1
            probs = probs + check_variant_empty(name, final_of(resp))
            for inv, why in probs:
                violations.append({"name": name, "inv": inv, "why": why})
        # E. 병렬 봉투 — fixture 우주(단일 액션) 밖이라 따로 돈다 (B24-1)
        for pname, pcode, expect in PARALLEL_PROBES:
            try:
                resp, err = _execute(pcode), None
            except Exception as exc:
                resp, err = None, exc
            if err is not None:
                failed.append((pname, str(err)[:80]))
                continue
            checked += 1
            for inv, why in check_parallel_envelope(resp, expect):
                violations.append({"name": pname, "inv": inv, "why": why})
    static = static_bare_error_returns()

    print("==== 정직성 불변식 스윕 ====")
    if not static_only:
        print(f"실측 {checked} · 위반 {len(violations)} · 실행 불능 {len(failed)}"
              + (f" · 블립 재시도 {len(retried)}건" if retried else ""))
        for inv, label in (("B", "통화 부재(선언 items 인데 items 없음)"),
                           ("F", "좌표 칸 계약(좌표류 칸이 있으면 lat/lng 숫자)"),
                           ("G", "원천 변이 0건(shape_variants 예시의 0행 = 드리프트 의심)"),
                           ("E", "병렬 봉투(분기 실패 미신고·전 가지 실패를 성공으로)")):
            rows = [v for v in violations if v["inv"] == inv]
            print(f"\n[{inv}] {label} — {len(rows)}건")
            for v in rows:
                print(f"  ‼️ {v['name']}: {v['why']}")
        if failed:
            print(f"\n실행 불능 {len(failed)}건 (판정 아님):")
            for name, why in failed[:8]:
                print(f"  · {name}: {why}")
    print(f"\n[D] 텍스트 계약(접두) 실패 return {sum(static.values())}자리 / {len(static)}파일 (정보 — 부채 아님)")
    for p, n in sorted(static.items(), key=lambda kv: -kv[1]):
        print(f"  · {p}: {n}")

    print("@@HONESTY@@ " + json.dumps({
        "checked": checked, "failed": len(failed), "retried": retried,
        "violations": violations,
        "prefix_contract_sites": sum(static.values()),
    }, ensure_ascii=False))
    return 1 if (strict and (violations or failed or (not static_only and not checked))) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
