#!/usr/bin/env python3
"""seed_imagination_round_25.py - 25회차 시드 (2026-08-23).

멱등: intent dedupe 로 두 번 돌려도 0건. 목적은 재실행이 아니라 재현 가능한 출처다.

무엇을 가르치는가 - 25회차 중점은 **분기 문법의 미답 가지**였다. 전 코퍼스 3,573 문장을
census 하니 `if` 는 32건인데 `else if` 0 · `??` 3단 0 · `case` 3 · 괄호분기 3 ·
블록-인-파이프 3 · `spill` 3 · `reduce` 8 · 식 할당 7. 몸통만 밟혀 있고 가지는 처녀지였다.
아래 8건은 그 자리에서 **라이브 실행까지 통과한** 문형이다.

★B25-1 이 새로 참으로 만든 문형은 여기 없다. 25회차가 발견한 B25-1(조건 좌변의 소스
  참조가 리스트 인덱스 경로를 못 넘음)을 같은 날 수리했지만, 그 수리는 backend/*.py 가
  끼어 **지연 적용**이라 시딩 시점 라이브가 아니었다. 20회차 규율('판정이 새로 참으로
  만든 문형만 가르친다')대로 적용·야생 검증 후 다음 회차에 올린다. 보류분 2건:
     [if: sense:weather{city: "청주"}.items.0.max_temp > 30]{...}[else]{...}
     [case: sense:weather{city: "청주"}.items.0.max_temp]{"30~45": ..., default: ...}

실행: .venv/bin/python3 scripts/seed_imagination_round_25.py
"""
import sys, os, json
from pathlib import Path

# 격리 사본(.worktrees/...)에서 돌더라도 해마 원장은 라이브 하나뿐이다 - 라이브 루트로 고정.
ROOT = Path(__file__).resolve().parents[1]
if ".worktrees" in ROOT.parts:
    ROOT = Path(*ROOT.parts[:ROOT.parts.index(".worktrees")])
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("INDIEBIZ_BASE_PATH", str(ROOT))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    ("CPU 높으면 알려주고 아니면 메모리도 확인해줘",
     '[if: sense:host{op: "status"}.cpu_percent > 80]{[self:notify_user]{message: "CPU 과부하"}}\n'
     '[else if: sense:host{op: "status"}.memory_percent > 70]{[self:notify_user]{message: "메모리 압박"}}\n'
     '[else]{[self:time]}',
     "self,sense", "system", "조건,elseif,3단분기,자기수용감각"),
    ("그 종목 시세 안 나오면 다른 걸로라도 찾아줘",
     '[sense:stock]{op: "quote", ticker: "NOSUCHTICKER123"} ?? [sense:stock]{op: "quote", ticker: "ALSOBAD456"} ?? [sense:search]{source: "naver", query: "코스피 지수"}',
     "sense", "invest", "폴백,3단연쇄,조회"),
    ("시세가 안 되면 검색해서 위에서 두 개만",
     '[sense:stock]{op: "quote", ticker: "BADTICKER999"} ?? ([sense:search]{source: "naver", query: "코스피 지수"} >> [table:take]{n: 2})',
     "sense,table", "invest", "폴백,괄호분기,파이프가지"),
    ("검색 결과 많으면 다섯 개, 적으면 두 개만 추려줘",
     '[sense:book]{op: "search", query: "인공지능"} >> [if: count($items) > 10]{[table:take]{n: 5}} [else]{[table:take]{n: 2}} >> [table:select]{columns: ["bookname", "authors", "publication_year"]}',
     "sense,table", "research", "블록인파이프,조건,items변수,투영"),
    ("흥덕구 아파트 실거래 열 건 금액 다 합치면",
     '[sense:realty]{source: "molit", region: "청주시 흥덕구", type: "apt", deal: "trade"} >> [table:take]{n: 10} >> [table:reduce]{init: 0, step: "acc + 거래금액", as: "총거래액"}',
     "sense,table", "realty", "고차,reduce,누적,합계"),
    ("그 평균도 계산해서 알려줘",
     '$합 = [sense:realty]{source: "molit", region: "청주시 흥덕구", type: "apt", deal: "trade"} >> [table:take]{n: 10} >> [table:reduce]{init: 0, step: "acc + 거래금액", as: "총거래액"}\n'
     '$평균 = $합.value / 10\n'
     '[self:notify_user]{message: "흥덕구 평균 $평균 만원"}',
     "sense,table,self", "realty", "식할당,스칼라연산,변수치환,발신"),
    ("결과는 파일로 빼두고 앞부분만 보여줘",
     '[sense:book]{op: "search", query: "부동산"} >> [self:write]{path: "outputs/책검색.json", spill: true} >> [table:take]{n: 2} >> [table:select]{columns: ["bookname"]}',
     "sense,self,table", "research", "축적,spill,봉투다이어트,투명해소"),
    ("이 피드에 새 글 올라온 것만",
     '[sense:feed]{url: "https://news.hada.io/rss/news", limit: 5} >> [table:since]{key: "긱뉴스"}',
     "sense,table", "research", "시간,검침,since,감시"),
]

if __name__ == "__main__":
    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패 - 시딩 중단(_index_batch 는 실패를 삼킨다)"
    import sqlite3
    conn = sqlite3.connect(str(ROOT / "data" / "ibl_usage.db"))
    existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
    conn.close()
    batch = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2,
              "source": "manual_seed", "tags": t} for i, c, n, cat, t in NEW if i not in existing]
    print(f"시드 추가: {db.add_examples_batch(batch) if batch else 0}건 (중복 스킵 {len(NEW) - len(batch)}건)")
    dist_path = ROOT / "data" / "training" / "ibl_distilled.json"
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
    print(f"ibl_distilled: +{added}건 -> {len(dist)}건")
