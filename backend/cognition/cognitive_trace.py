"""
cognitive_trace.py - 도구 호출 trace 직렬화 + 자기반성 메시지
IndieBiz OS Core

agent_cognitive.py 에서 분리(2026-07-17, 1500줄 규칙 모듈화). 평가자 입력용
도구 호출 시퀀스 직렬화(serialize_tool_trace)·검증용 액션 원장(build_action_ledger)·
실행 에이전트 자기반성 메시지(build_reflection_message)와 그 헬퍼들.
전부 모듈 레벨 순수 함수라 mixin 과 독립 — 기존 import 경로(agent_cognitive)는
재수출로 유지된다.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union


# ============================================================
# 도구 호출 trace 직렬화 (평가자 입력용)
# ============================================================

# 파일 경로 인풋 키 — Write/Edit/MultiEdit 류와 IBL self:write 등에서 파일 경로를 담는 흔한 키들.
# tool_calls에서 input을 스캔할 때 이 키 중 하나가 있으면 생성/수정된 파일 후보로 본다.
_FILE_PATH_INPUT_KEYS = ("file_path", "path", "filepath", "target", "output", "output_path", "filename")
# 파일 변경(생성/수정) 의미를 갖는 도구 이름 — 정규화된 이름 기준.
_FILE_WRITE_TOOL_NAMES = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _brief_input(tool_input: Any, max_len: int = 160) -> str:
    """tool input dict를 한 줄로 요약. 키=값 일부만 보여서 시퀀스 트레이스를 짧게 유지."""
    if not isinstance(tool_input, dict) or not tool_input:
        if tool_input in (None, "", {}):
            return ""
        s = str(tool_input)
        return s if len(s) <= max_len else s[:max_len] + "…"
    parts = []
    # 우선 순위: 식별성 높은 키 먼저 (execute_ibl/IBL/Write/Edit/Bash 등의 핵심 인자)
    priority_keys = (
        "node", "action", "op", "command", "query", "name",
        "file_path", "path", "filepath", "output_path",
        "subagent_type", "url", "id",
    )
    seen = set()
    for k in priority_keys:
        if k in tool_input and k not in seen:
            v = tool_input[k]
            sv = str(v) if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)
            if len(sv) > 60:
                sv = sv[:60] + "…"
            parts.append(f"{k}={sv}")
            seen.add(k)
    # 남은 키는 이름만 (값 너무 클 수 있음)
    remaining = [k for k in tool_input.keys() if k not in seen]
    if remaining:
        parts.append("+" + ",".join(remaining[:5]))
    joined = " ".join(parts)
    return joined if len(joined) <= max_len else joined[:max_len] + "…"


def _normalize_tool_entry(entry: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """문자열(legacy) 또는 dict(신규 구조)를 표준 dict로 변환."""
    if isinstance(entry, dict):
        return {
            "name": entry.get("name") or entry.get("tool_name") or "",
            "input": entry.get("input") or {},
            "result": entry.get("result", ""),
            "is_error": bool(entry.get("is_error", False)),
        }
    # 문자열 — name·input 불명, 결과만 보존 (backward-compat)
    return {"name": "", "input": {}, "result": str(entry), "is_error": False}


def _merge_keywords(existing: str, new: str) -> str:
    """두 키워드 문자열을 합집합으로 병합 (순서 보존, 중복 제거).

    심층메모리 UPDATE/REPLACE 시 키워드가 무한 누적되지 않도록."""
    seen, out = set(), []
    for kw in (existing or "").split(",") + (new or "").split(","):
        k = kw.strip()
        if k and k.lower() not in seen:  # vj-ok: 내부 트레이스 키 dedup
            seen.add(k.lower())
            out.append(k)
    return ",".join(out)


def _unwrap_payload(obj: Any, depth: int = 0) -> Any:
    """IBL 결과 envelope({"success":..,"results":[..]})을 재귀적으로 벗겨 페이로드만 남긴다.

    병렬 실행 결과는 results[].result 안에 branch별 JSON이 문자열로 재포장돼
    있어 한 겹으로는 안 벗겨진다 — 문자열이 JSON이면 파싱해 계속 내려간다."""
    if depth > 6:
        return obj
    if isinstance(obj, str):
        s = obj.strip()
        if s[:1] in "[{":
            try:
                return _unwrap_payload(json.loads(s), depth + 1)
            except Exception:
                return obj
        return obj
    if isinstance(obj, dict):
        # 봉투 다이어트(2026-08-22 M1) 뒤엔 results[] 가 요약이라 증거는 final_result 에만 있다.
        if obj.get("_results_summarized") and obj.get("final_result"):
            return _unwrap_payload(obj["final_result"], depth + 1)
        for k in ("results", "result"):
            if obj.get(k):
                return _unwrap_payload(obj[k], depth + 1)
        return obj
    if isinstance(obj, list):
        return [_unwrap_payload(x, depth + 1) for x in obj]
    return obj


def _result_evidence(result: Any) -> str:
    """평가자에게 보여줄 결과 발췌의 원문 — envelope 대신 실제 내용(검색 결과 등).

    발췌가 `{"success": true, "steps_completed"...}` 포장에서 끝나면 평가자가
    증거 없이 자기 파라미터 지식으로 사실성을 판정하는 사고가 난다
    (2026-07-03 fable5 오판: 실제 검색 증거를 못 보고 실존 모델을 허구로 판정)."""
    if not isinstance(result, str):
        result = str(result)
    try:
        unwrapped = _unwrap_payload(result)
    except Exception:
        return result
    if isinstance(unwrapped, str):
        return unwrapped
    try:
        return json.dumps(unwrapped, ensure_ascii=False)
    except Exception:
        return result


def serialize_tool_trace(
    items: List[Union[str, Dict[str, Any]]],
    total_budget: int = 8000,
    head_keep: int = 8,
    tail_keep: int = 8,
    per_result_chars: int = 1600,
) -> str:
    """도구 호출 시퀀스를 평가자가 읽을 수 있는 한 문자열로 직렬화.

    핵심 원칙: **호출 이름·순서는 어떤 경우에도 보존**한다. 결과 본문만 잘라낸다.
    호출 수가 많아 total_budget을 넘으면, 앞 head_keep + 뒤 tail_keep 개 호출만 상세히 보여주고
    가운데는 "[헤더만 — 결과 생략]" 모드로 압축하여 시퀀스 자체는 끝까지 노출한다.

    Args:
        items: dict(`{name,input,result,is_error}`) 또는 str(legacy) 리스트
        total_budget: 직렬화 결과 전체 길이 한계 (대략치)
        head_keep: 앞쪽에서 결과까지 상세히 보여줄 호출 수
        tail_keep: 뒤쪽에서 결과까지 상세히 보여줄 호출 수
        per_result_chars: 호출당 결과 본문 최대 길이

    Returns:
        직렬화된 트레이스 문자열 (items 비어있으면 "").
    """
    if not items:
        return ""

    normalized = [_normalize_tool_entry(it) for it in items if it is not None]
    if not normalized:
        return ""

    total = len(normalized)
    # 모든 호출의 헤더(이름+input brief)는 무조건 살린다.
    # detail 마스크: True면 결과까지 노출, False면 헤더만.
    if total <= head_keep + tail_keep:
        detail_mask = [True] * total
    else:
        detail_mask = (
            [True] * head_keep
            + [False] * (total - head_keep - tail_keep)
            + [True] * tail_keep
        )

    lines: List[str] = [f"# 도구 호출 시퀀스 (총 {total}회)"]
    omitted_run = 0
    for idx, (entry, detailed) in enumerate(zip(normalized, detail_mask), start=1):
        name = entry["name"] or "(이름미상)"
        brief = _brief_input(entry["input"])
        err_tag = " [ERROR]" if entry["is_error"] else ""
        header = f"[{idx}] {name}({brief}){err_tag}" if brief else f"[{idx}] {name}{err_tag}"

        if detailed:
            if omitted_run > 0:
                lines.append(f"  … (호출 {omitted_run}개 — 헤더는 위에서 이어짐, 결과 생략) …")
                omitted_run = 0
            result = _result_evidence(entry["result"]) if entry["result"] else ""
            if isinstance(result, str) and result:
                excerpt = result.strip().replace("\n", " ")
                if len(excerpt) > per_result_chars:
                    excerpt = excerpt[:per_result_chars] + "…"
                lines.append(f"{header}\n    → {excerpt}")
            else:
                lines.append(header)
        else:
            # 헤더만 — 시퀀스 손실 방지가 목적
            lines.append(header)
            omitted_run += 1

    if omitted_run > 0:
        lines.append(f"  … (위 {omitted_run}개 호출은 결과 본문 생략됨) …")

    serialized = "\n".join(lines)

    # 안전망: 그래도 budget을 넘으면 결과 라인부터 추가 truncate.
    # 호출 헤더(`[N] name(...)` 줄)는 살리고, 결과 줄(`    → ...`)을 우선적으로 자른다.
    if len(serialized) > total_budget:
        kept: List[str] = []
        budget = total_budget
        for line in lines:
            if budget <= 0:
                # 결과 줄이면 스킵, 헤더 줄이면 짧게라도 포함.
                # 상세 항목은 "헤더\n    → 결과" 결합 문자열이라 헤더만 잘라 살린다
                # (안 하면 budget 소진 후에도 결과 본문이 통째로 통과).
                if line.startswith("    → ") or line.startswith("  … "):
                    continue
                kept.append(line.split("\n", 1)[0])
                continue
            kept.append(line)
            budget -= len(line) + 1
        kept.append(f"  (총 길이 budget {total_budget}자 초과 — 일부 결과 본문 생략됨)")
        serialized = "\n".join(kept)

    return serialized


# 검증용 액션 원장 — execute_ibl의 code에서 [node:action]을 추출해 '실제 실행된 액션 전수'를
# 정규화 리스트로 만든다. serialize_tool_trace는 모든 execute_ibl을 'execute_ibl(+code)'로만
# 보여줘(브리프에 code 미노출) 평가자가 어떤 IBL 액션이 실제 호출됐는지 — 예: 특정 파일을
# 읽었는지, grep을 돌렸는지 — 를 볼 수 없었다. 이 원장은 그 '부재'를 검증 가능하게 노출한다.
_IBL_ACTION_RE = re.compile(r'\[([a-z_]+):([a-z_]+)\]')
_IBL_TARGET_RE = re.compile(
    r'(?:path|file_path|image_path|source|destination|url|site_id|workflow_id|query|pattern)'
    r'\s*:\s*"([^"]+)"'
)


def build_action_ledger(items: List[Union[str, Dict[str, Any]]]) -> str:
    """실제 호출된 액션을 검증용으로 정규화한 원장 문자열.

    execute_ibl 호출은 input.code에서 모든 `[node:action]`과 대상(path/url/query 등)을 추출한다.
    비-IBL 도구(Bash 등)는 이름 + 핵심 인자로 집계한다. 액션별 호출 횟수와 distinct 대상을 모은다.
    legacy str 항목(이름·input 없음)은 원장에 기여하지 못하므로 건너뛴다 (그 경우 빈 문자열 반환).
    """
    if not items:
        return ""
    from collections import OrderedDict
    ledger: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    def _slot(key: str) -> Dict[str, Any]:
        return ledger.setdefault(key, {"count": 0, "targets": []})

    def _add_target(slot: Dict[str, Any], t: str):
        if isinstance(t, str) and t:
            tv = t if len(t) <= 90 else "…" + t[-89:]
            if tv not in slot["targets"]:
                slot["targets"].append(tv)

    had_structured = False
    for it in items:
        ent = _normalize_tool_entry(it)
        name = ent["name"]
        if not name:
            continue  # legacy str — 이름 없음, 원장 기여 불가
        had_structured = True
        inp = ent["input"] if isinstance(ent["input"], dict) else {}
        code = inp.get("code")
        if "execute_ibl" in name and isinstance(code, str):
            acts = _IBL_ACTION_RE.findall(code)
            targets = _IBL_TARGET_RE.findall(code)
            if not acts:
                _slot("execute_ibl(파싱불가)")["count"] += 1
                continue
            for node, action in acts:
                slot = _slot(f"{node}:{action}")
                slot["count"] += 1
                for t in targets:
                    _add_target(slot, t)
        else:
            slot = _slot(name)
            slot["count"] += 1
            for tk in ("file_path", "path", "command", "url", "query"):
                v = inp.get(tk)
                if isinstance(v, str) and v:
                    _add_target(slot, v)
                    break

    if not had_structured:
        return ""

    lines: List[str] = []
    for key, slot in ledger.items():
        tgt = ""
        if slot["targets"]:
            shown = slot["targets"][:8]
            tgt = "  → " + " | ".join(shown)
            extra = len(slot["targets"]) - len(shown)
            if extra > 0:
                tgt += f" (외 {extra}개)"
        lines.append(f"- {key} (×{slot['count']}){tgt}")
    return "\n".join(lines)


# ============================================================
# 자기반성 게이트 — 반성이 값을 낼 궤적만 반성한다 (2026-07-21)
# ============================================================
# 에피소드 806~808 실측: 성공한 단건 조회(도구 1회)에도 반성 턴이 무조건 돌아
# 본 실행 대비 +45~58% 오버헤드. 반성의 존재 이유는 (a) 도구 실패를 세계 사실로
# 오해하는 것(에피소드 727/728), (b) 긴 궤적의 표류, (c) 세계를 바꾼 일의 검증이다.
# 셋 다 없는 궤적(짧고·성공했고·읽기만)은 반성이 응답 재작성 비용만 낸다 → 스킵.

# 도구 호출 자체는 성공(is_error=False)이지만 *내용*이 실패인 부류 — execute_ibl 은
# IBL 실패를 성공한 도구 결과 안에 success:false 로 담아 온다.
_RESULT_FAILURE_RE = re.compile(
    r'"success"\s*:\s*false|\'success\'\s*:\s*False|_param_hint'
    r'|["\']error["\']\s*:|timed out|Traceback \(most recent call\)|Exit code [1-9]',
    re.IGNORECASE)
_IBL_ACTION_RE = re.compile(r'\[(\w+):(\w+)\]')
_SAFETY_MAP_CACHE: dict = {}
# 빈 tool_result 가 정상인 도구 — ToolSearch 는 스키마를 별도 <functions> 블록으로 싣고
# 본문은 비워 돌려준다. 이걸 "빈 껍데기"로 오인해 반성 턴을 돌리면 매번 20~40초 낭비.
_EMPTY_RESULT_OK = {"ToolSearch"}


def _ibl_safety_map() -> dict:
    """{(node, action): safe} — ibl_safety(returns: 파생, side_effect 오버라이드)에서 렌트."""
    if not _SAFETY_MAP_CACHE:
        try:
            from ibl_safety import load_safety_map
            _SAFETY_MAP_CACHE.update(load_safety_map())
        except Exception:
            pass
    return _SAFETY_MAP_CACHE


_OP_SAFETY_MAP_CACHE: dict = {}


def _ibl_op_safety_map() -> dict:
    """{(node, action, op): safe} — op 축(2026-08-05). 액션 롤업만 보면 `[self:memory]{op:"recall"}` 같은 읽기 op 가
    쓰기 액션 안에 갇혀 반성 턴을 헛돌린다(2026-09-05 실측: 2주 usage 494건에서 '부작용 액션' 사유 58회 중
    memory·script·forage·body·notebook 의 읽기 op 가 다수, 반성 라운드 중앙값 46초). 조종실 검수기와 같은 단일 소스."""
    if not _OP_SAFETY_MAP_CACHE:
        try:
            from ibl_safety import load_op_safety_map
            _OP_SAFETY_MAP_CACHE.update(load_op_safety_map())
        except Exception:
            pass
    return _OP_SAFETY_MAP_CACHE


def _ibl_steps(code: str):
    """코드 → [(node, action, params)] 전수(병렬·폴백·블록 안까지). 파싱 실패면 None(호출자가 정규식 폴백)."""
    try:
        from ibl_parser import parse
        steps = parse(code)
    except Exception:
        return None
    out = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("_node") and o.get("action"):
                out.append((str(o["_node"]), str(o["action"]), o.get("params") if isinstance(o.get("params"), dict) else {}))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(steps)
    return out


def _action_safe(node: str, action: str, params: dict, safety: dict, op_safety: dict) -> bool:
    """이 호출이 읽기인가 — **op 축 우선**: 실제 실행될 op 가 op 안전지도에 있으면 그 판정, 없으면 액션 롤업(미등록=쓰기 취급)."""
    if op_safety:
        op = None
        try:
            from ibl_access import load_nodes_raw
            from ibl_ops import resolve_op
            ad = ((load_nodes_raw() or {}).get("nodes", {}).get(node, {}).get("actions", {}).get(action)) or {}
            op = resolve_op(ad, params or {})
        except Exception:
            op = None
        if op is not None and (node, action, op) in op_safety:
            return bool(op_safety[(node, action, op)])
    return bool(safety.get((node, action), False))


# 셸(run_command) 읽기 전용 인식 — 보수적 화이트리스트. 여기 없는 동사·리다이렉트·-i·-delete·xargs 는
# "분류 불가"(읽기가 아님)로 두어 복잡도 규칙이 잡게 한다. 누락의 방향은 항상 "반성 한 번 더"(안전).
_SHELL_READ_VERBS = {
    "ls", "cat", "head", "tail", "grep", "egrep", "fgrep", "rg", "find", "wc", "awk", "echo", "printf",
    "pwd", "which", "stat", "file", "du", "df", "ps", "whoami", "date", "uname", "sort", "uniq", "cut",
    "tr", "jq", "tree", "true", "cd", "type", "env", "printenv", "basename", "dirname", "realpath",
    "md5", "shasum", "diff", "cmp", "column", "nl", "od", "xxd", "strings", "sqlite3",
}
_GIT_READ_SUBCMDS = {"status", "log", "diff", "show", "branch", "rev-parse", "ls-files", "remote",
                     "describe", "blame", "shortlog", "tag", "config", "reflog", "cat-file", "grep",
                     "rev-list", "name-rev", "check-ignore", "count-objects", "ls-tree", "whatchanged"}
_SHELL_SPLIT_RE = re.compile(r'\|\||&&|;|\|')
_SHELL_NOT_READ_RE = re.compile(r'(^|[^>])>(?!&2)|\bxargs\b|\s-i\b|\s-delete\b|\s-exec\b|\s-ok\b|`|\$\(')


def shell_command_is_read_only(command: str) -> bool:
    """셸 명령이 *알려진 읽기 동사만으로* 이뤄졌는가. 불확실하면 False(분류 불가).

    파이프 각 단계·&&/;/|| 각 구간의 첫 동사(환경변수 대입 건너뜀)가 읽기 동사여야 한다.
    git 은 읽기 하위명령만. 리다이렉트(>)·xargs·sed/find 의 -i/-delete/-exec·명령 치환은 False.
    sqlite3 는 SELECT/.schema/.tables 류만 읽기 — 안에 insert/update/delete/drop/create 가 있으면 False."""
    cmd = (command or "").strip()
    if not cmd:
        return False
    if _SHELL_NOT_READ_RE.search(cmd):
        return False
    for seg in _SHELL_SPLIT_RE.split(cmd):
        toks = seg.strip().split()
        while toks and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', toks[0]):
            toks = toks[1:]
        if not toks:
            return False
        verb = toks[0].rsplit("/", 1)[-1]
        if verb == "git":
            sub = next((t for t in toks[1:] if not t.startswith("-")), "")
            if sub not in _GIT_READ_SUBCMDS:
                return False
            continue
        if verb == "sed":
            if "-n" not in toks[1:]:
                return False
            continue
        if verb == "sqlite3":
            low = seg.lower()
            if re.search(r'\b(insert|update|delete|drop|create|alter|replace|vacuum|pragma\s+\w+\s*=)\b', low):
                return False
            continue
        if verb not in _SHELL_READ_VERBS:
            return False
    return True


def _classify_call(tc: dict, safety: dict, op_safety: dict = None):
    """도구 호출 1건 → ("read"|"write"|"unknown", 사유). 실패 판정은 호출자가 먼저 한다.
    IBL 은 op 축으로 판정한다(2026-09-05) — 파싱해 (node, action, params) 를 얻고 실제 op 의 안전을 본다; 파싱 못 하는
    코드는 정규식으로 액션만 뽑아 액션 롤업(보수)으로 떨어진다."""
    if op_safety is None:
        op_safety = _ibl_op_safety_map()
    name = str(tc.get("name", ""))
    base_name = name.rsplit("__", 1)[-1]  # mcp__indiebizos__execute_ibl → execute_ibl
    inp = tc.get("input") if isinstance(tc.get("input"), dict) else {}
    if base_name in _FILE_WRITE_TOOL_NAMES:
        return "write", f"파일 변경 ({base_name})"
    if base_name == "execute_ibl":
        code = str(inp.get("code", ""))
        actions = _IBL_ACTION_RE.findall(code)
        if not actions:
            return "unknown", f"IBL 액션 없음 ({name})"
        steps = _ibl_steps(code)
        judged = set()
        for node, action, params in (steps or []):
            judged.add((node, action))
            if not _action_safe(node, action, params, safety, op_safety):
                op = (params or {}).get("op")
                return "write", f"부작용 액션 ([{node}:{action}]" + (f'{{op: "{op}"}}' if isinstance(op, str) else "") + ")"
        for node, action in actions:
            if (node, action) in judged:
                continue
            # 파서가 못 편 자리(do 문자열 안 등)는 액션 롤업 — 안전지도에 없거나 safe=False → 부작용 취급 (보수적)
            if not safety.get((node, action), False):
                return "write", f"부작용 액션 ([{node}:{action}])"
        return "read", ""
    if base_name == "run_command":
        cmd = str(inp.get("command", ""))
        if shell_command_is_read_only(cmd):
            return "read", ""
        return "unknown", f"셸 분류 불가 ({cmd[:40]!r})"
    if base_name in _READ_ONLY_TOOL_NAMES:
        return "read", ""
    return "unknown", f"미분류 도구 ({base_name})"


# 읽기만 하는 하네스 도구(파일·검색·스키마 로더) — 궤적 분류용.
_READ_ONLY_TOOL_NAMES = {"Read", "Grep", "Glob", "LS", "ToolSearch", "WebSearch", "WebFetch",
                         "read_file", "search_files", "list_directory", "get_current_time"}


def should_self_reflect(tool_calls: list, min_tool_calls: int = 3) -> Tuple[bool, str]:
    """자기반성 턴을 돌릴 가치가 있는 궤적인가 → (돌릴지, 사유).

    반성 조건(하나라도): ①실패 신호(is_error·결과 내 실패 마커·빈 결과)
    ②세계 변경(파일 쓰기 도구, 또는 IBL 부작용 액션 — ibl_safety 안전지도 파생, 미등록=보수적 변경 취급)
    ③궤적 복잡도(호출 수 ≥ min_tool_calls) — 단, **읽기만 한 궤적은 제외**(2026-09-02 사용자 판정):
      모든 호출이 읽기(안전지도 safe 액션·읽기 셸 동사·읽기 도구)로 분류되고 실패가 없으면 길어도 스킵.
      분류 불가 호출(미지 셸 동사·미분류 도구)이 섞인 긴 궤적만 복잡도로 잡는다.
    실측 근거: git 상태 확인 턴이 읽기 9회로 반성 5라운드(+60s)를 더 돌았다 — 반성이 값을 내는
    (a) 실패 오해 (b) 표류 (c) 세계 변경 검증 중 어느 것도 읽기 궤적엔 없다.
    """
    n = len(tool_calls or [])
    safety = _ibl_safety_map()
    op_safety = _ibl_op_safety_map()
    unknown = []
    for tc in (tool_calls or []):
        if not isinstance(tc, dict):
            continue
        name = str(tc.get("name", ""))
        base_name = name.rsplit("__", 1)[-1]
        result = tc.get("result", "")
        if tc.get("is_error"):
            return True, f"도구 오류 ({name})"
        # ToolSearch(스키마 로더)는 tool_result 본문이 비어 보이는 게 정상 동작이다
        # (도구 정의는 별도 블록으로 실림) — 빈-결과 트리거에서 제외 (에피소드 855·857 오발동).
        if not str(result).strip() and base_name not in _EMPTY_RESULT_OK:
            return True, f"빈 결과 ({name}) — 빈 껍데기 오해 위험"
        if _RESULT_FAILURE_RE.search(str(result)):
            return True, f"결과 내 실패 신호 ({name})"
        kind, why = _classify_call(tc, safety, op_safety)
        if kind == "write":
            return True, why
        if kind == "unknown":
            unknown.append(why)

    if unknown and n >= min_tool_calls:
        return True, f"궤적 복잡도 (도구 {n}회 ≥ {min_tool_calls}, 분류 불가 {len(unknown)}회: {unknown[0]})"
    if not unknown:
        return False, f"읽기만 한 궤적 (도구 {n}회, 실패·변경 없음)"
    return False, f"짧고 성공한 궤적 (도구 {n}회, 분류 불가 {len(unknown)}회 < 복잡도 하한)"


# ============================================================
# 실행 에이전트 자기반성 메시지 (끝내기 전, '너 자신의 점검')
# ============================================================
# ★판정이 아니다: 별도 경량 평가자가 위에서 도장 찍는 게 아니라, 실행 에이전트 *자신*이
# 같은 세션(resume)을 이어받아 자기 궤적을 입력으로 받고 스스로 반성·재행동한다. 무엇을
# 할지는 에이전트가 정한다(도구를 다시 써서 재시도하거나, 응답을 정직하게 고치거나, 충분하면
# 마치거나). 궤적을 명시적으로 얹는 이유 = '앞으로 나아가는' 흐름을 '뒤돌아보는' 검사 대상으로
# 바꾸는 병치 효과(에피소드 727/728: 도구 실패를 세계 사실로 오해).
_REFLECTION_MSG_CACHE = {"text": ""}


_IBL_HEAD_RE = re.compile(r"\[([a-z_]+):")


def ibl_call_cost(tool_calls: list) -> Dict[str, int]:
    """이번 주행의 IBL 호출 경제 — 손에 있는 tool_calls 만으로 센다(궤적 DB 를 다시 읽지 않는다).

    두 궤적 모양을 다 받는다: 평가/반성용 `{name, input, result, is_error}` 와 증류용
    `{tool_name, input, success}`. 액션 수는 code 의 대괄호 머리 수(`[node:` 계수)다.
    반환: calls(execute_ibl 호출 수)·single(액션 1개 호출)·failed·typed_chars(code 자수 합).
    """
    calls = single = failed = typed = 0
    retyped = retyped_warns = pointed = fn_calls = 0
    other_calls = other_typed = 0          # IBL 밖 도구(셸 등) — 우회 통로도 모델이 친 글자다(2026-09-06 반성 4)
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name = tc.get("tool_name") or tc.get("name") or ""
        if name != "execute_ibl":
            other_calls += 1
            _oi = tc.get("input")
            if isinstance(_oi, dict):
                other_typed += sum(len(v) for v in _oi.values() if isinstance(v, str))
            continue
        inp = tc.get("input")
        code = inp.get("code", "") if isinstance(inp, dict) else ""
        code = code if isinstance(code, str) else str(code or "")
        calls += 1
        typed += len(code)
        if isinstance(inp, dict):
            for _f in (inp.get("files") or []):          # files 첨부도 모델이 친 글자다
                typed += len(_f) if isinstance(_f, str) else 0
        if len(_IBL_HEAD_RE.findall(code)) <= 1:
            single += 1
        fn_calls += code.count("[fn:")
        ok = tc.get("success") if "success" in tc else (not tc.get("is_error", False))
        if ok is False:
            failed += 1
        # 되받아쓰기·가리킴(2026-09-06 [출력해부]) — 궤적 항목의 수치 메타 또는 결과 봉투에서
        _rc, _pt = tc.get("retyped_chars"), tc.get("pointed")
        if _rc is None or _pt is None:
            _res = tc.get("result")
            if isinstance(_res, str) and ('"retyped"' in _res or '"turn_vars"' in _res):
                try:
                    _o = json.loads(_res)
                    if _rc is None:
                        _rc = ((_o.get("retyped") or {}).get("verbatim_chars")) or 0
                    if _pt is None:
                        _pt = len(((_o.get("turn_vars") or {}).get("injected")) or [])
                except Exception:
                    pass
        if _rc:
            retyped += int(_rc)
            retyped_warns += 1
        pointed += int(_pt or 0)
    return {"calls": calls, "single": single, "failed": failed, "typed_chars": typed,
            "retyped_chars": retyped, "retyped_warns": retyped_warns, "pointed": pointed, "fn_calls": fn_calls,
            "other_calls": other_calls, "other_typed_chars": other_typed}


def _fmt_chars(n: int) -> str:
    n = int(n or 0)
    if n < 1000:
        return f"{n}자"
    return f"{n / 1000:.1f}K자" if n < 10000 else f"{round(n / 1000)}K자"


def run_cost_line(tool_calls: list) -> str:
    """`이번 주행: execute_ibl k회(액션 1개 호출 j회) · 실패 m · 타이핑 NK자` — 수치만, 질문 없음
    (반성 출력 계약은 사용자 답만 허용). IBL 호출이 없으면 빈 문자열."""
    c = ibl_call_cost(tool_calls)
    if not c["calls"] and not c["other_typed_chars"]:     # IBL 도 없고 밖 도구가 친 글자도 없으면 줄 없음
        return ""
    line = (f"이번 주행: execute_ibl {c['calls']}회(액션 1개 호출 {c['single']}회) · 실패 {c['failed']} · "
            f"타이핑 {_fmt_chars(c['typed_chars'])} · 되받아쓰기 {_fmt_chars(c['retyped_chars'])}"
            f"({c['retyped_warns']}회 경고) · 가리킴 {c['pointed']}회 · [fn:] {c['fn_calls']}회")
    if c["other_calls"]:
        line += f" · IBL 밖 도구 {c['other_calls']}회 {_fmt_chars(c['other_typed_chars'])}"
    return line


def build_reflection_message(response: str, tool_calls: list) -> str:
    """실행 에이전트 자기반성 턴에 넣을 메시지를 만든다.

    구성 = [자기점검 지시(파일)] + [이번 주행 비용 한 줄] + [지금까지의 궤적(도구 호출·결과 병치)] + [초안 응답].
    같은 세션 resume이라 문맥은 이미 있지만, 궤적을 명시적으로 입력해 회고 자세를 촉발한다.
    비용 한 줄(2026-09-05): 호출 수·액션 1개 호출·실패·타이핑 자수 — 적합도가 모델의 눈에 있어야
    다음 프로그램이 줄어든다. 수치만 두고 질문은 덧붙이지 않는다(출력 계약).
    """
    trace = serialize_tool_trace(tool_calls) if tool_calls else ""
    cost = run_cost_line(tool_calls) if tool_calls else ""
    if not _REFLECTION_MSG_CACHE["text"]:
        p = Path(__file__).parent.parent.parent / "data" / "common_prompts" / "execution_reflection_prompt.md"
        try:
            _REFLECTION_MSG_CACHE["text"] = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            _REFLECTION_MSG_CACHE["text"] = (
                "일 마치기 전, 네가 밟은 궤적을 스스로 돌아보라. 도구가 빈 껍데기·깨진 데이터·"
                "'없음'을 줬는데 그걸 세계의 사실로 오해하지 않았나? 하위 목표마다 실제로 됐나? "
                "★출력 계약: 이 턴의 출력이 초안을 대체해 사용자에게 그대로 전송된다 — 반성 "
                "과정·점검 보고를 출력하지 마라. 수정할 게 있으면 완결된 최종 응답 전체를 내고, "
                "수정할 게 없으면 첫 줄에 정확히 NO_REVISION 이라고만 써라(초안이 그대로 나간다)."
            )
    parts = [_REFLECTION_MSG_CACHE["text"]]
    if cost:
        parts.append(cost)
    if trace:
        parts.append(f"## 지금까지의 궤적 (네가 부른 도구와 그 결과)\n{trace}")
    parts.append(f"## 네가 내놓으려던 응답\n{(response or '')[:8000]}")
    return "\n\n".join(parts)
