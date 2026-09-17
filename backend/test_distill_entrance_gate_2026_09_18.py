"""낱말 증류 입구 관문 회귀 (2026-09-18) — 개인 명사·홈 경로·장문 본문은 코퍼스에 못 들어온다."""
import ast, os, sys
sys.path.insert(0, os.path.dirname(__file__)); import boot_paths  # noqa
from ibl_idiom import example_entrance_reason, EXAMPLE_CODE_CEILING


def test_home_path_in_code_rejected():
    assert example_entrance_reason("문서 읽기", '[self:read]{path: "/Users/someone/Desktop/a.md"}')


def test_home_path_in_intent_rejected():
    assert example_entrance_reason("/home/someone/notes 를 읽어줘", '[self:read]{path: "a.md"}')


def test_long_body_rejected():
    code = '[self:write]{path: "a.md", content: "' + "가" * (EXAMPLE_CODE_CEILING + 1) + '"}'
    assert "상한" in example_entrance_reason("메모 저장", code)


def test_plain_literal_example_passes():
    # 용례는 리터럴 든 단발이 정상 꼴 — 함수의 자(슬롯 0 거절)를 쓰지 않는다
    assert example_entrance_reason("서울 날씨", '[sense:weather]{city: "서울"}') is None
    assert example_entrance_reason("홈 아래 문서", '[self:read]{path: "~/Documents/a.md"}') is None


def test_distill_path_calls_the_gate_before_saving():
    src = open(os.path.join(os.path.dirname(__file__), "cognition", "ibl_usage_rag.py"), encoding="utf-8").read()
    assert src.index("example_entrance_reason(intent, code)") < src.index('source="distilled_component" if component else "distilled"')
    ast.parse(src)


if __name__ == '__main__':
    import sys, pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
