#!/usr/bin/env python3
"""seed_imagination_round_21.py — 21회차 시드 (2026-08-22 집행, 2026-08-22 스크립트 고정).

★이 스크립트는 **사후 고정본**이다. 시딩 자체는 2026-08-22 18:4x 에 이미 집행됐고
  (코퍼스 3,549→3,557 · ibl_distilled 833→841), 그때는 `scripts/` 가 RED 인데 그 턴이
  수리 경로가 아니어서 파일을 남기지 못했다(게이트가 정직하게 막았다). 다시 돌려도
  intent dedupe 로 0건이 되는 **멱등** 스크립트이며, 목적은 재실행이 아니라 **재현 가능한 출처**다.

무엇을 가르치는가:
  ① **21회차 시드 후보 5건**(사용자 승인) — 중심은 **폴백 `??`**. 문법 축에서 유일하게
     행동 조합 0% 였고(& 18.8% · if/case 5.3% · `$변수` 3.9% 인데 `??` 는 0), 21회차가
     처음 실측했다. 코퍼스가 안 가르치면 번역기도 안 쓴다 — 희소가 희소를 낳던 고리를 끊는다.
     나머지는 축적 `reduce` · 고차 `each >> flatten`(retired-ok: 21회차 시딩 당시의 기록 —
     그 관용구는 2026-08-23 은퇴, 코퍼스는 이미 이행 완료) · `limb` 조회.
  ② **21회차 수리가 새로 참으로 만든 문형 3건** — 20회차 규율("판정이 새로 참으로 만든
     문형만 가르친다")을 그대로 따른다. 셋 다 수리 *전에는 실패하던* 문장이다:
       · `>> [engines:render_html]` 파이프 싱크 (V21-1) — 전엔 "html은 필수입니다" 로 죽었다
       · `[self:cctv]{op:"stats"} >> [table:*]` (V21-2) — 전엔 통화 없음으로 거절됐다
       · `?? ( … >> … )` 괄호 가지 (F21-1) — 구현은 됐는데 교재가 "단일 액션만" 이라 막았다

★시드는 교재다 — 8건 전건 `/ibl/validate` + **라이브 실행까지** 통과 확인 후 넣었다(8/8).
  검증만으로는 런타임 거절 부류를 못 거른다(20회차 실측 교훈).
  집행 당시 확인: 벡터 색인 8/8(`ibl_examples_vec_rowids` — `_index_batch` 는 실패를 삼키므로
  계수 대조) · 라이브 회상 실증("테슬라 주가 알려주고 안 되면 웹에서라도"→0.853 으로 괄호 가지).

실행: .venv/bin/python3 scripts/seed_imagination_round_21.py   (★_load_model_sync 뒤 add, intent dedupe)
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    # ── ① 21회차 시드 후보 (사용자 승인) ──────────────────────
    ("죽백동 전세 매물 보여줘, 네이버가 비면 직방으로라도",
     "[sense:realty]{source: \"naver\", region: \"죽백동\", deal: \"lease\"} ?? [sense:realty]{source: \"zigbang\", region: \"죽백동\", deal: \"lease\"}",
     "sense", "realty", "폴백,??,소스대체,realty"),
    ("전세사기 법령 찾아보고 없으면 검색으로, 셋만",
     "[sense:legal]{query: \"전세사기\"} ?? [sense:search]{source: \"naver\", query: \"전세사기 처벌\"} >> [table:take]{n: 3}",
     "sense,table", "legal", "폴백,??,폴백뒤변환자,take"),
    ("죽백동 아파트 실거래 총액이 얼마나 되나",
     "[sense:realty]{source: \"molit\", region: \"죽백동\", type: \"apt\", deal: \"trade\"} >> [table:reduce]{init: 0, step: \"acc + 거래금액\", as: \"총거래액\"}",
     "sense,table", "realty", "축적,reduce,molit,거래금액"),
    ("살아있는 USB 손발만 별칭·기기·만료일로 추려줘",
     "[self:limb]{op: \"list\"} >> [table:filter]{where: \"revoked == false\"} >> [table:select]{columns: [\"alias\", \"device_id\", \"expires_at\"]}",
     "self,table", "system", "limb,filter,select"),
    ("즐겨찾기한 보드마다 최근 글을 한 표로 모아줘",
     "[others:board]{op: \"list\"} >> [table:take]{n: 2} >> [table:each]{do: \"[others:feed]{op: 'read', hashtag: '$it.hashtag'}\"} >> [table:flatten]{field: \"_result\"}",
     "others,table", "indienet", "적용,each,flatten,board"),

    # ── ② 21회차 수리가 새로 참으로 만든 문형 ──────────────────
    ("비트코인 시세 한 문장으로 요약해서 그림으로 뽑아줘",
     "[sense:crypto]{symbol: \"BTC\"} >> [table:brief]{instruction: \"한 문장 시세 요약\"} >> [engines:render_html]",
     "sense,table,engines", "media", "파이프싱크,render_html,brief,V21-1"),
    ("CCTV 소스별 현황 위에 두 개만 이름이랑 대수로 보여줘",
     "[self:cctv]{op: \"stats\"} >> [table:take]{n: 2} >> [table:select]{columns: [\"name\", \"total_cctv\"]}",
     "self,table", "cctv", "통화승격,items,select,V21-2"),
    ("애플 주가, 안 되면 웹에서 두 줄이라도 찾아줘",
     "[sense:stock]{op: \"quote\", ticker: \"AAPL\"} ?? ([sense:search]{source: \"ddg\", query: \"애플 주가\"} >> [table:take]{n: 2})",
     "sense,table", "invest", "폴백,??,괄호가지,F21-1"),
]

if __name__ == "__main__":
    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단(★_index_batch 는 실패를 삼킨다)"
    import sqlite3
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "..", "data", "ibl_usage.db"))
    existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
    conn.close()
    batch = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2,
              "source": "manual_seed", "tags": t} for i, c, n, cat, t in NEW if i not in existing]
    print(f"시드 추가: {db.add_examples_batch(batch) if batch else 0}건 (중복 스킵 {len(NEW) - len(batch)}건)")
    dist_path = os.path.join(os.path.dirname(__file__), "..", "data", "training", "ibl_distilled.json")
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
