#!/usr/bin/env python3
"""검색→주소마다읽기→본문에서찾기 결합 용례 시딩 (2026-10-07 웹 검색 반성 4번).

ep4327·4351 에서 모델은 검색 결과를 받은 뒤 열 선택·주소별 join·재포장에 라운드를 따로 썼다.
결합 관용구는 이미 있었지만 회상에 뜨지 않았다 — 기존 용례의 의도가 일반적("도서관 소식")이라
부동산·뉴스·구매 같은 실제 조사 과제의 의도와 멀었다. 이 스크립트는 실제 과제 모양의 의도로
수집+발췌를 한 문장에 묶은 용례를 넣는다. 새 낱말은 없다. --apply 없이 검증만, --apply 로 멱등 등록."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401

import argparse
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "search_then_extract_2026_10_07"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    seeds = json.loads((ROOT / "data/idioms/search_then_extract_seeds.json").read_text())
    from ibl_param_vocab import check_code_params
    from ibl_usage_rag import _validate_ibl_actions
    from ibl_typecheck import typecheck_code
    for sample in seeds:
        code = sample["ibl_code"]
        assert _validate_ibl_actions(code), ("액션 미존재", sample["intent"])
        assert not check_code_params(code), ("인자 오류", sample["intent"], check_code_params(code))
        checked = typecheck_code(code)
        assert not checked.get("syntax_error"), (sample["intent"], checked)
        errors = [i for i in checked.get("issues", []) if i.get("severity", i.get("level")) == "error"]
        assert not errors, (sample["intent"], errors)
    print(f"수집+발췌 결합 용례 {len(seeds)}건 검증 통과")
    if not args.apply:
        return
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    # 새 프로세스는 인코더를 백그라운드로 띄우므로, 먼저 동기 로드하지 않으면 add_examples_batch 가
    # 벡터 없이 행만 넣는다(2026-10-07 실측: 8건 적재 뒤 vec 0행 → 회상에 안 뜸).
    assert db._load_model_sync(), "임베딩 모델 로드 실패 — 벡터 없는 시딩은 회상에 뜨지 않는다"
    with db._get_connection() as con:
        existing = {r[0] for r in con.execute("SELECT ibl_code FROM ibl_examples WHERE source=?", (SOURCE,))}
    pending = [dict(intent=s["intent"], ibl_code=s["ibl_code"], topic=s["topic"], nodes="sense,table",
                    source=SOURCE, tags="web,search,extract", category="phrase")
               for s in seeds if s["ibl_code"] not in existing]
    if pending:
        assert db.add_examples_batch(pending) == len(pending)
    conn = db._get_vec_connection()
    db._ensure_vec_table(conn)
    ids = [r[0] for r in conn.execute("SELECT id FROM ibl_examples WHERE source=?", (SOURCE,))]
    vec_rows = conn.execute(f"SELECT count(*) FROM ibl_examples_vec WHERE rowid IN ({','.join('?' * len(ids))})", ids).fetchone()[0]
    conn.close()
    assert vec_rows == len(ids), f"벡터 {vec_rows}/{len(ids)} — 회상 인덱스 불완전"
    # 다음 학습용 정본에도 같은 호출 용례를 남긴다.
    path = ROOT / "data/training/ibl_distilled.json"
    raw = path.read_text()
    training = json.loads(raw)
    codes = {s.get("ibl_code") for s in training}
    new = [{"intent": s["intent"], "ibl_code": s["ibl_code"]} for s in seeds if s["ibl_code"] not in codes]
    if new:
        backup = ROOT / "data/_backups/2026-10-07_search_then_extract"
        backup.mkdir(exist_ok=True)
        if not (backup / path.name).exists():
            shutil.copy2(path, backup / path.name)
        assert path.read_text() == raw, "학습 원장이 바뀌었습니다. 재실행하세요."
        path.write_text(json.dumps(training + new, ensure_ascii=False, indent=2) + "\n")
    print(f"해마 새 용례 {len(pending)}건, 학습 JSON 새 용례 {len(new)}건")


if __name__ == "__main__":
    main()
