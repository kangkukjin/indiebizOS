"""
channel_engine.py - IBL 채널 노드 실행 엔진

[others:channel_send]{channel_type: "gmail", to: "user@mail.com", subject: "제목", body: "내용"}
[others:channel_read]{channel_type: "gmail", max_results: 10}
[others:channel_read]{channel_type: "gmail", query: "from:someone"}  # query 주면 검색

에이전트 identity 기반 발송:
- 외부 에이전트: 에이전트에 설정된 주소(email/nostr)를 사용
- 내부 에이전트: 외부 채널 사용 불가 (실패 반환)
- account 파라미터로 명시적 주소 지정 가능 (예: 사용자 이메일 확인)
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


# === 지원 채널 ===
SUPPORTED_CHANNELS = ["gmail", "nostr"]

# 시스템 AI(=indiebizOS 운영 주체) 식별자. 런처 indienet과 nostr 신원을 공유한다.
SYSTEM_AI_ID = "system_ai"


# === 시스템 계정 조회 ===

def _get_system_gmail_address() -> Optional[str]:
    """시스템 AI gmail 주소 — gmail extension config.yaml의 email.

    indiebizOS가 운영하는 계정이다. (owner 개인 계정과는 별개 — owner는 .env의
    OWNER_EMAILS로 등록되어 '명령 출처'로만 인식된다.)
    """
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    base = Path(env_path) if env_path else Path(__file__).parent.parent
    config_path = base / "data" / "packages" / "installed" / "extensions" / "gmail" / "config.yaml"
    if not config_path.exists():
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return (config.get("gmail") or {}).get("email") or None
    except Exception:
        return None


# === 에이전트 identity 조회 (발신 신원 + 발신 게이트) ===

def _resolve_agent_identity(channel_type: str, params: dict,
                            project_path: str, agent_id: str = None) -> dict:
    """
    채널 발신/수신 시 '누구로서' 동작할지(발신 신원)를 결정한다.

    신원 모델:
    - 시스템 AI(SYSTEM_AI_ID): 시스템 자체 계정 사용 (gmail=config.yaml, nostr=indienet 신원).
      신뢰된 주체이므로 account 명시 override 허용. 항상 발신 가능.
    - 프로젝트 에이전트: 자기 agents.yaml에 설정된 계정(email/npub)만 사용.
      계정이 비어 있으면 '연락처 없음'으로 보고 외부 발신을 차단한다.
      (외부로 연락하는 기능은 함부로 열지 않는다 — 명시적 옵트인.)
      사칭 방지를 위해 account override는 허용하지 않는다.
    - 내부(internal) 에이전트: 외부 채널 사용 불가.

    Returns:
        {"email": "..."} 또는 {"npub": "..."} 또는 {"use_system": True} 또는 {"error": "..."}
    """
    # 0-pre) 폰 네이티브: 단일 사용자 기기 — nostr 발신은 폰 indienet 신원(=시스템 신원)으로
    # 서명한다(폰 /ibl/execute 는 agent_id="phone"). 데스크탑/원격 앱표면이 system_ai 로 doing 것과 동치.
    if channel_type == "nostr" and os.environ.get("INDIEBIZ_PROFILE") == "phone":
        return {"use_system": True}

    # 0) 시스템 AI — 신뢰된 운영 주체. 시스템 자체 계정 사용.
    if agent_id == SYSTEM_AI_ID:
        account = params.get("account")
        if channel_type == "gmail":
            email = account or _get_system_gmail_address()
            if not email:
                return {"error": "시스템 gmail 계정이 설정되지 않았습니다. (gmail extension config.yaml의 email)"}
            return {"email": email}
        elif channel_type == "nostr":
            # 시스템 nostr는 항상 indienet 신원으로 서명 (런처 indienet과 공유).
            # account는 임의 pubkey를 가리킬 뿐 서명 주체가 아니므로 무시한다.
            return {"use_system": True}
        return {"error": f"identity 미지원 채널: {channel_type}"}

    # 1) 프로젝트 에이전트 — 자기 계정만. (account override 불가: 사칭 방지)
    if not agent_id:
        return {"error": "에이전트 identity가 없어 외부 채널을 사용할 수 없습니다."}

    agents_file = Path(project_path) / "agents.yaml"
    if not agents_file.exists():
        return {"error": f"agents.yaml을 찾을 수 없습니다: {agents_file}"}

    try:
        with open(agents_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return {"error": f"agents.yaml 읽기 실패: {e}"}

    # 에이전트 찾기
    agent_config = None
    for agent in data.get("agents", []):
        if agent.get("id") == agent_id:
            agent_config = agent
            break

    if not agent_config:
        return {"error": f"에이전트 '{agent_id}'를 찾을 수 없습니다."}

    # 내부 에이전트 체크
    if agent_config.get("type") == "internal":
        return {"error": f"내부 에이전트 '{agent_id}'는 외부 채널을 사용할 수 없습니다."}

    # 발신 게이트: 계정(연락처)이 비어 있으면 외부 발신 차단
    if channel_type == "gmail":
        email = agent_config.get("email")
        if not email:
            return {"error": f"에이전트 '{agent_id}'에 gmail 계정(연락처)이 설정되지 않아 외부 발신이 차단됩니다."}
        return {"email": email}

    elif channel_type == "nostr":
        npub = agent_config.get("npub") or agent_config.get("nostr")
        if not npub:
            return {"error": f"에이전트 '{agent_id}'에 nostr 계정(연락처)이 설정되지 않아 외부 발신이 차단됩니다."}
        return {"npub": npub}

    return {"error": f"identity 미지원 채널: {channel_type}"}


# === 수신자 해소 (이름 → 주소록 주소) ===

def _looks_like_address(channel_type: str, to: str) -> bool:
    """to가 이미 채널 주소 형식인지 판별."""
    to = (to or "").strip()
    if channel_type == "gmail":
        return "@" in to
    elif channel_type == "nostr":
        if to.startswith("npub"):
            return True
        if len(to) == 64:  # hex 공개키
            try:
                int(to, 16)
                return True
            except ValueError:
                return False
    return False


# 주인(사용자 본인) 별칭 — 이웃·고객과 다른 존재라 주소록이 아니라 .env 확정 원천에서 해소.
_OWNER_ALIASES = {
    "나", "나에게", "나한테", "내주소", "내 주소", "내게", "본인", "주인", "저", "제게",
    "me", "self", "myself", "owner",
}


def _load_owner_addresses(channel_type: str) -> list:
    """`.env`의 OWNER_* 에서 주인 발송 주소 목록을 읽는다 (단일 확정 원천).

    channel_poller._is_from_owner 가 수신측에서 쓰는 것과 같은 원천을 발신측에서도 사용.
    """
    try:
        from dotenv import load_dotenv
        from runtime_utils import get_base_path
        load_dotenv(get_base_path() / ".env")
    except Exception:
        pass
    if channel_type == "gmail":
        raw = os.getenv("OWNER_EMAILS", "")
    elif channel_type == "nostr":
        raw = os.getenv("OWNER_NOSTR_PUBKEYS", "")
    else:
        raw = ""
    return [a.strip() for a in raw.split(",") if a.strip()]


def _norm_addr(channel_type: str, addr: str) -> str:
    """비교용 주소 정규화. nostr 는 npub/hex 두 형식이 등가라 npub 소문자로 통일.

    (주소록 contacts 는 npub 로 저장됨 — business_manager 마이그레이션 참조.)
    """
    a = (addr or "").strip().lower()
    if channel_type == "nostr" and len(a) == 64:
        try:
            int(a, 16)
            from channel_poller import _hex_to_npub
            return (_hex_to_npub(a) or a).lower()
        except Exception:
            return a
    return a


def _resolve_recipient(channel_type: str, to: str, confirmed: bool = False) -> dict:
    """수신자(to)를 채널 주소로 해소한다 — 주소록/주인 확정 원천만 신뢰.

    규율(모델이 아무 주소나 골라 보내는 것을 막는다):
    - "나/주인" 별칭 → .env(OWNER_*) 확정 원천으로 해소.
    - 이름 → business.db 주소록에서 해당 채널 주소. 0건: 에러. 다건: 후보와 함께 에러.
    - 이미 주소 형식이면 주소록/주인에 등록된 주소일 때만 통과. 미등록이면
      needs_confirmation 으로 되돌려 AI 가 사용자 확인을 받게 한다(confirmed=True 면 통과).

    Returns: {"value": addr} | {"error": ..., "candidates": [...]}
             | {"needs_confirmation": True, "error": ..., "address": ...}
    """
    to = (to or "").strip()
    if not to:
        return {"error": "수신자(to)가 비어 있습니다."}

    owner_addrs = _load_owner_addresses(channel_type)
    owner_set = {_norm_addr(channel_type, a) for a in owner_addrs}

    # 1) 주인 별칭 → .env 확정 원천 (이웃 목록을 뒤지지 않는다)
    if to.lower() in _OWNER_ALIASES:
        if not owner_addrs:
            return {"error": f"주인의 {channel_type} 주소가 .env(OWNER_*)에 설정되어 있지 않습니다."}
        return {"value": owner_addrs[0], "owner": True}

    try:
        from business_manager import BusinessManager
        bm = BusinessManager()
    except Exception as e:
        return {"error": f"주소록 조회 실패: {e}"}

    # 2) 이미 주소 형식 → 주소록/주인에 등록된 주소만 통과, 아니면 확인 요청
    if _looks_like_address(channel_type, to):
        norm = _norm_addr(channel_type, to)
        if norm in owner_set:
            return {"value": to, "owner": True}
        try:
            found = bm.get_neighbor_by_contact(channel_type, norm) or \
                    bm.get_neighbor_by_contact(channel_type, to.strip())
        except Exception:
            found = None
        if found:
            return {"value": to}
        if confirmed:
            return {"value": to, "unregistered": True}
        return {
            "needs_confirmation": True,
            "address": to,
            "error": (f"'{to}' 는 주소록에 없는 새 {channel_type} 주소입니다. 임의로 발송하지 "
                      f"않았습니다. 사용자에게 이 주소가 맞는지 확인하세요. 확인되면 "
                      f"[others:neighbor]/[others:contact]로 주소록에 먼저 등록한 뒤 이름으로 "
                      f"보내거나, 같은 발송을 confirmed: true 로 다시 실행하세요."),
        }

    # 3) 이름 → 주소록 해소 (이름이 같은 이웃들의 해당 채널 연락처 수집)
    name_l = to.lower()
    matched = []
    try:
        for n in bm.get_neighbors():
            if (n.get("name") or "").strip().lower() != name_l:
                continue
            for c in bm.get_contacts(n.get("id")):
                if c.get("contact_type") == channel_type and c.get("contact_value"):
                    matched.append(c["contact_value"])
    except Exception as e:
        return {"error": f"주소록 조회 실패: {e}"}

    if not matched:
        return {"error": f"주소록에서 '{to}'의 {channel_type} 주소를 찾지 못했습니다. "
                         f"이름을 확인하거나, 주소를 직접 지정한 뒤 사용자 확인을 받으세요."}
    uniq = list(dict.fromkeys(matched))
    if len(uniq) > 1:
        return {"error": f"'{to}'에 해당하는 {channel_type} 주소가 여러 개입니다. 어느 것인지 지정하세요.",
                "candidates": uniq}
    return {"value": uniq[0]}


# === IBL 노드 액션 핸들러 (ibl_engine에서 호출) ===

def execute_channel_action(action: str, params: dict,
                           project_path: str, agent_id: str = None) -> Any:
    """
    ibl_engine에서 호출되는 채널 노드 액션 핸들러

    Args:
        action: send, read, search
        params: 액션별 파라미터 (channel_type 포함)
        project_path: 프로젝트 경로
        agent_id: 에이전트 ID (identity 결정에 사용)
    """
    # 커뮤니티(IndieNet) — channel_type 없는 별도 액션(피드/보드/계정)은 채널 게이트 이전에 분기.
    if action == "feed":
        return _community_feed(params)
    if action == "board":
        return _community_board(params)
    if action == "follow":
        return _community_follow(params)
    if action == "nostr":
        return _nostr_identity(params)
    if action == "publish":
        return _publish_article(params)

    channel_type_raw = params.get("channel_type", "")
    if not channel_type_raw:
        # 수신자가 이메일 형식이면 gmail로 추론 (코퍼스 다수가 channel_type 생략).
        _to = str(params.get("to", "")).strip()
        if "@" in _to and "." in _to.split("@")[-1]:
            channel_type_raw = "gmail"
    if not channel_type_raw:
        return {
            "error": "channel_type이 필요합니다.",
            "supported_channels": SUPPORTED_CHANNELS,
            "usage": {
                "send": '[others:channel_send]{channel_type: "gmail", to: "user@mail.com", subject: "제목", body: "내용"}',
                "read": '[others:channel_read]{channel_type: "gmail", max_results: 10}',
                "search": '[others:channel_read]{channel_type: "gmail", query: "from:someone"}',
            }
        }

    channel_type = channel_type_raw.lower().strip()
    if channel_type not in SUPPORTED_CHANNELS:
        return {
            "error": f"지원하지 않는 채널: {channel_type}",
            "supported_channels": SUPPORTED_CHANNELS
        }

    # 에이전트 identity 결정
    identity = _resolve_agent_identity(channel_type, params, project_path, agent_id)
    if "error" in identity:
        return {"success": False, "channel": channel_type, "error": identity["error"]}

    # IBL 액션명(channel_send/read/search)을 내부 키(send/read/search)로 정규화.
    if action.startswith("channel_"):
        action = action[len("channel_"):]

    if action == "send":
        return _channel_send(channel_type, params, identity)
    elif action == "read":
        # query 있으면 검색으로 자동 위임 (read/search 통합).
        if params.get("query"):
            return _channel_search(channel_type, params, identity)
        return _channel_read(channel_type, params, identity)
    elif action == "search":
        return _channel_search(channel_type, params, identity)
    else:
        return {
            "error": f"알 수 없는 채널 액션: {action}",
            "available_actions": ["send", "read", "search"]
        }


# === Gmail 클라이언트 ===

def _get_gmail_client(email: str = None):
    """Gmail 클라이언트 가져오기

    Args:
        email: 사용할 Gmail 주소. None이면 extension config에서 읽음.
    """
    from api_gmail import get_gmail_client_for_email

    if email:
        return get_gmail_client_for_email(email)

    # fallback: extension config
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        base = Path(env_path)
    else:
        base = Path(__file__).parent.parent

    gmail_ext_path = base / "data" / "packages" / "installed" / "extensions" / "gmail"
    config_path = gmail_ext_path / "config.yaml"

    if not config_path.exists():
        raise Exception("Gmail config.yaml이 없습니다. Gmail 채널 설정을 먼저 완료하세요.")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    gmail_config = config.get("gmail", {})
    default_email = gmail_config.get("email", "")
    if not default_email:
        raise Exception("Gmail 이메일 주소가 설정되지 않았습니다.")

    return get_gmail_client_for_email(default_email)


# === IndieNet ===

def _get_indienet():
    """IndieNet 싱글톤 가져오기"""
    from indienet import get_indienet
    indienet = get_indienet()
    if not indienet.is_initialized():
        raise Exception("IndieNet이 초기화되지 않았습니다. Nostr 설정을 먼저 완료하세요.")
    return indienet


def _publish_article(params: dict) -> dict:
    """others:publish — 마크다운을 NIP-23(kind:30023) 공개 글로 발행하고 njump 링크 반환.
    신문·리포트를 친구에게 링크 하나로 공유. slug 재발행 = 같은 주소 갱신.
    ★발행물=사용자/앱이 조립한 것만 verbatim(조작·PII 유출 금지)."""
    indienet = _get_indienet()
    title = (params.get("title") or "").strip()
    content = params.get("content") or ""
    slug = (params.get("slug") or "").strip()
    summary = (params.get("summary") or "").strip()
    if not content:
        return {"error": "content(마크다운 본문)가 필요합니다."}
    if not slug:
        import re as _re
        slug = _re.sub(r"[^0-9a-z가-힣]+", "-", title.lower()).strip("-") or "article"
    event_id = indienet.publish_article(title=title, content=content, slug=slug, summary=summary)
    if not event_id:
        return {"error": "발행 실패 — Nostr 설정/릴레이 연결을 확인하세요."}
    url = indienet.article_url(slug)
    return {
        "success": True,
        "event_id": event_id,
        "slug": slug,
        "url": url,
        "message": f"공개 발행 완료 — {url}" if url else "공개 발행 완료",
    }


# === 커뮤니티 (IndieNet 피드/보드) — others:feed / others:board ===

def _fmt_unix(ts) -> str:
    """Unix timestamp → 'MM/DD HH:MM' (실패 시 빈 문자열)."""
    try:
        from datetime import datetime
        return datetime.fromtimestamp(int(ts)).strftime("%m/%d %H:%M")
    except Exception:
        return ""


def _bridge_status(pubkey: str, indienet) -> dict:
    """팔로우↔이웃 승격 다리 상태 — 한 인물(npub)의 팔로우 여부 + 이웃 등록 여부(business.db nostr 연락처 조인).

    공개층(IndieNet)에서 만난 사람이 사적층(메신저 이웃)으로 이어져 있는지를 한 줄(status)로.
    hex/npub 표기 차이를 흡수하기 위해 hex 로 정규화해 비교."""
    def _hex(pk: str) -> str:
        try:
            return indienet._pubkey_to_hex(pk) or pk
        except Exception:
            return pk

    target = _hex(pubkey)
    following = any(_hex(f.get("pubkey", "")) == target for f in (indienet.get_follows() or []))
    neighbor_name = ""
    try:
        from business_manager import BusinessManager
        bm = BusinessManager()
        nb = bm.find_neighbor_by_contact("nostr", pubkey)
        if not nb:  # 표기 차이 폴백 — 전 이웃의 nostr 연락처를 hex 비교
            for n in bm.get_neighbors() or []:
                for c in bm.get_contacts(n["id"]) or []:
                    if c.get("contact_type") == "nostr" and _hex(c.get("contact_value", "")) == target:
                        nb = n
                        break
                if nb:
                    break
        if nb:
            neighbor_name = nb.get("name", "")
    except Exception:
        pass
    status = ("팔로우 중" if following else "팔로우 안 함") + \
             (f" · 이웃: {neighbor_name}" if neighbor_name else " · 이웃 아님")
    return {"following": following, "neighbor_name": neighbor_name, "status": status,
            "neighbor_mark": (" · 이웃✓" if neighbor_name else "")}


def _community_feed(params: dict) -> dict:
    """커뮤니티 피드 — op:read(조회)/post(게시). IndieNet(Nostr) 기반, 릴레이가 진실원."""
    op = (params.get("op") or "read").lower()
    try:
        indienet = _get_indienet()
    except Exception as e:
        return {"success": False, "error": str(e)}

    if op == "post":
        content = params.get("content") or params.get("body") or params.get("text")
        if not content:
            return {"success": False, "error": "게시할 내용(content)이 필요합니다."}
        hashtag = params.get("hashtag") or params.get("board")
        try:
            event_id = indienet.post_to_board(content=content, hashtag=hashtag)
            if not event_id:
                return {"success": False, "error": "게시 실패 (릴레이 발행 실패)"}
            return {"success": True, "event_id": event_id, "message": "게시했습니다."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # read — 4갈래: author(특정인) > following(팔로우 타임라인) > hashtag(보드) > 기본 피드
    limit = int(params.get("limit") or 50)
    author = params.get("author") or params.get("pubkey") or params.get("npub")
    following = str(params.get("following") or "").lower() in ("true", "1", "yes")
    hashtag = params.get("hashtag") or params.get("board")
    try:
        if author:
            raw = indienet.fetch_author_posts(pubkey=author, limit=limit)
        elif following:
            raw = indienet.fetch_following_feed(limit=limit)
        elif hashtag:
            raw = indienet.fetch_board_posts(hashtag=hashtag, limit=limit)
        else:
            raw = indienet.fetch_posts(limit=limit)
    except Exception as e:
        return {"success": False, "error": str(e)}

    posts = []
    for p in raw or []:
        full = p.get("author", "") or ""
        short = (full[:10] + "…") if full.startswith("npub") and len(full) > 12 else full
        content = (p.get("content", "") or "").strip()
        time_str = _fmt_unix(p.get("created_at"))
        ev_id = p.get("id", "") or ""
        posts.append({
            "author": short,
            "author_full": full,  # 저자 드릴다운·팔로우에 쓰는 전체 npub
            "content": content,
            "time": time_str,
            "id": ev_id,
        })
    # 단일 통화 — native 글 dict(author/content/time/id 등)를 items로.
    out = {"items": posts, "count": len(posts),
           "message": "" if posts else "아직 글이 없습니다."}
    # 저자 드릴다운이면 그 저자를 팔로우/이웃 등록할 수 있게 한 줄짜리 author_row 동봉
    # (+승격 다리 상태: 팔로우 여부 · 이웃 등록 여부).
    if author:
        out["author_row"] = [{
            "pubkey": author,
            "name": (author[:12] + "…") if str(author).startswith("npub") and len(str(author)) > 14 else author,
            **_bridge_status(str(author), indienet),
        }]
        # 공개 얼굴: kind:0 인사말 + kind:30023 공개 문서를 동봉 → 드릴다운에서 프로필·문서에 도달.
        short_a = (author[:12] + "…") if str(author).startswith("npub") and len(str(author)) > 14 else str(author)
        about, pname = "", ""
        try:
            info = indienet.fetch_author_profile(author) or {}
            about = (info.get("about") or "").strip()
            pname = (info.get("name") or info.get("display_name") or "").strip()
        except Exception:
            pass
        out["profile"] = [{"name": pname or short_a, "about": about}] if about else []
        try:
            arts = indienet.fetch_author_articles(pubkey=author, limit=20)
        except Exception:
            arts = []
        out["articles"] = [{
            "title": a.get("title") or "(제목 없음)",
            "content": (a.get("content") or "").strip(),
            "summary": a.get("summary") or "",
            "time": _fmt_unix(a.get("created_at")),
            "id": a.get("id") or "",
        } for a in (arts or [])]
    # 게시판 계기용(with_boards: true) — 활성 보드 글 + 보드 목록을 한 액션·한 응답으로.
    if str(params.get("with_boards") or "").lower() in ("true", "1", "yes"):
        out["boards"] = _boards_items(indienet)
        out["active_board"] = (getattr(indienet.settings, "active_board", None) or "indienet")
    return out


def _community_follow(params: dict) -> dict:
    """팔로우 관리 — op:list/add/remove. 로컬 저장(settings.follows).

    나중에 이 목록을 kind:3(NIP-02)으로 발행하면 다른 Nostr 앱과 공유되는
    포터블 소셜 그래프로 승격 가능(현재는 로컬만)."""
    op = (params.get("op") or "list").lower()
    try:
        indienet = _get_indienet()
    except Exception as e:
        return {"success": False, "error": str(e)}

    if op == "add":
        pk = params.get("pubkey") or params.get("npub") or params.get("author")
        if not pk:
            return {"success": False, "error": "팔로우할 pubkey(npub 또는 hex)가 필요합니다."}
        try:
            entry = indienet.add_follow(pk, name=params.get("name"))
            return {"success": True, "follow": entry, "message": "팔로우했습니다."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    if op == "remove":
        pk = params.get("pubkey") or params.get("npub") or params.get("author")
        if not pk:
            return {"success": False, "error": "언팔로우할 pubkey가 필요합니다."}
        ok = indienet.remove_follow(pk)
        return {"success": bool(ok),
                "message": "언팔로우했습니다." if ok else "팔로우 목록에 없습니다."}

    # list — 승격 다리 상태(이웃 등록 여부) 동봉
    follows = indienet.get_follows() or []
    out = []
    for f in follows:
        pk = f.get("pubkey", "") or ""
        short = (pk[:12] + "…") if pk.startswith("npub") and len(pk) > 14 else pk
        out.append({
            "pubkey": pk,
            "name": f.get("name") or short,
            "short": short,
            **_bridge_status(pk, indienet),
        })
    return {"items": out, "count": len(out),
            "message": "" if out else "아직 팔로우한 사람이 없습니다."}


def _boards_items(indienet) -> list:
    """보드 목록 items — 기본 #indienet + 사용자 보드, 활성 표시.
    active_mark(✓)는 렌더러 템플릿용 표시 필드 — 활성 보드를 목록에서 한눈에."""
    active = (getattr(indienet.settings, "active_board", None) or "indienet")
    boards = [{"name": "IndieNet", "hashtag": "indienet"}] + list(indienet.get_boards() or [])
    return [{"name": b.get("name", ""), "hashtag": b.get("hashtag", ""),
             "active": (b.get("hashtag") == active),
             "active_mark": ("✓ " if b.get("hashtag") == active else "")} for b in boards]


def _community_board(params: dict) -> dict:
    """커뮤니티 보드 — op:list/create/switch."""
    op = (params.get("op") or "list").lower()
    try:
        indienet = _get_indienet()
    except Exception as e:
        return {"success": False, "error": str(e)}

    if op == "create":
        name = params.get("name") or params.get("board_name")
        hashtag = params.get("hashtag") or params.get("tag")
        if not name or not hashtag:
            return {"success": False, "error": "보드 이름(name)과 해시태그(hashtag)가 필요합니다."}
        try:
            board = indienet.create_board(name=name, hashtag=hashtag)
            return {"success": True, "board": board, "message": f"보드 '{name}' 생성"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    if op == "switch":
        hashtag = params.get("hashtag") or params.get("tag")  # 없으면 기본 보드
        try:
            ok = indienet.set_active_board(hashtag.lstrip('#') if hashtag else None)
        except Exception as e:
            return {"success": False, "error": str(e)}
        return {"success": bool(ok), "active": (hashtag or "indienet"),
                "message": "보드를 전환했습니다." if ok else "전환 실패 (보드 없음)"}

    if op == "delete":
        hashtag = (params.get("hashtag") or params.get("tag") or "").lstrip('#').lower()
        if not hashtag:
            return {"success": False, "error": "삭제할 보드 해시태그(hashtag)가 필요합니다."}
        if hashtag == "indienet":
            return {"success": False, "error": "기본 보드 #indienet 은 삭제할 수 없습니다."}
        ok = indienet.delete_board(hashtag)
        # 글은 릴레이에 남는다 — 보드 삭제=로컬 등록 해제(재생성 시 복원). 활성 보드였다면 기본으로 복귀.
        return {"success": bool(ok),
                "message": f"보드 #{hashtag} 를 삭제했습니다." if ok else "삭제 실패 (보드 없음)"}

    # list — 기본 #indienet + 사용자 보드, 활성 표시
    active = (getattr(indienet.settings, "active_board", None) or "indienet")
    # 단일 통화 — native 보드 dict(name/hashtag/active)를 items로.
    out = _boards_items(indienet)
    return {"items": out, "active": active,
            "message": "" if out else "보드가 없습니다."}


def _nostr_identity(params: dict) -> dict:
    """IndieNet/Nostr 계정 — op:profile/rename/relays/import_key/reset_identity.
    IndieNet 창의 신원·설정 기능을 IBL 로 노출(창 은퇴 대비)."""
    op = (params.get("op") or "profile").lower()
    try:
        indienet = _get_indienet()
    except Exception as e:
        return {"success": False, "error": str(e)}
    idy = indienet.identity
    s = indienet.settings

    if op == "rename":
        name = params.get("name") or params.get("display_name")
        if not name:
            return {"success": False, "error": "표시 이름(name)이 필요합니다."}
        ok = idy.set_display_name(name)
        return {"success": bool(ok), "display_name": name,
                "message": "표시 이름을 바꿨습니다." if ok else "변경 실패"}

    if op == "relays":
        if params.get("restore_defaults"):
            from indienet import DEFAULT_RELAYS
            s.relays = list(DEFAULT_RELAYS); s.save()
            return {"success": True, "relays": [{"url": r} for r in s.relays], "message": "기본 릴레이로 초기화"}
        new = params.get("set") or params.get("relays")
        if new:
            s.relays = new if isinstance(new, list) else [x.strip() for x in str(new).split(",") if x.strip()]
            s.save()
            return {"success": True, "relays": [{"url": r} for r in s.relays], "message": "릴레이를 갱신했습니다."}
        return {"relays": [{"url": r} for r in s.relays], "count": len(s.relays)}

    if op == "import_key":
        nsec = params.get("nsec")
        if not nsec:
            return {"success": False, "error": "nsec가 필요합니다."}
        ok = idy.import_nsec(nsec)
        return {"success": bool(ok), "identity": idy.to_dict() if ok else None,
                "message": "신원을 가져왔습니다." if ok else "가져오기 실패 (nsec 확인)"}

    if op == "reset_identity":
        ok = idy.reset_identity()
        return {"success": bool(ok), "identity": idy.to_dict() if ok else None,
                "message": "새 신원을 생성했습니다." if ok else "초기화 실패"}

    # profile (기본) — npub·표시이름·활성보드·릴레이 한 번에
    active = (getattr(s, "active_board", None) or "indienet")
    return {
        "npub": idy.npub or "",
        "display_name": idy.display_name or "(미설정)",
        "created_at": (idy.created_at or "")[:10],
        "active_board": active,
        "relays": [{"url": r} for r in s.relays],
        "relay_count": len(s.relays),
    }


# === 내부 구현 ===

def _channel_send(channel_type: str, params: dict, identity: dict) -> dict:
    """메시지 발송"""
    if channel_type == "gmail":
        to = params.get("to")
        subject = params.get("subject", "(제목 없음)")
        body = params.get("body", "")
        attachment_path = params.get("attachment_path")

        if not to:
            return {"error": "수신자(to)가 필요합니다. (이웃 이름 또는 이메일 주소)"}

        # 수신자 해소: 이름/주인 별칭 → 주소록·.env 확정 원천. 미등록 주소는 확인 요청.
        resolved = _resolve_recipient("gmail", to, confirmed=bool(params.get("confirmed")))
        if resolved.get("error") or resolved.get("needs_confirmation"):
            out = {"success": False, "channel": "gmail", "error": resolved.get("error")}
            if resolved.get("needs_confirmation"):
                out["needs_confirmation"] = True
                out["address"] = resolved.get("address")
            if resolved.get("candidates"):
                out["candidates"] = resolved["candidates"]
            return out
        to = resolved["value"]

        try:
            client = _get_gmail_client(email=identity.get("email"))
            result = client.send_message(
                to=to, subject=subject, body=body,
                attachment_path=attachment_path
            )
            return {
                "success": True,
                "channel": "gmail",
                "from": identity.get("email"),
                "message_id": result.get("id"),
                "thread_id": result.get("threadId"),
                "to": to,
                "subject": subject
            }
        except Exception as e:
            return {"success": False, "channel": "gmail", "error": str(e)}

    elif channel_type == "nostr":
        to = params.get("to") or params.get("to_pubkey")
        content = params.get("content") or params.get("body", "")

        if not to:
            return {"error": "수신자(to)가 필요합니다. (이웃 이름, npub 또는 hex)"}
        if not content:
            return {"error": "메시지 내용(content)이 필요합니다."}

        # nostr 발신은 현재 indienet 단일 신원으로만 서명 가능.
        # 프로젝트 에이전트의 자체 npub 키 서명은 아직 미지원 → 시스템 신원만 허용.
        if not identity.get("use_system"):
            return {"success": False, "channel": "nostr",
                    "error": "에이전트 자체 nostr 키 서명은 아직 지원되지 않습니다. "
                             "현재 nostr 발신은 시스템(indienet) 신원만 가능합니다."}

        # 수신자 해소: 이름/주인 별칭 → 주소록·.env 확정 원천. 미등록 주소는 확인 요청.
        resolved = _resolve_recipient("nostr", to, confirmed=bool(params.get("confirmed")))
        if resolved.get("error") or resolved.get("needs_confirmation"):
            out = {"success": False, "channel": "nostr", "error": resolved.get("error")}
            if resolved.get("needs_confirmation"):
                out["needs_confirmation"] = True
                out["address"] = resolved.get("address")
            if resolved.get("candidates"):
                out["candidates"] = resolved["candidates"]
            return out
        to = resolved["value"]

        try:
            indienet = _get_indienet()
            # NIP-17(gift-wrap)로 발송 — 최신 클라이언트(Damus/Amethyst/0xchat)가 읽는 표준.
            # 수신자의 kind:10050 DM relay로 배달. (구 NIP-04 send_dm은 최신 앱이 복호 못 함)
            event_id = indienet.send_dm_nip17(to_pubkey=to, content=content)
            if event_id:
                return {
                    "success": True,
                    "channel": "nostr",
                    "protocol": "nip17",
                    "event_id": event_id,
                    "to": to[:20] + "..."
                }
            return {"success": False, "channel": "nostr", "error": "DM 전송 실패"}
        except Exception as e:
            return {"success": False, "channel": "nostr", "error": str(e)}

    return {"error": f"send 미지원 채널: {channel_type}"}


def _channel_read(channel_type: str, params: dict, identity: dict) -> dict:
    """메시지 읽기"""
    if channel_type == "gmail":
        query = params.get("query")
        max_results = params.get("max_results", 10)

        try:
            client = _get_gmail_client(email=identity.get("email"))
            messages = client.get_messages(query=query, max_results=max_results)

            simplified = []
            for msg in messages:
                if msg is None:
                    continue
                simplified.append({
                    "id": msg.get("id"),
                    "subject": msg.get("subject", ""),
                    "from": msg.get("from", ""),
                    "date": msg.get("date", ""),
                    "snippet": msg.get("snippet", ""),
                    "body": (msg.get("body") or "")[:500],
                })

            return {
                "success": True,
                "channel": "gmail",
                "account": identity.get("email"),
                "count": len(simplified),
                "query": query,
                "items": simplified  # 단일 통화 items = native 메시지 dict(id/subject/from/date/snippet/body)
            }
        except Exception as e:
            return {"success": False, "channel": "gmail", "error": str(e)}

    elif channel_type == "nostr":
        limit = params.get("limit", 20)
        since = params.get("since")

        try:
            indienet = _get_indienet()
            dms = indienet.fetch_dms(limit=limit, since=since)
            return {
                "success": True,
                "channel": "nostr",
                "count": len(dms),
                "items": dms  # 단일 통화 items = native DM dict
            }
        except Exception as e:
            return {"success": False, "channel": "nostr", "error": str(e)}

    return {"error": f"read 미지원 채널: {channel_type}"}


def _channel_search(channel_type: str, params: dict, identity: dict) -> dict:
    """메시지 검색"""
    if channel_type == "gmail":
        query = params.get("query", "")
        max_results = params.get("max_results", 10)

        if not query:
            return {"error": "검색어(query)가 필요합니다."}

        try:
            client = _get_gmail_client(email=identity.get("email"))
            messages = client.get_messages(query=query, max_results=max_results)

            simplified = []
            for msg in messages:
                if msg is None:
                    continue
                simplified.append({
                    "id": msg.get("id"),
                    "subject": msg.get("subject", ""),
                    "from": msg.get("from", ""),
                    "date": msg.get("date", ""),
                    "snippet": msg.get("snippet", "")
                })

            return {
                "success": True,
                "channel": "gmail",
                "account": identity.get("email"),
                "query": query,
                "count": len(simplified),
                "messages": simplified
            }
        except Exception as e:
            return {"success": False, "channel": "gmail", "error": str(e)}

    elif channel_type == "nostr":
        query_text = params.get("query", "")
        limit = params.get("max_results", 20)

        if not query_text:
            return {"error": "검색어(query)가 필요합니다."}

        try:
            from business_manager import BusinessManager
            bm = BusinessManager()
            all_msgs = bm.get_messages(limit=limit * 3)

            matched = []
            for msg in all_msgs:
                if msg.get("contact_type") != "nostr":
                    continue
                content = (msg.get("content") or "") + " " + (msg.get("subject") or "")
                if query_text.lower() in content.lower():
                    matched.append({
                        "id": msg.get("id"),
                        "from": msg.get("contact_value", ""),
                        "content": (msg.get("content") or "")[:300],
                        "date": msg.get("message_time", "")
                    })
                    if len(matched) >= limit:
                        break

            return {
                "success": True,
                "channel": "nostr",
                "query": query_text,
                "count": len(matched),
                "messages": matched,
                "note": "Nostr 검색은 로컬 DB에서 수행됩니다."
            }
        except Exception as e:
            return {"success": False, "channel": "nostr", "error": str(e)}

    return {"error": f"search 미지원 채널: {channel_type}"}
