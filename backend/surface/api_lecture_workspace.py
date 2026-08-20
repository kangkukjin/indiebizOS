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
        base = str(Path(__file__).resolve().parent.parent.parent)

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
    design_system: Optional[str] = "native_vintage_book"


class DeckMetaUpdateRequest(BaseModel):
    """deck.json 메타 부분 갱신. None은 변경 없음."""
    title: Optional[str] = None
    audience: Optional[str] = None
    thesis: Optional[str] = None
    duration_minutes: Optional[int] = None
    design_system: Optional[str] = None
    lecture_memo: Optional[str] = None  # 사용자 메모(왼쪽 항상 표시) — AI 미사용


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
# 선택지 매트릭스 (톤 × 렌더 방식)
# ★`/{lecture_id}` 보다 **먼저** 선언해야 한다 — FastAPI 는 선언 순서로 매칭하므로
#   뒤에 두면 "design-systems"가 lecture_id 로 먹힌다.
# ─────────────────────────────────────────────────────────────────────

@router.get("/design-systems")
async def design_systems():
    """강의 창 드롭다운 2축의 선택지 — 톤 목록 + 렌더 방식 + 톤별 지원 매트릭스.

    프론트엔드에 톤 목록을 하드코딩하지 않기 위한 엔드포인트다(그 드리프트 때문에
    은퇴한 톤이 드롭다운에 계속 남아 고르면 생성이 실패했다 — 2026-08-06 개편).
    진실 소스 = media_producer/slide_tones.py.
    """
    ls = _load_lecture_store()
    return ls._load_tone_registry().matrix()


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
        design_system=req.design_system or "native_vintage_book",
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


@router.post("/{lecture_id}/slides/{slide_id}/duplicate")
async def duplicate_slide(lecture_id: str, slide_id: str):
    """슬라이드 복제 — 같은 내용으로 한 장 더 (원본 바로 뒤). AI/렌더 호출 없음(파일 복사)."""
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    try:
        return ls.duplicate_slide(lecture_id, slide_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─────────────────────────────────────────────────────────────────────
# 슬라이드 생성/편집 (AI)
# ─────────────────────────────────────────────────────────────────────

class SlideCreateRequest(BaseModel):
    instruction: str
    insert_at: Optional[int] = None
    # 렌더 방식 — 이 한 장만 덱 기본과 다르게 (native|image|html). 강의 창의 '렌더 방식' 셀렉터.
    render: Optional[str] = None
    # layout = HTML 구조 강제(프로그래매틱·IBL 용). UI 에는 노출하지 않는다 — 구조는 AI 몫.
    layout: Optional[str] = None
    image_quality: Optional[str] = None  # 이미지 품질: 'pro'(고품질·비쌈) / 'fast'(저가·빠름)
    image_base64: Optional[str] = None  # 채팅 첨부 이미지 — 이 파일이 '들어간' 슬라이드를 조판 (2026-08-05)
    image_name: Optional[str] = None


class SlideEditRequest(BaseModel):
    instruction: str
    render: Optional[str] = None
    layout: Optional[str] = None
    image_quality: Optional[str] = None
    image_base64: Optional[str] = None
    image_name: Optional[str] = None


def _save_chat_image(ls, lecture_id: str, image_base64: str, image_name: Optional[str]) -> str:
    """채팅 첨부 이미지를 강의 materials/ 에 저장하고 절대경로 반환.

    이름은 시각+원본명으로 유일화(덮어쓰기 방지), 확장자 화이트리스트 밖은 png 로 강제.
    렌더러(shadcn_slides)가 image_path 를 base64 임베드하므로 파일은 강의 폴더에 영속 —
    재렌더·내보내기 때도 살아 있어야 한다."""
    import base64 as _b64
    import re as _re
    from datetime import datetime as _dt
    raw = image_base64.split(",", 1)[-1]  # data URL 프리픽스 허용
    data = _b64.b64decode(raw)
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="첨부 이미지가 너무 큽니다 (15MB 초과)")
    # 매직바이트 검사 — 이미지만 (family-news 업로드 선례)
    if not (data[:8].startswith(b"\x89PNG") or data[:3] == b"\xff\xd8\xff"
            or data[:6] in (b"GIF87a", b"GIF89a") or data[8:12] == b"WEBP"):
        raise HTTPException(status_code=400, detail="이미지 파일이 아닙니다 (png/jpg/gif/webp)")
    stem = _re.sub(r"[^\w가-힣.-]", "_", (image_name or "chat_image"))[:60]
    ext = Path(stem).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        stem, ext = stem + ".png", ".png"
    mdir = ls.materials_dir(lecture_id)
    mdir.mkdir(parents=True, exist_ok=True)
    path = mdir / f"{_dt.now().strftime('%H%M%S')}_{stem}"
    path.write_bytes(data)
    return str(path.resolve())


def _load_handler():
    """lecture_workspace 패키지의 handler 모듈 로드 (slide_create/slide_edit 위임)."""
    base = os.environ.get("INDIEBIZ_BASE_PATH")
    if not base:
        base = str(Path(__file__).resolve().parent.parent.parent)
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
        "op": "create",
        "lecture_id": lecture_id,
        "instruction": req.instruction,
    }
    if req.insert_at is not None:
        tool_input["insert_at"] = req.insert_at
    if req.render:
        tool_input["render"] = req.render
    if req.layout:
        tool_input["layout"] = req.layout
    if req.image_quality:
        tool_input["image_quality"] = req.image_quality
    if req.image_base64:
        tool_input["user_image_path"] = _save_chat_image(ls, lecture_id, req.image_base64, req.image_name)

    import json as _json
    # Playwright sync API + AI 동기 호출 → 스레드풀에서 실행
    result_str = await run_in_threadpool(
        handler_mod.execute, tool_input, _MiniCtx("slide_op")
    )
    result = _json.loads(result_str)
    if not result.get("success"):
        # 잘못된 요청(미지원 톤×렌더 조합 등)은 400, AI/렌더 실패는 500 — edit 엔드포인트와 동형.
        err_type = result.get("error_type", "")
        status = 400 if err_type in ("validation", "not_found") else 500
        raise HTTPException(status_code=status, detail=result.get("error", "슬라이드 생성 실패"))
    return result


def _load_slide_ai():
    """lecture_workspace 패키지의 slide_ai 모듈 동적 로드 (outline 위임)."""
    base = os.environ.get("INDIEBIZ_BASE_PATH")
    if not base:
        base = str(Path(__file__).resolve().parent.parent.parent)
    pkg_dir = Path(base) / "data" / "packages" / "installed" / "tools" / "lecture_workspace"
    if str(pkg_dir) not in sys.path:
        sys.path.insert(0, str(pkg_dir))
    if "slide_ai" in sys.modules:
        return sys.modules["slide_ai"]
    spec = importlib.util.spec_from_file_location("slide_ai", pkg_dir / "slide_ai.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["slide_ai"] = mod
    spec.loader.exec_module(mod)
    return mod


class OutlineRequest(BaseModel):
    count: Optional[int] = None  # 원하는 슬라이드 장수 (없으면 AI 자동)


@router.post("/{lecture_id}/outline")
async def outline_lecture(lecture_id: str, req: OutlineRequest):
    """강의 자료를 읽어 슬라이드 초안(instruction) 목록을 반환.

    일괄 생성의 1단계 — UI가 이 목록을 받아 한 장씩 /slides 로 순차 생성한다.
    AI 한 번 호출이라 비교적 빠르지만 동기 호출 → 스레드풀에 위임.
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")

    deck = ls.read_deck(lecture_id)
    lecture_dir_path = ls.lecture_dir(lecture_id)
    existing_count = len(deck.get("slide_order", []))  # >0이면 '이어붙이는' 일괄생성
    slide_ai = _load_slide_ai()
    try:
        slides = await run_in_threadpool(
            slide_ai.outline_from_materials, deck, lecture_dir_path, req.count, existing_count
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"초안 생성 실패: {e}")
    return {"success": True, "slides": slides, "count": len(slides)}


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
        base = str(Path(__file__).resolve().parent.parent.parent)
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
    if fmt not in ("pdf", "pptx", "pptx_image", "pptx_editable", "images"):
        raise HTTPException(
            status_code=400,
            detail="format은 pdf / pptx (이미지) / pptx_editable (편집 가능) / images (이미지 폴더 ZIP) 중 하나여야 합니다.",
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
async def slide_png(lecture_id: str, slide_id: str, base: bool = False):
    """슬라이드 PNG를 HTTP로 서빙. UI는 <img src> 또는 fetch로 접근.

    base=true 면 '글자 얹기' 이전의 원본({slide_id}.base.png)을 우선 서빙 —
    배치 편집기가 글자 없는 배경 위에 라이브 글자 박스를 그릴 때 쓴다.
    (원본 백업이 없으면 = 얹은 글자가 없는 슬라이드이므로 현재 PNG 그대로.)
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    safe_id = Path(slide_id).name
    png_path = ls.slides_dir(lecture_id) / f"{safe_id}.png"
    if base:
        base_path = ls.slides_dir(lecture_id) / f"{safe_id}.base.png"
        if base_path.exists():
            png_path = base_path
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
        {"op": "patch", "lecture_id": lecture_id, "slide_id": slide_id, "patch": req.patch},
        _MiniCtx("slide_op"),
    )
    result = _json.loads(result_str)
    if not result.get("success"):
        # patch 실패 — 400 또는 500 분기
        err_type = result.get("error_type", "")
        status = 400 if err_type in ("not_found", "validation") else 500
        raise HTTPException(status_code=status, detail=result.get("error", "patch 실패"))
    return result


class SlideNoteRequest(BaseModel):
    note: str = ""  # 강의 노트(말할 내용). 빈 문자열이면 노트 제거.


@router.patch("/{lecture_id}/slides/{slide_id}/note")
async def set_slide_note(lecture_id: str, slide_id: str, req: SlideNoteRequest):
    """슬라이드의 강의 노트(말할 내용) 저장. AI/렌더 호출 없음 — deck 메타만 갱신."""
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    try:
        return ls.set_speaker_note(lecture_id, slide_id, req.note)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
        {"op": "rerender", "lecture_id": lecture_id, "slide_id": slide_id},
        _MiniCtx("slide_op"),
    )
    result = _json.loads(result_str)
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "슬라이드 재렌더 실패"),
        )
    return result


class SlideImageEditRequest(BaseModel):
    instruction: str
    image_quality: Optional[str] = None  # 'pro' / 'fast'


@router.post("/{lecture_id}/slides/{slide_id}/image-edit")
async def image_edit_slide(lecture_id: str, slide_id: str, req: SlideImageEditRequest):
    """통짜 이미지/이미지 슬라이드 '부분 수정' — 다시 그리지 않고 현재 이미지를 편집.

    제목 한 줄 등 일부만 바꿀 때 사용. 이미지 모델 호출이라 스레드풀에서 실행.
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    if not req.instruction.strip():
        raise HTTPException(status_code=400, detail="instruction은 필수입니다.")

    handler_mod = _load_handler()
    import json as _json
    edit_input = {"op": "image_edit", "lecture_id": lecture_id, "slide_id": slide_id, "instruction": req.instruction}
    if req.image_quality:
        edit_input["image_quality"] = req.image_quality
    result_str = await run_in_threadpool(
        handler_mod.execute, edit_input, _MiniCtx("slide_op"),
    )
    result = _json.loads(result_str)
    if not result.get("success"):
        err_type = result.get("error_type", "")
        status = 400 if err_type in ("validation", "not_found") else 500
        raise HTTPException(status_code=status, detail=result.get("error", "이미지 편집 실패"))
    return result


class SlideTextOverlayRequest(BaseModel):
    text: Optional[str] = None      # 얹을 문구 (없이 clear만 주면 원본 복원)
    position: Optional[str] = None  # 9방 (top-left … bottom-right, 기본 bottom-right)
    x: Optional[float] = None       # 자유 좌표 — 박스 좌상단, 슬라이드 폭의 % (position 보다 우선)
    y: Optional[float] = None       # 자유 좌표 — 슬라이드 높이의 %
    size: Optional[str] = None      # small(기본)/medium/large
    size_vw: Optional[float] = None  # 자유 크기 — 슬라이드 폭의 % (size 보다 우선)
    font: Optional[str] = None      # sans(기본)/serif
    color: Optional[str] = None     # white(기본)/black/#hex
    chip: bool = False              # 반투명 배경칩
    clear: bool = False             # 얹은 글자 전부 제거·원본 복원
    # 전체 교체 (드래그 배치 편집기의 저장) — 있으면 위 단건 필드 대신 이 목록이 통째로 적용
    overlays: Optional[list] = None


@router.post("/{lecture_id}/slides/{slide_id}/text-overlay")
async def text_overlay_slide(lecture_id: str, slide_id: str, req: SlideTextOverlayRequest):
    """결정론 '글자 얹기' — 이미지 모델 없이 현재 슬라이드 PNG 위에 문구만 합성.

    그림 픽셀 보존(원본은 base.png 로 자동 보존, clear 로 복원). AI 호출 0.
    overlays(배열)를 주면 전체 교체 — 배치 편집기의 저장 경로.
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    if req.overlays is None and not (req.text or "").strip() and not req.clear:
        raise HTTPException(status_code=400, detail="text, overlays 또는 clear=true 가 필요합니다.")

    handler_mod = _load_handler()
    import json as _json
    edit_input = {"op": "image_edit", "lecture_id": lecture_id, "slide_id": slide_id}
    if req.overlays is not None:
        edit_input["overlay_set"] = req.overlays
    else:
        if (req.text or "").strip():
            edit_input["overlay_text"] = req.text.strip()
        if req.position:
            edit_input["overlay_position"] = req.position
        if req.x is not None:
            edit_input["overlay_x"] = req.x
        if req.y is not None:
            edit_input["overlay_y"] = req.y
        if req.size:
            edit_input["overlay_size"] = req.size
        if req.size_vw is not None:
            edit_input["overlay_size_vw"] = req.size_vw
        if req.font:
            edit_input["overlay_font"] = req.font
        if req.color:
            edit_input["overlay_color"] = req.color
        if req.chip:
            edit_input["overlay_chip"] = True
        if req.clear:
            edit_input["overlay_clear"] = True
    result_str = await run_in_threadpool(
        handler_mod.execute, edit_input, _MiniCtx("slide_op"),
    )
    result = _json.loads(result_str)
    if not result.get("success"):
        err_type = result.get("error_type", "")
        status = 400 if err_type in ("validation", "not_found") else 500
        raise HTTPException(status_code=status, detail=result.get("error", "글자 얹기 실패"))
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
    edit_input = {"op": "edit", "lecture_id": lecture_id, "slide_id": slide_id, "instruction": req.instruction}
    if req.render:
        edit_input["render"] = req.render
    if req.layout:
        edit_input["layout"] = req.layout
    if req.image_quality:
        edit_input["image_quality"] = req.image_quality
    if req.image_base64:
        edit_input["user_image_path"] = _save_chat_image(ls, lecture_id, req.image_base64, req.image_name)
    result_str = await run_in_threadpool(
        handler_mod.execute,
        edit_input,
        _MiniCtx("slide_op"),
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
            pkg_dir = Path(__file__).resolve().parent.parent.parent / "data" / "packages" / "installed" / "tools" / "lecture_workspace"
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
# 실강 녹음 (강의 창의 '나레이션 녹음 모드')
# ─────────────────────────────────────────────────────────────────────
# 강의 창에서 실제 강의를 녹음하면 오디오 한 덩어리 + 슬라이드 전환 타임라인이
# 여기로 올라온다. 렌더([self:deck]{op:"video"})는 이 폴더가 있으면 TTS 대신
# 이 녹음을 구간으로 잘라 쓰고, 씬 길이도 전환 간격이 정한다
# (deck_video.live_recording / slice_recording).
#
# ★한 강의에 녹음은 하나다 — 다시 녹음하면 폴더째 갈아엎는다. 부분 갱신을 하면
#   지난 녹음의 구간 wav(seg_*.wav)가 남아 다음 렌더가 옛것과 새것을 섞어 쓴다.

LIVE_DIR_NAME = "narration_live"
_AUDIO_SUFFIX = {
    "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
}


def _live_dir(ls, lecture_id: str) -> Path:
    return ls.lecture_dir(lecture_id) / LIVE_DIR_NAME


def _live_status(ls, lecture_id: str) -> dict:
    d = _live_dir(ls, lecture_id)
    tj = d / "timeline.json"
    if not tj.exists():
        return {"exists": False}
    try:
        tl = json.loads(tj.read_text(encoding="utf-8"))
    except Exception as e:
        return {"exists": False, "error": f"타임라인 읽기 실패: {e}"}
    audio = d / (tl.get("audio_file") or "")
    ok = bool(tl.get("audio_file")) and audio.exists()
    return {
        "exists": ok,
        "audio_path": str(audio) if ok else None,
        "bytes": audio.stat().st_size if ok else 0,
        "duration_sec": tl.get("duration_sec"),
        "created_at": tl.get("created_at"),
        "marks": tl.get("marks") or [],
    }


@router.get("/{lecture_id}/narration-recording")
async def get_narration_recording(lecture_id: str):
    """저장된 실강 녹음이 있는지 — 렌더 버튼이 어느 경로로 갈지의 근거."""
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    return _live_status(ls, lecture_id)


@router.get("/{lecture_id}/narration-recording/audio")
async def narration_recording_audio(lecture_id: str):
    """녹음 오디오 서빙 — 강의 창의 '강의 플레이'가 <audio> 로 문다.

    ★파일명을 클라이언트가 넘기지 않는다: 확장자는 브라우저가 준 mime 마다 다르고
      (webm/ogg/m4a…), 경로를 받으면 트래버설 방어를 여기서 또 짜야 한다.
      timeline.json 의 audio_file 이 정본이므로 서버가 그걸 보고 고른다.

    Range 는 starlette FileResponse 가 처리한다(206) — <audio> 의 탐색이 그걸 쓴다.
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    st = _live_status(ls, lecture_id)
    if not st.get("exists") or not st.get("audio_path"):
        raise HTTPException(status_code=404, detail="저장된 녹음이 없습니다.")
    path = Path(st["audio_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="녹음 오디오 파일이 없습니다.")
    media = {
        ".webm": "audio/webm", ".ogg": "audio/ogg", ".m4a": "audio/mp4",
        ".mp3": "audio/mpeg", ".wav": "audio/wav",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(str(path), media_type=media)


@router.post("/{lecture_id}/narration-recording")
async def save_narration_recording(
    lecture_id: str,
    audio: UploadFile = File(...),
    timeline: str = Form(...),
):
    """녹음 오디오 + 전환 타임라인 저장. 기존 녹음은 통째로 대체된다."""
    from datetime import datetime
    import shutil

    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    try:
        tl = json.loads(timeline)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"timeline JSON 파싱 실패: {e}")
    marks = [m for m in (tl.get("marks") or []) if m.get("slide_id")]
    if not marks:
        raise HTTPException(status_code=400, detail="전환 기록(marks)이 비었습니다.")
    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="빈 오디오입니다.")

    d = _live_dir(ls, lecture_id)
    if d.exists():
        await run_in_threadpool(shutil.rmtree, d)
    d.mkdir(parents=True, exist_ok=True)

    mime = (audio.content_type or "").split(";")[0].strip()
    suffix = _AUDIO_SUFFIX.get(mime) or Path(audio.filename or "").suffix or ".webm"
    name = f"recording{suffix}"
    await run_in_threadpool((d / name).write_bytes, content)

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mime": mime or "audio/webm",
        "audio_file": name,
        "duration_sec": round(float(tl.get("duration_sec") or 0), 3),
        # t = 그 슬라이드가 화면에 뜬 시각(녹음 시작 기준 초).
        "marks": [{"slide_id": str(m["slide_id"]), "t": round(float(m.get("t") or 0), 3)}
                  for m in marks],
    }
    await run_in_threadpool(
        (d / "timeline.json").write_text,
        json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    return {"success": True, **_live_status(ls, lecture_id)}


@router.delete("/{lecture_id}/narration-recording")
async def delete_narration_recording(lecture_id: str):
    """녹음 폐기 — 다음 렌더는 다시 스피커 노트 TTS 경로로 간다."""
    import shutil
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    d = _live_dir(ls, lecture_id)
    if d.exists():
        await run_in_threadpool(shutil.rmtree, d)
    return {"success": True, "exists": False}


@router.post("/{lecture_id}/slides/upload-images")
async def upload_slide_images(
    lecture_id: str,
    files: list[UploadFile] = File(...),
    insert_at: Optional[int] = Form(None),
):
    """이미지 파일 여러 장을 슬라이드로 한 번에 추가.

    AI 생성/렌더 없이 **업로드 이미지 자체가 슬라이드 PNG**가 된다(layout="image").
    이미 만들어둔 슬라이드 이미지를 한꺼번에 올릴 때 사용. 파일 순서대로 데크에 삽입.
    """
    ls = _load_lecture_store()
    if not ls.lecture_exists(lecture_id):
        raise HTTPException(status_code=404, detail=f"강의 없음: {lecture_id}")
    if not files:
        raise HTTPException(status_code=400, detail="이미지 파일이 없습니다.")

    # UploadFile.read()는 async → 먼저 다 읽고, PIL 변환/저장은 스레드풀에서.
    items = [(f.filename or "image", await f.read()) for f in files]

    def _process():
        from PIL import Image
        import io as _io
        import json as _json
        sdir = ls.slides_dir(lecture_id)
        sdir.mkdir(parents=True, exist_ok=True)
        created, skipped = [], []
        for idx, (fname, content) in enumerate(items):
            try:
                img = Image.open(_io.BytesIO(content)).convert("RGB")
            except Exception:
                skipped.append(fname)
                continue
            deck = ls.read_deck(lecture_id)           # 매번 최신 deck → next_slide_id 정확
            sid = ls.next_slide_id(deck)
            img.save(str(sdir / f"{sid}.png"), format="PNG")
            title = (Path(fname).stem or sid)[:60]
            spec = {
                "layout": "image",
                "title": title,
                "image_slide": True,          # AI 재렌더/패치 대상 아님 (UI가 분기)
                "source_image": Path(fname).name,
            }
            (sdir / f"{sid}.json").write_text(
                _json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            at = None if insert_at is None else insert_at + len(created)
            meta = ls.register_slide(
                lecture_id, sid, title, "image",
                f"slides/{sid}.json", f"slides/{sid}.png", insert_at=at,
            )
            created.append(meta)
        return created, skipped

    created, skipped = await run_in_threadpool(_process)
    if not created:
        raise HTTPException(status_code=400, detail="유효한 이미지가 없습니다.")
    return {"success": True, "created": created, "count": len(created), "skipped": skipped}


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
        from websocket_manager import send_launcher_command, get_launcher_ws
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
