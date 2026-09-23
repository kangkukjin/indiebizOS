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
IBL_TRANSLATE_TASK = """너는 IBL(IndieBiz Logic) 컴파일러다. 사용자의 자연어 명령을 IBL 코드로 번역만 한다.
아래 <ibl_spec>가 IBL 문법·노드 체계·패턴의 정식 명세다 (모든 에이전트가 쓰는 교재). 이대로 따르라.

규칙:
1. 아래 '참고 용례'에 나온 실제 액션 이름만 사용하라. 지어내지 마라.
2. IBL 원문만 출력하라 — execute_ibl('...') 같은 호출 래퍼, 따옴표, 코드블록 표시(```), 설명·인사 모두 금지. 현재 문법의 헤더 #!ibl edition=2와 프로그램 전체를 출력하라. 명시 인자·return·값 식을 사용하라.
3. 의도가 모호하면 가장 단순하고 되돌릴 수 있는 해석을 택하라."""


def load_ibl_spec() -> str:
    """모든 에이전트가 받는 정식 IBL 교재(12_ibl_only.md)를 그대로 읽는다.
    수동 모드 번역기도 같은 문법 진실 소스를 쓰게 해 중복을 없앤다 (사람-페이스라 매번 읽어도 무방)."""
    try:
        from runtime_utils import get_base_path
        p = get_base_path() / "data" / "common_prompts" / "fragments" / "12_ibl_only.md"
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def strip_code_fence(text: str) -> str:
    """바깥 코드 펜스만 벗긴다. 원문의 구문·헤더·마지막 식은 보존한다."""
    t = (text or "").strip()
    fence = re.fullmatch(r"```(?:ibl|text)?[ \t]*\n([\s\S]*?)\n```", t)
    return fence.group(1).strip() if fence else t


def translated_source(text: str) -> str:
    """새 작성 의미를 고정하고 실제 파서로 검사한다. 임의 텍스트 절단은 없다."""
    from ibl_edition import explicit_source
    from ibl_v2_parser import parse
    source = explicit_source(strip_code_fence(text), 2)
    parse(source)
    return source
