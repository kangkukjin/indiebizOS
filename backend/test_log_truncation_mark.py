"""로그 절단 표식 회귀 (2026-08-22)

재현하는 결함(pitfall_silent_clamp 의 로그 판):
  ① episode_log 의 tool_use 인자가 300자에서 잘렸다 — 실측 2026-08-16~22 구간 IBL 호출
     1,723건 중 436건(25%). IBL 코드는 조합 구조가 사는 자리라, 잘린 뒤의 `>>`·`&`·`??`
     를 셀 수 없어 조합률 지표가 통째로 **하한**이 됐다.
  ② 잘린 양이 남지 않아, 읽는 쪽이 "짧은 호출"과 "잘린 호출"을 **정규식 실패로 추정**
     했다. 추정은 이스케이프가 깨진 값(2026-08-22 파서 수리 부류)을 절단으로
     오분류한다 — 깨짐과 절단은 서로 다른 사실이다.
  ③ 같은 사실을 두 모양으로 적었다 — tool_use 는 `...`, IBL_DEBUG 는
     `... [trunc, total=N]`. 읽는 쪽이 두 벌을 알아야 하는 이름 드리프트.

처방: 표식 모양·절단 함수를 base 층 한 벌(episode_logger)이 소유하고, 폭은 자리마다
값으로 두되 **자른 양을 반드시 신고**한다.

실행: .venv/bin/python -m pytest backend/test_log_truncation_mark.py
"""
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

from episode_logger import (TRUNC_MARK_RE, hidden_chars, strip_trunc_mark,
                            truncate_for_log)


# ── ① 표식 계약 ──────────────────────────────────────────────────────────────

def test_short_value_is_untouched_and_reads_as_complete():
    """cap 이하는 손대지 않는다 — 그리고 '완전 관측'으로 읽힌다."""
    s = '{"code": "[self:read]{path: \\"a.md\\"}"}'
    assert truncate_for_log(s, 300) == s
    assert hidden_chars(s) == 0
    assert not TRUNC_MARK_RE.search(s)


def test_truncated_value_reports_how_much_was_hidden():
    """잘린 양이 표식에 실린다 — 원문 길이 = cap + 숨긴 수."""
    src = "가" * 1000
    out = truncate_for_log(src, 300)
    assert hidden_chars(out) == 700
    assert len(strip_trunc_mark(out)) == 300
    assert 300 + hidden_chars(out) == len(src)


def test_reader_separates_truncation_from_a_broken_value():
    """★핵심: 깨진 값은 절단이 아니다.

    날 따옴표로 JSON 이 깨져 code 를 못 뜯는 줄과, 길어서 잘린 줄은 서로 다른 사실이다.
    옛 판은 둘 다 '정규식 실패'로 뭉뚱그려 절단으로 셌다."""
    broken = '{"code": "[self:write]{content: "따옴표"}"}'          # 짧지만 깨짐
    assert truncate_for_log(broken, 300) == broken
    assert hidden_chars(broken) == 0                                # 절단 아님

    long_ok = '{"code": "' + "[a:b]{} >> " * 60 + '"}'
    assert hidden_chars(truncate_for_log(long_ok, 300)) > 0         # 절단


# ── ② 프로바이더 자리 — IBL 코드만 폭이 넓다 ────────────────────────────────

def _tool_use_lines(events, capsys):
    from providers.claude_code import ClaudeCodeProvider
    p = ClaudeCodeProvider.__new__(ClaudeCodeProvider)
    p.agent_name = "시험"
    p._last_context_size = 0
    p._pending_map_tags = []
    for ev in events:
        p._translate_stream_event(ev, "", 0.0)
    return [l for l in capsys.readouterr().out.splitlines() if " tool_use " in l]


def _assistant(name, tool_input):
    return {"type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": "t1",
                                     "name": name, "input": tool_input}]}}


def test_ibl_code_gets_the_wide_cap_and_others_do_not(capsys):
    """같은 길이의 인자라도 execute_ibl 은 더 많이 남는다 — 조합 구조를 보려고."""
    from providers.claude_code import _TOOLUSE_CAP, _TOOLUSE_CAP_IBL
    assert _TOOLUSE_CAP_IBL > _TOOLUSE_CAP

    code = "[sense:search]{query: \"x\"} >> " * 40 + "[self:write]{path: \"o.md\"}"
    bash = "echo " + "y" * 2000
    lines = _tool_use_lines(
        [_assistant("mcp__indiebizos__execute_ibl", {"code": code}),
         _assistant("Bash", {"command": bash})], capsys)
    ibl_line, bash_line = lines[0], lines[1]

    # Bash 는 좁은 폭 그대로 — 무차별 확장이 아니다.
    assert hidden_chars(bash_line) > 0
    assert len(strip_trunc_mark(bash_line)) < len(strip_trunc_mark(ibl_line))
    # IBL 은 통째로 실린다(이 길이는 넓은 폭 안).
    assert hidden_chars(ibl_line) == 0
    assert '[self:write]{path: \\"o.md\\"}' in ibl_line   # 꼬리까지 실렸다


def test_long_ibl_payload_still_truncates_but_says_how_much(capsys):
    """폭은 넓혔을 뿐 무제한이 아니다 — 편집 payload(최대 5만 자 실측)는 여전히 자른다."""
    code = '[self:edit]{path: "a.py", old: "' + "가" * 5000 + '"}'
    line = _tool_use_lines(
        [_assistant("mcp__indiebizos__execute_ibl", {"code": code})], capsys)[0]
    assert hidden_chars(line) > 0
    from providers.claude_code import _TOOLUSE_CAP_IBL
    assert len(strip_trunc_mark(line).split(" tool_use ", 1)[1]) > _TOOLUSE_CAP_IBL - 100


# ── ③ 모양은 한 벌 ──────────────────────────────────────────────────────────

def test_ibl_debug_uses_the_same_mark_as_tool_use():
    """IBL_DEBUG 도 자기만의 모양(`[trunc, total=N]`)을 쓰지 않는다."""
    import cognition.system_tools_ibl as sti
    # ★경로는 판정 대상 모듈 자신에게 묻는다 (2026-08-31). 종전엔 저장소 루트 기준
    # 상대경로가 박혀 있어, pytest 를 backend/ 에서 돌리면 FileNotFoundError 로 죽었다 —
    # '통과도 실패도 아닌' 관문이 된다(pitfall_judge_home_pinned_path_checks).
    src = sti.__file__
    assert "[trunc, total={len(code)}]" not in open(src, encoding="utf-8").read()
    out = truncate_for_log("가" * (sti._IBL_DEBUG_CAP + 42), sti._IBL_DEBUG_CAP)
    assert hidden_chars(out) == 42


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
