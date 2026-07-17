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
from typing import Any, Dict, List, Union


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
        if k and k.lower() not in seen:
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
# 실행 에이전트 자기반성 메시지 (끝내기 전, '너 자신의 점검')
# ============================================================
# ★판정이 아니다: 별도 경량 평가자가 위에서 도장 찍는 게 아니라, 실행 에이전트 *자신*이
# 같은 세션(resume)을 이어받아 자기 궤적을 입력으로 받고 스스로 반성·재행동한다. 무엇을
# 할지는 에이전트가 정한다(도구를 다시 써서 재시도하거나, 응답을 정직하게 고치거나, 충분하면
# 마치거나). 궤적을 명시적으로 얹는 이유 = '앞으로 나아가는' 흐름을 '뒤돌아보는' 검사 대상으로
# 바꾸는 병치 효과(에피소드 727/728: 도구 실패를 세계 사실로 오해).
_REFLECTION_MSG_CACHE = {"text": ""}


def build_reflection_message(response: str, tool_calls: list) -> str:
    """실행 에이전트 자기반성 턴에 넣을 메시지를 만든다.

    구성 = [자기점검 지시(파일)] + [지금까지의 궤적(도구 호출·결과 병치)] + [초안 응답].
    같은 세션 resume이라 문맥은 이미 있지만, 궤적을 명시적으로 입력해 회고 자세를 촉발한다.
    """
    trace = serialize_tool_trace(tool_calls) if tool_calls else ""
    if not _REFLECTION_MSG_CACHE["text"]:
        p = Path(__file__).parent.parent / "data" / "common_prompts" / "execution_reflection_prompt.md"
        try:
            _REFLECTION_MSG_CACHE["text"] = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            _REFLECTION_MSG_CACHE["text"] = (
                "일 마치기 전, 네가 밟은 궤적을 스스로 돌아보라. 도구가 빈 껍데기·깨진 데이터·"
                "'없음'을 줬는데 그걸 세계의 사실로 오해하지 않았나? 하위 목표마다 실제로 됐나? "
                "다시 시도할 게 있으면 지금 도구를 써서 하고, 응답이 실패를 얼버무렸으면 정직하게 "
                "고쳐라. 이미 충분하면 그대로 마쳐라. 무엇을 할지는 네가 정한다."
            )
    parts = [_REFLECTION_MSG_CACHE["text"]]
    if trace:
        parts.append(f"## 지금까지의 궤적 (네가 부른 도구와 그 결과)\n{trace}")
    parts.append(f"## 네가 내놓으려던 응답\n{(response or '')[:8000]}")
    return "\n\n".join(parts)
