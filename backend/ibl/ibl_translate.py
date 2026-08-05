"""IBL 번역(자연어→IBL 컴파일) 공용 조각 — api_ibl 에서 이동 (2026-08-05 감사 ⑦).

왜 분리: 조종실 번역기의 task 프레이밍·교재 로더·출력 정제기를 body_ask(인지층,
몸 간 부탁의 컴파일러)가 재사용하는데, 그것이 라우터 모듈(api_ibl)에 살아
인지층→표면 역방향 import 를 만들었다. 언어층(IBL)의 것이므로 여기가 정본.
소비자 둘: api_ibl(/ibl/translate) · body_ask(_compile_cockpit/_compile_gemini).
"""

import re


# 모델은 선장이 아니라 컴파일러다. 자연어를 IBL로 "번역"만 하고,
# 지능(주권)은 인간 + 언어(IBL)에 남는다. 검수는 코드가 아니라 효과(dry-run)로 한다.

# 번역 task 프레이밍 — IBL 문법은 아래 정식 교재(12_ibl_only.md)에 맡기고, 여기선 '번역만 하라'는 역할과 출력 규칙만 둔다.
_IBL_TRANSLATE_TASK = """너는 IBL(IndieBiz Logic) 컴파일러다. 사용자의 자연어 명령을 IBL 코드로 번역만 한다.
아래 <ibl_spec>가 IBL 문법·노드 체계·패턴의 정식 명세다 (모든 에이전트가 쓰는 교재). 이대로 따르라.

규칙:
1. 아래 '참고 용례'에 나온 실제 액션 이름만 사용하라. 지어내지 마라.
2. IBL 원문만 출력하라 — execute_ibl('...') 같은 호출 래퍼, 따옴표, 코드블록 표시(```), 설명·인사 모두 금지. [node:action]{...} 으로 시작해서 끝나야 한다.
3. 의도가 모호하면 가장 단순하고 되돌릴 수 있는 해석을 택하라."""


def _load_ibl_spec() -> str:
    """모든 에이전트가 받는 정식 IBL 교재(12_ibl_only.md)를 그대로 읽는다.
    수동 모드 번역기도 같은 문법 진실 소스를 쓰게 해 중복을 없앤다 (사람-페이스라 매번 읽어도 무방)."""
    try:
        from runtime_utils import get_base_path
        p = get_base_path() / "data" / "common_prompts" / "fragments" / "12_ibl_only.md"
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _strip_code_fence(text: str) -> str:
    """모델 출력에서 IBL 원문만 추출. 앞의 펜스/설명/execute_ibl( 래퍼와
    뒤의 따옴표/괄호 잔여물(예: ...}')))을 모두 떼어낸다."""
    t = (text or "").strip()
    # ```lang ... ``` 펜스 제거
    fence = re.search(r"```[a-zA-Z]*\s*(.+?)\s*```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    # 첫 [node:action] 부터 채택 (앞에 execute_ibl(' 같은 래퍼·설명이 붙은 경우)
    m = re.search(r"\[[a-z_]+:[a-z_]+\]", t)
    if m:
        t = t[m.start():].strip()
    # 마지막 } 또는 ] 이후는 잘라낸다 (execute_ibl('...') 흉내의 ') 꼬리, 후행 설명 제거)
    last = max(t.rfind("}"), t.rfind("]"))
    if last != -1:
        t = t[:last + 1]
    return t
