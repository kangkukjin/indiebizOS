"""api_lecture_workspace.py - 강의 만들기 워크스페이스 REST API

UI가 호출하는 얇은 REST 엔드포인트. 모든 로직은 lecture_workspace 패키지의
lecture_store 모듈에 위임한다.

AI는 동일한 lecture_store를 IBL 액션([self:lecture]{op: "list"} 등)으로 호출 —
두 진입점이 같은 데이터 레이어를 공유.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/lectures", tags=["lectures"])


# ─────────────────────────────────────────────────────────────────────
# lecture_store 모듈 로드 (패키지 폴더에서)
# ─────────────────────────────────────────────────────────────────────

def _load_lecture_store():
    """lecture_workspace 패키지의 lecture_store 모듈을 동적 로드.

    패키지 경로가 dev/production에서 다르고 INDIEBIZ_BASE_PATH 환경변수로
    제어되므로, sys.path에 추가해서 import.
    """
    base = os.environ.get("INDIEBIZ_BASE_PATH")
    if not base:
        # dev 모드: backend/ 의 부모(indiebizOS) 기준
        base = str(Path(__file__).resolve().parent.parent)

    pkg_dir = Path(base) / "data" / "packages" / "installed" / "tools" / "lecture_workspace"
    if not pkg_dir.exists():
        raise RuntimeError(f"lecture_workspace 패키지가 없습니다: {pkg_dir}")

    if str(pkg_dir) not in sys.path:
        sys.path.insert(0, str(pkg_dir))

    # 이미 로드되어 있을 수 있음
    if "lecture_store" in sys.modules:
        return sys.modules["lecture_store"]

    spec = importlib.util.spec_from_file_location(
        "lecture_store", pkg_dir / "lecture_store.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lecture_store"] = mod
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────
# Pydantic 모델
# ─────────────────────────────────────────────────────────────────────

class LectureCreateRequest(BaseModel):
    title: str
    audience: Optional[str] = None
    thesis: Optional[str] = None
    duration_minutes: Optional[int] = None
    design_system: Optional[str] = "vintage_book"


class DeckMetaUpdateRequest(BaseModel):
    """deck.json 메타 부분 갱신. None은 변경 없음."""
    title: Optional[str] = None
    audience: Optional[str] = None
    thesis: Optional[str] = None
    duration_minutes: Optional[int] = None
    design_system: Optional[str] = None


class ReorderRequest(BaseModel):
    order: list[str]


class MaterialTextRequest(BaseModel):
    text: str
    filename: str


class MaterialFilePathRequest(BaseModel):
    file_path: str


class CumulativeMemoPatch(BaseModel):
    tone_preferred: Optional[list[str]] = None
    tone_rejected: Optional[list[str]] = None
    metaphors_adopted: Optional[list[str]] = None
    decisions: Optional[list[str]] = None


# ─────────────────────────────────────────────────────────────────────
# 강의 CRUD
# ─────────────────────────────────────────────────────────────────────

@router.get("")
async def list_lectures():
    """모든 강의 요약 목록."""
    ls = _load_lecture_store()
    return {
        "lectures": ls.list_lectures(),
        "lectures_root": str(ls.LECTURES_ROOT.resolve()),
    }


@router.post("")
async def create_lecture(req: LectureCreateRequest):
    """새 강의 생성."""
    ls = _load_lecture_store()
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="title은 필수입니다.")
    deck = ls.create_lecture(
        title=req.title.strip(),
        audience=req.audience,
        thesis=req.thesis,
        duration_minutes=req.duration_minutes,
        design_system=req.design_system or "vintage_book",
    )
    return {
        "lecture_id": deck["lecture_id"],
        "deck": deck,
        "lecture_dir": str(ls.lecture_dir(deck["lecture_id"]).resolve()),
    }


@router.get("/{lecture_id}")
async def load_lecture(lecture_id: str):
    """강의 데이터 전체 + slides_dir/materials_dir 절대경로."""
    ls = _load_lecture_store()
    try:
        return ls.load_lecture(lecture_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{lecture_id}")
async def update_deck_meta(lecture_id: str, req: DeckMetaUpdateRequest):
    """강의 메타(제목·청중·요지·분량·design_system) 부분 갱신.

    None은 변경 없음. design_system 변경 시: 기존 슬라이드 PNG는 옛 톤 그대로 — 새 슬라이드
    또는 편집(재생성)된 슬라이드만 새 톤 적용.
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    patch = req.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="갱신할 필드가 없습니다.")
    try:
        return ls.update_deck_meta(lecture_id, patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{lecture_id}")
async def delete_lecture(lecture_id: str):
    """강의 폴더 전체 삭제. 클라이언트가 사전 확인 후 호출."""
    ls = _load_lecture_store()
    try:
        return ls.delete_lecture(lecture_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─────────────────────────────────────────────────────────────────────
# 데크 조작
# ─────────────────────────────────────────────────────────────────────

@router.post("/{lecture_id}/reorder")
async def reorder_deck(lecture_id: str, req: ReorderRequest):
    """슬라이드 순서만 갱신 (파일은 안 건드림)."""
    ls = _load_lecture_store()
    try:
        return ls.reorder_deck(lecture_id, req.order)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{lecture_id}/slides/{slide_id}")
async def delete_slide(lecture_id: str, slide_id: str):
    """슬라이드 삭제."""
    ls = _load_lecture_store()
    try:
        return ls.delete_slide(lecture_id, slide_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────────────
# 슬라이드 생성/편집 (AI)
# ─────────────────────────────────────────────────────────────────────

class SlideCreateRequest(BaseModel):
    instruction: str
    insert_at: Optional[int] = None
    layout: Optional[str] = None  # 강의자가 명시적으로 선택한 layout (없으면 AI 자동)


class SlideEditRequest(BaseModel):
    instruction: str
    layout: Optional[str] = None


def _load_handler():
    """lecture_workspace 패키지의 handler 모듈 로드 (slide_create/slide_edit 위임)."""
    base = os.environ.get("INDIEBIZ_BASE_PATH")
    if not base:
        base = str(Path(__file__).resolve().parent.parent)
    pkg_dir = Path(base) / "data" / "packages" / "installed" / "tools" / "lecture_workspace"
    if str(pkg_dir) not in sys.path:
        sys.path.insert(0, str(pkg_dir))
    if "lecture_ws_handler" in sys.modules:
        return sys.modules["lecture_ws_handler"]
    spec = importlib.util.spec_from_file_location(
        "lecture_ws_handler", pkg_dir / "handler.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lecture_ws_handler"] = mod
    spec.loader.exec_module(mod)
    return mod


class _MiniCtx:
    """REST 호출에서 handler를 직접 부를 때 쓰는 ToolContext 흉내."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name


@router.post("/{lecture_id}/slides")
async def create_slide(lecture_id: str, req: SlideCreateRequest):
    """강의자의 자연어 요청 → AI가 슬라이드 한 장 생성 → 데크 등록.

    핸들러 내부에서 Playwright sync API(slide_shadcn 렌더링)를 쓰므로
    run_in_threadpool로 스레드풀에 위임 — asyncio 루프 충돌 회피.
    AI 응답 대기 시간 만큼 블로킹 (보통 5~30초).
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    if not req.instruction.strip():
        raise HTTPException(status_code=400, detail="instruction은 필수입니다.")

    handler_mod = _load_handler()
    tool_input = {
        "lecture_id": lecture_id,
        "instruction": req.instruction,
    }
    if req.insert_at is not None:
        tool_input["insert_at"] = req.insert_at
    if req.layout:
        tool_input["layout"] = req.layout

    import json as _json
    # Playwright sync API + AI 동기 호출 → 스레드풀에서 실행
    result_str = await run_in_threadpool(
        handler_mod.execute, tool_input, _MiniCtx("slide_create")
    )
    result = _json.loads(result_str)
    if not result.get("success"):
        # AI/렌더 실패 → 500
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "슬라이드 생성 실패"),
        )
    return result


# ─────────────────────────────────────────────────────────────────────
# 슬라이드 AI 캐시 상태 조회
# ─────────────────────────────────────────────────────────────────────

@router.get("/{lecture_id}/cache-status")
async def cache_status(lecture_id: str):
    """이 강의의 슬라이드 AI 캐시 상태 (UI 표시용).

    반환: {cached: bool, created_at?, materials_bytes?, model?, ttl_seconds?}
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")

    state_path = ls.lecture_dir(lecture_id) / "_slide_cache_state.json"
    if not state_path.exists():
        return {"cached": False}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return {
            "cached": True,
            "created_at": state.get("created_at"),
            "materials_bytes": state.get("materials_bytes"),
            "model": state.get("model"),
            "ttl_seconds": state.get("ttl_seconds"),
        }
    except Exception as e:
        return {"cached": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────
# 데크 내보내기 (PDF/PPTX)
# ─────────────────────────────────────────────────────────────────────

def _load_export_module():
    """lecture_workspace 패키지의 lecture_export 모듈 동적 로드."""
    base = os.environ.get("INDIEBIZ_BASE_PATH")
    if not base:
        base = str(Path(__file__).resolve().parent.parent)
    pkg_dir = Path(base) / "data" / "packages" / "installed" / "tools" / "lecture_workspace"
    if str(pkg_dir) not in sys.path:
        sys.path.insert(0, str(pkg_dir))
    if "lecture_export" in sys.modules:
        return sys.modules["lecture_export"]
    spec = importlib.util.spec_from_file_location(
        "lecture_export", pkg_dir / "lecture_export.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lecture_export"] = mod
    spec.loader.exec_module(mod)
    return mod


@router.post("/{lecture_id}/export")
async def export_deck(lecture_id: str, format: str):
    """데크를 PDF/PPTX로 내보내고 파일 메타 반환 (다운로드는 /export/file).

    PIL/python-pptx 둘 다 sync 호출이라 run_in_threadpool로 위임.
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    fmt = (format or "").lower().strip()
    if fmt not in ("pdf", "pptx", "pptx_image", "pptx_editable"):
        raise HTTPException(
            status_code=400,
            detail="format은 pdf / pptx (이미지) / pptx_editable (편집 가능) 중 하나여야 합니다.",
        )

    export_mod = _load_export_module()
    try:
        result = await run_in_threadpool(export_mod.export_deck, lecture_id, fmt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


# ─────────────────────────────────────────────────────────────────────
# 슬라이드/재료 파일 HTTP 서빙 (UI의 file:// 의존 제거)
# ─────────────────────────────────────────────────────────────────────

@router.get("/{lecture_id}/slides/{slide_id}/png")
async def slide_png(lecture_id: str, slide_id: str):
    """슬라이드 PNG를 HTTP로 서빙. UI는 <img src> 또는 fetch로 접근."""
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    safe_id = Path(slide_id).name
    png_path = ls.slides_dir(lecture_id) / f"{safe_id}.png"
    if not png_path.exists():
        raise HTTPException(status_code=404, detail=f"슬라이드 PNG 없음: {safe_id}")
    return FileResponse(str(png_path), media_type="image/png")


@router.get("/{lecture_id}/slides/{slide_id}/spec")
async def slide_spec(lecture_id: str, slide_id: str):
    """슬라이드 JSON spec 서빙 (재생성/편집 시 참고용)."""
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    safe_id = Path(slide_id).name
    spec_path = ls.slides_dir(lecture_id) / f"{safe_id}.json"
    if not spec_path.exists():
        raise HTTPException(status_code=404, detail=f"슬라이드 spec 없음: {safe_id}")
    return FileResponse(str(spec_path), media_type="application/json")


@router.get("/{lecture_id}/materials/{filename}/file")
async def material_file(lecture_id: str, filename: str):
    """재료 파일 다운로드 (UI 미리보기·다운로드용)."""
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    safe_name = Path(filename).name
    file_path = ls.materials_dir(lecture_id) / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"재료 파일 없음: {safe_name}")
    # MIME 자동 추측
    import mimetypes
    media_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(str(file_path), media_type=media_type or "application/octet-stream")


@router.get("/{lecture_id}/export/file")
async def download_export_file(lecture_id: str, filename: str):
    """exports/ 안의 파일을 다운로드. filename은 export_deck이 반환한 값."""
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    # 경로 트래버설 차단
    safe_name = Path(filename).name
    file_path = ls.lecture_dir(lecture_id) / "exports" / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"파일 없음: {safe_name}")
    media_type = (
        "application/pdf" if safe_name.lower().endswith(".pdf")
        else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if safe_name.lower().endswith(".pptx")
        else "application/octet-stream"
    )
    return FileResponse(str(file_path), media_type=media_type, filename=safe_name)


class SlidePatchRequest(BaseModel):
    patch: dict  # spec에 병합할 키-값. None 값은 필드 삭제.


@router.post("/{lecture_id}/slides/{slide_id}/patch")
async def patch_slide_spec(lecture_id: str, slide_id: str, req: SlidePatchRequest):
    """슬라이드 spec 필드 직접 patch + 재렌더. PowerPoint식 편집. AI 호출 없음.

    patch dict의 키-값을 spec에 shallow update. layout 변경은 거부 (필요 필드 달라져 깨짐).
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    if not isinstance(req.patch, dict) or not req.patch:
        raise HTTPException(status_code=400, detail="patch는 비어있지 않은 객체여야 합니다.")

    handler_mod = _load_handler()
    import json as _json
    result_str = await run_in_threadpool(
        handler_mod.execute,
        {"lecture_id": lecture_id, "slide_id": slide_id, "patch": req.patch},
        _MiniCtx("slide_patch_spec"),
    )
    result = _json.loads(result_str)
    if not result.get("success"):
        # patch 실패 — 400 또는 500 분기
        err_type = result.get("error_type", "")
        status = 400 if err_type in ("not_found", "validation") else 500
        raise HTTPException(status_code=status, detail=result.get("error", "patch 실패"))
    return result


@router.post("/{lecture_id}/slides/{slide_id}/rerender")
async def rerender_slide(lecture_id: str, slide_id: str):
    """슬라이드 spec 변경 없이 PNG만 재렌더. design_system 변경 후 사용.

    AI 호출 없음 → 빠르고 spec이 흔들리지 않음.
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")

    handler_mod = _load_handler()
    import json as _json
    result_str = await run_in_threadpool(
        handler_mod.execute,
        {"lecture_id": lecture_id, "slide_id": slide_id},
        _MiniCtx("slide_rerender"),
    )
    result = _json.loads(result_str)
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "슬라이드 재렌더 실패"),
        )
    return result


@router.post("/{lecture_id}/slides/{slide_id}/edit")
async def edit_slide(lecture_id: str, slide_id: str, req: SlideEditRequest):
    """특정 슬라이드 편집(재생성). 슬라이드 생성과 마찬가지로 스레드풀에서 실행."""
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    if not req.instruction.strip():
        raise HTTPException(status_code=400, detail="instruction은 필수입니다.")

    handler_mod = _load_handler()
    import json as _json
    edit_input = {"lecture_id": lecture_id, "slide_id": slide_id, "instruction": req.instruction}
    if req.layout:
        edit_input["layout"] = req.layout
    result_str = await run_in_threadpool(
        handler_mod.execute,
        edit_input,
        _MiniCtx("slide_edit"),
    )
    result = _json.loads(result_str)
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "슬라이드 편집 실패"),
        )
    return result


# ─────────────────────────────────────────────────────────────────────
# 재료 관리
# ─────────────────────────────────────────────────────────────────────

@router.post("/{lecture_id}/materials/text")
async def add_material_text(lecture_id: str, req: MaterialTextRequest):
    """텍스트 직접 입력으로 재료 추가."""
    ls = _load_lecture_store()
    try:
        return ls.add_material_from_text(lecture_id, req.text, req.filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{lecture_id}/materials/path")
async def add_material_path(lecture_id: str, req: MaterialFilePathRequest):
    """로컬 파일 경로로 재료 추가 (파일을 materials/로 복사)."""
    ls = _load_lecture_store()
    try:
        return ls.add_material_from_file(lecture_id, req.file_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{lecture_id}/materials/upload")
async def upload_material(lecture_id: str, file: UploadFile = File(...)):
    """multipart 업로드로 재료 추가 (브라우저 드래그앤드롭/파일선택용)."""
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")

    # /tmp/에 임시 저장 후 add_material_from_file로 전달
    import tempfile
    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # add_material_from_file은 원본명을 유지하므로, 임시명 대신 원본명 보존하도록
        # 직접 materials/로 복사
        import shutil
        md = ls.materials_dir(lecture_id)
        md.mkdir(parents=True, exist_ok=True)
        original_name = file.filename or "upload"
        # 경로 트래버설 차단
        safe_name = Path(original_name).name
        dest = md / safe_name
        if dest.exists():
            stem = dest.stem
            suffix2 = dest.suffix
            n = 2
            while True:
                cand = md / f"{stem}-{n}{suffix2}"
                if not cand.exists():
                    dest = cand
                    break
                n += 1
        shutil.copy2(tmp_path, dest)

        deck = ls.read_deck(lecture_id)
        rel = f"materials/{dest.name}"
        from datetime import datetime
        entry = {
            "file": rel,
            "type": ls._detect_material_type(dest.name),
            "added_at": datetime.now().isoformat(timespec="seconds"),
            "source": "upload",
        }
        deck.setdefault("materials", []).append(entry)
        ls.write_deck(lecture_id, deck)

        # 캐시 무효화 — 새 재료가 들어왔으니 다음 슬라이드 생성 시 재생성
        try:
            import sys as _sys
            pkg_dir = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools" / "lecture_workspace"
            if str(pkg_dir) not in _sys.path:
                _sys.path.insert(0, str(pkg_dir))
            import slide_ai  # type: ignore
            slide_ai.invalidate_lecture_cache(lecture_id)
        except Exception as e:
            print(f"[upload] 캐시 무효화 실패 (무시): {e}")

        return entry
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.delete("/{lecture_id}/materials/{filename}")
async def remove_material(lecture_id: str, filename: str):
    """재료 삭제."""
    ls = _load_lecture_store()
    try:
        return ls.remove_material(lecture_id, filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─────────────────────────────────────────────────────────────────────
# 누적 메모 (Step 3에서 AI가 사용, UI는 보기/편집)
# ─────────────────────────────────────────────────────────────────────

@router.patch("/{lecture_id}/memo")
async def patch_memo(lecture_id: str, patch: CumulativeMemoPatch):
    """누적 메모 부분 갱신."""
    ls = _load_lecture_store()
    patch_dict = {k: v for k, v in patch.model_dump().items() if v is not None}
    try:
        return ls.update_cumulative_memo(lecture_id, patch_dict)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─────────────────────────────────────────────────────────────────────
# 워크스페이스 창 열기 (Launcher WS로 Electron에 신호)
# ─────────────────────────────────────────────────────────────────────

class OpenWorkspaceRequest(BaseModel):
    lecture_id: Optional[str] = None


@router.post("/open-workspace")
async def open_workspace(req: OpenWorkspaceRequest):
    """강의 만들기 창 열기 신호를 Launcher WS로 Electron에 전송."""
    try:
        from api_websocket import send_launcher_command, get_launcher_ws
    except ImportError:
        raise HTTPException(status_code=500, detail="WebSocket 모듈 로드 실패")

    if not get_launcher_ws():
        raise HTTPException(
            status_code=503,
            detail="Launcher WS 미연결. Electron 메인 창이 실행 중인지 확인하세요.",
        )

    sent = await send_launcher_command(
        "open_lecture_workspace",
        {"lecture_id": req.lecture_id} if req.lecture_id else {},
    )
    if not sent:
        raise HTTPException(status_code=500, detail="Launcher 명령 전달 실패")
    return {"success": True, "lecture_id": req.lecture_id}
