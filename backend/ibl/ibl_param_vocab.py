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

# 런타임 메타 키 — 핸들러 인자가 아니라 라우팅이 읽는 키.
#   project_id: ibl_routing.resolve_project_path · scope: ibl_routing scope 해소
#   (same/system/cross/workspace, ibl_routing.py params.get("scope") + ibl_engine action scope).
RUNTIME_META_KEYS = {"project_id", "scope"}

# 라우팅이 *가로채는* 키 — 작가가 params 에 적어도 핸들러까지 도달하지 못한다.
#   project_path: ibl_routing.resolve_project_path 가 호출자 정체성 경로(2번 우선순위)를
#   먼저 반환하므로, 호출자 경로가 있는 한 params 의 값은 영영 안 읽힌다. 이 부류의
#   침묵은 특히 비싸다 — 빈 결과가 아니라 *다른 대상의 정상 응답*이 돌아와 오답을
#   참으로 믿게 된다(2026-08-18 [self:recent_chats] 실측: 시스템 AI 가 투자 프로젝트를
#   지정했는데 자기 대화가 멀쩡한 모양으로 반환). 의도를 나르는 정본 키는 project_id.
ROUTING_INTERCEPTED_KEYS: Dict[str, str] = {"project_path": "project_id"}

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


def documented_vocab(action_config: dict, tool_name: str) -> Set[str]:
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


def _check_intercepted(node: str, action: str, params: dict,
                       action_config: dict) -> Optional[dict]:
    """라우팅 가로채기 키만 보는 좁은 검사 — 허용키 출처가 없는 라우터(driver/system/…)용.

    전면 검사(allowed_param_keys)는 핸들러 패키지의 AST 읽기키에 기대므로 코어 액션엔
    쓸 수 없다(코어 src yaml 에는 params 스키마가 아예 없다 — target_key 24건이 전부).
    그래서 여기서는 *스키마를 요구하지 않는* 좁은 판정만 한다: 그 액션이 이 키를
    자기 것으로 선언(tool.json input_schema · aliases · target_key)하지 않았는데
    params 에 들어왔다면, 그 값은 라우팅에 먹혀 사라진다.
    선언한 액션(web-builder 부류)은 정당한 도구 인자이므로 통과한다.
    """
    if not isinstance(action_config, dict):
        return None
    declared = _alias_keys(action_config) | UNIVERSAL_PARAM_KEYS | RUNTIME_META_KEYS
    tk = action_config.get("target_key")
    if tk:
        declared.add(tk)
    tool_name = action_config.get("tool")
    if tool_name:
        try:
            declared |= _schema_props(tool_name)
        except Exception:
            pass
    hits = [k for k in sorted(ROUTING_INTERCEPTED_KEYS)
            if k in params and k not in declared]
    if not hits:
        return None
    suggest = {k: ROUTING_INTERCEPTED_KEYS[k] for k in hits}
    parts = [
        f"'{k}' 는 [{node}:{action}] 에 전달되지 않습니다 — 라우팅이 호출자 경로로 "
        f"덮어쓰므로 조용히 무시되고, 빈 결과가 아니라 *다른 대상의 정상 응답*이 "
        f"돌아옵니다. 대신 '{suggest[k]}' 를 쓰세요."
        for k in hits
    ]
    return {"unknown": hits, "suggest": suggest, "soft": {},
            "message": " ".join(parts)}


# === 검사 본체 ===

# 공용 런타임 컨텍스트 키 — 액션 어휘가 아니라 실행 경로가 소비하는 키(라우팅이 프로젝트
# 해소·발신 신원에 씀). /ibl/execute 직접 경로는 이 키를 *요구*하므로, 액션별 어휘 검사가
# 나무라면 "요구하며 경고하는" 자기모순이 된다 (2026-08-20 상상훈련 17회차 F17-1(b)).
_CONTEXT_KEYS = {"project_id", "agent_id"}


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
            from ibl_registry import load_nodes_installed
            action_config = (load_nodes_installed().get("nodes", {})
                             .get(node, {}).get("actions", {}).get(action)) or {}
        except Exception:
            return None

    allowed = allowed_param_keys(node, action, action_config)
    if allowed is None:
        # 허용키 출처가 없는 액션(비핸들러 라우터·open_params·tool 미매핑).
        # 전면 검사는 여전히 스킵하되(보수적), 라우팅 가로채기 키만은 좁게 본다 —
        # 그 부류는 조용한 무시가 *그럴듯한 오답*을 만들어 침묵 비용이 특히 크다.
        return _check_intercepted(node, action, params, action_config)

    user_keys = {k for k in params.keys()
                 if isinstance(k, str) and not k.startswith(("_", "$"))
                 and k not in _CONTEXT_KEYS}
    unknown = sorted(user_keys - allowed)

    vocab = documented_vocab(action_config, action_config.get("tool", ""))

    # 소프트 층 (2026-08-16 상상훈련 F2): 패키지 AST 합집합(allowed)은 내부 파이썬
    # 식별자까지 품는 과대 허용이라, [self:notebook]{notebook: ...} 같은 오타가 침묵
    # 통과했다. 문서화 어휘 밖 + 코퍼스 용례에도 없는 키 + 문서화 키 근접(제안 키가
    # params 에 없음)일 때만 조용히 무시될 가능성을 경고한다 — 코퍼스=관용 사전이라
    # 기존 정상 용법(측정: 94키/599히트)은 구조적으로 오탐하지 않는다.
    soft: Dict[str, str] = {}
    _soft_cands = sorted((user_keys & allowed) - vocab)
    if _soft_cands:
        attested = _corpus_action_keys(node, action)
        if attested is not None:
            for k in _soft_cands:
                if k in attested:
                    continue
                close = difflib.get_close_matches(k, sorted(vocab), n=1, cutoff=0.55)
                if close and close[0] not in user_keys:
                    soft[k] = close[0]

    if not unknown and not soft:
        return None

    suggest: Dict[str, str] = {}
    for k in unknown:
        close = difflib.get_close_matches(k, sorted(vocab), n=1, cutoff=0.55)
        if close:
            suggest[k] = close[0]

    parts = []
    if unknown:
        parts.append(f"미인식 파라미터 {unknown} — [{node}:{action}] 핸들러가 읽지 않는 키라 "
                     f"조용히 무시됐을 수 있습니다.")
        if suggest:
            parts.append("비슷한 키: " + ", ".join(f"{k}→{v}" for k, v in suggest.items()) + ".")
    for k, v in soft.items():
        parts.append(f"'{k}' 는 이 액션의 문서화된 파라미터가 아니고 용례에도 없습니다 — "
                     f"'{v}' 를 의도했나요? (핸들러가 읽지 않는 키는 조용히 무시됩니다.)")
    if vocab:
        parts.append(f"이 액션의 주요 키: {sorted(vocab)}.")
    return {"unknown": unknown, "suggest": suggest, "soft": soft,
            "message": " ".join(parts)}


# === 코퍼스 관용 사전 (soft 층의 오탐 방지 장치) ===

_corpus_keys_cache: Dict[str, tuple] = {}  # "node:action" -> (computed_at, keys|None)
_CORPUS_KEYS_TTL = 600


def _corpus_action_keys(node: str, action: str) -> Optional[Set[str]]:
    """해마 코퍼스에서 이 액션의 실사용 파라미터 키 집합. 실패 시 None(=soft 층 스킵 — 안전측)."""
    qualified = f"{node}:{action}"
    hit = _corpus_keys_cache.get(qualified)
    now = time.time()
    if hit and now - hit[0] < _CORPUS_KEYS_TTL:
        return hit[1]
    keys: Optional[Set[str]] = None
    try:
        import sqlite3
        from runtime_utils import get_base_path
        db_path = Path(get_base_path()) / "data" / "ibl_usage.db"
        if db_path.is_file():
            conn = sqlite3.connect(str(db_path))
            try:
                rows = conn.execute(
                    "SELECT ibl_code FROM ibl_examples WHERE ibl_code LIKE ? LIMIT 400",
                    (f"%[{qualified}]%",)).fetchall()
            finally:
                conn.close()
            from ibl_parser import parse as _parse
            found: Set[str] = set()

            def _walk(o):
                if isinstance(o, dict):
                    if o.get("_node") == node and o.get("action") == action:
                        for k in (o.get("params") or {}):
                            if isinstance(k, str):
                                found.add(k)
                    for v in o.values():
                        _walk(v)
                elif isinstance(o, list):
                    for v in o:
                        _walk(v)

            for (code,) in rows:
                try:
                    _walk(_parse(code))
                except Exception:
                    continue
            keys = found
    except Exception:
        keys = None
    _corpus_keys_cache[qualified] = (now, keys)
    return keys


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
