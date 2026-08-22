#!/usr/bin/env python3
"""seed_imagination_round_23.py — 23회차 시드 (2026-08-22).

★멱등: intent dedupe 로 두 번 돌려도 0건이 된다. 목적은 재실행이 아니라 **재현 가능한 출처**다.

무엇을 가르치는가 — 23회차 중점은 **실패 경로**였다:
  22회차가 M3(오류 처리)·M4(반복)를 처음 돌렸지만 전부 *행복 경로*였다(try 몸통이 성공해
  [catch] 가 한 번도 안 돌았고, 요약이 안 죽어 [on_error: skip] 도 안 돌았다). 코퍼스 census 도
  같은 말을 했다 — resume 0 · halted 0 · condition_errors 0 · [catch] 2 (교재 3,558 중).
  그래서 23회차는 일부러 죽는 문장으로 실패 경로를 답사했고, 여기 8건은 그때 **실행까지
  통과한** 문형이다. 코퍼스가 안 가르치면 번역기도 안 쓴다 — 희소가 희소를 낳던 고리를 끊는다.

  ① 실패를 다루는 문형 4건 — try/catch · on_error skip · repeat until · each on_error
  ② 통화·산출 문형 3건 — struct(비정형→items) · structure→document · scalar 선언 액션의 정렬
  ③ 23회차가 **야생 검증한** 문형 1건 — `$return` 워크플로우.
     22회차 B22-1 수리(시그니처 = 사용 − 할당, 커밋 30ec862)가 새로 참으로 만든 문형이고,
     22회차엔 지연 적용 대기라 시드에서 뺐다가 23회차에 라이브 확인 후 올린다
     (20회차 규율 — '판정이 새로 참으로 만든 문형만 가르친다').

★B23-1(resume 침묵 무시) 수리는 **시드가 없다** — resume 은 IBL 코드가 아니라 도구
  파라미터라 문장으로 표현되지 않는다. 가르칠 자리는 코퍼스가 아니라 도구 스키마·문서다.

★검증: 8건 전건 /ibl/validate 8/8 + 라이브 실행 8/8 통과 후 넣었다(검수만으로는 런타임
  거절 부류를 못 거른다 — 20회차 실측 교훈).

실행: .venv/bin/python3 scripts/seed_imagination_round_23.py   (★_load_model_sync 뒤 add, intent dedupe)
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    # ── ① 실패를 다루는 문형 (23회차 중점) ──────────────────────
    ("사이트가 막혀 있으면 검색으로라도 알아봐줘",
     '[try]{[sense:crawl]{url: "https://www.pewresearch.org/feed/"} >> [table:take]{n: 3}}\n'
     '[catch]{[sense:search]{source: "ddg", query: "pew research 최신 보고서"} >> [table:take]{n: 2}}',
     "sense,table", "research", "오류처리,try,catch,폴백대체"),
    ("중간이 죽더라도 있는 데까지는 보여줘",
     '[on_error: skip] [sense:feed]{url: "https://news.hada.io/rss/news", limit: 5} >> [table:groupby]{by: "meta"} >> [table:take]{n: 2}',
     "sense,table", "research", "오류처리,on_error,skip,부분결과"),
    ("새 글 나올 때까지 지켜봐줘",
     '$새것 = 0\n[repeat: until $새것 > 0, max: 2, every: "1s"]{$새것 = 1\n[sense:feed]{url: "https://news.hada.io/rss/news", limit: 3}}',
     "sense", "research", "시간,repeat,until,상태변수"),
    ("여러 곳 훑되 한 곳이 막혀도 나머지는 살려줘",
     '[table:each]{items: [{"url": "https://news.hada.io/rss/news"}, {"url": "https://www.pewresearch.org/feed/"}], do: "[sense:feed]{url: \'$it.url\', limit: 2}", on_error: "skip"}',
     "table,sense", "research", "적용,each,리터럴팬아웃,on_error"),

    # ── ② 통화·산출 문형 ────────────────────────────────────────
    ("이 메모 뭉치를 표로 만들어줘",
     '[self:struct]{text: "죽백동 84제곱 6억8천 12층 2023년식 / 세교동 84제곱 2억3백 4층 1998년식", schema: "단지·면적·가격·층·건축년도"}',
     "self", "system", "struct,비정형구조화,입구"),
    ("최근 커밋을 문서로 정리해줘",
     '[self:body]{op: "log", limit: 5} >> [table:structure]{instruction: "최근 커밋 요약 문서"} >> [table:document]{format: "markdown"}',
     "self,table", "system", "structure,document,문서IR,body"),
    ("디스크 파티션을 여유 순으로 보여줘",
     '[sense:host]{op: "resources"} >> [table:sort]{by: "free_gb", desc: true} >> [table:take]{n: 3}',
     "sense,table", "system", "자기수용감각,host,sort,통화접속"),

    # ── ③ 22회차 수리가 새로 참으로 만든 문형 (23회차 야생 검증) ──
    ("저장해둔 문장을 이름으로 불러 결과를 돌려줘",
     '[self:workflow]{op: "save", name: "비트코인시세", do: "$r = [sense:crypto]{symbol: \'BTC\'}\\n$return = $r"}',
     "self", "system", "workflow,$return,상태변수,B22-1"),
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
