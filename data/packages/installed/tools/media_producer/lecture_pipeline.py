"""강의 슬라이드 4단계 파이프라인.

PLAN → WRITE → ILLUSTRATE → COMPOSE.

각 단계가 산출물 파일을 남기고, 다음 단계가 이전 산출물을 입력으로 받음.
의식 에이전트는 각 단계의 일에만 집중. 평가 에이전트가 단계마다 산출물을 검토.

설계 원칙:
- 액션은 가벼운 파일 IO + 스키마 검증. 실제 명제 추출/콘텐츠 작성은 의식 에이전트의 일.
- 단계 산출물은 항상 lecture_<id>/{outline.json, contents.json, illustrations/, deck/} 구조.
- 부분 재실행을 위해 only_indices(특정 슬라이드만 재처리) 옵션 지원.
"""

from __future__ import annotations
import json
import os
import uuid
from typing import Any


# ============================================
# 스키마 정의 — 검증과 LLM 안내에 동시 사용
# ============================================

OUTLINE_SLIDE_SCHEMA = {
    "required": ["idx", "role", "title"],
    "optional": ["device", "visual", "concrete", "speaker_note"],
    "roles": [
        "cover", "intro", "thesis",
        "closure_table", "closure_diagram",
        "quote", "outro", "reference",
    ],
    "devices": ["contrast", "chain", "equation", "scale", "hierarchy", "none"],
}

CONTENTS_SLIDE_SCHEMA = {
    "required": ["idx", "layout", "title"],
    "optional": [
        "eyebrow", "subtitle", "body", "labels",
        "footer", "footer_quote", "image_prompt", "image_path",
        "left_title", "left_body", "left_image_prompt", "left_image_path",
        "right_title", "right_body", "right_image_prompt", "right_image_path",
        "text_align", "columns", "rows", "label_header",
    ],
}


# ============================================
# 공통 헬퍼
# ============================================

def _resolve_lecture_dir(tool_input: dict, output_base: str) -> str:
    """lecture_dir을 결정. 미지정 시 새로 생성."""
    d = tool_input.get("lecture_dir")
    if d:
        d = os.path.abspath(d)
    else:
        d = os.path.abspath(os.path.join(output_base, f"lecture_{uuid.uuid4().hex[:8]}"))
    os.makedirs(d, exist_ok=True)
    return d


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _validate_slide(slide: dict, schema: dict, idx: int) -> list[str]:
    """슬라이드 dict가 스키마를 만족하는지 — 누락 필드 리스트 반환 (빈 리스트면 OK)."""
    missing = [k for k in schema["required"] if k not in slide or slide[k] in (None, "")]
    return [f"슬라이드 {idx}: 누락 필드 {m}" for m in missing]


def _append_criteria_marker(response: str, action_name: str) -> str:
    """응답 끝에 액션의 achievement_criteria를 표준 마커로 첨부.

    평가 에이전트(agent_cognitive._extract_achievement_criteria의 3차 fallback)가
    이 마커를 인식해 액션 단위 자동 평가 기준으로 사용한다.
    """
    try:
        import sys
        sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[5] / "backend"))
        from ibl_action_manager import get_action_achievement_criteria
        criteria = get_action_achievement_criteria("engines", action_name)
        if criteria:
            return f"{response}\n\n[ACHIEVEMENT_CRITERIA:engines:{action_name}]\n{criteria}\n[/ACHIEVEMENT_CRITERIA]"
    except Exception:
        pass  # 메타 조회 실패는 무해 — 응답 그대로 반환
    return response


# ============================================
# 단계 1 — PLAN (메시지 큐레이션)
# ============================================

def create_lecture_plan(tool_input: dict, output_base: str) -> str:
    """슬라이드 outline을 저장.

    사용 패턴 (의식 에이전트):
      1) lecture_dir 없이 init_skeleton=True로 호출 → 스켈레톤 outline.md 생성, lecture_dir 받음
      2) 책 본문을 읽고 명제 추출 후, outline 배열을 채워 다시 호출 → 검증 + 저장

    파라미터:
      - lecture_dir (선택): 기존 작업 디렉토리. 없으면 새로 생성
      - outline (필수, init_skeleton 모드 제외): [{idx, role, title, device, visual, concrete}] 배열
      - source (선택): 원문 메타 (책 제목·부·저자 등). outline.md 헤더에 들어감
      - style (선택): "notebooklm" | "classic". 기본 notebooklm
      - init_skeleton (선택): True면 빈 스켈레톤만 생성하고 안내 반환
    """
    lecture_dir = _resolve_lecture_dir(tool_input, output_base)

    if tool_input.get("init_skeleton"):
        skeleton_md = (
            "# 강의 outline (스켈레톤)\n\n"
            "이 파일은 자동 생성된 스켈레톤입니다. 다음 5단계를 따라 채우세요:\n\n"
            "1. **명제 추출**: 책에서 '잊으면 안 될 한 줄 단정문' N개 뽑기\n"
            "2. **슬라이드 제목 = 명제**: 챕터명을 그대로 가져오면 안 됨\n"
            "3. **수사 장치 매핑**: contrast / chain / equation / scale / hierarchy 5종 중 하나\n"
            "4. **구체화**: 수치·고유명사·연도를 concrete 필드로 격리\n"
            "5. **이중 회수**: 마지막 두 장은 closure_table + closure_diagram\n\n"
            "각 슬라이드 형식:\n"
            "```json\n"
            "{\n"
            '  "idx": 2,\n'
            '  "role": "thesis",\n'
            '  "title": "AI 모델 ≠ AI의 실체",         // 단정문!\n'
            '  "device": "contrast",                   // 5종 중 하나\n'
            '  "visual": "유리병 속 뇌 vs 깨진 유리병+하네스",\n'
            '  "concrete": ["유리병 속의 뇌"],          // 수치·고유명사\n'
            '  "speaker_note": "강사 발화 1~2문장"     // 선택\n'
            "}\n"
            "```\n\n"
            "outline 배열을 채운 뒤 같은 lecture_dir로 다시 [engines:lecture_plan] 호출.\n"
        )
        skel_path = os.path.join(lecture_dir, "outline_SKELETON.md")
        with open(skel_path, "w", encoding="utf-8") as f:
            f.write(skeleton_md)
        return (
            f"강의 작업 디렉토리 생성: {lecture_dir}\n"
            f"스켈레톤 안내: {skel_path}\n"
            "다음 단계: 명제 outline 배열을 채워 [engines:lecture_plan]{lecture_dir, outline: [...]} 호출."
        )

    outline = tool_input.get("outline")
    if not outline or not isinstance(outline, list):
        return (
            "오류: outline 배열이 필요합니다. "
            "처음이라면 init_skeleton=True로 호출해 스켈레톤 안내를 받으세요. "
            "[engines:lecture_plan]{init_skeleton: true}"
        )

    # 스키마 검증
    errors: list[str] = []
    for i, slide in enumerate(outline):
        if not isinstance(slide, dict):
            errors.append(f"슬라이드 {i}: dict가 아님")
            continue
        errors.extend(_validate_slide(slide, OUTLINE_SLIDE_SCHEMA, slide.get("idx", i)))
        role = slide.get("role")
        if role and role not in OUTLINE_SLIDE_SCHEMA["roles"]:
            errors.append(f"슬라이드 {slide.get('idx', i)}: 알 수 없는 role '{role}' (허용: {OUTLINE_SLIDE_SCHEMA['roles']})")
        device = slide.get("device")
        if device and device not in OUTLINE_SLIDE_SCHEMA["devices"]:
            errors.append(f"슬라이드 {slide.get('idx', i)}: 알 수 없는 device '{device}' (허용: {OUTLINE_SLIDE_SCHEMA['devices']})")

    # 이중 회수 슬라이드 존재 검증 (style=notebooklm일 때만 강제)
    style = tool_input.get("style", "notebooklm")
    if style == "notebooklm":
        roles = [s.get("role") for s in outline if isinstance(s, dict)]
        if "closure_table" not in roles:
            errors.append("이중 회수 누락: role='closure_table' 슬라이드가 없습니다 (§2 ⑤ 위반)")
        if "closure_diagram" not in roles:
            errors.append("이중 회수 누락: role='closure_diagram' 슬라이드가 없습니다 (§2 ⑤ 위반)")

    if errors:
        return "outline 검증 실패:\n- " + "\n- ".join(errors)

    # 메타데이터 + 저장
    plan = {
        "source": tool_input.get("source", ""),
        "style": style,
        "slide_count": len(outline),
        "outline": outline,
    }
    json_path = os.path.join(lecture_dir, "outline.json")
    md_path = os.path.join(lecture_dir, "outline.md")
    _write_json(json_path, plan)

    # outline.md 생성 (인간 검토용)
    md_lines = [f"# 강의 outline", ""]
    if plan["source"]:
        md_lines += [f"**원문**: {plan['source']}", ""]
    md_lines += [f"**스타일**: {style} · **슬라이드 수**: {len(outline)}", "", "## 슬라이드 명세", ""]
    md_lines.append("| # | role | 제목 (명제) | device | visual | concrete |")
    md_lines.append("|---|------|------------|--------|--------|----------|")
    for s in outline:
        concrete = s.get("concrete") or []
        concrete_str = ", ".join(concrete) if isinstance(concrete, list) else str(concrete)
        md_lines.append(
            f"| {s.get('idx', '?')} | {s.get('role', '')} | {s.get('title', '')} | "
            f"{s.get('device', '')} | {s.get('visual', '')} | {concrete_str} |"
        )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    msg = (
        f"✓ PLAN 단계 완료. {len(outline)}장 outline 저장.\n"
        f"lecture_dir: {lecture_dir}\n"
        f"outline.json: {json_path}\n"
        f"outline.md (인간 검토용): {md_path}\n"
        f"다음 단계: [engines:lecture_write]{{lecture_dir: \"{lecture_dir}\", contents: [...]}}"
    )
    return _append_criteria_marker(msg, "lecture_plan")


# ============================================
# 단계 2 — WRITE (각 슬라이드 콘텐츠 집필)
# ============================================

def create_lecture_write(tool_input: dict, output_base: str) -> str:
    """outline.json을 입력으로 받아 슬라이드별 콘텐츠(layout/labels/image_prompt 등)를 저장.

    파라미터:
      - lecture_dir (필수): PLAN 단계가 생성한 디렉토리
      - contents (필수): [{idx, layout, title, labels, image_prompt, ...}] 슬라이드별 콘텐츠 배열
      - design_system (선택): contents.json에 저장됨. ILLUSTRATE/COMPOSE 단계에서 사용
      - only_indices (선택): 부분 갱신할 슬라이드 idx 리스트. 기존 contents.json을 로드하고 해당 idx만 덮어씀
    """
    lecture_dir = tool_input.get("lecture_dir")
    if not lecture_dir or not os.path.isdir(lecture_dir):
        return f"오류: lecture_dir이 유효하지 않습니다: {lecture_dir}"
    lecture_dir = os.path.abspath(lecture_dir)

    outline_path = os.path.join(lecture_dir, "outline.json")
    if not os.path.exists(outline_path):
        return f"오류: outline.json이 없습니다. 먼저 [engines:lecture_plan]을 실행하세요: {outline_path}"
    plan = _read_json(outline_path)
    outline = plan.get("outline", [])
    outline_idx_set = {s.get("idx") for s in outline if isinstance(s, dict)}

    contents_input = tool_input.get("contents")
    if not contents_input or not isinstance(contents_input, list):
        return "오류: contents 배열이 필요합니다."

    only_indices = tool_input.get("only_indices")
    contents_path = os.path.join(lecture_dir, "contents.json")

    # 부분 갱신 모드
    if only_indices:
        if not os.path.exists(contents_path):
            return f"오류: only_indices 모드는 기존 contents.json이 있어야 합니다."
        existing = _read_json(contents_path)
        existing_by_idx = {s.get("idx"): s for s in existing.get("contents", [])}
        for s in contents_input:
            existing_by_idx[s.get("idx")] = s
        merged = sorted(existing_by_idx.values(), key=lambda x: x.get("idx", 0))
        contents_doc = {
            "design_system": tool_input.get("design_system", existing.get("design_system", "sf_blueprint")),
            "contents": merged,
        }
    else:
        contents_doc = {
            "design_system": tool_input.get("design_system", "sf_blueprint"),
            "contents": contents_input,
        }

    # 스키마 검증
    errors: list[str] = []
    for i, slide in enumerate(contents_doc["contents"]):
        if not isinstance(slide, dict):
            errors.append(f"슬라이드 {i}: dict가 아님")
            continue
        errors.extend(_validate_slide(slide, CONTENTS_SLIDE_SCHEMA, slide.get("idx", i)))
        if slide.get("idx") not in outline_idx_set:
            errors.append(f"슬라이드 {slide.get('idx')}: outline에 해당 idx가 없습니다")

    # 일러스트 프롬프트 필요 여부 검증 — illustration_* 레이아웃은 image_prompt 필수
    for slide in contents_doc["contents"]:
        layout = slide.get("layout", "")
        if layout.startswith("illustration_") or layout in ("hero_illustration",):
            if not slide.get("image_prompt") and not slide.get("image_path"):
                errors.append(f"슬라이드 {slide.get('idx')}: layout='{layout}'는 image_prompt 또는 image_path가 필요합니다")
        if layout == "split_concept":
            if not (slide.get("left_image_prompt") or slide.get("left_image_path")):
                errors.append(f"슬라이드 {slide.get('idx')}: split_concept에 left_image_prompt 필요")
            if not (slide.get("right_image_prompt") or slide.get("right_image_path")):
                errors.append(f"슬라이드 {slide.get('idx')}: split_concept에 right_image_prompt 필요")

    if errors:
        return "contents 검증 실패:\n- " + "\n- ".join(errors)

    _write_json(contents_path, contents_doc)
    msg = (
        f"✓ WRITE 단계 완료. {len(contents_doc['contents'])}장 콘텐츠 저장.\n"
        f"contents.json: {contents_path}\n"
        f"design_system: {contents_doc['design_system']}\n"
        f"다음 단계: [engines:lecture_illustrate]{{lecture_dir: \"{lecture_dir}\"}}"
    )
    return _append_criteria_marker(msg, "lecture_write")


# ============================================
# 단계 3 — ILLUSTRATE (일러스트 생성)
# ============================================

def create_lecture_illustrate(tool_input: dict, output_base: str) -> str:
    """contents.json의 image_prompt들을 image_gemini로 병렬 호출, illustrations/manifest.json 생성.

    파라미터:
      - lecture_dir (필수)
      - style_preset (선택): 미지정 시 design_system을 그대로 사용
      - quality (선택): fast(기본) / pro / legacy
      - image_size (선택): 1K(기본) / 2K / 4K
      - only_indices (선택): 부분 재생성. 해당 슬라이드의 일러스트만 다시 만듦
    """
    lecture_dir = tool_input.get("lecture_dir")
    if not lecture_dir or not os.path.isdir(lecture_dir):
        return f"오류: lecture_dir이 유효하지 않습니다: {lecture_dir}"
    lecture_dir = os.path.abspath(lecture_dir)

    contents_path = os.path.join(lecture_dir, "contents.json")
    if not os.path.exists(contents_path):
        return f"오류: contents.json이 없습니다. 먼저 [engines:lecture_write]를 실행하세요."
    doc = _read_json(contents_path)
    contents = doc.get("contents", [])

    style_preset = tool_input.get("style_preset") or doc.get("design_system", "sf_blueprint")
    quality = tool_input.get("quality", "fast")
    image_size = tool_input.get("image_size", "1K")
    only = tool_input.get("only_indices")
    only_set = set(only) if only else None

    illustrations_dir = os.path.join(lecture_dir, "illustrations")
    os.makedirs(illustrations_dir, exist_ok=True)

    manifest_path = os.path.join(illustrations_dir, "manifest.json")
    manifest = _read_json(manifest_path) if os.path.exists(manifest_path) else {"items": []}
    manifest_by_idx = {item["idx"]: item for item in manifest.get("items", [])}

    # image_gemini 로딩 (지연)
    from handler import generate_gemini_image

    results: list[dict] = []
    skipped: list[int] = []
    failures: list[str] = []

    for slide in contents:
        idx = slide.get("idx")
        if only_set is not None and idx not in only_set:
            # 부분 재생성 모드 — 대상 외는 기존 manifest 유지
            if idx in manifest_by_idx:
                results.append(manifest_by_idx[idx])
            skipped.append(idx)
            continue

        layout = slide.get("layout", "")
        prompt_pairs: list[tuple[str, str]] = []  # (output_filename, prompt) — split_concept는 2장

        if slide.get("image_prompt"):
            prompt_pairs.append((f"slide_{idx:02d}.png", slide["image_prompt"]))
        if layout == "split_concept":
            if slide.get("left_image_prompt"):
                prompt_pairs.append((f"slide_{idx:02d}_left.png", slide["left_image_prompt"]))
            if slide.get("right_image_prompt"):
                prompt_pairs.append((f"slide_{idx:02d}_right.png", slide["right_image_prompt"]))

        if not prompt_pairs:
            continue  # 일러스트 없는 슬라이드 (lecture_body / quote 등)

        item: dict[str, Any] = {"idx": idx, "files": {}}
        for filename, prompt in prompt_pairs:
            out_path = os.path.join(illustrations_dir, filename)
            ret = generate_gemini_image({
                "prompt": prompt,
                "style_preset": style_preset,
                "aspect_ratio": "16:9" if "left" not in filename and "right" not in filename else "1:1",
                "image_size": image_size,
                "quality": quality,
                "output_path": out_path,
            }, illustrations_dir)
            if "오류" in ret or "실패" in ret:
                failures.append(f"슬라이드 {idx} ({filename}): {ret.splitlines()[0]}")
                continue
            # 파일 키 결정 (image_path / left_image_path / right_image_path)
            if "_left" in filename:
                item["files"]["left_image_path"] = out_path
            elif "_right" in filename:
                item["files"]["right_image_path"] = out_path
            else:
                item["files"]["image_path"] = out_path

        if item["files"]:
            manifest_by_idx[idx] = item
            results.append(item)

    # manifest 저장
    final_items = sorted(manifest_by_idx.values(), key=lambda x: x.get("idx", 0))
    _write_json(manifest_path, {"style_preset": style_preset, "items": final_items})

    msg = [
        f"✓ ILLUSTRATE 단계 완료. {len([r for r in results if r['idx'] not in skipped])}장 생성/갱신.",
        f"manifest: {manifest_path}",
        f"style_preset: {style_preset}, quality: {quality}, image_size: {image_size}",
    ]
    if skipped:
        msg.append(f"건너뜀 (only_indices 모드): {len(skipped)}장")
    if failures:
        msg.append("실패:")
        msg.extend(f"  - {f}" for f in failures)
    msg.append(f"다음 단계: [engines:lecture_compose]{{lecture_dir: \"{lecture_dir}\"}}")
    return _append_criteria_marker("\n".join(msg), "lecture_illustrate")


# ============================================
# 단계 4 — COMPOSE (슬라이드 데크 합성)
# ============================================

def create_lecture_compose(tool_input: dict, output_base: str) -> str:
    """contents.json + illustrations/manifest.json → slide_shadcn 호출 → 최종 데크.

    파라미터:
      - lecture_dir (필수)
      - only_indices (선택): 부분 재합성. 미지정 시 전체
    """
    lecture_dir = tool_input.get("lecture_dir")
    if not lecture_dir or not os.path.isdir(lecture_dir):
        return f"오류: lecture_dir이 유효하지 않습니다: {lecture_dir}"
    lecture_dir = os.path.abspath(lecture_dir)

    contents_path = os.path.join(lecture_dir, "contents.json")
    if not os.path.exists(contents_path):
        return "오류: contents.json이 없습니다."
    doc = _read_json(contents_path)
    contents = doc.get("contents", [])
    design_system = doc.get("design_system", "sf_blueprint")

    manifest_path = os.path.join(lecture_dir, "illustrations", "manifest.json")
    manifest_by_idx: dict[int, dict] = {}
    if os.path.exists(manifest_path):
        manifest = _read_json(manifest_path)
        manifest_by_idx = {item["idx"]: item.get("files", {}) for item in manifest.get("items", [])}

    only = tool_input.get("only_indices")
    only_set = set(only) if only else None

    # 슬라이드별 image_path 머지 (manifest에서 가져옴)
    slides_for_shadcn: list[dict] = []
    for slide in contents:
        idx = slide.get("idx")
        if only_set is not None and idx not in only_set:
            continue
        merged = dict(slide)
        # idx는 슬라이드 엔진이 모름. layout만 살리고 idx는 제거 (그러나 manifest 매칭에는 사용)
        merged.pop("idx", None)
        files = manifest_by_idx.get(idx, {})
        for k, v in files.items():
            merged.setdefault(k, v)
        # image_prompt는 슬라이드 엔진 입력에 불필요
        merged.pop("image_prompt", None)
        merged.pop("left_image_prompt", None)
        merged.pop("right_image_prompt", None)
        slides_for_shadcn.append(merged)

    if not slides_for_shadcn:
        return "오류: 합성할 슬라이드가 없습니다 (only_indices 필터로 모두 제외되었을 수 있음)."

    deck_dir = os.path.join(lecture_dir, "deck")
    os.makedirs(deck_dir, exist_ok=True)

    # slide_shadcn 호출
    import importlib.util
    import sys
    module_path = os.path.join(os.path.dirname(__file__), "shadcn_slides.py")
    spec = importlib.util.spec_from_file_location("shadcn_slides", module_path)
    shadcn_slides = importlib.util.module_from_spec(spec)
    sys.modules["shadcn_slides"] = shadcn_slides
    spec.loader.exec_module(shadcn_slides)

    result = shadcn_slides.create_shadcn_slides({
        "slides": slides_for_shadcn,
        "design_system": design_system,
        "output_dir": deck_dir,
    }, output_base)

    msg = (
        f"✓ COMPOSE 단계 완료. {len(slides_for_shadcn)}장 데크 합성.\n"
        f"deck_dir: {deck_dir}\n"
        f"design_system: {design_system}\n"
        f"--- slide_shadcn 결과 ---\n{result}"
    )
    return _append_criteria_marker(msg, "lecture_compose")
