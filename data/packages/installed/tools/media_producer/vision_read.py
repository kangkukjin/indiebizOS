"""이미지 읽기·평가 — [engines:image_read]{op: read|critic} 구현 (벤더 중립).

handler.py 에서 2026-08-05 분리 (1500줄 규칙). 디스패치 표(_OP_DISPATCHERS)는 AST 가드
때문에 handler.py 에 남고, 구현만 여기 산다.

시각 읽기·채점은 실행 역할의 짧은 원샷(system_ai_call)이다. 이미지 입력이 가능한
실행 모델을 쓰고, 미지원/미확인일 때만 별도 비전 설정으로 보완한다. 실행 이력은
재전송하지 않으며, 작업 전체의 최종 승인은 의식 감독이 맡는다.
재발 방지 관문 = test_vision_gear_contract(이 파일에 벤더 URL 금지).
"""
import os
import json
from pathlib import Path

# 취향 파일 원장 — 심사 기준은 코드 상수가 아니라 데이터로 산다("명사의 자리").
# 사용자의 비평이 이 디렉토리 yaml 의 diff 로 축적된다.
_ROOT = Path(__file__).resolve().parents[5]  # indiebizOS/
_CRITERIA_DIR = _ROOT / "data" / "criteria"


def _ai_call(prompt, system_prompt=None, images=None, role="execution"):
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


_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def _image_path_from_prev(prev) -> str:
    """파이프 통화(_prev_result)에서 이미지 경로 회수 (2026-08-29 마찰 ②).

    `[engines:web]{op:"check"} >> [engines:image_read]` 처럼 앞 액션이 만든 이미지
    (items 행의 path/file_path/screenshot 자리)를 image_path 미지정 시 집어 온다 —
    종전엔 파이프가 "image_path 가 필요합니다"로 끊겨 매번 file_find 재탐색이 필요했다.
    실존하는 이미지 확장자 경로만, items 뒤쪽(최신 산출) 우선.
    """
    if not prev:
        return ""
    obj = prev
    if isinstance(obj, str):
        s = obj.strip()
        if not s.startswith("{"):
            return s if s.lower().endswith(_IMG_EXTS) and os.path.exists(s) else ""
        try:
            obj = json.loads(s)
        except Exception:
            return ""
    if not isinstance(obj, dict):
        return ""
    candidates = []
    for row in reversed(obj.get("items") or []):
        if isinstance(row, dict):
            for k in ("path", "file_path", "image_path", "screenshot"):
                v = row.get(k)
                if isinstance(v, str):
                    candidates.append(v)
    for k in ("path", "file_path", "image_path"):
        v = obj.get(k)
        if isinstance(v, str):
            candidates.append(v)
    sc = obj.get("screenshot")
    if isinstance(sc, dict) and isinstance(sc.get("path"), str):
        candidates.append(sc["path"])
    for c in candidates:
        if c.lower().endswith(_IMG_EXTS) and os.path.exists(c):
            return c
    return ""


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
    """이미지를 기준에 대고 채점한다 — 실행 역할의 의도 정합 verdict.

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
    image_path = (tool_input.get("image_path") or tool_input.get("path")
                  or _image_path_from_prev(tool_input.get("_prev_result")))
    intent = tool_input.get("intent", "")
    if not image_path:
        return json.dumps({"success": False, "error": (
            "image_path(또는 path)가 필요합니다 — 파이프로 받을 때는 앞 액션의 통화에 "
            "이미지 경로(items 행의 path 등)가 실려 있어야 합니다.")}, ensure_ascii=False)
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
    preset = (tool_input.get("preset") or "").strip().lower()   # 미지정 = general (2026-08-29 ③)
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
    elif preset == "slide_illustration":
        # 슬라이드 일러스트 기준표 — 2026-08-29 마찰 ③ 로 **명시 요청제**가 됐다.
        # 종전엔 criteria·preset 미지정의 기본값이어서, 웹 스크린샷·문서 화면이
        # "한글 렌더링 → 무조건 실패" 같은 무관 판정을 받았다(08-27·08-29 두 번 실측).
        # 도메인 기준표를 보편 기본으로 두는 것이 결함 — 기본은 아래 general.
        rubric = "preset:slide_illustration"
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
    else:
        # 기본 = 매체 중립 (2026-08-29 ③): 기준표 미지정이면 의도 충족 + 보편 결함만 본다.
        # 매체 기준이 필요하면 criteria(web/sheet/visual_base) 또는 preset: slide_illustration.
        rubric = ("preset:general(기본값 — criteria·preset 미지정; 매체 기준은 "
                  "criteria: web|sheet|visual_base 또는 preset: slide_illustration)"
                  if not (tool_input.get("preset") or "").strip() else "preset:general")
        default_checks = [
            "이미지가 의도(intent)를 정확하고 충분히 충족하는가?",
            "시각적 결함(텍스트 잘림·겹침, 레이아웃 불균형, 깨짐, 저해상도, 빈 공간 과다)이 없는가?",
        ]
        if style_preset:
            default_checks.append(f"스타일/톤이 '{style_preset}'와 일관되는가?")
        intro = "당신은 산출물 품질 평가자입니다. 아래 이미지가 의도를 잘 충족하는지 엄격하게 평가하세요."
        hard_rule = ""

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

    # 개별 산출물 채점은 실행 역할, 전체 목표의 최종 승인은 의식 역할이다.
    text = _ai_call(instruction, images=[image], role="execution")
    if not text or not str(text).strip():
        return json.dumps({"success": False,
                           "error": "이미지 채점 실패 — 조종실 기어 설정의 이미지 읽기·채점 모델과 비전 대체 설정을 확인하세요."},
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
    if (not isinstance(verdict, dict)
            or type(verdict.get("passed")) is not bool
            or type(verdict.get("score")) not in (int, float)
            or not 0 <= verdict["score"] <= 10
            or not isinstance(verdict.get("issues"), list)
            or any(not isinstance(issue, str) for issue in verdict["issues"])
            or not isinstance(verdict.get("notes", ""), str)):
        return json.dumps({"success": False, "error": "VLM 채점 응답 형식 오류",
                           "raw": text[:500]}, ensure_ascii=False)
    # 모델이 자체 표식을 꾸며도 실제 호출 경로·적용 기준이 정본이다.
    verdict["tier"] = "vision"
    verdict["rubric"] = rubric

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
    image_path = (tool_input.get("image_path") or tool_input.get("path")
                  or _image_path_from_prev(tool_input.get("_prev_result")))
    if not image_path:
        return json.dumps({"success": False, "error": (
            "image_path(또는 path)가 필요합니다 — 파이프로 받을 때는 앞 액션의 통화에 "
            "이미지 경로(items 행의 path 등)가 실려 있어야 합니다.")}, ensure_ascii=False)
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
                           "error": "이미지 읽기 실패 — 조종실 기어 설정의 이미지 읽기·채점 모델과 비전 대체 설정을 확인하세요."},
                          ensure_ascii=False)
    return str(text).strip()
