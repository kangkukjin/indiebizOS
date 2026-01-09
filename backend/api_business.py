"""
api_business.py - 비즈니스 관리 API
kvisual-mcp의 비즈니스 기능을 indiebizOS에 통합
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from business_manager import BusinessManager

router = APIRouter(prefix="/business")

# 매니저 인스턴스
business_manager: BusinessManager = None

def init_manager():
    """매니저 초기화"""
    global business_manager
    business_manager = BusinessManager()


# ============ Pydantic 모델 ============

class BusinessCreate(BaseModel):
    name: str
    level: int = 0
    description: Optional[str] = None

class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    level: Optional[int] = None
    description: Optional[str] = None

class BusinessItemCreate(BaseModel):
    title: str
    details: Optional[str] = None
    attachment_path: Optional[str] = None

class BusinessItemUpdate(BaseModel):
    title: Optional[str] = None
    details: Optional[str] = None
    attachment_path: Optional[str] = None

class DocumentUpdate(BaseModel):
    title: str
    content: str

class NeighborCreate(BaseModel):
    name: str
    info_level: int = 0
    rating: int = 0
    additional_info: Optional[str] = None
    business_doc: Optional[str] = None
    info_share: int = 0

class NeighborUpdate(BaseModel):
    name: Optional[str] = None
    info_level: Optional[int] = None
    rating: Optional[int] = None
    additional_info: Optional[str] = None
    business_doc: Optional[str] = None
    info_share: Optional[int] = None

class ContactUpdate(BaseModel):
    contact_type: Optional[str] = None
    contact_value: Optional[str] = None

class ContactCreate(BaseModel):
    contact_type: str
    contact_value: str

class MessageCreate(BaseModel):
    content: str
    contact_type: str
    contact_value: str
    subject: Optional[str] = None
    neighbor_id: Optional[int] = None
    is_from_user: int = 0
    attachment_path: Optional[str] = None

class ChannelSettingUpdate(BaseModel):
    enabled: Optional[bool] = None
    config: Optional[str] = None
    polling_interval: Optional[int] = None


# ============ 통신채널 설정 ============
# 주의: /channels는 /{business_id}보다 먼저 정의해야 함

def _sanitize_channel_config(channel: dict) -> dict:
    """채널 설정에서 민감한 정보(nsec, private_key_hex) 제거"""
    if not channel or 'config' not in channel:
        return channel

    try:
        import json
        config = json.loads(channel.get('config', '{}'))
        # 비밀키 제거 (npub, relays만 유지)
        config.pop('nsec', None)
        config.pop('private_key_hex', None)
        channel['config'] = json.dumps(config)
    except:
        pass
    return channel

@router.get("/channels")
async def get_all_channel_settings():
    """모든 통신채널 설정 조회"""
    try:
        channels = business_manager.get_all_channel_settings()
        # 민감한 정보 제거
        return [_sanitize_channel_config(ch) for ch in channels]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/channels/poller/status")
async def get_poller_status():
    """채널 폴러 상태 조회"""
    try:
        from channel_poller import get_channel_poller
        poller = get_channel_poller()
        return {
            "running": poller.running,
            "active_channels": list(poller.threads.keys())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/channels/{channel_type}")
async def get_channel_setting(channel_type: str):
    """특정 통신채널 설정 조회"""
    try:
        channel = business_manager.get_channel_setting(channel_type)
        if not channel:
            raise HTTPException(status_code=404, detail="통신채널을 찾을 수 없습니다")
        # 민감한 정보 제거
        return _sanitize_channel_config(channel)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/channels/{channel_type}")
async def update_channel_setting(channel_type: str, data: ChannelSettingUpdate):
    """통신채널 설정 업데이트"""
    try:
        channel = business_manager.update_channel_setting(
            channel_type,
            enabled=data.enabled,
            config=data.config,
            polling_interval=data.polling_interval
        )

        # 채널 폴러에 설정 변경 알림
        try:
            from channel_poller import get_channel_poller
            poller = get_channel_poller()
            poller.refresh_channel(channel_type)
        except Exception as e:
            print(f"[API] 채널 폴러 새로고침 실패: {e}")

        return channel
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/channels/{channel_type}/poll")
async def poll_channel_now(channel_type: str):
    """채널 즉시 폴링"""
    try:
        from channel_poller import get_channel_poller
        poller = get_channel_poller()
        result = poller.poll_now(channel_type)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 비즈니스 CRUD (목록/생성만 - 동적 경로는 파일 끝에) ============

@router.get("")
async def get_businesses(
    level: Optional[int] = Query(None, description="필터링할 레벨"),
    search: Optional[str] = Query(None, description="검색어")
):
    """비즈니스 목록 조회"""
    try:
        businesses = business_manager.get_businesses(level=level, search=search)
        return businesses
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def create_business(data: BusinessCreate):
    """비즈니스 생성"""
    try:
        business = business_manager.create_business(
            name=data.name,
            level=data.level,
            description=data.description
        )
        return business
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/items/{item_id}")
async def update_business_item(item_id: int, data: BusinessItemUpdate):
    """비즈니스 아이템 수정"""
    try:
        item = business_manager.update_business_item(
            item_id,
            title=data.title,
            details=data.details,
            attachment_path=data.attachment_path
        )
        return item
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/items/{item_id}")
async def delete_business_item(item_id: int):
    """비즈니스 아이템 삭제"""
    try:
        business_manager.delete_business_item(item_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 비즈니스 문서 ============

@router.get("/documents/all")
async def get_all_business_documents():
    """모든 비즈니스 문서 조회"""
    try:
        docs = business_manager.get_all_business_documents()
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/{level}")
async def get_business_document(level: int):
    """특정 레벨의 비즈니스 문서 조회"""
    try:
        doc = business_manager.get_business_document(level)
        return doc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/documents/{level}")
async def update_business_document(level: int, data: DocumentUpdate):
    """비즈니스 문서 수정"""
    try:
        doc = business_manager.update_business_document(level, data.title, data.content)
        return doc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 근무 지침 ============

@router.get("/guidelines/all")
async def get_all_work_guidelines():
    """모든 근무 지침 조회"""
    try:
        guidelines = business_manager.get_all_work_guidelines()
        return guidelines
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/guidelines/{level}")
async def get_work_guideline(level: int):
    """특정 레벨의 근무 지침 조회"""
    try:
        guideline = business_manager.get_work_guideline(level)
        return guideline
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/guidelines/{level}")
async def update_work_guideline(level: int, data: DocumentUpdate):
    """근무 지침 수정"""
    try:
        guideline = business_manager.update_work_guideline(level, data.title, data.content)
        return guideline
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 문서 자동 생성 ============

@router.post("/documents/regenerate")
async def regenerate_business_documents():
    """비즈니스 목록 기반으로 모든 레벨의 문서 자동 재생성"""
    try:
        result = business_manager.regenerate_business_documents()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 이웃 (Neighbors) CRUD ============

@router.get("/neighbors")
async def get_neighbors(
    search: Optional[str] = Query(None),
    info_level: Optional[int] = Query(None, description="정보 레벨로 필터링")
):
    """이웃 목록 조회"""
    try:
        neighbors = business_manager.get_neighbors(search=search, info_level=info_level)
        return neighbors
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/neighbors")
async def create_neighbor(data: NeighborCreate):
    """이웃 생성"""
    try:
        neighbor = business_manager.create_neighbor(
            name=data.name,
            info_level=data.info_level,
            rating=data.rating,
            additional_info=data.additional_info,
            business_doc=data.business_doc,
            info_share=data.info_share
        )
        return neighbor
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/neighbors/{neighbor_id}")
async def get_neighbor(neighbor_id: int):
    """이웃 상세 조회"""
    try:
        neighbor = business_manager.get_neighbor(neighbor_id)
        if not neighbor:
            raise HTTPException(status_code=404, detail="이웃을 찾을 수 없습니다")
        return neighbor
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/neighbors/{neighbor_id}")
async def update_neighbor(neighbor_id: int, data: NeighborUpdate):
    """이웃 수정"""
    try:
        neighbor = business_manager.update_neighbor(
            neighbor_id,
            name=data.name,
            info_level=data.info_level,
            rating=data.rating,
            additional_info=data.additional_info,
            business_doc=data.business_doc,
            info_share=data.info_share
        )
        return neighbor
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/neighbors/{neighbor_id}")
async def delete_neighbor(neighbor_id: int):
    """이웃 삭제"""
    try:
        business_manager.delete_neighbor(neighbor_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 연락처 (Contacts) ============

@router.get("/neighbors/{neighbor_id}/contacts")
async def get_contacts(neighbor_id: int):
    """이웃의 연락처 목록 조회"""
    try:
        contacts = business_manager.get_contacts(neighbor_id)
        return contacts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/neighbors/{neighbor_id}/contacts")
async def add_contact(neighbor_id: int, data: ContactCreate):
    """연락처 추가"""
    try:
        contact = business_manager.add_contact(
            neighbor_id=neighbor_id,
            contact_type=data.contact_type,
            contact_value=data.contact_value
        )
        return contact
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/contacts/{contact_id}")
async def update_contact(contact_id: int, data: ContactUpdate):
    """연락처 수정"""
    try:
        contact = business_manager.update_contact(
            contact_id,
            contact_type=data.contact_type,
            contact_value=data.contact_value
        )
        return contact
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: int):
    """연락처 삭제"""
    try:
        business_manager.delete_contact(contact_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 메시지 (Messages) ============

@router.get("/messages")
async def get_messages(
    neighbor_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    unprocessed_only: bool = Query(False),
    unreplied_only: bool = Query(False),
    limit: int = Query(50)
):
    """메시지 목록 조회"""
    try:
        messages = business_manager.get_messages(
            neighbor_id=neighbor_id,
            status=status,
            unprocessed_only=unprocessed_only,
            unreplied_only=unreplied_only,
            limit=limit
        )
        return messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages")
async def create_message(data: MessageCreate):
    """메시지 저장"""
    try:
        message = business_manager.create_message(
            content=data.content,
            contact_type=data.contact_type,
            contact_value=data.contact_value,
            subject=data.subject,
            neighbor_id=data.neighbor_id,
            is_from_user=data.is_from_user,
            attachment_path=data.attachment_path
        )
        return message
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/messages/{message_id}")
async def get_message(message_id: int):
    """메시지 상세 조회"""
    try:
        message = business_manager.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
        return message
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/messages/{message_id}/status")
async def update_message_status(message_id: int, status: str, error_message: Optional[str] = None):
    """메시지 상태 업데이트"""
    try:
        message = business_manager.update_message_status(message_id, status, error_message)
        return message
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/{message_id}/processed")
async def mark_message_processed(message_id: int):
    """메시지 처리 완료 표시"""
    try:
        message = business_manager.mark_message_processed(message_id)
        return message
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/{message_id}/replied")
async def mark_message_replied(message_id: int):
    """메시지 응답 완료 표시"""
    try:
        message = business_manager.mark_message_replied(message_id)
        return message
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 자동응답 설정 ============

@router.get("/auto-response/status")
async def get_auto_response_status():
    """자동응답 서비스 상태 조회"""
    try:
        from auto_response import get_auto_response_service
        service = get_auto_response_service()
        return {
            "running": service._running,
            "check_interval": service._check_interval,
            "processed_count": len(service._processed_messages)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-response/start")
async def start_auto_response():
    """자동응답 서비스 시작"""
    try:
        from auto_response import get_auto_response_service
        service = get_auto_response_service()
        service.start()
        return {"status": "started", "running": service._running}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-response/stop")
async def stop_auto_response():
    """자동응답 서비스 중지"""
    try:
        from auto_response import get_auto_response_service
        service = get_auto_response_service()
        service.stop()
        return {"status": "stopped", "running": service._running}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 비즈니스 동적 라우트 (맨 마지막에 위치해야 함) ============
# 주의: /{business_id} 형태의 동적 경로는 /neighbors, /documents 등보다 뒤에 있어야 함

@router.get("/{business_id}")
async def get_business(business_id: int):
    """비즈니스 상세 조회"""
    try:
        business = business_manager.get_business(business_id)
        if not business:
            raise HTTPException(status_code=404, detail="비즈니스를 찾을 수 없습니다")
        return business
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{business_id}")
async def update_business(business_id: int, data: BusinessUpdate):
    """비즈니스 수정"""
    try:
        business = business_manager.update_business(
            business_id,
            name=data.name,
            level=data.level,
            description=data.description
        )
        return business
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{business_id}")
async def delete_business(business_id: int):
    """비즈니스 삭제"""
    try:
        business_manager.delete_business(business_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{business_id}/items")
async def get_business_items(business_id: int):
    """비즈니스 아이템 목록 조회"""
    try:
        items = business_manager.get_business_items(business_id)
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{business_id}/items")
async def create_business_item(business_id: int, data: BusinessItemCreate):
    """비즈니스 아이템 생성"""
    try:
        item = business_manager.create_business_item(
            business_id=business_id,
            title=data.title,
            details=data.details,
            attachment_path=data.attachment_path
        )
        return item
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
