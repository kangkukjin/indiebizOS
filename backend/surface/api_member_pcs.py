"""회원 PC 등록 관리. 이웃 CRM·주인 원격 PC와 독립된 기기 자격을 관리한다."""
import json
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict

import device_registry
import limb_keys
from api_external_users import owner_access, member_address

router = APIRouter(prefix="/member-pcs", dependencies=[Depends(owner_access)])


class Registration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    user_label: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=1000)
    ttl_days: int = Field(default=0, ge=0, le=3650)


class Update(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    user_label: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=1000)
    enabled: bool | None = None


def _name(value):
    name = value.strip()
    if not name:
        raise HTTPException(400, "PC 이름을 입력해 주세요")
    return name


def _stop(device_id, member_id):
    # 관리자 조회 때문에 러너를 새로 초기화하지 않는다.
    from member_session import MemberSessionManager
    manager = MemberSessionManager._instance
    if manager:
        manager.close(member_id, device_id)


def _require(device_id):
    rec = limb_keys.get_by_device(device_id)
    if not rec or not rec.get("member_id") or not isinstance(rec.get("member_pc"), dict):
        raise HTTPException(404, "등록된 회원 PC를 찾을 수 없습니다")
    return rec


@router.get("")
def overview():
    from member_bridge import connected
    from member_session import load_policy, _base, MemberSessionManager
    try:
        usage = json.loads((_base() / "data" / "member_usage.json").read_text())
    except FileNotFoundError:
        usage = {}
    except (OSError, ValueError):
        raise HTTPException(503, "사용 현황을 읽지 못했습니다")
    policy = load_policy()
    today = time.strftime("%Y-%m-%d")
    rows = []
    manager = MemberSessionManager._instance
    for rec in limb_keys.list_keys():
        if not rec.get("member_id") or not isinstance(rec.get("member_pc"), dict):
            continue
        pc = rec["member_pc"]
        online = connected(rec["device_id"])
        presence = device_registry.get(rec["device_id"]) or {}
        used = usage.get(rec["member_id"], {}).get(today, {})
        if rec["revoked"]:
            state = "revoked"
        elif not pc.get("enabled", True):
            state = "disabled"
        elif rec["expired"]:
            state = "expired"
        elif online:
            state = "online"
        else:
            state = "offline" if rec["last_used"] else "pending"
        env = rec.get("env") or {}
        active = 0
        if manager:
            with manager.lock:
                active = manager.active.get(rec["member_id"], 0)
        # 환경 원문·키 힌트·작업 본문은 관리 목록에 싣지 않는다.
        rows.append({"device_id": rec["device_id"], "name": rec["alias"],
                     "user_label": pc.get("user_label", ""), "note": pc.get("note", ""),
                     "enabled": pc.get("enabled", True), "status": state,
                     "created_at": rec["created_at"], "expires_at": rec["expires_at"],
                     "last_seen": presence.get("last_seen") or rec["last_used"],
                     "host": rec["last_host"] or "", "os": str(env.get("os", "")),
                     "client_version": env.get("client_version", ""),
                     "client": "desktop" if env.get("client") == "desktop" else "web" if env.get("client") == "web" else "native" if rec["last_used"] else "",
                     "turns_today": used.get("turns", 0), "tokens_today": used.get("tokens", 0),
                     "active_tasks": active, "daily_limit": policy["daily_turns"]})
    return {"address": member_address(), "pcs": rows,
            "daily_limit": policy["daily_turns"], "global_daily_limit": policy["global_daily_turns"]}


@router.post("")
def register(req: Registration):
    issued = limb_keys.mint(_name(req.name), req.ttl_days, member_pc={
        "user_label": req.user_label.strip(), "note": req.note.strip()})
    return {**issued, "address": member_address()}


@router.patch("/{device_id}")
def update(device_id: str, req: Update):
    rec = _require(device_id)
    row = limb_keys.update_member_pc(device_id,
        alias=_name(req.name) if req.name is not None else None,
        user_label=req.user_label.strip() if req.user_label is not None else None,
        note=req.note.strip() if req.note is not None else None, enabled=req.enabled)
    if row is None:
        raise HTTPException(409, "해제한 등록은 변경할 수 없습니다")
    if req.enabled is not None:
        _stop(device_id, rec["member_id"])
    return {"success": True}


@router.post("/{device_id}/key")
def rotate(device_id: str):
    rec = _require(device_id)
    row = limb_keys.update_member_pc(device_id, rotate_key=True)
    if row is None:
        raise HTTPException(409, "해제한 PC는 새로 등록해 주세요")
    _stop(device_id, rec["member_id"])
    return {"key": row["key"], "device_id": device_id, "alias": row["alias"],
            "expires_at": row["expires_at"], "address": member_address()}


@router.delete("/{device_id}")
def unregister(device_id: str):
    rec = _require(device_id)
    limb_keys.update_member_pc(device_id, revoke_key=True)
    _stop(device_id, rec["member_id"])
    return {"success": True}


@router.post("/{device_id}/invite")
def invite(device_id: str):
    from member_enrollment import issue
    from urllib.parse import urlencode, urlsplit
    _require(device_id)
    try:
        result = issue(device_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    address = member_address()
    parsed = urlsplit(address["url"])
    hub = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else ""
    return {**result, "address": address, "hub": hub,
            "link": "indiebiz-member://enroll?" + urlencode({"hub": hub, "code": result["code"]})}
