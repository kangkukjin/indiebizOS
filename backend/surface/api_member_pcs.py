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
        days = usage.get(rec["member_id"], {})
        used = days.get(today, {})
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
                     "tokens_total": sum(int(d.get("tokens", 0)) for d in days.values()),
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


@router.get("/{device_id}/activity")
def activity(device_id: str):
    from member_activity import recent
    from member_session import _base
    rec = _require(device_id)
    return {"tasks": recent(_base(), rec['member_id'])}


def _member_gear():
    import model_resolver as M
    from model_settings_view import AXIS_INFO
    return {"axis_info": AXIS_INFO, "current_gear": M.get_gear(), "gears": M.list_gears(),
            "presets": M.get_presets(), "tiers": M.TIERS, "axis_names": M.AXES,
            "consciousness_enabled": M.consciousness_enabled(),
            "axes": {axis: {k: v for k, v in M.resolve(role).items()
                            if k in ("tier", "provider", "model")}
                     for axis, role in zip(M.AXES, ("classify", "evaluate", "execution", "consciousness"))}}


@router.get("/models")
def get_models():
    import member_model_settings as settings
    from api_config_tiers import _with_provider_memory
    with settings.scope():
        return {"models": {tier: _with_provider_memory(config)
                           for tier, config in settings.load()['models'].items()}}


@router.put("/models")
def put_models(body: dict):
    import member_model_settings as settings
    import model_resolver as M
    from api_config_tiers import _MODEL_PROVIDERS
    models = body.get('models')
    if not isinstance(models, dict) or set(models) != set(M.TIERS):
        raise HTTPException(400, '경량·중급·고급 모델 설정이 필요합니다')
    for config in models.values():
        if not isinstance(config, dict) or config.get('provider') not in _MODEL_PROVIDERS:
            raise HTTPException(400, '지원하는 AI 제공자를 선택하세요')
        if not isinstance(config.get('model'), str) or not config['model'].strip():
            raise HTTPException(400, '모델 이름을 입력하세요')
        if config['provider'] == 'codex':
            raise HTTPException(400, 'Codex CLI는 아직 회원 작업 격리를 지원하지 않습니다')
    with settings.scope(), settings.lock:
        value = settings.load()
        value['models'] = {tier: M.merge_model_config(config, value['models'][tier], M.default_model_config(tier))
                           for tier, config in models.items()}
        settings.save(value)
        return get_models()


@router.get("/model-gear")
def get_member_gear():
    import member_model_settings as settings
    with settings.scope():
        return _member_gear()


@router.put("/model-gear")
def put_member_gear(body: dict):
    import member_model_settings as settings
    import model_resolver as M
    with settings.scope(), settings.lock:
        if not M.set_gear(body.get('gear')):
            raise HTTPException(400, '알 수 없는 기어입니다')
        return _member_gear()


@router.put("/model-gear/presets")
def put_member_presets(body: dict):
    import member_model_settings as settings
    import model_resolver as M
    with settings.scope(), settings.lock:
        presets = body.get('presets')
        if not isinstance(presets, dict) or any(set(v) != set(M.AXES) for v in presets.values() if isinstance(v, dict)):
            raise HTTPException(400, '각 기어의 네 가지 축을 모두 지정하세요')
        if not M.set_presets(presets):
            raise HTTPException(400, '올바른 기어 프리셋을 입력하세요')
        return _member_gear()


@router.put("/model-gear/consciousness")
def put_member_consciousness(body: dict):
    import member_model_settings as settings
    import model_resolver as M
    if not isinstance(body.get('enabled'), bool):
        raise HTTPException(400, 'enabled는 참 또는 거짓이어야 합니다')
    with settings.scope(), settings.lock:
        M.set_consciousness(body['enabled'])
        return _member_gear()


@router.get("/{device_id}/statistics")
def statistics(device_id: str, offset: int = 0):
    from datetime import date, timedelta
    from member_activity import recent
    from member_session import _base
    rec = _require(device_id)
    if offset < 0:
        raise HTTPException(400, 'offset은 0 이상이어야 합니다')
    today = date.today()
    start = today - timedelta(days=29)
    try:
        usage = json.loads((_base() / 'data/member_usage.json').read_text())
        days = usage.get(rec['member_id'], {})
        month = [v for day, v in days.items() if start.isoformat() <= day <= today.isoformat()]
        tokens = sum(int(v.get('tokens', 0)) for v in month)
        turns = sum(int(v.get('turns', 0)) for v in month)
    except FileNotFoundError:
        tokens = turns = 0
    except (OSError, ValueError, TypeError, AttributeError):
        raise HTTPException(503, '사용 현황을 읽지 못했습니다')
    tasks = recent(_base(), rec['member_id'], limit=51, offset=offset, device_id=device_id)
    return {'period_start': start.isoformat(), 'period_end': today.isoformat(),
            'tokens_month': tokens, 'turns_month': turns, 'tasks': tasks[:50],
            'next_offset': offset + 50 if len(tasks) > 50 else None}
