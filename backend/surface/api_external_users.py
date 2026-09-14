"""런처의 외부사용자 관리창. 주인이 직접 조작하는 HTTP 표면(IBL 등록 없음)."""
import json
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import limb_keys
import principal
from api_vocabulary import human_authority


def owner_access(request: Request, response: Response):
    if not principal.is_owner():
        raise HTTPException(403, "주인만 외부사용자를 관리할 수 있습니다")
    human_authority(request)
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/external-users", dependencies=[Depends(owner_access)])


def member_address():
    """/m/*를 서빙하는 직결 호스트를 우선한다. 미설정 주소는 추측하지 않는다."""
    from face_config import load_config
    cfg = load_config()
    base = (cfg.get("public_base") or "").rstrip("/")
    direct = [h for h in cfg.get("direct_hosts", []) if h]
    parsed = urlsplit(base)
    if parsed.scheme in {"http", "https"} and parsed.netloc in direct:
        return {"url": base + "/m/app", "warning": ""}
    if direct:
        return {"url": "https://" + direct[0] + "/m/app", "warning": ""}
    return {"url": "", "warning": "외부 접속 주소가 설정되지 않았습니다. 설정에서 터널의 직접 서빙 주소를 확인하세요."}


@router.get("")
def overview():
    from business_manager import BusinessManager
    from member_session import load_policy, _base
    from member_bridge import connected
    bm = BusinessManager()
    people = [{"id": n["id"], "name": n["name"], "level": int(n.get("info_level") or 0)}
              for n in bm.get_neighbors()]
    names = {str(n["id"]): n for n in people}
    try:
        usage = json.loads((_base() / "data" / "member_usage.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        usage = {}
    except (OSError, ValueError):
        raise HTTPException(503, "사용 현황을 읽지 못했습니다")
    day = time.strftime("%Y-%m-%d")
    policy = load_policy()
    rows = []
    for rec in limb_keys.list_keys():
        nid = rec.get("neighbor_id")
        if nid in (None, ""):
            continue
        person = names.get(str(nid))
        linked = bm.get_neighbor_by_contact("body", rec["device_id"])
        valid_link = bool(linked and str(linked["id"]) == str(nid))
        rows.append({**rec, "name": person["name"] if person else "삭제된 이웃",
                     "level": person["level"] if person else None,
                     "linked": valid_link, "connected": connected(rec["device_id"]),
                     "turns_today": (usage.get(str(nid), {}).get(day) or {}).get("turns", 0),
                     "daily_limit": policy.get("daily_turns_by_level", {}).get(
                         str(person["level"] if person else 0), policy["daily_turns"])})
    return {"address": member_address(), "people": people, "keys": rows,
            "daily_turns": policy["daily_turns"], "global_daily_turns": policy["global_daily_turns"],
            "notice": policy.get("notice", "")}


class PersonRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    level: int = Field(default=0, ge=0, le=4)


@router.post("/people")
def add_person(data: PersonRequest):
    from business_manager import BusinessManager
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "이름을 입력해 주세요")
    person = BusinessManager().create_neighbor(name=name, info_level=data.level)
    return {"id": person["id"], "name": person["name"], "level": person["info_level"]}


class IssueRequest(BaseModel):
    neighbor_id: int = Field(gt=0)
    alias: str = Field(default="", max_length=100)
    ttl_days: int = Field(default=0, ge=0, le=3650)


@router.post("/keys")
def issue_key(data: IssueRequest):
    from business_manager import BusinessManager
    from body_trust import link_body
    person = BusinessManager().get_neighbor(data.neighbor_id)
    if not person:
        raise HTTPException(404, "이웃을 찾을 수 없습니다")
    minted = limb_keys.mint(data.alias.strip() or person["name"], data.ttl_days, data.neighbor_id)
    try:
        linked = link_body(minted["device_id"], data.neighbor_id)
        if not linked.get("linked"):
            raise HTTPException(409, linked.get("error", "이웃 연결 실패"))
        # 설치 없는 웹 로그인은 첫 연결 전에도 회원 키를 검증한다.
        limb_keys.approve(minted["device_id"])
    except Exception:
        limb_keys.revoke(minted["device_id"])
        raise
    return {**minted, "name": person["name"], "address": member_address()}


@router.delete("/keys/{device_id}")
def revoke_key(device_id: str):
    rec = limb_keys.get_by_device(device_id)
    if not rec or rec.get("neighbor_id") in (None, ""):
        raise HTTPException(404, "외부사용자 키를 찾을 수 없습니다")
    limb_keys.revoke(device_id)
    return {"success": True}
