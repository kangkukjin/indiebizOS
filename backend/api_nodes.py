"""api_nodes.py — 다중 노드 프레즌스 API (허브=맥이 서빙)

각 노드(폰 등)가 부팅 시 자기를 등록하고 주기적으로 heartbeat 한다. 허브가 "지금 연결된
노드" 라이브 테이블을 유지 → 폰 수를 고정하지 않고 연결로 확인. 라우팅(ibl_engine)이 이
테이블을 조회해 원격 액션의 대상을 동적으로 고른다.

인증: 전역 remote_access_guard 가 외부(비-localhost) 요청에 런처 세션을 요구한다(localhost 통과).
폰은 이미 _forward_to_mac 용 세션이 있으므로 같은 세션으로 등록한다.

설계: docs/MULTINODE_TOPOLOGY_DESIGN.md
"""
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

import device_registry as dr

router = APIRouter()


class RegisterRequest(BaseModel):
    device_id: str
    alias: str
    capabilities: List[str] = []
    url: str = ""                 # 허브가 이 노드에 닿는 주소 (LAN IP:포트 등)
    auth: str = "x_phone_token"   # 포워드 인증 방식
    owner: str = "self"
    primary: bool = False


class HeartbeatRequest(BaseModel):
    device_id: str


class PrimaryRequest(BaseModel):
    target: Optional[str] = None    # 주(主)로 지정할 노드의 별칭 또는 device_id
    connected_phone: bool = False   # True면 "지금 연결된 폰"을 자동 선택(1대일 때)


@router.post("/nodes/register")
async def register_node(req: RegisterRequest):
    """노드 자기등록(upsert). 폰 부팅/IP변동 시 호출."""
    caps = req.capabilities or [dr.PHONE_CLASS]
    entry = dr.register(req.device_id, req.alias, caps, req.url,
                        auth=req.auth, owner=req.owner, primary=req.primary)
    if entry.get("error"):
        return {"success": False, **entry}
    return {"success": True, "node": entry, "live_count": len(dr.list_live())}


@router.post("/nodes/heartbeat")
async def node_heartbeat(req: HeartbeatRequest):
    ok = dr.heartbeat(req.device_id)
    return {"success": ok, "live_count": len(dr.list_live())}


@router.get("/nodes/live")
async def list_nodes():
    """지금 연결된(라이브) 노드 목록 — "폰 몇 대?"를 연결로 확인.

    (경로가 /nodes 가 아닌 /nodes/live 인 이유: /nodes 는 api_packages 의 논리-노드 목록이
    이미 차지. 여긴 *물리 기기* 프레즌스.)
    """
    live = dr.list_live()
    return {
        "count": len(live),
        "nodes": [
            {"alias": e.get("alias"), "device_id": e.get("device_id"),
             "capabilities": e.get("capabilities"), "primary": e.get("primary"),
             "self": e.get("self"), "last_seen": e.get("last_seen")}
            for e in live
        ],
    }


@router.get("/nodes/peer-status")
async def peer_status():
    """피어(다른 몸)의 연결상태 — 계기판이 "연락할 몸이 살아있나"를 표시한다.

    몸-인식(body-aware), 한 엔드포인트로 양방향:
      · 폰  → 맥(집 PC)의 공개 /ping 을 핑해 온/오프라인.
      · 맥(허브) → 라이브 노드 테이블(self 제외)에서 연결된 폰을 본다.
    각 백엔드의 로컬 호출(WebView/Electron → 자기 백엔드)이라 무인증 통과.
    """
    import os
    try:
        from runtime_utils import detect_body
        kind = detect_body().get("kind", "mac")
    except Exception:
        kind = "mac"

    # 폰 → 맥(집 PC) 생존 핑
    if kind == "phone":
        mac_url = (os.environ.get("INDIEBIZ_MAC_URL") or "").rstrip("/")
        if not mac_url:
            return {"has_peer": False, "peer_name": "맥미니(집 PC)", "online": False,
                    "detail": "맥 주소(INDIEBIZ_MAC_URL) 미설정"}

        def _probe() -> bool:
            try:
                import requests
                return requests.get(f"{mac_url}/ping", timeout=2).status_code == 200
            except Exception:
                return False
        import asyncio
        online = await asyncio.get_event_loop().run_in_executor(None, _probe)
        return {"has_peer": True, "peer_name": "맥미니(집 PC)", "online": bool(online), "detail": None}

    # 맥(허브) → 라이브 테이블에서 연결된 폰(self 제외)
    others = [e for e in dr.list_live() if not e.get("self")]
    online = len(others) > 0
    if not online:
        peer_name = "안드로이드 폰"
    elif len(others) == 1:
        peer_name = others[0].get("alias") or "안드로이드 폰"
    else:
        peer_name = f"폰 {len(others)}대"
    return {"has_peer": True, "peer_name": peer_name, "online": online,
            "nodes": [e.get("alias") for e in others], "detail": None}


@router.post("/nodes/primary")
async def set_primary(req: PrimaryRequest):
    """노드를 그 능력의 주(主)기기로 지정(주소 생략 시 자동선택 대상). 같은 능력의 다른
    노드는 주(主) 해제(능력당 0~1). connected_phone=True 면 지금 연결된 폰(1대일 때) 자동 선택."""
    target = req.target
    if req.connected_phone and not target:
        phones = dr.live_with_capability(dr.PHONE_CLASS)
        if not phones:
            return {"success": False, "error": "지금 연결된 폰이 없습니다. (폰 백엔드가 켜져 "
                    "허브에 등록됐는지 확인하세요)"}
        if len(phones) > 1:
            return {"success": False, "error": "연결된 폰이 여러 대입니다 — 어느 폰을 주(主)로?",
                    "options": [p.get("alias") for p in phones]}
        target = phones[0].get("alias")
    if not target:
        return {"success": False, "error": "target(별칭/device_id) 또는 connected_phone 필요"}
    node = dr.set_primary(target)
    if node is None or node.get("error"):
        return {"success": False, "error": (node or {}).get("error", f"'{target}' 노드를 찾을 수 없음"),
                "live_nodes": dr.live_aliases()}
    return {"success": True, "primary": node.get("alias"), "device_id": node.get("device_id")}
