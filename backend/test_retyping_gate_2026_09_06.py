"""되받아쓰기 관문 — 일반 관문(2026-09-06, 사용자: "경우마다 막을 수 없다, 일반적으로 막아라").

모델이 친 긴 문자열 인자를 이 턴의 변수 값·직전 결과 그림자·대상 파일 현재 내용과 대조해 봉투가 말하고(warn),
파일 통째 재작성급이면 실행 전 거절(refuse). 어휘 이름 무관. 임계는 lifecycle_policy.yaml `retyping:`.
+ 초안 인계(code:"$초안") · 반성 수치 줄(되받아쓰기·가리킴) · 평가자 응답 형식.

실행: .venv/bin/python -m pytest -q backend/test_retyping_gate_2026_09_06.py
"""
import json
import uuid

import pytest

from system_tools import _execute_ibl_unified
from thread_context import actor_context


def _run(code, tmp_path, task, **extra):
    with actor_context(agent_id="probe", task_id=task):
        raw = _execute_ibl_unified({"code": code, **extra}, str(tmp_path), agent_id="probe")
    try:
        return json.loads(raw)
    except Exception:
        return {"_text": raw}          # 일부 핸들러(edit)는 산문 한 줄을 돌려준다 — 봉투 표식 없음


@pytest.fixture
def task():
    return f"task_test_{uuid.uuid4().hex[:8]}"


ROWS = [{"단지": f"단지{i}아파트", "보증금": 24000 + i * 137, "url": f"https://x.test/item/{1000 + i}"} for i in range(25)]
ITEMS = json.dumps(ROWS, ensure_ascii=False)


def _prose():
    return "\n".join(f"- {r['단지']} 전세 보증금 {r['보증금']}만원 · [매물 보기]({r['url']}) — 조건 검토 대상" for r in ROWS)


def test_body_retyping_turn_var_data_is_flagged(tmp_path, task):
    first = _run(f'$표 = [table:take]{{items: {ITEMS}, n: 25}}', tmp_path, task)
    assert first.get("success") is True and first["turn_vars"]["live"] == ["표"]
    out = _run('[self:write]{path: "%s", content: "$file:0"}' % (tmp_path / "report.md"), tmp_path, task,
               files=[_prose()])
    rt = out.get("retyped")
    assert rt and rt["level"] == "warn", out
    assert rt["data_tokens"].split("/")[0] != "0" and "$표" in json.dumps(rt, ensure_ascii=False)
    assert "가리켜라" in rt["hint"]
    assert (tmp_path / "report.md").exists()          # warn 은 실행을 막지 않는다


def test_body_retyping_from_unnamed_previous_result_shadow(tmp_path, task):
    first = _run(f'[table:take]{{items: {ITEMS}, n: 25}}', tmp_path, task)      # 이름 없는 결과
    assert first.get("success") is True
    out = _run('[self:write]{path: "%s", content: "$file:0"}' % (tmp_path / "r2.md"), tmp_path, task, files=[_prose()])
    rt = out.get("retyped")
    assert rt and rt["level"] == "warn" and "직전 결과" in rt["sources"], out


def test_whole_file_rewrite_is_refused_even_without_task(tmp_path):
    target = tmp_path / "big.md"
    body = "\n".join(f"{i:03d} 이 줄은 파일에 이미 있는 내용이라 다시 칠 이유가 없다 — 줄범위 edit 이 맞다 {i}" for i in range(220))
    target.write_text(body, encoding="utf-8")
    out = json.loads(_execute_ibl_unified({"code": '[self:write]{path: "%s", content: "$file:0"}' % target,
                                           "files": [body]}, str(tmp_path), agent_id="probe_no_task"))
    assert out.get("success") is False and out.get("error_type") == "retyping", out
    assert out["retyped"]["level"] == "refuse" and out["retyped"]["file_verbatim_chars"] >= 8000
    assert target.read_text(encoding="utf-8") == body      # 실행 전 거절


def test_short_anchor_edit_is_not_flagged(tmp_path, task):
    target = tmp_path / "small.txt"
    target.write_text("alpha\nbeta gamma delta\nomega", encoding="utf-8")
    out = _run('[self:edit]{path: "%s", old_string: "beta gamma delta", new_string: "beta GAMMA delta"}' % target,
               tmp_path, task)
    assert "retyped" not in out, out


def test_new_content_without_sources_is_not_flagged(tmp_path, task):
    prose = "\n".join(f"새로 짓는 문장 {i} — 어디에도 없던 판단이다, 숫자도 없이 길게 쓴다 아무 데도 없는 글" for i in range(40))
    out = _run('[self:write]{path: "%s", content: "$file:0"}' % (tmp_path / "fresh.md"), tmp_path, task, files=[prose])
    assert out.get("success") is not False and "retyped" not in out, out


def test_draft_handoff_runs_stored_draft(tmp_path, task):
    from ibl_turn_vars import save_draft
    with actor_context(agent_id="probe", task_id=task):
        assert save_draft('$d = [table:take]{items: [{"k": 1}], n: 1}')
    out = _run("$초안", tmp_path, task)
    assert out.get("success") is True and out["turn_vars"]["live"] == ["d"], out
    other = _run("$초안", tmp_path, f"{task}_none")
    assert "초안이 없습니다" in other.get("error", "")


def test_cost_line_reports_retyping_and_pointing():
    from cognitive_trace import ibl_call_cost, run_cost_line
    calls = [
        {"tool_name": "execute_ibl", "input": {"code": "[fn:보고서]{주제: 1}"}, "success": True,
         "result": json.dumps({"retyped": {"verbatim_chars": 2500}, "turn_vars": {"injected": ["a", "b"]}})},
        {"tool_name": "execute_ibl", "input": {"code": "$a >> [table:take]{n: 1}", "files": ["x" * 300]}, "success": True,
         "retyped_chars": 0, "pointed": 1},
    ]
    c = ibl_call_cost(calls)
    assert c["retyped_chars"] == 2500 and c["retyped_warns"] == 1 and c["pointed"] == 3 and c["fn_calls"] == 1
    assert c["typed_chars"] >= 300
    line = run_cost_line(calls)
    assert "되받아쓰기 2.5K자(1회 경고)" in line and "가리킴 3회" in line and "[fn:] 1회" in line


def test_policy_is_data_and_prompts_carry_the_rules():
    from pathlib import Path
    from ibl_retyping import load_policy
    pol = load_policy()
    assert pol["refuse_file_verbatim_chars"] == 8000 and pol["warn_data_min_tokens"] == 20
    root = Path(__file__).resolve().parent.parent / "data" / "common_prompts"
    assert "미충족 항목만" in (root / "evaluator_prompt.md").read_text(encoding="utf-8")
    frag = (root / "fragments" / "12_ibl_only.md").read_text(encoding="utf-8")
    assert "경로 + 요지 3줄" in frag and "있는 것은 치지 말고 가리켜라" in frag


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
