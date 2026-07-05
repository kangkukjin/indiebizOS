"""앱 모드 홈 레이아웃 — 자율주행 데스크탑의 개인화 레이어를 앱모드에 이식.

자율주행 탭(projects.json)은 사용자가 만든 *레코드*라 이동/휴지통/폴더 상태를
레코드 자체에 저장한다. 반면 앱모드의 아이콘은 매니페스트(/launcher/instruments)에서
매번 파생되는 *카탈로그*라, 상태를 앱에 못 박을 수 없다.

→ 앱 id 로 키잉하는 얇은 개인화 레이어를 별도 파일에 둔다. 카탈로그(무엇이 존재하나)와
   레이아웃(어떻게 배치·정리했나)의 깨끗한 분리. 매니페스트가 새 app: 블록으로 커져도
   레이아웃은 그대로 유지되고, 모르는 앱은 홈에 자동 등장(기존 '자동 등장' 불변식 보존).

스키마 (data/launcher_app_layout.json):
{
  "version": 1,
  "positions":  { "<appId|folderId>": [x, y] },   # 홈 자유 배치 좌표
  "folders":    { "<folderId>": {"label": "금융", "icon": "📁"} },
  "membership": { "<appId>": "<folderId>" },        # 앱 → 폴더 소속
  "removed":    ["<appId>", ...]                     # 앱저장소로 내려간 것(홈에서 뺌)
}

휴지통 의미(사용자 결정): 홈에서 빼서 앱저장소로 되돌림 + 그 앱이 사용 중 쌓은 데이터를
지우고 초기화(soft reset). 앱의 완전한 제거(패키지 언인스톨)는 별개 — 앱저장소에서 선택.
"""

import os
import json

LAYOUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "launcher_app_layout.json")

_DEFAULT = {
    "version": 1,
    "positions": {},
    "folders": {},
    "membership": {},
    "removed": [],       # 앱저장소로 내려간 것(홈에서 뺌, 복구 가능)
    "uninstalled": [],   # 완전 삭제 — 카탈로그에서 영구 제거(홈·앱저장소 어디에도 안 나옴)
}


def load_layout() -> dict:
    """레이아웃 로드 — 파일 없거나 깨졌으면 빈 기본값(모든 앱 홈에 자동 배치)."""
    try:
        with open(LAYOUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(_DEFAULT)
        # 누락 키 보정 (구버전 파일 안전)
        out = dict(_DEFAULT)
        for k in ("positions", "folders", "membership"):
            v = data.get(k)
            if isinstance(v, dict):
                out[k] = v
        for k in ("removed", "uninstalled"):
            v = data.get(k)
            if isinstance(v, list):
                out[k] = [str(x) for x in v]
        out["version"] = data.get("version", 1)
        return out
    except FileNotFoundError:
        return dict(_DEFAULT)
    except Exception:
        return dict(_DEFAULT)


def _sanitize(data: dict) -> dict:
    """클라이언트가 보낸 레이아웃을 스키마에 맞춰 정제 (신뢰 경계 — localhost/인증 뒤이지만 방어)."""
    out = dict(_DEFAULT)
    if not isinstance(data, dict):
        return out
    pos = data.get("positions")
    if isinstance(pos, dict):
        clean = {}
        for k, v in pos.items():
            if isinstance(v, (list, tuple)) and len(v) == 2:
                try:
                    clean[str(k)] = [int(v[0]), int(v[1])]
                except (TypeError, ValueError):
                    continue
        out["positions"] = clean
    fol = data.get("folders")
    if isinstance(fol, dict):
        clean = {}
        for k, v in fol.items():
            if isinstance(v, dict):
                clean[str(k)] = {
                    "label": str(v.get("label", "폴더"))[:60],
                    "icon": str(v.get("icon", "📁"))[:8],
                }
        out["folders"] = clean
    mem = data.get("membership")
    if isinstance(mem, dict):
        out["membership"] = {str(k): str(v) for k, v in mem.items() if v}
    for k in ("removed", "uninstalled"):
        v = data.get(k)
        if isinstance(v, list):
            out[k] = sorted({str(x) for x in v})
    out["version"] = 1
    return out


def save_layout(data: dict) -> dict:
    """레이아웃 저장 — 정제 후 원자적 쓰기."""
    clean = _sanitize(data)
    os.makedirs(os.path.dirname(LAYOUT_PATH), exist_ok=True)
    tmp = LAYOUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    os.replace(tmp, LAYOUT_PATH)
    return clean


def _instrument_reset_code(app_id: str) -> str | None:
    """매니페스트에서 앱의 선언적 reset IBL 코드를 찾는다.

    앱의 app: 블록(또는 standalone 매니페스트)에 reset: "<IBL 코드>" 를 선언하면
    휴지통에 넣을 때 그 코드로 앱 데이터를 초기화한다. 선언 없으면 None(깊은 초기화 안 함).
    임의 DB 삭제를 일반화하지 않는다 — 각 앱이 '내 데이터가 무엇인지' 스스로 선언해야 한다.
    """
    try:
        from api_launcher_web import _derive_instruments
        manifest = _derive_instruments().get("instruments", [])
    except Exception:
        return None
    for inst in manifest:
        if inst.get("id") != app_id:
            continue
        # 계기 최상위 또는 첫 모드에 reset 선언 허용
        if isinstance(inst.get("reset"), str):
            return inst["reset"]
        for m in (inst.get("modes") or []):
            if isinstance(m, dict) and isinstance(m.get("reset"), str):
                return m["reset"]
    return None


def reset_app_data(app_id: str) -> dict:
    """휴지통 의미 — 앱이 사용 중 쌓은 데이터를 지우고 초기화.

    앱이 reset IBL 코드를 선언했으면 그걸 실행(앱이 정의한 '내 데이터' 초기화).
    선언 없으면 no-op(안전) — 클라이언트측 상태(입력값 기억 등) 청소는 프론트가 담당.
    """
    code = _instrument_reset_code(app_id)
    if not code:
        return {"reset": False, "reason": "no_reset_declared", "app_id": app_id}
    try:
        from system_tools import _execute_ibl_unified
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        _execute_ibl_unified({"code": code}, base, agent_id="system_ai")
        return {"reset": True, "app_id": app_id}
    except Exception as e:
        return {"reset": False, "reason": str(e), "app_id": app_id}
