"""타 언어 주석 표식은 진단과 함께 거절된다 (2026-08-31).

사건(ep2455, AI 동향 보고서 04:07): Codex 가 4-액션 배치 앞줄에
`// 투자·경제: 한국어/영어 4회` 를 달았다. IBL 의 주석 표식은 `#` 하나뿐이라 그 줄은
문장으로 파싱을 시도하다 실패했고, 봉투는 `IBL 실행 오류: 파싱 실패: // 투자·경제:
한국어/영어 4회` 한 줄만 돌려줬다 — **무엇이 틀렸는지 안 적혀 있어** 모델이 자가교정할
근거가 없었고, 배치 하나가 통째로 버려졌다.

모델은 자기 모어(母語)의 주석 표식을 그대로 쓴다. 이건 한 모델의 실수가 아니라 부류다.

수리의 축은 둘이고, 여기서 지키는 건 둘째다:
  ① 예방 — 프롬프트(fragments/12_ibl_only.md 'Common Mistakes')가 `#` 가 유일한 주석
     표식임을 WRONG/RIGHT 로 못박는다.
  ② 진단 — 그래도 새어 들어오면 거절문이 정답 형태를 동반한다(F16-1 분기 헤더 진단과 같은 축).

★`//` 를 주석으로 *받아들이지는* 않는다. 주석 표식은 문법이고, 문법 변경은 언어 개정
(사용자 판정 사안)이다. 이 관문이 지키는 계약은 "거절하되 가르친다" 뿐이다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
for _p in ("", "base", "cognition", "datastore", "ibl", "services", "surface", "common"):
    _d = os.path.join(BACKEND, _p) if _p else BACKEND
    if _d not in sys.path:
        sys.path.insert(0, _d)

import boot_paths  # noqa: F401,E402  (독립 스크립트 규약)
from ibl.ibl_parser import parse, IBLSyntaxError  # noqa: E402

PROMPT = os.path.join(os.path.dirname(BACKEND), "data", "common_prompts",
                      "fragments", "12_ibl_only.md")

# (코드, 표식) — 줄머리와 꼬리 두 자리를 모두 덮는다(파서의 실패 지점이 다르다:
# 줄머리는 문장 파싱 실패, 꼬리는 '해석되지 않은 잔여' 검사).
HEAD_CASES = [
    ('// 1단계\n[sense:search]{query: "a"}', "//"),
    ('/* 1단계 */\n[sense:search]{query: "a"}', "/*"),
    ('-- 1단계\n[sense:search]{query: "a"}', "--"),
    ('<!-- 1단계 -->\n[sense:search]{query: "a"}', "<!--"),
]
TAIL_CASES = [
    ('[sense:search]{query: "a"} // 꼬리', "//"),
    ('[sense:search]{query: "a"} -- 꼬리', "--"),
]


@pytest.mark.parametrize("code,mark", HEAD_CASES + TAIL_CASES)
def test_foreign_comment_is_rejected_with_the_remedy(code, mark):
    """거절하되 가르친다 — 표식 이름과 `#` 정답 형태가 오류문에 함께 온다."""
    with pytest.raises(IBLSyntaxError) as ei:
        parse(code)
    msg = str(ei.value)
    assert mark in msg, f"어떤 표식이 문제인지 안 적혀 있다: {msg}"
    assert "`#`" in msg, f"정답 형태(`#`)가 오류문에 없다 — 자가교정을 못 이끈다: {msg}"


def test_hash_comment_and_markdown_body_still_parse():
    """대조군 — 진짜 주석과 문자열 속 `#` 는 그대로 산다(과잉 차단 방지).

    ★문자열 보호(D3)를 되밟는다: content 안의 마크다운 헤딩이 주석으로 오인되면
    [self:write] 본문이 조용히 손상된다.
    """
    parse('# 진짜 주석\n[sense:search]{query: "a"}')
    parse('[sense:search]{query: "a"} >> [table:take]{n: 3}')
    steps = parse('[self:write]{path: "x.md", content: "# 마크다운 헤딩\n본문"}')
    body = steps[0]["params"]["content"]
    assert "# 마크다운 헤딩" in body and "본문" in body, f"문자열 속 헤딩이 깎였다: {body!r}"


def test_prompt_documents_the_single_comment_mark():
    """예방 축 — 프롬프트가 `#` 가 유일한 주석 표식임을 실제로 적고 있다.

    진단만 남고 예방이 사라지면 매 호 같은 라운드를 버린다(crystallized-but-unrouted).
    """
    src = open(PROMPT, encoding="utf-8").read()
    assert "//" in src and "주석" in src, "프롬프트에 주석 표식 규약이 없다"
    assert "`#`" in src or "# 1단계" in src, "정답 형태(`#`)가 프롬프트에 없다"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
