"""네이티브 통짜 이미지 슬라이드 — NotebookLM식 '한 장 통째 저작'.

[engines:slide]{style: "native"} 경로.

기존 두 경로(텍스트형 custom_html, 프리미엄 일러스트 slide_image)는 모두 **2층 구조**다:
글자는 HTML/CSS 타이포 레이어, 그림은 별도 일러스트 — 둘을 합성한다. 그래서 일러스트가
'개념을 나르는 시각 장치'가 되기 어렵고(글자가 다른 레이어에 있으니 등식·다이어그램이 그림의
일부가 될 수 없다), 결과적으로 그림은 장식, 글은 받아쓰기에 머무른다.

이 모듈은 정반대다. **이미지 모델(Nano Banana Pro)이 한글 타이포·다이어그램·일러스트를
하나의 컴포지션으로 통째로 저작**한다 — NotebookLM이 하는 그 방식. 합성층이 없다.

흐름:
  1) 저작 AI(텍스트 LLM) — 원고 문단을 **한 장 한 명제**로 큐레이션:
       제목(명제) + 시각 수사 장치(등식·흐름·대비·은유…) + 화면에 박을 **정확한 한글 문자열** +
       영어 장면/레이아웃 지시.  ← "내용을 이해한 느낌"은 여기서 나온다.
  2) 이미지 생성 — 위 브리프를 한 프롬프트로 묶어 gemini-3-pro-image-preview가 16:9 한 장 렌더.
  3) (선택) 검증 — Vision OCR로 한글이 정확/또렷하게 박혔는지 읽어보고, 깨지면 재생성.
     비라틴 텍스트 깨짐이 이 경로의 유일한 실질 리스크 → 읽기-검증이 안전망.
"""
import os, re, json, base64, importlib.util, sys

import httpx


# ─────────────────────────────────────────────────────────────────────
# 설정/공통
# ─────────────────────────────────────────────────────────────────────

def _system_ai_config() -> dict:
    from runtime_utils import get_base_path
    p = get_base_path() / "data" / "system_ai_config.json"
    if p.exists():
        return json.load(open(p, encoding="utf-8"))
    return {"provider": "anthropic", "model": "", "apiKey": ""}


def _gemini_key() -> str:
    """Gemini 이미지/Vision API 키. 정식 경로(generate_gemini_image)와 동일하게 GEMINI_API_KEY env
    우선 — system_ai provider가 claude_code/anthropic일 때 그 apiKey는 Gemini 키가 아니므로.
    폴백으로만 system_ai apiKey(provider가 google일 때 유효)를 본다."""
    return (os.environ.get("GEMINI_API_KEY")
            or (_system_ai_config().get("apiKey") or "").strip())


def _fix_json_escapes(s: str) -> str:
    """JSON에서 유효하지 않은 백슬래시 이스케이프를 리터럴로 교정.
    유효 이스케이프: \\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX. 그 외 백슬래시(\\u 뒤 비-16진 포함)는
    리터럴 백슬래시로 보고 이중화해 json.loads가 깨지지 않게 한다.
    (저작 모델 응답이 'Invalid \\uXXXX escape'로 파싱 실패하던 버그 방어 — 2026-06-23 관측.)"""
    return re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', s)


def _extract_json(text: str) -> dict:
    if not text:
        raise ValueError("AI 응답이 비어 있습니다.")
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    cand = m.group(1) if m else None
    if cand is None:
        a, b = text.find("{"), text.rfind("}")
        if a == -1 or b <= a:
            raise ValueError("JSON 없음: " + text[:200])
        cand = text[a:b + 1]
    try:
        return json.loads(cand)
    except json.JSONDecodeError:
        # 잘못된 이스케이프 교정 후 재시도 (저작 모델이 가끔 \u·스트레이 백슬래시를 흘림)
        return json.loads(_fix_json_escapes(cand))


def _clean_text(s):
    """저작 모델이 가끔 섞는 U+FFFD 대체문자·제어문자 제거(개행/탭만 허용).
    이게 제목/라벨에 남으면 덱 메타와 이미지 프롬프트가 깨진다(관측: '그�럴듯한')."""
    if not isinstance(s, str):
        return s
    s = s.replace("�", "")
    s = "".join(ch for ch in s if ch >= " " or ch in "\n\t")
    return s.strip()


def _sanitize_spec(spec: dict) -> dict:
    """spec의 사람이 읽는 문자열 필드를 정제(이미지에 박힐 한글이 깨지지 않게)."""
    for k in ("title", "scene_en", "reasoning", "device"):
        if isinstance(spec.get(k), str):
            spec[k] = _clean_text(spec[k])
    kt = spec.get("korean_texts")
    if isinstance(kt, list):
        spec["korean_texts"] = [_clean_text(t) for t in kt if _clean_text(t)]
    return spec


# ─────────────────────────────────────────────────────────────────────
# 미적 톤(aesthetic) — 한 덱을 한 톤으로 고정하면 NotebookLM처럼 일관된 '책'이 된다.
# design_system 어휘와 맞물려 사용자가 기존 단어로 고를 수 있게 한다.
# 값 = 이미지 모델에 줄 '아트 디렉션' 문장(팔레트·재질·서체 분위기). 글자도 이 톤으로 렌더된다.
# ─────────────────────────────────────────────────────────────────────

AESTHETICS = {
    "vintage_book": {
        "ko": "빈티지 교과서",
        "art": ("Premium vintage editorial textbook aesthetic. Warm cream paper with faint grain, "
                "deep navy ink and warm terracotta accents, refined serif Korean typography, subtle "
                "blueprint grid and fine hand-drawn ink diagrams. Elegant, scholarly, restrained."),
    },
    "academic_paper": {
        "ko": "학술 페이퍼",
        "art": ("Clean academic paper aesthetic. Crisp white background, charcoal text, a single "
                "scholarly blue accent, generous margins, precise thin-line diagrams and labeled "
                "figures, neutral sans-serif Korean typography. Calm, rigorous, uncluttered."),
    },
    "tech_minimal": {
        "ko": "테크 미니멀",
        "art": ("Modern tech-minimal aesthetic. Near-white or soft cool-grey background, near-black "
                "Korean type, one vivid accent (electric blue or orange), lots of negative space, "
                "clean geometric infographic shapes and flow arrows. Confident, contemporary, sharp."),
    },
    "magazine_modern": {
        "ko": "모던 매거진",
        "art": ("Bold modern magazine editorial aesthetic. Strong typographic hierarchy with very large "
                "Korean display headline, confident color blocking, one or two saturated accents, "
                "dynamic asymmetric layout, high contrast. Striking and stylish."),
    },
    "dark_keynote": {
        "ko": "다크 키노트",
        "art": ("Cinematic dark keynote aesthetic. Deep near-black background, luminous white Korean "
                "type, a glowing teal-and-amber accent, soft volumetric light, sleek glass and chrome "
                "diagram elements, subtle particle depth. Dramatic, premium, focused."),
    },
    "blueprint": {
        "ko": "청사진 다이어그램",
        "art": ("Technical blueprint diagram aesthetic. Warm off-white or pale blue ground, indigo "
                "linework, coral highlight, faint grid and leader lines, precise schematic figures and "
                "annotated parts, mono-style labels. Engineered, clear, intellectual."),
    },
}

_DEFAULT_AESTHETIC = "vintage_book"


def _resolve_aesthetic(tool_input: dict) -> dict:
    """aesthetic 또는 design_system 키로 톤을 고른다. 별칭/미지정은 기본값."""
    key = (tool_input.get("aesthetic") or tool_input.get("design_system") or "").strip()
    alias = {"default": _DEFAULT_AESTHETIC, "sf_blueprint": "blueprint", "minimal": "tech_minimal"}
    key = alias.get(key, key)
    return AESTHETICS.get(key, AESTHETICS[_DEFAULT_AESTHETIC])


def aesthetic_keys_help() -> str:
    return " / ".join(f"{k}({v['ko']})" for k, v in AESTHETICS.items())


# ─────────────────────────────────────────────────────────────────────
# 1) 저작 — 한 장 한 명제 큐레이션 + 시각 장치 + 박을 한글 문자열
# ─────────────────────────────────────────────────────────────────────

_AUTHOR_PROMPT = """당신은 NotebookLM 수준의 발표 슬라이드 한 장을 설계하는 정상급 아트디렉터 겸 편집자 AI다.
이미지 모델이 **글자·다이어그램·일러스트를 한 장에 통째로** 그릴 것이므로, 당신은 그 한 장의
'무엇을·어떻게'를 완전히 설계해 JSON 한 객체로만 출력한다.

# 절대 원칙 (NotebookLM이 잘하는 바로 그 일)
1. **한 장 = 한 명제. 전사(받아쓰기) 금지 — 재저작하라.** 원고 문단을 그대로 옮기는 것은 실패다.
   문단을 *읽고 이해한 뒤*, 그것이 말하려는 **단 하나의 핵심 주장**을 새로 벼려 제목으로 삼는다.
   제목은 라벨('AI의 역사')이 아니라 단정문('AI는 도구가 아니라 협업자가 되었다').
   ★단, instruction·근거(content)가 *자료의 프레임(핵심 주장)*을 담고 있으면 **그 프레임에 충실하라** —
   더 펀치 있지만 곁가지인 주장으로 갈아끼우지 마라. 예시를 주제로 착각하지 말 것
   (가장 정교한 부분 논증이나 가장 시각화하기 쉬운 조각이 곧 핵심 주장은 아니다).
2. **시각 수사로 극화.** 핵심을 글로 길게 쓰지 말고 **그림이 의미를 나르게** 한다. 내용에 맞는 장치를 *하나* 골라
   그 장치가 화면을 지배하게 한다(두 장치를 섞지 말 것):
   - equation(등식: A = B + C, 취소선 A ≠ B 같은 대조)
   - flow(흐름도: Input → 처리 → Output, 화살표·단계·붕괴)
   - comparison(좌우/상하 대비: 전·후, 우리·경쟁, 통념·진실 — 두 열의 대조 표/패널)
   - hierarchy(계층·구조: 포함·층위·분해, 동심원·피라미드·트리)
   - metaphor(은유 일러스트: 뇌+의수, 외골격 등 개념을 사물로)
   - bigfact(거대한 숫자/단어 하나로 충격)
   - matrix/timeline 등 내용이 요구하면 무엇이든.
3. **글자는 최소·키워드 단위.** 이미지 모델은 긴 문장을 깨뜨린다. 화면의 글자는 제목 + 라벨/짧은 캡션 몇 개로
   제한한다. **한 슬라이드의 한글 글자 총량은 대략 80자 이내**를 목표로 — 길어지면 잘못 설계한 것이다.
   문장이 길어질 것 같으면 키워드로 쪼개 라벨로 배치하라.
4. **제목은 상단의 또렷한 헤더로.** 덱 전체가 한 책처럼 보이도록, 제목은 화면 위쪽에 명확한 헤더로 둔다.
5. **근거 우선.** `참고 내용`이 있으면 거기서 사실·표현·고유명사를 가져오고 지어내지 말 것.

# 출력 JSON (이 스키마 그대로, 다른 텍스트 금지)
{
  "title": "화면 맨 위(또는 핵심 위치)에 들어갈 한글 명제. 18~34자.",
  "device": "equation|flow|comparison|hierarchy|metaphor|bigfact|matrix|timeline 중 하나",
  "korean_texts": [
    "화면에 '정확히 이 글자 그대로' 렌더돼야 하는 한글/기호 문자열들을 짧게 나열.",
    "예: 'AI ≠ Magic', 'AI = AI 모델 + 하네스', '입력: 고문맥', '출력: 헛소리'.",
    "제목도 여기에 포함. 항목당 짧게(키워드·짧은 구). 6개 이내 권장."
  ],
  "scene_en": "이미지 모델에 줄 '장면+레이아웃' 영어 지시. 시각 장치를 구체 사물·도형·화살표·관계로 묘사하고, 어떤 한글 텍스트가 화면 어디에(상단/중앙/좌/우/하단) 얼마나 크게 놓이는지 명시. 핵심 등식/다이어그램이 화면의 주인공이 되도록. 색·서체는 별도 아트디렉션이 입혀지니 여기선 구조·배치·은유에 집중.",
  "reasoning": "왜 이 명제·장치를 골랐는지 한 줄(한글)."
}

# 좋은 예 (등식)
{
  "title": "환상을 깨는 단 하나의 공식",
  "device": "equation",
  "korean_texts": ["환상을 깨는 단 하나의 공식", "AI ≠ Magic", "AI = AI 모델 + 하네스",
                   "현실에 개입하는 가장 흔한 오류는 'AI'를 '순수한 AI 모델'로 인식하는 것"],
  "scene_en": "A complete 16:9 lecture slide. Top: the Korean title as a clear header. Center stage, dominating the slide: a large typographic equation. First a struck-through line 'AI ≠ Magic' in muted tone with a hand-drawn diagonal strikethrough, then below it a bold large equation 'AI = AI 모델 + 하네스' where '하네스' is emphasized in the accent color. A thin caption line sits at the bottom. Generous calm margins; the equation is the hero.",
  "reasoning": "통념(마법)을 취소선으로 깨고 정의(모델+하네스)를 등식으로 못박는 게 이 문단의 단 하나의 주장."
}

# 좋은 예 (대비 comparison)
{
  "title": "자율주행이 아니라 함께 입는 외골격이다",
  "device": "comparison",
  "korean_texts": ["자율주행이 아니라 함께 입는 외골격이다", "자율주행 AI", "인지 외골격",
                   "목적지를 대신 정함", "목적지는 내가 정함", "판단을 위임", "판단을 증폭"],
  "scene_en": "A complete 16:9 lecture slide. Title as a header at the top. The body is split into two contrasting vertical panels of equal width. Left panel (cooler, muted tone) headed '자율주행 AI' shows a small figure asleep in a self-driving car. Right panel (warm, accent tone) headed '인지 외골격' shows a figure actively wearing a powered exoskeleton, in control. Under each header, two short Korean phrases as stacked labels. A faint divider down the middle. The two-column contrast is the hero.",
  "reasoning": "이 문단의 단 하나의 주장은 '대신함 vs 증폭함'의 대비 — 좌우 패널로 극화."
}
"""


def _get_author_ai():
    cfg = _system_ai_config()
    api_key = (cfg.get("apiKey") or "").strip()
    if not api_key:
        raise RuntimeError("시스템 AI API 키가 없습니다 (설정 → 시스템 AI).")
    from providers import get_provider
    prov = get_provider((cfg.get("provider") or "anthropic").strip(), api_key=api_key,
                        model=(cfg.get("model") or "").strip(), system_prompt=_AUTHOR_PROMPT, tools=[])
    prov.init_client()
    return prov


# ─────────────────────────────────────────────────────────────────────
# 2) 이미지 생성 — 한 장 통째 (Nano Banana Pro)
# ─────────────────────────────────────────────────────────────────────

_STYLE_REF_CLAUSE = (
    "\n\nSTYLE REFERENCE — the attached image is a PRIOR slide from this same deck, given ONLY so this "
    "slide shares the same house style: the same color palette, paper/texture, typography mood, margins "
    "and finish. Match that SURFACE STYLE. But do NOT copy its composition, its visual device "
    "(equation / comparison / flow / diagram / etc.), its headline, or its Korean text — the composition "
    "and device for THIS slide are dictated by the SCENE & LAYOUT above and must be followed even if they "
    "differ from the reference. Same look and feel, different structure and message."
)


def _build_image_prompt(spec: dict, art: str, has_references: bool = False) -> str:
    """저작 spec + 아트디렉션 → 이미지 모델 한 프롬프트. 한글을 '정확히' 박으라고 강제.

    has_references=True 이면 첨부된 앞뒤 슬라이드를 '스타일만' 참고하라는 절을 덧붙인다.
    """
    texts = [t for t in (spec.get("korean_texts") or []) if str(t).strip()]
    title = (spec.get("title") or "").strip()
    if title and title not in texts:
        texts.insert(0, title)
    text_block = "\n".join(f'   • "{t}"' for t in texts)
    scene = (spec.get("scene_en") or "").strip()

    prompt = (
        "Design a single, complete, polished 16:9 presentation slide — a finished slide, not an "
        "illustration. The slide must read as one unified composition where typography, diagram and "
        "imagery are designed together (NotebookLM / premium keynote quality).\n\n"
        f"ART DIRECTION (palette, material, type mood): {art}\n\n"
        f"SCENE & LAYOUT:\n{scene}\n\n"
        "KOREAN TEXT — render these strings EXACTLY as written, with correct, crisp, legible Hangul. "
        "Do not transliterate, translate, paraphrase, drop, or garble any character. Use clean, "
        "well-kerned Korean typography. Spell every syllable correctly:\n"
        f"{text_block}\n\n"
        "RULES: Only the Korean/symbol strings listed above may appear as text — render no other words, "
        "no Lorem Ipsus, no random Latin, no watermark. Keep text minimal and large; let the visual "
        "device (equation / diagram / metaphor) be the hero. Strong focal hierarchy, generous margins, "
        "nothing cut off at the edges. Cohesive professional color palette per the art direction."
    )
    if has_references:
        prompt += _STYLE_REF_CLAUSE
    return prompt


def _ref_image_parts(reference_images) -> list:
    """앞뒤 슬라이드 PNG 경로 리스트 → Gemini inlineData 파트 리스트(읽기 실패는 조용히 건너뜀)."""
    parts = []
    for p in (reference_images or []):
        try:
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            parts.append({"inlineData": {"mimeType": "image/png", "data": b64}})
        except Exception as e:
            print(f"[slide_native] 스타일 참고 이미지 읽기 실패 (건너뜀): {p} — {e}")
    return parts


def _gen_image(prompt: str, out_path: str, quality: str = "pro", image_size: str = "2K",
               reference_images=None) -> str:
    api_key = _gemini_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 없습니다 (.env 또는 환경변수).")
    model = {"pro": "gemini-3-pro-image-preview",
             "fast": "gemini-3.1-flash-image-preview"}.get(quality, "gemini-3-pro-image-preview")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    # 참고 이미지(앞뒤 슬라이드)를 텍스트 프롬프트 앞에 inlineData 파트로 첨부 — 스타일 일관성용.
    parts = _ref_image_parts(reference_images) + [{"text": prompt}]
    payload = {"contents": [{"parts": parts}],
               "generationConfig": {"responseModalities": ["IMAGE", "TEXT"],
                                    "imageConfig": {"aspectRatio": "16:9", "imageSize": image_size}}}
    with httpx.Client(timeout=300.0) as c:
        r = c.post(url, params={"key": api_key}, json=payload,
                   headers={"Content-Type": "application/json"})
        r.raise_for_status()
        data = r.json()
    for part in data["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            open(out_path, "wb").write(base64.b64decode(part["inlineData"]["data"]))
            return out_path
    raise RuntimeError(f"이미지 생성 실패: {json.dumps(data)[:300]}")


# ─────────────────────────────────────────────────────────────────────
# 3) 검증 — Vision OCR로 한글 정확/가독 확인 (이 경로의 유일한 실질 리스크 = 한글 깨짐)
# ─────────────────────────────────────────────────────────────────────

def _verify_text(img_path: str, required: list) -> dict:
    """렌더된 슬라이드에서 한글이 정확/또렷하게 박혔는지 Vision으로 확인.

    반환: {"passed": bool, "score": 0-10, "garbled": [...], "missing": [...], "notes": "..."}.
    ★fail-open: 키 부재·VLM 실패 시 {"passed": True, "_error": ...} — 검증은 게이트가 아니라 안전망.
    """
    api_key = _gemini_key()
    if not api_key:
        return {"passed": True, "_error": "no_api_key"}
    try:
        b64 = base64.b64encode(open(img_path, "rb").read()).decode()
    except Exception as e:
        return {"passed": True, "_error": f"read_fail: {e}"}

    req_block = "\n".join(f'- "{t}"' for t in required if str(t).strip())
    instruction = (
        "당신은 슬라이드 한글 텍스트 품질 검사자입니다. 이 슬라이드 이미지를 보고, 아래 '있어야 할 문자열'들이 "
        "**정확한 한글로(오탈자·깨짐 없이) 또렷하게** 렌더되어 있는지 확인하세요. 이미지 생성 모델이 한글을 "
        "잘못 그리면(없는 글자, 뭉개짐, 엉뚱한 자모) garbled에 넣고, 아예 안 보이면 missing에 넣으세요.\n\n"
        f"**있어야 할 문자열**:\n{req_block}\n\n"
        "JSON 한 개만 출력(다른 텍스트 금지):\n"
        '{"passed": true|false, "score": 0-10, "garbled": ["깨진 문자열"], "missing": ["빠진 문자열"], "notes": "1~2문장"}\n'
        "깨지거나 빠진 핵심 문자열이 있으면 passed=false. 모두 정확하고 읽기 좋으면 passed=true, score>=8."
    )
    payload = {"contents": [{"parts": [
        {"inlineData": {"mimeType": "image/png", "data": b64}},
        {"text": instruction},
    ]}], "generationConfig": {"temperature": 0.1, "responseModalities": ["TEXT"]}}
    last = None
    for model in ("gemini-3-pro-preview", "gemini-2.5-pro"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            with httpx.Client(timeout=120.0) as c:
                r = c.post(url, params={"key": api_key}, json=payload,
                           headers={"Content-Type": "application/json"})
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                data = r.json()
            parts = (data.get("candidates", [{}])[0].get("content", {}) or {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:]
                text = text.split("```")[0].strip()
            v = json.loads(text)
            v["passed"] = bool(v.get("passed"))
            return v
        except Exception as e:
            last = e
            continue
    return {"passed": True, "_error": f"vlm_fail: {last}"}


def _gen_with_verify(spec, art, base_img_path, output_base, base, quality, image_size, max_rounds,
                     reference_images=None):
    """생성→한글검증→재생성 루프. 최고본의 (path, verdict, attempts) 반환.

    통과하거나 검증 fail-open이면 종료. 못 통과하면 최고 점수본 채택.
    재생성 라운드는 깨진/빠진 문자열을 프롬프트에 '이 글자를 정확히' 강조로 되먹인다.
    reference_images: 앞뒤 슬라이드 PNG 경로 — 스타일 참고용으로 매 라운드 첨부.
    """
    required = list(spec.get("korean_texts") or [])
    if spec.get("title") and spec["title"] not in required:
        required.insert(0, spec["title"])
    base_prompt = _build_image_prompt(spec, art, has_references=bool(reference_images))
    attempts = []
    best_path, best_verdict, best_score = None, None, -1.0
    cur_prompt = base_prompt
    for rnd in range(1, max_rounds + 1):
        path_r = base_img_path if rnd == 1 else os.path.join(output_base, f"{base}_r{rnd}.png")
        _gen_image(cur_prompt, path_r, quality=quality, image_size=image_size,
                   reference_images=reference_images)
        verdict = _verify_text(path_r, required)
        try:
            score = float(verdict.get("score")) if verdict.get("score") is not None else 0.0
        except Exception:
            score = 0.0
        attempts.append({"round": rnd, "passed": verdict.get("passed"), "score": verdict.get("score"),
                         "garbled": verdict.get("garbled"), "missing": verdict.get("missing"),
                         "error": verdict.get("_error")})
        if score > best_score:
            best_path, best_verdict, best_score = path_r, verdict, score
        if verdict.get("_error") or verdict.get("passed"):
            best_path, best_verdict = path_r, verdict
            break
        if rnd < max_rounds:
            bad = (verdict.get("garbled") or []) + (verdict.get("missing") or [])
            fix = "\n".join(f'   • "{b}"' for b in bad if str(b).strip())
            cur_prompt = (
                base_prompt +
                "\n\nCRITICAL FIX — the previous attempt rendered these Korean strings WRONG (garbled "
                "or missing). Render them again, perfectly, every Hangul syllable correct and legible:\n"
                f"{fix}"
            )
    return best_path, best_verdict, attempts


# ─────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────

def edit_native_slide(tool_input: dict, base_image_path: str, output_base: str, slide_id: str) -> str:
    """기존 통짜 이미지 슬라이드를 '부분 수정' — 다시 그리지 않고 현재 이미지를 편집한다.

    현재 PNG(base_image_path)를 이미지 모델에 입력으로 주고 "instruction이 시키는 부분만 바꾸고
    나머지는 그대로 두라"고 지시한다. 전면 재생성보다 구도·그림·다른 글자를 보존한다
    (완전 픽셀 동일은 보장 못 함 — 이미지 모델 편집의 한계).

    결과 PNG는 {output_base}/{slide_id}.png 에 덮어쓴다(제자리 수정).
    """
    instruction = (tool_input.get("instruction") or "").strip()
    if not instruction:
        return json.dumps({"success": False, "message": "instruction은 필수입니다."}, ensure_ascii=False)
    if not os.path.exists(base_image_path):
        return json.dumps({"success": False, "message": f"원본 이미지 없음: {base_image_path}"}, ensure_ascii=False)
    quality = (tool_input.get("quality") or "pro").strip()
    image_size = (tool_input.get("image_size") or "2K").strip()

    edit_prompt = (
        "You are given a FINISHED 16:9 presentation slide image. Edit it MINIMALLY according to the "
        "instruction below. Change ONLY what the instruction asks. Keep the ENTIRE rest of the slide "
        "visually identical — the same layout, background, palette, illustration/diagram, and every "
        "other text element in the same position and style. Preserve the existing Korean typography "
        "look. Render any new or changed Korean text EXACTLY as specified, with correct, crisp, "
        "legible Hangul; do not add, drop, move, or garble any other text.\n\n"
        f"EDIT INSTRUCTION (Korean): {instruction}"
    )
    os.makedirs(output_base, exist_ok=True)
    out_path = os.path.join(output_base, f"{slide_id}.png")
    try:
        # 현재 이미지를 입력으로 첨부해 편집 (reference_images 메커니즘 재사용 — 파트는 텍스트 앞에 둠).
        # _ref_image_parts가 호출 전에 파일을 메모리로 읽으므로 out_path == base_image_path 덮어써도 안전.
        _gen_image(edit_prompt, out_path, quality=quality, image_size=image_size,
                   reference_images=[base_image_path])
    except Exception as e:
        return json.dumps({"success": False, "message": f"이미지 편집 실패: {e}"}, ensure_ascii=False)

    return json.dumps({
        "success": True, "image_path": out_path,
        "message": "통짜 이미지 부분 수정 완료(기존 그림 유지).",
    }, ensure_ascii=False)


def create_native_slide(tool_input: dict, output_base: str, slide_id: str = None) -> str:
    """[engines:slide]{style:"native"} — 통짜 이미지 슬라이드 1장 저작·생성·검증.

    slide_id가 있으면 출력 파일명을 {slide_id}.png 로 고정(강의창 통합용).
    """
    instruction = (tool_input.get("instruction") or "").strip()
    if not instruction:
        return json.dumps({"success": False, "message": "instruction은 필수입니다."}, ensure_ascii=False)
    content = (tool_input.get("content") or "").strip()
    quality = (tool_input.get("quality") or "pro").strip()
    image_size = (tool_input.get("image_size") or "2K").strip()
    # 앞뒤 슬라이드 PNG 경로 — 같은 덱의 톤·레이아웃 언어를 스타일만 참고(내용 복제 금지).
    reference_images = [
        p for p in (tool_input.get("style_reference_images") or [])
        if isinstance(p, str) and os.path.exists(p)
    ]
    art_def = _resolve_aesthetic(tool_input)
    art = art_def["art"]

    # 1) 저작 (한 장 한 명제 큐레이션)
    parts = [f"# 만들 슬라이드\n{instruction}"]
    if content:
        parts.append(f"\n# 참고 내용 (이 사실·표현에서 가져오고 지어내지 말 것)\n{content[:12000]}")
    parts.append(f"\n# 미적 톤\n{art_def['ko']} — 위 JSON 스키마 그대로 한 객체만 출력하라.")
    user = "\n".join(parts)
    try:
        ai = _get_author_ai()
        resp = ai.process_message(user, history=[], images=[], execute_tool=None)
        spec = _sanitize_spec(_extract_json(resp))
    except Exception as e:
        return json.dumps({"success": False, "message": f"저작 실패: {e}"}, ensure_ascii=False)

    if not (spec.get("scene_en") or "").strip():
        return json.dumps({"success": False, "message": "scene_en 누락", "spec": spec}, ensure_ascii=False)

    # 2) 이미지 생성 (+ 검증 루프)
    os.makedirs(output_base, exist_ok=True)
    base = slide_id if slide_id else f"slide_native_{spec.get('device', 'x')}"
    img_path = os.path.join(output_base, f"{base}.png")
    _v = tool_input.get("verify", True)
    verify_on = _v if isinstance(_v, bool) else str(_v).strip().lower() not in ("false", "0", "no", "off")
    rounds = max(1, int(tool_input.get("verify_rounds") or 2))
    verdict, attempts = None, []
    try:
        if verify_on:
            img_path, verdict, attempts = _gen_with_verify(
                spec, art, img_path, output_base, base, quality, image_size, rounds,
                reference_images=reference_images)
        else:
            _gen_image(_build_image_prompt(spec, art, has_references=bool(reference_images)),
                       img_path, quality=quality, image_size=image_size,
                       reference_images=reference_images)
    except Exception as e:
        return json.dumps({"success": False, "message": f"이미지 생성 실패: {e}", "spec": spec},
                          ensure_ascii=False)

    result = {
        "success": True, "image_path": img_path, "title": spec.get("title"),
        "device": spec.get("device"), "aesthetic": art_def["ko"], "reasoning": spec.get("reasoning"),
        "korean_texts": spec.get("korean_texts"), "spec": spec,
        "message": f"네이티브 통짜 슬라이드 1장 ({art_def['ko']} · {spec.get('device')}).",
    }
    if verdict is not None:
        result["verify"] = {
            "passed": verdict.get("passed"), "score": verdict.get("score"),
            "garbled": verdict.get("garbled"), "missing": verdict.get("missing"),
            "notes": verdict.get("notes"), "error": verdict.get("_error"), "rounds": len(attempts),
        }
        n = len(attempts)
        if verdict.get("_error"):
            result["message"] += f" (한글검증 건너뜀: {verdict.get('_error')})"
        elif n > 1:
            verb = "통과" if verdict.get("passed") else "최고점 채택"
            result["message"] += f" — 한글검증 {n}라운드 후 {verb}(score={verdict.get('score')})"
    return json.dumps(result, ensure_ascii=False)
