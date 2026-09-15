#!/usr/bin/env python3
"""수집 구분 교재 검증. --apply는 새 관용구·합성 용례만 멱등 등록한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401

import argparse
import json
import shutil

from curate_idioms import ROOT, apply_catalog, validate_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    catalog = json.loads((ROOT / "data/idioms/curated.json").read_text())
    infos = validate_catalog(catalog)
    entry = next(e for e in catalog["idioms"] if e["name"] == "본문에서찾기")
    seeds = json.loads((ROOT / "data/idioms/web_collection_seeds.json").read_text())
    from ibl_param_vocab import check_code_params
    from ibl_usage_rag import _validate_ibl_actions
    from ibl_typecheck import typecheck_code
    for sample in seeds:
        code = sample["ibl_code"]
        assert _validate_ibl_actions(code) and not check_code_params(code), sample
        checked = typecheck_code(code)
        assert not checked.get("syntax_error"), checked
        assert not any(i.get("severity", i.get("level")) == "error"
                       for i in checked.get("issues", [])), checked
    print(f"관용구와 수집 용례 {len(seeds)}건 검증 통과")
    if not args.apply:
        return
    # 실행 중인 몸의 인코더 사용. 기존 선정집의 다른 이름·노출 상태는 손대지 않는다.
    apply_catalog({"idioms": [entry], "demote": {}}, infos, local_encoder=True)
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    with db._get_connection() as con:
        existing = {r[0] for r in con.execute(
            "SELECT ibl_code FROM ibl_examples WHERE source='web_collection_2026_09_15'")}
    pending = [dict(s, nodes="sense,table", source="web_collection_2026_09_15",
                    tags="web,collection", category="phrase", topic="수집")
               for s in seeds if s["ibl_code"] not in existing]
    if pending:
        assert db.add_examples_batch(pending) == len(pending)
    # 다음 학습용 정본에도 같은 호출 용례를 남긴다. 본문 정의는 선정집이 소유한다.
    samples = seeds + [{"intent": entry["when"], "ibl_code": entry["example"]}]
    samples += [{"intent": e["intent"], "ibl_code": e["code"]} for e in entry.get("examples", [])]
    path = ROOT / "data/training/ibl_distilled.json"
    raw = path.read_text()
    training = json.loads(raw)
    codes = {s.get("ibl_code") for s in training}
    new = [s for s in samples if s["ibl_code"] not in codes]
    if new:
        backup = ROOT / "data/_backups/2026-09-15_web_collection"
        backup.mkdir(exist_ok=True)
        if not (backup / path.name).exists():
            shutil.copy2(path, backup / path.name)
        assert path.read_text() == raw, "학습 원장이 바뀌었습니다. 재실행하세요."
        path.write_text(json.dumps(training + new, ensure_ascii=False, indent=2) + "\n")
    print(f"해마 새 용례 {len(pending)}건, 학습 JSON 새 용례 {len(new)}건")


if __name__ == "__main__":
    main()
