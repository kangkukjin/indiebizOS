"""build_ibl_nodes 앱 표면 어휘·검증 계층 (2026-07-18 모듈화 — 1500줄 규칙).

build_ibl_nodes.py 에서 verbatim 이동: APP_* 뷰 어휘 선언(표면 언어 표준 코어)과
app: 블록/standalone 계기/템플릿 param 검증, 뷰-어휘·뷰-렌더러 가드.
★뷰-렌더러 가드(check_view_renderers)가 스캔하는 대상은 렌더러 *파일 경로*
(GenericInstrument.tsx·api_launcher_web.py)라 이 모듈 이동과 무관.
"""
from __future__ import annotations
from pathlib import Path

from iblbuild_common import (
    UNIVERSAL_PARAM_KEYS,
    RUNTIME_META_KEYS,
    CORPUS_PARAM_ALLOW,
    _dir_read_keys,
    _extract_action_param_aliases,
)
from iblbuild_derive import build_tool_index

# === app: 블록 검증 (2026-06-11, 원격 앱 표면 제네릭화 2단계) ===
# 액션이 자기 앱 표면(inputs/action 템플릿/view)을 선언하면 원격 런처가 자동 파생.
# 어휘 명세: docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md. 소비자: api_launcher_web._derive_instruments.
APP_VIEW_TYPES = {"metric", "kv", "kv_list", "card_list", "image_grid", "sparkline", "list_action", "thread", "form", "editable_list", "map", "calendar", "group", "blocks", "media_player"}
# 뷰-이벤트 → 액션 바인딩(상호작용을 데이터로): map 프리미티브가 사용자 조작을 액션으로 흘린다.
#   marker_click=마커 클릭(IBL 템플릿: 페이로드 $id/$name/$lat/$lng/$url · 또는 {stream: true}=마커 url 을 클라이언트 영상 재생, CCTV) · moveend/center_drag=지도 이동·중심 드래그(자동 재조회, $lat/$lng/$radius/$radius_km) · search_here="이 지역에서 검색" 버튼(사용자가 영역을 잡고 명시적 클릭 시 현재 뷰포트로 재조회, $lat/$lng/$radius/$radius_km)
APP_VIEW_EVENTS = {"marker_click", "moveend", "center_drag", "search_here"}
APP_EVENT_VARS = {"lat", "lng", "id", "name", "radius", "radius_km", "url"}  # 이벤트 페이로드가 액션 템플릿에 주입하는 $변수
APP_INPUT_TYPES = {"text", "select"}
APP_FORM_FIELD_TYPES = {"text", "select", "toggle", "textarea", "images", "date", "time", "datetime", "recurrence", "folder"}
# ai_dock 어피던스(textarea 위 ephemeral AI 제안 — 요청→제안→반영/첨부/닫기). BinNote 656 UX 를
# 어휘로 흡수 — 어떤 선언형 form 이든 textarea 에 붙일 수 있다. dismiss 는 항상, 아래는 적용 모드.
APP_AIDOCK_MODES = {"replace", "append"}
APP_KEYS = {"instrument", "icon", "name", "order", "mode", "mode_order", "modes",
            "note", "auto_run", "inputs", "buttons", "action", "view", "renderer", "compose", "filter",
            "phone_render",
            # top_buttons: 탭과 무관하게 계기 최상단에 항상 보이는 버튼(소개발행 등). 인스트루먼트 레벨.
            "top_buttons",
            # system: true = 런처 직속 시스템 표면(메신저·커뮤니티) — 데스크탑 앱 그리드에서 제외,
            # 원격/폰(리모컨)은 노출 유지. 진입점은 런처 버튼·전용 창.
            "system"}
APP_TPL_FILTERS = {"round", "num", "abs", "arrow"}  # + 'opt:' / 'trunc:' 접두 허용

# === 뷰-어휘 문서-동기 가드 (2026-07-03, ibl.md '표현 언어의 층위' 조항 집행) ===
# app: 뷰 어휘는 표면 언어의 표준 코어(위 APP_* 선언 + 렌더러 2곳)인데, 에이전트가
# 앱 저술 때 읽는 교육 문서의 어휘 줄은 삼각검증 밖이라 조용히 낡는다(실사례:
# new_action_checklist.md "7종"·ibl.md "12종" 박제 — 실제 13종). 두 문서의 정형 줄
# "view 프리미티브 N종: a / b / …" · "form 필드 N종: …" 을 코드 선언과 집합 대조한다.
_APP_VOCAB_DOC_PATHS = (
    "data/system_docs/ibl.md",
    "data/guides/new_action_checklist.md",
)


def check_app_vocab_docs(root: Path) -> list[str]:
    """교육 문서의 뷰-어휘 줄 ↔ APP_VIEW_TYPES/APP_FORM_FIELD_TYPES 집합·개수 대조."""
    import re as _re

    declared = {"view 프리미티브": APP_VIEW_TYPES, "form 필드": APP_FORM_FIELD_TYPES}
    issues: list[str] = []
    for rel in _APP_VOCAB_DOC_PATHS:
        fp = root / rel
        if not fp.is_file():
            issues.append(f"{rel}: 문서 부재")
            continue
        text = fp.read_text(encoding="utf-8")
        for label, decl in declared.items():
            # 어휘 줄: "<label> N종: a / b / …" (— 이후는 부연이라 절단). N종에 숫자 필수
            # 라 조항 산문의 "N종: …" 예시는 매치되지 않는다.
            matches = _re.findall(rf"{_re.escape(label)}\s*(\d+)종:\s*([^\n—]+)", text)
            if not matches:
                issues.append(f"{rel}: '{label} N종: …' 정형 어휘 줄 없음")
                continue
            for n_str, names_str in matches:
                names = {w.strip() for w in names_str.split("/") if w.strip()}
                if int(n_str) != len(decl):
                    issues.append(
                        f"{rel}: {label} 개수 불일치 — 문서 {n_str}종 vs 코드 선언 {len(decl)}종"
                    )
                if names != decl:
                    missing = sorted(decl - names)
                    extra = sorted(names - decl)
                    issues.append(
                        f"{rel}: {label} 집합 불일치 — 문서에 없음 {missing} / 문서에만 있음 {extra}"
                    )
    return issues


def check_view_renderers(root: Path) -> list[str]:
    """뷰 어휘(APP_VIEW_TYPES) ↔ 렌더러 2곳의 p.type 디스패치 파리티(뷰-렌더러 가드).

    build 는 app: 블록이 *선언한* view type 이 enum 에 있는지만 봤다 — 하지만 그 type 을
    실제로 *그리는* 렌더러 코드가 없으면 success:true 인데 빈 화면(좀비 어휘)이다.
    check_launcher_handlers(어휘→라우터→main.js) 와 같은 패턴을 뷰 계층에 적용:
    데스크탑(GenericInstrument.tsx if-chain)·원격(api_launcher_web.py renderPrim if-chain)
    두 렌더러가 각 view type 을 디스패치하는지 정규식으로 확인한다.

    견고화(경량 모델·리팩터 대비):
      · `\\bp\\.type` 단어경계 — inp.type/f.type/apChat.type 오채집 제거.
      · if-chain(p.type===) 와 switch(case '…') 두 문법을 union 추출 — 부분 리팩터로
        한 view 만 문법이 바뀌어도 거짓 하드에러가 안 나게(과채집은 '누락' 방향엔 무해).
      · 알려진 view type 추출량이 기대치의 70% 미만이면 형식 전면 변경으로 보고 graceful skip.
    '누락' 방향(enum 에 있으나 렌더러에 없음)만 하드 에러로 emit — 렌더러에만 있는 여분
    (예: 'select' 하위 프리미티브)은 무시(거짓양성 회피). OVERRIDES/STATIC 컴포넌트
    (Newspaper·Book·Invest 등)는 제네릭 렌더러 밖이라 이 검사 범위 아님(사각지대)."""
    import re as _re
    issues: list[str] = []
    desktop = root / "frontend" / "src" / "components" / "GenericInstrument.tsx"
    remote = root / "backend" / "api_launcher_web.py"
    if not desktop.is_file() or not remote.is_file():
        return issues  # 소스 부재(폰/헤드리스) — graceful skip
    try:
        dtext = desktop.read_text(encoding="utf-8")
        rtext = remote.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues
    pats = (_re.compile(r"\bp\.type\s*===\s*['\"](\w+)['\"]"),
            _re.compile(r"\bcase\s+['\"](\w+)['\"]"))

    def _extract(text: str) -> set[str]:
        out: set[str] = set()
        for pat in pats:
            out.update(pat.findall(text))
        return out

    desktop_types = _extract(dtext)
    remote_types = _extract(rtext)
    thresh = max(1, int(len(APP_VIEW_TYPES) * 0.7))
    if (len(desktop_types & APP_VIEW_TYPES) < thresh
            or len(remote_types & APP_VIEW_TYPES) < thresh):
        return issues  # 디스패치 형식 전면 변경 — graceful skip(거짓양성 회피)
    for missing in sorted(APP_VIEW_TYPES - desktop_types):
        issues.append(
            f"뷰 어휘 {missing!r} 가 APP_VIEW_TYPES 에 선언됐으나 데스크탑 렌더러 "
            f"(frontend/src/components/GenericInstrument.tsx)에 p.type 케이스 없음 — "
            f"빈 화면(좀비 어휘). 렌더러에 추가하거나 어휘에서 제거."
        )
    for missing in sorted(APP_VIEW_TYPES - remote_types):
        issues.append(
            f"뷰 어휘 {missing!r} 가 APP_VIEW_TYPES 에 선언됐으나 원격 렌더러 "
            f"(backend/api_launcher_web.py renderPrim)에 p.type 케이스 없음 — "
            f"데스크탑/원격 파리티 깨짐. 원격 렌더러에 추가."
        )
    return issues


def _app_action_templates(app: dict) -> list[str]:
    """app 블록에서 IBL 액션 템플릿 문자열 전부 수집 (참조 존재 검증용)."""
    import re as _re  # noqa: F401 (지역 사용 명시)
    out: list[str] = []
    if isinstance(app.get("action"), str):
        out.append(app["action"])
    cmp = app.get("compose")  # 블록 레벨 작성바(채팅/피드) — $text + {행필드} 템플릿
    if isinstance(cmp, dict) and isinstance(cmp.get("action"), str):
        out.append(cmp["action"])
    for b in app.get("buttons") or []:
        if isinstance(b, dict) and isinstance(b.get("action"), str):
            out.append(b["action"])
    for inp in app.get("inputs") or []:
        if isinstance(inp, dict) and isinstance(inp.get("options_action"), str):
            out.append(inp["options_action"])

    def walk_view(view):
        for p in view or []:
            if not isinstance(p, dict):
                continue
            # form(저장) / editable_list(추가·삭제) 액션
            if p.get("type") == "form" and isinstance(p.get("action"), str):
                out.append(p["action"])
            if p.get("type") == "form":  # 보조 액션(즐겨찾기 토글·삭제 등)
                for a in p.get("actions") or []:
                    if isinstance(a, dict) and isinstance(a.get("action"), str):
                        out.append(a["action"])
                for f in p.get("fields") or []:  # images 필드의 add_image/remove_image · ai_dock 템플릿
                    if not isinstance(f, dict):
                        continue
                    if f.get("type") == "images":
                        for k in ("add_action", "remove_action"):
                            if isinstance(f.get(k), str):
                                out.append(f[k])
                    dock = f.get("ai_dock")
                    if isinstance(dock, dict) and isinstance(dock.get("action"), str):
                        out.append(dock["action"])
            if p.get("type") in ("editable_list", "calendar"):
                if isinstance(p.get("delete_action"), str):
                    out.append(p["delete_action"])
                add = p.get("add")
                if isinstance(add, dict) and isinstance(add.get("action"), str):
                    out.append(add["action"])
            for _bk in ("button", "button2"):  # list_action 행 버튼(▶ 재생 / ⬇ 다운로드)
                btn = p.get(_bk)
                if isinstance(btn, dict) and isinstance(btn.get("action"), str):
                    out.append(btn["action"])
            rsel = p.get("select")  # list_action 행 드롭다운({sel}=고른 값 주입)
            if isinstance(rsel, dict) and isinstance(rsel.get("action"), str):
                out.append(rsel["action"])
            drill = p.get("item_click")
            if isinstance(drill, dict):
                if isinstance(drill.get("action"), str):
                    out.append(drill["action"])
                dcmp = drill.get("compose")  # 드릴(스레드) 레벨 작성바
                if isinstance(dcmp, dict) and isinstance(dcmp.get("action"), str):
                    out.append(dcmp["action"])
                walk_view(drill.get("view"))
                for tab in drill.get("tabs") or []:  # 드릴 상세 탭(대화/정보)
                    if isinstance(tab, dict):
                        tcmp = tab.get("compose")
                        if isinstance(tcmp, dict) and isinstance(tcmp.get("action"), str):
                            out.append(tcmp["action"])
                        walk_view(tab.get("view"))
            on = p.get("on")  # 뷰-이벤트(마커클릭·지도이동)→액션 템플릿
            if isinstance(on, dict):
                for v in on.values():
                    if isinstance(v, str):
                        out.append(v)

    walk_view(app.get("view"))
    return out


def _block_local_keys(blk: dict) -> set:
    """블록 내 암묵 입력 키 집합 — compose($text), form 필드, editable_list add 필드.
    드릴 view·tabs 까지 재귀. validate 의 $key↔input 검사에 합류."""
    keys: set = set()

    def from_compose(c):
        if isinstance(c, dict) and c.get("action"):
            keys.add("text")
            if isinstance(c.get("channels"), dict):  # 채널 선택 → action 의 $channel_type/$to 주입
                keys.update(("channel_type", "to"))

    def from_fields(fields):
        for f in fields or []:
            if isinstance(f, dict) and f.get("key"):
                keys.add(f["key"])
            if isinstance(f, dict) and f.get("type") == "images":  # add/remove_image 가 $path 런타임 주입
                keys.add("path")
            if isinstance(f, dict) and isinstance(f.get("ai_dock"), dict):  # ai_dock.action 이 $dock(요청) 주입
                keys.add("dock")

    def walk(view):
        for p in view or []:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "form":
                from_fields(p.get("fields"))
            if p.get("type") == "editable_list" and isinstance(p.get("add"), dict):
                from_fields(p["add"].get("fields"))
            if p.get("type") == "calendar" and isinstance(p.get("add"), dict):
                from_fields(p["add"].get("fields"))  # add.fields 키(제목/시간/반복/타입/메모 등)
                keys.add("date")  # 렌더러가 선택일 date 를 add 액션에 자동 주입
            if isinstance(p.get("on"), dict):  # 뷰-이벤트 액션의 $lat/$lng/$id/$radius 등은 이벤트 페이로드가 주입
                keys.update(APP_EVENT_VARS)
            drill = p.get("item_click")
            if isinstance(drill, dict):
                from_compose(drill.get("compose"))
                walk(drill.get("view"))
                for tab in drill.get("tabs") or []:
                    if isinstance(tab, dict):
                        from_compose(tab.get("compose"))
                        walk(tab.get("view"))

    from_compose(blk.get("compose"))
    walk(blk.get("view"))
    return keys


def _check_ai_dock(where: str, field: dict) -> list[str]:
    """textarea 필드의 ai_dock 어피던스 검증 — action(AI 템플릿) 필수, modes 는 {replace,append} 부분집합.
    ai_dock.action 은 $<필드키>(현재 텍스트)·$dock(요청 입력)을 주입받는다(_block_local_keys 참조)."""
    issues: list[str] = []
    dock = field.get("ai_dock")
    if not isinstance(dock, dict):
        issues.append(f"{where}: ai_dock 는 매핑")
        return issues
    if field.get("type") != "textarea":
        issues.append(f"{where}: ai_dock 는 textarea 필드 전용 (현재 type={field.get('type')!r})")
    if not isinstance(dock.get("action"), str) or not dock.get("action"):
        issues.append(f"{where}: ai_dock.action(AI IBL 템플릿) 필수")
    modes = dock.get("modes")
    if modes is not None and (not isinstance(modes, list) or not modes
                              or any(m not in APP_AIDOCK_MODES for m in modes)):
        issues.append(f"{where}: ai_dock.modes 는 {sorted(APP_AIDOCK_MODES)} 부분집합")
    return issues


def _check_compose_channels(where: str, cmp) -> list[str]:
    """compose.channels(발신 채널 선택) 스키마 검증 — from/type/value 필수, sendable 은 리스트."""
    issues: list[str] = []
    if not isinstance(cmp, dict):
        return issues
    ch = cmp.get("channels")
    if ch is None:
        return issues
    if not isinstance(ch, dict):
        issues.append(f"{where}: compose.channels 는 매핑")
        return issues
    for k in ("from", "type", "value"):
        if not isinstance(ch.get(k), str) or not ch.get(k):
            issues.append(f"{where}: compose.channels.{k}(필드명) 필수")
    if ch.get("sendable") is not None and not isinstance(ch.get("sendable"), list):
        issues.append(f"{where}: compose.channels.sendable 은 채널 타입 리스트")
    return issues


def _app_check_filter_block(where: str, blk: dict) -> list[str]:
    """app.filter 구조 검증 — 정적(items) 또는 동적(from_field) 둘 중 하나.
    items=재조회 칩([{label,value,default?}], 선택 시 $key 로 액션 재호출).
    from_field=클라이언트 측 결과-필드 동적 칩(distinct 값, 재조회 없이 items 거름). from=거를 배열 경로(기본 items)."""
    issues: list[str] = []
    f = blk.get("filter")
    if f is None:
        return issues
    if not isinstance(f, dict):
        issues.append(f"{where}: app.filter 는 매핑이어야 함")
        return issues
    has_items = isinstance(f.get("items"), list) and bool(f["items"])
    has_ff = isinstance(f.get("from_field"), str) and bool(f["from_field"])
    if not has_items and not has_ff:
        issues.append(f"{where}: app.filter 는 items(정적 칩) 또는 from_field(결과-필드 동적 칩) 필수")
    if has_items and has_ff:
        issues.append(f"{where}: app.filter 는 items 와 from_field 중 하나만(정적 vs 동적)")
    if f.get("from") is not None and not isinstance(f.get("from"), str):
        issues.append(f"{where}: app.filter.from 은 거를 배열 경로(문자열)")
    return issues


def _app_check_view(qualified: str, view, depth: int = 0, in_group: bool = False) -> list[str]:
    """view 프리미티브 배열 구조 검증 (드릴 뷰 재귀 포함).

    in_group=True 는 group 콤비네이터 내부 view — 원격 rowDrill 이 최상위 view[vi] 로만 항목을 찾아
    중첩 카드의 item_click 을 못 잇는다. 데스크탑만 되고 원격이 깨지는 드리프트를 막으려 item_click 금지
    (링크·버튼은 됨). group-내부-드릴이 필요해지면 원격 rowDrill 을 group 인지하게 고친 뒤 허용.
    """
    issues: list[str] = []
    if not isinstance(view, list) or not view:
        issues.append(f"{qualified}: app.view 는 비어있지 않은 리스트여야 함")
        return issues
    for i, p in enumerate(view):
        where = f"{qualified}: app.view[{i}]" + (" (드릴)" if depth else "")
        if not isinstance(p, dict):
            issues.append(f"{where} 가 매핑이 아님")
            continue
        ptype = p.get("type")
        if ptype not in APP_VIEW_TYPES:
            issues.append(f"{where}: 미지의 프리미티브 type={ptype!r} (어휘: {sorted(APP_VIEW_TYPES)})")
            continue
        if ptype in ("kv_list", "card_list", "image_grid", "sparkline", "list_action", "thread", "editable_list", "blocks") and not p.get("from"):
            issues.append(f"{where}: {ptype} 는 from(데이터 경로) 필수")
        if ptype == "card_list" and not isinstance(p.get("card"), dict):
            issues.append(f"{where}: card_list 는 card 매핑 필수")
        if ptype == "thread" and not p.get("text"):
            issues.append(f"{where}: thread 는 text(버블 본문 템플릿) 필수")
        if ptype == "form":
            if not isinstance(p.get("action"), str):
                issues.append(f"{where}: form 은 action(저장 IBL 템플릿) 필수")
            fields = p.get("fields")
            if not isinstance(fields, list) or not fields:
                issues.append(f"{where}: form 은 fields(필드 리스트) 필수")
            else:
                for fi, f in enumerate(fields):
                    if not isinstance(f, dict) or not f.get("key"):
                        issues.append(f"{where}: form.fields[{fi}] key 필수")
                    elif f.get("type") not in APP_FORM_FIELD_TYPES:
                        issues.append(f"{where}: form.fields[{fi}] type={f.get('type')!r} (허용: {sorted(APP_FORM_FIELD_TYPES)})")
                    if isinstance(f, dict) and f.get("ai_dock") is not None:
                        issues.extend(_check_ai_dock(f"{where}: form.fields[{fi}]", f))
            # 보조 액션(즐겨찾기 토글·삭제 등) — label + action 필수, style 은 danger 만
            acts = p.get("actions")
            if acts is not None:
                if not isinstance(acts, list):
                    issues.append(f"{where}: form.actions 는 리스트")
                else:
                    for ai, a in enumerate(acts):
                        if not isinstance(a, dict) or not a.get("label") or not isinstance(a.get("action"), str):
                            issues.append(f"{where}: form.actions[{ai}] label·action(IBL 템플릿) 필수")
                        elif a.get("style") not in (None, "danger"):
                            issues.append(f"{where}: form.actions[{ai}] style={a.get('style')!r} (허용: danger)")
        if ptype == "group":
            # 파티션 콤비네이터 — from 리스트를 by 키로 나눠 그룹마다 내부 view 를 재귀 렌더(data={items: 멤버}).
            # table:groupby(집계)와 달리 멤버를 유지한다. 뷰-계층의 groupby. 내부 view 는 from:items 로 그룹 슬라이스 참조.
            if not isinstance(p.get("by"), str) or not p.get("by"):
                issues.append(f"{where}: group 은 by(파티션 키 템플릿, 예 '{{query}}') 필수")
            issues.extend(_app_check_view(qualified, p.get("view"), depth + 1, in_group=True))
        if ptype == "calendar":
            # 월 그리드 + 선택일 상세 + add.fields 폼(form 필드 어휘 재사용, date 자동주입). from=이벤트 리스트.
            if not p.get("from"):
                issues.append(f"{where}: calendar 는 from(이벤트 리스트 경로) 필수")
            add = p.get("add")
            if add is not None:
                if not isinstance(add, dict) or not isinstance(add.get("action"), str):
                    issues.append(f"{where}: calendar.add 는 action(IBL 템플릿) 필수")
                else:
                    for fi, f in enumerate(add.get("fields") or []):
                        if not isinstance(f, dict) or not f.get("key"):
                            issues.append(f"{where}: calendar.add.fields[{fi}] key 필수")
                        elif f.get("type") not in APP_FORM_FIELD_TYPES:
                            issues.append(f"{where}: calendar.add.fields[{fi}] type={f.get('type')!r} (허용: {sorted(APP_FORM_FIELD_TYPES)})")
            if p.get("delete_action") is not None and not isinstance(p.get("delete_action"), str):
                issues.append(f"{where}: calendar.delete_action 은 IBL 템플릿 문자열")
        if ptype == "editable_list":
            if not p.get("display"):
                issues.append(f"{where}: editable_list 는 display(행 표시 템플릿) 필수")
            add = p.get("add")
            if add is not None and (not isinstance(add, dict) or not isinstance(add.get("action"), str)):
                issues.append(f"{where}: editable_list.add 는 action(IBL 템플릿) 필수")
            if p.get("delete_action") is not None and not isinstance(p.get("delete_action"), str):
                issues.append(f"{where}: editable_list.delete_action 은 IBL 템플릿 문자열")
        if True in p or False in p:  # ★YAML 1.1 함정: 따옴표 없는 on/off/yes/no 키가 불리언으로 파싱됨
            issues.append(f"{where}: 불리언 키 발견 — 'on'(또는 off/yes/no) 키는 YAML 불리언으로 해석됨. 따옴표로 감싸세요('on':)")
        if "on" in p:  # 뷰-이벤트→액션 바인딩 — 현재 map 전용
            on = p.get("on")
            if ptype != "map":
                issues.append(f"{where}: on(뷰-이벤트) 은 map 전용")
            elif not isinstance(on, dict) or not on:
                issues.append(f"{where}: on 은 비어있지 않은 매핑(event→IBL 템플릿)")
            else:
                for ev, atpl in on.items():
                    if ev not in APP_VIEW_EVENTS:
                        issues.append(f"{where}: on 미지의 이벤트 {ev!r} (허용: {sorted(APP_VIEW_EVENTS)})")
                    # marker_click 은 IBL 템플릿(문자열·재조회) 또는 클라이언트 스트림 재생 {stream: true}(CCTV 영상 등) 둘 중 하나.
                    if ev == "marker_click" and isinstance(atpl, dict):
                        if atpl.get("stream") is not True or (set(atpl) - {"stream"}):
                            issues.append(f"{where}: on.marker_click 객체형은 {{stream: true}} 만 허용")
                    elif not isinstance(atpl, str) or not atpl:
                        issues.append(f"{where}: on.{ev} 은 IBL 액션 템플릿 문자열(또는 marker_click 의 {{stream: true}})")
        drill = p.get("item_click")
        if drill is not None:
            if in_group:
                issues.append(f"{where}: group 내부 view 는 item_click(드릴) 미지원 — 원격 rowDrill 제약. 링크(card.link)·버튼 사용")
            if ptype not in ("card_list", "list_action"):
                issues.append(f"{where}: item_click 은 card_list/list_action 전용")
            elif not isinstance(drill, dict) or not isinstance(drill.get("action"), str):
                issues.append(f"{where}: item_click 은 action 템플릿 필수")
            else:
                tabs = drill.get("tabs")
                if isinstance(tabs, list) and tabs:  # 상세 탭(대화/정보)
                    for ti, tab in enumerate(tabs):
                        if not isinstance(tab, dict) or not tab.get("name"):
                            issues.append(f"{where}: item_click.tabs[{ti}] name 필수")
                            continue
                        issues.extend(_app_check_view(qualified, tab.get("view"), depth + 1))
                        tcmp = tab.get("compose")
                        if tcmp is not None and (not isinstance(tcmp, dict) or not isinstance(tcmp.get("action"), str)):
                            issues.append(f"{where}: item_click.tabs[{ti}].compose 는 action 필수")
                        issues.extend(_check_compose_channels(where, tcmp))
                elif "tabs" in drill:
                    issues.append(f"{where}: item_click.tabs 는 비어있지 않은 리스트여야 함")
                else:
                    issues.extend(_app_check_view(qualified, drill.get("view"), depth + 1))
                    dcmp = drill.get("compose")
                    if dcmp is not None and (not isinstance(dcmp, dict) or not isinstance(dcmp.get("action"), str)):
                        issues.append(f"{where}: item_click.compose 는 action(IBL 템플릿) 필수")
                    issues.extend(_check_compose_channels(where, dcmp))
        # button/button2: list_action 은 {action} 행 버튼(2번째=즐겨찾기·다운로드 등). form/editable_list 의 button 은 라벨 문자열이라 제외.
        if ptype not in ("form", "editable_list"):
            for _bk in ("button", "button2"):
                btn = p.get(_bk)
                if btn is None:
                    continue
                # stream:true 버튼 = 클라이언트 측 스트림 재생 지시(StreamPlayer). 행 데이터(url/playable)를
                # 그대로 플레이어로 연다 — IBL action 없이 동작하므로 action 면제(CCTV '▶ 보기' 등).
                if isinstance(btn, dict) and btn.get("stream") is True:
                    continue
                if not isinstance(btn, dict) or not isinstance(btn.get("action"), str):
                    issues.append(f"{where}: {_bk} 은 action 템플릿 필수")
            rsel = p.get("select")  # list_action 행 드롭다운 — action(IBL 템플릿)+options 필수
            if rsel is not None:
                if not isinstance(rsel, dict) or not isinstance(rsel.get("action"), str):
                    issues.append(f"{where}: select 는 action 템플릿 필수")
                elif not isinstance(rsel.get("options"), list) or not rsel["options"]:
                    issues.append(f"{where}: select 는 options 목록 필수")
    return issues


def _app_check_filters(qualified: str, app: dict) -> list[str]:
    """표시 템플릿 '{path|filter}' 의 필터 오타 검출."""
    import re
    issues: list[str] = []
    strings: list[str] = []

    def walk(o):
        if isinstance(o, str):
            strings.append(o)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)

    walk(app.get("view"))
    for m in app.get("modes") or []:          # 명시적 modes 각 탭의 view 도 검사
        if isinstance(m, dict):
            walk(m.get("view"))
    for s in strings:
        for expr in re.findall(r"\{([^{}]+)\}", s):
            for f in [x.strip() for x in expr.split("|")[1:]]:
                if f in APP_TPL_FILTERS or f.startswith("opt:") or f.startswith("trunc:"):
                    continue
                issues.append(f"{qualified}: 미지의 템플릿 필터 {f!r} (in {s!r})")
    return issues


def _validate_app_block(blabel: str, blk: dict, qualified_set: set) -> list[str]:
    """단일 앱 블록(탭 또는 단독 계기) 검증 — 노드 app: 블록과 standalone 매니페스트 공용.

    action(IBL 템플릿) 필수 · view 어휘 · compose · inputs(key/type/select) ·
    템플릿의 [node:action] 실존 · $key↔inputs 대응.
    """
    import re
    issues: list[str] = []
    if not isinstance(blk.get("action"), str) and not blk.get("buttons"):
        issues.append(f"{blabel}: app.action(IBL 템플릿) 또는 buttons 필수")
    # action 있는 블록은 결과를 그릴 view 필수. 버튼 전용(action 없음)은 그릴 데이터가
    # 없어 view 생략 가능 — 단 view 를 선언했으면 구조는 검증한다.
    _view = blk.get("view")
    if isinstance(blk.get("action"), str) or _view is not None:
        issues.extend(_app_check_view(blabel, _view))
    _cmp = blk.get("compose")
    if _cmp is not None and (not isinstance(_cmp, dict) or not isinstance(_cmp.get("action"), str)):
        issues.append(f"{blabel}: app.compose 는 action(IBL 템플릿) 필수")
    issues.extend(_check_compose_channels(blabel, _cmp))
    input_keys: set = set()
    input_keys |= _block_local_keys(blk)
    issues.extend(_app_check_filter_block(blabel, blk))
    _pd = blk.get("filter")
    if isinstance(_pd, dict) and not _pd.get("from_field"):
        input_keys.add(_pd.get("key") or "filter")
    for j, inp in enumerate(blk.get("inputs") or []):
        if not isinstance(inp, dict) or not inp.get("key"):
            issues.append(f"{blabel}: app.inputs[{j}] 에 key 없음")
            continue
        input_keys.add(inp["key"])
        itype = inp.get("type")
        if itype not in APP_INPUT_TYPES:
            issues.append(f"{blabel}: app.inputs[{j}] type={itype!r} (허용: {sorted(APP_INPUT_TYPES)})")
        if itype == "select":
            if inp.get("options"):
                opts = inp["options"]
                if not isinstance(opts, list) or not all(
                    isinstance(o, dict) and "value" in o and "label" in o for o in opts
                ):
                    issues.append(f"{blabel}: app.inputs[{j}] 정적 options 는 [{{value,label}}] 배열")
            elif inp.get("options_action"):
                if not inp.get("options_from"):
                    issues.append(f"{blabel}: app.inputs[{j}] select options_action 에 options_from 필수")
            else:
                issues.append(f"{blabel}: app.inputs[{j}] select 는 정적 options 또는 options_action 필수")
    for t in _app_action_templates(blk):
        for ref_node, ref_action in re.findall(r"\[(\w+):(\w+)\]", t):
            if f"{ref_node}:{ref_action}" not in qualified_set:
                issues.append(f"{blabel}: app 템플릿이 미존재 액션 [{ref_node}:{ref_action}] 참조 ({t!r})")
        for key in re.findall(r"\$(\w+)", t):
            if key not in input_keys:
                issues.append(f"{blabel}: app 템플릿 $%s 에 대응하는 input 없음 ({t!r})" % key)
    return issues


def validate_standalone_instruments(data: dict) -> list[str]:
    """data/instruments/*.yaml (어휘 없는 순수 앱) 검증 — 노드 app: 블록과 같은 어휘.

    각 파일은 하나의 계기: instrument/icon/name 필수 + 각 모드가 앱 블록.
    모드 action: 의 [node:action] 이 실존하는지 검사 → 앱→어휘 참조 깨짐을 저술 시점에 잡음.
    """
    import glob
    import os
    import re
    import yaml
    issues: list[str] = []
    inst_dir = os.path.join(os.path.dirname(__file__), "..", "data", "instruments")
    if not os.path.isdir(inst_dir):
        return issues
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    qualified_set = {
        f"{n}:{a}"
        for n, nd in nodes.items() if isinstance(nd, dict)
        for a in (nd.get("actions") or {})
    }
    for fp in sorted(glob.glob(os.path.join(inst_dir, "*.yaml"))):
        name = os.path.basename(fp)
        try:
            with open(fp, "r", encoding="utf-8") as f:
                m = yaml.safe_load(f) or {}
        except Exception as e:  # noqa: BLE001
            issues.append(f"instruments/{name}: YAML 파싱 실패 — {e}")
            continue
        if not isinstance(m, dict):
            issues.append(f"instruments/{name}: 매핑이어야 함")
            continue
        for req in ("instrument", "icon", "name"):
            if not m.get(req):
                issues.append(f"instruments/{name}: {req} 필수")
        # %BASE% 는 서버측 치환 토큰이라 검증 시엔 그대로 둔 채 [node:action]·$key 만 본다.
        modes = m.get("modes")
        if isinstance(modes, list) and modes:
            for mi, mode in enumerate(modes):
                if not isinstance(mode, dict):
                    issues.append(f"instruments/{name}: modes[{mi}] 가 매핑이 아님")
                    continue
                if not mode.get("name"):
                    issues.append(f"instruments/{name}: modes[{mi}] name(탭 이름) 필수")
                issues.extend(_validate_app_block(f"instruments/{name} modes[{mi}]", mode, qualified_set))
        else:
            issues.append(f"instruments/{name}: modes(비어있지 않은 리스트) 필수")
    return issues


def validate_app_blocks(data: dict) -> list[str]:
    """app: 블록 정합성 — 액션 템플릿의 [node:action] 실존, $key↔inputs, view 어휘, 계기 그룹."""
    import re  # noqa: F401 (verbatim 이동 — 원본 지역 import 유지)
    issues: list[str] = []
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    qualified_set = {
        f"{n}:{a}"
        for n, nd in nodes.items() if isinstance(nd, dict)
        for a in (nd.get("actions") or {})
    }
    groups: dict[str, list[tuple[str, dict]]] = {}

    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict) or "app" not in action:
                continue
            qualified = f"{node_name}:{action_name}"
            app = action["app"]
            if not isinstance(app, dict):
                issues.append(f"{qualified}: app 은 매핑이어야 함")
                continue

            unknown = set(app.keys()) - APP_KEYS
            if unknown:
                issues.append(f"{qualified}: app 미지의 키 {sorted(unknown)} (허용: {sorted(APP_KEYS)})")

            # io(action/view/inputs/템플릿)는 블록 단위로 검증.
            # 명시적 modes(탭)면 각 탭이 독립 블록, 아니면 app 자신이 단일 블록.
            mode_list = app.get("modes")
            if isinstance(mode_list, list) and mode_list:
                blocks: list[tuple[str, dict]] = []
                for mi, m in enumerate(mode_list):
                    if not isinstance(m, dict):
                        issues.append(f"{qualified}: app.modes[{mi}] 가 매핑이 아님")
                        continue
                    if not m.get("name"):
                        issues.append(f"{qualified}: app.modes[{mi}] name(탭 이름) 필수")
                    blocks.append((f"{qualified} modes[{mi}]", m))
            elif "modes" in app:
                issues.append(f"{qualified}: app.modes 는 비어있지 않은 리스트여야 함")
                blocks = []
            else:
                blocks = [(qualified, app)]

            for blabel, blk in blocks:
                issues.extend(_validate_app_block(blabel, blk, qualified_set))

            issues.extend(_app_check_filters(qualified, app))

            gid = app.get("instrument") or action_name
            groups.setdefault(gid, []).append((qualified, app))

    # 계기 그룹 정합
    for gid, members in groups.items():
        partial = [q for q, a in members if bool(a.get("icon")) != bool(a.get("name"))]
        if partial:
            issues.append(f"계기 {gid!r}: icon/name 은 함께 선언해야 함 — 반쪽 선언 {partial}")
        primaries = [q for q, a in members if a.get("icon") and a.get("name")]
        if len(members) == 1:
            q, a = members[0]
            if not (a.get("icon") and a.get("name")):
                issues.append(f"{q}: 단독 계기 {gid!r} 는 icon+name 필수")
        else:
            if len(primaries) != 1:
                issues.append(
                    f"계기 {gid!r}: icon+name 선언 멤버(primary)가 정확히 1개여야 함 (현재 {len(primaries)}: {primaries})"
                )
            no_mode = [q for q, a in members if not a.get("mode")]
            if no_mode:
                issues.append(f"계기 {gid!r}: 복수 멤버는 전원 mode(탭 이름) 필수 — 누락 {no_mode}")
            mode_names = [a.get("mode") for _, a in members if a.get("mode")]
            if len(mode_names) != len(set(mode_names)):
                issues.append(f"계기 {gid!r}: mode 이름 중복 {mode_names}")
    return issues


def _template_param_keys(t: str) -> list[tuple[str, str, set[str]]]:
    """IBL 템플릿 문자열에서 각 [node:action]{...} 의 최상위 리터럴 파라미터 *키* 추출.

    (node, action, {key,...}) 리스트. $변수·{행필드} 는 값이라 키가 아니며(depth>1),
    중첩·따옴표를 추적해 값 안의 콜론/중괄호를 키로 오인하지 않는다. 과소추출(놓침)은
    검사를 건너뛸 뿐이나 과대추출(값→키 오인)은 거짓 하드에러라, 확신 위치의 키만 잡는다."""
    import re as _re
    out: list[tuple[str, str, set[str]]] = []
    for m in _re.finditer(r"\[(\w+):(\w+)\]", t):
        node, action = m.group(1), m.group(2)
        j = m.end()
        n = len(t)
        while j < n and t[j] in " \t":
            j += 1
        keys: set[str] = set()
        if j < n and t[j] == "{":
            depth = 0
            expect_key = False
            k = j
            while k < n:
                c = t[k]
                if c in "\"'":
                    if depth == 1 and expect_key:  # 따옴표 키 "path":
                        km = _re.match(r"([\"'])([A-Za-z_]\w*)\1\s*:", t[k:])
                        if km:
                            keys.add(km.group(2))
                            k += km.end()
                            expect_key = False
                            continue
                    q = c  # 문자열 값 통째 skip(내부 콤마·중괄호 무시)
                    k += 1
                    while k < n and t[k] != q:
                        if t[k] == "\\":
                            k += 1
                        k += 1
                    k += 1
                    continue
                if c == "{":
                    depth += 1
                    if depth == 1:
                        expect_key = True
                    k += 1
                    continue
                if c == "}":
                    depth -= 1
                    k += 1
                    if depth == 0:
                        break
                    continue
                if depth == 1:
                    if c == ",":
                        expect_key = True
                        k += 1
                        continue
                    if c in " \t\n":
                        k += 1
                        continue
                    if expect_key:
                        km = _re.match(r"([A-Za-z_]\w*)\s*:", t[k:])
                        if km:
                            keys.add(km.group(1))
                            k += km.end()
                            expect_key = False
                            continue
                        expect_key = False  # 키 위치가 아님(값 시작)
                    k += 1
                    continue
                k += 1  # depth != 1
        out.append((node, action, keys))
    return out


def validate_app_template_params(data: dict, root: Path) -> list[str]:
    """app:/standalone 템플릿의 리터럴 파라미터 키 ↔ 액션 허용키 대조 (뷰-어휘 밖 침묵 닫기).

    validate_corpus_params 와 같은 허용집합(핸들러 읽기키 ∪ aliases ∪ 보편키 ∪ target_key)을
    쓰되 출처가 학습 코퍼스가 아니라 *저술된 앱 템플릿*이다. 선언형 앱이 [sense:realty]{deposit_max:…}
    처럼 핸들러가 안 읽는 키를 넘겨 조용히 무시되는 오답(성공처럼 보임)을 저술 시점(빌드)에
    하드 실패로 잡는다. open_params 액션·미존재 액션(별도 가드가 잡음)은 스킵 = 보수적."""
    import glob
    import os
    import yaml

    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    action_cfg: dict[str, dict] = {}
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if isinstance(action, dict):
                action_cfg[f"{node_name}:{action_name}"] = action

    aliases = _extract_action_param_aliases(data)
    tool_index = build_tool_index(root)
    backend_keys = _dir_read_keys((root / "backend").glob("*.py"))
    pkg_cache: dict[Path, set[str]] = {}

    # (label, template) 수집 — 노드 app: 블록 + standalone 매니페스트.
    templates: list[tuple[str, str]] = []
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict) or "app" not in action:
                continue
            app = action["app"]
            if not isinstance(app, dict):
                continue
            qualified = f"{node_name}:{action_name}"
            mode_list = app.get("modes")
            blocks = ([m for m in mode_list if isinstance(m, dict)]
                      if isinstance(mode_list, list) and mode_list else [app])
            for blk in blocks:
                for tmpl in _app_action_templates(blk):
                    templates.append((qualified, tmpl))
    inst_dir = os.path.join(os.path.dirname(__file__), "..", "data", "instruments")
    if os.path.isdir(inst_dir):
        for fp in sorted(glob.glob(os.path.join(inst_dir, "*.yaml"))):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    mani = yaml.safe_load(f) or {}
            except Exception:
                continue
            if not isinstance(mani, dict):
                continue
            for mode in mani.get("modes") or []:
                if isinstance(mode, dict):
                    for tmpl in _app_action_templates(mode):
                        templates.append((f"instruments/{os.path.basename(fp)}", tmpl))

    def _known_for(qualified: str, ac: dict) -> set[str]:
        known = set(UNIVERSAL_PARAM_KEYS) | set(RUNTIME_META_KEYS)
        if ac.get("target_key"):
            known.add(ac["target_key"])
        known |= aliases.get(qualified, set())
        known |= CORPUS_PARAM_ALLOW.get(qualified, set())
        tool_name = ac.get("tool")
        if ac.get("router") == "handler" and tool_name and tool_name in tool_index:
            pkg_dir = tool_index[tool_name][0]
            if pkg_dir not in pkg_cache:
                pkg_cache[pkg_dir] = _dir_read_keys(pkg_dir.rglob("*.py"))
            known |= pkg_cache[pkg_dir]
        else:
            known |= backend_keys
        return known

    issues: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for label, tmpl in templates:
        for node, action, keys in _template_param_keys(tmpl):
            # '_'/'$' 접두 키는 시스템/템플릿 메타 — 런타임 check_params 와 동일 제외.
            keys = {k for k in keys if not k.startswith(("_", "$"))}
            if not keys:
                continue
            qualified = f"{node}:{action}"
            ac = action_cfg.get(qualified)
            if not isinstance(ac, dict):
                continue  # 미존재 액션 참조는 _validate_app_block 이 잡음
            if ac.get("open_params"):
                continue  # 자유 키 선언 — 스킵
            unknown = sorted(keys - _known_for(qualified, ac))
            if not unknown:
                continue
            dedup = (label, qualified, ",".join(unknown))
            if dedup in seen:
                continue
            seen.add(dedup)
            issues.append(
                f"{label}: app 템플릿이 [{qualified}] 에 미인식 파라미터 {unknown} 전달 — "
                f"핸들러가 읽지 않는 키라 조용히 무시됨(오타?). 액션 정의처 aliases: 블록에 추가 · "
                f"오타 정정 · open_params 중 택1. ({tmpl!r})"
            )
    return issues
