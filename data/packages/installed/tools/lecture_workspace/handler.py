"""
handler.py - lecture_workspace 패키지 도구 디스패처

ToolContext 시그니처: execute(tool_input, context) -> str

데이터 레이어는 lecture_store 모듈에 모두 모여 있고, 이 파일은 도구 이름으로 분기 + 입력 검증 + JSON 응답 포맷만 담당.

Step 1 (현재): 강의 CRUD + 데크 조작 + 재료 관리 + lecture_open 스텁.
Step 2/3에서 추가 예정: slide_create, slide_edit (AI 슬라이드 생성/편집).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# lecture_store / slide_ai / lecture_export를 같은 디렉토리에서 import
sys.path.insert(0, os.path.dirname(__file__))
import lecture_store  # noqa: E402
import slide_ai  # noqa: E402
import lecture_export  # noqa: E402


def _ok(payload: dict) -> str:
    """성공 응답 — payload를 JSON 문자열로."""
    return json.dumps({"success": True, **payload}, ensure_ascii=False, indent=2)


def _err(message: str, **extra) -> str:
    """에러 응답."""
    return json.dumps({"success": False, "error": message, **extra}, ensure_ascii=False, indent=2)


# 2026-05-28 dispatcher 표준화 — 단일 액션 op 키 메타데이터 (browser-action 패턴).
# 값은 None — 분기 로직은 _dispatch_*_op 함수 안에 그대로 유지.
# --check 가 이 dict 키로 src.ops.values 와 정확 비교.
_OP_DISPATCHERS = {
    "lecture_op": {"list": None, "create": None, "load": None, "delete": None, "open": None},
    "slide_op": {"create": None, "edit": None, "delete": None, "patch": None, "rerender": None},
    "material_op": {"add": None, "remove": None},
    "deck_op": {"reorder": None, "export": None},
}
# 모두 op 필수 — _OP_DEFAULTS 항목 없음.


def execute(tool_input: dict, context) -> str:
    """도구 실행 entry point (ToolContext 기반)."""
    tool_name = context.tool_name

    try:
        # 통합 도구 (op 분기) — IBL 어휘에 노출되는 4개
        if tool_name == "lecture_op":
            return _dispatch_lecture_op(tool_input)
        elif tool_name == "slide_op":
            return _dispatch_slide_op(tool_input)
        elif tool_name == "material_op":
            return _dispatch_material_op(tool_input)
        elif tool_name == "deck_op":
            return _dispatch_deck_op(tool_input)
        # 옛 도구 이름 (직접 호출 호환 유지)
        elif tool_name == "lecture_list":
            return _lecture_list(tool_input)
        elif tool_name == "lecture_create":
            return _lecture_create(tool_input)
        elif tool_name == "lecture_load":
            return _lecture_load(tool_input)
        elif tool_name == "lecture_delete":
            return _lecture_delete(tool_input)
        elif tool_name == "lecture_open":
            return _lecture_open(tool_input)
        elif tool_name == "deck_reorder":
            return _deck_reorder(tool_input)
        elif tool_name == "slide_delete":
            return _slide_delete(tool_input)
        elif tool_name == "material_add":
            return _material_add(tool_input)
        elif tool_name == "material_remove":
            return _material_remove(tool_input)
        elif tool_name == "slide_create":
            return _slide_create(tool_input)
        elif tool_name == "slide_edit":
            return _slide_edit(tool_input)
        elif tool_name == "slide_rerender":
            return _slide_rerender(tool_input)
        elif tool_name == "slide_patch_spec":
            return _slide_patch_spec(tool_input)
        elif tool_name == "deck_export":
            return _deck_export(tool_input)
        else:
            return _err(f"알 수 없는 도구: {tool_name}")
    except FileNotFoundError as e:
        return _err(str(e), error_type="not_found")
    except ValueError as e:
        return _err(str(e), error_type="validation")
    except Exception as e:
        return _err(f"실행 중 예외: {e}", error_type=type(e).__name__)


# ─────────────────────────────────────────────────────────────────────
# 통합 도구 op 디스패처 (lecture_op / slide_op / material_op / deck_op)
# ─────────────────────────────────────────────────────────────────────

def _dispatch_lecture_op(tool_input: dict) -> str:
    op = (tool_input.get("op") or "").strip()
    if not op:
        return _err("op는 필수입니다. (list|create|load|delete|open)")
    if op == "list":
        return _lecture_list(tool_input)
    if op == "create":
        return _lecture_create(tool_input)
    if op == "load":
        return _lecture_load(tool_input)
    if op == "delete":
        return _lecture_delete(tool_input)
    if op == "open":
        return _lecture_open(tool_input)
    return _err(f"알 수 없는 op: {op}. (list|create|load|delete|open 중 하나)")


def _dispatch_slide_op(tool_input: dict) -> str:
    op = (tool_input.get("op") or "").strip()
    if not op:
        return _err("op는 필수입니다. (create|edit|delete|patch|rerender)")
    if op == "create":
        return _slide_create(tool_input)
    if op == "edit":
        return _slide_edit(tool_input)
    if op == "delete":
        return _slide_delete(tool_input)
    if op == "patch":
        return _slide_patch_spec(tool_input)
    if op == "rerender":
        return _slide_rerender(tool_input)
    return _err(f"알 수 없는 op: {op}. (create|edit|delete|patch|rerender 중 하나)")


def _dispatch_material_op(tool_input: dict) -> str:
    op = (tool_input.get("op") or "").strip()
    if not op:
        return _err("op는 필수입니다. (add|remove)")
    if op == "add":
        return _material_add(tool_input)
    if op == "remove":
        return _material_remove(tool_input)
    return _err(f"알 수 없는 op: {op}. (add|remove 중 하나)")


def _dispatch_deck_op(tool_input: dict) -> str:
    op = (tool_input.get("op") or "").strip()
    if not op:
        return _err("op는 필수입니다. (reorder|export)")
    if op == "reorder":
        return _deck_reorder(tool_input)
    if op == "export":
        return _deck_export(tool_input)
    return _err(f"알 수 없는 op: {op}. (reorder|export 중 하나)")


# ─────────────────────────────────────────────────────────────────────
# 강의 CRUD
# ─────────────────────────────────────────────────────────────────────

def _lecture_list(tool_input: dict) -> str:
    lectures = lecture_store.list_lectures()
    return _ok({
        "lectures": lectures,
        "count": len(lectures),
        "lectures_root": str(lecture_store.LECTURES_ROOT.resolve()),
    })


def _lecture_create(tool_input: dict) -> str:
    title = (tool_input.get("title") or "").strip()
    if not title:
        return _err("title은 필수입니다.")
    deck = lecture_store.create_lecture(
        title=title,
        audience=tool_input.get("audience"),
        thesis=tool_input.get("thesis"),
        duration_minutes=tool_input.get("duration_minutes"),
        design_system=tool_input.get("design_system") or "vintage_book",
    )
    return _ok({
        "lecture_id": deck["lecture_id"],
        "deck": deck,
        "lecture_dir": str(lecture_store.lecture_dir(deck["lecture_id"]).resolve()),
    })


def _lecture_load(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    data = lecture_store.load_lecture(lecture_id)
    return _ok(data)


def _lecture_delete(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    confirm = bool(tool_input.get("confirm"))
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    if not confirm:
        return _err(
            "삭제하려면 confirm=true가 필요합니다. 사용자 확인 후 호출하세요.",
            error_type="confirmation_required",
        )
    result = lecture_store.delete_lecture(lecture_id)
    return _ok(result)


# ─────────────────────────────────────────────────────────────────────
# 워크스페이스 창 열기 (Step 2에서 IPC 연결 예정)
# ─────────────────────────────────────────────────────────────────────

def _lecture_open(tool_input: dict) -> str:
    """강의 만들기 창 열기 — Launcher WS로 Electron에 신호 + 데이터 반환.

    AI가 "강의만들기창 열어줘" 받으면 이 액션 호출 →
    Electron 메인 프로세스가 새 BrowserWindow를 띄움.
    """
    lecture_id = (tool_input.get("lecture_id") or "").strip() or None

    # 존재 확인 (lecture_id 지정 시)
    if lecture_id and not lecture_store.lecture_exists(lecture_id):
        return _err(
            f"강의를 찾을 수 없습니다: {lecture_id}",
            error_type="not_found",
            hint="lecture_list로 사용 가능한 강의를 확인하세요.",
        )

    # Launcher WS로 Electron에 창 열기 신호
    ws_sent = False
    ws_error = None
    try:
        import asyncio
        from api_websocket import send_launcher_command, get_launcher_ws

        if not get_launcher_ws():
            ws_error = "Launcher WS 미연결 (Electron 메인 창이 실행 중인지 확인하세요)"
        else:
            params = {"lecture_id": lecture_id} if lecture_id else {}
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    fut = asyncio.run_coroutine_threadsafe(
                        send_launcher_command("open_lecture_workspace", params),
                        loop,
                    )
                    ws_sent = fut.result(timeout=5)
                else:
                    ws_sent = asyncio.run(
                        send_launcher_command("open_lecture_workspace", params)
                    )
            except RuntimeError:
                ws_sent = asyncio.run(
                    send_launcher_command("open_lecture_workspace", params)
                )
    except Exception as e:
        ws_error = f"WS 전송 예외: {e}"

    payload = {
        "action": "open_lecture_workspace",
        "lecture_id": lecture_id,
        "window_opened": ws_sent,
    }
    if ws_error:
        payload["ws_warning"] = ws_error

    # 같이 데이터도 반환 (AI가 즉시 확인용)
    if lecture_id:
        payload["data"] = lecture_store.load_lecture(lecture_id)
    else:
        payload["data"] = {
            "lectures": lecture_store.list_lectures(),
            "lectures_root": str(lecture_store.LECTURES_ROOT.resolve()),
        }

    return _ok(payload)


# ─────────────────────────────────────────────────────────────────────
# 데크 조작
# ─────────────────────────────────────────────────────────────────────

def _deck_reorder(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    order = tool_input.get("order")
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    if not isinstance(order, list):
        return _err("order는 slide_id 배열이어야 합니다.")
    result = lecture_store.reorder_deck(lecture_id, order)
    return _ok(result)


def _slide_delete(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    slide_id = (tool_input.get("slide_id") or "").strip()
    if not lecture_id or not slide_id:
        return _err("lecture_id와 slide_id 모두 필수입니다.")
    result = lecture_store.delete_slide(lecture_id, slide_id)
    return _ok(result)


# ─────────────────────────────────────────────────────────────────────
# 재료 관리
# ─────────────────────────────────────────────────────────────────────

def _material_add(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    if not lecture_store.lecture_exists(lecture_id):
        return _err(f"강의를 찾을 수 없습니다: {lecture_id}", error_type="not_found")

    file_path = tool_input.get("file_path")
    text = tool_input.get("text")
    filename = tool_input.get("filename")

    if file_path:
        entry = lecture_store.add_material_from_file(lecture_id, file_path)
    elif text is not None and filename:
        entry = lecture_store.add_material_from_text(lecture_id, text, filename)
    else:
        return _err(
            "file_path 또는 (text + filename) 둘 중 하나는 제공해야 합니다.",
            hint="파일 복사: {file_path: '/...'}, 텍스트 저장: {text: '...', filename: 'notes.md'}",
        )

    # 재료가 바뀌면 캐시 무효화 (다음 슬라이드 생성 시 자동 재생성)
    try:
        slide_ai.invalidate_lecture_cache(lecture_id)
    except Exception as e:
        print(f"[handler] 캐시 무효화 실패 (무시): {e}")

    return _ok({"material": entry})


def _material_remove(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    filename = (tool_input.get("filename") or "").strip()
    if not lecture_id or not filename:
        return _err("lecture_id와 filename 모두 필수입니다.")
    result = lecture_store.remove_material(lecture_id, filename)

    # 재료가 바뀌면 캐시 무효화
    try:
        slide_ai.invalidate_lecture_cache(lecture_id)
    except Exception as e:
        print(f"[handler] 캐시 무효화 실패 (무시): {e}")

    return _ok(result)


# ─────────────────────────────────────────────────────────────────────
# 슬라이드 생성/편집 (AI)
# ─────────────────────────────────────────────────────────────────────

def _generate_and_register_slide(
    lecture_id: str,
    instruction: str,
    focus_slide_id: str = None,
    insert_at: int = None,
    forced_layout: str = None,
) -> dict:
    """AI 호출 → 렌더 → deck 등록의 공통 흐름. dict 반환.

    forced_layout: UI에서 명시적으로 layout을 선택한 경우. AI가 그 layout으로 강제 생성.
    """
    deck = lecture_store.read_deck(lecture_id)
    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    slides_dir_path = lecture_store.slides_dir(lecture_id)

    # focus slide의 현재 spec 로드 (편집 모드)
    focus_spec = None
    if focus_slide_id:
        if focus_slide_id not in deck.get("slides", {}):
            raise ValueError(f"슬라이드 없음: {focus_slide_id}")
        spec_file = lecture_dir_path / deck["slides"][focus_slide_id]["spec_file"]
        if spec_file.exists():
            try:
                with open(spec_file, "r", encoding="utf-8") as f:
                    focus_spec = json.load(f)
            except Exception as e:
                print(f"[slide_edit] focus spec 읽기 실패: {e}")

    # AI 호출
    ai_response = slide_ai.generate_slide_response(
        deck=deck,
        lecture_dir=lecture_dir_path,
        user_instruction=instruction,
        focus_slide=focus_spec,
        forced_layout=forced_layout,
    )

    slide_spec = ai_response.get("slide")
    if not isinstance(slide_spec, dict):
        raise ValueError("AI 응답의 'slide'가 객체가 아닙니다.")

    # slide_id 결정
    if focus_slide_id:
        slide_id = focus_slide_id
    else:
        slide_id = lecture_store.next_slide_id(deck)

    # 일러스트 layout이면 이미지 생성 → spec에 image_path 주입
    illustrations = ai_response.get("illustrations")
    if illustrations and isinstance(illustrations, dict):
        try:
            injected = slide_ai.generate_slide_illustrations(
                illustrations=illustrations,
                design_system=deck.get("design_system", "vintage_book"),
                slides_dir=slides_dir_path,
                slide_id=slide_id,
            )
            # 절대경로를 slide_spec에 주입 (slide_shadcn이 자동 base64 변환)
            slide_spec.update(injected)
        except Exception as e:
            # 이미지 생성 실패 — 슬라이드 자체는 텍스트만으로 진행 (degraded)
            print(f"[slide_create] 일러스트 생성 실패, 텍스트만으로 진행: {e}")

    # 렌더 → 파일 저장
    rendered = slide_ai.render_slide_to_files(
        spec=slide_spec,
        design_system=deck.get("design_system", "vintage_book"),
        slides_dir=slides_dir_path,
        slide_id=slide_id,
    )

    # deck 갱신
    title = slide_spec.get("title") or slide_spec.get("quote", "")[:30] or "(제목 없음)"
    layout = slide_spec.get("layout", "lecture_body")
    lecture_store.register_slide(
        lecture_id=lecture_id,
        slide_id=slide_id,
        title=title,
        layout=layout,
        spec_file=rendered["spec_file"],
        png_file=rendered["png_file"],
        insert_at=insert_at,
    )

    # 누적 메모 패치
    memo_signals = ai_response.get("memo_signals") or {}
    if isinstance(memo_signals, dict) and memo_signals:
        try:
            lecture_store.update_cumulative_memo(lecture_id, memo_signals)
        except Exception as e:
            print(f"[slide_create] 메모 패치 실패: {e}")

    # 결과
    return {
        "slide_id": slide_id,
        "slide": slide_spec,
        "png_file": rendered["png_file"],
        "spec_file": rendered["spec_file"],
        "reasoning": ai_response.get("reasoning"),
        "speaker_note": ai_response.get("speaker_note"),
        "memo_signals": memo_signals,
        "mode": "edit" if focus_slide_id else "create",
    }


_VALID_LAYOUTS = {
    "hero", "lecture_body", "metaphor_story", "comparison_table", "factbox", "quote",
    "hero_illustration", "illustration_anchor", "split_concept",
    "illustration_background", "illustration_overlay", "comparison_iconic",
}


def _slide_create(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    instruction = (tool_input.get("instruction") or "").strip()
    insert_at = tool_input.get("insert_at")
    forced_layout = (tool_input.get("layout") or "").strip() or None
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    if not instruction:
        return _err("instruction(강의자의 자연어 요청)은 필수입니다.")
    if insert_at is not None:
        try:
            insert_at = int(insert_at)
        except (TypeError, ValueError):
            return _err("insert_at은 정수여야 합니다.")
    if forced_layout and forced_layout not in _VALID_LAYOUTS:
        return _err(f"알 수 없는 layout: {forced_layout!r}. 사용 가능: {sorted(_VALID_LAYOUTS)}")
    result = _generate_and_register_slide(
        lecture_id=lecture_id,
        instruction=instruction,
        focus_slide_id=None,
        insert_at=insert_at,
        forced_layout=forced_layout,
    )
    return _ok(result)


def _slide_rerender(tool_input: dict) -> str:
    """슬라이드 spec 변경 없이 PNG만 재렌더.

    용도: design_system이 바뀐 후 같은 내용으로 새 톤 적용. AI 호출 없음 — 빠르고 비결정적
    응답으로 spec이 흔들리는 일도 없음.
    """
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    slide_id = (tool_input.get("slide_id") or "").strip()
    if not lecture_id or not slide_id:
        return _err("lecture_id와 slide_id 모두 필수입니다.")

    deck = lecture_store.read_deck(lecture_id)
    slide_meta = deck.get("slides", {}).get(slide_id)
    if not slide_meta:
        return _err(f"슬라이드 없음: {slide_id}", error_type="not_found")

    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    slides_dir_path = lecture_store.slides_dir(lecture_id)

    # 현재 spec 로드
    spec_file = lecture_dir_path / slide_meta["spec_file"]
    if not spec_file.exists():
        return _err(f"spec 파일 없음: {spec_file}")
    try:
        with open(spec_file, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as e:
        return _err(f"spec 파일 읽기 실패: {e}")

    # 재렌더 (현재 design_system 적용, 일러스트는 기존 파일 재사용)
    try:
        rendered = slide_ai.render_slide_to_files(
            spec=spec,
            design_system=deck.get("design_system", "vintage_book"),
            slides_dir=slides_dir_path,
            slide_id=slide_id,
        )
    except Exception as e:
        return _err(f"재렌더 실패: {e}", error_type="render_error")

    # deck의 slide updated_at 갱신 (UI 캐시 무효화 + 변경 추적)
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    deck["slides"][slide_id]["updated_at"] = now
    lecture_store.write_deck(lecture_id, deck)

    return _ok({
        "slide_id": slide_id,
        "mode": "rerender",
        "design_system": deck.get("design_system"),
        "png_file": rendered["png_file"],
        "title": spec.get("title") or slide_meta.get("title"),
    })


def _slide_patch_spec(tool_input: dict) -> str:
    """슬라이드 spec 필드를 직접 patch + PNG 재렌더. AI 호출 없음.

    PowerPoint식 "필드 편집"의 백엔드. 사용자가 폼에서 직접 입력한 값을 그대로 적용.

    patch dict의 키-값을 spec에 shallow update (dict.update). image_path류·복잡 구조도
    문자열/배열/객체 그대로 받아 spec에 주입. layout 키는 변경 위험이 커서 거부 —
    layout 바꾸려면 slide_edit + forced_layout 사용.
    """
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    slide_id = (tool_input.get("slide_id") or "").strip()
    patch = tool_input.get("patch")
    if not lecture_id or not slide_id:
        return _err("lecture_id와 slide_id 모두 필수입니다.")
    if not isinstance(patch, dict) or not patch:
        return _err("patch는 비어있지 않은 객체여야 합니다.")
    if "layout" in patch:
        return _err(
            "layout은 직접 patch로 못 바꿉니다. slide_edit + forced_layout을 쓰세요.",
            hint="레이아웃이 바뀌면 필요 필드도 달라져 spec이 깨질 수 있음.",
        )

    deck = lecture_store.read_deck(lecture_id)
    slide_meta = deck.get("slides", {}).get(slide_id)
    if not slide_meta:
        return _err(f"슬라이드 없음: {slide_id}", error_type="not_found")

    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    slides_dir_path = lecture_store.slides_dir(lecture_id)

    # 현재 spec 로드
    spec_file = lecture_dir_path / slide_meta["spec_file"]
    if not spec_file.exists():
        return _err(f"spec 파일 없음: {spec_file}")
    try:
        with open(spec_file, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as e:
        return _err(f"spec 파일 읽기 실패: {e}")

    # patch 적용 — shallow update. spec[k] = v for each k,v in patch.
    # None은 사용자가 의도적으로 비우려 한 것으로 처리하지 않고 제거.
    for key, value in patch.items():
        if value is None:
            spec.pop(key, None)
        else:
            spec[key] = value

    # 재렌더
    try:
        rendered = slide_ai.render_slide_to_files(
            spec=spec,
            design_system=deck.get("design_system", "vintage_book"),
            slides_dir=slides_dir_path,
            slide_id=slide_id,
        )
    except Exception as e:
        return _err(f"재렌더 실패: {e}", error_type="render_error")

    # deck 메타 갱신 (title이 patch에 있으면 deck의 slide title도 갱신)
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    deck["slides"][slide_id]["updated_at"] = now
    new_title = spec.get("title") or spec.get("quote", "")[:30]
    if new_title:
        deck["slides"][slide_id]["title"] = new_title
    lecture_store.write_deck(lecture_id, deck)

    return _ok({
        "slide_id": slide_id,
        "mode": "patch",
        "spec": spec,
        "png_file": rendered["png_file"],
        "patched_keys": list(patch.keys()),
        "design_system": deck.get("design_system"),
    })


def _slide_edit(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    slide_id = (tool_input.get("slide_id") or "").strip()
    instruction = (tool_input.get("instruction") or "").strip()
    forced_layout = (tool_input.get("layout") or "").strip() or None
    if not lecture_id or not slide_id:
        return _err("lecture_id와 slide_id 모두 필수입니다.")
    if not instruction:
        return _err("instruction(편집 요청)은 필수입니다.")
    if forced_layout and forced_layout not in _VALID_LAYOUTS:
        return _err(f"알 수 없는 layout: {forced_layout!r}. 사용 가능: {sorted(_VALID_LAYOUTS)}")
    result = _generate_and_register_slide(
        lecture_id=lecture_id,
        instruction=instruction,
        focus_slide_id=slide_id,
        forced_layout=forced_layout,
    )
    return _ok(result)


# ─────────────────────────────────────────────────────────────────────
# 데크 내보내기 (PDF/PPTX)
# ─────────────────────────────────────────────────────────────────────

def _deck_export(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    fmt = (tool_input.get("format") or "").strip().lower()
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    if fmt not in ("pdf", "pptx", "pptx_image", "pptx_editable"):
        return _err(
            f"format은 'pdf', 'pptx'(이미지), 'pptx_editable'(편집 가능) 중 하나여야 합니다. 받은 값: {fmt!r}"
        )
    if not lecture_store.lecture_exists(lecture_id):
        return _err(f"강의 없음: {lecture_id}", error_type="not_found")
    result = lecture_export.export_deck(lecture_id, fmt)
    return _ok(result)
