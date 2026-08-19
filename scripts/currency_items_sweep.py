#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""통화(items) 병기 준수 스윕 — V13-1 부류의 전수 측정 (2026-08-19 상상훈련 13회차 판정).

부류: 결과 봉투에 dict 목록이 다른 키(goals·volumes …) 아래 있으면서 items 병기가
없는 생산자 — 그 뒤에 어떤 table 변환자도 붙지 못한다(goal list·storage volumes 실측).

측정 우주 = data/ibl_fixtures.json 의 행동 fixture(부작용 없는 코드, 건강 순찰이 매일
도는 것과 같은 집합). 판정만 하고 고치지 않는다 — 깃발은 사람/대장장이의 입력.

사용: .venv/bin/python scripts/currency_items_sweep.py [--limit N]
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8765"


def _execute(code: str, timeout: int = 60):
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


def _dict_list_keys(env: dict):
    """items 아닌 키 아래의 dict 목록(1개 이상) — 병기 누락 후보."""
    hits = []
    for k, v in env.items():
        if k in ("items", "results", "steps") or k.startswith("_"):
            continue
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            hits.append((k, len(v)))
    return hits


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    fixtures = json.load(open(ROOT / "data" / "ibl_fixtures.json"))["fixtures"]
    flagged, ok, failed = [], 0, []
    for i, (name, code) in enumerate(sorted(fixtures.items())):
        if limit and i >= limit:
            break
        try:
            resp = _execute(code)
        except Exception as e:
            failed.append((name, f"실행 불능: {str(e)[:80]}"))
            continue
        env = _final_envelope(resp)
        if env is None:
            ok += 1  # 문자열/스칼라 통화 — 이 부류 판정 대상 아님
            continue
        has_items = isinstance(env.get("items"), list)
        hits = _dict_list_keys(env)
        if hits and not has_items:
            flagged.append((name, hits))
            print(f"  🚩 {name}: items 없음, dict 목록 키 = {hits}")
        else:
            ok += 1
    print("\n==== 통화 병기 스윕 결과 ====")
    print(f"검사 {ok + len(flagged) + len(failed)} · 준수 {ok} · 🚩 병기 누락 {len(flagged)} · 실행 불능 {len(failed)}")
    for name, hits in flagged:
        print(f"  🚩 {name}: {hits}")
    if failed:
        print("  (실행 불능은 판정 아님 — 픽스처·환경 문제)")
        for name, why in failed[:10]:
            print(f"    · {name}: {why}")


if __name__ == "__main__":
    main()
