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
# backend 모듈(project_manager 등) import 보장 (인프로세스에선 보통 이미 path에 있음)
_BACKEND_DIR = str(Path(__file__).resolve().parents[5] / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
import lecture_store  # noqa: E402
import slide_ai  # noqa: E402
import lecture_export  # noqa: E402


# 앱/수동 모드가 쓰는 시스템 프로젝트 — 이들이 만든 강의는 전역에 둔다(현행 유지).
SYSTEM_PROJECT_IDS = {"앱모드", "수동모드"}


def _project_path_for(project_id: str):
    """project_id → 프로젝트 절대경로 (ProjectManager). 실패 시 None."""
    try:
        from project_manager import ProjectManager
        p = ProjectManager().get_project_path(project_id)
        if p and Path(p).exists():
            return str(Path(p).resolve())
    except Exception as e:
        print(f"[lecture_workspace] project_path 해석 실패 ({project_id}): {e}")
    return None


def _apply_roots(context) -> None:
    """ToolContext로부터 강의 쓰기/검색 루트를 해석해 lecture_store에 주입.

    원칙: 프로젝트 에이전트가 만든 강의는 그 프로젝트 outputs/lectures 아래.
          앱/수동 모드·시스템 AI·프로젝트 미상 → 전역 outputs/lectures (현행 유지).
    읽기는 [프로젝트, 전역] 순으로 폴백 — 전역에 있던 기존 강의도 계속 읽힌다.
    """
    try:
        global_root = lecture_store._global_lectures_root()
        pid = getattr(context, "project_id", None)
        agent_id = getattr(context, "agent_id", None)

        project_dir = None
        if pid and pid not in SYSTEM_PROJECT_IDS and agent_id != "system_ai":
            project_dir = _project_path_for(pid)

        if project_dir:
            project_root = Path(project_dir) / "outputs" / "lectures"
            lecture_store.set_roots(project_root, [project_root, global_root])
        else:
            lecture_store.set_roots(global_root, [global_root])
    except Exception as e:
        # 실패 시 전역으로 안전 폴백
        try:
            g = lecture_store._global_lectures_root()
            lecture_store.set_roots(g, [g])
        except Exception:
            pass
        print(f"[lecture_workspace] 루트 해석 실패, 전역 폴백: {e}")


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

    # 호출 컨텍스트(프로젝트 에이전트 vs 앱모드)에 따라 강의 저장/검색 루트 결정.
    _apply_roots(context)

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
        elif tool_name == "slide_image_edit":
            return _slide_image_edit(tool_input)
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
    records = [{
        "title": lec.get("title") or lec.get("lecture_id") or "(제목 없음)",
        "meta": " · ".join(p for p in [
            lec.get("audience") or None,
            (f"{lec.get('slide_count')}슬라이드" if lec.get("slide_count") is not None else None),
        ] if p),
        "summary": None,
        "url": None,
    } for lec in lectures]
    return _ok({
        "lectures": lectures,
        "count": len(lectures),
        "lectures_root": str(lecture_store.write_root().resolve()),
        "items": records,
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
        # 2026-06-23: 기본값을 native(통짜 이미지, NotebookLM식)로. 텍스트형 톤은 명시 지정.
        design_system=tool_input.get("design_system") or "native_vintage_book",
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
            "lectures_root": str(lecture_store.write_root().resolve()),
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

def _is_native_design(design: str) -> bool:
    """덱 design_system이 네이티브 통짜 경로인가 — "native" 또는 "native_<톤>"/"native:<톤>"."""
    d = (design or "").strip()
    return d == "native" or d.startswith("native_") or d.startswith("native:")


def _native_aesthetic(design: str) -> str:
    """native 또는 native_tech_minimal / native:blueprint 에서 톤 추출(기본 vintage_book)."""
    d = (design or "").strip()
    for sep in ("_", ":"):
        if d.startswith("native" + sep):
            return d.split(sep, 1)[1] or "vintage_book"
    return "vintage_book"


def _load_slide_native():
    import importlib.util
    import sys as _sys
    path = Path(__file__).resolve().parent.parent / "media_producer" / "slide_native.py"
    spec = importlib.util.spec_from_file_location("slide_native", str(path))
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["slide_native"] = mod
    spec.loader.exec_module(mod)
    return mod


def _neighbor_context(deck: dict, lecture_dir_path, focus_slide_id, insert_at):
    """새/편집 슬라이드의 앞뒤 이웃 슬라이드를 찾아 스타일 참고 자료를 모은다.

    Returns: (ref_png_paths, neighbor_briefs)
      - ref_png_paths: 존재하는 이웃 슬라이드 PNG 절대경로 리스트(앞 우선, 최대 2장).
      - neighbor_briefs: [{position, title, layout}] — 텍스트 경로 프롬프트 힌트용.
    위치 결정:
      - 편집(focus): slide_order 상 focus 양옆.
      - 신규: insert_at 앞(insert_at-1)과 그 자리(insert_at). insert_at 미지정=맨 끝 → 직전 1장.
    """
    order = deck.get("slide_order", [])
    slides = deck.get("slides", {})
    prev_sid = next_sid = None
    if focus_slide_id and focus_slide_id in order:
        idx = order.index(focus_slide_id)
        if idx > 0:
            prev_sid = order[idx - 1]
        if idx + 1 < len(order):
            next_sid = order[idx + 1]
    else:
        if insert_at is None:
            if order:
                prev_sid = order[-1]
        else:
            if 0 < insert_at <= len(order):
                prev_sid = order[insert_at - 1]
            if 0 <= insert_at < len(order):
                next_sid = order[insert_at]

    ref_paths, briefs = [], []
    for position, sid in (("앞", prev_sid), ("뒤", next_sid)):
        if not sid or sid not in slides:
            continue
        s = slides[sid]
        briefs.append({"position": position, "title": s.get("title"), "layout": s.get("layout")})

    # 스타일 참고 이미지는 '하나'만 쓴다 — 앞뒤 스타일이 서로 다를 때 둘을 첨부하면
    # 이미지 모델이 상충하는 단서를 섞어 결과가 흔들린다. 덱은 위→아래로 읽히므로
    # **직전(앞) 슬라이드를 기준 앵커**로 삼고(앞이 없으면 뒤), 그 한 장에 맞춰 일관성을 준다.
    # 업로드한 원본 이미지(layout=="image")는 슬라이드 디자인이 아니므로 앵커에서 제외.
    for sid in (prev_sid, next_sid):
        if not sid or sid not in slides:
            continue
        if slides[sid].get("layout") == "image":
            continue
        png_rel = slides[sid].get("png_file")
        if png_rel:
            p = (lecture_dir_path / png_rel).resolve()
            if p.exists():
                ref_paths.append(str(p))
                break
    return ref_paths, briefs


def _generate_native_slide(
    lecture_id, deck, slides_dir_path, instruction, focus_slide_id, insert_at, design,
    reference_images=None, image_quality="pro",
) -> dict:
    """네이티브 통짜 이미지 슬라이드 — slide_native 위임 후 deck에 등록(NotebookLM식)."""
    slide_id = focus_slide_id or lecture_store.next_slide_id(deck)
    sn = _load_slide_native()

    ctx = []
    if deck.get("title"):
        ctx.append(f"강의: {deck['title']}")
    if deck.get("thesis"):
        ctx.append(f"핵심 논지: {deck['thesis']}")
    if deck.get("audience"):
        ctx.append(f"청중: {deck['audience']}")
    tool_input = {"instruction": instruction, "aesthetic": _native_aesthetic(design)}
    if ctx:
        tool_input["content"] = " / ".join(ctx)
    if reference_images:
        tool_input["style_reference_images"] = reference_images
    # 이미지 품질/모델: fast=Nano Banana 2(Gemini 3.1 Flash, 저가·1K) / pro=Nano Banana Pro(Gemini 3 Pro, 고품질·2K)
    if (image_quality or "pro").strip() == "fast":
        tool_input["quality"] = "fast"
        tool_input["image_size"] = "1K"
    else:
        tool_input["quality"] = "pro"
        tool_input["image_size"] = "2K"

    result = json.loads(
        sn.create_native_slide(tool_input, str(slides_dir_path), slide_id=slide_id)
    )
    if not result.get("success"):
        raise RuntimeError(result.get("message") or "네이티브 슬라이드 생성 실패")

    spec = result.get("spec") or {}
    spec_meta = {
        "layout": "native", "device": result.get("device"), "aesthetic": result.get("aesthetic"),
        "title": result.get("title"), **spec,
    }
    with open(slides_dir_path / f"{slide_id}.json", "w", encoding="utf-8") as f:
        json.dump(spec_meta, f, ensure_ascii=False, indent=2)

    png_rel = f"slides/{slide_id}.png"
    spec_rel = f"slides/{slide_id}.json"
    lecture_store.register_slide(
        lecture_id=lecture_id, slide_id=slide_id,
        title=result.get("title") or "(제목 없음)",
        layout="native", spec_file=spec_rel, png_file=png_rel, insert_at=insert_at,
    )
    return {
        "slide_id": slide_id, "slide": spec_meta, "png_file": png_rel, "spec_file": spec_rel,
        # 절대 경로 — 평가 루프의 시각 산출물 수집기가 결과 문자열에서 이미지를 찾게 한다
        # (상대경로 png_file은 정규식 /…png 에 안 걸림). 평가자가 픽셀을 직접 보는 통로.
        "png_path": str((slides_dir_path / f"{slide_id}.png").resolve()),
        "reasoning": result.get("reasoning"), "device": result.get("device"),
        "verify": result.get("verify"),
        "mode": "edit" if focus_slide_id else "create",
    }


def _generate_and_register_slide(
    lecture_id: str,
    instruction: str,
    focus_slide_id: str = None,
    insert_at: int = None,
    forced_layout: str = None,
    image_quality: str = "pro",
) -> dict:
    """AI 호출 → 렌더 → deck 등록의 공통 흐름. dict 반환.

    forced_layout: UI에서 명시적으로 layout을 선택한 경우. AI가 그 layout으로 강제 생성.
    """
    deck = lecture_store.read_deck(lecture_id)
    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    slides_dir_path = lecture_store.slides_dir(lecture_id)

    # 앞뒤 이웃 슬라이드 — 스타일 일관성 참고(항상 자동). 이미지 경로는 native 경로,
    # 간단 brief는 텍스트 경로 프롬프트 힌트로 쓴다.
    ref_png_paths, neighbor_briefs = _neighbor_context(
        deck, lecture_dir_path, focus_slide_id, insert_at
    )

    # 네이티브 통짜 이미지(NotebookLM식, 기본)면 별도 경로 — media_producer/slide_native 위임.
    # 그 외(명시적 텍스트 톤)는 아래 custom HTML 경로.
    # 단, 강의자가 UI 레이아웃 드롭다운에서 명시적으로 비-native 레이아웃(텍스트/일러스트/custom)을
    # 강제하면 그 한 장만 통짜 이미지가 아니라 HTML 경로로 그린다(혼합 덱 허용). 레이아웃 강제는
    # 본디 슬라이드별 컨트롤이므로 덱 기본(native)을 슬라이드 단위로 덮는 것이 least-surprise.
    design = (deck.get("design_system") or "native_vintage_book").strip()
    native_deck = _is_native_design(design)
    force_text_on_native = native_deck and bool(forced_layout) and forced_layout != "native"
    if native_deck and not force_text_on_native:
        return _generate_native_slide(
            lecture_id, deck, slides_dir_path, instruction, focus_slide_id, insert_at, design,
            reference_images=ref_png_paths, image_quality=image_quality,
        )

    # HTML 경로가 쓸 design_system — native 덱을 슬라이드 단위로 덮는 경우 native_ 접두를 떼어
    # HTML 렌더러가 아는 톤으로 매핑(native_vintage_book → vintage_book). 비-native 덱은 그대로.
    html_design = _native_aesthetic(design) if native_deck else design

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

    # AI 호출 — 프롬프트 메타의 '디자인'도 HTML 톤으로 맞춘다(native 덱을 텍스트로 덮을 때
    # 'native_vintage_book'이 메타에 박혀 AI가 통짜 이미지 스펙을 내려는 오정렬 방지).
    prompt_deck = {**deck, "design_system": html_design} if html_design != design else deck
    ai_response = slide_ai.generate_slide_response(
        deck=prompt_deck,
        lecture_dir=lecture_dir_path,
        user_instruction=instruction,
        focus_slide=focus_spec,
        forced_layout=forced_layout,
        neighbor_briefs=neighbor_briefs,
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
                design_system=html_design,
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
        design_system=html_design,
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
        # AI가 뽑은 스피커 노트를 강의 노트 초안으로 시드 (사용자가 이미 적었으면 보존됨)
        speaker_note=ai_response.get("speaker_note"),
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
        # 절대 경로 — 평가 루프 시각 산출물 수집기가 결과에서 이미지를 찾게 한다 (네이티브 경로와 동일 의도)
        "png_path": str((lecture_dir_path / rendered["png_file"]).resolve()),
        "reasoning": ai_response.get("reasoning"),
        "speaker_note": ai_response.get("speaker_note"),
        "memo_signals": memo_signals,
        "mode": "edit" if focus_slide_id else "create",
    }


_VALID_LAYOUTS = {
    "hero", "lecture_body", "metaphor_story", "comparison_table", "factbox", "quote",
    "hero_illustration", "illustration_anchor", "split_concept",
    "illustration_background", "illustration_overlay", "comparison_iconic",
    "custom",  # 자유형 — AI가 슬라이드 HTML을 직접 작성 (고정 틀 없음)
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
        image_quality=(tool_input.get("image_quality") or "pro"),
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

    # 통짜 이미지(native)·업로드 이미지(image) **슬라이드**는 spec→HTML 재렌더가 아니라 이미지
    # *재생성*이라야 톤이 바뀐다(HTML 재렌더기는 native/image spec을 못 그림). 재생성 경로로 안내.
    # ★판단은 덱이 아니라 *이 슬라이드의 layout*으로 — native 덱에 끼운 텍스트형(HTML) 슬라이드는
    #  재렌더 가능하다(혼합 덱). native 슬라이드는 등록 layout이 "native"라 그대로 걸린다.
    if slide_meta.get("layout") in ("native", "image"):
        return _err(
            "통짜 이미지/업로드 이미지 슬라이드는 rerender 대신 슬라이드를 다시 생성하세요 "
            "([self:slide]{op:\"edit\", slide_id, instruction} 또는 op:\"create\"). "
            "통짜 이미지는 재렌더가 아니라 재생성이 맞습니다.",
            error_type="unsupported",
        )

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
    # 덱이 native여도 이 슬라이드는 HTML이므로 native_ 접두를 떼어 렌더러가 아는 톤으로 매핑.
    _deck_design = (deck.get("design_system") or "vintage_book").strip()
    html_design = _native_aesthetic(_deck_design) if _is_native_design(_deck_design) else _deck_design
    try:
        rendered = slide_ai.render_slide_to_files(
            spec=spec,
            design_system=html_design,
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

    # 통짜 이미지(native)·업로드 이미지(image) **슬라이드**는 글자가 PNG에 구워져 있어 spec patch→HTML
    # 재렌더가 불가능하다(HTML 렌더기가 native/image spec을 못 그림). 그 슬라이드만 재생성 경로로 안내.
    # ★판단 기준은 덱이 아니라 *이 슬라이드의 layout*이다 — 덱이 native여도 그 안에 끼운 텍스트형(HTML)
    #  슬라이드는 필드 직접 편집이 가능하다(혼합 덱). native 슬라이드는 spec에 layout:"native"를 가져
    #  아래 조건에 그대로 걸리므로, 덱 단위 _is_native_design 검사는 텍스트 슬라이드를 과잉 차단한다.
    if spec.get("layout") in ("native", "image"):
        return _err(
            "통짜 이미지/업로드 이미지 슬라이드는 필드 직접 편집을 지원하지 않습니다. "
            "제목·내용을 바꾸려면 슬라이드를 선택한 뒤 AI 채팅으로 다시 생성하세요(예: \"제목을 '...'로 바꿔줘\").",
            error_type="validation",
        )

    # patch 적용 — shallow update. spec[k] = v for each k,v in patch.
    # None은 사용자가 의도적으로 비우려 한 것으로 처리하지 않고 제거.
    for key, value in patch.items():
        if value is None:
            spec.pop(key, None)
        else:
            spec[key] = value

    # 재렌더 — 덱이 native여도 이 슬라이드는 HTML이므로 native_ 접두를 떼어 렌더러가 아는 톤으로 매핑
    # (native_vintage_book → vintage_book). 비-native 덱은 그대로.
    _deck_design = (deck.get("design_system") or "vintage_book").strip()
    html_design = _native_aesthetic(_deck_design) if _is_native_design(_deck_design) else _deck_design
    try:
        rendered = slide_ai.render_slide_to_files(
            spec=spec,
            design_system=html_design,
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
        image_quality=(tool_input.get("image_quality") or "pro"),
    )
    return _ok(result)


def _slide_image_edit(tool_input: dict) -> str:
    """통짜 이미지/업로드 이미지 슬라이드를 '부분 수정' — 다시 그리지 않고 현재 PNG를 편집.

    제목 한 줄만 바꾸려고 전체 재생성하면 비싸고 구도가 달라지는 문제를 해결.
    layout이 native/image인 슬라이드에만 적용(텍스트 슬라이드는 필드 편집 ✏️ 사용).
    """
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    slide_id = (tool_input.get("slide_id") or "").strip()
    instruction = (tool_input.get("instruction") or "").strip()
    if not lecture_id or not slide_id:
        return _err("lecture_id와 slide_id 모두 필수입니다.")
    if not instruction:
        return _err("instruction(수정 요청)은 필수입니다.")

    deck = lecture_store.read_deck(lecture_id)
    meta = deck.get("slides", {}).get(slide_id)
    if not meta:
        return _err(f"슬라이드 없음: {slide_id}", error_type="not_found")
    if meta.get("layout") not in ("native", "image"):
        return _err(
            "이미지 부분 수정은 통짜 이미지/이미지 슬라이드에서만 됩니다. "
            "텍스트 슬라이드는 필드 편집(✏️)을 쓰세요.",
            error_type="validation",
        )

    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    slides_dir_path = lecture_store.slides_dir(lecture_id)
    base_png = lecture_dir_path / (meta.get("png_file") or "")
    if not base_png.exists():
        return _err(f"원본 이미지가 없습니다: {base_png}")

    image_quality = (tool_input.get("image_quality") or "pro").strip()
    ti = {"instruction": instruction}
    if image_quality == "fast":
        ti["quality"], ti["image_size"] = "fast", "1K"
    else:
        ti["quality"], ti["image_size"] = "pro", "2K"

    sn = _load_slide_native()
    result = json.loads(sn.edit_native_slide(ti, str(base_png), str(slides_dir_path), slide_id))
    if not result.get("success"):
        raise RuntimeError(result.get("message") or "이미지 편집 실패")

    # 썸네일 캐시 버스트 (PNG는 같은 경로로 덮어씀)
    from datetime import datetime
    deck["slides"][slide_id]["updated_at"] = datetime.now().isoformat(timespec="seconds")
    lecture_store.write_deck(lecture_id, deck)

    return _ok({
        "slide_id": slide_id,
        "mode": "image_edit",
        "png_file": meta.get("png_file"),
        "png_path": str(base_png.resolve()),
        "title": meta.get("title"),
    })


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
