"""api_guides.py — 가이드 파일 표면 라우터 (2026-09-13)

런처 안경 메뉴 '가이드 파일' 이 부른다. 목록·신선도·등록 여부는 datastore/guide_registry 가
소유하고, 여기는 HTTP 껍데기만. 로컬 전용 — is_public_remote_path 등록 금지(절차 기억 본문·편집).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import guide_registry as GR

router = APIRouter(prefix="/guides", tags=["guides"])


class GuideBody(BaseModel):
    content: str


@router.get("")
def guides_list():
    """전 가이드 목록(파일 × 등록 × 신선도 × 표식) + 예산."""
    return GR.guide_catalog()


@router.get("/{name}")
def guide_read(name: str):
    p = GR.resolve_guide(name)
    if p is None:
        raise HTTPException(status_code=400, detail="잘못된 가이드 이름")
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"가이드 없음: {p.name}")
    return {"file": p.name, "content": p.read_text(encoding="utf-8"), "bytes": p.stat().st_size,
            "budget_bytes": GR.guide_budget_bytes()}


@router.put("/{name}")
def guide_write(name: str, body: GuideBody):
    """본문 저장 — 기존 파일만(새 가이드 등록은 guide_registration.md 절차: guide_db 등록이 함께 필요).
    예산 초과는 막지 않고 알린다(정책=압축·분할, 삭제 금지 — check_file_size 가 커밋에서 집행)."""
    p = GR.resolve_guide(name)
    if p is None:
        raise HTTPException(status_code=400, detail="잘못된 가이드 이름")
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"가이드 없음: {p.name} (새 가이드는 등록 절차로)")
    text = body.content if body.content.endswith("\n") else body.content + "\n"
    p.write_text(text, encoding="utf-8")
    size = p.stat().st_size
    budget = GR.guide_budget_bytes()
    return {"ok": True, "file": p.name, "bytes": size, "budget_bytes": budget, "over_budget": size > budget}
