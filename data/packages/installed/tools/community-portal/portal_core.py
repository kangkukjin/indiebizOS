"""portal_core.py — 개인 포털(커뮤니티 홈) 상태·게이트 단일 소스.

handler.py(IBL 운영자 어휘)와 backend/api_portal.py(공개 서빙·회원 실행 게이트)가
같은 상태 파일을 만지므로, 상태 읽기-수정-쓰기를 여기 한 곳에 모으고 flock 으로
직렬화한다(모듈 인스턴스가 둘이어도 파일락이 지켜줌 — showcase '동시 쓰기 금지' 교훈).

★이 파일 수정 시: handler 는 /packages/reload 로 갱신되지만, api_portal 이 sys.modules
  에 캐시한 인스턴스는 백엔드 재시작으로만 갱신된다.

핵심 개념(핸드오프 §1):
- 회원 = {id, name, contact, level(0 손님/1 이웃/2 가족), key(개인 링크=열쇠), usage}
- display = 계기·콘텐츠마다 {enabled, min_level, guest_daily, member_daily, global_daily}
- 진열 가능 목록(listable universe)은 노드 축으로 유도: self/others/limbs 가 낀 계기는
  목록 밖(다이얼 자체가 없음 — 공급망 게이트 철학). 예외는 MANUAL_LISTABLE 에 명시.
- 회원 실행 게이트: 범용 /ibl/execute 직결 금지 — 계기 app: 블록에 선언된 액션 템플릿의
  '인스턴스'만 실행(리터럴 파라미터는 일치, $key·{field} 자리만 값 허용).
"""

import os
import re
import sys
import json
import copy
import time
import fcntl
import secrets
import importlib.util
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parents[5]
_BACKEND = str(_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_STATE_PATH = _ROOT / "data" / "portal_state.json"
_LOCK_PATH = _ROOT / "data" / "portal_state.lock"
_AUDIT_PATH = _ROOT / "data" / "portal_audit.jsonl"

LEVEL_LABELS = {0: "손님", 1: "이웃", 2: "가족"}
LEVEL_MAX = 2

_NAME_MAX = 24
_CONTACT_MAX = 60
_MEMBER_CAP = 500
_JOIN_MIN_INTERVAL_S = 30
_AUDIT_MAX_BYTES = 5 * 1024 * 1024
_PARAM_VALUE_MAX = 400

# 노드 축 유도(핸드오프 §1.4): 사적/몸/발신 노드가 낀 계기는 진열 목록 밖.
FORBIDDEN_NODES = {"self", "others", "limbs"}

# 노드 축이 못 거르는 명시 차단 — host(시스템)는 sense 지만 대상이 '집 PC 자신'(CPU·디스크·
# 프로세스 목록=사적)이라 절대금지군(핸드오프 §1.5). 조회 대상이 세계가 아니라 몸이면 여기에.
FORBIDDEN_INSTRUMENTS = {"host"}

# 수동 승인 예외(핸드오프 "설정 파일 수동 편집으로만 추가") — 코드에 명시된 감사 가능한 예외.
# ytmusic: limbs:music 이 끼지만 ▶ 버튼은 mode:"client"(회원 브라우저에서 소리) 리터럴이
# 템플릿 게이트로 강제되고, 맥 스피커를 만지는 '큐' 탭은 phone_render:false 라 포털 필터가
# 걷어낸다. 익명 공개 금지(유튜브 공개 프록시화) — 회원 전용(min_level 1+).
MANUAL_LISTABLE = {
    "ytmusic": {"min_level": 1, "guest_daily": 0, "member_daily": 60, "global_daily": 200},
}

# 노드 프로파일별 기본 다이얼 — 안전 우선(전부 회원 1+). 무료 조회 계기를 손님(레벨 0)에
# 열지는 운영자가 다이얼로 내린다(크롤형=집 IP 평판 → 손님 금지 기본이 안전).
# min_level(누가 보는가)만 프로파일별로 다르게 두고, 사용 횟수 캡(손님/회원/전체)은
# 포털-수준 설정(_DEFAULT_LIMITS/portal["limits"])이 단일 소스 — display_entry 가 계기 캡을
# 포털 한도로 덮는다(코드 수정 없이 설정 탭에서 조정). guest_daily 값은 아래에 남겨두되
# 참고용(포털 limits 가 없을 때의 폴백)이고, 실제로는 포털 limits 가 우선한다.
_ENGINES_DEFAULT = {"min_level": 1, "guest_daily": 0, "member_daily": 20, "global_daily": 60}
_SENSE_DEFAULT = {"min_level": 1, "guest_daily": 3, "member_daily": 50, "global_daily": 300}
_CONTENT_DEFAULT = {"min_level": 1, "guest_daily": 0, "member_daily": 0, "global_daily": 0}

# 포털-수준 일일 한도 기본값(계기 사용 횟수). 사용자가 설정 탭에서 포털마다 바꾼다 —
# 매번 코드를 고치지 않는다. 진열 사다리(min_level)가 접근을 막으므로(손님은 min_level 0 만
# 도달) 캡을 포털 공통으로 둬도 안전하다. 콘텐츠 타일(news/files/board=아웃링크)에는 적용 안 함.
_DEFAULT_LIMITS = {"guest_daily": 3, "member_daily": 50, "global_daily": 300}
_LIMIT_KEYS = ("guest_daily", "member_daily", "global_daily")


# ── 상태 (flock 직렬화) — 다중 포털 ─────────────────────────────────────
# 포털 = 대상별 공개 주소(가족용·친구용…). 각 포털이 자기 회원 명부·진열 다이얼을 가진다
# (showcase 바스켓 패턴). 첫페이지는 그 주소의 display 로만 조립된다.

_PORTAL_CAP = 20


def _new_portal(title: str = "우리 마을", slug: str = "") -> dict:
    return {"id": "p" + secrets.token_hex(3), "slug": slug or new_slug(), "title": title,
            "intro": "", "members": [], "display": {}, "usage_global": {},
            "limits": dict(_DEFAULT_LIMITS)}


def _defaults(st: dict) -> dict:
    if "portals" not in st:
        # 구 단일-포털 스키마 마이그레이션 (2026-07-16 이전 상태 파일)
        if st.get("slug") or st.get("members") or st.get("display"):
            p = _new_portal(st.get("title") or "우리 마을", st.get("slug") or "")
            p["intro"] = st.get("intro", "")
            p["members"] = st.get("members", [])
            p["display"] = st.get("display", {})
            p["usage_global"] = st.get("usage_global", {})
            st = {"portals": [p], "public_base": st.get("public_base", "")}
        else:
            st = {"portals": [], "public_base": st.get("public_base", "")}
    st.setdefault("portals", [])
    # 포털-수준 일일 한도 마이그레이션 — 없으면 기본값 시드(설정 탭에서 조정).
    for p in st["portals"]:
        lim = p.get("limits") or {}
        p["limits"] = {**_DEFAULT_LIMITS,
                       **{k: int(lim[k]) for k in _LIMIT_KEYS if lim.get(k) is not None}}
    if not st.get("public_base"):
        st["public_base"] = _default_public_base()
    return st


def load_state() -> dict:
    try:
        return _defaults(json.loads(_STATE_PATH.read_text(encoding="utf-8")))
    except Exception:
        return _defaults({})


def mutate_state(fn):
    """load-modify-save 를 파일락으로 직렬화. fn(state) 가 수정하면 저장 후 반환."""
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOCK_PATH, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            state = load_state()
            ret = fn(state)
            tmp = _STATE_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(_STATE_PATH)
            return state if ret is None else ret
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def _default_public_base() -> str:
    """공개 사이트 base — 공개파일·가족신문과 같은 Worker."""
    try:
        sc = json.loads((_ROOT / "data" / "showcase_state.json").read_text(encoding="utf-8"))
        return (sc.get("settings") or {}).get("public_base", "") or ""
    except Exception:
        return ""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def new_slug() -> str:
    import string
    return "".join(secrets.choice(string.ascii_uppercase) for _ in range(5))


def ensure_default_portal(state: dict) -> dict:
    """포털이 하나도 없으면 기본 포털 생성. 첫(기본) 포털 반환."""
    if not state["portals"]:
        state["portals"].append(_new_portal())
    return state["portals"][0]


def portal_by_slug(state: dict, slug: str):
    for p in state.get("portals", []):
        if slug and p.get("slug") == slug:
            return p
    return None


def portal_by_ref(state: dict, ref: str = ""):
    """운영자 어휘의 portal 파라미터 해소 — slug/id/이름, 비우면 첫 포털."""
    ref = (ref or "").strip()
    ps = state.get("portals", [])
    if not ref:
        return ps[0] if ps else None
    for p in ps:
        if ref in (p.get("slug"), p.get("id")) or ref == p.get("title"):
            return p
    return None


def create_portal(state: dict, title: str) -> dict:
    title = (title or "").strip()[:40]
    if not title:
        raise ValueError("포털 이름을 입력해 주세요")
    if len(state["portals"]) >= _PORTAL_CAP:
        raise ValueError("포털 수 상한에 도달했습니다")
    p = _new_portal(title)
    state["portals"].append(p)
    return p


def portal_url(state: dict, portal: dict) -> str:
    base = (state.get("public_base") or "").rstrip("/")
    slug = (portal or {}).get("slug") or ""
    return f"{base}/h/{slug}/" if base and slug else ""


def member_link(state: dict, portal: dict, m: dict) -> str:
    u = portal_url(state, portal)
    return f"{u}k/{m.get('key','')}" if u and m.get("key") else ""


# ── 회원 (포털별 명부) ───────────────────────────────────────────────────

_LOGIN_ID_RE = re.compile(r"^[a-z0-9_.-]{3,20}$")


def find_member(portal: dict, member_id: str = "", key: str = ""):
    for m in (portal or {}).get("members", []):
        if member_id and m.get("id") == member_id:
            return m
        if key and m.get("key") and m.get("key") == key and not m.get("revoked"):
            return m
    return None


def find_member_by_login(portal: dict, login_id: str):
    lid = (login_id or "").strip().lower()
    for m in (portal or {}).get("members", []):
        if lid and m.get("login_id") == lid:
            return m
    return None


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(s: str) -> bool:
    return bool(_EMAIL_RE.match((s or "").strip()))


def find_member_by_email(portal: dict, email: str):
    """복구용 이메일(contact)로 회원 찾기 — 셀프 가입(login_id 보유)만."""
    e = (email or "").strip().lower()
    if not e:
        return None
    for m in (portal or {}).get("members", []):
        if m.get("login_id") and (m.get("contact") or "").strip().lower() == e:
            return m
    return None


# 임시 비밀번호 알파벳 — 헷갈리는 0/O·1/I/l 제외(메일로 읽고 입력하기 쉽게).
_TEMP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def gen_temp_password(n: int = 10) -> str:
    return "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(n))


def set_password(m: dict, pw: str) -> None:
    import hashlib
    if not (4 <= len(pw or "") <= 64):
        raise ValueError("비밀번호는 4~64자여야 해요")
    salt = secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()
    m["pw"] = f"pbkdf2${salt}${h}"


def verify_password(m: dict, pw: str) -> bool:
    import hashlib
    try:
        _algo, salt, h = (m.get("pw") or "").split("$")
        return hashlib.pbkdf2_hmac("sha256", (pw or "").encode(), salt.encode(), 100_000).hex() == h
    except Exception:
        return False


def create_member(portal: dict, name: str, contact: str = "", level: int = 0,
                  login_id: str = "", password: str = "") -> dict:
    """회원 생성 — login_id+password 를 주면 셀프 가입형(로그인 가능), 없으면 링크 전용."""
    name = (name or "").strip()[:_NAME_MAX]
    if not name:
        raise ValueError("이름이 필요합니다")
    if len(portal.get("members", [])) >= _MEMBER_CAP:
        raise ValueError("회원 수 상한에 도달했습니다")
    m = {
        "id": "m" + secrets.token_hex(3),
        "name": name,
        "contact": (contact or "").strip()[:_CONTACT_MAX],
        "level": max(0, min(LEVEL_MAX, int(level))),
        "key": secrets.token_urlsafe(18),   # 쿠키 세션 토큰 겸 개인 링크 열쇠
        "joined_at": _now(),
        "last_used": "",
        "revoked": False,
        "usage": {},
    }
    if login_id:
        lid = login_id.strip().lower()
        if not _LOGIN_ID_RE.match(lid):
            raise ValueError("아이디는 영문 소문자·숫자 3~20자예요")
        if find_member_by_login(portal, lid):
            raise ValueError("이미 있는 아이디예요")
        m["login_id"] = lid
        set_password(m, password)
    portal.setdefault("members", []).append(m)
    return m


def member_usage_today(m: dict) -> int:
    t = _today()
    return sum(int(d.get(t, 0)) for d in (m.get("usage") or {}).values())


def usage_global_today(portal: dict) -> int:
    t = _today()
    return sum(int(d.get(t, 0)) for d in (portal or {}).get("usage_global", {}).values())


# ── 진열 가능 목록(listable universe) — 노드 축 유도 ─────────────────────

# 클라이언트 다운로드(op:"download")는 폰 WebView 전용 배선(b64→네이티브 저장) — 일반
# 브라우저(포털 회원)엔 저장 경로가 없어 MB급 응답만 낭비된다. 포털판에선 버튼을 걷어낸다.
_DOWNLOAD_OP_RE = re.compile(r'op:\s*"download"')


def _prune_client_download(obj):
    if isinstance(obj, dict):
        for bk in ("button", "button2"):
            b = obj.get(bk)
            if isinstance(b, dict) and _DOWNLOAD_OP_RE.search(str(b.get("action", ""))):
                obj.pop(bk, None)
        if isinstance(obj.get("buttons"), list):
            obj["buttons"] = [b for b in obj["buttons"]
                              if not (isinstance(b, dict) and _DOWNLOAD_OP_RE.search(str(b.get("action", ""))))]
        for v in obj.values():
            _prune_client_download(v)
    elif isinstance(obj, list):
        for v in obj:
            _prune_client_download(v)


def _portal_filter_inst(inst: dict):
    """계기 매니페스트의 포털판 — phone_render:false 모드 제거(포털=브라우저, 폰과 같은 제약:
    맥 스피커·네이티브 창·데스크탑 전용 출력은 회원 화면에 못 싣는다) + 다운로드 버튼 제거."""
    inst = copy.deepcopy(inst)
    modes = inst.get("modes")
    if isinstance(modes, list):
        kept = [m for m in modes if not (isinstance(m, dict) and m.get("phone_render") is False)]
        if not kept:
            return None
        inst["modes"] = kept
    _prune_client_download(inst)
    return inst


def _action_heads(obj) -> set:
    """매니페스트 안 모든 IBL 템플릿의 (node, action) 머리 집합."""
    blob = json.dumps(obj, ensure_ascii=False)
    return set(re.findall(r"\[(\w+):(\w+)\]", blob))


def _derive_all_instruments() -> list:
    """api_launcher_web 의 매니페스트 파생 재사용(포크 금지). backend 프로세스 안에서 호출됨."""
    from api_launcher_web import _derive_instruments
    return _derive_instruments().get("instruments", [])


# 포털 전용 안내문 — 회원 화면(브라우저)에서만 붙는다. 데스크탑·폰 표면의 note 와 별개.
PORTAL_NOTES = {
    "icon": "그림이 나오면 꾹 눌러 복사한 뒤 카톡에 붙여넣으세요. (자동 복사는 폰 앱에서만 돼요)",
    "ytmusic": "재생하면 소리는 이 기기에서 나요 — 집 밖에서도 들을 수 있어요.",
}


def portal_instrument(iid: str):
    """포털에 내보낼 수 있는 형태의 계기 매니페스트(포털 필터 + 포털 안내문). 없으면 None."""
    for inst in _derive_all_instruments():
        if inst.get("id") == iid:
            pinst = _portal_filter_inst(inst)
            note = PORTAL_NOTES.get(iid)
            if pinst and note:
                targets = pinst.get("modes") if isinstance(pinst.get("modes"), list) else [pinst]
                for m in targets:
                    m["note"] = (note + " " + m["note"]) if m.get("note") else note
            return pinst
    return None


def listable_universe(state: dict) -> list:
    """다이얼을 달 수 있는 항목 전체 — [{key, icon, name, kind, default}].

    계기: 노드 축으로 유도(FORBIDDEN_NODES 낀 것은 목록 밖, MANUAL_LISTABLE 예외).
    콘텐츠: 가족신문(/n/)·공개파일 바스켓(/s/) — 홈의 개인화된 색인 타일.
    """
    out = []
    for inst in _derive_all_instruments():
        iid = inst.get("id", "")
        pinst = _portal_filter_inst(inst)
        if not pinst:
            continue
        heads = _action_heads(pinst)
        if not heads:
            continue
        nodes = {n for n, _ in heads}
        if iid in FORBIDDEN_INSTRUMENTS:
            continue  # 몸-대상 조회(집 PC 상태 등) — 다이얼 자체가 없음
        if iid in MANUAL_LISTABLE:
            default = dict(MANUAL_LISTABLE[iid])
        elif nodes & FORBIDDEN_NODES:
            continue  # 사적/몸/발신 계기 — 다이얼 자체가 없음
        elif "engines" in nodes:
            default = dict(_ENGINES_DEFAULT)
        else:
            default = dict(_SENSE_DEFAULT)
        out.append({"key": iid, "icon": inst.get("icon", "🔧"), "name": inst.get("name", iid),
                    "kind": "instrument", "default": default})

    # 콘텐츠 타일 — 발행물 링크(신문·바스켓 자체는 무변경, 홈은 색인일 뿐)
    try:
        fn = json.loads((_ROOT / "data" / "family_news" / "state.json").read_text(encoding="utf-8"))
        if fn.get("slug") and any(e.get("published_at") for e in fn.get("editions", [])):
            out.append({"key": f"news:{fn['slug']}", "icon": "🗞️",
                        "name": fn.get("title", "가족신문"), "kind": "content",
                        "url": f"/n/{fn['slug']}/", "default": dict(_CONTENT_DEFAULT)})
    except Exception:
        pass
    try:
        sc = json.loads((_ROOT / "data" / "showcase_state.json").read_text(encoding="utf-8"))
        for b in sc.get("baskets", []):
            if b.get("slug"):
                out.append({"key": f"files:{b['slug']}", "icon": "📁",
                            "name": b.get("title", b["slug"]), "kind": "content",
                            "url": f"/s/{b['slug']}/", "default": dict(_CONTENT_DEFAULT)})
    except Exception:
        pass
    try:
        bl = json.loads((_ROOT / "data" / "bulletin" / "state.json").read_text(encoding="utf-8"))
        for b in bl.get("boards", []):
            if b.get("slug"):
                out.append({"key": f"board:{b['slug']}", "icon": "📋",
                            "name": b.get("title", b["slug"]), "kind": "content",
                            "url": f"/b/{b['slug']}/", "default": dict(_CONTENT_DEFAULT)})
    except Exception:
        pass
    # 정기보고 발행 면 — /r/<slug>/ 는 항상 그 폴더 최신 보고서를 렌더(앱 아닌 산출물 링크).
    try:
        rp = json.loads((_ROOT / "data" / "report_publish.json").read_text(encoding="utf-8"))
        for r in rp.get("reports", []):
            if r.get("slug") and r.get("enabled", True):
                out.append({"key": f"report:{r['slug']}", "icon": "📑",
                            "name": r.get("title", "정기보고"), "kind": "content",
                            "url": f"/r/{r['slug']}/", "default": dict(_CONTENT_DEFAULT)})
    except Exception:
        pass
    return out


def display_entry(portal: dict, universe_item: dict) -> dict:
    """항목의 현재 다이얼(포털별) — 그 포털에 저장된 값 위에 기본값을 깐다.

    사용 횟수 캡(손님/회원/전체)은 포털-수준 limits 가 단일 소스라 계기별 스냅샷을 덮는다
    (설정 탭에서 한 번 정하면 그 포털 전 계기에 적용). min_level·enabled 는 계기별 유지.
    콘텐츠 타일(아웃링크)은 사용 게이트를 안 지나므로 캡을 덮지 않는다."""
    cur = ((portal or {}).get("display") or {}).get(universe_item["key"]) or {}
    d = dict(universe_item["default"])
    d.update({k: v for k, v in cur.items() if v is not None})
    d.setdefault("enabled", bool(cur.get("enabled", False)))
    if universe_item.get("kind") == "instrument":
        lim = (portal or {}).get("limits") or {}
        for k in _LIMIT_KEYS:
            if lim.get(k) is not None:
                d[k] = int(lim[k])
    return d


def visible_tiles(state: dict, portal: dict, viewer_level) -> list:
    """그 포털 홈에 진열할 타일 — enabled 항목 전부(잠긴 것도 획득 표면으로 보여줌).

    viewer_level: None=손님(레벨 -1 취급 아님 — min_level 0 이면 사용 가능), int=회원 레벨.
    """
    lv = -1 if viewer_level is None else int(viewer_level)
    tiles = []
    for u in listable_universe(state):
        d = display_entry(portal, u)
        if not d.get("enabled"):
            continue
        ml = int(d.get("min_level", 1))
        unlocked = (ml == 0) or (lv >= ml)
        tiles.append({"key": u["key"], "icon": u["icon"], "name": u["name"], "kind": u["kind"],
                      "min_level": ml, "unlocked": unlocked, "url": u.get("url", "")})
    return tiles


# ── 회원 실행 게이트 — 템플릿 화이트리스트 ────────────────────────────────

def collect_templates(inst: dict) -> list:
    """계기 매니페스트에 선언된 IBL 액션 템플릿 문자열 전부(재귀)."""
    out = []

    def _walk(o):
        if isinstance(o, str):
            if re.match(r"^\s*\[\w+:\w+\]", o):
                out.append(o.strip())
        elif isinstance(o, dict):
            for v in o.values():
                _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)

    _walk(inst)
    return out


_PLACEHOLDER_RE = re.compile(r"\$\w+|\{[\w.|:$ ]+\}")


def _parse_single(code: str):
    """단일 단순 액션만 파싱(파이프라인·병렬·제어 블록 거부). 실패 시 None."""
    try:
        import ibl_parser
        steps = ibl_parser.parse(code)
    except Exception:
        return None
    if not isinstance(steps, list) or len(steps) != 1:
        return None
    s = steps[0]
    if not isinstance(s, dict) or not s.get("_node") or not s.get("action"):
        return None
    if s.get("type") or s.get("steps") or s.get("parallel"):
        return None
    return s


def _value_regex(template_value: str):
    """플레이스홀더($key·{field})가 든 템플릿 값 → 값 매칭 정규식."""
    parts = _PLACEHOLDER_RE.split(template_value)
    holes = _PLACEHOLDER_RE.findall(template_value)
    rx = ""
    for i, lit in enumerate(parts):
        rx += re.escape(lit)
        if i < len(holes):
            rx += r"[\s\S]{0,%d}?" % _PARAM_VALUE_MAX
    return re.compile(rx + r"$")


def action_allowed(code: str, templates: list):
    """posted code 가 선언 템플릿의 인스턴스인가 — (허용여부, 사유)."""
    step = _parse_single(code)
    if step is None:
        return False, "허용되지 않는 형식입니다 (단일 계기 동작만 가능)"
    node, action, params = step["_node"], step["action"], step.get("params") or {}
    if node in {"self", "others"}:
        return False, "허용되지 않는 동작입니다"
    for k, v in params.items():
        if isinstance(v, (dict, list)):
            return False, "허용되지 않는 파라미터 형식입니다"
        if isinstance(v, str) and len(v) > _PARAM_VALUE_MAX:
            return False, "입력이 너무 깁니다"
    for t in templates:
        ts = _parse_single(t)
        if ts is None or ts["_node"] != node or ts["action"] != action:
            continue
        tp = ts.get("params") or {}
        ok = True
        for k, v in params.items():
            if k not in tp:
                ok = False
                break
            tv = tp[k]
            if isinstance(tv, str) and _PLACEHOLDER_RE.search(tv):
                if not _value_regex(tv).match(str(v)):
                    ok = False
                    break
            elif v != tv and str(v) != str(tv):
                ok = False
                break
        if not ok:
            continue
        # 템플릿의 리터럴 파라미터는 생략 불가(op·mode 강제) — 플레이스홀더 자리만 생략 허용.
        for k, tv in tp.items():
            if isinstance(tv, str) and _PLACEHOLDER_RE.search(tv):
                continue
            if k not in params:
                ok = False
                break
        if ok:
            return True, ""
    return False, "이 계기에 선언되지 않은 동작입니다"


class PortalDenied(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status
        self.msg = msg


def authorize_and_count(slug: str, iid: str, member_key: str, ip: str) -> dict:
    """회원/손님·레벨·한도를 원자적으로 검사하고 사용량을 센다. 통과 시 viewer 정보 반환."""
    universe = {u["key"]: u for u in listable_universe(load_state())}
    if iid not in universe or universe[iid]["kind"] != "instrument":
        raise PortalDenied(404, "그런 계기가 없습니다")

    result = {}

    def _fn(state):
        portal = portal_by_slug(state, slug)
        if not portal:
            raise PortalDenied(404, "그런 포털이 없습니다")
        d = display_entry(portal, universe[iid])
        if not d.get("enabled"):
            raise PortalDenied(403, "지금은 열려 있지 않은 계기입니다")
        viewer = find_member(portal, key=member_key) if member_key else None
        ml = int(d.get("min_level", 1))
        t = _today()
        if viewer:
            if int(viewer.get("level", 0)) < ml:
                raise PortalDenied(403, f"레벨 {ml} 이상 회원만 쓸 수 있어요")
            per = int(d.get("member_daily", 0))
            u = viewer.setdefault("usage", {}).setdefault(iid, {})
            if per and int(u.get(t, 0)) >= per:
                raise PortalDenied(429, f"오늘 사용 한도({per}회)에 도달했어요 — 내일 다시 만나요")
            u[t] = int(u.get(t, 0)) + 1
            # 날짜 키 청소(최근 14일만)
            for k in [k for k in u if k < t and (len(u) > 14)]:
                u.pop(k, None)
            viewer["last_used"] = _now()
            result["who"] = f"{viewer['name']}({viewer['id']})"
            result["member"] = {"id": viewer["id"], "name": viewer["name"], "level": viewer["level"]}
        else:
            if ml > 0:
                raise PortalDenied(403, "회원 전용 계기입니다 — 로그인해 주세요")
            per = int(d.get("guest_daily", 0))
            if per:
                n = _guest_count(ip, slug + ":" + iid)
                if n >= per:
                    raise PortalDenied(429, f"오늘 손님 한도({per}회)에 도달했어요")
                _guest_bump(ip, slug + ":" + iid)
            result["who"] = f"guest:{ip}"
            result["member"] = None
        gcap = int(d.get("global_daily", 0))
        g = portal.setdefault("usage_global", {}).setdefault(iid, {})
        if gcap and int(g.get(t, 0)) >= gcap:
            raise PortalDenied(429, "오늘은 이 계기가 쉬는 시간이에요 (전체 한도 도달)")
        g[t] = int(g.get(t, 0)) + 1
        for k in [k for k in g if k < t and (len(g) > 14)]:
            g.pop(k, None)

    mutate_state(_fn)
    return result


# 손님 IP별 일일 카운터 — 메모리(백엔드 재시작 시 리셋 허용, 전역 캡이 최종 방어선)
_GUEST_COUNTS = {}


def _guest_count(ip: str, iid: str) -> int:
    return _GUEST_COUNTS.get((_today(), ip or "?", iid), 0)


def _guest_bump(ip: str, iid: str) -> None:
    k = (_today(), ip or "?", iid)
    _GUEST_COUNTS[k] = _GUEST_COUNTS.get(k, 0) + 1
    if len(_GUEST_COUNTS) > 20000:
        t = _today()
        for kk in [kk for kk in _GUEST_COUNTS if kk[0] != t]:
            _GUEST_COUNTS.pop(kk, None)


_JOIN_LAST_BY_IP = {}


def join_rate_ok(ip: str) -> bool:
    now = time.time()
    if ip and now - _JOIN_LAST_BY_IP.get(ip, 0) < _JOIN_MIN_INTERVAL_S:
        return False
    _JOIN_LAST_BY_IP[ip] = now
    return True


_LOGIN_TRIES = {}   # ip -> [timestamps] — 로그인 무차별 대입 방어(분당 10회)


def login_rate_ok(ip: str) -> bool:
    now = time.time()
    tries = [t for t in _LOGIN_TRIES.get(ip or "?", []) if now - t < 60]
    if len(tries) >= 10:
        _LOGIN_TRIES[ip or "?"] = tries
        return False
    tries.append(now)
    _LOGIN_TRIES[ip or "?"] = tries
    return True


_RESET_HITS = {}   # 이메일/ip -> [timestamps] — 재설정 메일 폭탄 방어


def reset_rate_ok(key: str) -> bool:
    """비밀번호 재설정 요청 제한 — 같은 키(이메일·ip) 5분에 1회, 하루 5회."""
    now = time.time()
    hits = [t for t in _RESET_HITS.get(key or "?", []) if now - t < 86400]
    if len(hits) >= 5 or (hits and now - hits[-1] < 300):
        _RESET_HITS[key or "?"] = hits
        return False
    hits.append(now)
    _RESET_HITS[key or "?"] = hits
    return True


# ── 감사로그 ─────────────────────────────────────────────────────────────

def audit_log(who: str, instrument: str, code: str, ok: bool, note: str = "",
              portal: str = "") -> None:
    try:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        if _AUDIT_PATH.exists() and _AUDIT_PATH.stat().st_size > _AUDIT_MAX_BYTES:
            lines = _AUDIT_PATH.read_text(encoding="utf-8").splitlines()[-2000:]
            _AUDIT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        entry = {"at": _now(), "who": who, "instrument": instrument,
                 "code": (code or "")[:300], "ok": bool(ok)}
        if portal:
            entry["portal"] = portal[:40]
        if note:
            entry["note"] = note[:200]
        with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass


def audit_tail(limit: int = 100) -> list:
    try:
        lines = _AUDIT_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for ln in reversed(lines):
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        return out
    except Exception:
        return []


def load_shared(path: Path, name: str):
    """공유 모듈 로더 — sys.modules 캐시로 프로세스당 1 인스턴스."""
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod
