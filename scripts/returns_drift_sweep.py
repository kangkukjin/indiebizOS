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
import time
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
    variants = {}      # "node:action" -> {param=값: returns} (param-조건부 통화, B36-3)
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
            if isinstance(ad.get("returns_variants"), dict):
                variants[f"{node}:{act}"] = ad["returns_variants"]
    return decl, decl_op, default_op, op_values, variants


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
    """실측 통화 모양: items / table / blocks / scalar(dict인데 통화 없음) / raw(비 dict).

    ★2026-08-24: 바깥 세계가 죽은 것을 '약속 위반'으로 읽지 않는다. 외부 API 가
    타임아웃·오류를 내면 봉투에 통화가 없으니 옛 판정은 scalar 였고, 그러면 items 를
    약속한 액션이 매번 [B]('더 나쁨')로 신고됐다 — 실측 sense:book=data4library 30초
    타임아웃. **부재≠파손을 계측층에도 적용**: 오류 봉투는 모양이 아니라 '실행 불능'
    (failed)이다. 늑대를 외치는 관문은 다음 사람이 안 믿는다.
    """
    if env is None:
        return "raw"
    if env.get("error") and not (
            isinstance(env.get("items"), list) or isinstance(env.get("blocks"), list)
            or isinstance(env.get("table"), dict) or isinstance(env.get("rows"), list)):
        return "error"
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

# 차단기 쿨다운을 기다려 줄 상한 — 이보다 길면 기다리지 않고 '실행 불능'으로 적는다
# (순찰이 한 액션 때문에 몇 분씩 서 있으면 그것대로 규율이 깨진다).
# 실측 쿨다운은 90초까지 관측됐다(연속 3회 실패). 주 1회 순찰이 90초 서는 값은,
# 사람이 멀쩡한 API 를 유령 신고 때문에 파헤치는 20분보다 싸다.
_MAX_BREAKER_WAIT = 120


def _is_drift(declared, actual):
    if declared in ("scalar", "effect") and actual in CURRENCY:
        return "over"
    if declared in ("items", "table") and actual == "scalar":
        return "under"
    return None


def _try_once(code):
    """1회 실행 → (shape, items_n, error, blocked_for). error 는 실행 불능만.

    봉투 안의 오류(외부 API 다운 등)도 '실행 불능'으로 올린다 — 모양 판정 밖이다.
    blocked_for = 차단기(circuit breaker) 쿨다운 잔여 초 · 아니면 None.
    """
    try:
        env = _final_envelope(_execute(code))
    except Exception as e:
        return None, 0, e, None
    shape = _actual_shape(env)
    if shape == "error":
        blocked = env.get("retry_after_seconds") if env.get("blocked") else None
        return None, 0, RuntimeError(f"봉투 오류: {str(env.get('error'))[:120]}"), blocked
    n = len(env.get("items") or []) if isinstance(env, dict) else 0
    return shape, n, None, None


# ── 런타임 모양 실측 (action_health.shape, 2026-08-24 B36-3) ─────────────────────
# fixture 면제(하드웨어·유료 LLM·인자 의존)는 이 스윕의 측정 우주 밖이라 선언 드리프트가
# 영영 안 잡혔다(table:structure 실측 — 면제 = 측정 사각). ibl_engine 이 실행마다 봉투
# 모양을 action_health.shape 에 적으므로(판정기 = ibl_envelope.classify_currency 한 벌),
# 실사용에서 한 번이라도 돈 액션은 여기서 공짜로 대조된다 — 면제는 '합성 실행 면제'일 뿐
# '측정 면제'가 아니게 된다.
#
# 판정은 보수적이다: action_health 는 op·param 을 기록하지 않으므로, 허용 집합 =
# 액션 선언 ∪ 모든 op 선언 ∪ returns_variants(param-조건부 통화) 의 합집합. 이 합집합
# 밖의 모양이 성공 행에서 관측되면 위반이다.
_RUNTIME_OK = {
    "items": {"items"},
    "transform": {"items"},
    # scalar 와 effect 는 이 입도에서 구별 불가 — {success:true, lat:…} 같은 데이터 봉투도
    # 판정기는 "effect" 라 부른다(sense:here 실측). 런타임 축의 판정은 한 방향만 본다:
    # **통화(items)를 선언 없이 내는가 / 선언하고 안 내는가**. scalar↔effect 오류는
    # fixture 스윕(op 축 포함)의 몫이다.
    "scalar": {"dict", "text", "message", "effect"},
    "effect": {"effect", "dict", "message", "text"},
}


def _runtime_observations(days=60):
    """{node:action: {shape: count}} — 성공 행만, test/training 격리(B18-1 규율)."""
    import sqlite3
    db = ROOT / "data" / "world_pulse.db"
    if not db.exists():
        return {}
    out = {}
    try:
        conn = sqlite3.connect(str(db), timeout=5)
        cur = conn.execute(
            "SELECT node, action, shape, COUNT(*) FROM action_health "
            "WHERE success=1 AND shape IS NOT NULL "
            "AND source NOT IN ('test','training') "
            "AND timestamp >= datetime('now', ?) "
            "GROUP BY node, action, shape", (f"-{days} days",))
        for node, action, shape, cnt in cur.fetchall():
            out.setdefault(f"{node}:{action}", {})[shape] = cnt
        conn.close()
    except Exception:
        return {}
    return out


def _allowed_shapes(act, decl, decl_op, variants):
    allowed = set(_RUNTIME_OK.get(decl.get(act, "?"), set()))
    for k, rv in decl_op.items():
        if k.split("#", 1)[0] == act:
            allowed |= _RUNTIME_OK.get(rv, set())
    for rv in (variants.get(act) or {}).values():
        allowed |= _RUNTIME_OK.get(rv, set())
    return allowed


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
    decl, decl_op, default_op, op_values, variants = _load_declarations()
    fx = json.load(open(ROOT / "data" / "ibl_fixtures.json"))
    fixtures, exempt = fx["fixtures"], fx.get("exempt") or {}
    rows, failed, retried = [], [], []
    _waited = set()   # 차단기 대기는 액션당 1회 — 순찰이 쿨다운마다 멈추지 않게
    for name, code in sorted(fixtures.items()):
        declared, level = _declared_of(name, decl, decl_op, default_op, code)
        actual, n, err, blocked = _try_once(code)
        if blocked is not None:
            # ★2026-08-24: 차단기 연쇄를 독립 실패로 세지 않는다. 한 액션이 한 번
            # 느려서 차단되면, 같은 액션의 **다른 op fixture 들이 API 를 부르지도 못한 채**
            # 줄줄이 실패로 적힌다(실측: sense:book 1건 타임아웃 → book·#codes·#popular·
            # #recommended·#trending 5건 신고. 바깥은 멀쩡했다 — 0.9초에 20,607건).
            # 즉시 재시도는 쿨다운이 안 지나 무의미하므로 **한 액션당 한 번만** 기다린다.
            act = name.split("#", 1)[0]
            if act not in _waited and blocked <= _MAX_BREAKER_WAIT:
                _waited.add(act)
                print(f"  · {act} 차단기 대기 {blocked}s (연쇄 오탐 방지)")
                time.sleep(blocked + 1)
                actual, n, err, blocked = _try_once(code)
        if err is not None or _is_drift(declared, actual):
            # 외부 API 일시 블립 흡수 — 1회 재시도 (골든 파이프 §1C 선례. 2026-08-20
            # sense:classic 실측: 같은 코드·fixture 가 1차 [B]→2차 정합 = 주 1회 거짓
            # 깃발. 진짜 회귀는 결정론적이라 재시도로 안 사라진다).
            a2, n2, e2, _b2 = _try_once(code)
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

    # ── 런타임 모양 실측 — 면제=측정 사각을 닫는 눈 (2026-08-24 B36-3) ──
    runtime = _runtime_observations()
    exempt_actions = sorted({str(k).split("#", 1)[0] for k in exempt})
    rt_blind = [a for a in exempt_actions if not runtime.get(a)]
    rt_flags = []
    for act, shapes in sorted(runtime.items()):
        if act not in decl:
            continue   # 은퇴·미지 어휘의 잔재 행
        bad = {s: c for s, c in shapes.items()
               if s not in _allowed_shapes(act, decl, decl_op, variants)}
        if bad:
            rt_flags.append((act, decl.get(act), bad, shapes))
    print(f"\n런타임 모양 실측 (action_health 성공 행, 최근 60일): 관측 액션 {len(runtime)}개")
    print(f"  면제 액션 {len(exempt_actions)} 중 실측 있음 {len(exempt_actions) - len(rt_blind)}"
          f" · 실측 없는 사각 {len(rt_blind)}"
          + (f": {', '.join(rt_blind)}" if rt_blind else ""))
    if not runtime:
        print("  (아직 기록 없음 — shape 컬럼은 2026-08-24 부터 적재)")
    if rt_flags:
        print(f"  ‼️ 런타임 위반 {len(rt_flags)}건 — 선언에 없는 통화 모양이 실사용에서 관측:")
        for act, d, bad, shapes in rt_flags:
            print(f"     {act}: 선언 {d} · 위반 관측 {bad} (전체 {shapes})")

    # 기계 판독 요약 (유지보수 번들 §9 소비 — ibl_health_check 의 @@HEALTH_JSON@@ 계약 선례)
    print("@@RETURNS_DRIFT@@ " + json.dumps({
        "checked": len(rows), "exact": len(exact), "failed": len(failed),
        "over": [r[0] for r in over], "under": [r[0] for r in under],
        "retried": retried,
        "op_paths": op_total, "op_covered": op_covered, "op_exempt": op_exempt,
        "op_unverified": op_unverified,
        "runtime_actions": len(runtime),
        "runtime_flags": [f"{a}: {bad}" for a, _, bad, _ in rt_flags],
        "exempt_blind": rt_blind,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
