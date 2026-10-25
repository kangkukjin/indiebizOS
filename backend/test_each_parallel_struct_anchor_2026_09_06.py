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
from test_ibl_v2_core import run, value, adapter
from ibl_v2_ir import Fault

ROWS = [{"v": i} for i in range(6)]


def _items(out):
    return [r for r in out.get("items") or []]


@pytest.mark.parametrize('parallel',[0,9,'x'])
def test_invalid_parallel_value_is_rejected(parallel):
    source='[1] >> [table:each]{parallel:'+json.dumps(parallel)+'}{return $it}'
    assert not run(source)['success']


def test_parallel_keeps_order_and_matches_sequential():
    source='$rows >> [table:each]{parallel:%d}{return {got:$it.v}}'
    sequential=value(source%1, inputs={'rows':ROWS})
    parallel=value(source%4, inputs={'rows':ROWS})
    assert sequential==parallel==[{'got':i} for i in range(6)]


def test_parallel_partial_failure_keeps_input_order():
    source='$rows >> [table:each]{parallel:%d,on_error:"collect"}{return 1/$it}'
    sequential=value(source%1,inputs={'rows':[0,1,0]})
    parallel=value(source%3,inputs={'rows':[0,1,0]})
    assert [r.ok for r in sequential]==[r.ok for r in parallel]==[False,True,False]
    assert parallel[1].value==1


def test_parallel_stop_reports_failure():
    result=run('[1,0,2] >> [table:each]{parallel:3}{return 1/$it}')
    assert not result['success']


def test_parallel_really_runs_concurrently():
    import threading
    barrier=threading.Barrier(4,timeout=5)
    def work(rt,args):
        barrier.wait()
        return args['n']
    registry={'test:work':adapter(work,{'n':'Number'},result='Number',effects=['pure'])}
    assert value('[0,1,2,3] >> [table:each]{parallel:4}{[test:work]{n:$it}}',registry=registry)==[0,1,2,3]


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
        return [{"tip": "출력 형식을 JSON 으로 고정한다", "timestamp": None, "_quote": "시스템 프롬프트에 출력 형식을"},
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
