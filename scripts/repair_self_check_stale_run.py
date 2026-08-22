#!/usr/bin/env python3
"""repair_self_check_stale_run.py — '결과를 달라'는 질의가 '전수 점검 실행'을 배운 자리 (2026-08-22).

`[sense:self_check]` 는 op 기본값이 `run`(부작용 없는 전 액션 실행, **수 분 소요**)이다.
코퍼스의 balanced_20260516 8건은 전부 파라미터 없는 맨몸 `[sense:self_check]` 인데,
그중 셋은 intent 가 명시적으로 **결과·목록**을 달라고 한다 — 맨몸은 그 질문의 답이 아니다.

실측(2026-08-22, source 축 시드 직후 회상): "만성 실패 왜 났어" → top1 이
`만성 실패 액션 뭐가 있어? → [sense:self_check]`(0.690). 만성 실패는 **실사용 원장**이
세는 것인데(V18-2), 이 용례는 몇 분짜리 전수 점검을 새로 돌리라고 가르친다.

세 건만 고친다. 나머지 다섯("지금 시스템 정상이야?" 등)은 상태를 묻는 말이라 run 이
그럴듯한 답이다 — 추측으로 넓히지 않는다.

실행: .venv/bin/python3 scripts/repair_self_check_stale_run.py [--dry-run]
"""
import sys, os, json, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

FIXES = {
    # intent: (새 코드, 왜)
    "만성 실패 액션 뭐가 있어?": (
        '[sense:self_check]{op: "results", source: "usage", limit: 500} '
        '>> [table:filter]{where: "success == false"} >> [table:groupby]{by: "title"} '
        '>> [table:sort]{by: "count", desc: true}',
        "만성 실패는 실사용 원장(action_health)이 세는 것 — 경보의 근거와 같은 곳을 봐야 한다",
    ),
    "자가점검 패턴 분석 결과 알려줘": (
        '[sense:self_check]{op: "results", limit: 200} >> [table:filter]{where: "success == false"} '
        '>> [table:groupby]{by: "title"} >> [table:sort]{by: "count", desc: true}',
        "'결과 알려줘'는 조회다 — 자가점검 원장(기본 source)의 결과를 읽는다",
    ),
    "시스템 자가점검 결과": (
        '[sense:self_check]{op: "results", limit: 50}',
        "'결과'를 달라는 말에 전수 점검 실행(수 분)을 가르치면 안 된다",
    ),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from ibl_parser import parse
    for intent, (code, _) in FIXES.items():
        parse(code)          # 교재는 넣기 전에 판다
    print(f"파싱 통과 ✓ ({len(FIXES)}건)")

    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패 — 중단"

    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT id, intent, ibl_code FROM ibl_examples WHERE intent IN ({})".format(
                ",".join("?" * len(FIXES))), list(FIXES)).fetchall()
    for r in rows:
        new, why = FIXES[r["intent"]]
        print(f"  {r['intent']!r}\n    옛: {r['ibl_code']}\n    새: {new[:96]}…\n    왜: {why}")
    missing = set(FIXES) - {r["intent"] for r in rows}
    if missing:
        print(f"  (DB 미존재 {len(missing)}건: {missing})")
    if args.dry_run:
        return

    vec = db._get_vec_connection()
    for r in rows:
        new, _ = FIXES[r["intent"]]
        with db._get_connection() as conn:
            conn.execute("UPDATE ibl_examples SET ibl_code=?, updated_at=datetime('now') WHERE id=?",
                         (new, r["id"]))
            conn.commit()
        # ★임베딩은 intent+code 로 만든다 — 코드가 바뀌면 반드시 재색인.
        #   vec0 는 REPLACE 불가라 DELETE 후 INSERT (sqlite_vec 함정).
        if vec is not None:
            vec.execute("DELETE FROM ibl_examples_vec WHERE rowid=?", (r["id"],))
            vec.commit()
        db._index_single(r["id"], r["intent"], new)
    print(f"DB 수리: {len(rows)}건")

    # 트레이너는 DB 와 훈련 json 을 둘 다 읽는다 — 양쪽을 같이 고친다.
    jp = os.path.join(ROOT, "data", "training", "ibl_training_balanced_20260516.json")
    with open(jp, encoding="utf-8") as f:
        data = json.load(f)
    n = 0
    for item in data:
        if item.get("intent") in FIXES:
            item["ibl_code"] = FIXES[item["intent"]][0]
            n += 1
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"훈련 json 수리: {n}건 ({os.path.basename(jp)})")


if __name__ == "__main__":
    main()
