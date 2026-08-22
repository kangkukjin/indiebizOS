#!/usr/bin/env python3
"""seed_imagination_round_24.py — 24회차 시드 (2026-08-22).

★멱등: intent dedupe 로 두 번 돌려도 0건. 목적은 재실행이 아니라 **재현 가능한 출처**다.

무엇을 가르치는가 — 24회차 중점은 **가장 많이 쓰는 문법(`&` 병렬 18.7%)의 경계**였다:
  23회차가 *순차* 실패를 답사했고(try/catch·on_error·`??`·each 전부 모범), 24회차는 병렬로
  갔다. 교재 census 가 구멍을 정확히 가리켰다 — `&` 141건인데 **try 안 & 0 · each 중첩 0 ·
  괄호분기 1 · `$items` 7 · goal 4**. 아래 5건은 그 자리에서 **실행까지 통과한** 문형이다.

★**병렬 실패 문형은 여기 없다.** 24회차가 B24-1(병렬 분기 실패를 봉투가 안 셈)을 발견했고
  같은 날 수리했지만(branches_failed 승격 + 전 가지 실패 success:false + 이항 변환자 경고),
  그 수리는 **지연 적용**이라 시딩 시점 라이브가 아니었다. 20회차 규율('판정이 새로 참으로
  만든 문형만 가르친다')대로 적용·야생 검증 후 다음 회차에 올린다.

★검증: 5건 전건 /ibl/validate + 라이브 실행 통과 후 넣었다.

실행: .venv/bin/python3 scripts/seed_imagination_round_24.py   (★_load_model_sync 뒤 add, intent dedupe)
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    ("각각 찾아보고 그 안에서 또 각각 처리해줘",
     '[table:each]{items: [{"q": "AI"}, {"q": "반도체"}], do: "[sense:search]{source: \'ddg\', query: \'$it.q\'} >> [table:take]{n: 2} >> [table:each]{do: \\"[self:time]\\"}"}',
     "table,sense", "research", "고차,each중첩,적용,재귀깊이"),
    ("찾은 맛집들을 한 지도에 한꺼번에 찍어줘",
     '[sense:restaurant]{query: "평택 죽백동 맛집"} >> [table:take]{n: 3} >> [limbs:show_map]{markers: "$items"}',
     "sense,table,limbs", "places", "집합참조,items변수,지도,한번에"),
    ("두 곳을 같이 보되 통째로 안 되면 검색으로",
     '[try]{[sense:feed]{url: "https://news.hada.io/rss/news", limit: 3} & [sense:feed]{url: "https://www.pewresearch.org/feed/", limit: 3}}\n'
     '[catch]{[sense:search]{source: "ddg", query: "기술 뉴스"} >> [table:take]{n: 2}}',
     "sense,table", "research", "오류처리,try안병렬,catch,교차"),
    ("열이 다른 두 소스를 한 표로 이어붙여줘",
     '[sense:feed]{url: "https://news.hada.io/rss/news", limit: 2} & [sense:host]{op: "resources"} >> [table:union]',
     "sense,table", "system", "병렬,union,이질열,이항변환자"),
    ("코스피가 6900 아래로 내려가면 알려줘",
     '[goal: "코스피 하락 감시"]{every: "1h", max_rounds: 24, success_condition: "하락 시 알림 전송", strategy: [if: sense:stock{op: "quote", ticker: "^KS11"}.current_price < 6900]{[self:notify_user]{message: "코스피 6900 이탈"}}}',
     "self,sense", "invest", "시간,goal블록,조건,감시"),
]

if __name__ == "__main__":
    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단(★_index_batch 는 실패를 삼킨다)"
    import sqlite3
    root = os.path.join(os.path.dirname(__file__), "..")
    conn = sqlite3.connect(os.path.join(root, "data", "ibl_usage.db"))
    existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
    conn.close()
    batch = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2,
              "source": "manual_seed", "tags": t} for i, c, n, cat, t in NEW if i not in existing]
    print(f"시드 추가: {db.add_examples_batch(batch) if batch else 0}건 (중복 스킵 {len(NEW) - len(batch)}건)")
    dist_path = os.path.join(root, "data", "training", "ibl_distilled.json")
    with open(dist_path, encoding="utf-8") as f:
        dist = json.load(f)
    have = {d.get("intent") for d in dist}
    added = 0
    for i, c, n, cat, t in NEW:
        if i not in have:
            dist.append({"intent": i, "ibl_code": c, "nodes": n, "category": cat,
                         "difficulty": 2, "source": "manual_seed"})
            added += 1
    if added:
        with open(dist_path, "w", encoding="utf-8") as f:
            json.dump(dist, f, ensure_ascii=False, indent=2)
    print(f"ibl_distilled: +{added}건 → {len(dist)}건")
