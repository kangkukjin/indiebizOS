"""심층메모리 증류 프롬프트의 날짜 앵커 회귀 시험.

사고(2026-08-30, ep2359): 추출 프롬프트에 오늘 날짜가 없어 경량 모델이 연도를
추측으로 채웠고, "8/31 예정"이 2025-08-31 중요날짜로 각인됐다. 기억은 태어나는
자리에서 절대 날짜여야 한다 — 이 시험은 앵커가 프롬프트에서 조용히 사라지는 것을 막는다.

실행: python3 backend/test_distill_date_anchor.py  (또는 pytest)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "cognition", "cognitive_distill.py")


def _extract_prompt_block() -> str:
    """_distill_deep_memory 의 extract_prompt f-string 본문을 소스에서 잘라낸다."""
    with open(_SRC, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r'extract_prompt = f"""(.*?)"""', src, re.DOTALL)
    assert m, "extract_prompt f-string 을 찾지 못함 (구조 변경 시 이 시험도 갱신)"
    return m.group(1)


def test_date_anchor_present():
    block = _extract_prompt_block()
    assert "{today}" in block, "추출 프롬프트에 오늘 날짜 앵커({today})가 없다"
    assert "연도" in block, "연도 명시·추측 금지 지시가 없다"


def test_today_is_computed_before_prompt():
    with open(_SRC, encoding="utf-8") as f:
        src = f.read()
    body = re.search(r"def _distill_deep_memory.*?extract_prompt = f", src, re.DOTALL)
    assert body and re.search(r"today\s*=", body.group(0)), \
        "extract_prompt 이전에 today 계산이 없다"


if __name__ == "__main__":
    # 러너는 하나 — pytest 에 위임 (test_single_runner 규약).
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
