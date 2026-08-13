"""
gemini_image.py - Gemini AI 이미지 생성/편집 ([engines:image_gemini])

handler.py 1500줄 규칙 분할(2026-08-13, gemini_vision.py 선례) — 프롬프트 프리셋 결합·
input_image 편집 축·image_data 봉투 반환. handler 가 spec-load 로 가져다 디스패치한다.
"""

import os
import json
import uuid


STYLE_PRESETS = {
    "vintage_book": (
        "Hand-drawn pen and ink illustration on aged beige parchment paper, "
        "two-tone palette of deep navy blue (#2c3e6f) and rust brown (#a55a3e), "
        "fine cross-hatching, geometric grid background lines, subtle paper texture and grain, "
        "vintage scientific manuscript aesthetic, balanced empty space around the central subject, "
        "centered composition with breathing room. "
        "Do NOT include any Korean or Hangul characters. Do NOT add decorative Latin text, ciphers, or unreadable script. "
        "Only the subject illustration — minimal or no text inside the image."
    ),
    "ink_orange": (
        "Bold flat pictogram infographic on bright ivory paper (#f2efe6): thick uniform "
        "charcoal-black (#2b2e33) stroke icons and geometric structures, exactly one vivid orange "
        "(#ee5f1c) reserved for flow — thick connector lines, arrows, radiating broadcast arcs or "
        "organic road networks — deliberate contrast of black structure versus orange flow, generous "
        "margins, poster-like clarity. "
        "Do NOT include any Korean or Hangul characters. Avoid decorative gibberish text — "
        "only meaningful short English labels if any."
    ),
    "architect": (
        "Flat isometric systems diagram on warm ivory paper (#efeae0), low-rise isometric slabs and "
        "cubes in muted brick terracotta (#ce6440) and desaturated steel blue (#33597f) with subtle "
        "face shading, deep slate-navy (#2e3947) drafting dimension lines, leader lines with round "
        "anchor dots and measurement arrows, faint blueprint grid floor, NotebookLM systems-architecture "
        "diagram aesthetic, generous empty space around the composition. "
        "Do NOT include any Korean or Hangul characters. Avoid decorative gibberish text — "
        "only meaningful short English labels if any."
    ),
    "blueprint": (
        "Precise technical drafting illustration on pale blue-grey drafting paper, "
        "thin indigo ink (#26305e) linework with a coral (#d86541) accent highlight, "
        "schematic figure with faint grid, leader lines and annotated parts, "
        "engineering-drawing aesthetic, exact and restrained, balanced empty space around the central subject. "
        "Do NOT include any Korean or Hangul characters. Do NOT add decorative Latin text or unreadable script. "
        "Only the subject illustration — minimal or no text inside the image."
    ),
}


def _build_image_prompt(user_prompt: str, style_preset: str = None) -> str:
    """스타일 프리셋을 사용자 프롬프트와 결합. 디자인 시스템과 어울리는 일러스트 생성용."""
    if not style_preset or style_preset == "default":
        return user_prompt
    style = STYLE_PRESETS.get(style_preset)
    if not style:
        return user_prompt
    return f"{user_prompt}\n\n--- STYLE GUIDELINES ---\n{style}"


def _image_envelope(path: str, max_bytes: int = 1_400_000):
    """생성 PNG → image_data 봉투({b64, media_type, path}). system_tools 수확 관문이
    모델에 진짜 이미지 블록으로 넣고 채팅에도 표시한다(guest-helper screen 선례).
    큰 파일(2K/4K)은 JPEG 재인코딩으로 봉투만 줄인다(디스크 원본은 그대로).
    실패 시 None — 봉투 없이 경로 텍스트만 남는다(정직 폴백)."""
    import base64
    try:
        raw = open(path, "rb").read()
        media_type = "image/jpeg" if path.lower().endswith((".jpg", ".jpeg")) else "image/png"
        if len(raw) > max_bytes:
            try:
                from PIL import Image
                import io
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                if max(im.size) > 1600:
                    im.thumbnail((1600, 1600))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=85)
                raw, media_type = buf.getvalue(), "image/jpeg"
            except Exception:
                pass
        if len(raw) > max_bytes:
            return None
        return {"b64": base64.b64encode(raw).decode(), "media_type": media_type,
                "path": os.path.abspath(path)}
    except Exception:
        return None


def generate_gemini_image(tool_input, output_base):
    """Gemini API를 사용하여 이미지를 생성/편집합니다 (input_image 있으면 편집)."""
    import httpx
    import base64

    prompt = tool_input.get("prompt")
    if not prompt:
        return "오류: prompt는 필수입니다."

    # input_image = 원본 사진을 주고 지시대로 고치는 편집 축 (채팅 첨부 사진 편집 등).
    # 문자열 하나 또는 목록 — 존재하는 파일만 inlineData 파트로 텍스트 앞에 첨부한다
    # (slide_native.edit_native_slide 와 같은 메커니즘).
    input_images = tool_input.get("input_image") or tool_input.get("input_image_path") or []
    if isinstance(input_images, str):
        input_images = [input_images]
    input_images = [p for p in input_images if isinstance(p, str) and os.path.exists(p)]
    if (tool_input.get("input_image") or tool_input.get("input_image_path")) and not input_images:
        return "오류: input_image 경로의 파일이 없습니다. 절대 경로를 확인하세요."

    api_key = tool_input.get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "오류: GEMINI_API_KEY 환경변수가 설정되지 않았거나 api_key 파라미터가 필요합니다."

    output_path = tool_input.get("output_path")
    # 편집(input_image)일 땐 aspect_ratio 미지정 시 비율을 강제하지 않는다(원본 비율 보존).
    aspect_ratio = tool_input.get("aspect_ratio") or (None if input_images else "1:1")
    image_size = tool_input.get("image_size", "1K")  # 512/1K/2K/4K (3.x), 2.5는 무시
    style_preset = tool_input.get("style_preset")
    final_prompt = _build_image_prompt(prompt, style_preset)
    if input_images:
        # 최소 편집 프레이밍 — 지시한 부분만 바꾸고 나머지(구도·배경·인물 정체성)는 보존
        # (slide_native.edit_native_slide 의 편집 계약과 같은 원리, 일반 사진용 일반화).
        final_prompt = (
            "Edit the provided photo/image according to the instruction below. "
            "Change ONLY what the instruction asks; keep everything else — composition, "
            "background, lighting, and the identity of any people — as close to the "
            "original as possible.\n\nEDIT INSTRUCTION: " + final_prompt
        )

    # 모델 선택 — 기본은 Nano Banana 2 (Gemini 3.1 Flash, 2026-02 출시)
    # quality 별칭으로 간편 선택, 또는 model로 직접 지정 가능
    quality = tool_input.get("quality")  # "fast" | "pro" | "legacy"
    quality_map = {
        "fast": "gemini-3.1-flash-image-preview",  # Nano Banana 2 (기본)
        "pro": "gemini-3-pro-image-preview",       # Nano Banana Pro — 4K, 더 정밀
        "legacy": "gemini-2.5-flash-image",        # 구버전 폴백
    }
    model = tool_input.get("model") or quality_map.get(quality, "gemini-3.1-flash-image-preview")

    # output_path가 지정되면 파일명만 추출하여 output_base에 저장
    if output_path:
        filename = os.path.basename(output_path)
        output_path = os.path.join(output_base, filename)
    else:
        output_path = os.path.join(output_base, f"gemini_image_{uuid.uuid4().hex[:8]}.png")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    # 페이로드 구조: 양쪽 모델 모두 generationConfig.imageConfig 사용.
    #   - 2.5: aspectRatio만 지원
    #   - 3.x: aspectRatio + imageSize (1K/2K/4K/512) 지원
    is_legacy = model.startswith("gemini-2.5")
    image_config = {}
    if aspect_ratio:
        image_config["aspectRatio"] = aspect_ratio
    if not is_legacy:
        image_config["imageSize"] = image_size
    # 편집 원본은 텍스트 앞에 첨부 (edit_native_slide 의 파트 순서와 동일)
    parts = []
    for p in input_images:
        mime = "image/jpeg" if p.lower().endswith((".jpg", ".jpeg")) else "image/png"
        parts.append({"inlineData": {"mimeType": mime,
                                     "data": base64.b64encode(open(p, "rb").read()).decode()}})
    parts.append({"text": final_prompt})
    gen_config = {"responseModalities": ["IMAGE", "TEXT"]}
    if image_config:
        gen_config["imageConfig"] = image_config
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": gen_config,
    }

    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(
                url,
                params={"key": api_key},
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()

        # 응답에서 이미지 데이터 추출
        candidates = data.get("candidates", [])
        if not candidates:
            return f"오류: Gemini API 응답에 결과가 없습니다. 응답: {data}"

        parts = candidates[0].get("content", {}).get("parts", [])
        image_saved = False
        description = ""

        for part in parts:
            if "inlineData" in part:
                img_data = base64.b64decode(part["inlineData"]["data"])
                with open(output_path, "wb") as f:
                    f.write(img_data)
                image_saved = True
            elif "text" in part:
                description = part["text"]

        if not image_saved:
            return f"오류: 응답에 이미지 데이터가 없습니다. 텍스트 응답: {description or data}"

        size_note = "" if is_legacy else f" / {image_size}"
        # JSON + image_data 봉투 반환 — system_tools 수확 관문이 모델·채팅에 그림으로
        # 전달한다(본문에서 base64 는 자동 제거). 봉투 실패 시 경로 텍스트만 남는다.
        out = {
            "success": True,
            "message": ("이미지 편집 완료" if input_images else "이미지 생성 완료")
                       + f": {os.path.abspath(output_path)}",
            "path": os.path.abspath(output_path),
            "model": f"{model}{size_note}" + (f" (aspect {aspect_ratio})" if aspect_ratio else ""),
            "prompt": prompt,
        }
        if description:
            out["description"] = description
        env = _image_envelope(output_path)
        if env:
            out["image_data"] = env
        return json.dumps(out, ensure_ascii=False, indent=2)

    except httpx.HTTPStatusError as e:
        return f"Gemini API 오류 ({e.response.status_code}): {e.response.text}"
    except Exception as e:
        return f"Gemini 이미지 생성 중 오류 발생: {str(e)}"

