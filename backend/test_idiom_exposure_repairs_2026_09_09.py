"""노출 실험에서 발견한 실제 저장·교재 누락·불필요한 수리의 회귀."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from idiom_exposure_cases import GOLD, judge, setup, returned_body

EVIDENCE = ROOT / "docs/experiments/idiom_exposure_2026_09_09"
REGISTRY = json.loads((EVIDENCE / "registry.json").read_text())
CALL = '[fn:최신범위읽기]{폴더:"drafts",패턴:"*.md",시작줄:11,줄수:12}'
QUEUE = (
    '[self:read]{path:"queue.json"} '
    ">> [table:filter]{where:\"state == 'open' and priority >= 3\"} "
    '>> [table:sort]{by:"id"} '
    '>> [self:write]{path:"outputs/pending.json",format:"json"}'
)










@pytest.mark.local
def test_current_lesson_matches_operational_registry():
    catalog = json.loads((ROOT / "data/idioms/curated.json").read_text())
    lesson = next(e for e in catalog["idioms"] if e["name"] == "위치마다읽기")
    # 불변식은 교재 몸 == **운영 원장의 현재 몸**(다르면 소개기가 교재를 버린다). v1 스냅샷은 09-09 서명 개정
    # (파이프형→자족형, 지렛대 1) 이전의 몸이라 비교 대상이 아니다 — 운영 원장을 읽기 전용으로 본다.
    live = ROOT / "data/ibl_usage.db"
    if not live.exists():
        pytest.skip("운영 원장 없음")
    with sqlite3.connect(f"file:{live}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        row = dict(con.execute(
            "SELECT intent, ibl_code, alias, returns, signature FROM ibl_examples "
            "WHERE alias='위치마다읽기'").fetchone())
    assert (
        lesson["body"] == row["ibl_code"]
    )  # 운영 몸을 옛 교재로 되돌리지 않는다








def test_equivalent_body_is_accepted_but_trace_and_wrong_body_are_rejected(
    tmp_path,
):
    setup(tmp_path, 7)
    initial = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    body = "\n".join(
        initial["drafts/report_2026-08-27.md"].decode().splitlines()[10:22]
    )

    def verdict(payload):
        return judge(
            "counter_latest",
            {"success": True, "final_result": payload},
            tmp_path,
            {},
            initial,
        )[0]

    assert verdict({"items": [{"file": "a.md", "content": body}]})
    assert verdict(
        {"_value_result": True, "value": {"items": [{"본문": body}]}}
    )
    assert not verdict({"items": [{"content": body + "\n원치 않은 줄"}]})
    assert not verdict({"results": [{"content": body}], "message": "완료"})
    assert not verdict({"items": [{"content": "다른 문서"}]})
    assert returned_body({"items": []}) == []




if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
