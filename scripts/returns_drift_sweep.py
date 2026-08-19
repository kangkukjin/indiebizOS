#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""returns 선언 ↔ 실측 출력 드리프트 스윕 (2026-08-19 조사).

질문: `returns: scalar/effect` 로 선언된 어휘 중 실제로는 items(통화)를 내는 것이 있는가.
드리프트의 비용: ①건강 단언 사각(ibl_health_check 는 선언=items 인 것만 통화를 단언 —
스칼라 선언 어휘의 items 출력은 깨져도 순찰이 모른다) ②오류문 처방("returns 선언 확인")의
신뢰성 ③설계·판정 오도. 반대 방향(items 선언인데 스칼라 실측)은 더 나쁘다 — 약속 위반.

측정 우주 = data/ibl_fixtures.json (부작용 없는 행동 fixture). 선언 해소 = op 별
`ops.returns[op]` 우선, 없으면 액션 `returns` (ibl_ops.returns_of 와 같은 규칙).
판정만 하고 고치지 않는다.

사용: .venv/bin/python scripts/returns_drift_sweep.py
"""
import json
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8765"


def _load_declarations():
    reg = yaml.safe_load(open(ROOT / "data" / "ibl_nodes.yaml"))
    decl = {}          # "node:action" -> returns (액션 레벨)
    decl_op = {}       # "node:action#op" -> returns (op 레벨)
    default_op = {}    # "node:action" -> ops.default
    for node, nd in (reg.get("nodes") or {}).items():
        for act, ad in (nd.get("actions") or {}).items():
            decl[f"{node}:{act}"] = ad.get("returns") or "?"
            ops = ad.get("ops") or {}
            if ops.get("default"):
                default_op[f"{node}:{act}"] = ops["default"]
            for op, rv in (ops.get("returns") or {}).items():
                decl_op[f"{node}:{act}#{op}"] = rv
    return decl, decl_op, default_op


import re as _re

_OP_IN_CODE = _re.compile(r'''\bop:\s*["'](\w+)["']''')


def _declared_of(name, decl, decl_op, default_op, code=""):
    """이 호출의 통화 선언 — op 별 선언 우선, 없으면 액션 (ibl_ops.returns_of 규칙).

    ★해소 순서 (오탐 2건의 교훈, 2026-08-19):
      ①fixture 키의 #op ②**fixture 코드가 명시한 op**(키에 #op 이 없어도 코드가
      `op: "list"` 를 박아 두면 그 op 이 실행된다 — self:limb 오탐: 이름 기반
      default(issue=effect)로 읽어 items 방출을 드리프트로 오인) ③ops.default
      ④액션 returns (sense:stock 오탐: 기본 quote=items 를 액션 scalar 로 오인)."""
    if name in decl_op:
        return decl_op[name], "op"
    base = name.split("#")[0]
    if "#" not in name:
        m = _OP_IN_CODE.search(code or "")
        if m:
            # 코드가 op 을 명시 — 그 op 의 선언으로만 해소한다. op 레벨 선언이 없으면
            # 액션 returns 상속 (★ops.default 로 떨어지면 *다른 op* 의 선언을 읽는다
            # — self:limb 재오탐: op:"list" 명시인데 default(issue)=effect 로 오독).
            k = f"{base}#{m.group(1)}"
            if k in decl_op:
                return decl_op[k], "op-code"
            return decl.get(base, "?"), "action"
        if base in default_op:
            k = f"{base}#{default_op[base]}"
            if k in decl_op:
                return decl_op[k], "op-default"
    return decl.get(base, "?"), "action"


def _execute(code, timeout=60):
    req = urllib.request.Request(
        f"{API}/ibl/execute",
        data=json.dumps({"code": code, "project_id": "정보센터"}).encode(),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def _final_envelope(resp):
    d = resp.get("result", resp)
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except Exception:
            return None
    if isinstance(d, dict) and "final_result" in d:
        d = d["final_result"]
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except Exception:
            return None
    return d if isinstance(d, dict) else None


def _actual_shape(env):
    """실측 통화 모양: items / table / blocks / scalar(dict인데 통화 없음) / raw(비 dict)."""
    if env is None:
        return "raw"
    if isinstance(env.get("items"), list):
        return "items"
    t = env.get("table")
    if (isinstance(t, dict) and isinstance(t.get("rows"), list)) or (
            isinstance(env.get("rows"), list) and isinstance(env.get("columns"), list)):
        return "table"
    if isinstance(env.get("blocks"), list):
        return "blocks"
    return "scalar"


def main():
    decl, decl_op, default_op = _load_declarations()
    fixtures = json.load(open(ROOT / "data" / "ibl_fixtures.json"))["fixtures"]
    rows, failed = [], []
    for name, code in sorted(fixtures.items()):
        declared, level = _declared_of(name, decl, decl_op, default_op, code)
        try:
            env = _final_envelope(_execute(code))
        except Exception as e:
            failed.append((name, str(e)[:80]))
            continue
        actual = _actual_shape(env)
        # items 개수(빈 목록=통화 계약은 지킴)
        n = len(env.get("items") or []) if isinstance(env, dict) else 0
        rows.append((name, declared, level, actual, n))

    CURRENCY = {"items", "table", "blocks"}
    over = [r for r in rows if r[1] in ("scalar", "effect") and r[3] in CURRENCY]
    under = [r for r in rows if r[1] in ("items", "table") and r[3] == "scalar"]
    exact = [r for r in rows if r not in over and r not in under]

    print("==== returns 드리프트 스윕 ====")
    print(f"실측 {len(rows)} · 선언과 정합 {len(exact)} · 실행 불능 {len(failed)}")
    print(f"\n[A] 선언 scalar/effect 인데 통화 실측 (조합 가능한데 선언이 가림 — 건강 단언 사각) — {len(over)}건")
    for name, d, lvl, a, n in over:
        print(f"  🚩 {name}: 선언 {d}({lvl}) → 실측 {a}" + (f"[{n}행]" if a == "items" else ""))
    print(f"\n[B] 선언 items/table 인데 scalar 실측 (약속 위반 — 더 나쁨) — {len(under)}건")
    for name, d, lvl, a, n in under:
        print(f"  ‼️ {name}: 선언 {d}({lvl}) → 실측 {a}")
    if failed:
        print(f"\n실행 불능 {len(failed)}건 (판정 아님):")
        for name, why in failed[:8]:
            print(f"  · {name}: {why}")

    # 기계 판독 요약 (유지보수 번들 §9 소비 — ibl_health_check 의 @@HEALTH_JSON@@ 계약 선례)
    print("@@RETURNS_DRIFT@@ " + json.dumps({
        "checked": len(rows), "exact": len(exact), "failed": len(failed),
        "over": [r[0] for r in over], "under": [r[0] for r in under],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
