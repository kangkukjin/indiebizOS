"""selfbuild_gate.py — 자작 관문 (2026-09-07, 사용자 판정 '자작 관문도 만들어줘').

뿌리: 어휘 우회에는 관문이 있고(`shell_shadow_gate`), 관용구 우회에도 관문이 있는데
(`fn_recognizer.variant_of`), **"세상에 이미 있는 걸 자작하고 있다"** 에는 관문이 없었다 —
`data/guides/world_tools.md` 지도와 의식 규정의 '세상의 방식'·'전문가의 선택' 필드뿐이고,
둘 다 *규정 순간*에 서는 것이다. 실측된 실패는 늘 **행동 순간**에 있었다(3D 모델링 요청에
Blender 대신 브라우저 상자를 300줄 짜고 "최선"이라 보고).

관문이 세는 것은 도메인이 아니라 **행동**이다. 어떤 라이브러리를 베꼈는지는 기계가 판정할
수 없지만, "이 턴에 새 구현 코드를 한 무더기 썼는데 세상의 도구를 한 번도 확인하지 않았다"는
셀 수 있다. 셀 수 있으면 관문이 실패시킨다(카운터를 심고 두고 보지 않는다).

세 조건이 **모두** 참일 때만 선다:
  ① 새 구현 코드가 이 턴 누적 THRESHOLD_LINES 줄을 넘었다 (파일별 최대치의 합 —
     같은 파일을 고쳐 다시 쓰는 반복은 두 번 세지 않는다)
  ② 이 턴에 세상을 확인한 적이 없다 (`[self:install_lib]` · 지도 읽기 · read_guide)
  ③ 쓴 코드가 지도에 있는 도구를 하나도 쓰고 있지 않다 (이미 세상 어깨 위면 통과)
그리고 몸의 코드(RED·등록 스크립트·패키지)는 애초에 세지 않는다 — 지도는 세상의 능력이지
몸의 능력이 아니다.

거절문은 `shell_shadow_gate` 와 같은 규약을 따른다 — **다음 한 걸음을 돌려준다**. 지도를 열고
후보를 `check: true` 로 물어보면 관문이 걷힌다. 확인하고도 마땅한 도구가 없으면 그대로
이어서 쓰면 된다 — 관문은 *답*을 강요하지 않고 *확인*을 강요한다.

★잎 모듈(표준 라이브러리만) — base 층. 지도는 파생물이 아니라 사람·AI 가 고치는 가이드라
빌드 파생표를 두지 않고 mtime 캐시로 그때그때 읽는다(단일 소스 유지, 파생 부패 없음).
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Dict, List, Optional, Set

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAP_REL = os.path.join("data", "guides", "world_tools.md")
LOCAL_MAP_REL = os.path.join("data", "guides", "world_tools_local.md")

#: 이 턴에 새로 쓴 구현 코드가 이 줄 수를 넘으면 관문이 선다(파일별 최대치의 합).
THRESHOLD_LINES = 150
#: 이보다 짧은 쓰기는 원장에도 안 적는다 — 한 줄 고치기는 자작이 아니다.
MIN_COUNTED_LINES = 12
#: 지도 이름 대조용으로 들고 있는 코드 본문 상한(메모리 경계).
_MAX_KEPT_CODE = 60_000
#: 원장 수명 — 턴이 닫히면 reset() 이 걷지만, 못 걷힌 것은 이 시간 뒤 스스로 삭는다.
_TTL_SECONDS = 3600

#: 구현 코드로 세는 확장자. 데이터·문서·설정(.md·.json·.csv·.yaml·.txt)은 자작이 아니다.
_CODE_EXT = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html", ".htm", ".vue", ".svelte",
    ".go", ".rs", ".java", ".kt", ".swift", ".c", ".h", ".cc", ".cpp", ".hpp", ".m", ".mm",
    ".rb", ".php", ".lua", ".scala", ".dart", ".sh", ".zsh", ".bash", ".r", ".jl", ".scad",
}

#: 몸의 코드 — 지도의 관할이 아니다. RED(자기수정)·등록 스크립트·패키지·격리 사본.
_BODY_PREFIXES = ("backend/", "frontend/", "scripts/", "data/scripts/", "data/packages/",
                  ".worktrees/", "cloud_training/")

#: 지도에서 뽑되 코드에 흔해 오탐이 되는 이름 — 대조에서 뺀다.
_TOO_GENERIC = {
    "json", "html", "css", "http", "https", "sqlite", "python", "node", "web", "api",
    "table", "chart", "image", "text", "data", "file", "self", "sense", "code", "open",
    "build", "test", "conda", "brew", "pip", "cdn", "gui", "cli", "install", "cask",
    # 표에서 딸려 나오는 낱말 — 도구 이름이 아니다(영어 낱말·IBL 노드·brew 옵션·탭 주인·확장 이름)
    "deal", "engines", "spatial", "no-quarantine", "gerlero", "pdf", "app", "src", "url",
    "log", "min", "max", "sum", "row", "col", "key", "val", "str", "int", "new", "get",
}

#: 예시 파일 이름(`in.scad`·`out.stl`)은 도구가 아니다.
_ARTIFACT_RE = re.compile(r"^[a-z0-9_-]+\.(stl|scad|obj|step|png|jpg|csv|py|md|nc|txt|json|pdf|db)$")

_lock = threading.Lock()
_ledger: Dict[str, "_TurnLedger"] = {}
_map_cache: Dict[str, object] = {"names": None, "stamp": None}

_TOKEN_RE = re.compile(r"[a-z][a-z0-9_.+-]{2,}")
_BACKTICK_RE = re.compile(r"`([^`]+)`")


class _TurnLedger:
    """한 턴(=agent_id)의 자작 원장."""

    def __init__(self) -> None:
        self.lines_by_path: Dict[str, int] = {}
        self.code = ""              # 지도 이름 대조용 누적 본문(상한)
        self.consulted: Optional[str] = None   # 확인한 출처(있으면 관문 걷힘)
        self.fired = 0
        self.opened_at = time.time()

    @property
    def total_lines(self) -> int:
        return sum(self.lines_by_path.values())


# ---------------------------------------------------------------- 지도
def _map_names(root: str) -> Set[str]:
    """세상의 도구 지도에서 이름을 뽑는다 — 도구 이름 · `pip:X` · 백틱 토큰(import 이름·바이너리).

    지도는 마크다운 표다(`| 도구 | 잘하는 일 | 통로 | 비고 |`). 표의 어느 칸에서든 이름이 될 만한
    토큰을 모으고, 코드에 흔한 낱말은 뺀다. 이름 하나라도 코드에 있으면 '이미 세상 어깨 위'다.
    """
    paths = [os.path.join(root, MAP_REL), os.path.join(root, LOCAL_MAP_REL)]
    stamp = tuple((p, os.path.getmtime(p)) for p in paths if os.path.exists(p))
    with _lock:
        if _map_cache["stamp"] == stamp and _map_cache["names"] is not None:
            return _map_cache["names"]           # type: ignore[return-value]

    names: Set[str] = set()
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        for line in text.splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2 or set(cells[0]) <= {"-", ":"}:
                continue                          # 구분선
            # 도구 칸 — "Three.js / Babylon.js", "FEniCSx (dolfinx 0.11)" 처럼 갈라 적힌다
            for chunk in re.split(r"[/·,()]", cells[0]):
                _add_name(names, chunk)
            # 나머지 칸의 백틱 토큰 — `pip:trimesh` · `cv2` · `blender -b -P …`
            for cell in cells[1:]:
                for tok in _BACKTICK_RE.findall(cell):
                    tok = tok.replace("pip:", " ").replace("brew install", " ")
                    for chunk in re.split(r"[\s/·,()<>]", tok):
                        _add_name(names, chunk)
    with _lock:
        _map_cache["stamp"] = stamp
        _map_cache["names"] = names
    return names


def _add_name(names: Set[str], chunk: str) -> None:
    chunk = chunk.strip().strip("*`'\"").lower()
    chunk = re.sub(r"^[^a-z0-9]+|[^a-z0-9.+-]+$", "", chunk)
    if len(chunk) < 3 or chunk in _TOO_GENERIC:
        return
    if not re.match(r"^[a-z][a-z0-9_.+-]*$", chunk) or _ARTIFACT_RE.match(chunk):
        return
    names.add(chunk)
    head = chunk.split(".")[0]  # path-ok: 도구 이름의 접미(three.js→three), 값의 경로가 아니다
    if len(head) >= 4 and head not in _TOO_GENERIC:
        names.add(head)


def _uses_world_tool(code: str, root: str) -> Optional[str]:
    """코드가 지도의 도구를 하나라도 쓰고 있으면 그 이름 — 아니면 None."""
    names = _map_names(root)
    if not names:
        return None
    for tok in set(_TOKEN_RE.findall(code.lower())):
        if tok in names:
            return tok
        head = tok.split(".")[0]  # path-ok: 코드 토큰의 모듈 머리(scipy.stats→scipy), 값의 경로가 아니다
        if head in names:
            return head
    return None


# ---------------------------------------------------------------- 원장
def _entry(agent_id: str) -> Optional["_TurnLedger"]:
    key = (agent_id or "").strip()
    if not key:
        return None
    with _lock:
        e = _ledger.get(key)
        if e is not None and time.time() - e.opened_at > _TTL_SECONDS:
            _ledger.pop(key, None)
            e = None
        if e is None:
            e = _ledger[key] = _TurnLedger()
        return e


def reset(agent_id: str) -> None:
    """턴 시작 — 원장을 걷는다(파이프라인이 부른다)."""
    with _lock:
        _ledger.pop((agent_id or "").strip(), None)


def note_consult(agent_id: str, source: str) -> None:
    """세상을 확인했다 — `[self:install_lib]` · 지도 읽기 · read_guide 가 부른다."""
    e = _entry(agent_id)
    if e is not None and not e.consulted:
        e.consulted = source or "확인"


def state(agent_id: str) -> Dict[str, object]:
    """관측용 — 시험과 로그가 읽는다(판정에는 쓰지 않는다)."""
    e = _entry(agent_id)
    if e is None:
        return {}
    return {"lines": e.total_lines, "files": len(e.lines_by_path),
            "consulted": e.consulted, "fired": e.fired}


# ---------------------------------------------------------------- 판정
def is_body_path(path: str, root: str) -> bool:
    """몸의 코드인가 — RED·등록 스크립트·패키지·격리 사본은 지도의 관할이 아니다."""
    try:
        rel = os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")
    except ValueError:
        return False
    if rel.startswith("../"):
        return False
    return rel.startswith(_BODY_PREFIXES)


def note_code_write(agent_id: str, path: str, content: str,
                    root: Optional[str] = None) -> Optional[str]:
    """새 구현 코드 쓰기를 원장에 적고, 관문이 서면 **거절문**을 돌려준다(통과=None).

    부르는 자리는 쓰기 싱크 하나다 — 셸 그림자 관문이 네이티브 Write/Edit·인라인 파이썬을
    이미 `[self:write]` 로 몰아 두었으므로, 이 자리가 코드가 몸에 들어오는 길목이다.
    """
    base = root or _ROOT
    if not isinstance(content, str) or not path:
        return None
    if os.path.splitext(path)[1].lower() not in _CODE_EXT:
        return None
    if is_body_path(path, base):
        return None
    lines = content.count("\n") + 1
    if lines < MIN_COUNTED_LINES:
        return None

    e = _entry(agent_id)
    if e is None:
        return None                                # 신원 없는 호출(시험·배치)은 세지 않는다
    key = os.path.abspath(path)
    if lines > e.lines_by_path.get(key, 0):        # 같은 파일 재작성은 최대치만 — 다듬기는 자작이 아니다
        e.lines_by_path[key] = lines
    if len(e.code) < _MAX_KEPT_CODE:
        e.code += "\n" + content[: _MAX_KEPT_CODE - len(e.code)]

    if e.consulted or e.total_lines <= THRESHOLD_LINES:
        return None
    used = _uses_world_tool(e.code, base)
    if used:
        e.consulted = f"코드가 이미 {used} 를 쓴다"
        return None
    e.fired += 1
    return _refusal(e)


def _refusal(e: "_TurnLedger") -> str:
    return (
        f"[자작 관문] 이 턴에 새 구현 코드 {e.total_lines}줄({len(e.lines_by_path)}개 파일)을 썼는데 "
        f"세상의 도구를 한 번도 확인하지 않았다. 이 일을 업으로 하는 사람이 쓰는 도구가 이미 있다면 "
        f"지금이 갈림길이다 — 표준 라이브러리로 다시 짠 것은 대개 장난감이 된다.\n"
        f"다음 한 걸음(둘 중 하나면 관문이 걷힌다):\n"
        f'  [self:read]{{path: "data/guides/world_tools.md"}}   # 이 일을 잘하는 도구가 표에 있나\n'
        f'  [self:install_lib]{{package: "<후보>", check: true}}  # 부작용 0 — 여러 개 물어도 된다\n'
        f"확인하고도 마땅한 도구가 없거나 이미 쓰고 있으면 그대로 이어서 써라 — 관문은 답이 아니라 "
        f"확인을 요구한다. 방금 쓰려던 내용은 저장되지 않았으니 확인 뒤 같은 쓰기를 다시 보내라."
    )
