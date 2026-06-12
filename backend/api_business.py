"""
api_business.py - 비즈니스 관리 API
kvisual-mcp의 비즈니스 기능을 indiebizOS에 통합
"""

import json
import shutil
import httpx
import logging
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Optional, List
from business_manager import BusinessManager
from runtime_utils import get_data_path

logger = logging.getLogger(__name__)

# ============ nostr.build 이미지 업로드 ============

NOSTR_BUILD_UPLOAD_URL = "https://nostr.build/api/v2/upload/files"
IMAGE_SECTION_SEPARATOR = "\n\n📷 상품 이미지:\n"


async def upload_to_nostr_build(file_path: str) -> Optional[str]:
    """로컬 이미지를 nostr.build에 업로드하고 URL 반환"""
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        logger.warning(f"[nostr.build] 파일 없음: {file_path}")
        return None

    # 10MB 제한
    if path.stat().st_size > 10 * 1024 * 1024:
        logger.warning(f"[nostr.build] 파일 크기 초과 (10MB): {file_path}")
        return None

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(file_path, "rb") as f:
                files = {"file": (path.name, f, f"image/{path.suffix.lstrip('.').lower()}")}
                resp = await client.post(NOSTR_BUILD_UPLOAD_URL, files=files)

            if resp.status_code != 200:
                logger.error(f"[nostr.build] 업로드 실패 HTTP {resp.status_code}: {resp.text[:200]}")
                return None

            data = resp.json()
            # NIP-94 응답에서 URL 추출
            if data.get("status") == "success":
                nip94 = data.get("data", [])
                for item in nip94:
                    tags = item.get("tags", [])
                    for tag in tags:
                        if isinstance(tag, list) and len(tag) >= 2 and tag[0] == "url":
                            logger.info(f"[nostr.build] 업로드 성공: {tag[1]}")
                            return tag[1]

            logger.error(f"[nostr.build] URL 추출 실패: {json.dumps(data)[:300]}")
            return None
    except Exception as e:
        logger.error(f"[nostr.build] 업로드 예외: {e}")
        return None


def build_details_with_images(details: Optional[str], image_urls: List[str]) -> str:
    """details 텍스트에 이미지 URL 섹션을 추가/갱신"""
    # 기존 사용자 설명과 이미지 섹션 분리
    user_text = strip_image_section(details)

    if not image_urls:
        return user_text

    url_lines = "\n".join(f"- {url}" for url in image_urls)
    return f"{user_text}{IMAGE_SECTION_SEPARATOR}{url_lines}"


def strip_image_section(details: Optional[str]) -> str:
    """details에서 이미지 URL 섹션을 제거하고 사용자 텍스트만 반환"""
    if not details:
        return ""
    idx = details.find(IMAGE_SECTION_SEPARATOR)
    if idx >= 0:
        return details[:idx]
    return details


def extract_image_urls(details: Optional[str]) -> List[str]:
    """details에서 기존 nostr.build 이미지 URL 추출"""
    if not details:
        return []
    idx = details.find(IMAGE_SECTION_SEPARATOR)
    if idx < 0:
        return []
    section = details[idx + len(IMAGE_SECTION_SEPARATOR):]
    urls = []
    for line in section.strip().split("\n"):
        line = line.strip()
        if line.startswith("- "):
            url = line[2:].strip()
            if url.startswith("https://"):
                urls.append(url)
    return urls


def _delete_local_images(attachment_path: Optional[str]):
    """attachment_path(JSON 배열 or 단일 경로)에서 로컬 이미지 파일 삭제"""
    if not attachment_path:
        return
    try:
        paths = json.loads(attachment_path)
        if not isinstance(paths, list):
            paths = [attachment_path]
    except (json.JSONDecodeError, TypeError):
        paths = [attachment_path]

    images_dir = get_data_path() / "business_images"
    for p in paths:
        fp = Path(p)
        # business_images 폴더 내 파일만 삭제 (안전장치)
        try:
            if fp.exists() and fp.is_file() and images_dir in fp.parents:
                fp.unlink()
                logger.info(f"[이미지 정리] 삭제: {fp.name}")
        except Exception as e:
            logger.warning(f"[이미지 정리] 삭제 실패 {fp}: {e}")

router = APIRouter(prefix="/business")

# 매니저 인스턴스
business_manager: BusinessManager = None

def init_manager():
    """매니저 초기화"""
    global business_manager
    business_manager = BusinessManager()


# ============ 폰↔PC 동기화 (합집합 머지 — LWW + tombstone) ============
# business.db 주소록 메타데이터(이웃·연락처·사업·아이템·문서·지침)를 다른 기기(폰)와 합집합 머지.
# 자동응답=PC전용, 메시지/글 내용=릴레이/Gmail 수렴이라 머지 대상 아님. (business_sync.py)
# ★인증: api.py 의 remote_access_guard 미들웨어가 외부(터널) 요청에 launcher 세션(X-Launcher-Session)을
#        강제한다(localhost=데스크탑은 통과). 주소록 전체를 노출하는 데이터 엔드포인트라 public
#        화이트리스트(is_public_remote_path)에 넣지 않는다 → 외부는 반드시 로그인 후 접근.

@router.get("/sync/export")
async def business_sync_export():
    """이 기기의 business.db 동기화 스냅샷(삭제 tombstone 포함)을 내보냄."""
    try:
        from business_sync import export_business_db
        return {"success": True, "data": export_business_db(business_manager)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/merge")
async def business_sync_merge(payload: dict = Body(...)):
    """다른 기기의 export 를 이 기기에 합집합 머지(LWW+tombstone) 후, 머지된 이 기기의 최신
    스냅샷을 반환 → 호출자가 그걸 다시 머지하면 1왕복으로 양방향 동기화(머지는 교환·멱등).
    payload = {"data": {table: [rows]}} 또는 {table: [rows]} 직접."""
    try:
        from business_sync import export_business_db, merge_business_db
        remote = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        if not isinstance(remote, dict):
            raise HTTPException(status_code=400, detail="sync 페이로드 형식 오류(dict 필요)")
        stats = merge_business_db(business_manager, remote)
        return {"success": True, "stats": stats, "data": export_business_db(business_manager)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    attachment_paths: Optional[List[str]] = None  # 다중 이미지

class BusinessItemUpdate(BaseModel):
    title: Optional[str] = None
    details: Optional[str] = None
    attachment_path: Optional[str] = None
    attachment_paths: Optional[List[str]] = None  # 다중 이미지

class ImageCopyRequest(BaseModel):
    source_paths: List[str]

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
    favorite: Optional[int] = None

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
    status: Optional[str] = "received"  # pending으로 설정하면 실제 발송

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

        # Gmail 채널의 경우 config.yaml도 업데이트 (유일한 출처)
        if channel_type == 'gmail' and data.config:
            try:
                import yaml
                from runtime_utils import get_base_path
                config = json.loads(data.config)

                gmail_path = get_base_path() / "data" / "packages" / "installed" / "extensions" / "gmail"
                gmail_path.mkdir(parents=True, exist_ok=True)
                config_yaml_path = gmail_path / "config.yaml"

                # config.yaml 업데이트 (토큰 파일은 email 기반으로 자동 결정)
                gmail_yaml = {
                    'gmail': {
                        'client_id': config.get('client_id', ''),
                        'client_secret': config.get('client_secret', ''),
                        'email': config.get('email', ''),
                    }
                }
                with open(config_yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(gmail_yaml, f, default_flow_style=False, allow_unicode=True)
            except Exception as e:
                print(f"[API] Gmail config.yaml 업데이트 실패: {e}")

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


@router.post("/channels/gmail/authenticate")
async def authenticate_gmail():
    """Gmail OAuth 인증 시작"""
    try:
        import json
        from pathlib import Path

        bm = BusinessManager()
        channel = bm.get_channel_setting('gmail')
        if not channel:
            raise HTTPException(status_code=404, detail="Gmail 채널 설정 없음")

        config = json.loads(channel.get('config', '{}'))
        client_id = config.get('client_id', '')
        client_secret = config.get('client_secret', '')

        if not client_id or not client_secret:
            raise HTTPException(status_code=400, detail="OAuth 클라이언트 ID/Secret이 설정되지 않았습니다")

        # Gmail 확장 경로의 config.yaml 생성
        from runtime_utils import get_base_path
        gmail_path = get_base_path() / "data" / "packages" / "installed" / "extensions" / "gmail"
        gmail_path.mkdir(parents=True, exist_ok=True)
        config_path = gmail_path / "config.yaml"

        import yaml
        gmail_config = {
            'gmail': {
                'client_id': client_id,
                'client_secret': client_secret,
                'token_file': 'tokens/token.json',
                'credentials_path': str(gmail_path / 'credentials.json'),
            }
        }

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(gmail_config, f, default_flow_style=False)

        # credentials.json도 생성 (Google API가 요구하는 형식)
        credentials_data = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }

        credentials_path = gmail_path / "credentials.json"
        with open(credentials_path, 'w', encoding='utf-8') as f:
            json.dump(credentials_data, f, indent=2)

        # Gmail 클라이언트로 인증 시작
        import sys
        sys.path.insert(0, str(gmail_path))

        try:
            from gmail import GmailClient
            gmail_client = GmailClient(gmail_config['gmail'])
            gmail_client.authenticate()

            # 인증 성공 시 config 업데이트
            config['authenticated'] = True
            # 이메일은 사용자가 미리 지정한 값(config['email']) 유지
            bm.update_channel_setting('gmail', config=json.dumps(config))

            return {"status": "success", "message": "Gmail 인증 완료"}
        except Exception as auth_error:
            return {"status": "error", "message": f"인증 실패: {str(auth_error)}"}

    except HTTPException:
        raise
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

@router.post("/items/copy-images")
async def copy_images_for_item(data: ImageCopyRequest):
    """이미지 파일들을 business_images 디렉토리로 복사"""
    try:
        images_dir = get_data_path() / "business_images"
        images_dir.mkdir(parents=True, exist_ok=True)

        copied_paths = []
        allowed_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

        for src_path in data.source_paths:
            src = Path(src_path)
            if not src.exists() or not src.is_file():
                continue
            if src.suffix.lower() not in allowed_exts:
                continue

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            safe_name = src.name.replace(" ", "_")
            dest_name = f"{timestamp}_{safe_name}"
            dest_path = images_dir / dest_name

            shutil.copy2(str(src), str(dest_path))
            copied_paths.append(str(dest_path))

        return {"status": "success", "paths": copied_paths}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/items/{item_id}")
async def update_business_item(item_id: int, data: BusinessItemUpdate):
    """비즈니스 아이템 수정 (이미지 변경 시 nostr.build 재업로드)"""
    try:
        attachment_path = data.attachment_path
        if data.attachment_paths is not None:
            attachment_path = json.dumps(data.attachment_paths)

        details = data.details

        # attachment_paths가 제공되면 이미지 URL 섹션 갱신
        if data.attachment_paths is not None:
            # 기존 아이템의 details에서 이미 업로드된 URL 확인
            existing_item = business_manager.get_business_item(item_id)
            old_urls = extract_image_urls(existing_item.get("details") if existing_item else None)

            # 기존 attachment_paths 파악
            old_att = existing_item.get("attachment_path", "") if existing_item else ""
            try:
                old_paths = json.loads(old_att) if old_att else []
            except (json.JSONDecodeError, TypeError):
                old_paths = [old_att] if old_att else []

            new_paths = data.attachment_paths or []

            # 제거된 이미지 로컬 파일 삭제
            removed = set(old_paths) - set(new_paths)
            for rp in removed:
                fp = Path(rp)
                images_dir = get_data_path() / "business_images"
                try:
                    if fp.exists() and fp.is_file() and images_dir in fp.parents:
                        fp.unlink()
                        logger.info(f"[이미지 정리] 삭제: {fp.name}")
                except Exception as e:
                    logger.warning(f"[이미지 정리] 삭제 실패 {fp}: {e}")

            if len(new_paths) == 0:
                # 이미지 전부 삭제 → URL 섹션 제거
                details = strip_image_section(details)
            else:
                # 기존 경로와 URL을 매핑 (순서 기반)
                path_url_map = {}
                for i, p in enumerate(old_paths):
                    if i < len(old_urls):
                        path_url_map[p] = old_urls[i]

                # 새 경로 목록 처리
                image_urls = []
                for fp in new_paths:
                    if fp in path_url_map:
                        # 기존 이미지 유지 → 기존 URL 재사용
                        image_urls.append(path_url_map[fp])
                    else:
                        # 새 이미지 → nostr.build 업로드
                        url = await upload_to_nostr_build(fp)
                        if url:
                            image_urls.append(url)

                details = build_details_with_images(details, image_urls)

        item = business_manager.update_business_item(
            item_id,
            title=data.title,
            details=details,
            attachment_path=attachment_path
        )
        return item
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/items/{item_id}")
async def delete_business_item(item_id: int):
    """비즈니스 아이템 삭제 (로컬 이미지도 정리)"""
    try:
        # 삭제 전에 이미지 경로 확인
        item = business_manager.get_business_item(item_id)
        if item:
            _delete_local_images(item.get("attachment_path"))

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
            info_share=data.info_share,
            favorite=data.favorite
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

@router.get("/neighbors/favorites/list")
async def get_favorite_neighbors():
    """빠른 연락처(즐겨찾기) 이웃 목록 조회"""
    try:
        neighbors = business_manager.get_favorite_neighbors()
        return neighbors
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/neighbors/{neighbor_id}/favorite/toggle")
async def toggle_neighbor_favorite(neighbor_id: int):
    """이웃 빠른 연락처 토글"""
    try:
        neighbor = business_manager.toggle_neighbor_favorite(neighbor_id)
        if not neighbor:
            raise HTTPException(status_code=404, detail="이웃을 찾을 수 없습니다")
        return neighbor
    except HTTPException:
        raise
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
            attachment_path=data.attachment_path,
            status=data.status
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
    """자동응답 서비스 시작 (영속 — 재시작에도 켜진 상태 유지)"""
    try:
        from auto_response import get_auto_response_service
        service = get_auto_response_service()
        service.enable()
        return {"status": "started", "running": service._running}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-response/stop")
async def stop_auto_response():
    """자동응답 서비스 중지 (영속 — 재시작해도 꺼진 상태 유지)"""
    try:
        from auto_response import get_auto_response_service
        service = get_auto_response_service()
        service.disable()
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
    """비즈니스 삭제 (하위 아이템의 로컬 이미지도 정리)"""
    try:
        # 삭제 전에 하위 아이템들의 이미지 정리
        items = business_manager.get_business_items(business_id)
        for item in items:
            _delete_local_images(item.get("attachment_path"))

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
    """비즈니스 아이템 생성 (이미지 → nostr.build 자동 업로드)"""
    try:
        attachment_path = data.attachment_path
        if data.attachment_paths is not None:
            attachment_path = json.dumps(data.attachment_paths)

        # 이미지가 있으면 nostr.build에 업로드하고 URL을 details에 추가
        details = data.details
        if data.attachment_paths:
            image_urls = []
            for fp in data.attachment_paths:
                url = await upload_to_nostr_build(fp)
                if url:
                    image_urls.append(url)
            if image_urls:
                details = build_details_with_images(details, image_urls)

        item = business_manager.create_business_item(
            business_id=business_id,
            title=data.title,
            details=details,
            attachment_path=attachment_path
        )
        return item
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
