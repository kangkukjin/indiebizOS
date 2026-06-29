"""
[engines:slide] 저작 기층 액션 — 자연어 명령 한 줄 → 슬라이드 한 장(PNG).

slide_shadcn(렌더러)이 "완성된 spec → PNG"라면, 이 모듈은 그 위에 얇은 '저자(author)' 층을
올린다: 명령을 받아 **메시지 큐레이션 + 디자인 판단**까지 하고 자유형 슬라이드 한 장을 빚는다.
강의 워크스페이스에 의존하지 않는 독립 기층 — AI가 이 액션을 조합해 더 큰 산출물
(리포트→슬라이드, 검색결과→카드, 신문 요약→발표자료 등)을 만들 수 있게 한다.

호출: [engines:slide] {instruction, content?, design_system?, width?, height?, output_dir?}
"""

import os
import re
import json
import importlib.util
import sys


# ─────────────────────────────────────────────────────────────────────
# 저작 시스템 프롬프트 — 단일 슬라이드 저자
# ─────────────────────────────────────────────────────────────────────

_AUTHOR_SYSTEM_PROMPT = """당신은 슬라이드 한 장을 빚는 전문 저자 AI다. 매 호출마다 **단 한 장의 슬라이드 JSON 스펙**을 만든다.

# 핵심 원칙
1. **제목 = 명제** — 청중이 제목만 봐도 핵심을 얻는 단정문. 챕터명·라벨 금지.
   - ✗ "AI의 역사" (라벨) → ✓ "AI는 도구가 아니라 협업자가 되었다" (명제)
2. **한 슬라이드 = 한 아이디어** — 두 가지를 말하려 하지 말 것.
3. **본문은 키워드 단위** — 긴 문장 나열 금지. 핵심만 압축.
4. **수치·고유명사는 시각 요소로 격리** — 평문에 묻지 말고 강조 박스/큰 숫자로.
5. **근거 우선** — `참고 내용`이 주어지면 거기서 사실·표현을 가져오고 지어내지 말 것.

# 표현 방식 — 자유형(custom)이 기본 + 패턴 라이브러리 변주
이 액션의 강점은 **틀에 갇히지 않는 자유 디자인**이다. 기본적으로 `layout: "custom"` + `custom_html`로
내용에 맞는 배치를 직접 디자인하라(타임라인·플로우·계층·매트릭스·강조 등). **단 백지에서 짜지 말고,
아래 '레이아웃 패턴 라이브러리'에서 내용에 맞는 패턴을 골라 변주하는 것을 우선**하라(품질이 안정적이다).
패턴은 고정 틀이 아니라 출발점 — 색·아이콘·항목 수·구조를 내용에 맞게 조정하라. 단, 아래 단순 정형이
명백히 더 적합하면 고정 레이아웃을 써도 된다:
- `hero`: title, subtitle (표지·한 문장 임팩트)
- `lecture_body`: eyebrow, title, body, bullets[] (본문+불릿)
- `comparison_table`: eyebrow, title, headers[], rows[[...]] (텍스트 표)
- `factbox`: eyebrow, title, body, items[], source (수치·팩트)
- `quote`: quote, attribution, context (인용)

# 자유형(custom) 작성 규칙 — 반드시 지킬 것
custom_html은 선택된 디자인 시스템(vintage_book 등)의 CSS 래퍼 안에 삽입된다. 색·폰트가 자동으로
흐르게 하려면 **하드코딩 색상 금지**, 반드시 CSS 변수를 써라:
- 글자: `hsl(var(--foreground))` / 보조: `hsl(var(--muted-foreground))`
- 강조: `hsl(var(--accent))` / 배경: `hsl(var(--background))` / 면: `hsl(var(--muted))` / 테두리: `hsl(var(--border))`
- 사용 가능 자산: **Tailwind 유틸리티 클래스**, **animate.css**, **lucide 아이콘**(`<i data-lucide="이름"></i>`), 이모지, **인라인 SVG**.
- 시각 요소는 SVG/이모지/아이콘/CSS로 직접 그려라 — 이 액션은 **이미지 API를 호출하지 않는다**(빠르고 무료).
- 최상위 요소는 슬라이드 전체(1280×720)를 채운다: `<div class="w-full h-full ...">` 로 시작. 넘침 없이 여유 있게.
- 한글 텍스트는 HTML이므로 그대로 써도 된다.

# 출력 형식
**반드시 JSON 한 객체만** 반환(코드펜스 가능, 다른 설명 텍스트 금지):
```json
{
  "slide": {
    "layout": "custom",
    "title": "데크 목록 표시용 짧은 제목",
    "custom_html": "<div class=\\"w-full h-full flex flex-col p-16\\" style=\\"color: hsl(var(--foreground))\\">...</div>"
  },
  "reasoning": "왜 이 배치/레이아웃을 골랐는지 한 줄"
}
```
custom은 `title` + `custom_html` 두 필드면 충분. 고정 레이아웃을 쓰면 그 레이아웃의 필드를 채워라.
"""


# ─────────────────────────────────────────────────────────────────────
# AI provider (system_ai 설정 재사용)
# ─────────────────────────────────────────────────────────────────────

def _load_system_ai_config() -> dict:
    from runtime_utils import get_base_path
    cfg_path = get_base_path() / "data" / "system_ai_config.json"
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "apiKey": ""}


def _resolve_content_text_config() -> dict:
    """슬라이드 *텍스트* 모델을 모델 기어 'content_text' 역할(실행 축)로 해소.
    (슬라이드 이미지=Gemini 는 모달리티=기어 밖, 여기서 다루지 않는다.) 실패 시 옛 config 폴백."""
    try:
        from model_resolver import resolve
        d = resolve("content_text")
        if d.get("model"):
            return {"provider": d.get("provider", "anthropic"),
                    "model": d["model"], "apiKey": d.get("api_key", "")}
    except Exception:
        pass
    return _load_system_ai_config()


def _load_pattern_library() -> str:
    """같은 패키지의 slide_patterns.py 에서 패턴 라이브러리 텍스트 로드. 실패 시 빈 문자열."""
    try:
        module_path = os.path.join(os.path.dirname(__file__), "slide_patterns.py")
        spec = importlib.util.spec_from_file_location("slide_patterns", module_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["slide_patterns"] = mod
        spec.loader.exec_module(mod)
        return mod.render_pattern_library()
    except Exception as e:
        print(f"[slide_author] 패턴 라이브러리 로드 실패(무시): {e}")
        return ""


def _build_system_prompt() -> str:
    """저작 시스템 프롬프트 = 기본 원칙 + 패턴 라이브러리."""
    patterns = _load_pattern_library()
    return _AUTHOR_SYSTEM_PROMPT + ("\n\n" + patterns if patterns else "")


def _get_author_ai():
    """슬라이드 저작용 provider — 모델 기어 'content_text' 역할로 해소.
    (모듈이 호출마다 재로드되므로 매번 새로 빌드 — 무방.)"""
    cfg = _resolve_content_text_config()
    provider_name = (cfg.get("provider") or "anthropic").strip()
    api_key = (cfg.get("apiKey") or "").strip()
    # claude_code/ollama 는 자체 인증이라 키 불요.
    no_key = {"claude_code", "claude-code", "claudecode", "ollama"}
    if not api_key and provider_name.lower() not in no_key:
        raise RuntimeError(
            "텍스트 생성 모델 키가 설정되지 않았습니다. 모델 기어(실행 축) 또는 시스템 AI 설정을 확인하세요."
        )
    from providers import get_provider
    provider = get_provider(
        provider_name,
        api_key=api_key,
        model=(cfg.get("model") or "").strip(),
        system_prompt=_build_system_prompt(),
        tools=[],
    )
    provider.init_client()
    return provider


# ─────────────────────────────────────────────────────────────────────
# JSON 추출
# ─────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """AI 응답에서 JSON 객체 추출. 코드펜스/주변 텍스트 허용."""
    if not text:
        raise ValueError("AI 응답이 비어 있습니다.")
    # 코드펜스 우선
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = m.group(1) if m else None
    if candidate is None:
        # 첫 { 부터 마지막 } 까지
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("AI 응답에서 JSON을 찾지 못했습니다: " + text[:300])
        candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # 잘못된 이스케이프(\u 뒤 비-16진·스트레이 백슬래시) 교정 후 재시도
        fixed = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', candidate)
        return json.loads(fixed)


# ─────────────────────────────────────────────────────────────────────
# 렌더러 로드 (같은 패키지의 shadcn_slides 재사용)
# ─────────────────────────────────────────────────────────────────────

def _load_shadcn():
    module_path = os.path.join(os.path.dirname(__file__), "shadcn_slides.py")
    spec = importlib.util.spec_from_file_location("shadcn_slides", module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["shadcn_slides"] = mod
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────

def _load_module(fname: str, modname: str):
    path = os.path.join(os.path.dirname(__file__), fname)
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def create_slide(tool_input: dict, output_base: str) -> str:
    """명령 → 슬라이드 한 장 저작 + 렌더. JSON 문자열 반환.

    style이 프리미엄 이미지 프리셋(ink_blueprint/cinematic_3d/isometric/lineart_duotone)이면
    개념 일러스트 경로(slide_image)로 위임. 없으면 텍스트형 custom_html 경로(빠름·무료).
    """
    instruction = (tool_input.get("instruction") or "").strip()
    if not instruction:
        return json.dumps(
            {"success": False, "message": "instruction(만들 슬라이드 설명)은 필수입니다."},
            ensure_ascii=False,
        )

    # 스타일 — native(통짜 이미지)가 유일한 기본. 빠른 텍스트형만 style:"text"로 옵트아웃.
    # (2026-06-23 통합) 프리미엄 일러스트 경로(slide_image) 은퇴 — 미지정·옛 스타일값 전부 native로.
    style = (tool_input.get("style") or "").strip().lower()
    if style != "text":
        try:
            slide_native = _load_module("slide_native.py", "slide_native")
            return slide_native.create_native_slide(tool_input, output_base)
        except Exception as e:
            return json.dumps(
                {"success": False, "message": f"네이티브 슬라이드 처리 실패: {e}"}, ensure_ascii=False
            )

    # style == "text": 아래 텍스트형(custom HTML) 경로
    content = (tool_input.get("content") or "").strip()
    design_system = (tool_input.get("design_system") or "default").strip()
    width = int(tool_input.get("width") or 1280)
    height = int(tool_input.get("height") or 720)

    # 1) 저작 프롬프트
    parts = [f"# 만들 슬라이드\n{instruction}"]
    if content:
        parts.append(
            f"\n# 참고 내용 (이 사실·표현에서 가져오고 지어내지 말 것)\n{content[:12000]}"
        )
    parts.append(
        f"\n# 디자인 시스템\n선택된 design_system은 `{design_system}`이다. custom_html은 "
        f"이 톤의 CSS 변수를 상속하므로 색을 하드코딩하지 말고 `hsl(var(--foreground))` 등을 써라.\n"
        f"\n위 정보로 **단 한 장의 슬라이드 JSON**을 출력하라."
    )
    user_prompt = "\n".join(parts)

    # 2) AI 저작
    try:
        ai = _get_author_ai()
        response_text = ai.process_message(user_prompt, history=[], images=[], execute_tool=None)
    except Exception as e:
        return json.dumps(
            {"success": False, "message": f"슬라이드 저작 실패: {e}"}, ensure_ascii=False
        )

    try:
        parsed = _extract_json(response_text)
    except Exception as e:
        return json.dumps(
            {"success": False, "message": f"AI 응답 JSON 파싱 실패: {e}",
             "raw": response_text[:500]},
            ensure_ascii=False,
        )

    slide_spec = parsed.get("slide")
    if not isinstance(slide_spec, dict):
        return json.dumps(
            {"success": False, "message": "AI 응답에 'slide' 객체가 없습니다.",
             "raw": response_text[:500]},
            ensure_ascii=False,
        )

    # 3) 렌더 (slide_shadcn 재사용)
    try:
        shadcn = _load_shadcn()
        render_result_str = shadcn.create_shadcn_slides(
            {
                "slides": [slide_spec],
                "design_system": design_system,
                "output_dir": output_base,
                "width": width,
                "height": height,
            },
            output_base,
        )
        render = (
            json.loads(render_result_str)
            if isinstance(render_result_str, str)
            else render_result_str
        )
    except Exception as e:
        return json.dumps(
            {"success": False, "message": f"슬라이드 렌더 실패: {e}",
             "spec": slide_spec},
            ensure_ascii=False,
        )

    if not render.get("success"):
        return json.dumps(
            {"success": False, "message": f"렌더러 오류: {render.get('message') or render}",
             "spec": slide_spec},
            ensure_ascii=False,
        )

    images = render.get("images", [])
    htmls = render.get("html_files", [])
    return json.dumps(
        {
            "success": True,
            "image_path": images[0] if images else None,
            "html_path": htmls[0] if htmls else None,
            "title": slide_spec.get("title"),
            "layout": slide_spec.get("layout"),
            "design_system": design_system,
            "reasoning": parsed.get("reasoning"),
            "spec": slide_spec,
            "message": "슬라이드 1장을 생성했습니다.",
        },
        ensure_ascii=False,
    )
