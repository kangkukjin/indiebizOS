"""정기보고앱 핸들러 — 정기 보고서(예: AI 동향 보고서) 뷰어 + 작성 트리거.

보고서는 항상 **맥**의 outputs/ 폴더에 저장되고, 작성도 **맥의 시스템 AI**가 한다.
그래서 이 액션은 runs_on: mac_only — 폰 앱모드에서 버튼을 눌러도 분산 IBL 이
맥에 단건 라우팅하므로, 읽기/작성 모두 맥에서 일어난다 (폰 로컬 폴더가 아니다).

보고서 타입은 REPORT_TYPES 매핑으로 추상화한다. 지금은 'ai_trend' 하나뿐이지만
폴더·파일패턴·작성 프롬프트만 등록하면 새 타입이 전 op·앱 모드에 자동 반영된다.
"""

import re
from pathlib import Path

# data/packages/installed/tools/report-viewer/handler.py → parents[5] = indiebizOS 루트
REPO_ROOT = Path(__file__).resolve().parents[5]

# === 보고서 타입 ↔ 폴더 매핑 (추상화 — 새 타입은 여기만 추가) ===
REPORT_TYPES = {
    "ai_trend": {
        "label": "AI 동향 보고서",
        "folder": "outputs/ai_trend_reports",
        "pattern": "ai_trend_report_*.md",
        "prompt": "AI 동향 보고서 써줘",   # 시스템 AI에게 보낼 작성 의도(가이드가 검색·로드됨)
    },
}
DEFAULT_TYPE = "ai_trend"

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _resolve_type(tool_input: dict):
    """type 파라미터 → (type_id, cfg). 비면 기본, 미지원이면 (None, None)."""
    t = (tool_input.get("type") or "").strip() or DEFAULT_TYPE
    cfg = REPORT_TYPES.get(t)
    return (t, cfg) if cfg else (t, None)


def _folder(cfg: dict) -> Path:
    return (REPO_ROOT / cfg["folder"]).resolve()


def _list_files(cfg: dict):
    """해당 타입 폴더의 보고서 파일을 최신순(파일명 사전순 역순)으로."""
    folder = _folder(cfg)
    if not folder.is_dir():
        return []
    return sorted(folder.glob(cfg["pattern"]), key=lambda p: p.name, reverse=True)


def _record(cfg: dict, path: Path) -> dict:
    m = _DATE_RE.search(path.name)
    date = m.group(1) if m else ""
    title = f"{cfg['label']} — {date}" if date else path.name
    return {
        "title": title,
        "date": date,
        "filename": path.name,
        "path": str(path),
        "sub": date or path.name,
    }


def _split_blocks(text: str):
    """본문을 빈 줄 기준 블록으로 — thread 뷰가 한 블록=한 버블로 렌더(줄바꿈 보존)."""
    parts = re.split(r"\n\s*\n", text)
    return [{"text": p.strip()} for p in parts if p.strip()]


def _read_path(path_str: str):
    """등록된 보고서 폴더 안의 .md 만 읽도록 제한(임의 파일 읽기 차단)."""
    path = Path(path_str).expanduser().resolve()
    allowed = {_folder(cfg) for cfg in REPORT_TYPES.values()}
    if path.parent not in allowed or path.suffix.lower() != ".md":
        return None
    if not path.is_file():
        return None
    return path


# ---- op 구현 ----

def _op_types(tool_input: dict, context) -> dict:
    types = [{"value": tid, "label": cfg["label"]} for tid, cfg in REPORT_TYPES.items()]
    return {"success": True, "types": types, "count": len(types)}


def _op_list(tool_input: dict, context) -> dict:
    t, cfg = _resolve_type(tool_input)
    if not cfg:
        return {"success": False, "error": f"알 수 없는 보고서 타입: {t}"}
    reports = [_record(cfg, p) for p in _list_files(cfg)]
    return {
        "success": True,
        "type": t,
        "label": cfg["label"],
        "reports": reports,
        "count": len(reports),
    }


def _read_into(cfg: dict, t: str, path: Path) -> dict:
    rec = _record(cfg, path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return {"success": False, "error": f"읽기 실패: {e}"}
    rec.update({
        "success": True,
        "type": t,
        "label": cfg["label"],
        "blocks": _split_blocks(text),
    })
    return rec


def _op_read(tool_input: dict, context) -> dict:
    path_str = tool_input.get("path")
    if path_str:
        path = _read_path(path_str)
        if not path:
            return {"success": False, "error": "허용된 보고서 폴더의 .md 파일이 아닙니다."}
        # 경로의 타입 추론(폴더 매칭)
        for tid, cfg in REPORT_TYPES.items():
            if path.parent == _folder(cfg):
                return _read_into(cfg, tid, path)
        return {"success": False, "error": "보고서 타입을 식별할 수 없습니다."}
    # path 없으면 type 의 최신
    return _op_latest(tool_input, context)


def _op_latest(tool_input: dict, context) -> dict:
    t, cfg = _resolve_type(tool_input)
    if not cfg:
        return {"success": False, "error": f"알 수 없는 보고서 타입: {t}"}
    files = _list_files(cfg)
    if not files:
        return {
            "success": True,
            "type": t,
            "label": cfg["label"],
            "title": cfg["label"],
            "empty": True,
            "blocks": [{"text": f"아직 작성된 {cfg['label']}가 없습니다.\n\n'작성' 탭에서 새 보고서를 만들어 보세요. 작성은 맥의 시스템 AI가 수행합니다."}],
        }
    return _read_into(cfg, t, files[0])


def _op_new(tool_input: dict, context) -> dict:
    """맥의 시스템 AI에게 보고서 작성을 비동기 큐잉(파이프라인 비의존)."""
    t, cfg = _resolve_type(tool_input)
    if not cfg:
        return {"success": False, "error": f"알 수 없는 보고서 타입: {t}"}
    try:
        import sys
        backend = str(REPO_ROOT / "backend")
        if backend not in sys.path:
            sys.path.insert(0, backend)
        from system_ai_runner import SystemAIRunner
        SystemAIRunner.send_message(content=cfg["prompt"], from_agent="정기보고앱")
    except Exception as e:  # noqa: BLE001 — 큐잉 실패는 사용자에게 그대로 보고
        return {"success": False, "error": f"시스템 AI 작성 요청 실패: {e}"}
    return {
        "success": True,
        "type": t,
        "label": cfg["label"],
        "queued": True,
        "message": f"{cfg['label']} 작성을 시작했습니다. 완료되면 '최신'·'목록' 탭에서 확인할 수 있습니다.",
    }


_OP_DISPATCHERS = {
    "report_op": {
        "list": _op_list,
        "read": _op_read,
        "latest": _op_latest,
        "new": _op_new,
        "types": _op_types,
    },
}
_OP_DEFAULTS = {"report_op": "list"}


def execute(tool_input: dict, context):
    name = context.tool_name
    table = _OP_DISPATCHERS.get(name)
    if not table:
        return {"success": False, "error": f"알 수 없는 도구: {name}"}
    op = (tool_input.get("op") or _OP_DEFAULTS.get(name) or "list").strip()
    fn = table.get(op)
    if not fn:
        return {"success": False, "error": f"알 수 없는 op: {op} (허용: {', '.join(table)})"}
    return fn(tool_input, context)
