"""
business/handler.py
비즈니스 관계 및 연락처(이웃) 관리 도구
"""

import sys
import json
from pathlib import Path

from common.currency import items  # IBL 단일 통화 생성자


# === messages_op: 메신저 (op 분기 — build --check 삼각 검증 대상) ===

def _parse_dt(s: str):
    """ISO 8601 또는 RFC 2822(이메일 Date) 문자열 → datetime (실패 시 None)."""
    if not s:
        return None
    s = str(s).strip()
    from datetime import datetime
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s)
    except Exception:
        return None


def _short_time(iso: str) -> str:
    """타임스탬프 → 'MM/DD HH:MM' 짧은 표시 (파싱 실패 시 앞 16자)."""
    if not iso:
        return ""
    dt = _parse_dt(iso)
    return dt.strftime("%m/%d %H:%M") if dt else str(iso)[:16]


def _epoch(s: str) -> float:
    """정렬용 epoch (파싱 실패 시 0). tz-aware/naive 혼재 안전."""
    dt = _parse_dt(s)
    if not dt:
        return 0.0
    try:
        return dt.timestamp()
    except Exception:
        return 0.0


def _primary_channel(bm, neighbor_id: int) -> str:
    """이웃의 기본 메시징 채널(gmail/nostr) — 연락처에서 추론, 없으면 nostr."""
    try:
        for c in bm.get_contacts(neighbor_id):
            if c.get("contact_type") in ("gmail", "nostr"):
                return c["contact_type"]
    except Exception:
        pass
    return "nostr"


# --- IndieNet Nostr DM 통합 (dms.db 캐시 — 비이웃 npub도 메신저에 표시) ---

def _indienet():
    """IndieNet 싱글톤 (초기화됐을 때만). 미초기화/실패 시 None — 메신저는 business.db만으로도 동작."""
    try:
        from indienet import get_indienet
        ind = get_indienet()
        return ind if ind.is_initialized() else None
    except Exception:
        return None


def _hex_to_npub(h: str) -> str:
    try:
        from pynostr.key import PublicKey
        return PublicKey(bytes.fromhex(h)).bech32()
    except Exception:
        return h or ""


def _npub_to_hex(n: str) -> str:
    if not n:
        return ""
    try:
        from pynostr.key import PublicKey
        return PublicKey.from_npub(n).hex() if n.startswith("npub") else n
    except Exception:
        return n


def _short_npub(n: str) -> str:
    return (n[:12] + "…") if n and n.startswith("npub") and len(n) > 13 else (n or "")


def _fmt_unix(ts) -> str:
    try:
        from datetime import datetime
        return datetime.fromtimestamp(int(ts)).strftime("%m/%d %H:%M")
    except Exception:
        return ""


def _badge(is_nb, level, rating) -> str:
    """대화/이웃 배지 — 이웃이면 'L{레벨}'(+평점), DM이면 '쪽지'. (이웃관리 창의 레벨 태그처럼 항상 표시)"""
    if not is_nb:
        return "쪽지"
    s = "L" + str(_int_or(level, 0))
    if _int_or(rating, 0):
        s += " ★" + str(_int_or(rating, 0))
    return s


def _is_phone_feed(content: str) -> bool:
    """폰 컴패니언 텔레메트리 피드(알림/위치/걸음 NIP-17 DM)인지 — 인간 대화가 아니므로 메신저에서 제외.
    (이 신호는 sense:phone 파이프라인이 소비한다.)"""
    c = (content or "").lstrip()
    if not c.startswith("{"):
        return False
    try:
        obj = json.loads(c)
    except Exception:
        return False
    return isinstance(obj, dict) and obj.get("type") in ("notification", "location", "steps", "phone_notification")


def _msg_thread(bm, tool_input: dict) -> str:
    """한 대화의 메시지 스레드 — business.db(이웃, 양방향) + dms.db(Nostr DM) 통합, 시간 오름차순.

    neighbor_id 가 있으면 그 이웃의 다채널 메시지 + (nostr 주소가 있으면) dms.db 병합.
    pubkey(비이웃 npub) 면 dms.db 만으로 스레드 구성. 두 소스는 Nostr 이벤트 id 로 dedupe.
    """
    neighbor_id = tool_input.get("neighbor_id")
    pubkey = tool_input.get("pubkey") or ""
    has_neighbor = bool(neighbor_id) and str(neighbor_id) not in ("0", "")
    if not has_neighbor and not pubkey:
        return json.dumps({"success": False, "message": "neighbor_id 또는 pubkey가 필요합니다."}, ensure_ascii=False)

    items, seen_eids = [], set()
    name, channel, to = "", "nostr", ""
    target_hex = None
    nb = {}  # 이웃 메타(레벨/평점/즐겨찾기/정보) — 헤더·정보 탭용
    contacts = []  # 이웃 연락처 목록 — 정보 탭 editable_list용

    if has_neighbor:
        neighbor_id = int(neighbor_id)
        nb = bm.get_neighbor(neighbor_id) or {}
        name = nb.get("name", "")
        channel = _primary_channel(bm, neighbor_id)
        contacts = [{"id": c.get("id"), "contact_type": c.get("contact_type", ""),
                     "contact_value": c.get("contact_value", "")} for c in (bm.get_contacts(neighbor_id) or [])]
        for m in reversed(bm.get_messages(neighbor_id=neighbor_id, limit=200)):  # DESC→오름차순
            eid = m.get("external_id")
            if eid:
                seen_eids.add(eid)
            tv = m.get("message_time") or m.get("created_at")
            items.append({"content": m.get("content", ""), "is_from_user": m.get("is_from_user", 0),
                          "contact_type": m.get("contact_type", ""), "time": _short_time(tv), "_ts": _epoch(tv),
                          "status": m.get("status") or "received", "processed": m.get("processed", 0),
                          "replied": m.get("replied", 0), "subject": m.get("subject") or "",
                          "sent_at": m.get("sent_at") or "", "attachment_path": m.get("attachment_path") or ""})
            if not to:
                to = m.get("contact_value") or ""
        for c in (bm.get_contacts(neighbor_id) or []):
            if c.get("contact_type") == "nostr" and c.get("contact_value"):
                target_hex = _npub_to_hex(c["contact_value"]); break
        if not target_hex and channel == "nostr" and to:
            target_hex = _npub_to_hex(to)
    else:
        name = _short_npub(pubkey)
        to = pubkey
        channel = "nostr"
        target_hex = _npub_to_hex(pubkey)

    # dms.db 병합 (이 대화의 nostr 상대 hex 로 필터, 캐시 직접 — 릴레이 안 침)
    following_label = ""
    if target_hex:
        ind = _indienet()
        if ind:
            try:
                # 승격 다리 역방향 표시 — 이 상대를 IndieNet에서 팔로우 중인지
                if any(_npub_to_hex(f.get("pubkey", "")) == target_hex
                       for f in (ind.get_follows() or [])):
                    following_label = "팔로우 중"
            except Exception:
                pass
            try:
                my_hex = ind.identity.public_key.hex()
                for d in ind._get_cached_dms(limit=500):
                    if d.get("from") != target_hex or d.get("id") in seen_eids:
                        continue
                    if _is_phone_feed(d.get("content", "")):
                        continue  # 폰 텔레메트리 제외
                    ts = d.get("created_at") or 0
                    items.append({"content": d.get("content", ""),
                                  "is_from_user": 1 if d.get("from") == my_hex else 0,
                                  "contact_type": "nostr", "time": _fmt_unix(ts), "_ts": float(ts),
                                  "status": "received", "processed": 0, "replied": 0,
                                  "subject": "", "sent_at": "", "attachment_path": ""})
            except Exception:
                pass

    items.sort(key=lambda x: x["_ts"])
    for it in items:
        it.pop("_ts", None)
    # 단일 통화 items = native 메시지 dict(content/is_from_user/time/status…). thread 뷰 직독.
    # contacts(연락처)는 정보 탭 editable_list용 보조 컬렉션 — items와 공존(주=스레드).
    return json.dumps({
        "name": name, "channel": channel or "nostr", "to": to,
        "items": items,
        "neighbor_id": (nb.get("id") if nb else (0 if not has_neighbor else neighbor_id)),
        "info_level": nb.get("info_level", 0) if nb else 0,
        "rating": nb.get("rating", 0) if nb else 0,
        "favorite": nb.get("favorite", 0) if nb else 0,
        "info_share": nb.get("info_share", 0) if nb else 0,
        "additional_info": nb.get("additional_info") or "" if nb else "",
        "business_doc": nb.get("business_doc") or "" if nb else "",
        "is_neighbor": bool(nb),
        "badge": _badge(bool(nb), nb.get("info_level", 0) if nb else 0, nb.get("rating", 0) if nb else 0),
        "contacts": contacts,
        "following_label": following_label,  # IndieNet 팔로우 여부 (승격 다리 역방향 표시)
        "message": "" if items else "주고받은 메시지가 없습니다.",
    }, ensure_ascii=False)


def _msg_inbox(bm, tool_input: dict) -> str:
    """대화 목록 — business.db(다채널 이웃) + dms.db(IndieNet Nostr DM) 통합, 최근순.

    이웃 대화로 이미 잡힌 nostr 상대는 중복 제외. 비이웃 DM 상대는 npub 를 키로 별도 대화 행.
    """
    convs = []
    biz_nostr_hex = set()  # 이미 이웃 대화로 잡힌 nostr 상대 hex (중복 방지)
    # 필터: level(정보 공개 수준), search(이름 부분 일치). level 지정 시 비이웃 DM은 제외(레벨 없음).
    search = (tool_input.get("search") or "").strip() or None
    _lv = tool_input.get("level")
    level_int = _int_or(_lv) if (_lv not in (None, "", "all", "전체")) else None
    # 이웃관리 모델: 메시지 없는 이웃도 포함(연락처/정보 관리 위해). 대화 있으면 미리보기·최근순.
    # ★이웃당 개별 쿼리(마지막 메시지·미답신·연락처) 금지 — 이웃 수백 명이면 그 시간만큼
    #   이벤트 루프가 멈춘다. get_inbox_summary 가 연결 1개·집계 쿼리로 한 번에 준다.
    for n in bm.get_inbox_summary(search=search, info_level=level_int):
        last = n.pop("_last", None)
        unread = n.pop("_unread", 0)
        ch_contacts = n.pop("_channel_contacts", [])
        primary = ch_contacts[0][0] if ch_contacts else "nostr"  # 구 _primary_channel 과 동일
        if last:
            ct = last.get("contact_type", "")
            channel = ct if ct in ("gmail", "nostr") else primary
            to = last.get("contact_value") or ""
            preview = (last.get("content", "") or "")[:40]
            ts = last.get("message_time") or last.get("created_at") or ""
            sort, time_s = _epoch(ts), _short_time(ts)
        else:
            channel = primary
            to = next((v for (t, v) in ch_contacts if v), "")
            preview, time_s, sort, unread = "", "", 0.0, 0
        if channel == "nostr" and to:
            biz_nostr_hex.add(_npub_to_hex(to))
        peer = _int_or(n.get("is_indiebiz_peer", 0), 0)
        convs.append({
            "id": n["id"], "pubkey": "", "name": n.get("name", ""), "channel": channel,
            "to": to, "preview": preview, "time": time_s, "unread": unread, "_sort": sort,
            "info_level": n.get("info_level", 0), "rating": n.get("rating", 0),
            "favorite": n.get("favorite", 0), "is_neighbor": 1,
            "is_indiebiz_peer": peer, "peer_version": n.get("peer_version") or "",
            "badge": ("🤖 " if peer else "") + _badge(1, n.get("info_level", 0), n.get("rating", 0)),
        })

    # dms.db: 이웃으로 안 잡힌 Nostr DM 상대를 대화로 추가 (캐시 직접 — 릴레이 안 침).
    # level 필터 지정 시 DM은 제외(레벨 개념 없음).
    ind = _indienet() if level_int is None else None
    if ind:
        try:
            groups = {}
            for d in ind._get_cached_dms(limit=500):
                h = d.get("from", "")
                if not h or h in biz_nostr_hex:
                    continue
                if _is_phone_feed(d.get("content", "")):
                    continue  # 폰 텔레메트리(알림/위치/걸음)는 메신저 대화 아님
                g = groups.setdefault(h, {"last": None})
                if g["last"] is None or (d.get("created_at") or 0) > (g["last"].get("created_at") or 0):
                    g["last"] = d
            for h, g in groups.items():
                npub = _hex_to_npub(h)
                if search and search.lower() not in npub.lower():
                    continue  # 검색어가 있으면 npub 매칭만
                last = g["last"]; ts = last.get("created_at") or 0
                convs.append({
                    "id": 0, "pubkey": npub, "name": _short_npub(npub), "channel": "nostr",
                    "to": npub, "preview": (last.get("content", "") or "")[:40],
                    "time": _fmt_unix(ts), "unread": 0, "_sort": float(ts),
                    "info_level": 0, "rating": 0, "favorite": 0, "is_neighbor": 0,
                    "badge": "쪽지",
                })
        except Exception:
            pass

    convs.sort(key=lambda c: (c.get("favorite", 0), c["_sort"]), reverse=True)  # 즐겨찾기 먼저, 그다음 최근순
    for c in convs:
        c.pop("_sort", None)
    # 단일 통화 items = native 대화 dict(id/name/channel/preview/unread/badge…). card_list 직독.
    return json.dumps({"items": convs,
                       "message": "" if convs else "대화가 없습니다."}, ensure_ascii=False)


# === 이웃/연락처 CRUD (neighbor_op / contact_op) ===

def _ok(payload: dict, message: str = "") -> str:
    return json.dumps({"success": True, "message": message, **payload}, ensure_ascii=False)


def _err(message: str) -> str:
    return json.dumps({"success": False, "message": message}, ensure_ascii=False)


def _int_or(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


def _nb_save(bm, ti: dict) -> str:
    """이웃 생성(id 없음)/수정(id 있음) — 이름·정보레벨·평점·정보공유·메모·비즈니스문서.

    npub 옵션: nostr 연락처를 함께 연결(IndieNet 팔로우→이웃 승격 다리). 같은 npub 이
    이미 이웃이면 새로 만들지 않고 그 이웃을 반환(멱등 — 승격 버튼 중복 클릭 안전)."""
    nid = _int_or(ti.get("id") or ti.get("neighbor_id"))
    npub = (ti.get("npub") or "").strip()
    fields = {}
    for k in ("name", "additional_info", "business_doc"):
        if ti.get(k) is not None:
            fields[k] = ti.get(k)
    for k in ("info_level", "rating", "info_share"):
        if ti.get(k) is not None:
            fields[k] = _int_or(ti.get(k), 0)
    if nid:
        nb = bm.update_neighbor(nid, **fields)
        if npub:
            _ensure_nostr_contact(bm, nid, npub)
        return _ok({"neighbor": nb}, "이웃 정보를 저장했습니다.")
    # 승격 멱등 가드 — 같은 npub 이 이미 이웃이면 그대로 반환
    if npub:
        existing = bm.find_neighbor_by_contact("nostr", npub)
        if existing:
            return _ok({"neighbor": existing}, f"이미 이웃입니다: {existing.get('name', '')}")
    name = fields.pop("name", None)
    if not name:
        return _err("이름(name)이 필요합니다.")
    nb = bm.create_neighbor(name=name, **fields)
    if npub:
        _ensure_nostr_contact(bm, nb["id"], npub)
        return _ok({"neighbor": nb}, "이웃으로 등록하고 nostr 연락처를 연결했습니다.")
    return _ok({"neighbor": nb}, "이웃을 추가했습니다.")


def _ensure_nostr_contact(bm, neighbor_id: int, npub: str):
    """이웃에 nostr 연락처가 없으면 추가 (있으면 그대로 — 중복 방지)."""
    try:
        for c in bm.get_contacts(neighbor_id) or []:
            if c.get("contact_type") == "nostr" and c.get("contact_value") == npub:
                return
        bm.add_contact(neighbor_id, "nostr", npub)
    except Exception:
        pass


def _nb_delete(bm, ti: dict) -> str:
    nid = _int_or(ti.get("id") or ti.get("neighbor_id"))
    if not nid:
        return _err("id(neighbor_id)가 필요합니다.")
    bm.delete_neighbor(nid)
    return _ok({"deleted": nid}, "이웃을 삭제했습니다.")


def _nb_favorite(bm, ti: dict) -> str:
    """즐겨찾기 토글."""
    nid = _int_or(ti.get("id") or ti.get("neighbor_id"))
    if not nid:
        return _err("id(neighbor_id)가 필요합니다.")
    cur = (bm.get_neighbor(nid) or {}).get("favorite", 0)
    new = 0 if cur else 1
    bm.update_neighbor(nid, favorite=new)
    return _ok({"id": nid, "favorite": new}, "")


def _nb_list(bm, ti: dict) -> str:
    """이웃 목록 (search 부분일치 / info_level 0-4 필터)."""
    neighbors = bm.get_neighbors(search=ti.get("search"), info_level=ti.get("info_level"))
    # 단일 통화 items = native 이웃 dict(id/name/info_level/rating/favorite…).
    return _ok({"items": neighbors}, f"이웃 {len(neighbors)}명")


def _nb_detail(bm, ti: dict) -> str:
    """이웃 상세 (neighbor_id 또는 name) — 연락처·최근 메시지 5건 포함."""
    nid = _int_or(ti.get("id") or ti.get("neighbor_id"))
    name = ti.get("name")
    if not nid and name:
        ex = [n for n in bm.get_neighbors(search=name) if n["name"] == name]
        if not ex:
            return _err(f"'{name}' 이름의 이웃을 찾을 수 없습니다.")
        nid = ex[0]["id"]
    if not nid:
        return _err("neighbor_id 또는 name 중 하나가 필요합니다.")
    nb = bm.get_neighbor(nid)
    if not nb:
        return _err(f"ID {nid}의 이웃을 찾을 수 없습니다.")
    # items = 최근 메시지(주 컬렉션), contacts·neighbor는 보조(thread 선례).
    return _ok({"neighbor": nb, "contacts": bm.get_contacts(nid),
                "items": bm.get_messages(neighbor_id=nid, limit=5)}, nb.get("name", ""))


def _ct_add(bm, ti: dict) -> str:
    nid = _int_or(ti.get("neighbor_id"))
    ct, cv = ti.get("contact_type"), ti.get("contact_value")
    if not nid or not ct or not cv:
        return _err("neighbor_id·contact_type·contact_value가 필요합니다.")
    c = bm.add_contact(nid, ct, cv)
    return _ok({"contact": c}, "연락처를 추가했습니다.")


def _ct_update(bm, ti: dict) -> str:
    cid = _int_or(ti.get("contact_id") or ti.get("id"))
    if not cid:
        return _err("contact_id가 필요합니다.")
    c = bm.update_contact(cid, contact_type=ti.get("contact_type"), contact_value=ti.get("contact_value"))
    return _ok({"contact": c}, "연락처를 수정했습니다.")


def _ct_delete(bm, ti: dict) -> str:
    cid = _int_or(ti.get("contact_id") or ti.get("id"))
    if not cid:
        return _err("contact_id가 필요합니다.")
    bm.delete_contact(cid)
    return _ok({"deleted": cid}, "연락처를 삭제했습니다.")


# === 비즈니스 엔티티 CRUD (business_op / business_item_op / business_document_op / work_guideline_op) ===
# 나의 사업·상품·레벨별 공개 문서·근무 지침. 옛 비즈니스 창(REST)을 IBL 어휘로 흡수.

def _biz_list(bm, ti: dict) -> str:
    """비즈니스 목록 — level/search 필터(전체=필터 없음)."""
    lv = ti.get("level")
    level = _int_or(lv) if lv not in (None, "", "all", "전체") else None
    search = (ti.get("search") or "").strip() or None
    businesses = bm.get_businesses(level=level, search=search)
    # 단일 통화 items = native 비즈니스 dict(name/id/level/description). card_list·셀렉터가 직독.
    return _ok(items(businesses))


def _biz_detail(bm, ti: dict) -> str:
    """비즈니스 단건 상세 + 소속 아이템."""
    bid = _int_or(ti.get("id") or ti.get("business_id"))
    if not bid:
        return _err("id(business_id)가 필요합니다.")
    b = bm.get_business(bid)
    if not b:
        return _err("비즈니스를 찾을 수 없습니다.")
    return _ok({"business": b, "items": bm.get_business_items(bid)})


def _biz_save(bm, ti: dict) -> str:
    """비즈니스 생성(id 없음)/수정(id 있음) — name·level(0-4)·description."""
    bid = _int_or(ti.get("id") or ti.get("business_id"))
    if bid:
        fields = {}
        for k in ("name", "description"):
            if ti.get(k) is not None:
                fields[k] = ti.get(k)
        if ti.get("level") is not None:
            fields["level"] = _int_or(ti.get("level"), 0)
        b = bm.update_business(bid, **fields)
        return _ok({"business": b}, "비즈니스를 저장했습니다.")
    name = ti.get("name")
    if not name:
        return _err("이름(name)이 필요합니다.")
    b = bm.create_business(name=name, level=_int_or(ti.get("level"), 0), description=ti.get("description"))
    return _ok({"business": b}, "비즈니스를 추가했습니다.")


def _biz_delete(bm, ti: dict) -> str:
    bid = _int_or(ti.get("id") or ti.get("business_id"))
    if not bid:
        return _err("id(business_id)가 필요합니다.")
    bm.delete_business(bid)
    return _ok({"deleted": bid}, "비즈니스를 삭제했습니다.")


def _item_list(bm, ti: dict) -> str:
    """한 비즈니스의 아이템(상품/항목) 목록. business_id 미지정 시 빈 목록(계기 셀렉터 미선택 대비)."""
    bid = _int_or(ti.get("business_id"))
    if not bid:
        return _ok({"items": [], "business_id": None})
    items = bm.get_business_items(bid)
    # 단일 통화 items = native 아이템 dict(title/details/id). editable_list 직독.
    return _ok({"items": items, "business_id": bid})


def _item_detail(bm, ti: dict) -> str:
    iid = _int_or(ti.get("id") or ti.get("item_id"))
    if not iid:
        return _err("item_id가 필요합니다.")
    it = bm.get_business_item(iid)
    if not it:
        return _err("아이템을 찾을 수 없습니다.")
    return _ok({"item": it})


def _item_save(bm, ti: dict) -> str:
    """아이템 생성(id 없음·business_id+title 필수)/수정(id 있음) — title·details·attachment_path."""
    iid = _int_or(ti.get("id") or ti.get("item_id"))
    if iid:
        fields = {}
        for k in ("title", "details", "attachment_path"):
            if ti.get(k) is not None:
                fields[k] = ti.get(k)
        it = bm.update_business_item(iid, **fields)
        return _ok({"item": it}, "아이템을 저장했습니다.")
    bid = _int_or(ti.get("business_id"))
    title = ti.get("title")
    if not bid or not title:
        return _err("business_id·title이 필요합니다.")
    it = bm.create_business_item(business_id=bid, title=title,
                                 details=ti.get("details"), attachment_path=ti.get("attachment_path"))
    return _ok({"item": it}, "아이템을 추가했습니다.")


def _item_delete(bm, ti: dict) -> str:
    iid = _int_or(ti.get("id") or ti.get("item_id"))
    if not iid:
        return _err("item_id가 필요합니다.")
    bm.delete_business_item(iid)
    return _ok({"deleted": iid}, "아이템을 삭제했습니다.")


# 아이템 첨부 이미지 — attachment_path 는 복사된 경로의 JSON 배열(레거시: 단일 문자열).
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _images_dir():
    from runtime_utils import get_base_path
    d = get_base_path() / "data" / "business_images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _item_paths(it) -> list:
    raw = (it or {}).get("attachment_path") or ""
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else [raw]
    except Exception:
        return [raw]


def _item_add_image(bm, ti: dict) -> str:
    """소스 이미지 파일을 business_images 로 복사하고 아이템 attachment_path(JSON 배열)에 추가.
    path 는 데스크탑 파일선택(window.electron.selectImages)에서 온 로컬 경로 — 백엔드 같은 머신."""
    import shutil
    from pathlib import Path as _P
    from datetime import datetime as _dt
    iid = _int_or(ti.get("id") or ti.get("item_id"))
    src = ti.get("path") or ti.get("source")
    if not iid or not src:
        return _err("item_id·path가 필요합니다.")
    it = bm.get_business_item(iid)
    if not it:
        return _err("아이템을 찾을 수 없습니다.")
    sp = _P(src)
    if not sp.exists() or not sp.is_file() or sp.suffix.lower() not in _IMG_EXTS:
        return _err("이미지 파일이 아니거나 찾을 수 없습니다.")
    dest = _images_dir() / (_dt.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + sp.name.replace(" ", "_"))
    shutil.copy2(str(sp), str(dest))
    paths = _item_paths(it) + [str(dest)]
    bm.update_business_item(iid, attachment_path=json.dumps(paths, ensure_ascii=False))
    return _ok({"item": bm.get_business_item(iid)}, "이미지를 추가했습니다.")


def _item_remove_image(bm, ti: dict) -> str:
    """아이템 attachment_path 에서 path 제거 + business_images 안의 파일이면 삭제."""
    from pathlib import Path as _P
    iid = _int_or(ti.get("id") or ti.get("item_id"))
    path = ti.get("path")
    if not iid or not path:
        return _err("item_id·path가 필요합니다.")
    it = bm.get_business_item(iid)
    if not it:
        return _err("아이템을 찾을 수 없습니다.")
    paths = [p for p in _item_paths(it) if p != path]
    bm.update_business_item(iid, attachment_path=json.dumps(paths, ensure_ascii=False))
    try:
        fp = _P(path)
        if fp.exists() and "business_images" in str(fp):
            fp.unlink()
    except Exception:
        pass
    return _ok({"item": bm.get_business_item(iid)}, "이미지를 제거했습니다.")


def _doc_list(bm, ti: dict) -> str:
    """레벨별 공개 비즈니스 문서 전체(레벨 0-4)."""
    docs = bm.get_all_business_documents()
    return _ok({"items": docs})


def _doc_detail(bm, ti: dict) -> str:
    lvl = _int_or(ti.get("level"))
    if lvl is None:
        return _err("level이 필요합니다.")
    d = bm.get_business_document(lvl)
    if not d:
        return _err("문서를 찾을 수 없습니다.")
    return _ok({"document": d})


def _doc_update(bm, ti: dict) -> str:
    lvl = _int_or(ti.get("level"))
    if lvl is None:
        return _err("level이 필요합니다.")
    d = bm.update_business_document(lvl, title=ti.get("title") or "", content=ti.get("content") or "")
    return _ok({"document": d}, "비즈니스 문서를 저장했습니다.")


def _doc_regenerate(bm, ti: dict) -> str:
    """비즈니스 목록·아이템 기반으로 레벨별 공개 문서를 자동 재생성."""
    r = bm.regenerate_business_documents()
    if (r or {}).get("status") == "success":
        docs = bm.get_all_business_documents()
        return _ok({"items": docs}, r.get("message") or "문서를 재생성했습니다.")
    return _err((r or {}).get("message") or "문서 재생성에 실패했습니다.")


def _public_base() -> str:
    """공개 창고(Worker) base URL — 공개파일(showcase) 설정과 같은 소스.
    설치본마다 다르므로 하드코딩 금지·변수로 읽는다(하부/상부 이음매). 미설정 시 빈 문자열."""
    try:
        p = Path(__file__).resolve().parents[4] / "showcase_state.json"
        sc = json.loads(p.read_text(encoding="utf-8"))
        return ((sc.get("settings") or {}).get("public_base") or "").rstrip("/")
    except Exception:
        return ""


def _doc_publish(bm, ti: dict) -> str:
    """공개인사프로필(kind:0, website=공개창고 주소) + 발견 노트(kind:1 #IndieNet)를 Nostr 발행.
    사용자가 쓴 공개인사프로필만 verbatim 발행 — 데이터 수집·합성 없음. *상세 내용은 Nostr에 안 싣고
    공개 창고가 쥔다*(kind:0=항상 켜진 명함, kind:1=발견 메시지, 둘 다 창고 주소를 가리킴).
    낯선 사람이 #IndieNet 으로 나를 찾고 → 창고에서 내 소개를 읽는다."""
    from business_manager import GREETING_DOC_LEVEL
    ind = _indienet()
    if not ind:
        return _err("IndieNet(Nostr) 미초기화 — 먼저 계정을 설정하세요.")
    greeting = ((bm.get_business_document(GREETING_DOC_LEVEL) or {}).get("content") or "").strip()
    if not greeting:
        return _err("공개할 내용이 없습니다. 공개문서의 '공개인사프로필'을 먼저 작성하세요.")
    name = ""
    try:
        name = (ind.identity.display_name or "").strip()
    except Exception:
        pass
    base = _public_base()
    home = (base + "/") if base else ""   # 공개 창고 홈(안정 주소). 방문자=레벨0, npub 로그인으로 승급.
    published = {}
    # 1) 공개인사프로필 → kind:0 (자기소개 명함). 창고 주소는 표준 website 필드에(항상 켜진 카드).
    pid = ind.publish_profile(about=greeting, name=name,
                              extra=({"website": home} if home else None))
    if pid:
        published["profile"] = pid
    # 2) 발견 노트 → kind:1 #IndieNet (망으로 보내는 소개 메시지). npub(서명)+창고 주소를 실어 검색으로 발견됨.
    iid = ind.publish_intro(text=greeting, website=home)
    if iid:
        published["intro"] = iid
    if not published:
        return _err("발행에 실패했습니다 (릴레이 응답 없음).")
    npub = ""
    try:
        npub = ind.identity.npub or ""
    except Exception:
        pass
    link = home or (f"https://njump.me/{npub}" if npub else "")   # 착지점=창고 홈(설정 시), 미설정 시 njump 폴백
    msg = "공개 발행 완료 (#IndieNet 발견 노트 포함)" + (f" — {link}" if link else "")
    return _ok({"published": published, "npub": npub, "home": home}, msg)


def _guide_list(bm, ti: dict) -> str:
    """레벨별 근무 지침 전체(레벨 0-4).

    단일 통화: native 지침 dict(level/title/content 등 풍부 필드)를 그대로 `items`로 낸다.
    옛 records-관습 변환(_to_records)은 *손실적*(level 필드를 버려 카드 `{level}`이 깨짐)이라
    은퇴. 카드는 native 필드를 그대로 읽고, derive_items는 items 존재 시 무동작.
    """
    return _ok({"items": bm.get_all_work_guidelines()})


def _guide_detail(bm, ti: dict) -> str:
    lvl = _int_or(ti.get("level"))
    if lvl is None:
        return _err("level이 필요합니다.")
    g = bm.get_work_guideline(lvl)
    if not g:
        return _err("지침을 찾을 수 없습니다.")
    return _ok({"guideline": g})


def _guide_update(bm, ti: dict) -> str:
    lvl = _int_or(ti.get("level"))
    if lvl is None:
        return _err("level이 필요합니다.")
    g = bm.update_work_guideline(lvl, title=ti.get("title") or "", content=ti.get("content") or "")
    return _ok({"guideline": g}, "근무 지침을 저장했습니다.")


# === 자동응답 서비스 제어 (auto_response_op) ===
# 외부 메시지 자동응답 on/off·상태. on/off 는 영속(재시작에도 사용자 의사 유지).

def _auto_response_service():
    from auto_response import get_auto_response_service
    return get_auto_response_service()


def _ar_status(bm, ti: dict) -> str:
    svc = _auto_response_service()
    running = bool(svc._running)
    interval = getattr(svc, "_check_interval", None)
    return _ok({
        "running": running,
        "enabled": svc.is_enabled(),
        "check_interval": interval,
        "processed_count": len(getattr(svc, "_processed_messages", {})),
        # 표시용(불리언→한글). 계기 kv 가 그대로 보여줌.
        "state_label": "● 켜짐" if running else "○ 꺼짐",
        "interval_label": (f"{interval}초마다 점검" if interval else ""),
        "summary": ("외부 메시지에 자동으로 응답합니다." if running
                    else "자동응답이 꺼져 있습니다."),
    })


def _ar_start(bm, ti: dict) -> str:
    svc = _auto_response_service()
    svc.enable()
    return _ok({"running": bool(svc._running), "enabled": True}, "자동응답을 켰습니다.")


def _ar_stop(bm, ti: dict) -> str:
    svc = _auto_response_service()
    svc.disable()
    return _ok({"running": bool(svc._running), "enabled": False}, "자동응답을 껐습니다.")


# 디스패처 표(빌드 --check 가 AST 로 키를 src.ops.values 와 정확 비교)
def _phone_sync(bm, ti: dict) -> str:
    """폰↔맥 business.db 합집합 동기화 (맥 주도, adb USB 경유, 양방향 1회).
    폰 export→맥 머지 + 맥 export→폰 머지. 폰 앱 미기동 시 자동 기동 시도.
    자동응답=PC전용·내용=릴레이수렴이라 머지 대상은 주소록 메타데이터(이웃·연락처·사업·아이템·문서·지침)뿐."""
    import subprocess
    import time as _t
    import httpx as _hx
    from business_sync import export_business_db, merge_business_db
    PHONE_PKG = "com.indiebiz.phoneagent"
    PORT = 8799
    BASE = f"http://127.0.0.1:{PORT}"

    def _adb(*a, timeout=20):
        try:
            return subprocess.run(["adb", *a], capture_output=True, text=True, timeout=timeout)
        except Exception:
            return None

    dev = _adb("devices")
    if dev is None:
        return json.dumps({"success": False, "message": "adb 실행 실패 — Android 플랫폼툴이 필요합니다."}, ensure_ascii=False)
    connected = [l for l in dev.stdout.splitlines()[1:] if l.strip() and l.strip().endswith("device")]
    if not connected:
        return json.dumps({"success": False, "message": "폰이 USB로 연결돼 있지 않습니다. 케이블을 연결한 뒤 다시 시도하세요."}, ensure_ascii=False)

    _adb("forward", f"tcp:{PORT}", "tcp:8765")
    try:
        def _up():
            try:
                return _hx.get(f"{BASE}/launcher/instruments", timeout=3).status_code == 200
            except Exception:
                return False

        if not _up():
            # 폰 앱(백엔드) 미기동 → 자동 기동 후 대기
            _adb("shell", "am", "start", "-n", f"{PHONE_PKG}/.MainActivity")
            for _ in range(20):
                _t.sleep(1.5)
                if _up():
                    break
            if not _up():
                return json.dumps({"success": False, "message": "폰 앱 백엔드가 기동되지 않았습니다. 폰 잠금을 풀고 IndieBiz 앱을 한 번 열어주세요."}, ensure_ascii=False)

        # 폰 export → 맥 머지
        pe = _hx.get(f"{BASE}/business/sync/export", timeout=30).json()
        if not pe.get("success"):
            return json.dumps({"success": False, "message": f"폰 export 실패: {pe.get('error')}"}, ensure_ascii=False)
        from_phone = merge_business_db(bm, pe.get("data") or {})

        # 맥 export → 폰 머지
        me = export_business_db(bm)
        r = _hx.post(f"{BASE}/business/sync/merge", json={"data": me}, timeout=30).json()
        to_phone = r.get("stats") if r.get("success") else None

        def _s(stats, key):
            return sum(v.get(key, 0) for v in (stats or {}).values())
        msg = (f"폰 동기화 완료 — 맥이 폰에서 추가 {_s(from_phone,'added')}·갱신 {_s(from_phone,'updated')}건, "
               f"폰이 맥에서 추가 {_s(to_phone,'added')}·갱신 {_s(to_phone,'updated')}건.")
        return json.dumps({"success": True, "message": msg, "from_phone": from_phone, "to_phone": to_phone}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "message": f"폰 동기화 오류: {e}"}, ensure_ascii=False)
    finally:
        _adb("forward", "--remove", f"tcp:{PORT}")


_OP_DISPATCHERS = {
    "messages_op": {"thread": _msg_thread, "inbox": _msg_inbox},
    "neighbor_op": {"list": _nb_list, "detail": _nb_detail, "save": _nb_save, "delete": _nb_delete, "favorite": _nb_favorite},
    "contact_op": {"add": _ct_add, "update": _ct_update, "delete": _ct_delete},
    "business_op": {"list": _biz_list, "detail": _biz_detail, "save": _biz_save, "delete": _biz_delete},
    "business_item_op": {"list": _item_list, "detail": _item_detail, "save": _item_save, "delete": _item_delete,
                          "add_image": _item_add_image, "remove_image": _item_remove_image},
    "business_document_op": {"list": _doc_list, "detail": _doc_detail, "update": _doc_update, "regenerate": _doc_regenerate, "publish": _doc_publish},
    "work_guideline_op": {"list": _guide_list, "detail": _guide_detail, "update": _guide_update},
    "auto_response_op": {"status": _ar_status, "start": _ar_start, "stop": _ar_stop},
}
_OP_DEFAULTS = {
    "messages_op": "thread",
    "neighbor_op": "list",
    "contact_op": "add",
    "business_op": "list",
    "business_item_op": "list",
    "business_document_op": "list",
    "work_guideline_op": "list",
    "auto_response_op": "status",
}


def execute(tool_input: dict, context) -> str:
    """비즈니스 도구 실행 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    try:
        # backend 경로 추가 (business_manager 임포트용)
        backend_path = str(Path(__file__).parent.parent.parent.parent.parent / "backend")
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)

        from business_manager import BusinessManager
        bm = BusinessManager()

        # 폰↔맥 합집합 동기화 (단일 동작, op 없음)
        if tool_name == "phone_sync":
            return _phone_sync(bm, tool_input)

        # op 분기 디스패처 (messages_op / neighbor_op / contact_op)
        if tool_name in _OP_DISPATCHERS:
            op = tool_input.get("op") or _OP_DEFAULTS.get(tool_name)
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if not fn:
                return json.dumps({"success": False, "message": f"알 수 없는 op: {op}"}, ensure_ascii=False)
            return fn(bm, tool_input)

        return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Error: {str(e)}"
