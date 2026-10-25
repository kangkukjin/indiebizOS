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
from idiom_exposure_worker import run

EVIDENCE = ROOT / "docs/experiments/idiom_exposure_2026_09_09"
REGISTRY = json.loads((EVIDENCE / "registry.json").read_text())
CALL = '[fn:최신범위읽기]{폴더:"drafts",패턴:"*.md",시작줄:11,줄수:12}'
QUEUE = (
    '[self:read]{path:"queue.json"} '
    ">> [table:filter]{where:\"state == 'open' and priority >= 3\"} "
    '>> [table:sort]{by:"id"} '
    '>> [self:write]{path:"outputs/pending.json",format:"json"}'
)


def execute(code, case="embedded_latest", seed=2026090901):
    return run(dict(code=code, case_id=case, seed=seed, registry=REGISTRY))




@pytest.mark.parametrize(
    "value",
    [
        "본문\n",
        "",
        {"items": []},
        {"items": [{"id": 1}]},
        [1, 2],
        {"success": True, "path": "saved"},
    ],
)
def test_return_projection_keeps_values_and_does_not_mutate_diagnostics(value):
    from common.currency import fn_result_payload
    from workflow_binding import _to_prev_currency

    env = dict(
        success=True,
        _fn_result=True,
        final_result=value,
        results=[{"step": 1}],
    )
    before = json.dumps(env)
    assert fn_result_payload(env) == (True, value)
    actual = _to_prev_currency(env)
    assert (actual if isinstance(value, str) else json.loads(actual)) == value
    assert json.dumps(env) == before
    failed = dict(env, success=False, error="실패", traceback={"frames": []})
    assert fn_result_payload(failed) == (False, failed)
    business = dict(
        fn="업무 필드", fn_source="idiom", final_result=value, success=True
    )
    assert fn_result_payload(business) == (False, business)




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


def test_current_block_body_uses_edition_checked_call_teaching(tmp_path, monkeypatch):
    import hashlib
    import ibl_access
    import runtime_utils
    from workflow_contract import call_signature

    catalog = json.loads((ROOT / "data/idioms/curated.json").read_text())
    lesson = next(e for e in catalog["idioms"] if e["name"] == "위치마다읽기")
    row = {"intent": lesson["when"], "ibl_code": lesson["body"], "alias": lesson["name"],
           "returns": "items", "signature": " ".join(call_signature(lesson["body"]))}
    # 상시 소개는 현재 호출 문법이다. 몸이 같은 구형 교재도 현재 호출의
    # 반환 봉투·파이프 계약을 검토하기 전에는 예시를 그대로 가르치지 않는다.
    (tmp_path / "data/idioms").mkdir(parents=True)
    (tmp_path / "data/idioms/curated.json").write_text(json.dumps(catalog))
    with sqlite3.connect(tmp_path / "data/ibl_usage.db") as con:
        con.execute(
            "CREATE TABLE ibl_examples (intent,ibl_code,success_count,fail_count,"
            "topic,alias,returns,signature,always_on,created_at)"
        )
        con.execute(
            "INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                row["intent"],
                row["ibl_code"],
                1,
                0,
                "찾기",
                row["alias"],
                row["returns"],
                row["signature"],
                1,
                "2026-09-09",
            ),
        )
    monkeypatch.setattr(runtime_utils, "get_base_path", lambda: tmp_path)
    monkeypatch.setattr(
        ibl_access, "_idioms_cache", {"text": None, "t": 0, "key": None}
    )
    from test_function_support import import_memory
    with sqlite3.connect(tmp_path / 'data/ibl_usage.db') as fixture_db:
        import_memory(fixture_db)
    block = ibl_access.idioms_map(None)
    assert lesson["example"] not in block
    assert '[fn:위치마다읽기]' not in block
    assert '앞 통화' not in block

    current = {
        'name': lesson['name'], 'source_edition': 1,
        'source_sha256': hashlib.sha256(lesson['body'].encode()).hexdigest(),
        'inputs': '위치 목록·개수·줄수를 명시하고 전체 Record를 받는다.',
        'example': '#!ibl edition=2\nreturn [fn:위치마다읽기]{위치:[],개수:0,줄수:1}',
    }
    (tmp_path / 'data/idioms/current_call_lessons.json').write_text(json.dumps({'idioms': [current]}))
    monkeypatch.setattr(ibl_access, '_idioms_cache', {'text': None, 't': 0, 'key': None})
    block = ibl_access.idioms_map(None)
    assert current['inputs'] not in block
    assert current['example'].split('\n', 1)[1] not in block
    assert lesson['example'] not in block




def test_trial_stops_at_correct_result_even_if_runtime_has_warning(
    tmp_path, monkeypatch
):
    import idiom_exposure_study as study

    calls = []

    def model(*args):
        calls.append(args)
        return {"result": '{"code":"test"}', "wall_ms": 1}

    monkeypatch.setattr(study, "call_model", model)
    monkeypatch.setattr(
        study,
        "execute",
        lambda *a: {
            "quality_ok": True,
            "runtime_ok": False,
            "verdict": "품질 기준 통과",
            "result": {"success": False, "error": "부수 오류"},
        },
    )
    record = study.trial(
        tmp_path,
        {"cases": study.CASES, "max_repairs": 1},
        {
            "case": "direct_ledger",
            "repeat": 0,
            "arm": "exposed",
            "seed": 1,
        },
    )
    assert len(calls) == len(record["attempts"]) == 1


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
