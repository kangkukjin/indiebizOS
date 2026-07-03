"""
ibl_param_vocab.py - 인자(파라미터) 층 어휘 검사 (2026-07-03)

동사(node:action)는 미존재 시 시끄럽게 실패하고 op 는 enum 으로 어휘화됐지만,
인자는 열린 dict 라 오타·미인식 키가 핸들러 .get() 기본값으로 조용히 흡수된다
(예: deposit_max 를 deposit 으로 불러도 무필터 전체 결과가 "성공"으로 반환).
여기서는 스키마 강제(거부) 대신 *가시화*를 택한다 — 에이전트 루프(평가 3라운드)와
조종실 dry-run 이 이미 재시도 기계이므로, 미인식 키를 경고+최근접 제안으로
소리 나게 만들면 다음 턴 자가교정이 된다. 침묵 인자 드리프트는 증류를 타고
코퍼스(몸)에 박제되므로, 이 검사는 해마 위생 장치이기도 하다.

허용집합 — 오탐 회피가 우선 (자주 틀리는 경고는 침묵보다 나쁘다. 실측:
input_schema 단독은 알려진-정상 코퍼스에서 79키 오경보):
  패키지 .py 읽기키(AST) ∪ tool.json input_schema ∪ aliases ∪ target_key ∪ 보편키
scripts/build_ibl_nodes.py 의 코퍼스 param 정합 검사와 같은 수 — 추출기와 상수를
여기서 단일 소유하고 빌드가 import 한다 (tool.json 파생화와 같은 결).

검사 대상: router=handler + tool 매핑 액션만 (그 외 라우터는 스킵 = 보수적).
탈출구: 액션 정의(src yaml)에 open_params: true — 자유 키를 정당하게 받는 액션용.
소비처: ibl_engine(실행 경고) · api_ibl /validate(dry-run) · ibl_usage_rag(증류 게이트)
        · vocab_crystallization(마찰 신호 D — data/param_friction.jsonl).
"""

import ast
import difflib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# === 어휘 상수 (빌드의 코퍼스 정합 검사와 공유 — 단일 소스) ===

# 모든 액션이 자연히 받는 보편 키 (op 디스패치/레거시 target).
UNIVERSAL_PARAM_KEYS = {"op", "target"}

# 런타임 메타 키 — 핸들러 인자가 아니라 라우팅이 읽는 키 (ibl_routing._resolve_project_path).
RUNTIME_META_KEYS = {"project_id"}

# 핸들러/별칭에 의도적으로 없는 문서화된 예외 (동적 pop 등 정적 검출 불가).
# 코퍼스 정제/별칭으로 해소되면 제거할 것.
CORPUS_PARAM_ALLOW: Dict[str, Set[str]] = {
    # browser_op은 2차 selector 'mode'를 _OP_SELECTOR로 동적 pop(handler.py) —
    # 정적 리터럴이 아니라 검출 불가. 핸들러가 실제로 읽으므로 의도된 예외.
    "limbs:browser": {"mode"},
}

# 마찰 로그 (결정화 감지기 신호 D 의 입력)
_FRICTION_MAX_BYTES = 1_000_000  # 초과 시 뒤쪽 절반만 보존
_PKG_KEYS_TTL = 600  # 패키지 읽기키 캐시 수명(초) — 패키지 편집은 드묾, 재계산 수십 ms


def _friction_path() -> Path:
    from runtime_utils import get_base_path
    return Path(get_base_path()) / "data" / "param_friction.jsonl"


# === 읽기키 AST 추출 (빌드에서 이주 — 단일 소유) ===

def _file_read_keys(text: str) -> Set[str]:
    """파이썬 소스에서 '핸들러가 읽는 키' 후보를 AST로 추출.
    함수 파라미터명 + .get/_arg/pop 문자열 인자 + call 키워드 인자 + 문자열 subscript."""
    keys: Set[str] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return keys
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.args
            for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
                keys.add(arg.arg)
        elif isinstance(n, ast.Call):
            for kw in n.keywords:
                if kw.arg:
                    keys.add(kw.arg)
            func = n.func
            fname = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
            if fname in ("_arg", "get", "pop"):
                for arg in n.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        keys.add(arg.value)
        elif isinstance(n, ast.Subscript):
            sl = n.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                keys.add(sl.value)
    keys.discard(None)
    return keys


def _dir_read_keys(paths) -> Set[str]:
    """여러 .py 파일에서 읽기키 합집합."""
    keys: Set[str] = set()
    for py in paths:
        try:
            keys |= _file_read_keys(py.read_text(encoding="utf-8"))
        except Exception:
            continue
    return keys


# === 패키지별 허용집합 (TTL 캐시) ===

_pkg_keys_cache: Dict[str, tuple] = {}  # pkg_dir_str -> (computed_at, keys)


def _package_read_keys(pkg_dir: Path) -> Set[str]:
    key = str(pkg_dir)
    hit = _pkg_keys_cache.get(key)
    now = time.time()
    if hit and now - hit[0] < _PKG_KEYS_TTL:
        return hit[1]
    keys = _dir_read_keys(pkg_dir.rglob("*.py"))
    _pkg_keys_cache[key] = (now, keys)
    return keys


def _alias_keys(action_config: dict) -> Set[str]:
    """aliases: {정규키: [별칭...]} → 정규키 ∪ 별칭 전체."""
    out: Set[str] = set()
    aliases = action_config.get("aliases")
    if isinstance(aliases, dict):
        for canonical, alts in aliases.items():
            out.add(str(canonical))
            out.update(str(a) for a in (alts or []))
    return out


def _schema_props(tool_name: str) -> Set[str]:
    try:
        from tool_loader import load_tool_schema
        tool_def = load_tool_schema(tool_name) or {}
        props = (tool_def.get("input_schema") or {}).get("properties") or {}
        return set(props.keys())
    except Exception:
        return set()


def _documented_vocab(action_config: dict, tool_name: str) -> Set[str]:
    """제안(did-you-mean)용 문서화 어휘 — 허용집합보다 좁은, 사람이 쓰라고 만든 키."""
    vocab = _schema_props(tool_name) | _alias_keys(action_config) | {"op"}
    tk = action_config.get("target_key")
    if tk:
        vocab.add(tk)
    return vocab


def allowed_param_keys(node: str, action: str,
                       action_config: dict) -> Optional[Set[str]]:
    """액션의 허용 파라미터 키 집합. 계산 불가/검사 부적합이면 None (= 검사 스킵).

    handler 라우터 + tool 매핑 액션만 대상. open_params: true 는 자유 키 선언(스킵).
    """
    if not isinstance(action_config, dict):
        return None
    if action_config.get("open_params"):
        return None
    if action_config.get("router") != "handler":
        return None
    tool_name = action_config.get("tool")
    if not tool_name:
        return None
    try:
        from tool_loader import build_tool_package_map, get_tools_path
        pkg_name = build_tool_package_map().get(tool_name)
        if not pkg_name:
            return None
        pkg_dir = get_tools_path() / pkg_name
        if not pkg_dir.is_dir():
            return None
        keys = set(_package_read_keys(pkg_dir))
    except Exception:
        return None

    qualified = f"{node}:{action}"
    keys |= _schema_props(tool_name)
    keys |= _alias_keys(action_config)
    keys |= UNIVERSAL_PARAM_KEYS | RUNTIME_META_KEYS
    keys |= CORPUS_PARAM_ALLOW.get(qualified, set())
    tk = action_config.get("target_key")
    if tk:
        keys.add(tk)
    return keys


# === 검사 본체 ===

def check_params(node: str, action: str, params: Any,
                 action_config: Optional[dict] = None) -> Optional[dict]:
    """미인식 파라미터 검사. 문제 없으면 None, 있으면
    {"unknown": [...], "suggest": {키: 제안}, "message": 한 줄 경고}.

    거부하지 않는다 — 호출자가 결과에 경고를 실어 다음 턴 자가교정을 돕는다.
    '_'/'$' 접두 키는 시스템/템플릿 메타라 제외.
    """
    if not isinstance(params, dict) or not params:
        return None
    if action_config is None:
        try:
            from ibl_engine import _load_nodes_config
            action_config = (_load_nodes_config().get("nodes", {})
                             .get(node, {}).get("actions", {}).get(action)) or {}
        except Exception:
            return None

    allowed = allowed_param_keys(node, action, action_config)
    if allowed is None:
        return None

    user_keys = {k for k in params.keys()
                 if isinstance(k, str) and not k.startswith(("_", "$"))}
    unknown = sorted(user_keys - allowed)
    if not unknown:
        return None

    vocab = _documented_vocab(action_config, action_config.get("tool", ""))
    suggest: Dict[str, str] = {}
    for k in unknown:
        close = difflib.get_close_matches(k, sorted(vocab), n=1, cutoff=0.55)
        if close:
            suggest[k] = close[0]

    parts = [f"미인식 파라미터 {unknown} — [{node}:{action}] 핸들러가 읽지 않는 키라 "
             f"조용히 무시됐을 수 있습니다."]
    if suggest:
        parts.append("비슷한 키: " + ", ".join(f"{k}→{v}" for k, v in suggest.items()) + ".")
    if vocab:
        parts.append(f"이 액션의 주요 키: {sorted(vocab)}.")
    return {"unknown": unknown, "suggest": suggest, "message": " ".join(parts)}


def check_code_params(code: str) -> List[dict]:
    """IBL 코드 문자열의 모든 statement 를 정적 검사 (증류 게이트/도구용).
    각 항목: {"action": "node:action", "unknown": [...], "message": ...}"""
    try:
        from ibl_parser import parse
        parsed = parse(code)
    except Exception:
        return []

    def walk(obj):
        res = []
        if isinstance(obj, dict):
            if "_node" in obj and "action" in obj:
                res.append(obj)
            for v in obj.values():
                res += walk(v)
        elif isinstance(obj, list):
            for v in obj:
                res += walk(v)
        return res

    issues: List[dict] = []
    for st in walk(parsed):
        node = st.get("_node") or ""
        action = st.get("action") or ""
        if not node or not action:
            continue
        w = check_params(node, action, st.get("params") or {})
        if w:
            issues.append({"action": f"{node}:{action}", **w})
    return issues


# === 마찰 로그 (결정화 감지기 신호 D) ===

def log_param_friction(node: str, action: str, unknown: List[str],
                       agent_id: Optional[str] = None) -> None:
    """미인식-키 이벤트를 JSONL 누적. 같은 (액션,키) 반복 = alias 후보/결핍 파라미터 신호."""
    try:
        path = _friction_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": datetime.now().isoformat(timespec="seconds"),
                 "action": f"{node}:{action}", "unknown": unknown,
                 "agent": agent_id or ""}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if path.stat().st_size > _FRICTION_MAX_BYTES:
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(lines[len(lines) // 2:]) + "\n", encoding="utf-8")
    except Exception:
        pass  # 로그는 부차 — 실행을 절대 방해하지 않는다


def read_param_friction(days: int = 7) -> List[dict]:
    """최근 N일 마찰 이벤트 (감지기 스캔용)."""
    path = _friction_path()
    if not path.is_file():
        return []
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    out: List[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("ts", "") >= cutoff:
                out.append(e)
    except Exception:
        return []
    return out
