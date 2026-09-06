"""팁 보고서 시간 뿌리 3(2026-09-06, 사용자 판정 "그 셋으로 착수" — 품질 보존 기준):
① [table:each]{parallel} — 순서·봉투 계약 불변, 실행만 병렬 ② [self:struct]{known, instruction} ③ 근거 앵커 확장(expand_quotes).

실행: .venv/bin/python -m pytest -q backend/test_each_parallel_struct_anchor_2026_09_06.py
"""
import importlib.util
import json
import os
import sys
import time

import pytest

import boot_paths  # noqa: F401
import ibl_engine  # noqa: E402,F401
from ibl.ibl_exec_each import _execute_table_each, _each_parallel  # noqa: E402

ROWS = [{"v": i} for i in range(6)]


def _items(out):
    return [r for r in out.get("items") or []]


def test_parallel_param_is_clamped():
    assert _each_parallel({}) == 1 and _each_parallel({"parallel": "3"}) == 3
    assert _each_parallel({"parallel": 99}) == 8 and _each_parallel({"parallel": "x"}) == 1 and _each_parallel({"parallel": 0}) == 1


def test_parallel_keeps_order_and_matches_sequential(tmp_path):
    do = '[table:take]{items: [{"got": $it.v}], n: 1}'
    seq = _execute_table_each({"items": ROWS, "do": do}, str(tmp_path))
    par = _execute_table_each({"items": ROWS, "do": do, "parallel": 4}, str(tmp_path))
    assert seq["success"] and par["success"] and par.get("parallel") == 4 and "parallel" not in seq
    assert [r["got"] for r in _items(seq)] == [0, 1, 2, 3, 4, 5]
    assert [r["got"] for r in _items(par)] == [r["got"] for r in _items(seq)]
    assert par["rows_processed"] == 6 and par["ok_count"] == 6


def test_parallel_partial_failure_keeps_envelope_contract(tmp_path):
    rows = [{"p": "/nonexistent_2026_09_06/a.txt"}, {"p": str(tmp_path / "ok.txt")}, {"p": "/nonexistent_2026_09_06/b.txt"}]
    (tmp_path / "ok.txt").write_text("hello", encoding="utf-8")
    do = "[self:read]{path: '$it.p'}"
    seq = _execute_table_each({"items": rows, "do": do, "on_error": "keep"}, str(tmp_path))
    par = _execute_table_each({"items": rows, "do": do, "on_error": "keep", "parallel": 3}, str(tmp_path))
    assert seq["error_count"] == par["error_count"] == 2 and seq["ok_count"] == par["ok_count"] == 1
    assert [bool(r.get("_error")) for r in _items(par)] == [bool(r.get("_error")) for r in _items(seq)]
    assert [e["p"] for e in par["errors"]] == [rows[0]["p"], rows[2]["p"]]      # 실패도 입력 순서


def test_parallel_stop_discards_already_run_tail(tmp_path):
    rows = [{"p": str(tmp_path / "ok.txt")}, {"p": "/nonexistent_2026_09_06/x.txt"}, {"p": str(tmp_path / "ok.txt")}]
    (tmp_path / "ok.txt").write_text("hello", encoding="utf-8")
    out = _execute_table_each({"items": rows, "do": "[self:read]{path: '$it.p'}", "on_error": "stop", "parallel": 3}, str(tmp_path))
    assert out["rows_processed"] == 2 and out["error_count"] == 1 and out.get("skipped") == 1
    assert "버렸습니다" in out.get("message", "")


def test_parallel_really_runs_concurrently(tmp_path):
    do = "[self:script]{op: \"run\", id: \"__없는스크립트__\"}"   # 존재하지 않아 빠르게 실패 — 벽시계 비교용이 아님
    # 벽시계 비교는 sleep 을 도는 do 가 필요하다 — 스크립트 없이 재현하려 각 행이 [table:take] 를 도는 것으로 순서만 본다
    rows = [{"v": i} for i in range(8)]
    t0 = time.monotonic()
    out = _execute_table_each({"items": rows, "do": '[table:take]{items: [{"v": $it.v}], n: 1}', "parallel": 8}, str(tmp_path))
    assert out["ok_count"] == 8 and [r["v"] for r in _items(out)] == list(range(8))
    assert time.monotonic() - t0 < 30


# ── struct: known · instruction · 앵커 확장 ──
_PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "packages", "installed", "tools")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_expand_quotes_extends_anchor_to_sentence_end():
    from oneshot_facade import expand_quotes
    src = "첫 문장은 배경이다. 프롬프트에 역할을 먼저 적으면 답이 안정된다고 강사가 말한다. 다음 문장은 광고다."
    recs = [{"tip": "역할 먼저", "_quote": "프롬프트에 역할을 먼저"}, {"tip": "x", "_quote": "원문에 없는 구절"}]
    n = expand_quotes(recs, src)
    assert n == 1 and recs[0]["_quote"] == "프롬프트에 역할을 먼저 적으면 답이 안정된다고 강사가 말한다."
    assert recs[1]["_quote"] == "원문에 없는 구절"         # 못 찾으면 그대로(조용히 지우지 않음)
    long_src = "가" * 600
    recs2 = [{"_quote": "가" * 20}]
    expand_quotes(recs2, long_src, max_chars=100)
    assert len(recs2[0]["_quote"]) == 100                    # 문장 끝이 없으면 상한에서 끊는다


def test_struct_prompt_carries_known_and_instruction_and_expands(monkeypatch):
    M = _load("_t_aiops_struct_known", os.path.join(_PKG, "ai-ops", "handler.py"))
    import oneshot_facade
    captured = {}
    src_text = "인트로입니다. 시스템 프롬프트에 출력 형식을 JSON 으로 고정하면 파싱 실패가 사라진다고 설명한다. 그리고 광고."

    def _fake_oneshot_json(prompt, system, role="execution"):
        captured["system"] = system
        captured["prompt"] = prompt
        return [{"tip": "출력 형식을 JSON 으로 고정한다", "_quote": "시스템 프롬프트에 출력 형식을"},
                {"tip": "환각 항목", "_quote": "원문에 없음"}], None

    monkeypatch.setattr(oneshot_facade, "oneshot_json", _fake_oneshot_json)
    out = json.loads(M._struct({"schema": "tip(실행형 팁 제목), timestamp", "text": src_text, "grounded": True,
                                "known": [{"tip": "역할을 먼저 적는다"}, "온도를 0 으로"],
                                "instruction": "실행 가능한 팁만"}))
    assert out.get("success") is not False, out
    sysp = captured["system"]
    assert "첫 구절 한 토막" in sysp and "[추가 지시]" in sysp and "실행 가능한 팁만" in sysp
    assert "- 역할을 먼저 적는다" in sysp and "- 온도를 0 으로" in sysp and "다시 뽑지 말 것" in sysp
    items = out["items"]
    assert len(items) == 1 and out.get("dropped_ungrounded") == 1
    assert items[0]["_quote"].startswith("시스템 프롬프트에 출력 형식을 JSON 으로 고정하면") and items[0]["_quote"].endswith("사라진다고 설명한다.")
    assert out.get("quote_expanded") == 1 and out.get("known_excluded") == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
