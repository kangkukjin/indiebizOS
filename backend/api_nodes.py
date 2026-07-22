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
    # >0 이면 롱폴: 푸시 작업(phone_jobs) 도착까지 최대 wait초 hold. LTE(CGNAT) 뒤의
    # 폰에 맥이 인바운드로 못 들어가므로, 폰이 이 hold 로 "밀어넣기"를 당겨간다.
    wait: float = 0.0


class JobResultRequest(BaseModel):
    job_id: str
    result: Optional[dict] = None


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
    # 명함 교환(실험 3): 등록해 온 몸의 명함을 백그라운드로 가져와 캐시(냄새).
    # 실패해도 등록엔 무영향 — 명함은 낡아도 냄새로 유효, 다음 등록 때 재시도.
    if req.url and not entry.get("self"):
        import os as _os
        import threading as _th
        _hdrs = {}
        _tok = _os.environ.get("INDIEBIZ_PHONE_TOKEN")
        if _tok and (req.auth == "x_phone_token" or dr.PHONE_CLASS in caps):
            _hdrs["X-Phone-Token"] = _tok
        from peer_cards import fetch_and_cache
        _th.Thread(target=fetch_and_cache, args=(req.url, req.alias),
                   kwargs={"headers": _hdrs}, daemon=True).start()
    return {"success": True, "node": entry, "live_count": len(dr.list_live())}


@router.post("/nodes/heartbeat")
async def node_heartbeat(req: HeartbeatRequest):
    """생존 신고 + (wait>0) 푸시 작업 롱폴 회수 — LTE 푸시의 하행 채널.

    hold 는 워커 스레드(anyio.to_thread)에서 — 이벤트 루프 비차단. hold 를 마친
    시점에 heartbeat 를 한 번 더 찍어 롱폴 자체가 라이브 판정을 노화시키지 않게 한다.
    """
    ok = dr.heartbeat(req.device_id)
    jobs = []
    # 작업 회수는 wait>0(롱폴을 아는 신버전 폰의 opt-in)일 때만 — 응답을 버리는
    # 구버전 폰의 heartbeat 가 큐를 비워 작업을 조용히 유실하는 것을 막는다.
    if ok and req.wait > 0:
        import anyio
        import phone_jobs
        wait = min(req.wait, 50.0)
        jobs = await anyio.to_thread.run_sync(
            phone_jobs.pull_blocking, req.device_id, wait)
        dr.heartbeat(req.device_id)
    return {"success": ok, "live_count": len(dr.list_live()), "jobs": jobs}


@router.post("/nodes/job-result")
async def node_job_result(req: JobResultRequest):
    """폰이 푸시 작업 실행 결과를 회신 — 대기 중인 포워드(wait_result)를 깨운다."""
    import phone_jobs
    phone_jobs.set_result(req.job_id, req.result)
    return {"success": True}


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


@router.get("/nodes/card")
async def capability_card(detail: str = "full"):
    """이 몸의 명함 — 자기 레지스트리에서 파생한 능력 자기소개(desc-프로젝션).

    몸 독립 소통 연구(실험 1): 두 몸이 서로의 어휘를 통째로 아는 대신 명함을
    교환한다. detail=full(액션 desc 전부) | summary(노드·그룹 집계).
    """
    from capability_card import build_card
    return build_card(detail=detail)


class AskRequest(BaseModel):
    message: str          # 자연어 부탁 — 상대는 내 코드를 조립하지 않는다
    from_body: str = ""   # 발신 몸 식별(선택, 계측용)
    dry_run: bool = False # True=컴파일만(실험 계측: 번역 품질을 실행과 분리 측정)


@router.post("/nodes/ask")
def body_ask(req: AskRequest):
    """부탁 경로 — 몸 독립 소통 연구(실험 2).

    명함만 아는 상대의 자연어 부탁을 받아 내 사전으로 컴파일·실행·통화 반환.
    동기 def(스레드풀) — LLM 번역·실행이 이벤트 루프를 막지 않게(자기교착 방지).
    """
    from body_ask import handle_ask
    return handle_ask(req.message, dry_run=req.dry_run, from_body=req.from_body)


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
            return {"has_peer": False, "peer_name": "맥미니(집 PC)", "peer_icon": "💻",
                    "online": False, "detail": "맥 주소(INDIEBIZ_MAC_URL) 미설정"}

        def _probe() -> bool:
            try:
                import requests
                return requests.get(f"{mac_url}/ping", timeout=2).status_code == 200
            except Exception:
                return False
        import asyncio
        online = await asyncio.get_event_loop().run_in_executor(None, _probe)
        return {"has_peer": True, "peer_name": "맥미니(집 PC)", "peer_icon": "💻",
                "online": bool(online), "detail": None}

    # 맥(허브) → 라이브 테이블에서 연결된 폰(self 제외)
    others = [e for e in dr.list_live() if not e.get("self")]
    online = len(others) > 0
    if not online:
        peer_name = "안드로이드 폰"
    elif len(others) == 1:
        peer_name = others[0].get("alias") or "안드로이드 폰"
    else:
        peer_name = f"폰 {len(others)}대"
    return {"has_peer": True, "peer_name": peer_name, "peer_icon": "📱", "online": online,
            "nodes": [e.get("alias") for e in others], "detail": None}


@router.get("/nodes/active-work")
def active_work():
    """조종실 '액티브 프로젝트' 계기 — 판단 기준 2층(사용자 확정, 2026-07-03):

    · 칩(창 열림) = **창이 열려 있는 프로젝트**. 프로젝트 창도 System AI 와 똑같이 창 존재
      하트비트(open_project_windows)로 판단한다 — 창이 열려 있으면 칩, 닫힘/크래시/재시작은
      하트비트 중단→TTL 만료로 self-healing 소멸. (예전엔 러너 레지스트리로 판단해 창 닫힘
      stop_all 신호가 실패하면 유령 칩이 남아 재발했다.)
    · busy(펄스) = thread_context 활성 작업 레지스트리에 지금 처리 중으로 잡히는 곳.
    · 러너 레지스트리(agent_runners)는 이제 칩의 에이전트 이름 소스로만 참조한다.
    · 시스템 AI 는 러너가 없는 싱글턴이라 대화창 하트비트(is_sysai_window_open)로
      "창 열림=활성"을 판단한다 — 창이 열려 있으면 칩, 처리 중이면 펄스(busy).
    · 창 없이 도는 런(위임 등)도 busy 로 잡히면 정직하게 표시한다(계기는 진실 우선).
    프로젝트는 id==name 관습이라 project_name=project_id 를 그대로 쓴다.
    """
    import time as _t
    from thread_context import list_active_work

    # 지금 처리 중(busy) — 프로젝트별 가장 이른 시작 시각
    busy_projects = {}
    sys_started = None
    for w in list_active_work():
        if w.get("sysai"):
            sys_started = w["started_at"] if sys_started is None else min(sys_started, w["started_at"])
            continue
        pid = w.get("project_id") or ""
        if pid:
            busy_projects[pid] = min(busy_projects.get(pid, w["started_at"]), w["started_at"])

    # 창 열림(하트비트) — 프로젝트의 started-runner 에 해당하는 System AI 신호.
    try:
        from thread_context import is_sysai_window_open
        sys_open = is_sysai_window_open()
    except Exception:
        sys_open = False

    now = _t.time()
    items = []
    # 창이 열려 있으면(창 열림=활성) 또는 지금 처리 중이면 칩을 띄운다. busy=처리 중일 때만 펄스.
    if sys_started is not None or sys_open:
        items.append({"kind": "system_ai", "project_id": "", "project_name": "시스템 AI",
                      "agents": [], "busy": sys_started is not None,
                      "elapsed_sec": int(now - sys_started) if sys_started is not None else 0})

    # 창 열림(하트비트) 프로젝트 집합 — self-healing. 창 닫힘 stop_all 신호에 의존하지 않는다.
    try:
        from thread_context import open_project_windows
        open_pids = open_project_windows()
    except Exception:
        open_pids = set()

    # 러너 레지스트리는 칩의 '에이전트 이름' 소스로만 참조 (창 열림 판단은 하트비트가 담당)
    try:
        from api_agents import get_agent_runners
        runners = get_agent_runners() or {}
    except Exception:
        runners = {}

    # 칩 = 창이 열린 프로젝트 ∪ 지금 처리 중(창 없는 위임 런 등, 진실 우선)
    for pid in sorted(set(open_pids) | set(busy_projects.keys())):
        names = []
        for aid, info in (runners.get(pid) or {}).items():
            r = (info or {}).get("runner")
            if (info or {}).get("running") and r is not None and getattr(r, "running", True):
                names.append(((info.get("config") or {}).get("name")) or aid)
        busy = pid in busy_projects
        items.append({"kind": "project", "project_id": pid, "project_name": pid,
                      "agents": sorted(names), "busy": busy,
                      "elapsed_sec": int(now - busy_projects[pid]) if busy else 0})
    return {"items": items}


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
