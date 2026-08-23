#!/usr/bin/env python3
"""seed_table_since_standalone.py — [table:since] 를 **문장의 머리**에서 가르친다 (2026-08-23).

멱등: intent dedupe 로 두 번 돌려도 0건. 목적은 재실행이 아니라 재현 가능한 출처다.

## 왜 — 진단이 기계적으로 확정된 자리

08-22·08-23 두 번의 재학습에서 **같은 프로브 2건**(`table:since` — "긱뉴스 새 글"·"관심 매물
가격 변동")을 연속으로 잃었다. 08-22 는 이를 *"파이프 안 시드는 그 낱말 단독을 안 가르친다"*
로 진단했지만 기제까지는 못 짚었다. 08-23 에 코퍼스를 세어 확정했다:

    table:since 코퍼스 25건 — **전부 2홉 이상. 머리에 선 적 0회.**

그리고 트레이너의 desc 쌍은 `extract_action_from_code()` = **코드의 첫 액션**으로만 만들어진다
(`ibl_embedding_trainer.py`). 즉 `[sense:feed]{…} >> [table:since]{…}` 라는 25건은 전부
`sense:feed` 의 description 과만 짝지어졌고, **`table:since` 는 intent→description 학습 쌍을
0건 받아 왔다.** 프로브(질의 vs 액션 description)가 이 낱말에서 흔들린 기계적 이유다.

★이건 since 만의 문제가 아니다 — 코퍼스에 나오지만 머리에 선 적 없는 액션이 **14개**이고
전부 `table:` 변환자다(take 150회·filter 52·sort 46·brief 30·since 25·…). 이 스크립트는
그중 사용자가 지시한 since 를 먼저 메운다. 나머지는 트레이너 쪽 판단이 필요하다
(첫 액션만 쓰는 desc 쌍 규칙을 바꿀 것인가 — desc Top-1 과 트레이드가 있다).

## 무엇을 가르치는가

단독형은 **억지 형태가 아니다** — `[table:since]{items: […], key: …}` 는 실측으로 정상
동작하고(통화를 직접 받는다), 사용자가 목록을 손에 들고 "전에 안 보던 것만"이라 말하는
자리가 실제로 있다. 아래 8건은 전부 **라이브 실행까지 통과**했다.

★라이브가 잡은 저작 오류 1건(기록): `watch` 를 쓰는 행에 url/id/link/title 이 없으면 since 가
행을 식별할 수 없어 정직하게 거절한다 → `by` 를 함께 줘야 한다. **검수(validate)는 이 자리를
못 본다** — 문법과 액션은 멀쩡하기 때문이다. 그래서 시드는 검수가 아니라 실행으로 검증한다.

실행: .venv/bin/python3 scripts/seed_table_since_standalone.py
"""
import sys, os, json
from pathlib import Path

# 격리 사본(.worktrees/...)에서 돌더라도 해마 원장은 라이브 하나뿐이다 — 라이브 루트로 고정.
ROOT = Path(__file__).resolve().parents[1]
if ".worktrees" in ROOT.parts:
    ROOT = Path(*ROOT.parts[:ROOT.parts.index(".worktrees")])
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("INDIEBIZ_BASE_PATH", str(ROOT))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    # ── 핵심 의미: 델타(지난 검침 이후) ─────────────────────────────
    ("이 목록에서 전에 안 보던 것만 골라줘",
     '[table:since]{items: [{"title": "8월 정산 안내", "url": "https://n/1"}, '
     '{"title": "배송 지연 공지", "url": "https://n/2"}], key: "공지검침"}',
     "table", "감시", "검침,델타,단독,since"),
    ("지난번 확인 이후 새로 생긴 것만",
     '[table:since]{items: [{"name": "A-1023", "url": "https://s/a"}, '
     '{"name": "A-1044", "url": "https://s/b"}], key: "주문검침"}',
     "table", "감시", "검침,델타,단독,since"),
    ("이미 본 건 빼고 새 것만 보여줘",
     '[table:since]{items: [{"제목": "공고 12호", "url": "https://g/12"}, '
     '{"제목": "공고 13호", "url": "https://g/13"}], key: "공고검침"}',
     "table", "감시", "검침,델타,단독,since"),

    # ── by: 행 식별 필드를 사람이 정한다 ─────────────────────────────
    ("링크 말고 제목 기준으로 새 것만 가려줘",
     '[table:since]{items: [{"title": "1분기 보고", "author": "김"}, '
     '{"title": "2분기 보고", "author": "박"}], key: "보고서검침", by: "title"}',
     "table", "감시", "검침,행식별,by,since"),

    # ── watch: '새로 생긴 것'과 '값이 바뀐 것'은 다른 질문 ────────────
    #    ★by 를 함께 주는 이유는 위 독스트링의 저작 오류 기록 참조.
    ("값이 바뀐 것만 보여줘, 새로 생긴 건 말고",
     '[table:since]{items: [{"code": "005930", "price": 281500}, '
     '{"code": "000660", "price": 1730000}], key: "관심종목검침", by: "code", watch: ["price"]}',
     "table", "감시", "검침,변동감시,watch,since"),
    ("가격 변동 있는 것만 추려줘",
     '[table:since]{items: [{"단지": "봉명아이파크", "price": 38000}, '
     '{"단지": "주공6단지", "price": 29500}], key: "관심단지검침", by: "단지", watch: ["price"]}',
     "table", "감시", "검침,변동감시,watch,since"),

    # ── peek: 기준선을 올리지 않고 들여다본다 ────────────────────────
    ("기준선은 그대로 두고 새 것만 미리 봐줘",
     '[table:since]{items: [{"title": "속보 A", "url": "https://p/a"}, '
     '{"title": "속보 B", "url": "https://p/b"}], key: "속보검침", peek: true}',
     "table", "감시", "검침,미리보기,peek,since"),

    # ── 첫 검침의 의미(0건 ≠ 없음) ─────────────────────────────────
    ("이번엔 기준선만 세워두고 다음부터 새 것 알려줘",
     '[table:since]{items: [{"title": "채용 공고 1", "url": "https://j/1"}, '
     '{"title": "채용 공고 2", "url": "https://j/2"}], key: "채용검침"}',
     "table", "감시", "검침,기준선,첫검침,since"),
]

if __name__ == "__main__":
    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단(_index_batch 는 실패를 삼킨다)"
    import sqlite3
    conn = sqlite3.connect(str(ROOT / "data" / "ibl_usage.db"))
    existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
    conn.close()
    batch = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2,
              "source": "manual_seed", "tags": t} for i, c, n, cat, t in NEW if i not in existing]
    print(f"시드 추가: {db.add_examples_batch(batch) if batch else 0}건 (중복 스킵 {len(NEW) - len(batch)}건)")

    # ★트레이너는 DB 와 이 파일을 **둘 다** 읽는다 — 한쪽만 채우면 다음 학습이 갈린다.
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
    print("★_index_batch 는 실패를 삼킨다 — 벡터 적재는 반드시 따로 센다:")
    vc = db._get_vec_connection()
    n_vec = vc.execute("select count(*) from ibl_examples_vec").fetchone()[0]
    conn = sqlite3.connect(str(ROOT / "data" / "ibl_usage.db"))
    n_row = conn.execute("select count(*) from ibl_examples").fetchone()[0]
    conn.close()
    print(f"   코퍼스 {n_row} · 벡터 {n_vec}"
          + ("  ✓" if n_vec == n_row else "  ← 불일치! rebuild_index() 후 백엔드 재기동할 것"))
