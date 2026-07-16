"""community-portal/handler.py — 개인 포털(커뮤니티 홈) 운영자 어휘 [others:portal].

"커뮤니티당 노드 하나" 전략의 홈. **포털은 여러 개** — 대상별 공개 주소(가족용·친구용…,
showcase 바스켓 패턴)이고, 각 포털이 자기 회원 명부·진열 다이얼을 가진다. 이 핸들러는
운영자 쪽 제어(포털 생성·이웃 승급·개인 링크·진열 다이얼·감사로그)만 담당 — 공개 서빙·
가입/로그인·회원 실행 게이트는 backend/api_portal.py, 상태·게이트 로직은 portal_core.py.

대부분 op 는 `portal` 파라미터(slug/이름/id)로 대상 포털을 고른다 — 비우면 첫 포털.
"""

import sys
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[5]
_BACKEND = str(_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from common.currency import items  # IBL 단일 통화 생성자

import importlib.util as _ilu


def _core():
    """portal_core 공유 인스턴스 (api_portal 과 같은 sys.modules 키)."""
    name = "indiebiz_portal_core"
    mod = sys.modules.get(name)
    if mod is None:
        p = Path(__file__).with_name("portal_core.py")
        spec = _ilu.spec_from_file_location(name, str(p))
        mod = _ilu.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


def _ok(rows, **extra) -> str:
    return json.dumps(items(rows, **extra), ensure_ascii=False)


def _fail(msg: str) -> str:
    return json.dumps(items([], success=False, message=msg), ensure_ascii=False)


def _get_portal(core, params: dict):
    """상태 로드 + portal 해소 (없으면 기본 포털 생성). (state, portal) 반환."""
    holder = {}

    def _fn(st):
        core.ensure_default_portal(st)
        holder["p"] = core.portal_by_ref(st, params.get("portal") or "")

    state = core.mutate_state(_fn)
    return state, holder["p"]


def _member_rows(core, state, portal) -> list:
    rows = []
    for m in portal.get("members", []):
        lv = int(m.get("level", 0))
        meta = f"가입 {m.get('joined_at', '')}"
        if m.get("login_id"):
            meta += f" · 아이디 {m['login_id']}"
        else:
            meta += " · 링크 전용"
        if m.get("contact"):
            meta += f" · {m['contact']}"
        if m.get("last_used"):
            meta += f" · 최근 {m['last_used']}"
        meta += f" · 오늘 {core.member_usage_today(m)}회"
        if m.get("revoked"):
            meta += " · ⛔ 회수됨"
        rows.append({
            "id": m.get("id", ""),
            "portal": portal.get("slug", ""),
            "name": m.get("name", ""),
            "level": lv,
            "level_label": f"레벨 {lv} ({core.LEVEL_LABELS.get(lv, lv)})" + (" ⛔" if m.get("revoked") else ""),
            "meta": meta,
            "key_hint": "⛔ 회수됨 — 재발급하면 새 링크·재로그인" if m.get("revoked")
                        else f"레벨 {lv} · " + ("아이디 로그인 가능" if m.get("login_id") else "링크로만 입장"),
            "key_link": "(회수됨)" if m.get("revoked") else core.member_link(state, portal, m),
        })
    return rows


def _settings_of(core, state, portal) -> dict:
    """설정 탭에 채울 값 — 이름·소개·공개 base + 포털 일일 한도(손님/회원/전체)."""
    lim = portal.get("limits") or {}
    return {
        "title": portal.get("title"),
        "intro": portal.get("intro"),
        "public_base": state.get("public_base"),
        "guest_daily": lim.get("guest_daily", 3),
        "member_daily": lim.get("member_daily", 50),
        "global_daily": lim.get("global_daily", 300),
    }


def _portal_kv(core, state, portal) -> dict:
    return {
        "url": core.portal_url(state, portal),
        "slug": portal.get("slug", ""),
        "title": portal.get("title", ""),
        "member_count": len(portal.get("members", [])),
        "usage_today": core.usage_global_today(portal),
        "display_on": sum(1 for u in core.listable_universe(state)
                          if core.display_entry(portal, u).get("enabled")),
    }


def _portal_row(core, state, p) -> dict:
    return {
        "id": p.get("id", ""),
        "slug": p.get("slug", ""),
        "title": p.get("title", ""),
        "label": f"{p.get('title','')} ({p.get('slug','')})",
        "url": core.portal_url(state, p),
        "meta": f"회원 {len(p.get('members', []))}명 · 진열 "
                f"{sum(1 for u in core.listable_universe(state) if core.display_entry(p, u).get('enabled'))}개 · "
                f"오늘 {core.usage_global_today(p)}회",
    }


# ── op 구현 ─────────────────────────────────────────────────────────────

def _fn_portals(params: dict) -> str:
    """포털 목록 — 관리 계기 셀렉터(options_action)와 개요 카드 공용."""
    core = _core()
    state, _ = _get_portal(core, {})
    rows = [_portal_row(core, state, p) for p in state["portals"]]
    return _ok(rows, message="" if rows else "포털이 없습니다 — 아래에서 만들어 보세요.")


def _fn_create(params: dict) -> str:
    core = _core()
    holder = {}

    def _fn(st):
        holder["p"] = core.create_portal(st, params.get("title") or "")

    try:
        state = core.mutate_state(_fn)
    except ValueError as e:
        return _fail(str(e))
    p = holder["p"]
    url = core.portal_url(state, p)
    core.audit_log("operator", "portal", f"create {p['title']}", True, portal=p["slug"])
    return _ok([], success=True, url=url,
               message=f"'{p['title']}' 포털 생성 — 주소: {url} (진열 탭에서 이 포털에 보여줄 것을 켜세요)")


def _fn_remove(params: dict) -> str:
    core = _core()
    ref = (params.get("portal") or "").strip()
    if not ref:
        return _fail("지울 포털을 지정해 주세요 (portal: 슬러그 또는 이름).")
    holder = {}

    def _fn(st):
        p = core.portal_by_ref(st, ref)
        if not p:
            raise ValueError(f"포털을 찾을 수 없습니다: {ref}")
        if p.get("members") and str(params.get("force")).lower() not in ("true", "1"):
            raise ValueError(f"회원 {len(p['members'])}명이 있는 포털입니다 — 정말 지우려면 force: true")
        st["portals"] = [x for x in st["portals"] if x["id"] != p["id"]]
        holder["p"] = p

    try:
        core.mutate_state(_fn)
    except ValueError as e:
        return _fail(str(e))
    p = holder["p"]
    core.audit_log("operator", "portal", f"remove {p['title']}", True, portal=p["slug"])
    return _ok([], success=True, message=f"'{p['title']}' 포털 삭제 — 주소·회원·다이얼이 함께 사라졌습니다.")


def _fn_status(params: dict) -> str:
    core = _core()
    state, portal = _get_portal(core, params)
    msg = ("" if portal.get("members") else
           "아직 이웃이 없습니다 — 홈 주소를 공유하면 가입(아이디·비밀번호)이 들어오고, "
           "승급해야 회원 계기가 열립니다.")
    return _ok([], portal=_portal_kv(core, state, portal),
               settings=_settings_of(core, state, portal),
               message=msg)


def _fn_members(params: dict) -> str:
    core = _core()
    state, portal = _get_portal(core, params)
    rows = _member_rows(core, state, portal)
    msg = "" if rows else f"'{portal.get('title')}' 포털에 아직 이웃이 없습니다. 홈 주소를 공유하거나 아래에서 직접 등록하세요."
    return _ok(rows, portal=_portal_kv(core, state, portal), message=msg)


def _fn_join(params: dict) -> str:
    """운영자가 이웃을 직접 등록(링크 전용 회원) — 공개 홈의 셀프 가입과 별개 경로."""
    core = _core()
    name = (params.get("name") or "").strip()
    if not name:
        return _fail("이름을 입력해 주세요.")
    holder = {}

    def _fn(st):
        core.ensure_default_portal(st)
        p = core.portal_by_ref(st, params.get("portal") or "")
        m = core.create_member(p, name, params.get("contact") or "",
                               int(params.get("level") or 0))
        holder["p"] = p
        holder["link"] = core.member_link(st, p, m)

    try:
        core.mutate_state(_fn)
    except ValueError as e:
        return _fail(str(e))
    core.audit_log("operator", "portal", f"join {name}", True, portal=holder["p"]["slug"])
    return _ok([], success=True, link=holder["link"],
               message=f"{name} 등록({holder['p']['title']}) — 개인 링크(자동 로그인)를 본인에게만 전달하세요: {holder['link']}")


def _member_op(params: dict, fn, done_msg):
    """member_id 로 회원을 찾아 fn(state, portal, member) 적용하는 공통 틀."""
    core = _core()
    mid = (params.get("member_id") or "").strip()
    holder = {}

    def _mut(st):
        core.ensure_default_portal(st)
        p = core.portal_by_ref(st, params.get("portal") or "")
        m = core.find_member(p, member_id=mid)
        if not m:
            # portal 미지정 시 전 포털에서 탐색 (행 버튼이 portal 을 실어 오지만 방어)
            if not (params.get("portal") or "").strip():
                for cand in st["portals"]:
                    m = core.find_member(cand, member_id=mid)
                    if m:
                        p = cand
                        break
        if not m:
            raise ValueError(f"회원을 찾을 수 없습니다: {mid}")
        fn(st, p, m)
        holder["p"], holder["m"] = p, dict(m)

    try:
        core.mutate_state(_mut)
    except ValueError as e:
        return _fail(str(e))
    p, m = holder["p"], holder["m"]
    core.audit_log("operator", "portal", done_msg(m), True, portal=p["slug"])
    return core, p, m


def _fn_promote(params: dict) -> str:
    core = _core()
    down = str(params.get("down")).lower() in ("true", "1")

    def _apply(st, p, m):
        if params.get("level") not in (None, ""):
            m["level"] = max(0, min(core.LEVEL_MAX, int(float(params["level"]))))
        else:
            m["level"] = max(0, min(core.LEVEL_MAX, int(m.get("level", 0)) + (-1 if down else 1)))

    r = _member_op(params, _apply, lambda m: f"promote {m['name']} → {m['level']}")
    if isinstance(r, str):
        return r
    core, p, m = r
    return _ok([], success=True,
               message=f"{m['name']} → 레벨 {m['level']} ({core.LEVEL_LABELS.get(m['level'])})")


def _fn_issue(params: dict) -> str:
    import secrets as _sec

    def _apply(st, p, m):
        m["key"] = _sec.token_urlsafe(18)
        m["revoked"] = False

    r = _member_op(params, _apply, lambda m: f"issue {m['name']}")
    if isinstance(r, str):
        return r
    core, p, m = r
    state = core.load_state()
    p2 = core.portal_by_ref(state, p["slug"])
    m2 = core.find_member(p2, member_id=m["id"])
    link = core.member_link(state, p2, m2)
    return _ok([], success=True, link=link,
               message=f"{m['name']} 새 링크: {link} (옛 링크·로그인 세션은 무효 — 비밀번호는 그대로)")


def _fn_revoke(params: dict) -> str:
    def _apply(st, p, m):
        m["revoked"] = True

    r = _member_op(params, _apply, lambda m: f"revoke {m['name']}")
    if isinstance(r, str):
        return r
    core, p, m = r
    return _ok([], success=True,
               message=f"{m['name']} 회수 — 링크·쿠키·아이디 로그인이 전부 막힙니다 (재발급으로 복구).")


def _fn_display(params: dict) -> str:
    """진열 다이얼(포털별) — key 없으면 목록, key 있으면 사다리/직접 값."""
    core = _core()
    key = (params.get("key") or "").strip()
    state, portal = _get_portal(core, params)
    universe = core.listable_universe(state)
    by_key = {u["key"]: u for u in universe}

    if key:
        if key not in by_key:
            return _fail(f"'{key}' 는 진열 가능 목록 밖입니다 — 사적/몸/발신 계기는 다이얼이 없습니다.")
        pref = portal.get("slug", "")

        def _fn(st):
            p = core.portal_by_ref(st, pref)
            cur = p.setdefault("display", {}).setdefault(key, {})
            base = core.display_entry(p, by_key[key])
            if str(params.get("toggle")).lower() in ("true", "1"):
                cur["enabled"] = not base.get("enabled")
            # 사다리 다이얼: 꺼짐(∞ 잠금) ↔ 2 가족만 ↔ 1 이웃부터 ↔ 0 손님도.
            ml = int(base.get("min_level", 1))
            if str(params.get("level_up")).lower() in ("true", "1"):
                if base.get("enabled"):
                    if ml >= core.LEVEL_MAX:
                        cur["enabled"] = False
                    else:
                        cur["min_level"] = ml + 1
            if str(params.get("level_down")).lower() in ("true", "1"):
                if not base.get("enabled"):
                    cur["enabled"] = True
                    cur["min_level"] = core.LEVEL_MAX
                elif ml > 0:
                    cur["min_level"] = ml - 1
            for f in ("min_level", "guest_daily", "member_daily", "global_daily"):
                if params.get(f) not in (None, ""):
                    cur[f] = max(0, int(float(params[f])))
            if params.get("enabled") not in (None, ""):
                cur["enabled"] = str(params["enabled"]).lower() in ("true", "1")
            for f in ("min_level", "guest_daily", "member_daily", "global_daily"):
                cur.setdefault(f, base.get(f))
            cur.setdefault("enabled", base.get("enabled", False))

        state = core.mutate_state(_fn)
        portal = core.portal_by_ref(state, pref)
        d = core.display_entry(portal, by_key[key])
        onoff = "켜짐" if d.get("enabled") else "꺼짐"
        return _ok([], success=True,
                   message=f"[{portal.get('title')}] {by_key[key]['name']}: {onoff} · 레벨 {d['min_level']}+ · "
                           f"손님 {d['guest_daily']}/일 · 회원 {d['member_daily']}/일")

    rows = []
    for u in universe:
        d = core.display_entry(portal, u)
        rows.append({
            "key": u["key"], "icon": u["icon"], "name": u["name"], "kind": u["kind"],
            "portal": portal.get("slug", ""),
            "state": ("🟢 켜짐" if d.get("enabled") else "⚪ 꺼짐") + f" · 레벨 {d.get('min_level')}+",
            "meta": f"{u['key']} · 손님 {d.get('guest_daily')}/일 · 회원 {d.get('member_daily')}/일"
                    + (f" · 전체 {d.get('global_daily')}/일" if d.get("global_daily") else "")
                    + (" · 콘텐츠" if u["kind"] == "content" else ""),
        })
    return _ok(rows, portal=_portal_kv(core, state, portal),
               message="" if rows else "진열 가능한 계기·콘텐츠가 없습니다.")


def _fn_audit(params: dict) -> str:
    core = _core()
    limit = int(params.get("limit") or 100)
    rows = [{
        "title": f"{e.get('who', '?')} · {e.get('instrument', '')}"
                 + ("" if e.get("ok") else " · ❌ 거부"),
        "meta": e.get("at", "") + (f" · 포털 {e.get('portal')}" if e.get("portal") else "")
                + (f" · {e.get('note')}" if e.get("note") else ""),
        "summary": e.get("code", ""),
    } for e in core.audit_tail(limit)]
    return _ok(rows, message="" if rows else "아직 기록이 없습니다.")


def _fn_config(params: dict) -> str:
    core = _core()
    changed = []
    pref = (params.get("portal") or "").strip()

    def _fn(st):
        core.ensure_default_portal(st)
        p = core.portal_by_ref(st, pref)
        if (params.get("title") or "").strip():
            p["title"] = params["title"].strip()[:40]
            changed.append("이름")
        if params.get("intro") is not None and str(params.get("intro")).strip() != "":
            p["intro"] = str(params["intro"]).strip()[:500]
            changed.append("소개")
        if (params.get("public_base") or "").strip():
            st["public_base"] = params["public_base"].strip()
            changed.append("공개 base")
        # 포털 일일 한도(손님/회원/전체) — 설정 탭에서 사용자가 정한다.
        lim = p.setdefault("limits", {})
        _labels = {"guest_daily": "손님 한도", "member_daily": "회원 한도", "global_daily": "전체 한도"}
        for k in ("guest_daily", "member_daily", "global_daily"):
            v = params.get(k)
            if v is None or str(v).strip() == "":
                continue
            try:
                lim[k] = max(0, int(float(str(v).strip())))
                changed.append(_labels[k])
            except (ValueError, TypeError):
                pass

    state = core.mutate_state(_fn)
    portal = core.portal_by_ref(state, pref)
    return _ok([], success=True,
               settings=_settings_of(core, state, portal),
               portal=_portal_kv(core, state, portal),
               message=("저장: " + ", ".join(changed)) if changed else "변경 없음.")


_OP_DISPATCHERS = {
    "portal_op": {
        "status": _fn_status,
        "portals": _fn_portals,
        "create": _fn_create,
        "remove": _fn_remove,
        "members": _fn_members,
        "join": _fn_join,
        "promote": _fn_promote,
        "issue": _fn_issue,
        "revoke": _fn_revoke,
        "display": _fn_display,
        "audit": _fn_audit,
        "config": _fn_config,
    },
}
_OP_DEFAULTS = {
    "portal_op": "status",
}


def execute(tool_input: dict, context) -> str:
    """포털 도구 실행 (ToolContext 시그니처)."""
    tool_name = context.tool_name
    try:
        if tool_name in _OP_DISPATCHERS:
            op = tool_input.get("op") or _OP_DEFAULTS.get(tool_name)
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if not fn:
                return json.dumps({"success": False, "message": f"알 수 없는 op: {op}"}, ensure_ascii=False)
            return fn(tool_input)
        return f"Unknown tool: {tool_name}"
    except Exception as e:
        return json.dumps({"success": False, "message": f"오류: {e}"}, ensure_ascii=False)
