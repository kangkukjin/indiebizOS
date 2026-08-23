#!/usr/bin/env python3
"""seed_imagination_round_31.py — 31회차 시드 (2026-08-23).

멱등: intent dedupe 로 두 번 돌려도 0건. 목적은 재실행이 아니라 재현 가능한 출처다.

무엇을 가르치는가 — 31회차 축은 **집합 참조(`$items`)** 였다. census: 전 코퍼스
3,592문장 중 `$items` 를 쓴 문장 9건(0.25%)이고, 그 집합을 param 으로 **받아본**
소비자는 `limbs:show_map`·`self:write` 둘뿐이었다. `$it.필드`(행 하나, 46건)의 짝인데
"한 번에 전부"를 아무도 안 가르친 것이다 — each 로 돌리면 지도가 3장, `$items` 면
마커 3개짜리 지도 1장인데 사용자가 원하는 쪽은 대개 후자다.

아래 2건은 **값 전체가 집합 참조**인 정상형이다(B31-2 가 거절하는 것은 문장 *속*에
섞인 `$items` 뿐 — 값 전체 참조는 그대로 산다).

★보고서의 세 번째 후보를 **올리지 않았다**:
    [sense:restaurant]{…} >> [table:take]{n:3} >> [table:each]{items: "$items", do: "[self:time]"}
  파서·validate 는 통과하지만 `items:` 는 **앞 통화가 없을 때** 쓰는 리터럴 팬아웃
  입구다(table.yaml 선언). 파이프 뒤에서 `items: "$items"` 를 주는 것은 무의미한
  중복이고, 08-23 each 통화 개정 이후의 정본형(`>> [table:each]{do: …}`)과 경쟁한다.
  ★시드는 교재다 — 동작한다는 것과 가르칠 만하다는 것은 다른 질문이다.

★F31-1(`question`→`prompt` 침묵)에는 시드가 필요 없었다: 코퍼스에 `[self:ask]{prompt:}`
  가 이미 15건 있다. 그 실패는 교재의 공백이 아니라 **실패 순간의 침묵**이었고,
  처방도 코퍼스가 아니라 에러 메시지 쪽이었다(선언 키 동봉).

실행 검증: ②는 방금 라이브 실행으로 재확인(임시 경로로 바꿔 실행 → 파일에 세 곡
제목이 실제로 들어갔고, 검증 파일은 지웠다). ①은 회차 안에서 실행 검증됐고 지금은
validate 만 다시 통과시켰다 — 재실행하면 사용자 화면에 지도 창이 뜬다(부작용).

실행: .venv/bin/python3 scripts/seed_imagination_round_31.py
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
    ("죽백동 전세 매물 전부 지도에 한꺼번에 찍어줘",
     '[sense:realty]{source: "naver", region: "죽백동", deal: "lease"} >> [table:take]{n: 3} >> [limbs:show_map]{markers: "$items"}',
     "sense,table,limbs", "realty", "집합참조,items전체,지도,한번에전부"),
    ("김광석 곡 목록을 파일로 한 번에 저장해줘",
     '[self:music]{op: "library", q: "김광석"} >> [table:take]{n: 3} >> [self:write]{path: "김광석.txt", content: "$items.title"}',
     "self,table", "media", "집합참조,items필드,축적,목록저장"),
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
