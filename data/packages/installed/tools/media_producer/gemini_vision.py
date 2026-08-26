"""Gemini Vision 읽기·평가 — [engines:image_read]{op: read|critic} 구현.

handler.py 에서 2026-08-05 분리 (1500줄 규칙 — image_critic 흡수로 래칫 상한 초과).
디스패치 표(_OP_DISPATCHERS)는 AST 가드 때문에 handler.py 에 남고, 구현만 여기 산다.
"""
import os
import json
from pathlib import Path

# 취향 파일 원장 — 심사 기준은 코드 상수가 아니라 데이터로 산다("명사의 자리").
# 사용자의 비평이 이 디렉토리 yaml 의 diff 로 축적된다.
_ROOT = Path(__file__).resolve().parents[5]  # indiebizOS/
_CRITERIA_DIR = _ROOT / "data" / "criteria"


def _load_criteria(name_or_path, _seen=None):
    """data/criteria/*.yaml 로딩 (+extends 사슬 병합).

    반환: ({intro, checks, forbidden}, None) 또는 (None, 오류문).
    병합 규칙: checks/forbidden 은 기저+자식 이어붙임, intro 는 자식이 이김.
    """
    import yaml
    _seen = _seen or set()
    name = str(name_or_path).strip()
    path = Path(name) if os.path.isabs(name) else _CRITERIA_DIR / (
        name if name.endswith((".yaml", ".yml")) else f"{name}.yaml")
    key = str(path.resolve())
    if key in _seen:
        return None, f"criteria extends 순환: {name}"
    _seen.add(key)
    if not path.exists():
        try:
            available = sorted(p.stem for p in _CRITERIA_DIR.glob("*.yaml"))
        except Exception:
            available = []
        return None, f"criteria 파일이 없습니다: {path} (사용 가능: {', '.join(available) or '없음'})"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return None, f"criteria 파싱 실패({path.name}): {e}"

    merged = {"intro": "", "checks": [], "forbidden": []}
    base_name = raw.get("extends")
    if base_name:
        base, err = _load_criteria(base_name, _seen)
        if err:
            return None, err
        merged = base
    merged = {
        "intro": (raw.get("intro") or merged["intro"] or "").strip(),
        "checks": list(merged["checks"]) + [str(c) for c in (raw.get("checks") or [])],
        "forbidden": list(merged["forbidden"]) + [str(f) for f in (raw.get("forbidden") or [])],
    }
    return merged, None


def critique_gemini_image(tool_input, output_base):
    """Gemini Vision으로 이미지를 평가한다 — 일러스트가 의도와 정합하는지 검증.

    파라미터:
      - image_path (필수): 평가할 이미지 절대 경로 (또는 base64 data URI)
      - intent (필수): "이 일러스트가 무엇을 표현해야 하는가" — 자연어 설명
      - checks (선택): 추가 체크 리스트 (예: ["다이어그램형인가", "한글이 들어갔는가", "오른쪽 1/3이 비어있는가"])
      - style_preset (선택): 디자인 시스템 톤 일관성 평가 기준 (vintage_book 등)
      - api_key (선택)

    반환:
      JSON 문자열 — {"passed": bool, "score": 0-10, "issues": [...], "notes": "..."}
      그리고 사람이 읽을 수 있는 요약 텍스트가 앞에 옴.
    """
    import httpx
    import base64
    import json as _json

    # path 는 IBL 표준 파라미터(self:read/grep/edit 모두 path) — image_path 미지정 시 폴백 수용.
    image_path = tool_input.get("image_path") or tool_input.get("path")
    intent = tool_input.get("intent", "")
    if not image_path:
        return json.dumps({"success": False, "error": "image_path(또는 path)가 필요합니다."}, ensure_ascii=False)
    if not intent:
        return json.dumps({"success": False, "error": "intent(이 일러스트가 무엇을 표현해야 하는지)가 필요합니다."}, ensure_ascii=False)

    # ── 0층 단락 (검수 비용 계층화, INSPECTION_COST_TIER 2026-08-27) ──
    # render 가 행에 동봉한 기계 관측(prescreen)이 비어 있지 않으면 이미 구체적 실패
    # 증거(콘솔 오류·빈 화면·수식 오류 표식)가 있다 — 유료 비전 호출 없이 즉시 실패
    # verdict 를 같은 모양으로 반환한다. API 키 검사보다 앞이라 키 없이도 돈다.
    prescreen = str(tool_input.get("prescreen") or "").strip()
    if prescreen:
        verdict = {"passed": False, "score": 0,
                   "issues": [f.strip() for f in prescreen.split(";") if f.strip()],
                   "notes": "0층 기계 관측 실패 — 비전 심사 생략(비용 계층화)",
                   "tier": "prescreen"}
        return "\n".join([
            f"이미지 평가: {image_path}",
            f"의도: {intent[:80]}{'...' if len(intent) > 80 else ''}",
            f"평가 결과: ✗ 실패 (score=0/10, 0층 기계 관측 — 비전 호출 생략)",
            "문제점:", *(f"  - {i}" for i in verdict["issues"]), "",
            f"verdict_json: {_json.dumps(verdict, ensure_ascii=False)}"])

    api_key = tool_input.get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return json.dumps({"success": False, "error": "GEMINI_API_KEY가 설정되지 않았습니다."}, ensure_ascii=False)

    # 이미지 로드 (절대 경로 또는 data URI)
    if image_path.startswith("data:"):
        # data URI → base64 페이로드만 추출
        try:
            _, b64data = image_path.split(",", 1)
            mime = image_path.split(";", 1)[0].split(":", 1)[1]
        except Exception:
            return json.dumps({"success": False, "error": "잘못된 data URI."}, ensure_ascii=False)
    else:
        if not os.path.exists(image_path):
            return json.dumps({"success": False, "error": f"파일이 없습니다: {image_path}"}, ensure_ascii=False)
        with open(image_path, "rb") as f:
            b64data = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(image_path)[1].lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(ext, "image/png")

    checks = tool_input.get("checks") or []
    style_preset = tool_input.get("style_preset", "")
    # preset: "slide_illustration"(기본, 현행 슬라이드 일러스트 체크) | "general"(임의 산출물 범용)
    preset = (tool_input.get("preset") or "slide_illustration").strip().lower()
    # criteria: data/criteria/*.yaml 취향 파일 — 지정 시 preset 기본 체크 대신 이 파일이 기준.
    criteria_name = (tool_input.get("criteria") or "").strip()

    if criteria_name:
        crit, cerr = _load_criteria(criteria_name)
        if cerr:
            return json.dumps({"success": False, "error": cerr}, ensure_ascii=False)
        default_checks = list(crit["checks"])
        if style_preset:
            default_checks.append(f"스타일/톤이 '{style_preset}'와 일관되는가?")
        intro = crit["intro"] or "당신은 시각 산출물 품질 평가자입니다. 아래 이미지를 기준에 대고 엄격하게 평가하세요."
        forbidden = crit["forbidden"]
        if forbidden:
            default_checks.extend(f"[금지] {f} — 발견되면 실패" for f in forbidden)
            hard_rule = " 금지([금지]) 항목이 하나라도 발견되면 무조건 passed=false."
        else:
            hard_rule = ""
    elif preset == "general":
        default_checks = [
            "이미지가 의도(intent)를 정확하고 충분히 충족하는가?",
            "시각적 결함(텍스트 잘림·겹침, 레이아웃 불균형, 깨짐, 저해상도, 빈 공간 과다)이 없는가?",
        ]
        if style_preset:
            default_checks.append(f"스타일/톤이 '{style_preset}'와 일관되는가?")
        intro = "당신은 산출물 품질 평가자입니다. 아래 이미지가 의도를 잘 충족하는지 엄격하게 평가하세요."
        hard_rule = ""
    else:
        default_checks = [
            "이 일러스트는 회화적 '씬(scene)'이 아니라 정보를 전달하는 '다이어그램/인포그래픽'인가? (NotebookLM 양식)",
            "한글(Hangul) 문자가 일러스트 안에 들어가 있는가? (있으면 실패 — 한글은 텍스트 레이어에서 처리)",
            "라벨 박스가 들어갈 빈 공간(여백)이 의도된 위치에 정말 비어 있는가? (intent에 명시된 빈 공간 위치 확인)",
            "주요 객체가 일러스트의 핵심 영역(중앙/지정 위치)에 명확하게 배치되어 있는가?",
        ]
        if style_preset:
            default_checks.append(f"디자인 시스템 톤이 '{style_preset}'와 일관되는가? (색·선·분위기)")
        intro = "당신은 강의 슬라이드 일러스트 평가자입니다. 다음 일러스트가 의도를 잘 표현하는지 엄격하게 평가하세요."
        hard_rule = " 한글이 일러스트에 들어가 있으면 무조건 passed=false."

    all_checks = default_checks + checks

    instruction = (
        intro + "\n\n"
        f"**의도 (이 결과물이 충족해야 할 것)**:\n{intent}\n\n"
        f"**체크 항목** ({len(all_checks)}개):\n"
        + "\n".join(f"{i+1}. {c}" for i, c in enumerate(all_checks))
        + "\n\n반드시 다음 JSON 형식 한 개만 출력하세요. 다른 텍스트 금지.\n"
        "```json\n"
        "{\n"
        '  "passed": true|false,\n'
        '  "score": 0-10,\n'
        '  "issues": ["체크 N번 실패 — 구체적 이유", ...],\n'
        '  "notes": "전반적 평가 (1~2문장)"\n'
        "}\n"
        "```\n"
        "passed는 issues가 없거나 score>=7일 때 true." + hard_rule
    )

    payload = {
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": mime, "data": b64data}},
                {"text": instruction},
            ]
        }],
        "generationConfig": {"temperature": 0.2, "responseModalities": ["TEXT"]},
    }

    # VLM 모델 — pro 우선, fallback flash
    model = tool_input.get("model") or "gemini-3-pro-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, params={"key": api_key}, json=payload,
                            headers={"Content-Type": "application/json"})
            if r.status_code == 404:
                # 폴백 모델
                model = "gemini-2.5-pro"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                r = client.post(url, params={"key": api_key}, json=payload,
                                headers={"Content-Type": "application/json"})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return json.dumps({"success": False, "error": f"VLM 호출 실패: {e}"}, ensure_ascii=False)

    parts = (data.get("candidates", [{}])[0].get("content", {}) or {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    # ```json ... ``` 코드 펜스 제거
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
        text = text.split("```")[0].strip()

    try:
        verdict = _json.loads(text)
    except Exception:
        return json.dumps({"success": False, "error": "VLM 응답 파싱 실패", "raw": text[:500]}, ensure_ascii=False)
    if isinstance(verdict, dict):
        verdict.setdefault("tier", "vision")  # 0층(prescreen) 단락과 판정 출처를 구분

    summary_lines = [
        f"이미지 평가: {image_path}",
        f"의도: {intent[:80]}{'...' if len(intent) > 80 else ''}",
        f"평가 결과: {'✓ 통과' if verdict.get('passed') else '✗ 실패'} (score={verdict.get('score', '?')}/10)",
    ]
    issues = verdict.get("issues") or []
    if issues:
        summary_lines.append("문제점:")
        summary_lines.extend(f"  - {i}" for i in issues)
    if verdict.get("notes"):
        summary_lines.append(f"메모: {verdict['notes']}")
    summary_lines.append("")
    summary_lines.append(f"verdict_json: {_json.dumps(verdict, ensure_ascii=False)}")
    return "\n".join(summary_lines)


def read_gemini_image(tool_input, output_base):
    """Gemini Vision으로 이미지를 *읽어* 질문에 자유서술로 답한다 (시각 QA / OCR / 검증).

    critique_gemini_image 와 다른 점: 합격/점수 채점이 아니라, 주어진 질문에 대한 자유 텍스트
    답을 돌려준다. "스크린샷의 숫자를 읽어줘", "이 그림에 무엇이 보이나", "이 통계 수치가
    332인가 136인가" 같은 시각 읽기·검증에 쓴다. 생성 일러스트 품질 평가는 image_critic 을 쓸 것.

    파라미터:
      - image_path (또는 path): 읽을 이미지 절대 경로 또는 base64 data URI (필수)
      - question (또는 query/intent/prompt): 무엇을 읽거나 답할지 (없으면 전체 묘사)
      - api_key (선택), model (선택)
    """
    import httpx
    import base64

    image_path = tool_input.get("image_path") or tool_input.get("path")
    if not image_path:
        return json.dumps({"success": False, "error": "image_path(또는 path)가 필요합니다."}, ensure_ascii=False)
    question = (tool_input.get("question") or tool_input.get("query")
               or tool_input.get("intent") or tool_input.get("prompt") or "").strip()

    api_key = tool_input.get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return json.dumps({"success": False, "error": "GEMINI_API_KEY가 설정되지 않았습니다."}, ensure_ascii=False)

    # 이미지 로드 (절대 경로 또는 data URI) — critique_gemini_image 와 동일.
    if image_path.startswith("data:"):
        try:
            _, b64data = image_path.split(",", 1)
            mime = image_path.split(";", 1)[0].split(":", 1)[1]
        except Exception:
            return json.dumps({"success": False, "error": "잘못된 data URI."}, ensure_ascii=False)
    else:
        if not os.path.exists(image_path):
            return json.dumps({"success": False, "error": f"파일이 없습니다: {image_path}"}, ensure_ascii=False)
        with open(image_path, "rb") as f:
            b64data = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(image_path)[1].lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/png")

    if question:
        instruction = (
            "당신은 이미지를 정확히 읽는 시각 분석가입니다. 아래 이미지를 보고 질문에 "
            "사실에 근거해 답하세요. 이미지에 적힌 텍스트·숫자는 보이는 그대로 정확히 옮기고, "
            "보이지 않거나 불확실하면 추측하지 말고 그렇다고 밝히세요.\n\n"
            f"**질문**: {question}"
        )
    else:
        instruction = ("아래 이미지를 보고 무엇이 있는지 상세히 묘사하세요. 이미지에 적힌 "
                       "텍스트·숫자가 있으면 보이는 그대로 정확히 옮기세요.")

    payload = {
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": mime, "data": b64data}},
                {"text": instruction},
            ]
        }],
        "generationConfig": {"temperature": 0.0, "responseModalities": ["TEXT"]},
    }
    model = tool_input.get("model") or "gemini-3-pro-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, params={"key": api_key}, json=payload,
                            headers={"Content-Type": "application/json"})
            if r.status_code == 404:
                model = "gemini-2.5-pro"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                r = client.post(url, params={"key": api_key}, json=payload,
                                headers={"Content-Type": "application/json"})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return json.dumps({"success": False, "error": f"VLM 호출 실패: {e}"}, ensure_ascii=False)

    parts = (data.get("candidates", [{}])[0].get("content", {}) or {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        return json.dumps({"success": False, "error": "VLM 빈 응답 (이미지를 읽지 못했습니다)."}, ensure_ascii=False)
    return text
