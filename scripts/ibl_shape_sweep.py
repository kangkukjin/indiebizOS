#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""반환 모양(열 이름) 관측 스윕 — 카탈로그가 "무엇을 돌려주는지"까지 말하게 한다 (2026-08-21).

왜: IBL 조합의 가장 큰 구조적 한계는 *뒷문장을 쓰려면 앞문장의 반환 모양을 봐야 한다*는 것이다.
`>> [table:filter]{where: "연도 == '2024'"}` 가 열 이름을 몰라 실패하면(ep1325) 모델은 한 번
돌려 보고 다시 쓴다 — 최소 2왕복. 카탈로그의 `returns: items` 는 "표다"까지만 말한다.
이 스윕은 부작용 없는 fixture 우주(data/ibl_fixtures.json)를 실행해 실측 열 이름을
`data/ibl_return_shapes.json` 에 적고, ibl_access 가 카탈로그 줄에 ⟨열: …⟩ 로 붙인다.

★변이 축(2026-08-22, F20-1): 색인 키는 `node:action[#op]` 인데 반환 열이 **param 으로**
갈리는 액션이 있다([sense:realty] 의 source=molit/naver/zigbang). 그런 액션은 자기
정의에 `shape_variants: {param=값: '<fixture 코드>'}` 를 선언하고, 여기서 함께 관측해
`node:action@param=값` 키로 적는다 — 카탈로그가 변이별로 열을 말한다.
열 이름은 세계의 명사(입력·외부 API 에 따라 변함)라 src yaml 에 손으로 적지 않고 **관측 데이터**로 둔다.

★스칼라·효과 축(2026-09-06, 55회차 F55-1): 옛 스윕은 items/table 만 적어 카탈로그가 122건 전부
items 였고 engines 는 0건이었다 — `$변수.경로` 로 스칼라 결과(arch_report 의 floors·grand_total,
write 의 path)를 뒷문장에 쓰려면 매번 한 번 돌려 눈으로 읽어야 했다. 이제 통화가 아닌 성공
봉투도 `kind: scalar` 로 **최상위 키(+dict 한 겹·배열 원소 한 겹)** 를 적고, 카탈로그는 ⟨키: …⟩ 로
싣는다(⟨열⟩은 통화, ⟨키⟩는 봉투 — 정적 검사기는 ⟨키⟩를 열로 쓰지 않는다).
fixture 가 없는(exempt) 액션은 합성 실행이 불가하므로 **실사용 원장**에서 수확한다 —
`action_health.keys`(엔진이 성공 봉투마다 공짜로 적는 키 목록)를 `--from-health` 가 읽어
fixture 관측이 없는 액션에 한해 `source: usage` 로 적는다(fixture 관측이 있으면 그것이 이긴다).
사용: .venv/bin/python scripts/ibl_shape_sweep.py [--only node:action] [--from-health]   (백엔드 8765 필요; --from-health 만이면 불필요)
"""
import json, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8765"
OUT = ROOT / "data" / "ibl_return_shapes.json"
MAX_KEYS = 10


def _execute(code, timeout=90):
    req = urllib.request.Request(
        f"{API}/ibl/execute",
        data=json.dumps({"code": code, "project_id": "정보센터", "agent_id": "__self_check__"}).encode(),
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


def _shape(env):
    """실측 모양 → (kind, keys). items=첫 dict 행들의 키 합집합(등장 순), table=columns."""
    if not isinstance(env, dict):
        return None, []
    items = env.get("items")
    if isinstance(items, list):
        keys = []
        for it in items[:5]:
            if isinstance(it, dict):
                for k in it.keys():
                    if k not in keys and not str(k).startswith("_"):
                        keys.append(str(k))
        return "items", keys[:MAX_KEYS]
    t = env.get("table")
    if isinstance(t, dict) and isinstance(t.get("columns"), list):
        return "table", [str(c) for c in t["columns"]][:MAX_KEYS]
    if isinstance(env.get("columns"), list) and isinstance(env.get("rows"), list):
        return "table", [str(c) for c in env["columns"]][:MAX_KEYS]
    if env.get("success") is False or (env.get("error") and env.get("success") is not True):
        return None, []          # 실패 봉투의 키(error)는 모양이 아니다 — main 이 실패로 센다
    keys = scalar_keys(env)
    return ("scalar", keys) if keys else (None, [])


def scalar_keys(env: dict, limit: int = MAX_KEYS + 2) -> list:
    """통화가 아닌 성공 봉투의 키 — 최상위(내부 표지 `_…`·success 제외) + dict 값은 `k.sub` 한 겹,
    dict 배열은 `k[].sub` 한 겹. 순서 = 등장 순(모델이 읽는 순)."""
    out = []
    for k, v in env.items():
        k = str(k)
        if k.startswith("_") or k == "success":
            continue
        out.append(k)
        if isinstance(v, dict):
            for sk in list(v.keys())[:4]:
                if not str(sk).startswith("_"):
                    out.append(f"{k}.{sk}")
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            for sk in list(v[0].keys())[:4]:
                if not str(sk).startswith("_"):
                    out.append(f"{k}[].{sk}")
    return out[:limit]


def harvest_from_health(shapes: dict, root: Path = ROOT) -> int:
    """실사용 원장 action_health.keys → fixture 관측이 없는 액션의 ⟨키⟩ (source: usage). 반환=적은 수."""
    import sqlite3
    db = root / "data" / "world_pulse.db"   # = datastore.pulse_db.CONSCIOUSNESS_DB_PATH
    if not db.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db))
        cols = {r[1] for r in conn.execute("PRAGMA table_info(action_health)")}
        if "keys" not in cols:
            return 0
        rows = conn.execute(
            "SELECT node, action, keys, shape, timestamp FROM action_health "
            "WHERE success=1 AND keys IS NOT NULL AND keys != '' ORDER BY timestamp DESC").fetchall()
    except Exception:
        return 0
    n = 0
    seen = set()
    for node, action, keys_json, shape, ts in rows:
        key = f"{node}:{action}"
        if key in seen:
            continue
        seen.add(key)
        cur = shapes.get(key)
        if cur and cur.get("source", "fixture") == "fixture":
            continue  # fixture 관측이 정본
        try:
            keys = json.loads(keys_json)
        except Exception:
            continue
        if not isinstance(keys, list) or not keys:
            continue
        shapes[key] = {"kind": "scalar" if shape not in ("items", "table") else shape,
                       "keys": [str(k) for k in keys][:MAX_KEYS + 2],
                       "observed": str(ts)[:10], "source": "usage"}
        n += 1
    return n


def main():
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    fx = json.load(open(ROOT / "data" / "ibl_fixtures.json", encoding="utf-8"))
    # ★F20-1 (2026-08-22): 변이 축 합류 — 반환 열이 op 이 아니라 param 으로 갈리는
    # 액션(`shape_variants:` 선언)의 변이도 관측한다. 키 = `node:action@param=값`.
    # 건강검진·통화 스윕은 `fixtures` 만 읽으므로 그 측정 우주는 그대로다.
    fixtures = {**fx["fixtures"], **(fx.get("shape_variants") or {})}
    prev = {}
    if OUT.exists():
        try:
            prev = json.load(open(OUT, encoding="utf-8")).get("shapes", {})
        except Exception:
            prev = {}
    shapes = dict(prev)
    ok = fail = skip = 0
    if "--from-health" in sys.argv and "--only" not in sys.argv:
        harvested = harvest_from_health(shapes)
        print(f"  실사용 원장 수확: {harvested}건 (fixture 미관측 액션의 ⟨키⟩, source=usage)")
        if "--health-only" in sys.argv:
            fixtures = {}
    for key, code in sorted(fixtures.items()):
        if only and not key.startswith(only):
            continue
        try:
            env = _final_envelope(_execute(code))
        except Exception as e:
            fail += 1
            print(f"  ✗ {key}: 전송 실패 {e}")
            continue
        if env is None or env.get("success") is False or (env.get("error") and env.get("success") is not True):
            fail += 1
            print(f"  ✗ {key}: {str((env or {}).get('error'))[:80]}")
            continue
        kind, keys = _shape(env)
        if not kind or not keys:
            skip += 1
            continue
        shapes[key] = {"kind": kind, "keys": keys, "observed": time.strftime("%Y-%m-%d"), "source": "fixture"}
        ok += 1
        print(f"  ✓ {key}: {kind} {keys}")
    OUT.write_text(json.dumps({
        "_comment": "GENERATED by scripts/ibl_shape_sweep.py — fixture 실측 반환 열(kind items/table=⟨열⟩) + "
                    "스칼라·효과 봉투의 키(kind scalar=⟨키⟩, 2026-09-06; source usage=실사용 원장 수확). 직접 수정 금지. "
                    "ibl_access 가 카탈로그 줄에 붙인다. 이름은 관측 데이터(세계의 명사).",
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "shapes": shapes,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n관측 {ok} · 통화 아님 {skip} · 실패 {fail} → {OUT} (총 {len(shapes)})")


if __name__ == "__main__":
    main()
