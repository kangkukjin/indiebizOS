"""
handler.py - lecture_workspace 패키지 도구 디스패처

ToolContext 시그니처: execute(tool_input, context) -> str

데이터 레이어는 lecture_store 모듈에 모두 모여 있고, 이 파일은 도구 이름으로 분기 + 입력 검증 + JSON 응답 포맷만 담당.

Step 1 (현재): 강의 CRUD + 데크 조작 + 재료 관리 + lecture_open 스텁.
Step 2/3에서 추가 예정: slide_create, slide_edit (AI 슬라이드 생성/편집).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# lecture_store / slide_ai / lecture_export를 같은 디렉토리에서 import
sys.path.insert(0, os.path.dirname(__file__))
# backend 모듈(project_manager 등) import 보장 (인프로세스에선 보통 이미 path에 있음)
_BACKEND_DIR = str(Path(__file__).resolve().parents[5] / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
import lecture_store  # noqa: E402
import slide_ai  # noqa: E402
import lecture_export  # noqa: E402
import slide_edit_ops  # noqa: E402  (image_edit·글자 얹기 — 1500줄 규칙 분할 2026-08-10)

# 분할 이전 이름으로 부르는 내부 호출·디스패처를 위한 별칭
_BAKED_LAYOUTS = slide_edit_ops.BAKED_LAYOUTS
_load_slide_native = slide_edit_ops.load_slide_native
_load_slide_overlay = slide_edit_ops.load_slide_overlay
_discard_overlay_state = slide_edit_ops.discard_overlay_state
_slide_image_edit = slide_edit_ops.slide_image_edit


# 앱/수동 모드가 쓰는 시스템 프로젝트 — 이들이 만든 강의는 전역에 둔다(현행 유지).
SYSTEM_PROJECT_IDS = {"앱모드", "수동모드"}


def _project_path_for(project_id: str):
    """project_id → 프로젝트 절대경로 (ProjectManager). 실패 시 None."""
    try:
        from project_manager import ProjectManager
        p = ProjectManager().get_project_path(project_id)
        if p and Path(p).exists():
            return str(Path(p).resolve())
    except Exception as e:
        print(f"[lecture_workspace] project_path 해석 실패 ({project_id}): {e}")
    return None


def _apply_roots(context) -> None:
    """ToolContext로부터 강의 쓰기/검색 루트를 해석해 lecture_store에 주입.

    원칙: 프로젝트 에이전트가 만든 강의는 그 프로젝트 outputs/lectures 아래.
          앱/수동 모드·시스템 AI·프로젝트 미상 → 전역 outputs/lectures (현행 유지).
    읽기는 [프로젝트, 전역] 순으로 폴백 — 전역에 있던 기존 강의도 계속 읽힌다.
    """
    try:
        global_root = lecture_store._global_lectures_root()
        pid = getattr(context, "project_id", None)
        agent_id = getattr(context, "agent_id", None)

        project_dir = None
        if pid and pid not in SYSTEM_PROJECT_IDS and agent_id != "system_ai":
            project_dir = _project_path_for(pid)

        if project_dir:
            project_root = Path(project_dir) / "outputs" / "lectures"
            lecture_store.set_roots(project_root, [project_root, global_root])
        else:
            lecture_store.set_roots(global_root, [global_root])
    except Exception as e:
        # 실패 시 전역으로 안전 폴백
        try:
            g = lecture_store._global_lectures_root()
            lecture_store.set_roots(g, [g])
        except Exception:
            pass
        print(f"[lecture_workspace] 루트 해석 실패, 전역 폴백: {e}")


def _ok(payload: dict) -> str:
    """성공 응답 — payload를 JSON 문자열로."""
    return json.dumps({"success": True, **payload}, ensure_ascii=False, indent=2)


def _err(message: str, **extra) -> str:
    """에러 응답."""
    return json.dumps({"success": False, "error": message, **extra}, ensure_ascii=False, indent=2)


def execute(tool_input: dict, context) -> str:
    """도구 실행 entry point (ToolContext 기반).

    통합 도구 (op 분기) — IBL 어휘에 노출되는 4개. REST(api_lecture_workspace.py)도
    2026-07-02부터 이 정본 이름(slide_op 등 + op)으로만 호출 → 옛 내부 tool명 직접
    분기(slide_create·lecture_list 등)는 전부 사망해 제거. 분기는 파일 끝
    _OP_DISPATCHERS 진짜 함수 테이블(--check 가 AST 로 키 정확 비교).
    """
    tool_name = context.tool_name

    # 호출 컨텍스트(프로젝트 에이전트 vs 앱모드)에 따라 강의 저장/검색 루트 결정.
    _apply_roots(context)

    try:
        table = _OP_DISPATCHERS.get(tool_name)
        if table is None:
            return _err(f"알 수 없는 도구: {tool_name}")
        ops = "|".join(table)
        op = (tool_input.get("op") or "").strip()
        if not op:  # 모두 op 필수 — _OP_DEFAULTS 없음.
            return _err(f"op는 필수입니다. ({ops})")
        fn = table.get(op)
        if fn is None:
            return _err(f"알 수 없는 op: {op}. ({ops} 중 하나)")
        return fn(tool_input)
    except FileNotFoundError as e:
        return _err(str(e), error_type="not_found")
    except ValueError as e:
        return _err(str(e), error_type="validation")
    except Exception as e:
        return _err(f"실행 중 예외: {e}", error_type=type(e).__name__)


# ─────────────────────────────────────────────────────────────────────
# 강의 CRUD
# ─────────────────────────────────────────────────────────────────────

def _lecture_list(tool_input: dict) -> str:
    lectures = lecture_store.list_lectures()
    records = [{
        "title": lec.get("title") or lec.get("lecture_id") or "(제목 없음)",
        "meta": " · ".join(p for p in [
            lec.get("audience") or None,
            (f"{lec.get('slide_count')}슬라이드" if lec.get("slide_count") is not None else None),
        ] if p),
        "summary": None,
        "url": None,
    } for lec in lectures]
    return _ok({
        "lectures": lectures,
        "count": len(lectures),
        "lectures_root": str(lecture_store.write_root().resolve()),
        "items": records,
    })


def _lecture_create(tool_input: dict) -> str:
    title = (tool_input.get("title") or "").strip()
    if not title:
        return _err("title은 필수입니다.")
    deck = lecture_store.create_lecture(
        title=title,
        audience=tool_input.get("audience"),
        thesis=tool_input.get("thesis"),
        duration_minutes=tool_input.get("duration_minutes"),
        # 2026-06-23: 기본값을 native(통짜 이미지, NotebookLM식)로. 텍스트형 톤은 명시 지정.
        design_system=tool_input.get("design_system") or "native_vintage_book",
    )
    return _ok({
        "lecture_id": deck["lecture_id"],
        "deck": deck,
        "lecture_dir": str(lecture_store.lecture_dir(deck["lecture_id"]).resolve()),
    })


def _lecture_load(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    data = lecture_store.load_lecture(lecture_id)
    return _ok(data)


def _lecture_delete(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    confirm = bool(tool_input.get("confirm"))
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    if not confirm:
        return _err(
            "삭제하려면 confirm=true가 필요합니다. 사용자 확인 후 호출하세요.",
            error_type="confirmation_required",
        )
    result = lecture_store.delete_lecture(lecture_id)
    return _ok(result)


# ─────────────────────────────────────────────────────────────────────
# 워크스페이스 창 열기 (Step 2에서 IPC 연결 예정)
# ─────────────────────────────────────────────────────────────────────

def _lecture_open(tool_input: dict) -> str:
    """강의 만들기 창 열기 — Launcher WS로 Electron에 신호 + 데이터 반환.

    AI가 "강의만들기창 열어줘" 받으면 이 액션 호출 →
    Electron 메인 프로세스가 새 BrowserWindow를 띄움.
    """
    lecture_id = (tool_input.get("lecture_id") or "").strip() or None

    # 존재 확인 (lecture_id 지정 시)
    if lecture_id and not lecture_store.lecture_exists(lecture_id):
        return _err(
            f"강의를 찾을 수 없습니다: {lecture_id}",
            error_type="not_found",
            hint="lecture_list로 사용 가능한 강의를 확인하세요.",
        )

    # Launcher WS로 Electron에 창 열기 신호
    ws_sent = False
    ws_error = None
    try:
        import asyncio
        from websocket_manager import send_launcher_command, get_launcher_ws

        if not get_launcher_ws():
            ws_error = "Launcher WS 미연결 (Electron 메인 창이 실행 중인지 확인하세요)"
        else:
            params = {"lecture_id": lecture_id} if lecture_id else {}
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    fut = asyncio.run_coroutine_threadsafe(
                        send_launcher_command("open_lecture_workspace", params),
                        loop,
                    )
                    ws_sent = fut.result(timeout=5)
                else:
                    ws_sent = asyncio.run(
                        send_launcher_command("open_lecture_workspace", params)
                    )
            except RuntimeError:
                ws_sent = asyncio.run(
                    send_launcher_command("open_lecture_workspace", params)
                )
    except Exception as e:
        ws_error = f"WS 전송 예외: {e}"

    payload = {
        "action": "open_lecture_workspace",
        "lecture_id": lecture_id,
        "window_opened": ws_sent,
    }
    if ws_error:
        payload["ws_warning"] = ws_error

    # 같이 데이터도 반환 (AI가 즉시 확인용)
    if lecture_id:
        payload["data"] = lecture_store.load_lecture(lecture_id)
    else:
        payload["data"] = {
            "lectures": lecture_store.list_lectures(),
            "lectures_root": str(lecture_store.write_root().resolve()),
        }

    return _ok(payload)


# ─────────────────────────────────────────────────────────────────────
# 데크 조작
# ─────────────────────────────────────────────────────────────────────

def _deck_reorder(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    order = tool_input.get("order")
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    if not isinstance(order, list):
        return _err("order는 slide_id 배열이어야 합니다.")
    result = lecture_store.reorder_deck(lecture_id, order)
    return _ok(result)


def _slide_delete(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    slide_id = (tool_input.get("slide_id") or "").strip()
    if not lecture_id or not slide_id:
        return _err("lecture_id와 slide_id 모두 필수입니다.")
    result = lecture_store.delete_slide(lecture_id, slide_id)
    _discard_overlay_state(lecture_store.slides_dir(lecture_id), slide_id)
    return _ok(result)


# ─────────────────────────────────────────────────────────────────────
# 재료 관리
# ─────────────────────────────────────────────────────────────────────

def _material_add(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    if not lecture_store.lecture_exists(lecture_id):
        return _err(f"강의를 찾을 수 없습니다: {lecture_id}", error_type="not_found")

    file_path = tool_input.get("file_path")
    text = tool_input.get("text")
    filename = tool_input.get("filename")

    if file_path:
        entry = lecture_store.add_material_from_file(lecture_id, file_path)
    elif text is not None and filename:
        entry = lecture_store.add_material_from_text(lecture_id, text, filename)
    else:
        return _err(
            "file_path 또는 (text + filename) 둘 중 하나는 제공해야 합니다.",
            hint="파일 복사: {file_path: '/...'}, 텍스트 저장: {text: '...', filename: 'notes.md'}",
        )

    # 재료가 바뀌면 캐시 무효화 (다음 슬라이드 생성 시 자동 재생성)
    try:
        slide_ai.invalidate_lecture_cache(lecture_id)
    except Exception as e:
        print(f"[handler] 캐시 무효화 실패 (무시): {e}")

    return _ok({"material": entry})


def _material_remove(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    filename = (tool_input.get("filename") or "").strip()
    if not lecture_id or not filename:
        return _err("lecture_id와 filename 모두 필수입니다.")
    result = lecture_store.remove_material(lecture_id, filename)

    # 재료가 바뀌면 캐시 무효화
    try:
        slide_ai.invalidate_lecture_cache(lecture_id)
    except Exception as e:
        print(f"[handler] 캐시 무효화 실패 (무시): {e}")

    return _ok(result)


# ─────────────────────────────────────────────────────────────────────
# 슬라이드 생성/편집 (AI)
# ─────────────────────────────────────────────────────────────────────

# 글자가 PNG에 구워진 슬라이드 = spec→HTML 재렌더/필드 편집 불가, 재생성만 가능.
#   native    통짜 이미지(이미지 모델이 글자까지 그림)
#   composite 이미지+글자 합성(타이포 레이어가 PNG로 구워짐)
#   image     강의자가 업로드한 원본 이미지
#   (_BAKED_LAYOUTS 정의는 slide_edit_ops.BAKED_LAYOUTS — 상단 별칭)


def _load_slide_tones():
    """톤 레지스트리 (media_producer/slide_tones.py) — 톤 × 렌더 방식 매트릭스의 단일 소스."""
    import importlib.util
    import sys as _sys
    if "slide_tones" in _sys.modules:
        return _sys.modules["slide_tones"]
    path = Path(__file__).resolve().parent.parent / "media_producer" / "slide_tones.py"
    spec = importlib.util.spec_from_file_location("slide_tones", str(path))
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["slide_tones"] = mod
    spec.loader.exec_module(mod)
    return mod


def _deck_axes(design: str) -> tuple:
    """`design_system` → (톤, 렌더 방식). 렌더 = native | image | html.

    2026-08-06 2축 개편: 문자열 하나가 두 축을 인코딩한다(`<렌더 접두>_<톤>`, 접두 없음=html).
    파싱 정본은 레지스트리 — 여기선 임포트 실패 시의 보수적 폴백만 갖는다.
    """
    try:
        return _load_slide_tones().parse_design_system(design)
    except Exception:
        d = (design or "").strip()
        for render in ("native", "image"):
            for sep in ("_", ":"):
                if d.startswith(render + sep):
                    return (d.split(sep, 1)[1] or "vintage_book"), render
            if d == render:
                return "vintage_book", render
        return (d or "vintage_book"), "html"


def _is_native_design(design: str) -> bool:
    """덱 design_system이 통짜 이미지(이미지 only) 경로인가."""
    return _deck_axes(design)[1] == "native"


def _is_image_design(design: str) -> bool:
    """덱 design_system이 이미지+글자(합성) 경로인가."""
    return _deck_axes(design)[1] == "image"


def _native_aesthetic(design: str) -> str:
    """design_system 에서 톤만 추출(기본 vintage_book)."""
    return _deck_axes(design)[0]


def _html_design_of(design: str) -> str:
    """이 덱의 톤을 **HTML 렌더러가 아는 키**로 변환(현재 4톤은 이름 일치 — 역사적 어긋남 대비 유지).

    톤이 HTML 렌더러에 없으면(은퇴 톤·미지원 톤) "default" 로 접는다 — create_shadcn_slides 는
    모르는 design_system 을 명시 오류로 거부하므로, 옛 덱(예: magazine_modern)이 새 HTML 슬라이드를
    뽑을 때 여기서 접어 줘야 조용히 계속 나온다(2026-08-07 톤 대압축 호환).
    """
    tone = _deck_axes(design)[0]
    try:
        return _load_slide_tones().style_key(tone, "html") or "default"
    except Exception:
        return "default"


def _load_slide_image():
    """이미지+글자 합성기 (media_producer/slide_image.py)."""
    import importlib.util
    import sys as _sys
    path = Path(__file__).resolve().parent.parent / "media_producer" / "slide_image.py"
    spec = importlib.util.spec_from_file_location("slide_image", str(path))
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["slide_image"] = mod
    spec.loader.exec_module(mod)
    return mod


_ANCHOR_SCAN_LIMIT = 16  # 같은 톤 앵커를 찾아 훑을 최대 슬라이드 수(긴 덱 전수 탐색 방지)

_NATIVE_TONE_BY_KO = None


def _native_tone_by_ko() -> dict:
    """통짜 아트디렉션의 한글 라벨 → 톤 키 역맵(1회 구축).

    2026-08-07 이전 슬라이드는 사이드카에 톤 키가 아니라 `aesthetic`(한글 라벨)만 남겼다.
    """
    global _NATIVE_TONE_BY_KO
    if _NATIVE_TONE_BY_KO is None:
        try:
            _NATIVE_TONE_BY_KO = {
                v.get("ko"): k for k, v in _load_slide_native().AESTHETICS.items() if v.get("ko")
            }
        except Exception:
            _NATIVE_TONE_BY_KO = {}
    return _NATIVE_TONE_BY_KO


def _slide_tone(slide_meta: dict, lecture_dir_path) -> str:
    """이 슬라이드가 **어느 톤으로** 만들어졌는지 — 사이드카 spec 에서 읽는다(모르면 "").

    우선순위: `tone`(정본, 2026-08-07~) → `style`(합성 경로는 톤 키가 그대로) →
    `aesthetic`(통짜 경로의 옛 한글 라벨).
    """
    rel = slide_meta.get("spec_file")
    if not rel:
        return ""
    try:
        with open(lecture_dir_path / rel, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except Exception:
        return ""
    if not isinstance(spec, dict):
        return ""
    for key in ("tone", "style"):
        v = (spec.get(key) or "").strip()
        if v:
            return v
    ko = (spec.get("aesthetic") or "").strip()
    return _native_tone_by_ko().get(ko, "") if ko else ""


def _anchor_scan(order: list, prev_idx, next_idx):
    """앵커 후보를 가까운 순서로 — 앞으로 거슬러 올라간 뒤, 뒤로 내려간다."""
    seen = 0
    i = prev_idx
    while i is not None and i >= 0 and seen < _ANCHOR_SCAN_LIMIT:
        yield order[i]
        i -= 1
        seen += 1
    j = next_idx
    while j is not None and j < len(order) and seen < _ANCHOR_SCAN_LIMIT:
        yield order[j]
        j += 1
        seen += 1


def _neighbor_context(deck: dict, lecture_dir_path, focus_slide_id, insert_at):
    """새/편집 슬라이드의 앞뒤 이웃 슬라이드를 찾아 스타일 참고 자료를 모은다.

    Returns: (ref_png_paths, neighbor_briefs)
      - ref_png_paths: 스타일 앵커 PNG 절대경로(최대 1장, 없으면 빈 리스트).
      - neighbor_briefs: [{position, title, layout}] — 텍스트 경로 프롬프트 힌트용.
    위치 결정:
      - 편집(focus): slide_order 상 focus 양옆.
      - 신규: insert_at 앞(insert_at-1)과 그 자리(insert_at). insert_at 미지정=맨 끝 → 직전 1장.
    """
    order = deck.get("slide_order", [])
    slides = deck.get("slides", {})
    prev_idx = next_idx = None
    if focus_slide_id and focus_slide_id in order:
        idx = order.index(focus_slide_id)
        if idx > 0:
            prev_idx = idx - 1
        if idx + 1 < len(order):
            next_idx = idx + 1
    else:
        if insert_at is None:
            if order:
                prev_idx = len(order) - 1
        else:
            if 0 < insert_at <= len(order):
                prev_idx = insert_at - 1
            if 0 <= insert_at < len(order):
                next_idx = insert_at
    prev_sid = order[prev_idx] if prev_idx is not None else None
    next_sid = order[next_idx] if next_idx is not None else None

    briefs = []
    for position, sid in (("앞", prev_sid), ("뒤", next_sid)):
        if not sid or sid not in slides:
            continue
        s = slides[sid]
        briefs.append({"position": position, "title": s.get("title"), "layout": s.get("layout")})

    # ── 스타일 앵커 ─────────────────────────────────────────────────────
    # 앵커는 **통짜(native) 경로에서만** 쓰이고, 그 프롬프트(_STYLE_REF_CLAUSE)는 첨부 이미지에
    # "이 표면 스타일(팔레트·종이질감·서체·마감)을 그대로 맞춰라"고 지시한다. 그래서 앵커는
    # **반드시 같은 톤**이어야 한다 — 톤이 다르면 아트디렉션(새 톤)과 앵커(옛 톤)가 한 프롬프트
    # 안에서 정면 충돌하고, 톤을 바꾼 첫 장이 늘 그 충돌을 뒤집어쓴다. 그래서 "덱에 이미 깔린
    # 톤 말고는 품질이 떨어진다"로 보인다(2026-08-07 관측: 빈티지 36장 덱에서 다크 키노트를
    # 뽑자 직전 빈티지 슬라이드가 앵커로 붙었다). 확인되는 후보가 없으면 **앵커 없이** 간다 —
    # 앵커 없음이 상충하는 앵커보다 낫다.
    #
    # 같은 톤이어도 통짜(native)를 합성(composite)보다 앞세운다: 합성판은 HTML 타이포 레이어와
    # 페이드가 얹힌 다른 마감이라 팔레트는 맞아도 표면이 덜 맞는다. 통짜가 없을 때의 차선.
    # 업로드 원본(image)·HTML 렌더는 애초에 앵커가 아니다.
    # 하나만 붙이는 이유는 종전과 같다: 둘을 첨부하면 모델이 상충하는 단서를 섞는다.
    deck_tone = _deck_axes(deck.get("design_system") or "native_vintage_book")[0]
    native_ref = composite_ref = None
    for sid in _anchor_scan(order, prev_idx, next_idx):
        s = slides.get(sid)
        if not s:
            continue
        layout = s.get("layout")
        if layout not in ("native", "composite"):
            continue
        if _slide_tone(s, lecture_dir_path) != deck_tone:
            continue
        png_rel = s.get("png_file")
        if not png_rel:
            continue
        p = (lecture_dir_path / png_rel).resolve()
        if not p.exists():
            continue
        if layout == "native":
            native_ref = str(p)
            break  # 최선을 찾았다 — 더 볼 것 없다
        if composite_ref is None:
            composite_ref = str(p)
    best = native_ref or composite_ref
    return ([best] if best else []), briefs


def _generate_native_slide(
    lecture_id, deck, slides_dir_path, instruction, focus_slide_id, insert_at, design,
    reference_images=None, image_quality="pro", content=None,
) -> dict:
    """네이티브 통짜 이미지 슬라이드 — slide_native 위임 후 deck에 등록(NotebookLM식)."""
    slide_id = focus_slide_id or lecture_store.next_slide_id(deck)
    sn = _load_slide_native()

    ctx = []
    if deck.get("title"):
        ctx.append(f"강의: {deck['title']}")
    if deck.get("thesis"):
        ctx.append(f"핵심 논지: {deck['thesis']}")
    if deck.get("audience"):
        ctx.append(f"청중: {deck['audience']}")
    tool_input = {"instruction": instruction, "aesthetic": _native_aesthetic(design)}
    # content = 호출자가 준 근거 원문(환각 방지) + 덱 컨텍스트 — 구 engines:slide 의 content 계약 승계
    parts = ([" / ".join(ctx)] if ctx else []) + ([content] if content else [])
    if parts:
        tool_input["content"] = "\n".join(parts)
    if reference_images:
        tool_input["style_reference_images"] = reference_images
    # 이미지 품질/모델: fast=Nano Banana 2(Gemini 3.1 Flash, 저가·1K) / pro=Nano Banana Pro(Gemini 3 Pro, 고품질·2K)
    if (image_quality or "pro").strip() == "fast":
        tool_input["quality"] = "fast"
        tool_input["image_size"] = "1K"
    else:
        tool_input["quality"] = "pro"
        tool_input["image_size"] = "2K"

    result = json.loads(
        sn.create_native_slide(tool_input, str(slides_dir_path), slide_id=slide_id)
    )
    if not result.get("success"):
        raise RuntimeError(result.get("message") or "네이티브 슬라이드 생성 실패")

    spec = result.get("spec") or {}
    spec_meta = {
        "layout": "native", "device": result.get("device"), "aesthetic": result.get("aesthetic"),
        "title": result.get("title"), **spec,
        # 톤 키(정본) — 다음 슬라이드가 '같은 톤인가'를 이걸로 판정해 스타일 앵커를 고른다.
        # (**spec 뒤에 둬서 저작 AI 응답이 덮어쓰지 못하게 한다.)
        "tone": _native_aesthetic(design),
    }
    with open(slides_dir_path / f"{slide_id}.json", "w", encoding="utf-8") as f:
        json.dump(spec_meta, f, ensure_ascii=False, indent=2)

    png_rel = f"slides/{slide_id}.png"
    spec_rel = f"slides/{slide_id}.json"
    lecture_store.register_slide(
        lecture_id=lecture_id, slide_id=slide_id,
        title=result.get("title") or "(제목 없음)",
        layout="native", spec_file=spec_rel, png_file=png_rel, insert_at=insert_at,
    )
    return {
        "slide_id": slide_id, "slide": spec_meta, "png_file": png_rel, "spec_file": spec_rel,
        # 절대 경로 — 평가 루프의 시각 산출물 수집기가 결과 문자열에서 이미지를 찾게 한다
        # (상대경로 png_file은 정규식 /…png 에 안 걸림). 평가자가 픽셀을 직접 보는 통로.
        "png_path": str((slides_dir_path / f"{slide_id}.png").resolve()),
        "reasoning": result.get("reasoning"), "device": result.get("device"),
        "verify": result.get("verify"),
        "mode": "edit" if focus_slide_id else "create",
    }


def _generate_image_slide(
    lecture_id, deck, slides_dir_path, instruction, focus_slide_id, insert_at, tone,
    image_quality="pro", content=None,
) -> dict:
    """이미지+글자 슬라이드 — 글자 없는 일러스트 + HTML 타이포 합성(slide_image 위임).

    구성(diptych/hero/side_panel/center_anchor/annotated/process)은 저작 AI가 내용을 보고
    고른다 — 사람이 고르는 축이 아니다.
    """
    slide_id = focus_slide_id or lecture_store.next_slide_id(deck)
    si = _load_slide_image()
    style = _load_slide_tones().style_key(tone, "image")
    if not style:
        raise ValueError(f"'{tone}' 톤은 이미지+글자 렌더를 지원하지 않습니다.")

    # 강의 맥락을 가볍게 곁들여 그라운딩 (주제·핵심·청중) + 호출자가 준 근거 원문
    ctx = []
    if deck.get("title"):
        ctx.append(f"강의: {deck['title']}")
    if deck.get("thesis"):
        ctx.append(f"핵심 논지: {deck['thesis']}")
    if deck.get("audience"):
        ctx.append(f"청중: {deck['audience']}")
    tool_input = {"instruction": instruction}
    parts = ([" / ".join(ctx)] if ctx else []) + ([content] if content else [])
    if parts:
        tool_input["content"] = "\n".join(parts)
    # 일러스트 품질 — 통짜 경로와 같은 어휘(pro=Nano Banana Pro / fast=Nano Banana 2)
    tool_input["quality"] = "fast" if (image_quality or "pro").strip() == "fast" else "pro"

    result = json.loads(
        si.create_image_slide(tool_input, str(slides_dir_path), style, slide_id=slide_id)
    )
    if not result.get("success"):
        raise RuntimeError(result.get("message") or "이미지+글자 슬라이드 생성 실패")

    # spec json 저장 (layout="image"라 필드 직접 편집이 아니라 재생성 경로로 안내된다)
    spec = result.get("spec") or {}
    spec_meta = {
        "layout": "composite", "style": result.get("style"), "composition": result.get("composition"),
        "title": result.get("title"), "kicker": result.get("kicker"), **spec,
        "tone": tone,  # 통짜 경로와 같은 정본 필드 (앵커 판정용)
    }
    with open(slides_dir_path / f"{slide_id}.json", "w", encoding="utf-8") as f:
        json.dump(spec_meta, f, ensure_ascii=False, indent=2)

    png_rel = f"slides/{slide_id}.png"
    spec_rel = f"slides/{slide_id}.json"
    lecture_store.register_slide(
        lecture_id=lecture_id, slide_id=slide_id,
        title=result.get("title") or "(제목 없음)",
        layout="composite", spec_file=spec_rel, png_file=png_rel, insert_at=insert_at,
    )
    return {
        "slide_id": slide_id, "slide": spec_meta, "png_file": png_rel, "spec_file": spec_rel,
        # 절대 경로 — 통짜 경로와 같은 의도(평가 루프가 픽셀을 직접 보는 통로)
        "png_path": str((slides_dir_path / f"{slide_id}.png").resolve()),
        "reasoning": result.get("reasoning"), "style": result.get("style"),
        "composition": result.get("composition"), "critique": result.get("critique"),
        "mode": "edit" if focus_slide_id else "create",
    }


def _generate_and_register_slide(
    lecture_id: str,
    instruction: str,
    focus_slide_id: str = None,
    insert_at: int = None,
    forced_layout: str = None,
    image_quality: str = "pro",
    content: str = None,
    user_image_path: str = None,
    render: str = None,
) -> dict:
    """AI 호출 → 렌더 → deck 등록의 공통 흐름. dict 반환.

    render: 이 한 장만 덱 기본과 다른 렌더 방식으로 그린다(native|image|html). 강의 창의
        '렌더 방식' 셀렉터가 쓰는 슬라이드 단위 override — 혼합 덱을 허용한다.
    forced_layout: HTML 경로의 layout 강제(프로그래매틱·IBL 용). 2026-08-06부터 UI 에는
        노출하지 않는다 — 구조는 AI가 내용을 보고 고르는 축이고, 사람이 고르는 건 톤과
        렌더 방식 둘뿐이다. 자연어("좌우로 대비해서", "자유롭게 배치해줘")가 그 자리를 대신한다.
    """
    deck = lecture_store.read_deck(lecture_id)
    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    slides_dir_path = lecture_store.slides_dir(lecture_id)

    # 앞뒤 이웃 슬라이드 — 스타일 일관성 참고(항상 자동). 이미지 경로는 native 경로,
    # 간단 brief는 텍스트 경로 프롬프트 힌트로 쓴다.
    ref_png_paths, neighbor_briefs = _neighbor_context(
        deck, lecture_dir_path, focus_slide_id, insert_at
    )

    # ── 이 슬라이드의 (톤, 렌더 방식) 확정 ─────────────────────────────
    design = (deck.get("design_system") or "native_vintage_book").strip()
    tone, deck_render = _deck_axes(design)
    slide_render = (render or "").strip() or deck_render
    if slide_render not in ("native", "image", "html"):
        slide_render = deck_render
    # 톤이 그 렌더 방식을 지원하지 않으면 **조용히 다른 걸 그리지 않는다** — 명시 오류.
    # (UI 는 지원 조합만 고르게 하므로 이 가드는 API·IBL 직접 호출용.)
    if slide_render != deck_render:
        try:
            _tones = _load_slide_tones()
            if not _tones.supports(tone, slide_render) and slide_render != "html":
                raise ValueError(
                    f"'{_tones.TONES.get(tone, {}).get('ko', tone)}' 톤은 "
                    f"'{slide_render}' 렌더 방식을 지원하지 않습니다. "
                    f"가능: {_tones.renders_for(tone)}"
                )
        except ValueError:
            raise
        except Exception:
            pass  # 레지스트리 로드 실패는 렌더를 막지 않는다

    # 강의자 첨부 이미지 = "이 파일을 배치하라" — 이미지 경로(native/composite)는 파일을 그대로
    # 못 담으므로 첨부가 있으면 HTML(shadcn) 경로로 내려간다 (hero_image/content_image/custom 임베드).
    if user_image_path:
        slide_render = "html"

    if slide_render == "native":
        return _generate_native_slide(
            lecture_id, deck, slides_dir_path, instruction, focus_slide_id, insert_at,
            f"native_{tone}",
            reference_images=ref_png_paths, image_quality=image_quality, content=content,
        )
    if slide_render == "image":
        return _generate_image_slide(
            lecture_id, deck, slides_dir_path, instruction, focus_slide_id, insert_at, tone,
            image_quality=image_quality, content=content,
        )

    # HTML(텍스트) 경로 — content 는 instruction 에 근거 블록으로 접합(전용 필드 없음)
    if content:
        instruction = f"{instruction}\n\n[근거 원문 — 사실·표현·고유명사는 여기서, 지어내지 말 것]\n{content}"

    # HTML 렌더러가 아는 톤 키로 변환.
    html_design = _html_design_of(design)

    # focus slide의 현재 spec 로드 (편집 모드)
    focus_spec = None
    if focus_slide_id:
        if focus_slide_id not in deck.get("slides", {}):
            raise ValueError(f"슬라이드 없음: {focus_slide_id}")
        spec_file = lecture_dir_path / deck["slides"][focus_slide_id]["spec_file"]
        if spec_file.exists():
            try:
                with open(spec_file, "r", encoding="utf-8") as f:
                    focus_spec = json.load(f)
            except Exception as e:
                print(f"[slide_edit] focus spec 읽기 실패: {e}")

    # AI 호출 — 프롬프트 메타의 '디자인'도 HTML 톤으로 맞춘다(native 덱을 텍스트로 덮을 때
    # 'native_vintage_book'이 메타에 박혀 AI가 통짜 이미지 스펙을 내려는 오정렬 방지).
    prompt_deck = {**deck, "design_system": html_design} if html_design != design else deck
    ai_response = slide_ai.generate_slide_response(
        user_image_path=user_image_path,
        deck=prompt_deck,
        lecture_dir=lecture_dir_path,
        user_instruction=instruction,
        focus_slide=focus_spec,
        forced_layout=forced_layout,
        neighbor_briefs=neighbor_briefs,
    )

    slide_spec = ai_response.get("slide")
    if not isinstance(slide_spec, dict):
        raise ValueError("AI 응답의 'slide'가 객체가 아닙니다.")

    # slide_id 결정
    if focus_slide_id:
        slide_id = focus_slide_id
    else:
        slide_id = lecture_store.next_slide_id(deck)

    # 일러스트 layout이면 이미지 생성 → spec에 image_path 주입
    illustrations = ai_response.get("illustrations")
    if illustrations and isinstance(illustrations, dict):
        try:
            injected = slide_ai.generate_slide_illustrations(
                illustrations=illustrations,
                design_system=html_design,
                slides_dir=slides_dir_path,
                slide_id=slide_id,
                image_quality=image_quality,
            )
            # 절대경로를 slide_spec에 주입 (slide_shadcn이 자동 base64 변환)
            slide_spec.update(injected)
        except Exception as e:
            # 이미지 생성 실패 — 슬라이드 자체는 텍스트만으로 진행 (degraded)
            print(f"[slide_create] 일러스트 생성 실패, 텍스트만으로 진행: {e}")

    # 렌더 → 파일 저장
    rendered = slide_ai.render_slide_to_files(
        spec=slide_spec,
        design_system=html_design,
        slides_dir=slides_dir_path,
        slide_id=slide_id,
    )

    # deck 갱신
    title = slide_spec.get("title") or slide_spec.get("quote", "")[:30] or "(제목 없음)"
    layout = slide_spec.get("layout", "lecture_body")
    lecture_store.register_slide(
        lecture_id=lecture_id,
        slide_id=slide_id,
        title=title,
        layout=layout,
        spec_file=rendered["spec_file"],
        png_file=rendered["png_file"],
        insert_at=insert_at,
        # AI가 뽑은 스피커 노트를 강의 노트 초안으로 시드 (사용자가 이미 적었으면 보존됨)
        speaker_note=ai_response.get("speaker_note"),
    )

    # 누적 메모 패치
    memo_signals = ai_response.get("memo_signals") or {}
    if isinstance(memo_signals, dict) and memo_signals:
        try:
            lecture_store.update_cumulative_memo(lecture_id, memo_signals)
        except Exception as e:
            print(f"[slide_create] 메모 패치 실패: {e}")

    # 결과
    return {
        "slide_id": slide_id,
        "slide": slide_spec,
        "png_file": rendered["png_file"],
        "spec_file": rendered["spec_file"],
        # 절대 경로 — 평가 루프 시각 산출물 수집기가 결과에서 이미지를 찾게 한다 (네이티브 경로와 동일 의도)
        "png_path": str((lecture_dir_path / rendered["png_file"]).resolve()),
        "reasoning": ai_response.get("reasoning"),
        "speaker_note": ai_response.get("speaker_note"),
        "memo_signals": memo_signals,
        "mode": "edit" if focus_slide_id else "create",
    }


_VALID_LAYOUTS = {
    "hero", "lecture_body", "metaphor_story", "comparison_table", "factbox", "quote",
    "hero_illustration", "illustration_anchor", "split_concept",
    "illustration_background", "illustration_overlay", "comparison_iconic",
    "custom",  # 자유형 — AI가 슬라이드 HTML을 직접 작성 (고정 틀 없음)
    # 마케팅·제품 레이아웃 (shadcn) — 2026-08-05 슬라이드 일원화 때 어휘 사정권으로 복원.
    # 렌더러(media_producer/shadcn_slides.py)가 원래 갖고 있던 메뉴 — 구 slide_shadcn 전용이었다.
    "hero_image", "features", "stats", "testimonial", "pricing", "cta", "content_image", "steps",
}


_SCRATCH_TITLE = "스크래치"


def _resolve_scratch_lecture(aesthetic: str = None) -> str:
    """lecture_id 미지정 단발 생성의 거처 — 스크래치 덱 (aesthetic별 1개, 자동 생성·재사용).

    구 [engines:slide](단발 PNG) 흡수 경로(2026-08-05 어휘 압축): 슬라이드는 항상 덱에
    산다 — 만든 뒤 편집(slide)·순서(deck reorder)·내보내기(deck export)·나레이션→영상이
    기존 어휘로 그대로 이어진다. aesthetic 은 덱의 design_system(native_<톤>)으로 관통 —
    같은 톤 N장 병렬 생성이 같은 스크래치 덱에 모인다."""
    tone = (aesthetic or "").strip()
    title = f"{_SCRATCH_TITLE} ({tone})" if tone else _SCRATCH_TITLE
    for lec in lecture_store.list_lectures():
        if (lec.get("title") or "") == title:
            return lec["lecture_id"]
    deck = lecture_store.create_lecture(
        title=title,
        design_system=(f"native_{tone}" if tone else "native_vintage_book"),
    )
    return deck["lecture_id"]


def _slide_create(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    instruction = (tool_input.get("instruction") or "").strip()
    insert_at = tool_input.get("insert_at")
    forced_layout = (tool_input.get("layout") or "").strip() or None
    if not instruction:
        return _err("instruction(강의자의 자연어 요청)은 필수입니다.")
    user_image_path = (tool_input.get("user_image_path") or "").strip() or None
    if user_image_path and not os.path.exists(user_image_path):
        return _err(f"첨부 이미지 파일이 없습니다: {user_image_path}")
    scratch = False
    if not lecture_id:
        lecture_id = _resolve_scratch_lecture(tool_input.get("aesthetic"))
        scratch = True
    if insert_at is not None:
        try:
            insert_at = int(insert_at)
        except (TypeError, ValueError):
            return _err("insert_at은 정수여야 합니다.")
    if forced_layout and forced_layout not in _VALID_LAYOUTS:
        return _err(f"알 수 없는 layout: {forced_layout!r}. 사용 가능: {sorted(_VALID_LAYOUTS)}")
    result = _generate_and_register_slide(
        lecture_id=lecture_id,
        instruction=instruction,
        focus_slide_id=None,
        insert_at=insert_at,
        forced_layout=forced_layout,
        image_quality=(tool_input.get("image_quality") or "pro"),
        content=(tool_input.get("content") or "").strip() or None,
        user_image_path=user_image_path,
        render=(tool_input.get("render") or "").strip() or None,
    )
    if scratch:
        result["lecture_id"] = lecture_id
        result["scratch_deck"] = True
        result["note"] = "lecture_id 미지정 — 스크래치 덱에 등록됨(이후 편집·순서·내보내기 가능)"
    return _ok(result)


def _slide_rerender(tool_input: dict) -> str:
    """슬라이드 spec 변경 없이 PNG만 재렌더.

    용도: design_system이 바뀐 후 같은 내용으로 새 톤 적용. AI 호출 없음 — 빠르고 비결정적
    응답으로 spec이 흔들리는 일도 없음.
    """
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    slide_id = (tool_input.get("slide_id") or "").strip()
    if not lecture_id or not slide_id:
        return _err("lecture_id와 slide_id 모두 필수입니다.")

    deck = lecture_store.read_deck(lecture_id)
    slide_meta = deck.get("slides", {}).get(slide_id)
    if not slide_meta:
        return _err(f"슬라이드 없음: {slide_id}", error_type="not_found")

    # 통짜 이미지(native)·업로드 이미지(image) **슬라이드**는 spec→HTML 재렌더가 아니라 이미지
    # *재생성*이라야 톤이 바뀐다(HTML 재렌더기는 native/image spec을 못 그림). 재생성 경로로 안내.
    # ★판단은 덱이 아니라 *이 슬라이드의 layout*으로 — native 덱에 끼운 텍스트형(HTML) 슬라이드는
    #  재렌더 가능하다(혼합 덱). native 슬라이드는 등록 layout이 "native"라 그대로 걸린다.
    if slide_meta.get("layout") in _BAKED_LAYOUTS:
        return _err(
            "글자가 이미지에 구워진 슬라이드는 rerender 대신 슬라이드를 다시 생성하세요 "
            "([self:slide]{op:\"edit\", slide_id, instruction} 또는 op:\"create\"). "
            "통짜 이미지는 재렌더가 아니라 재생성이 맞습니다.",
            error_type="unsupported",
        )

    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    slides_dir_path = lecture_store.slides_dir(lecture_id)

    # 현재 spec 로드
    spec_file = lecture_dir_path / slide_meta["spec_file"]
    if not spec_file.exists():
        return _err(f"spec 파일 없음: {spec_file}")
    try:
        with open(spec_file, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as e:
        return _err(f"spec 파일 읽기 실패: {e}")

    # 재렌더 (현재 design_system 적용, 일러스트는 기존 파일 재사용)
    # 덱 렌더 방식이 무엇이든 이 슬라이드는 HTML이므로 톤만 뽑아 렌더러가 아는 키로 매핑.
    _deck_design = (deck.get("design_system") or "vintage_book").strip()
    html_design = _html_design_of(_deck_design)
    try:
        rendered = slide_ai.render_slide_to_files(
            spec=spec,
            design_system=html_design,
            slides_dir=slides_dir_path,
            slide_id=slide_id,
        )
    except Exception as e:
        return _err(f"재렌더 실패: {e}", error_type="render_error")

    # deck의 slide updated_at 갱신 (UI 캐시 무효화 + 변경 추적)
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    deck["slides"][slide_id]["updated_at"] = now
    lecture_store.write_deck(lecture_id, deck)

    return _ok({
        "slide_id": slide_id,
        "mode": "rerender",
        "design_system": deck.get("design_system"),
        "png_file": rendered["png_file"],
        "title": spec.get("title") or slide_meta.get("title"),
    })


def _slide_patch_spec(tool_input: dict) -> str:
    """슬라이드 spec 필드를 직접 patch + PNG 재렌더. AI 호출 없음.

    PowerPoint식 "필드 편집"의 백엔드. 사용자가 폼에서 직접 입력한 값을 그대로 적용.

    patch dict의 키-값을 spec에 shallow update (dict.update). image_path류·복잡 구조도
    문자열/배열/객체 그대로 받아 spec에 주입. layout 키는 변경 위험이 커서 거부 —
    layout 바꾸려면 slide_edit + forced_layout 사용.
    """
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    slide_id = (tool_input.get("slide_id") or "").strip()
    patch = tool_input.get("patch")
    if not lecture_id or not slide_id:
        return _err("lecture_id와 slide_id 모두 필수입니다.")
    if not isinstance(patch, dict) or not patch:
        return _err("patch는 비어있지 않은 객체여야 합니다.")
    if "layout" in patch:
        return _err(
            "layout은 직접 patch로 못 바꿉니다. slide_edit + forced_layout을 쓰세요.",
            hint="레이아웃이 바뀌면 필요 필드도 달라져 spec이 깨질 수 있음.",
        )

    deck = lecture_store.read_deck(lecture_id)
    slide_meta = deck.get("slides", {}).get(slide_id)
    if not slide_meta:
        return _err(f"슬라이드 없음: {slide_id}", error_type="not_found")

    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    slides_dir_path = lecture_store.slides_dir(lecture_id)

    # 현재 spec 로드
    spec_file = lecture_dir_path / slide_meta["spec_file"]
    if not spec_file.exists():
        return _err(f"spec 파일 없음: {spec_file}")
    try:
        with open(spec_file, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as e:
        return _err(f"spec 파일 읽기 실패: {e}")

    # 이미지+글자(composite) 슬라이드: 글자는 spec 에 구조화 데이터로, 원료 일러스트는
    # {slide_id}_img.png 로 보존돼 있다 → 텍스트 필드만 patch 하고 그림 재사용 재합성(AI 0).
    if spec.get("layout") == "composite":
        return _patch_composite_slide(
            lecture_id, slide_id, deck, spec, spec_file, patch, slides_dir_path)

    # 통짜 이미지(native)·업로드 이미지(image) **슬라이드**는 글자가 PNG에 구워져 있어 spec patch→HTML
    # 재렌더가 불가능하다(HTML 렌더기가 native/image spec을 못 그림). 그 슬라이드만 재생성 경로로 안내.
    # ★판단 기준은 덱이 아니라 *이 슬라이드의 layout*이다 — 덱이 native여도 그 안에 끼운 텍스트형(HTML)
    #  슬라이드는 필드 직접 편집이 가능하다(혼합 덱). native 슬라이드는 spec에 layout:"native"를 가져
    #  아래 조건에 그대로 걸리므로, 덱 단위 _is_native_design 검사는 텍스트 슬라이드를 과잉 차단한다.
    if spec.get("layout") in _BAKED_LAYOUTS:
        return _err(
            "글자가 이미지에 구워진 슬라이드는 필드 직접 편집을 지원하지 않습니다. "
            "제목·내용을 바꾸려면 슬라이드를 선택한 뒤 AI 채팅으로 다시 생성하세요(예: \"제목을 '...'로 바꿔줘\").",
            error_type="validation",
        )

    # patch 적용 — shallow update. spec[k] = v for each k,v in patch.
    # None은 사용자가 의도적으로 비우려 한 것으로 처리하지 않고 제거.
    for key, value in patch.items():
        if value is None:
            spec.pop(key, None)
        else:
            spec[key] = value

    # 재렌더 — 덱 렌더 방식이 무엇이든 이 슬라이드는 HTML이므로 톤만 뽑아 렌더러가 아는 키로 매핑
    # (native_vintage_book / image_ink_blueprint → 톤 → html 키). 접두 없는 덱은 그대로.
    _deck_design = (deck.get("design_system") or "vintage_book").strip()
    html_design = _html_design_of(_deck_design)
    try:
        rendered = slide_ai.render_slide_to_files(
            spec=spec,
            design_system=html_design,
            slides_dir=slides_dir_path,
            slide_id=slide_id,
        )
    except Exception as e:
        return _err(f"재렌더 실패: {e}", error_type="render_error")

    # deck 메타 갱신 (title이 patch에 있으면 deck의 slide title도 갱신)
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    deck["slides"][slide_id]["updated_at"] = now
    new_title = spec.get("title") or spec.get("quote", "")[:30]
    if new_title:
        deck["slides"][slide_id]["title"] = new_title
    lecture_store.write_deck(lecture_id, deck)

    return _ok({
        "slide_id": slide_id,
        "mode": "patch",
        "spec": spec,
        "png_file": rendered["png_file"],
        "patched_keys": list(patch.keys()),
        "design_system": deck.get("design_system"),
    })


# 이미지+글자(composite) 슬라이드에서 직접 patch 가능한 텍스트 필드 —
# slide_image.COMPOSITIONS 템플릿이 소비하는 글자 어휘의 합집합. scene/composition/style 은
# 그림·조판 정체라 재생성 경로로만(바꾸면 원료 일러스트와 안 맞음).
_COMPOSITE_TEXT_KEYS = {"title", "kicker", "subtitle", "body", "bullets",
                        "captions", "labels", "steps"}


def _patch_composite_slide(
    lecture_id: str, slide_id: str, deck: dict, spec: dict, spec_file,
    patch: dict, slides_dir_path,
) -> str:
    """이미지+글자(composite) 슬라이드의 텍스트 필드만 patch — 보존된 원료 일러스트로 재합성.

    이미지 모델 호출 0: 글자 얹기와 같은 원리(그림 불변, 글자만 다시 조판).
    """
    bad = sorted(k for k in patch if k not in _COMPOSITE_TEXT_KEYS)
    if bad:
        return _err(
            f"이미지+글자 슬라이드는 텍스트 필드만 직접 수정할 수 있습니다: {sorted(_COMPOSITE_TEXT_KEYS)}. "
            f"거부된 키: {bad}. 그림·구도를 바꾸려면 재생성(edit)을 쓰세요.",
            error_type="validation",
        )
    img_path = slides_dir_path / f"{slide_id}_img.png"
    if not img_path.exists():
        return _err(
            f"원료 일러스트가 없어 재합성할 수 없습니다: {img_path.name}. 슬라이드를 재생성하세요.",
            error_type="not_found",
        )

    for key, value in patch.items():
        if value is None:
            spec.pop(key, None)
        else:
            spec[key] = value

    style = (spec.get("style") or "").strip()
    si = _load_slide_image()
    png_path = slides_dir_path / f"{slide_id}.png"
    result = json.loads(si.recompose_image_slide(spec, style, str(img_path), str(png_path)))
    if not result.get("success"):
        return _err(result.get("message") or "재합성 실패", error_type="render_error")

    with open(spec_file, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)

    # 얹은 글자(text_overlays)가 있으면: 새 합성판이 새 '원본' — base 교체 후 오버레이 재적용
    meta = deck["slides"][slide_id]
    overlays = list(meta.get("text_overlays") or [])
    if overlays:
        import shutil
        orig = slides_dir_path / f"{slide_id}.base.png"
        shutil.copy2(png_path, orig)
        so = _load_slide_overlay()
        r2 = json.loads(so.compose(str(orig), overlays, str(png_path)))
        if not r2.get("success"):
            print(f"[slide_patch] 얹은 글자 재적용 실패(글자 없이 진행): {r2.get('error')}")
    else:
        _discard_overlay_state(slides_dir_path, slide_id)

    from datetime import datetime
    if isinstance(patch.get("title"), str) and patch["title"].strip():
        meta["title"] = patch["title"].strip()
    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    lecture_store.write_deck(lecture_id, deck)

    return _ok({
        "slide_id": slide_id,
        "mode": "patch",
        "layout": "composite",
        "patched_keys": sorted(patch.keys()),
        "composition": result.get("composition"),
        "png_file": meta.get("png_file"),
        "png_path": str(png_path.resolve()),
        "message": "글자만 다시 조판했습니다 (그림·이미지 모델 호출 없음).",
    })


def _slide_edit(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    slide_id = (tool_input.get("slide_id") or "").strip()
    instruction = (tool_input.get("instruction") or "").strip()
    forced_layout = (tool_input.get("layout") or "").strip() or None
    if not lecture_id or not slide_id:
        return _err("lecture_id와 slide_id 모두 필수입니다.")
    if not instruction:
        return _err("instruction(편집 요청)은 필수입니다.")
    if forced_layout and forced_layout not in _VALID_LAYOUTS:
        return _err(f"알 수 없는 layout: {forced_layout!r}. 사용 가능: {sorted(_VALID_LAYOUTS)}")
    user_image_path = (tool_input.get("user_image_path") or "").strip() or None
    if user_image_path and not os.path.exists(user_image_path):
        return _err(f"첨부 이미지 파일이 없습니다: {user_image_path}")
    result = _generate_and_register_slide(
        lecture_id=lecture_id,
        instruction=instruction,
        focus_slide_id=slide_id,
        forced_layout=forced_layout,
        image_quality=(tool_input.get("image_quality") or "pro"),
        user_image_path=user_image_path,
        render=(tool_input.get("render") or "").strip() or None,
    )
    # 재생성으로 PNG가 새 픽셀이 됐다 — 얹은 글자 원본 백업은 폐기 (메타는 register가 교체)
    _discard_overlay_state(lecture_store.slides_dir(lecture_id), slide_id)
    return _ok(result)


# ─────────────────────────────────────────────────────────────────────
# 데크 내보내기 (PDF/PPTX)
# ─────────────────────────────────────────────────────────────────────

def _deck_export(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    fmt = (tool_input.get("format") or "").strip().lower()
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    if fmt not in ("pdf", "pptx", "pptx_image", "pptx_editable"):
        return _err(
            f"format은 'pdf', 'pptx'(이미지), 'pptx_editable'(편집 가능) 중 하나여야 합니다. 받은 값: {fmt!r}"
        )
    if not lecture_store.lecture_exists(lecture_id):
        return _err(f"강의 없음: {lecture_id}", error_type="not_found")
    result = lecture_export.export_deck(lecture_id, fmt)
    return _ok(result)


# ─────────────────────────────────────────────────────────────────────
# 덱 → 나레이션 동영상 (2026-08-05 결정화 — "동영상 만들어줘" 한 마디의 결정론 경로)
# 부품은 전부 있었다: 슬라이드 PNG(덱) + 장별 speaker_note(생성 때 자동 시드) +
# media_producer create_html_video(TTS→씬 길이 자동 맞춤→FFmpeg 합성). 여기는 그 다리 —
# 덱을 scenes/narration_texts 로 조립해 파이프라인에 넣는다. 렌더는 수 분이라 기본
# 백그라운드(즉시 반환 + video_state.json, 신문 발행·family-news 선례), wait:true=동기.
# ─────────────────────────────────────────────────────────────────────

def _load_media_handler():
    """media_producer/handler.py 차용 — create_html_video 파이프라인 (slide_native 차용과 같은 패턴)."""
    import importlib.util
    path = Path(__file__).resolve().parent.parent / "media_producer" / "handler.py"
    key = "_media_handler_for_lecture"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _video_state_path(lecture_id: str) -> Path:
    return lecture_store.lecture_dir(lecture_id) / "video_state.json"


def _write_video_state(lecture_id: str, state: dict) -> None:
    try:
        from datetime import datetime
        state = {**state, "updated_at": datetime.now().isoformat(timespec="seconds")}
        _video_state_path(lecture_id).write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[deck_video] 상태 저장 실패(무시): {e}")


def _scene_html_from_png(png_path: Path, width: int, height: int) -> str:
    """슬라이드 PNG 한 장 → 풀블리드 HTML 씬. base64 임베드 — 파일 경로 의존 없음."""
    import base64 as _b64
    b64 = _b64.b64encode(png_path.read_bytes()).decode("ascii")
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
        '<body style="margin:0;background:#000">'
        f'<img src="data:image/png;base64,{b64}" '
        f'style="width:{width}px;height:{height}px;object-fit:contain;display:block">'
        "</body></html>"
    )


def _deck_video_build(lecture_id: str, opts: dict) -> dict:
    """조립 + 렌더 본체 (동기). 스레드/동기 양쪽에서 호출 — 상태 파일에 결과를 남긴다."""
    width, height = int(opts.get("width") or 1280), int(opts.get("height") or 720)
    deck = lecture_store.read_deck(lecture_id)
    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    order = deck.get("slide_order") or []
    slides = deck.get("slides") or {}

    scenes, narrations, missing_notes, skipped = [], [], [], []
    for sid in order:
        meta = slides.get(sid) or {}
        png = lecture_dir_path / (meta.get("png_file") or "")
        if not meta.get("png_file") or not png.exists():
            skipped.append(sid)
            continue
        scenes.append({"html": _scene_html_from_png(png, width, height),
                       "duration": float(opts.get("duration_per_scene") or 5)})
        note = (meta.get("speaker_note") or "").strip()
        narrations.append(note)          # 빈 노트 = 무나레이션 씬 (html_video 가 기본 길이로 처리)
        if not note:
            missing_notes.append(sid)

    if not scenes:
        raise RuntimeError("렌더할 슬라이드가 없습니다 (PNG 미존재).")

    mh = _load_media_handler()
    video_dir = lecture_dir_path / "video"
    video_dir.mkdir(exist_ok=True)
    tool_input = {
        "scenes": scenes,
        "narration_texts": narrations,
        "voice": opts.get("voice") or "ko-KR-SunHiNeural",
        "rate": opts.get("rate") or "+0%",
        "transition": opts.get("transition") or "fade",
        "output_filename": opts.get("output_filename") or "lecture_video.mp4",
        "width": width, "height": height,
    }
    if opts.get("bgm_path"):
        tool_input["bgm_path"] = opts["bgm_path"]
    result_msg = mh.create_html_video(tool_input, str(video_dir))
    if not str(result_msg).startswith("HTML 동영상 제작 완료"):
        raise RuntimeError(str(result_msg)[:500])
    output = str(result_msg).split(":", 1)[1].strip().split(" (")[0]
    return {
        "output": output, "slides": len(scenes),
        "narrated": len(scenes) - len(missing_notes),
        "missing_notes": missing_notes, "skipped": skipped,
    }


def _deck_video(tool_input: dict) -> str:
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    if not lecture_id:
        return _err("lecture_id는 필수입니다.")
    if not lecture_store.lecture_exists(lecture_id):
        return _err(f"강의 없음: {lecture_id}", error_type="not_found")

    # 중복 기동 방지 — 상태 파일이 building 이고 10분 미경과면 진행 중으로 응답
    sp = _video_state_path(lecture_id)
    if sp.exists():
        try:
            st = json.loads(sp.read_text(encoding="utf-8"))
            if st.get("status") == "building":
                from datetime import datetime
                age = (datetime.now() - datetime.fromisoformat(st.get("updated_at"))).total_seconds()
                if age < 600:
                    return _ok({"status": "building", "note": "이미 렌더 중 — video_state.json 으로 진행 확인",
                                "state_file": str(sp)})
        except Exception:
            pass

    opts = {k: tool_input.get(k) for k in
            ("voice", "rate", "transition", "output_filename", "bgm_path",
             "duration_per_scene", "width", "height")}

    if tool_input.get("wait") in (True, "true", "True", 1, "1"):
        _write_video_state(lecture_id, {"status": "building"})
        try:
            result = _deck_video_build(lecture_id, opts)
        except Exception as e:
            _write_video_state(lecture_id, {"status": "error", "error": str(e)})
            return _err(f"동영상 렌더 실패: {e}")
        _write_video_state(lecture_id, {"status": "done", **result})
        return _ok(result)

    # 기본: 백그라운드 — 즉시 반환, 진행·결과는 상태 파일
    import threading

    def _bg():
        try:
            result = _deck_video_build(lecture_id, opts)
            _write_video_state(lecture_id, {"status": "done", **result})
        except Exception as e:
            _write_video_state(lecture_id, {"status": "error", "error": str(e)})

    _write_video_state(lecture_id, {"status": "building"})
    threading.Thread(target=_bg, daemon=True).start()
    return _ok({
        "status": "queued",
        "note": "백그라운드 렌더 시작 (슬라이드 수·나레이션 길이에 따라 수 분). "
                "완료·결과는 video_state.json — 같은 op 재호출로도 진행 확인.",
        "state_file": str(sp),
    })


# ─────────────────────────────────────────────────────────────────────
# 디스패치 테이블 — 진짜 함수 참조 (--check 가 AST 로 키 정확 비교)
# ─────────────────────────────────────────────────────────────────────

_OP_DISPATCHERS = {
    "lecture_op": {"list": _lecture_list, "create": _lecture_create, "load": _lecture_load,
                   "delete": _lecture_delete, "open": _lecture_open},
    "slide_op": {"create": _slide_create, "edit": _slide_edit, "delete": _slide_delete,
                 "patch": _slide_patch_spec, "rerender": _slide_rerender,
                 "image_edit": _slide_image_edit},
    "material_op": {"add": _material_add, "remove": _material_remove},
    "deck_op": {"reorder": _deck_reorder, "export": _deck_export, "video": _deck_video},
}
# 모두 op 필수 — _OP_DEFAULTS 항목 없음.
