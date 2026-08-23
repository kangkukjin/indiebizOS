r"""IBL 파라미터 문자열 이스케이프·침묵 절단 회귀 테스트 (2026-08-22)

ep1396(유튜브 AI 팁 보고서) 쓰기 경로 추적에서 나온 두 결함:

    E1. 느슨한 폴백이 `\n` 을 글자 `n` 으로 뭉갬       → 표준 이스케이프 해석
    E2. 값 안의 날 따옴표에서 content 가 조용히 절단  → IBLSyntaxError 정직 거절
    E3. 모르는 이스케이프(`\d` 등)가 글자로 뭉개짐     → 백슬래시째 보존
    E4. 조건 참조식이 파라미터 손실을 params={} 로 눙침 → None(유효하지 않은 참조)

배경: data/guides/youtube_ai_tips_report.md 2026-08-20 실측 ① — 이 결함 때문에
보고서 쓰기가 IBL 어휘를 떠나 Bash 히어독으로 이탈해 있었다.

실행: python3 backend/test_ibl_param_escape.py
"""
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401 — 층 디렉토리 등재

from ibl_parser import parse, IBLSyntaxError  # noqa: E402
from ibl_parser_values import _extract_string, _parse_params  # noqa: E402

# 느슨한 폴백을 반드시 타도록: JSON5 가 해석 못하는 모양(따옴표 없는 한글 키)
BS = chr(92)


def test_e1_newline_escape_decoded():
    """E1: 폴백 경로에서 \\n 이 진짜 개행이 된다 (예전엔 글자 'n')."""
    val, _ = _extract_string('"머리' + BS + 'n둘째' + BS + 't탭"', 0, '"')
    assert val == "머리\n둘째\t탭", repr(val)
    assert "n둘째" not in val, "백슬래시가 버려져 글자 n 이 박혔다"


def test_e1b_quote_and_backslash_still_right():
    """E1-b: 원래 우연히 맞던 \\" 와 \\\\ 는 그대로 맞아야 한다."""
    val, _ = _extract_string('"' + BS + '"인용' + BS + '" 그리고 ' + BS + BS + '역슬래시"', 0, '"')
    assert val == '"인용" 그리고 ' + BS + '역슬래시', repr(val)


def test_e1c_codepoint_escapes():
    """E1-c: \\uXXXX / \\xXX 해석."""
    val, _ = _extract_string('"' + BS + 'u0041' + BS + 'uAC00' + BS + 'x42"', 0, '"')
    assert val == "A가B", repr(val)


def test_e2_raw_quote_rejected_not_truncated():
    """E2: 값 안의 날 따옴표 → 조용한 절단이 아니라 IBLSyntaxError."""
    bad = ('[self:write]{path: "/tmp/rep.md", content: "# 보고서' + BS + 'n' + BS + 'n'
           '- **"한 수"는 이것이다.**' + BS + 'n- 둘째' + BS + 'n## 끝"}')
    try:
        steps = parse(bad)
    except IBLSyntaxError as e:
        msg = str(e)
        assert "끝까지" in msg, msg
        assert "이스케이프" in msg, "무엇을 고쳐야 하는지 말해야 한다: " + msg
        return
    got = steps[0].get("params", {}).get("content", "")
    raise AssertionError("조용히 통과했다 — content=%r (원문의 일부만 남음)" % got)


def test_e2b_escaped_report_survives_whole():
    """E2-b: 제대로 이스케이프한 같은 본문은 한 글자도 잃지 않는다."""
    good = ('[self:write]{path: "/tmp/rep.md", content: "# 보고서' + BS + 'n' + BS + 'n'
            '- **' + BS + '"한 수' + BS + '"는 이것이다.**' + BS + 'n- 둘째' + BS + 'n## 끝"}')
    content = parse(good)[0]["params"]["content"]
    assert content.count("\n") == 4, "줄이 뭉개졌다: %r" % content
    assert '"한 수"' in content, "따옴표가 사라졌다: %r" % content
    assert content.endswith("## 끝"), "꼬리가 잘렸다: %r" % content


def test_e3_unknown_escape_preserved():
    """E3: 정규식 \\d 가 글자 d 로 뭉개지면 [self:grep] 이 조용히 오작동한다."""
    val, _ = _extract_string('"^' + BS + 'd+' + BS + '*' + BS + '*헤딩"', 0, '"')
    assert val == "^" + BS + "d+" + BS + "*" + BS + "*헤딩", repr(val)


def test_e4_condition_ref_does_not_swallow():
    """E4: 조건 참조식이 파라미터 손실을 params={} 로 눙치지 않는다."""
    from ibl_executors import _parse_source_ref
    got = _parse_source_ref('sense:stock{ticker: "N"VDA"}.price')
    assert got is None or got[2].get("ticker"), (
        "파라미터를 잃은 채 유효한 참조인 척했다: %r" % (got,)
    )


def test_e5_healthy_inputs_unchanged():
    """E5: 멀쩡한 입력은 예전 그대로 통과해야 한다(과잉 거절 방지)."""
    ok = [
        ('{path: "/tmp/a.md", content: "머리' + BS + 'n둘째"}',
         {"path": "/tmp/a.md", "content": "머리\n둘째"}),
        ("{query: '한글', page: 1}", {"query": "한글", "page": 1}),
        ("{a: 1, b: true, c: null,}", {"a": 1, "b": True, "c": None}),
        ("{flags: [1, 2], nested: {x: 1}}", {"flags": [1, 2], "nested": {"x": 1}}),
        ("{}", {}),
    ]
    for text, want in ok:
        got = _parse_params(text)
        assert got == want, "%s → %r (기대 %r)" % (text, got, want)


def test_e6_multiline_indent_preserved():
    """F19-3: 물리 개행이 든 여러 줄 값에서 둘째 줄부터의 들여쓰기가 살아야 한다.

    옛 _preprocess 는 열린 문자열 안에서 시작하는 줄까지 strip() 해서,
    [self:write]/[self:edit] 로 쓴 파이썬이 IndentationError 로 즉사했다.
    """
    import ast
    NL = chr(10)
    body = NL.join(["    if x:", "", "        y = 1", "        return y", "    return 0"])
    code = '[self:edit]{path: "/tmp/a.py", old_string: "PASS", new_string: "' + body + '", regex: false}'
    params = parse(code)[0]["params"]
    new = params["new_string"]
    lines = new.split(NL)
    assert lines[2] == "        y = 1", "둘째 줄부터 들여쓰기가 깎였다: %r" % new
    assert lines[1] == "", "빈 줄이 사라졌다: %r" % new
    assert lines[4] == "    return 0", "꼬리가 어긋났다: %r" % new
    assert params.get("regex") is False, "여러 줄 값 뒤의 파라미터를 잃었다: %r" % params
    ast.parse("def f(x):" + NL + new + NL)


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
