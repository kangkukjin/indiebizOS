"""criteria 판정자의 기계 계수 (2026-09-05, ep2832 시스템 AI 보고).

심사 `[table:ai]` 의 criteria "selected 가 true 인 행이 정확히 4행" 이 5행 결과에 pass 로 돌아왔다.
판정자는 결과 원문 앞 6,000자만 보고 계수는 받지 못했다 — 셀 수 있는 것은 기계가 센다.

실행: .venv/bin/python -m pytest -q backend/test_judge_machine_facts_2026_09_05.py
"""
import json
import sys

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: E402,F401

import ibl_quality as iq  # noqa: E402


def _rows(n_true, n_false, pad=0):
    rows = [{"title": f"v{i}", "selected": i < n_true, "why": "x" * pad} for i in range(n_true + n_false)]
    return {"success": True, "items": rows}


def test_machine_facts_counts_rows_and_booleans():
    facts = iq._machine_facts(json.dumps(_rows(5, 43), ensure_ascii=False))
    assert facts.startswith("행 수 48")
    assert "- selected: 값 있음 48/48 · true 5 · false 43" in facts
    assert "- title: 값 있음 48/48" in facts
    # table 통화도 같은 판정기로 items 를 파생해 센다
    tbl = {"success": True, "table": {"columns": ["a", "ok"], "rows": [[1, True], [None, False], [3, True]]}}
    facts = iq._machine_facts(tbl)
    assert facts.startswith("행 수 3") and "- a: 값 있음 2/3" in facts and "true 2 · false 1" in facts
    # 통화 아님 → 빈 문자열(판정은 종전대로 원문으로)
    assert iq._machine_facts({"success": True, "path": "/x"}) == ""
    assert iq._machine_facts("산문 결과") == ""


def test_judge_prompt_carries_facts_even_when_raw_is_clipped(monkeypatch):
    seen = []

    def fake_judge(prompt):
        seen.append(prompt)
        return '{"pass": false, "reason": "selected true 5행 — 기준 4행"}'
    monkeypatch.setattr(iq, "_call_judge", fake_judge)
    result = json.dumps(_rows(5, 43, pad=400), ensure_ascii=False)   # 6,000자 상한을 훌쩍 넘는 원문
    assert len(result) > iq.JUDGE_OUTPUT_CAP
    v = iq._judge("입력의 모든 행이 유지되고 selected 가 true 인 행이 정확히 4행이다", result, "table", "ai", {})
    assert v["pass"] is False
    p = seen[0]
    assert "기계 계수" in p and "행 수 48" in p and "true 5" in p
    assert "앞 6000자만 보임" in p                       # 절단 고지는 그대로
    assert p.index("기계 계수") < p.index("실행 결과:")     # 계수가 원문보다 앞
    assert "다시 세지 마라" in iq._JUDGE_SYSTEM


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
