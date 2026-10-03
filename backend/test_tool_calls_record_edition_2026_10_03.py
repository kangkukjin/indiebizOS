"""기록층 판본 정규화(2026-10-03, ep4278 추적).

증상: `[연상:사용] hippocampus 0/3(executed)` — 회상된 관용구를 실제로 실행했는데 사용 0.
뿌리: agent_pipeline 의 tool_start 기록이 모델 원입력(edition 없음)을 그대로 적어, 소비자
(연상 사용 집계·관용구 귀속·증류 재사용)가 `explicit_source(code, None)` → 판본 1 로 파싱해
`return` 에서 실패했다. 실행층(system_tools)은 authoring_request 로 판본 2 를 기본값 삼아 돈다.
수리 = 기록 자리 한 곳에서 authoring_request 정규화(소비자마다 복붙하지 않는다).
"""
import re
from pathlib import Path

import boot_paths  # noqa: F401

import associative_recall as AR
from ibl_edition import authoring_request

RAW = {"code": 'return [fn:AI동향준비읽기]{폴더:"~workspace/outputs/ai_trend_reports"}',
       "describe": ["fn:검색묶음추리기"], "wait": 60}
PHRASE = {"id": "4878", "kind": "phrase", "alias": "AI동향준비읽기",
          "code": '#!ibl edition=2\n[def:AI동향준비읽기]($폴더) {\n  $후보 = [self:list]{path:$폴더}\n  return $후보\n}'}


def _presented():
    return [{"source": "hippocampus", "ids": ["4878"], "join": {"items": [dict(PHRASE)]}}]


def test_raw_codex_input_without_edition_is_missed_by_consumer(monkeypatch):
    """소비자는 기록된 edition 을 믿는다 — 원입력 그대로면 v2 코드를 놓친다(기록층이 정규화해야 하는 이유)."""
    import episode_logger
    monkeypatch.setattr(episode_logger, "record_trajectory_event", lambda *a, **k: None)
    out = AR.record_usage(_presented(), tool_calls=[{"tool_name": "execute_ibl", "input": dict(RAW), "success": True}])
    assert out[0]["used"] == []


def test_normalized_record_counts_phrase_call_as_used(monkeypatch):
    import episode_logger
    monkeypatch.setattr(episode_logger, "record_trajectory_event", lambda *a, **k: None)
    tc = {"tool_name": "execute_ibl", "input": authoring_request(dict(RAW)), "success": True}
    assert tc["input"]["edition"] == 2 and "edition" not in RAW          # 원입력은 바꾸지 않는다
    assert AR._ibl_codes([tc])[0].startswith("#!ibl edition=2\n")
    out = AR.record_usage(_presented(), tool_calls=[tc])
    assert out[0]["used"] == ["4878"] and out[0]["evidence"] == "executed"


def test_explicit_edition_or_header_is_kept_as_is():
    one = authoring_request({"code": "[self:read]{path: \"a\"}", "edition": 1})
    assert one["edition"] == 1
    headed = authoring_request({"code": "#!ibl edition=2\nreturn 1"})
    assert "edition" not in headed


def test_pipeline_record_site_normalizes_before_both_appends():
    """기록 자리(agent_pipeline tool_start)가 execute_ibl 입력을 authoring_request 로 정규화한 뒤
    증류용·평가용 두 목록에 같은 입력을 적는다 — 정규화는 이 한 자리."""
    src = Path(__file__).with_name("cognition").joinpath("agent_pipeline.py").read_text(encoding="utf-8")
    m = re.search(r'if et == "tool_start":(.*?)elif et == "tool_result":', src, re.DOTALL)
    assert m, "tool_start 분기를 찾지 못함"
    block = m.group(1)
    norm = block.find("authoring_request(_input)")
    log_append = block.find('tool_calls_log.append({"tool_name": _name, "input": _input')
    eval_append = block.find('"input": _input,')
    assert 0 <= norm < log_append and norm < eval_append
    assert 'ev.get("input", {})' not in block[norm:]      # 정규화 뒤엔 원입력을 다시 적지 않는다


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
