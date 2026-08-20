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
    op_values = {}     # "node:action" -> [op, ...] (ops.values 키 — op 축 우주 열거용)
    for node, nd in (reg.get("nodes") or {}).items():
        for act, ad in (nd.get("actions") or {}).items():
            decl[f"{node}:{act}"] = ad.get("returns") or "?"
            ops = ad.get("ops") or {}
            if ops.get("default"):
                default_op[f"{node}:{act}"] = ops["default"]
            for op, rv in (ops.get("returns") or {}).items():
                decl_op[f"{node}:{act}#{op}"] = rv
            vals = list((ops.get("values") or {}).keys())
            if vals:
                op_values[f"{node}:{act}"] = vals
    return decl, decl_op, default_op, op_values


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
    # agent_id="__self_check__" — 이 순찰의 실행이 action_health 에 source='self_check' 로
    # 기록되게 (ibl_health_check 선례). 이게 없던 동안 주 1회 126 fixture 가 'usage' 로
    # 적재돼 §1D 실사용 실패율을 오염시켰다(2026-08-21 ③ 조사 — 배터리·순찰이 실사용
    # 계수에 섞이는 부류).
    req = urllib.request.Request(
        f"{API}/ibl/execute",
        data=json.dumps({"code": code, "project_id": "정보센터",
                         "agent_id": "__self_check__"}).encode(),
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


CURRENCY = {"items", "table", "blocks"}


def _is_drift(declared, actual):
    if declared in ("scalar", "effect") and actual in CURRENCY:
        return "over"
    if declared in ("items", "table") and actual == "scalar":
        return "under"
    return None


def _try_once(code):
    """1회 실행 → (shape, items_n, error). error 는 실행 불능(HTTP/타임아웃)만."""
    try:
        env = _final_envelope(_execute(code))
    except Exception as e:
        return None, 0, e
    n = len(env.get("items") or []) if isinstance(env, dict) else 0
    return _actual_shape(env), n, None


def _op_axis_report(decl, decl_op, default_op, op_values, fixtures, exempt):
    """op 축 검증 커버리지 — 통화(items/table)를 약속한 op 경로가 fixture·exempt 어느
    쪽에도 없으면 '조용한 미검증'이다 (2026-08-21 ③ 조사: 이 신고가 없던 동안
    '전체 정합'이 op 축 사각을 가렸다). fixture 를 못 다는 op 은 exempt 로 사유를
    명시할 것 — 침묵 아닌 자백."""
    total = covered = exempted = 0
    unverified = []
    for name, vals in op_values.items():
        plain = fixtures.get(name)
        plain_op = None
        if plain:
            m = _OP_IN_CODE.search(plain)
            plain_op = m.group(1) if m else default_op.get(name)
        for op in vals:
            r = decl_op.get(f"{name}#{op}", decl.get(name))
            if r not in ("items", "table"):
                continue
            total += 1
            k = f"{name}#{op}"
            if k in fixtures or op == plain_op:
                covered += 1
            elif k in exempt or name in exempt:
                exempted += 1
            else:
                unverified.append(k)
    return total, covered, exempted, unverified


def main():
    decl, decl_op, default_op, op_values = _load_declarations()
    fx = json.load(open(ROOT / "data" / "ibl_fixtures.json"))
    fixtures, exempt = fx["fixtures"], fx.get("exempt") or {}
    rows, failed, retried = [], [], []
    for name, code in sorted(fixtures.items()):
        declared, level = _declared_of(name, decl, decl_op, default_op, code)
        actual, n, err = _try_once(code)
        if err is not None or _is_drift(declared, actual):
            # 외부 API 일시 블립 흡수 — 1회 재시도 (골든 파이프 §1C 선례. 2026-08-20
            # sense:classic 실측: 같은 코드·fixture 가 1차 [B]→2차 정합 = 주 1회 거짓
            # 깃발. 진짜 회귀는 결정론적이라 재시도로 안 사라진다).
            a2, n2, e2 = _try_once(code)
            if e2 is None:
                if err is not None or not _is_drift(declared, a2):
                    retried.append(name)
                actual, n, err = a2, n2, None
        if err is not None:
            failed.append((name, str(err)[:80]))
            continue
        rows.append((name, declared, level, actual, n))

    over = [r for r in rows if r[1] in ("scalar", "effect") and r[3] in CURRENCY]
    under = [r for r in rows if r[1] in ("items", "table") and r[3] == "scalar"]
    exact = [r for r in rows if r not in over and r not in under]
    op_total, op_covered, op_exempt, op_unverified = _op_axis_report(
        decl, decl_op, default_op, op_values, fixtures, exempt)

    print("==== returns 드리프트 스윕 ====")
    print(f"실측 {len(rows)} · 선언과 정합 {len(exact)} · 실행 불능 {len(failed)}"
          + (f" · 블립 재시도로 흡수 {len(retried)}건({', '.join(retried[:5])})" if retried else ""))
    print(f"op 축 커버리지: 통화 약속 op 경로 {op_total} = fixture {op_covered} + exempt {op_exempt}"
          f" + 미검증 {len(op_unverified)}")
    if op_unverified:
        print("  ⚠️ 조용한 미검증 op 경로 (fixture 또는 exempt+사유를 소스 yaml 에 달 것):")
        for k in op_unverified[:20]:
            print(f"    · {k}")
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
        "retried": retried,
        "op_paths": op_total, "op_covered": op_covered, "op_exempt": op_exempt,
        "op_unverified": op_unverified,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
