"""이미지 읽기·평가 — [engines:image_read]{op: read|critic} 구현 (벤더 중립).

handler.py 에서 2026-08-05 분리 (1500줄 규칙). 디스패치 표(_OP_DISPATCHERS)는 AST 가드
때문에 handler.py 에 남고, 구현만 여기 산다.

★모델은 기어가 단독 결정한다 (2026-08-27 수리 — 구 gemini_vision.py 벤더 고정 폐지).
시각 읽기·채점은 범용 능력이라 벤더 SDK 직호출이 아니라 기어-해소 원샷(system_ai_call)을
탄다: read=실행 축(role "execution") / critic=평가 축(role "evaluate") — GoalEval 평가자와
같은 눈. 벤더 고유 기능(이미지 *생성*)만 gemini_image.py 에 남는다.
재발 방지 관문 = test_vision_gear_contract(이 파일에 벤더 URL 금지).
"""
import os
import json
from pathlib import Path

# 취향 파일 원장 — 심사 기준은 코드 상수가 아니라 데이터로 산다("명사의 자리").
# 사용자의 비평이 이 디렉토리 yaml 의 diff 로 축적된다.
_ROOT = Path(__file__).resolve().parents[5]  # indiebizOS/
_CRITERIA_DIR = _ROOT / "data" / "criteria"


def _ai_call(prompt, system_prompt=None, images=None, role="evaluate"):
    """기어-해소 멀티모달 원샷 — 모델·키는 기어에서 흘러나온다(에이전트별 설정 금지).

    consciousness_agent.system_ai_call 과 같은 계약(반환 str|None). 함수 한 겹인 이유:
    패키지 로드 시점에 backend import 를 강제하지 않고, 시험이 이 이음매를 바꿔치기한다.
    """
    from consciousness_agent import system_ai_call
    return system_ai_call(prompt, system_prompt=system_prompt, images=images, role=role)


def _load_image_b64(image_path):
    """(dict|None, err) — 절대 경로 또는 data URI → {"base64", "media_type"}."""
    import base64
    if image_path.startswith("data:"):
        try:
            _, b64data = image_path.split(",", 1)
            mime = image_path.split(";", 1)[0].split(":", 1)[1]
        except Exception:
            return None, "잘못된 data URI."
        return {"base64": b64data, "media_type": mime}, None
    if not os.path.exists(image_path):
        return None, f"파일이 없습니다: {image_path}"
    with open(image_path, "rb") as f:
        b64data = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(image_path)[1].lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/png")
    return {"base64": b64data, "media_type": mime}, None


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


def critique_image(tool_input, output_base):
    """이미지를 기준에 대고 채점한다 — 의도 정합 verdict (기어 평가 축).

    파라미터:
      - image_path (필수): 평가할 이미지 절대 경로 (또는 base64 data URI)
      - intent (필수): "이 이미지가 무엇을 표현해야 하는가" — 자연어 설명
      - checks (선택): 추가 체크 리스트
      - criteria (선택): data/criteria/*.yaml 취향 파일 (extends 사슬)
      - style_preset (선택): 디자인 시스템 톤 일관성 평가 기준
      - prescreen (선택): render 행의 0층 기계 관측 — 차 있으면 비전 호출 없이 즉시 실패

    반환:
      사람 가독 요약 + "verdict_json: {passed, score, issues, notes, tier}"
    """
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
    # verdict 를 같은 모양으로 반환한다. 모델 호출보다 앞이라 기어 상태와 무관하게 돈다.
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

    image, ierr = _load_image_b64(image_path)
    if ierr:
        return json.dumps({"success": False, "error": ierr}, ensure_ascii=False)

    checks = tool_input.get("checks") or []
    style_preset = tool_input.get("style_preset", "")
    # preset: "slide_illustration"(기본, 현행 슬라이드 일러스트 체크) | "general"(임의 산출물 범용)
    preset = (tool_input.get("preset") or "slide_illustration").strip().lower()
    # criteria: data/criteria/*.yaml 취향 파일 — 지정 시 preset 기본 체크 대신 이 파일이 기준.
    criteria_name = (tool_input.get("criteria") or "").strip()

    # 적용 기준표를 verdict 에 정직 신고한다 (2026-08-28) — 08-27 실측: criteria·preset
    # 둘 다 미지정이면 슬라이드 일러스트 기준표가 **조용히** 적용돼, 공유창고 HTML 문서
    # 스크린샷이 "한글 텍스트가 들어갔다"로 1/10 실패 판정을 받았다. 오판 자체보다
    # 어느 기준표였는지가 verdict 에 없어 원인을 소스 대조로만 찾을 수 있던 것이 침묵이다.
    if criteria_name:
        crit, cerr = _load_criteria(criteria_name)
        if cerr:
            return json.dumps({"success": False, "error": cerr}, ensure_ascii=False)
        rubric = f"criteria:{criteria_name}"
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
        rubric = "preset:general"
        default_checks = [
            "이미지가 의도(intent)를 정확하고 충분히 충족하는가?",
            "시각적 결함(텍스트 잘림·겹침, 레이아웃 불균형, 깨짐, 저해상도, 빈 공간 과다)이 없는가?",
        ]
        if style_preset:
            default_checks.append(f"스타일/톤이 '{style_preset}'와 일관되는가?")
        intro = "당신은 산출물 품질 평가자입니다. 아래 이미지가 의도를 잘 충족하는지 엄격하게 평가하세요."
        hard_rule = ""
    else:
        rubric = ("preset:slide_illustration(기본값 — criteria·preset 미지정)"
                  if not (tool_input.get("preset") or "").strip()
                  else "preset:slide_illustration")
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
        + "\n\n첨부된 이미지를 평가하라. 반드시 다음 JSON 형식 한 개만 출력하세요. 다른 텍스트 금지.\n"
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

    # 채점 = 평가 축 — GoalEval 평가자(system_ai_call role="evaluate")와 같은 눈.
    text = _ai_call(instruction, images=[image], role="evaluate")
    if not text or not str(text).strip():
        return json.dumps({"success": False,
                           "error": "기어 모델 호출 실패 — 평가 축 모델이 비전을 지원하는지 기어 설정을 확인하세요."},
                          ensure_ascii=False)
    text = str(text).strip()
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
        verdict.setdefault("rubric", rubric)  # 어느 기준표로 심사했는가 — 침묵 기본값 방지

    summary_lines = [
        f"이미지 평가: {image_path}",
        f"의도: {intent[:80]}{'...' if len(intent) > 80 else ''}",
        f"기준표: {rubric}",
        f"평가 결과: {'✓ 통과' if verdict.get('passed') else '✗ 실패'} (score={verdict.get('score', '?')}/10)",
    ]
    if rubric.endswith("미지정)"):
        summary_lines.append(
            "  ⚠ 슬라이드 일러스트 기본 기준표로 심사됨 — 문서·웹·장부 검수라면 "
            "criteria(web/visual_base/sheet …) 또는 preset: 'general' 을 지정할 것.")
    issues = verdict.get("issues") or []
    if issues:
        summary_lines.append("문제점:")
        summary_lines.extend(f"  - {i}" for i in issues)
    if verdict.get("notes"):
        summary_lines.append(f"메모: {verdict['notes']}")
    summary_lines.append("")
    summary_lines.append(f"verdict_json: {_json.dumps(verdict, ensure_ascii=False)}")
    return "\n".join(summary_lines)


def read_image(tool_input, output_base):
    """이미지를 *읽어* 질문에 자유서술로 답한다 (시각 QA / OCR / 검증 — 기어 실행 축).

    critique_image 와 다른 점: 합격/점수 채점이 아니라, 주어진 질문에 대한 자유 텍스트
    답을 돌려준다. "스크린샷의 숫자를 읽어줘", "이 그림에 무엇이 보이나" 같은 시각
    읽기·검증에 쓴다. 산출물 품질 평가는 op:critic 을 쓸 것.

    파라미터:
      - image_path (또는 path): 읽을 이미지 절대 경로 또는 base64 data URI (필수)
      - question (또는 query/prompt): 무엇을 읽거나 답할지 (없으면 전체 묘사)
    """
    image_path = tool_input.get("image_path") or tool_input.get("path")
    if not image_path:
        return json.dumps({"success": False, "error": "image_path(또는 path)가 필요합니다."}, ensure_ascii=False)
    question = (tool_input.get("question") or tool_input.get("query")
                or tool_input.get("intent") or tool_input.get("prompt") or "").strip()

    image, ierr = _load_image_b64(image_path)
    if ierr:
        return json.dumps({"success": False, "error": ierr}, ensure_ascii=False)

    if question:
        instruction = (
            "당신은 이미지를 정확히 읽는 시각 분석가입니다. 첨부된 이미지를 보고 질문에 "
            "사실에 근거해 답하세요. 이미지에 적힌 텍스트·숫자는 보이는 그대로 정확히 옮기고, "
            "보이지 않거나 불확실하면 추측하지 말고 그렇다고 밝히세요.\n\n"
            f"**질문**: {question}"
        )
    else:
        instruction = ("첨부된 이미지를 보고 무엇이 있는지 상세히 묘사하세요. 이미지에 적힌 "
                       "텍스트·숫자가 있으면 보이는 그대로 정확히 옮기세요.")

    # 읽기 = 실행 중 지각 — 실행 축.
    text = _ai_call(instruction, images=[image], role="execution")
    if not text or not str(text).strip():
        return json.dumps({"success": False,
                           "error": "기어 모델 호출 실패 — 실행 축 모델이 비전을 지원하는지 기어 설정을 확인하세요."},
                          ensure_ascii=False)
    return str(text).strip()
