"""bulletin/handler.py — 자유게시판 (라이브 서빙, 인덱싱 없음).

게시판 메타는 상태 파일(data/bulletin/state.json), 글은 게시판별 posts.json 에 즉석 append.
공개 방문자는 로그인 없이 /b/<slug>/ 에서 글을 쓰고, 맥이 요청 시 서빙(backend/api_bulletin.py).
이 핸들러는 운영자 어휘 — 게시판 CRUD + 글 삭제(모더레이션). 상태·글 로직은 bulletin_core.

이음매(헌법 1조): 공개 Worker(substrate)는 slug 게이트 + 프록시만. 맥(superstructure)이
게시판을 검증하고 글을 저장·서빙. 포털 붙임은 portal_core.listable_universe 가 board:<slug>
콘텐츠 타일을 유도 — [others:portal]{op:display} 다이얼이 그대로 작동한다.
"""

import sys
import json
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[5]
_BACKEND = str(_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from common.currency import items  # IBL 단일 통화 생성자

_CORE = None


def _core():
    """bulletin_core 를 sys.modules 공유 키로 로드 — api_bulletin 과 같은 인스턴스(flock·IP캐시 공유)."""
    global _CORE
    if _CORE is not None:
        return _CORE
    key = "indiebiz_bulletin_core"
    if key in sys.modules:
        _CORE = sys.modules[key]
        return _CORE
    p = Path(__file__).resolve().parent / "bulletin_core.py"
    spec = importlib.util.spec_from_file_location(key, str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[key] = mod
    _CORE = mod
    return mod


def _as_bool(v) -> bool:
    return str(v).lower() in ("true", "1", "yes", "on")


def _err(msg: str) -> str:
    return json.dumps(items([], success=False, message=msg), ensure_ascii=False)


# ── 게시판 op ────────────────────────────────────────────────────────────

def _status(params: dict) -> str:
    c = _core()
    state = c.load_state()
    settings = state["settings"]
    rows = [c.board_row(settings, b) for b in state["boards"]]
    return json.dumps(items(rows, settings=settings, public_base=settings.get("public_base", "")),
                      ensure_ascii=False)


def _create(params: dict) -> str:
    c = _core()
    title = (params.get("title") or "").strip()
    if not title:
        return _err("게시판 이름을 입력해 주세요.")
    ai = params.get("allow_images")
    allow_images = _as_bool(ai) if ai not in (None, "") else True
    b = c.create_board(title, allow_images=allow_images)
    state = c.load_state()
    row = c.board_row(state["settings"], b)
    return json.dumps(items([row], success=True,
                            message=f"'{row['title']}' 게시판 생성 — 주소가 만들어졌습니다. 공유하면 누구나 글을 쓸 수 있어요."),
                      ensure_ascii=False)


def _config(params: dict) -> str:
    c = _core()
    bid = (params.get("board_id") or "").strip()
    if bid:
        ai = params.get("allow_images")
        ret = c.config_board(
            bid,
            title=(params.get("title") if (params.get("title") or "").strip() else None),
            allow_images=(_as_bool(ai) if ai not in (None, "") else None),
        )
        if isinstance(ret, dict) and ret.get("_err"):
            return _err(ret["_err"])
        state = c.load_state()
        row = c.board_row(state["settings"], ret)
        return json.dumps(items([row], success=True, message=f"'{row['title']}' 저장."), ensure_ascii=False)
    # 전역 설정 (public_base)
    def _do(state):
        if params.get("public_base"):
            state["settings"]["public_base"] = params.get("public_base")
    c.mutate_state(_do)
    state = c.load_state()
    return json.dumps(items([], settings=state["settings"], success=True, message="설정 저장."), ensure_ascii=False)


def _delete(params: dict) -> str:
    c = _core()
    bid = (params.get("board_id") or "").strip()
    ret = c.delete_board(bid)
    if isinstance(ret, dict) and ret.get("_err"):
        return _err(ret["_err"])
    return json.dumps(items([], success=True, message="게시판 삭제 — 주소·글·사진이 모두 사라졌습니다."),
                      ensure_ascii=False)


def _detail(params: dict) -> str:
    c = _core()
    bid = (params.get("board_id") or "").strip()
    state = c.load_state()
    b = c.get_board(state, bid)
    if not b:
        return _err("게시판을 찾을 수 없습니다.")
    row = c.board_row(state["settings"], b)
    posts = list(reversed(c.load_posts(b["id"])))[:200]   # 최신 먼저, 모더레이션용
    post_rows = []
    for p in posts:
        body = (p.get("body") or "").replace("\n", " ")
        if len(body) > 80:
            body = body[:80] + "…"
        img = " 🖼" if p.get("image") else ""
        post_rows.append({
            "id": p.get("id"),
            "title": f"{p.get('name', '')}{img}",
            "meta": f"{p.get('at', '')} · {body}",
            "board_id": b["id"],
        })
    note = "주소를 아는 사람은 로그인 없이 글을 씁니다. 부적절한 글은 아래에서 삭제하세요."
    return json.dumps(items([row], board=row, posts=post_rows, note=note, settings=state["settings"]),
                      ensure_ascii=False)


def _portals(params: dict) -> str:
    """이 게시판을 붙일 수 있는 포털 목록 + 현재 붙임 상태(읽기).

    실제 붙임/떼기는 정식 [others:portal]{op:display} 로 한다(여기선 목록·상태만 읽음 —
    portal_core.listable_universe 가 read 하는 것과 같은 저결합 파일 읽기). 각 행에 붙임
    상태와 다음 동작(enabled_next/min_level_next/action)을 미리 도장 찍어, 앱 버튼 하나가
    현재 상태에 따라 붙이기↔떼기로 뒤집히게 한다."""
    c = _core()
    bid = (params.get("board_id") or "").strip()
    state = c.load_state()
    b = c.get_board(state, bid)
    if not b:
        return _err("게시판을 찾을 수 없습니다.")
    key = f"board:{b['slug']}"
    try:
        pst = json.loads((_ROOT / "data" / "portal_state.json").read_text(encoding="utf-8"))
        portals = pst.get("portals", [])
    except Exception:
        portals = []
    rows = []
    for p in portals:
        entry = ((p.get("display") or {}).get(key) or {})
        attached = bool(entry.get("enabled"))
        rows.append({
            "portal_slug": p.get("slug", ""),
            "portal_title": p.get("title", p.get("slug", "")),
            "board_key": key,
            "title": p.get("title", p.get("slug", "")),
            "meta": ("✅ 이 포털에 붙어 있음" if attached else "➕ 붙이기 가능"),
            "attached": attached,
            "action": ("떼기" if attached else "붙이기"),
            "enabled_next": ("false" if attached else "true"),
            "min_level_next": "0",   # 자유게시판=손님(0)까지 열어 누구나 보임
        })
    note = ("포털에 붙이면 그 포털 홈에서 이 게시판으로 들어갈 수 있습니다. "
            "붙임/떼기는 포털별로 따로 저장돼요.") if portals else \
           "아직 포털이 없습니다. 먼저 포털 앱에서 포털을 만드세요."
    row = c.board_row(state["settings"], b)
    return json.dumps(items(rows, board=row, note=note, settings=state["settings"]), ensure_ascii=False)


def _post_delete(params: dict) -> str:
    c = _core()
    bid = (params.get("board_id") or "").strip()
    pid = (params.get("post_id") or "").strip()
    if c.delete_post(bid, pid):
        return json.dumps(items([], success=True, message="글을 삭제했습니다."), ensure_ascii=False)
    return _err("글을 찾을 수 없습니다.")


_OP_DISPATCHERS = {
    "bulletin_op": {
        "status": _status,
        "create": _create,
        "config": _config,
        "delete": _delete,
        "detail": _detail,
        "post_delete": _post_delete,
        "portals": _portals,
    },
}
_OP_DEFAULTS = {"bulletin_op": "status"}


def execute(tool_input: dict, context) -> str:
    """게시판 도구 실행 (ToolContext 시그니처)."""
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
