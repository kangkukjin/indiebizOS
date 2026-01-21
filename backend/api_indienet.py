"""
api_indienet.py - IndieNet 관련 API
"""

from typing import Optional

from fastapi import APIRouter, HTTPException

from api_models import (
    IndieNetPostRequest, IndieNetDMRequest, IndieNetSettingsUpdate,
    IndieNetDisplayNameUpdate, IndieNetImportNsec,
    IndieNetBoardCreate, IndieNetBoardPostRequest
)
from indienet import get_indienet

router = APIRouter()


# ============ IndieNet API ============

@router.get("/indienet/status")
async def get_indienet_status():
    """IndieNet 상태 조회"""
    try:
        indienet = get_indienet()
        return indienet.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indienet/identity")
async def get_indienet_identity():
    """IndieNet ID 조회"""
    try:
        indienet = get_indienet()
        if not indienet.is_initialized():
            raise HTTPException(status_code=400, detail="IndieNet이 초기화되지 않음")
        return indienet.identity.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/indienet/identity/display-name")
async def update_indienet_display_name(data: IndieNetDisplayNameUpdate):
    """IndieNet 표시 이름 변경"""
    try:
        indienet = get_indienet()
        if not indienet.is_initialized():
            raise HTTPException(status_code=400, detail="IndieNet이 초기화되지 않음")

        success = indienet.identity.set_display_name(data.display_name)
        if success:
            return {"status": "updated", "display_name": data.display_name}
        else:
            raise HTTPException(status_code=500, detail="이름 변경 실패")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/indienet/identity/import")
async def import_indienet_nsec(data: IndieNetImportNsec):
    """외부 nsec 키로 ID 가져오기"""
    try:
        indienet = get_indienet()

        success = indienet.identity.import_nsec(data.nsec)
        if success:
            return {
                "status": "imported",
                "identity": indienet.identity.to_dict()
            }
        else:
            raise HTTPException(status_code=400, detail="ID 가져오기 실패")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/indienet/identity/reset")
async def reset_indienet_identity():
    """ID 초기화 (새로 생성)"""
    try:
        indienet = get_indienet()

        success = indienet.identity.reset_identity()
        if success:
            return {
                "status": "reset",
                "identity": indienet.identity.to_dict()
            }
        else:
            raise HTTPException(status_code=500, detail="ID 초기화 실패")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indienet/settings")
async def get_indienet_settings():
    """IndieNet 설정 조회"""
    try:
        indienet = get_indienet()
        return indienet.settings.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/indienet/settings")
async def update_indienet_settings(data: IndieNetSettingsUpdate):
    """IndieNet 설정 변경"""
    try:
        indienet = get_indienet()

        if data.relays is not None:
            indienet.settings.relays = data.relays
        if data.auto_refresh is not None:
            indienet.settings.auto_refresh = data.auto_refresh
        if data.refresh_interval is not None:
            indienet.settings.refresh_interval = data.refresh_interval

        success = indienet.settings.save()
        if success:
            return {"status": "saved", "settings": indienet.settings.to_dict()}
        else:
            raise HTTPException(status_code=500, detail="설정 저장 실패")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indienet/posts")
async def get_indienet_posts(limit: int = 50, since: Optional[int] = None):
    """IndieNet 게시글 조회"""
    try:
        indienet = get_indienet()
        if not indienet.is_initialized():
            raise HTTPException(status_code=400, detail="IndieNet이 초기화되지 않음")

        posts = indienet.fetch_posts(limit=limit, since=since)
        return {"posts": posts, "count": len(posts)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/indienet/posts")
async def create_indienet_post(data: IndieNetPostRequest):
    """IndieNet에 글 게시"""
    try:
        indienet = get_indienet()
        if not indienet.is_initialized():
            raise HTTPException(status_code=400, detail="IndieNet이 초기화되지 않음")

        event_id = indienet.post(content=data.content, extra_tags=data.extra_tags)

        if event_id:
            import time
            return {
                "status": "posted",
                "event_id": event_id,
                "pubkey": indienet.identity.public_key.hex(),
                "created_at": int(time.time())
            }
        else:
            raise HTTPException(status_code=500, detail="게시 실패")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indienet/user/{pubkey}")
async def get_indienet_user(pubkey: str):
    """IndieNet 사용자 정보 조회"""
    try:
        indienet = get_indienet()
        if not indienet.is_initialized():
            raise HTTPException(status_code=400, detail="IndieNet이 초기화되지 않음")

        user_info = indienet.get_user_info(pubkey)
        if user_info:
            return user_info
        else:
            return {"pubkey": pubkey, "name": "", "display_name": "", "about": "", "picture": ""}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indienet/dms")
async def get_indienet_dms(limit: int = 50, since: Optional[int] = None):
    """IndieNet DM 목록 조회"""
    try:
        indienet = get_indienet()
        if not indienet.is_initialized():
            raise HTTPException(status_code=400, detail="IndieNet이 초기화되지 않음")

        dms = indienet.fetch_dms(limit=limit, since=since)
        return {"dms": dms, "count": len(dms)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/indienet/dms")
async def send_indienet_dm(data: IndieNetDMRequest):
    """IndieNet DM 전송"""
    try:
        indienet = get_indienet()
        if not indienet.is_initialized():
            raise HTTPException(status_code=400, detail="IndieNet이 초기화되지 않음")

        event_id = indienet.send_dm(to_pubkey=data.to_pubkey, content=data.content)

        if event_id:
            import time
            return {
                "status": "sent",
                "event_id": event_id,
                "to": data.to_pubkey,
                "created_at": int(time.time())
            }
        else:
            raise HTTPException(status_code=500, detail="DM 전송 실패")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 보드 (커스텀 해시태그 게시판) API ============

@router.get("/indienet/boards")
async def get_indienet_boards():
    """보드 목록 조회"""
    try:
        indienet = get_indienet()
        boards = indienet.get_boards()
        active_board = indienet.get_active_board()
        return {
            "boards": boards,
            "active_board": active_board,
            "count": len(boards)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/indienet/boards")
async def create_indienet_board(data: IndieNetBoardCreate):
    """새 보드 생성"""
    try:
        indienet = get_indienet()
        if not indienet.is_initialized():
            raise HTTPException(status_code=400, detail="IndieNet이 초기화되지 않음")

        board = indienet.create_board(name=data.name, hashtag=data.hashtag)
        return {"status": "created", "board": board}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/indienet/boards/{hashtag}")
async def delete_indienet_board(hashtag: str):
    """보드 삭제"""
    try:
        indienet = get_indienet()
        success = indienet.delete_board(hashtag)
        if success:
            return {"status": "deleted", "hashtag": hashtag}
        else:
            raise HTTPException(status_code=404, detail="보드를 찾을 수 없습니다")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/indienet/boards/active")
async def set_active_board(hashtag: Optional[str] = None):
    """활성 보드 설정 (hashtag=null이면 기본 IndieNet)"""
    try:
        indienet = get_indienet()
        success = indienet.set_active_board(hashtag)
        if success:
            return {
                "status": "changed",
                "active_board": indienet.get_active_board()
            }
        else:
            raise HTTPException(status_code=404, detail="보드를 찾을 수 없습니다")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indienet/boards/{hashtag}/posts")
async def get_board_posts(hashtag: str, limit: int = 50, since: Optional[int] = None):
    """특정 보드의 게시글 조회"""
    try:
        indienet = get_indienet()
        if not indienet.is_initialized():
            raise HTTPException(status_code=400, detail="IndieNet이 초기화되지 않음")

        posts = indienet.fetch_board_posts(hashtag=hashtag, limit=limit, since=since)
        return {"posts": posts, "count": len(posts), "hashtag": hashtag}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/indienet/boards/post")
async def post_to_board(data: IndieNetBoardPostRequest):
    """보드에 글 게시"""
    try:
        indienet = get_indienet()
        if not indienet.is_initialized():
            raise HTTPException(status_code=400, detail="IndieNet이 초기화되지 않음")

        event_id = indienet.post_to_board(content=data.content, hashtag=data.hashtag)

        if event_id:
            import time
            return {
                "status": "posted",
                "event_id": event_id,
                "hashtag": data.hashtag or indienet.settings.active_board or "indienet",
                "created_at": int(time.time())
            }
        else:
            raise HTTPException(status_code=500, detail="게시 실패")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
