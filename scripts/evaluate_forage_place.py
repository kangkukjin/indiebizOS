#!/usr/bin/env python3
"""포식 기억의 장소 찾기 평가 — 장소 @1·@3 (docs/FORAGE_MEMORY_AUDIT_2026_09_18.md §6).

포식 기억의 품질은 항목 순위가 아니라 "맞는 장소를 첫 번째로 짚는가"다(주소가 정해지면 그 장소의 전부가 오므로).
문항 = data/forage_surveys/_eval/place_cases.json (개인 경로가 들어 있어 git 밖): {"cases":[{"q": "...", "accept": ["<주소 접두|몸 이름>", ...]}]}
비교 = 글자 일치(옛 방식: 단언·끝 이름의 낱말 점수) 대 융합(의미+글자, 찾는 말 포함). 읽기 전용.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import forage_memory as FM  # noqa: E402
import tree_recall  # noqa: E402
from forage_recall_store import ForageStore  # noqa: E402

CASES = ROOT / "data" / "forage_surveys" / "_eval" / "place_cases.json"


def hit(pid: str, accept) -> bool:
    for a in accept:
        a = a.rstrip("/")
        if pid == a or pid.startswith(a + "/") or (a.startswith(pid.rstrip("/") + "/") and pid.count("/") >= 4):
            return True
    return False


def lexical_places(query: str):
    terms, grams = FM._query_terms(query)
    conn = FM._connect()
    try:
        rows = conn.execute("SELECT body, locus, claim FROM forage_map").fetchall()
    finally:
        conn.close()
    score = {}
    for r in rows:
        base = os.path.basename(FM._norm_locus(r["locus"])) if FM._is_tree(r["locus"]) else (r["locus"] or "")
        s = FM._score(r["claim"], terms, grams) + FM._score(base, terms, grams)
        if s:
            pid = FM.place_id(r["body"], r["locus"])
            score[pid] = max(score.get(pid, 0), s)
    return sorted(score, key=lambda p: -score[p])


def main():
    if not CASES.exists():
        print(f"문항 없음: {CASES}"); return 1
    cases = json.load(open(CASES, encoding="utf-8"))["cases"]
    store = ForageStore()
    tally = {"글자 일치": [0, 0], "융합": [0, 0]}
    misses = []
    for c in cases:
        orders = {"글자 일치": lexical_places(c["q"]),
                  "융합": tree_recall.search(store, c["q"], limit=5, min_sim=FM._PLACE_MIN_SIM)["ids"]}
        for name, order in orders.items():
            tally[name][0] += bool(order[:1] and hit(order[0], c["accept"]))
            tally[name][1] += any(hit(p, c["accept"]) for p in order[:3])
        if not (orders["융합"][:1] and hit(orders["융합"][0], c["accept"])):
            misses.append((c["q"], orders["융합"][:3]))
    n = len(cases)
    cued = sum(1 for it in store.items() if it.cues)
    print(f"장소 {len(store.items())}곳(찾는 말 있는 곳 {cued}) · 문항 {n}")
    for name, (a, b) in tally.items():
        print(f"  {name:6s}  장소 @1 {a}/{n} ({a * 100 // n}%)  @3 {b}/{n}")
    for q, top in misses:
        print(f"  ✗ {q} → {[p[-48:] for p in top]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
