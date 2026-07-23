"""api_limb.py — USB 헬퍼(손발) 수신 API (허브=허브가 서빙).

USB 로 낯선 PC 에서 실행된 헬퍼가 **아웃바운드로** 허브에 붙는다(그 PC 방화벽·공유기
무설정). 폰이 LTE(CGNAT) 뒤에서 명령을 당겨가는 구조(phone_jobs 롱폴)를 그대로 쓴다 —
헬퍼는 인바운드 주소가 없으므로 허브가 큐에 셸 명령을 넣고, 헬퍼가 poll 로 당겨간다.

인증: 전역 remote_access_guard 를 피해 **limb key 자체 인증**을 쓴다(nas/portal 선례). USB 엔
허브 비밀번호가 아니라 이 키가 실리므로, 헬퍼가 런처 세션(=허브 비밀번호)을 가질 이유가 없다.
→ is_public_remote_path 에 /limb/* 를 등록하고, 여기서 키를 직접 검증한다.

승인: **자동승인**이다 — 유효한 키로 붙으면 즉시 approved=True(첫 접속·재접속·다른 PC 모두).
오배송(엉뚱한 PC 에서 명령이 실행됨) 방어는 승인 게이트가 아니라 **명령 시 손발 이름
명시**로 옮겼다(handler._resolve_limb): 손발이 둘 이상이면 [limbs:guestpc] 가 이름을 강제하고
목록을 보여주므로, 유출된 키로 낯선 PC 가 하나 더 붙는 순간 사용자가 알아챈다. 다른 PC 로
옮겨 붙어도(정상 로밍) 마찰 없이 자동승인하되, host 변경은 알림으로 통지해 유출을 조기에
보이게 한다. 유출 시 최종 방어선은 [self:limb]{op:revoke}(키 폐기). approve op 는 특정 손발을
수동으로 잠그거나(approved=false) 다시 여는 용도로 남는다.

큐 통화: phone_jobs 의 job code 필드에 **셸 봉투 JSON**({op, ...})을 싣는다. 헬퍼가
자기 코드로 그걸 셸/파일 작업으로 해석한다(폰은 같은 필드를 IBL 로 해석 — device_id
네임스페이스가 분리돼 충돌 없음). 손발은 IBL 엔진이 없는 얇은 몸이라 IBL 을 모른다.
"""
import anyio
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

import device_registry as dr
import limb_keys
import phone_jobs

router = APIRouter()

# 헬퍼가 물어보는 롱폴 최대 hold(초). heartbeat 상한(50)과 맞춘다.
MAX_POLL_WAIT = 50.0


class ConnectRequest(BaseModel):
    key: str
    host: str = ""            # 헬퍼가 자기소개하는 호스트명/OS (표시·감사용)


class PollRequest(BaseModel):
    key: str
    wait: float = 25.0        # 롱폴 hold 초


class ResultRequest(BaseModel):
    key: str
    job_id: str
    result: Optional[dict] = None


def _notify_new_limb(rec: dict, host: str):
    """새 손발이 자동승인으로 붙었을 때 소유주에게 알림(best-effort)."""
    msg = (f"손발 '{rec.get('alias')}' 이(가) {host or '알 수 없는 PC'} 에 붙어 바로 쓸 수 있습니다. "
           f"내가 발급한 게 아니라면 [self:limb]{{op:revoke}} 로 폐기하세요.")
    try:
        from notification_manager import get_notification_manager
        get_notification_manager().create(
            title="손발 연결됨", message=msg, type="info", source="limb")
    except Exception:
        print(f"[limb] {msg}")


def _notify_host_change(rec: dict, prev_host: str, host: str):
    """이미 승인된 손발이 다른 PC 에서 붙었을 때 통지(자동승인이라 차단은 안 함).
    내가 옮긴 것이면 정상, 안 옮겼는데 떴다면 키 유출 신호 — revoke 유도."""
    msg = (f"손발 '{rec.get('alias')}' 이(가) 다른 PC 에서 붙었습니다 — "
           f"{prev_host} → {host or '알 수 없는 PC'}. 내가 옮긴 게 아니라면 "
           f"[self:limb]{{op:revoke}} 로 폐기하세요.")
    try:
        from notification_manager import get_notification_manager
        get_notification_manager().create(
            title="손발 위치 변경", message=msg, type="warning", source="limb")
    except Exception:
        print(f"[limb] {msg}")


@router.post("/limb/connect")
async def limb_connect(req: ConnectRequest):
    """헬퍼 최초 접속 — 키 검증 후 손발을 프레즌스에 등록. 승인 상태를 돌려준다.

    승인은 소유주 몫이라 여기서 자동으로 하지 않는다(자동승인 키 개념은 mint 시 결정).
    미승인이어도 등록은 해서 op:list 에 '대기'로 보이게 한다.
    """
    rec = limb_keys.validate(req.key)
    if not rec:
        return {"success": False, "error": "invalid_or_expired_key"}

    # 자동승인 — 붙는 즉시 승인(approve_if_pending). 방어는 명령 시 이름 명시로(위 모듈 주석).
    prev_host = rec.get("last_host")
    host_changed = bool(req.host and prev_host and req.host != prev_host)
    was_pending = not rec.get("approved")
    rec = limb_keys.touch(req.key, host=req.host, approve_if_pending=True) or rec

    # 손발을 프레즌스 레지스트리에 등록 — url="" (인바운드 주소 없음, 폰 푸시 모델과 동일).
    # auth="limb_key" 로 표식해 ibl_engine 이 이 노드에 인바운드 포워드를 시도하지 않게 한다.
    dr.register(rec["device_id"], rec["alias"], [limb_keys.GUEST_PC_CLASS], "",
                auth="limb_key", owner="self", primary=False)

    if was_pending:
        _notify_new_limb(rec, req.host)          # 첫 자동승인
    elif host_changed:
        _notify_host_change(rec, prev_host, req.host)   # 이미 승인된 것이 다른 PC 로 — 통지만

    return {
        "success": True,
        "device_id": rec["device_id"],
        "alias": rec["alias"],
        "approved": bool(rec.get("approved")),
        "poll_wait": MAX_POLL_WAIT,
    }


@router.post("/limb/poll")
async def limb_poll(req: PollRequest):
    """헬퍼가 셸 명령을 롱폴로 당겨간다. 미승인이면 빈 목록 + approved=False.

    hold 는 워커 스레드에서 — 이벤트 루프 비차단(heartbeat 선례).
    """
    rec = limb_keys.validate(req.key)
    if not rec:
        return {"success": False, "error": "invalid_or_expired_key"}

    device_id = rec["device_id"]
    dr.heartbeat(device_id)

    if not rec.get("approved"):
        # 승인 전엔 명령을 안 내려보낸다. 헬퍼는 짧게 쉬고 다시 물어본다.
        return {"success": True, "approved": False, "jobs": []}

    wait = min(max(0.0, float(req.wait)), MAX_POLL_WAIT)
    jobs = await anyio.to_thread.run_sync(phone_jobs.pull_blocking, device_id, wait)
    dr.heartbeat(device_id)
    return {"success": True, "approved": True, "jobs": jobs}


@router.post("/limb/result")
async def limb_result(req: ResultRequest):
    """헬퍼가 셸 실행 결과를 회신 — 대기 중인 [limbs:guestpc] 포워드를 깨운다."""
    rec = limb_keys.validate(req.key)
    if not rec:
        return {"success": False, "error": "invalid_or_expired_key"}
    phone_jobs.set_result(req.job_id, req.result)
    return {"success": True}
