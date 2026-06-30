"""
agent_cognitive.py - 인지/AI 초기화 믹스인
IndieBiz OS Core

AgentRunner의 인지 관련 메서드를 분리한 Mixin 클래스.
무의식/의식/평가 에이전트 파이프라인, IBL 도구 구성, 실행기억 등
AI 인지 아키텍처에 해당하는 로직을 포함한다.
"""

import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from ai_agent import AIAgent


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


def serialize_tool_trace(
    items: List[Union[str, Dict[str, Any]]],
    total_budget: int = 8000,
    head_keep: int = 8,
    tail_keep: int = 8,
    per_result_chars: int = 220,
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
            result = entry["result"] or ""
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
                # 결과 줄이면 스킵, 헤더 줄이면 짧게라도 포함
                if line.startswith("    → ") or line.startswith("  … "):
                    continue
                kept.append(line)
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
# SESSION_RESET 핸들러 (모듈 레벨 — call site에서 직접 호출)
# ============================================================

SESSION_RESET_RESPONSE = "새 세션을 시작했습니다. 무엇을 도와드릴까요?"


# ============================================================
# 의식 framing 캐시 (연속 turn 재사용)
# ------------------------------------------------------------
# THINK 판정 = "framing이 필요하다"는 수요 선언이다. 같은 대화 맥락에서 이미
# 의식 에이전트가 만든 framing이 지금 질문에 맞으면, 그걸 재사용해 비싼 의식
# (Opus) 호출을 건너뛴다. 없거나 안 맞으면 의식 에이전트가 새로 만든다.
#   키: registry_key (project_id:agent_id)
#   값: {"output": dict, "ts": epoch_seconds}
# ============================================================

_FRAMING_CACHE: Dict[str, Dict[str, Any]] = {}
_FRAMING_TTL_SEC = 1800  # 30분 — 오래된 동선이 새 대화로 새지 않도록 만료


def framing_cache_get(key: str) -> Optional[dict]:
    """저장된 framing 조회 (TTL 경과 시 폐기하고 None)."""
    import time as _t
    entry = _FRAMING_CACHE.get(key)
    if not entry:
        return None
    if _t.time() - entry.get("ts", 0) > _FRAMING_TTL_SEC:
        _FRAMING_CACHE.pop(key, None)
        return None
    return entry.get("output")


def framing_cache_set(key: str, output: dict):
    """framing 저장 (빈 값·미완성 framing은 호출 측에서 걸러 보낼 것)."""
    import time as _t
    if key and output:
        _FRAMING_CACHE[key] = {"output": output, "ts": _t.time()}


def clear_framing_cache(key: str = None):
    """framing 캐시 무효화. key 없으면 전체."""
    if key:
        _FRAMING_CACHE.pop(key, None)
    else:
        _FRAMING_CACHE.clear()


def handle_session_reset() -> str:
    """SESSION_RESET 분류 후 호출.

    현재 thread_context의 agent에 해당하는 Claude Code 세션 매핑을 제거하여
    다음 호출이 fresh Claude Code 세션으로 시작되도록 한다.
    Claude Code provider가 아닌 경우 no-op (안전).

    Returns:
        사용자에게 보여줄 표준 응답 텍스트
    """
    try:
        from providers.claude_code import clear_session_for_agent
        from thread_context import get_current_registry_key
        key = get_current_registry_key() or "default"
        clear_session_for_agent(key)
        clear_framing_cache(key)  # 저장된 의식 framing도 함께 폐기
        print(f"[SESSION_RESET] 세션 매핑 클리어: {key}")
    except Exception as e:
        print(f"[SESSION_RESET] 매핑 클리어 실패 (무시): {e}")
    return SESSION_RESET_RESPONSE


class AgentCognitiveMixin:
    """AgentRunner의 인지/AI 초기화 관련 메서드 모음.

    무의식 에이전트(분류), 의식 에이전트(메타 판단), 평가 에이전트(달성 기준 검증),
    IBL 도구 구성, 실행기억 생성 등 3단 인지 아키텍처의 핵심 로직을 담당한다.
    """

    def _init_ai(self):
        """AI 에이전트 초기화

        IBL + 범용 언어 + 인지 도구 모드:
        개별 도구 패키지(308개 액션)를 로딩하지 않고, execute_ibl로 모든 노드에 접근.
        범용 언어(Python/Node.js/Shell)와 인지 도구(todo/plan/질문)는 별도 최상위 도구로 제공.
        시스템 AI는 전용 도구/프롬프트/실행기 사용.
        """
        ai_config = self.config.get("ai", {})
        agent_name = self.config.get("name", "에이전트")
        agent_id = self.config.get("id")
        is_system_ai = self.config.get("_is_system_ai", False)

        if is_system_ai:
            # 시스템 AI: 전용 역할/도구/프롬프트/실행기
            from system_ai_tools import get_all_system_ai_tools
            from system_ai_core import execute_system_tool

            role = self._load_role()
            system_prompt = self._build_system_prompt(role)
            tools = get_all_system_ai_tools()

            self.ai = AIAgent(
                ai_config=ai_config,
                system_prompt=system_prompt,
                agent_name=agent_name,
                agent_id=agent_id,
                project_path=str(self.project_path),
                tools=tools,
                execute_tool_func=execute_system_tool
            )
        else:
            # 프로젝트 에이전트: 기존 경로
            role = self._load_role()
            system_prompt = self._build_system_prompt(role)
            tools = self._build_ibl_tools()

            # 모델 기어 '실행' 축 상속/핀 — 우선순위: 기어 중앙 핀(overrides[agent_id]) >
            # yaml ai 명시 핀 > 기어 실행 축 상속(미지정 에이전트는 개별 설정 불요).
            ai_config = self._resolve_execution_config(ai_config, agent_id)

            self.ai = AIAgent(
                ai_config=ai_config,
                system_prompt=system_prompt,
                agent_name=agent_name,
                agent_id=agent_id,
                project_path=str(self.project_path),
                tools=tools
            )

    def _resolve_execution_config(self, ai_config: dict, agent_id) -> dict:
        """프로젝트 에이전트 모델 = 모델 기어가 *단독* 결정한다.

        ★per-agent 모델 설정(yaml ai.provider/model/apiKey)은 폐지됨 — 런처의 모델 티어
        (경량/중급/고급)가 유일한 모델 설정이다. yaml 의 모델/키는 무시한다.
        우선순위: 기어 중앙 핀(overrides[agent_id]) > 현재 기어의 실행 축 티어.
        키도 티어에서 온다(에이전트는 키를 들고 다니지 않는다).
        ★핀 키 = registry_key 형식 `{project_id}:{agent_id}` — agent_id 는 프로젝트 간 중복
        (예: 여러 프로젝트가 'agent_001')이라 프로젝트로 한정해야 특정 에이전트만 고정된다.
        (thinkingBudget 등 비-모델 필드는 보존.)"""
        ai_config = dict(ai_config or {})
        # 레거시 per-agent 모델 설정 제거 — 기어가 전적으로 채운다.
        for k in ("provider", "model", "api_key", "apiKey"):
            ai_config.pop(k, None)
        project_id = self.config.get("_project_id") or getattr(self, "project_id", "") or ""
        pin_key = f"{project_id}:{agent_id}" if (project_id and agent_id) else agent_id
        try:
            from model_resolver import resolve
            d = resolve("execution", agent_id=pin_key)
        except Exception as e:
            print(f"[AgentRunner] 실행 축 해소 실패: {e}")
            return ai_config

        if d.get("model"):
            ai_config["provider"] = d.get("provider") or "anthropic"
            ai_config["model"] = d["model"]
            ai_config["api_key"] = d.get("api_key", "")
            src = "중앙 핀" if str(d.get("source", "")).startswith("override:") else "실행 축 티어"
            print(f"[AgentRunner] {pin_key}: 모델 기어({src}) → {ai_config['provider']}/{ai_config['model']} ({d.get('source')})")
        return ai_config

    def _load_role(self) -> str:
        """에이전트 역할 텍스트 로드"""
        if self.config.get("_is_system_ai"):
            from runtime_utils import get_base_path
            role_path = get_base_path() / "data" / "system_ai_role.txt"
            if role_path.exists():
                return role_path.read_text(encoding='utf-8').strip()
            return "IndieBiz OS의 관리자이자 안내자"
        else:
            agent_name = self.config.get("name", "에이전트")
            role_file = self.project_path / f"agent_{agent_name}_role.txt"
            if role_file.exists():
                return role_file.read_text(encoding='utf-8')
            return ""

    def _build_health_chart(self) -> str:
        """의료 프로젝트 에이전트면 현재 환자 기록 전체를 컨텍스트로 조립('차트를 책상에 펼치기').

        의사 에이전트가 [self:health]{op:query} 로 *읽으려고* 수십 번 호출하지 않게 — 데이터를
        프롬프트에 미리 깐다. 매 호출 시 라이브 DB에서 조립(노트처럼 박제 아님). 쓰기(추가/수정/
        삭제)만 [self:health]{op:save|delete} 액션으로(sync·스키마·경로는 액션이 책임).
        의료 외 프로젝트·시스템 AI엔 안 깐다(무관·민감). 몸별 DB 경로는 storage 가 해소(폰=userdata)."""
        import os as _os
        pid = self.config.get("_project_id") or ""
        if pid != "의료" and _os.path.basename(str(self.project_path)) != "의료":
            return ""
        try:
            import importlib.util
            from runtime_utils import get_base_path
            sp = _os.path.join(str(get_base_path()), "data", "packages", "installed",
                               "tools", "health-record", "storage.py")
            spec = importlib.util.spec_from_file_location("_health_storage_chart", sp)
            hs = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(hs)
            persons = hs.list_persons()
        except Exception:
            return ""

        def _fmt(cat, v):
            if not isinstance(v, dict):
                return str(v)
            if cat == "blood_pressure":
                return f"{v.get('systolic','?')}/{v.get('diastolic','?')}"
            if "value" in v:
                u = v.get("unit")
                return f"{v['value']}{(' ' + u) if u else ''}"
            return ", ".join(f"{k}={vv}" for k, vv in v.items())

        def _cell(x):
            # 마크다운 표 셀 안전화 — 파이프/줄바꿈이 표를 깨지 않게.
            return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ").strip()

        lines = ["", "# 환자 의료기록",
                 "아래 표가 현재 시점의 전체 기록이다. 이 표로 바로 답하라(읽기용 추가 조회 불필요).",
                 "추가·수정·삭제할 때만 `[self:health]{op: save|delete}` 액션을 쓴다.",
                 "각 표는 최신순(날짜 내림차순) — 가장 최근 값은 그 표의 첫 행이다."]
        for p in persons:
            name = p.get("name", "")
            note = p.get("note")
            lines.append(f"\n## {_cell(name)}" + (f" — {_cell(note)}" if note else ""))
            try:
                ms = hs.get_measurements(days=3650, limit=30, person=name)
                if ms:
                    lines.append("\n### 측정 (최신순)")
                    lines.append("| 날짜 | 항목 | 값 |")
                    lines.append("|---|---|---|")
                    for m in ms:
                        lines.append(f"| {(m.get('measured_at') or '')[:10]} | {_cell(m['category'])} | {_cell(_fmt(m['category'], m.get('value')))} |")
                ss = hs.get_symptoms(days=3650, person=name)
                if ss:
                    lines.append("\n### 증상 (최신순)")
                    lines.append("| 시작일 | 항목 | 설명 |")
                    lines.append("|---|---|---|")
                    for s in ss:
                        lines.append(f"| {(s.get('started_at') or '')[:10]} | {_cell(s['category'])} | {_cell(s.get('description'))} |")
                mds = hs.get_medications(days=3650, person=name)
                if mds:
                    lines.append("\n### 투약")
                    lines.append("| 약 | 용량 | 빈도 | 사유 | 상태 |")
                    lines.append("|---|---|---|---|---|")
                    for md in mds:
                        act = "복용중" if md.get("is_active") else "중단"
                        lines.append(f"| {_cell(md['name'])} | {_cell(md.get('dosage'))} | {_cell(md.get('frequency'))} | {_cell(md.get('reason'))} | {act} |")
                ds = hs.get_documents(days=3650, person=name)
                if ds:
                    lines.append("\n### 문서")
                    lines.append("| 날짜 | 종류 | 설명 |")
                    lines.append("|---|---|---|")
                    for d in ds:
                        lines.append(f"| {(d.get('recorded_at') or '')[:10]} | {_cell(d['doc_type'])} | {_cell(d.get('description'))} |")
            except Exception:
                continue
        return "\n".join(lines)

    def _build_system_prompt_split(self, role: str, consciousness_output: dict = None,
                                    execution_memory: str = "") -> tuple:
        """시스템 프롬프트를 (안정, 가변)로 분리해 반환.

        시스템 AI와 프로젝트 에이전트 둘 다 캐시 prefix 보존을 위해 사용.
        가변 부분은 호출 측에서 user message 앞에 prepend한다.

        Returns:
            (stable_prompt, dynamic_context)
        """
        if self.config.get("_is_system_ai"):
            return self._build_system_ai_prompt_split(role, consciousness_output, execution_memory)
        return self._build_agent_prompt_split(role, consciousness_output, execution_memory)

    def _build_agent_prompt_split(self, role: str, consciousness_output: dict = None,
                                   execution_memory: str = "") -> tuple:
        """프로젝트 에이전트 프롬프트를 (안정, 가변)로 분리."""
        from prompt_builder import build_agent_prompt_split

        agent_name = self.config.get("name", "에이전트")
        agent_count = self._get_agent_count()
        git_enabled = (self.project_path / ".git").exists()

        agent_notes = ""
        note_file = self.project_path / f"agent_{agent_name}_note.txt"
        if note_file.exists():
            agent_notes = note_file.read_text(encoding='utf-8').strip()

        # 의료 프로젝트 에이전트: 현재 환자 기록 전체를 컨텍스트에 주입(라이브 조립).
        # 의사가 호출 없이 바로 답하게 — 읽기 조회 0번. 의료 외 프로젝트엔 빈 문자열.
        _chart = self._build_health_chart()
        if _chart:
            agent_notes = (agent_notes + "\n" + _chart) if agent_notes else _chart

        is_delegated_from_system_ai = self.delegated_from_system_ai
        if not is_delegated_from_system_ai:
            try:
                pending = self.db.get_pending_tasks(delegated_to=agent_name)
                is_delegated_from_system_ai = any(
                    t.get('requester_channel') == 'system_ai' for t in pending
                )
            except Exception:
                pass

        allowed_nodes_config = self.config.get("allowed_nodes")

        return build_agent_prompt_split(
            agent_name=agent_name,
            role=role,
            agent_count=agent_count,
            agent_notes=agent_notes,
            git_enabled=git_enabled,
            delegated_from_system_ai=is_delegated_from_system_ai,
            ibl_only=True,
            allowed_nodes=allowed_nodes_config,
            project_path=str(self.project_path),
            agent_id=self.config.get("id"),
            consciousness_output=consciousness_output,
            model_name=self.config.get("model", ""),
            execution_memory=execution_memory,
        )

    def _build_system_prompt(self, role: str, consciousness_output: dict = None,
                             execution_memory: str = "") -> str:
        """시스템 프롬프트 구성 (동적 조합) — 안정+가변 합친 단일 문자열 (호환용).

        시스템 AI와 프로젝트 에이전트 모두 이 메서드를 사용.
        새 호출자는 _build_system_prompt_split를 직접 사용해 캐시 효율을 얻는다.
        """
        if self.config.get("_is_system_ai"):
            return self._build_system_ai_prompt(role, consciousness_output, execution_memory)

        from prompt_builder import build_agent_prompt

        agent_name = self.config.get("name", "에이전트")

        # 1. 프로젝트 내 에이전트 수 파악
        agent_count = self._get_agent_count()

        # 2. Git 활성화 여부 (system 노드는 ALWAYS_ALLOWED이므로 .git 존재만 확인)
        git_enabled = (self.project_path / ".git").exists()

        # 3. 에이전트별 영구메모
        agent_notes = ""
        note_file = self.project_path / f"agent_{agent_name}_note.txt"
        if note_file.exists():
            agent_notes = note_file.read_text(encoding='utf-8').strip()

        # 시스템 AI 위임 여부 확인
        is_delegated_from_system_ai = self.delegated_from_system_ai
        if not is_delegated_from_system_ai:
            try:
                pending = self.db.get_pending_tasks(delegated_to=agent_name)
                is_delegated_from_system_ai = any(
                    t.get('requester_channel') == 'system_ai' for t in pending
                )
            except Exception:
                pass

        # 4. allowed_nodes (IBL 노드 접근 제어)
        allowed_nodes_config = self.config.get("allowed_nodes")

        # 동적 프롬프트 빌드 (Phase 16: ibl_only 단일 경로)
        return build_agent_prompt(
            agent_name=agent_name,
            role=role,
            agent_count=agent_count,
            agent_notes=agent_notes,
            git_enabled=git_enabled,
            delegated_from_system_ai=is_delegated_from_system_ai,
            ibl_only=True,
            allowed_nodes=allowed_nodes_config,
            project_path=str(self.project_path),
            agent_id=self.config.get("id"),
            consciousness_output=consciousness_output,
            model_name=self.config.get("model", ""),
            execution_memory=execution_memory,
        )

    def _build_system_ai_prompt(self, role: str, consciousness_output: dict = None,
                                execution_memory: str = "") -> str:
        """시스템 AI 전용 프롬프트 빌드 (안정+가변 합친 단일 문자열, 호환용)"""
        from prompt_builder import build_system_ai_prompt
        from system_ai_memory import load_user_profile

        git_enabled = (self.project_path / ".git").exists()
        user_profile = load_user_profile()

        return build_system_ai_prompt(
            user_profile=user_profile,
            git_enabled=git_enabled,
            consciousness_output=consciousness_output,
            model_name=self.config.get("ai", {}).get("model", ""),
            execution_memory=execution_memory,
        )

    def _build_system_ai_prompt_split(self, role: str, consciousness_output: dict = None,
                                      execution_memory: str = "") -> tuple:
        """시스템 AI 프롬프트를 (안정, 가변)로 분리.

        안정 부분만 system_prompt로 넘기면 프롬프트 캐시 prefix가 매 호출마다
        동일해져 Anthropic 캐시가 hit한다. 가변 부분은 호출 측에서 user message
        앞에 prepend한다.

        Returns:
            (stable_prompt, dynamic_context)
        """
        from prompt_builder import build_system_ai_prompt_split
        from system_ai_memory import load_user_profile

        git_enabled = (self.project_path / ".git").exists()
        user_profile = load_user_profile()

        return build_system_ai_prompt_split(
            user_profile=user_profile,
            git_enabled=git_enabled,
            consciousness_output=consciousness_output,
            model_name=self.config.get("ai", {}).get("model", ""),
            execution_memory=execution_memory,
        )

    def _build_execution_memory(self, user_message: str, action_hint: Optional[str] = None) -> tuple:
        """연상기억 생성 — 실행기억(해마) + 관련기억(심층 메모리)

        파이프라인의 모든 에이전트(무의식/의식/실행/평가)가 공유하는 통합 기억.
        사용자 명령 당 해마 검색은 단 1회. 호출 측은 반환된 top_score를 그대로 사용하여
        Reflex 분기, 경험 증류 판정 등에서 추가 검색을 피한다.

        Args:
            user_message: 사용자 명령
            action_hint: 마법책에서 사용자가 명시적으로 선택한 액션 ID ("sense:price" 등).
                지정되면 해마 시맨틱 검색을 건너뛰고 그 액션을 Top-1로 <execution_memory> 합성.
                잘못된 액션 ID면 자동으로 해마 검색으로 폴백.

        Returns:
            (xml: str, top_score: float, top_code: str)
            - xml: <execution_memory> + <related_memory> 결합된 문자열 (없으면 "")
            - top_score: 해마 최고 점수 (action_hint 적용 시 1.0)
            - top_code: 해마 최고 점수 항목의 ibl_code (action_hint 적용 시 "[node:action]")
        """
        try:
            exec_xml, top_score, top_code = ("", 0.0, "")
            if action_hint:
                from ibl_usage_rag import build_execution_memory_from_hint
                exec_xml, top_score, top_code = build_execution_memory_from_hint(action_hint)
                if not exec_xml:
                    print(f"[연상] action_hint='{action_hint}' 유효하지 않음 — 해마 검색으로 폴백")

            if not exec_xml:
                from ibl_usage_rag import build_execution_memory
                allowed_nodes = self.config.get("allowed_nodes")
                allowed_set = None
                if allowed_nodes:
                    from ibl_access import resolve_allowed_nodes
                    allowed_set = resolve_allowed_nodes(allowed_nodes)
                exec_xml, top_score, top_code = build_execution_memory(user_message, allowed_set)

            # 심층 메모리에서 관련기억 검색 → 연상기억 합성
            related = self._search_related_memory(user_message)
            result = exec_xml
            if related:
                result = (result + "\n" + related) if result else related

            # 포식 기억(냄새지도) — ★실행기억처럼 *항상-on*. 회상은 싸고(LLM 0, DB+필터), 무관하면
            #   query 필터가 빈 결과로 자기-억제한다(비용~0). 주인모델(owner)은 query 무관 상시 노출
            #   =냄새(scent) → 명시 명령 없이도 능동 포식을 촉발. map 은 query 필터(관련 위치만).
            #   FORAGER_MULTIBODY_DESIGN §주입(THINK-게이트 폐기, 관련성=query 가 자연 게이트).
            forage = self._search_forage_memory(user_message)
            if forage:
                result = (result + "\n" + forage) if result else forage

            # 거친 디스크 골격(어디에) — ★포식 의도일 때만(상시-on 폐기, 웹랜드마크와 같은 게이트).
            #   집중 관심 폴더 아래 거친 디렉토리 트리(맥/윈도우/리눅스 각자 자기 루트). ~5천 자라
            #   파일·디스크 질의에만 값을 하고 그 외엔 무관 → _FORAGE_CUES 없으면 빈 결과(메서드 내 게이트).
            #   깊은 상세·큐레이션은 위 forager 냄새가 관련시 페이징. focus_map.py(헌법1조).
            skeleton = self._build_disk_skeleton(user_message)
            if skeleton:
                result = (result + "\n" + skeleton) if result else skeleton

            # 웹 랜드마크(참고지도) — 웹 포식 의도일 때만(상시-on 아님). 비액션 웹 출처
            #   "어디를·뭘 보러 가나". 수동 큐레이션(data/web_landmarks.md), 자동화는 다음 단계.
            web_landmarks = self._build_web_landmarks(user_message)
            if web_landmarks:
                result = (result + "\n" + web_landmarks) if result else web_landmarks

            if result:
                parts = []
                if "execution_memory" in result:
                    parts.append("실행기억")
                if "related_memory" in result:
                    parts.append("관련기억")
                if "forage_memory" in result:
                    parts.append("포식기억")
                if "disk_skeleton" in result:
                    parts.append("디스크골격")
                if "web_landmarks" in result:
                    parts.append("웹랜드마크")
                print(f"[연상] {'+'.join(parts)}: \"{user_message[:40]}\"")
            else:
                print(f"[연상] 빈 결과: \"{user_message[:40]}\"")

            return (result, top_score, top_code)
        except Exception as e:
            import traceback
            print(f"[연상] 생성 실패: {e}")
            traceback.print_exc()
            return ("", 0.0, "")

    def _search_related_memory(self, user_message: str) -> str:
        """심층 메모리에서 관련기억 검색 (top-3)

        사용자 메시지를 키워드로 심층 메모리를 검색하여
        <related_memory> XML 블록으로 반환한다.
        """
        try:
            import sys
            import os
            # memory_db 패키지 경로 추가
            mem_pkg = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..",
                "data", "packages", "installed", "tools", "memory"
            )
            if mem_pkg not in sys.path:
                sys.path.insert(0, mem_pkg)
            import memory_db

            from thread_context import get_current_agent_id
            agent_id = get_current_agent_id()
            project_path = str(self.project_path)

            # ★점수 바닥(자동 주입은 정밀도 우선): LIKE 폴백 끄고(semantic_only) 시맨틱 컷오프를
            #   0.45 로 올린다 — 키워드만 겹치는 무관 기억(예: 'kind:operator' 질의에 무의식-분류기)
            #   이 매번 3건 끌려오던 노이즈 제거. 바닥 미달이면 빈 결과 = 주입 안 함.
            results = memory_db.search(
                project_path=project_path,
                agent_id=agent_id,
                query=user_message,
                limit=3,
                semantic_only=True,
                min_score=0.45,
            )
            if not results:
                return ""

            # 전문 조회 (preview는 100자 잘림이므로)
            items = []
            for r in results:
                # last_seen은 read()가 used_at을 now로 갱신하기 전 값(search 결과)에서 취한다.
                # 마지막으로 확인된(사용되거나 만들어진) 날짜 — 에이전트가 낡음을 스스로 판단하도록.
                last_seen = (r.get("used_at") or r.get("created_at") or "")[:10]
                full = memory_db.read(project_path, agent_id, r["id"])
                if full:
                    cat = full.get("category", "")
                    kw = full.get("keywords", "")
                    content = full.get("content", "")
                    meta = f' category="{cat}"' if cat else ""
                    meta += f' keywords="{kw}"' if kw else ""
                    meta += f' last_seen="{last_seen}"' if last_seen else ""
                    items.append(f"  <memory{meta}>{content}</memory>")

            if not items:
                return ""

            xml = (
                '<related_memory note="심층 메모리에서 연상된 관련 기억입니다. 참고용. '
                'last_seen은 그 기억이 마지막으로 확인된 날짜이니, 오래된 기억은 현재와 다를 수 있음을 감안하세요.">\n'
                + "\n".join(items)
                + "\n</related_memory>"
            )
            print(f"[연상:관련기억] {len(items)}건 검색됨: \"{user_message[:40]}\"")
            print(f"[연상:관련기억] 내용:\n{xml}")
            return xml

        except Exception as e:
            print(f"[연상:관련기억] 검색 실패 (무시): {e}")
            return ""

    # 포식 의도 단서 — *이미 있는 걸 찾기* 의도 게이트(매체 무관, 싸고 너그럽게).
    #   ★공간(어느 몸: 디스크/코드/웹/책/볼륨…)은 키워드로 재유추하지 않는다 — 증류기 LLM 이
    #   명명한다(forager=AI, FORAGER_MULTIBODY_DESIGN §9 "불변 2축"). 여기 cue 는 *비용 게이트*일
    #   뿐: 비포식 잡담에 회상/증류 LLM 을 안 돌리려는 것. 매체가 늘어도 이 목록은 안 늘어난다.
    _FORAGE_CUES = (
        "찾", "검색", "어디", "뒤져", "뒤지", "파일", "사진", "자료", "폴더",
        "문서", "디스크", "볼륨", "찍은", "받은", "저장한", "예전", "지난",
        "코드", "코드베이스", "함수", "클래스", "구현", "정의", "모듈", "리포",
        "웹", "온라인", "인터넷", "구글", "논문", "기사",
        "find", "search", "where", "locate", "file", "photo", "folder",
        "document", "disk", "volume", "code", "codebase", "function",
        "implement", "module", "repo", "defined", "web", "online", "scholar", "arxiv",
    )

    # 포식 *증거* — 응답이 실제로 navigable/반구조 공간을 뒤졌나(증류 2차 비용 게이트).
    #   디스크 경로·URL·코드 구성·파일확장자를 *한 집합*으로(per-medium 분기 아님 — 매체 무관).
    _FORAGE_EVIDENCE_RE = re.compile(
        r"https?://|/[\w가-힣.\-]+/[\w가-힣.\-]+|"
        r"\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|kt|pdf|jpe?g|png|docx?|xlsx?)\b|"
        r"\b(?:def |class |import |grep)", re.IGNORECASE)
    _FORAGE_EVIDENCE_WORDS = (
        "폴더", "디렉토리", "디스크", "볼륨", "확장자", "파일명", "핸들러", "모듈",
        "출처", "검색 결과", "검색결과", "논문", "사이트", "scholar", "arxiv",
    )

    def _repo_root_path(self, *texts: str) -> Optional[str]:
        """포식 중인 코드 공간의 *루트 절대경로* — 응답 속 소스파일 경로의 .git 조상.

        폴백=cwd 의 git 루트. 못 찾으면 None. _repo_identity(basename)·코드 locus 정규화 공용.
        포식 *공간* 식별(하드웨어 자아 아님 — FORAGER_MULTIBODY_DESIGN §1).
        """
        import os
        def _git_root(start: str) -> Optional[str]:
            d = start
            for _ in range(10):
                if os.path.isdir(os.path.join(d, ".git")):
                    return d.rstrip("/") or None
                nd = os.path.dirname(d)
                if nd == d:
                    return None
                d = nd
            return None
        # 1) 응답 속 소스파일 절대경로 → .git 조상
        for t in texts:
            for m in re.finditer(r"(/[\w./가-힣-]+?\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|kt))\b",
                                 t or ""):
                root = _git_root(os.path.dirname(m.group(1)))
                if root:
                    return root
        # 2) 폴백 — 실행 cwd 의 git 루트
        try:
            return _git_root(os.getcwd())
        except Exception:
            return None

    def _repo_identity(self, *texts: str) -> Optional[str]:
        """코드 공간 정체(basename) — body 키 'code:<repo>' 용. _repo_root_path 의 basename."""
        import os
        root = self._repo_root_path(*texts)
        return os.path.basename(root) if root else None

    def _normalize_space(self, space: Optional[str], ai_response: str = "",
                         user_message: str = "") -> str:
        """증류기 LLM 이 명명한 공간 라벨을 body 키로 정규화(매체 무관).

        AI 가 무엇을 포식했는지 안다(forager=AI) → 키워드로 재유추하지 않고 *명명*을 받는다.
        'code'(레포명 없음)면 .git 으로 보강, 빈 값이면 'mac'(기본 디스크). 그 외엔 라벨 그대로
        (web/book:<제목>/disk:<라벨>/… 매체가 늘어도 코드 변경 0 — FORAGER_MULTIBODY_DESIGN §9).
        """
        s = (space or "").strip()
        if not s:
            return "mac"
        # bare "code"(레포명 없음)면 .git basename 으로 보강(케이스 보존 — repo/label 은 식별자).
        if s.lower() == "code":
            repo = self._repo_identity(ai_response, user_message)
            return f"code:{repo}" if repo else "code"
        return s  # 라벨 그대로(case-sensitive 식별자: code:<repo>/disk:<label>/book:<title>)

    def _search_forage_memory(self, user_message: str) -> str:
        """포식 기억(냄새지도) 회상 — ★실행기억처럼 항상-on(0단계 _build_execution_memory).

        회상은 싸다(LLM 0, SQLite+키워드필터). 무관하면 query 필터가 빈 결과로 자기-억제(비용~0).
        map 은 query 필터(관련 위치만), owner(주인모델)는 query 무관 상시 노출=냄새(scent)로 능동
        포식 촉발(filter_owner=False). 전 body 회상(query 가 자기-스코핑 §9). 해마 <execution_memory>·
        심층 <related_memory> 의 *공간* 짝(F2). 맥 자아 전용. 실패는 무시(파이프라인 불변).
        """
        try:
            import sys, os
            bk = os.path.dirname(os.path.abspath(__file__))
            if bk not in sys.path:
                sys.path.insert(0, bk)
            # 하드웨어 자아 게이트(누가 포식) — 폰 자아는 미디어-한정(A3 후속)
            try:
                from runtime_utils import detect_body
                hw = detect_body().get("profile") or "mac"
            except Exception:
                hw = "mac"
            if hw == "phone":
                return ""
            import forage_memory
            xml = forage_memory.recall_xml(body=None, query=user_message, limit=12,
                                           filter_owner=False)
            return xml
        except Exception as e:
            print(f"[포식기억] 회상 실패 (무시): {e}")
            return ""

    def _build_disk_skeleton(self, user_message: str = "") -> str:
        """거친 디스크 골격 회상 — 데스크탑(맥/윈도우/리눅스), *포식 의도일 때만*(웹랜드마크와 같은 게이트).

        집중 관심 폴더 아래 거친 디렉토리 트리("어디에"). focus 루트는 focus_map 이 몸별 해소 —
        focus 폴더(어휘)는 몸 독립, 생성기 바인딩만 몸별(헌법1조). 캐시(TTL)라 매 메시지 walk 없음.
        깊은 상세·큐레이션은 forager 냄새 몫. 실패는 무시(파이프라인 불변).

        ★게이트(상시-on 폐기): 디스크 골격은 ~5천 자인데 *파일·디스크 질의*에만 값을 한다 — 아키텍처
        ·대화·버그 질의엔 무관 폴더 목록을 매번 깔던 낭비(측정). _FORAGE_CUES(찾기·파일·폴더·디스크…)
        없으면 빈 결과. 웹랜드마크가 "웹 의도일 때만"인 것과 같은 의도 게이트.

        ★폰 제외(의도): 안드로이드 스코프드 스토리지라 os.walk 가 공유 스토리지에 안 먹히고
        (파일 접근은 MediaStore 경유), 폰에선 거친 디스크 지도 실익이 작다(사용자 결정). 빈 결과로
        '지원하는 척' 안 한다 — _search_forage_memory 의 폰 게이트와 같은 자리.
        """
        # 포식 의도 게이트 — 비포식(아키텍처·대화·버그) 질의엔 골격을 넣지 않는다.
        if not any(cue in (user_message or "").lower() for cue in self._FORAGE_CUES):
            return ""
        try:
            import sys, os
            bk = os.path.dirname(os.path.abspath(__file__))
            if bk not in sys.path:
                sys.path.insert(0, bk)
            try:
                from runtime_utils import detect_body
                profile = detect_body().get("profile") or "mac"
            except Exception:
                profile = "mac"
            if profile == "phone":
                return ""  # 폰 미지원(스코프드 스토리지·실익 작음)
            import focus_map
            return focus_map.build_coarse_map_xml(profile=profile)
        except Exception as e:
            print(f"[디스크골격] 생성 실패 (무시): {e}")
            return ""

    def _build_web_landmarks(self, user_message: str) -> str:
        """웹 랜드마크(참고지도) 주입 — 웹 포식 의도일 때만(상시-on 아님).

        "웹 보러 갈 때 펴는 지도" — 비액션 출처(어디를·뭘 보러 가나). data/web_landmarks.md
        (수동 큐레이션, 쓰면서 반성-업데이트). 자동화(forager 증류로 채우기·빈도→졸업/대체불가성
        →생존)는 다음 단계. 실패는 무시(파이프라인 불변).

        ★세션-인지 게이트(라이브 로그 교정): 웹 포식은 *멀티턴 세션*이라 매-메시지 키워드만으론
        후속 추적 턴("그녀가…")을 놓치고 디스크 파일찾기("…파일 찾아줘")엔 헛주입된다. 그래서
        ①키워드(새 웹 턴, 단 디스크-찾기 신호 있으면 제외) OR ②진행 중 웹 framing(재사용될
        의식 framing 의 highlight_actions 가 search/crawl/paper 면 키워드 없어도) 둘 중 하나로 연다.
        """
        try:
            msg = (user_message or "").lower()
            strong_web = ("검색", "서치", "search", "인터넷", "웹", "온라인", "조사",
                          "알아봐", "최신", "뉴스", "논문", "사이트", "출처", "google",
                          "구글", "리서치", "인물", "누구")
            find_cue = ("찾아", "찾는", "어디")
            disk_marker = ("파일", "폴더", "디렉토리", "디스크", "하드", "바탕화면", "다운로드")
            has_strong = any(s in msg for s in strong_web)
            # 디스크 작업(파일찾기 등)이면 웹 랜드마크 불필요 — 디스크 골격·forager 담당
            if any(d in msg for d in disk_marker) and not has_strong:
                return ""
            kw_web = has_strong or any(f in msg for f in find_cue)
            # 세션 신호: 진행 중(재사용될) 의식 framing 이 웹-지향이면 키워드 없어도 주입
            framing_web = False
            try:
                from thread_context import get_current_registry_key
                key = get_current_registry_key() or "default"
                prev = framing_cache_get(key)
                if prev:
                    acts = " ".join(
                        prev.get("capability_focus", {}).get("highlight_actions", [])
                    ).lower()
                    framing_web = any(v in acts for v in
                                      ("search", "crawl", "paper", "scholar", "ddg", "news"))
            except Exception:
                pass
            if not (kw_web or framing_web):
                return ""
            cls = type(self)
            cache = getattr(cls, "_web_landmarks_cache", None)
            if cache is None:
                from runtime_utils import get_base_path
                path = get_base_path() / "data" / "web_landmarks.md"
                cache = path.read_text(encoding="utf-8") if path.exists() else ""
                cls._web_landmarks_cache = cache
            if not cache:
                return ""
            note = ("웹 출처 참고지도(비액션). 액션 도메인은 IBL 액션으로 — "
                    "통계·공시·법령·부동산실거래·도서·공연·날씨·CCTV·쇼핑 등.")
            return f'<web_landmarks note="{note}">\n{cache}\n</web_landmarks>'
        except Exception as e:
            print(f"[웹랜드마크] 생성 실패 (무시): {e}")
            return ""

    def _run_consciousness_or_reuse(self, user_message: str, history: list,
                                    execution_memory: str = "") -> Optional[dict]:
        """THINK 경로의 의식 진입점 — framing 재고가 있으면 재사용, 없으면 생성.

        THINK 판정은 "framing이 필요하다"는 수요다. 같은 대화에서 이미 만든
        framing이 지금 질문에 맞으면(fit 게이트, 경량 1회) 재사용하고 의식(Opus)
        호출을 건너뛴다. 없거나 안 맞으면 의식 에이전트가 새로 만들어 저장한다.
        per-turn으로 바뀌는 achievement_criteria만 게이트가 새로 뽑는다.
        """
        from thread_context import get_current_registry_key
        key = get_current_registry_key() or "default"

        # 후속 turn(히스토리 존재) + 저장된 framing 있을 때만 재사용 시도
        prev = framing_cache_get(key) if history else None
        if prev:
            gate = self._consciousness_fit_gate(user_message, prev)
            if gate and gate.get("fits"):
                reused = dict(prev)
                reused["achievement_criteria"] = (
                    gate.get("criteria") or prev.get("achievement_criteria", "")
                )
                reused["history_summary"] = ""  # 실제 최근 history가 그대로 흐르도록
                self._log(
                    f"[의식] framing 재사용 (Opus 스킵): {reused.get('task_framing', '')[:50]}"
                )
                return reused

        # 없거나 안 맞음 → 의식 에이전트가 새로 만든다
        out = self._run_consciousness(user_message, history, execution_memory)
        # 미완성 framing(clarification 요청)은 재고로 쌓지 않는다
        if out and not out.get("needs_clarification"):
            framing_cache_set(key, out)
        return out

    def _consciousness_fit_gate(self, user_message: str, prev_framing: dict) -> Optional[dict]:
        """저장된 framing이 현재 질문에 맞는지 경량 모델로 판정 + 이번 turn 달성 기준 생성.

        Returns:
            {"fits": bool, "criteria": str} 또는 None(실패 → 호출 측은 풀 의식 폴백)
        """
        try:
            from consciousness_agent import lightweight_ai_call

            task_framing = (prev_framing or {}).get("task_framing", "")
            if not task_framing:
                return None

            prompt = f"""아래는 직전까지 진행 중인 태스크의 정의(framing)다.

[진행 중 태스크]
{task_framing}

[사용자의 새 메시지]
{user_message}

판정하라:
1. 이 framing이 새 메시지를 푸는 데 그대로 맞는가? 같은 태스크의 연장·변주(조건/방향/대상만 바뀐 경우)면 맞고(fits=true), 주제가 바뀌었으면 안 맞다(fits=false).
2. 맞다면 이번 메시지의 구체적 달성 기준을 한 줄로 작성하라.

JSON으로만 응답: {{"fits": true/false, "criteria": "..."}}"""

            resp = lightweight_ai_call(
                prompt,
                system_prompt="진행 중 태스크 framing의 적합성 판정기. JSON으로만 응답.",
                role="background",
            )
            if not resp:
                return None

            cleaned = resp.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            data = json.loads(cleaned)
            if not isinstance(data, dict) or "fits" not in data:
                return None
            return {
                "fits": bool(data.get("fits")),
                "criteria": str(data.get("criteria", "") or ""),
            }
        except Exception as e:
            self._log(f"[의식] fit 게이트 실패 (풀 의식 폴백): {e}")
            return None

    def _run_consciousness(self, user_message: str, history: list,
                           execution_memory: str = "") -> dict:
        """의식 에이전트 실행 — 메타 판단

        사용자 메시지와 히스토리를 분석하여 프롬프트 최적화 지침을 반환합니다.
        실패 시 None을 반환하고, 기존 방식으로 폴백합니다.

        Returns:
            의식 에이전트 출력 dict 또는 None
        """
        try:
            from consciousness_agent import (
                get_consciousness_agent,
                get_guide_list,
                get_world_pulse_text,
            )

            agent = get_consciousness_agent()
            if not agent.is_ready:
                return None

            agent_name = self.config.get("name", "")

            # 역할 전문 로드 (잘리지 않고 전체 전달 — self_awareness 판단용)
            agent_role = self._load_role()

            # 영구메모 로드 — 시스템 AI는 사용자 프로필 사용
            if self.config.get("_is_system_ai"):
                from system_ai_memory import load_user_profile
                agent_notes = load_user_profile()
            else:
                agent_notes = self.config.get("notes", "")

            # 가용 도구 목록 — 의식이 capability_focus.tools에 추천할 수 있는 범위.
            # 시스템 AI는 system_ai_tools, 프로젝트 에이전트는 _get_available_tools().
            try:
                if self.config.get("_is_system_ai"):
                    from system_ai_tools import get_all_system_ai_tools
                    available_tools = [t.get("name", "") for t in get_all_system_ai_tools()
                                       if isinstance(t, dict) and t.get("name")]
                else:
                    available_tools = self._get_available_tools()
            except Exception as e:
                self._log(f"[의식] 가용 도구 목록 조회 실패 (검증 스킵): {e}")
                available_tools = None

            result = agent.process(
                user_message=user_message,
                history=history,
                associative_memory=execution_memory,  # 연상기억(해마+심층메모리) 묶음
                guide_list=get_guide_list(user_message),
                world_pulse=get_world_pulse_text(),
                agent_name=agent_name,
                agent_role=agent_role,
                agent_notes=agent_notes,
                available_tools=available_tools,
            )

            if result:
                self._log(f"[의식] 태스크: {result.get('task_framing', '')[:60]}")
            return result

        except Exception as e:
            self._log(f"[의식] 실행 실패 (폴백): {e}")
            return None

    def _distill_deep_memory(self, user_message: str, ai_response: str):
        """대화 후 심층 메모리 자동 저장.

        경량 AI로 대화에서 기억할 정보 조각을 추출하고,
        기존 심층 메모리와 비교하여 추가/업데이트한다.
        """
        try:
            if not user_message or not ai_response:
                return

            import sys, os, json
            mem_pkg = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..",
                "data", "packages", "installed", "tools", "memory"
            )
            if mem_pkg not in sys.path:
                sys.path.insert(0, mem_pkg)
            import memory_db

            from thread_context import get_current_agent_id
            from consciousness_agent import lightweight_ai_call

            agent_id = get_current_agent_id()
            project_path = str(self.project_path)

            # 1단계: 대화에서 기억할 정보 조각 추출
            extract_prompt = f"""다음 대화에서 나중에 기억해둘 만한 사실 정보를 추출하라.
(이름, 중요한 날짜, 사용자 선호, 결정사항, 작업 결과 등)
일시적 데이터(주가, 날씨, 환율, 시세 등)와 추론/감상은 제외. JSON 배열로만 응답.
[{{"content": "...", "keywords": "k1,k2", "category": "사용자선호|사용자정보|작업기록|의사결정|중요날짜"}}]
정보가 없으면 빈 배열 [] 반환.

사용자: {user_message[:500]}
AI: {ai_response[:500]}"""

            result = lightweight_ai_call(
                prompt=extract_prompt,
                system_prompt="사실 정보만 추출하라. JSON 배열로만 응답.",
                role="background",
            )
            if not result:
                return

            # JSON 파싱
            cleaned = result.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            facts = json.loads(cleaned)
            if not isinstance(facts, list) or not facts:
                return

            saved_count = 0
            updated_count = 0

            # 2단계: 각 조각의 기존 유사 항목을 기계적으로 탐색(임베딩, 무LLM).
            #   - 유사 항목 없음 → 곧장 NEW (LLM 판정 불필요)
            #   - 유사 항목 있음 → (신규, 기존 후보) 쌍으로 모아 다음 단계에서 '한 번에' 판정
            pending = []   # [(fact, top)] — 배치 dedup 대상
            for fact in facts[:5]:  # 최대 5개 조각
                content = fact.get("content", "").strip()
                if not content:
                    continue
                fact["content"] = content
                fact["keywords"] = fact.get("keywords", "").strip()
                fact["category"] = fact.get("category", "").strip()

                existing = memory_db.search(
                    project_path=project_path, agent_id=agent_id,
                    query=fact["keywords"] or content, limit=3,
                )
                top = (memory_db.read(project_path, agent_id, existing[0]["id"])
                       if existing else None)
                if top:
                    pending.append((fact, top))
                else:
                    memory_db.save(
                        project_path=project_path, agent_id=agent_id,
                        content=content, keywords=fact["keywords"],
                        category=fact["category"],
                    )
                    saved_count += 1
                    print(f"[심층메모리] NEW [{fact['category']}]: \"{content[:50]}\"")

            # 3단계: 유사쌍이 있으면 '단 한 번'의 배치 호출로 전부 판정 (조각마다 호출 X)
            verdicts = []
            if pending:
                pairs_text = "\n".join(
                    f'{i+1}. 기존: {top["content"][:200]}\n   신규: {fact["content"][:200]}'
                    for i, (fact, top) in enumerate(pending)
                )
                batch_prompt = (
                    "각 쌍의 '기존 기억'과 '신규 정보'의 관계를 판정하라.\n"
                    "SAME(완전 동일) / UPDATE(기존도 유효한데 정보 보충) / "
                    "REPLACE(기존이 틀렸거나 옛 정보라 새 정보로 정정·대체) / "
                    "NEW(서로 다른 정보) 중 하나씩.\n\n"
                    f"{pairs_text}\n\n"
                    '쌍 순서대로 JSON으로만 응답: {"verdicts": ["SAME"|"UPDATE"|"REPLACE"|"NEW", ...]}'
                )
                resp = lightweight_ai_call(
                    prompt=batch_prompt,
                    system_prompt="기억 관계 판정기. 쌍 순서대로 verdict 배열만 JSON으로 응답.",
                    role="background",
                )
                if resp:
                    rc = resp.strip()
                    if rc.startswith("```"):
                        rc = rc.split("\n", 1)[-1]
                        if rc.endswith("```"):
                            rc = rc[:-3]
                        rc = rc.strip()
                    try:
                        verdicts = (json.loads(rc) or {}).get("verdicts", [])
                    except json.JSONDecodeError:
                        verdicts = []

            # 4단계: 판정 적용 (verdict 누락/불명은 NEW로 안전 처리)
            for i, (fact, top) in enumerate(pending):
                j = (verdicts[i] if i < len(verdicts) else "NEW")
                j = str(j).strip().upper()
                content = fact["content"]
                keywords = fact["keywords"]
                category = fact["category"]
                if "SAME" in j:
                    memory_db.update(project_path, agent_id, top["id"])
                    print(f"[심층메모리] SAME 스킵: \"{content[:50]}\"")
                elif "REPLACE" in j:
                    # 정정 → 기존을 새 정보로 덮어쓰기 (옛/틀린 정보 폐기)
                    merged_kw = _merge_keywords(top.get("keywords", ""), keywords)
                    memory_db.update(project_path, agent_id, top["id"],
                                     content=content, keywords=merged_kw)
                    updated_count += 1
                    print(f"[심층메모리] REPLACE: \"{content[:50]}\" → 기존 ID {top['id']} 덮어씀")
                elif "UPDATE" in j:
                    # 보충 → 기존 내용에 덧붙임 (둘 다 유효)
                    merged = f"{top['content']}\n[보충] {content}"
                    merged_kw = _merge_keywords(top.get("keywords", ""), keywords)
                    memory_db.update(project_path, agent_id, top["id"],
                                     content=merged, keywords=merged_kw)
                    updated_count += 1
                    print(f"[심층메모리] UPDATE: \"{content[:50]}\" → 기존 ID {top['id']}")
                else:  # NEW (또는 불명)
                    memory_db.save(project_path=project_path, agent_id=agent_id,
                                   content=content, keywords=keywords, category=category)
                    saved_count += 1
                    print(f"[심층메모리] NEW [{category}]: \"{content[:50]}\"")

            if saved_count or updated_count:
                print(f"[심층메모리] 저장 {saved_count}건, 업데이트 {updated_count}건: "
                      f"\"{user_message[:40]}\"")

        except json.JSONDecodeError:
            print(f"[심층메모리] JSON 파싱 실패 (무시)")
        except Exception as e:
            print(f"[심층메모리] 실패 (무시): {e}")

    def _distill_forage_memory(self, user_message: str, ai_response: str):
        """포식 후 자동 증류 — 냄새지도(forage_map)+주인모델(owner_model)에 *델타만* 누적.

        해마/심층메모리 증류의 *공간* 짝(docs/FORAGER_MEMORY_SCHEMA.md §4.2). forage 의도
        대화에서, 미래 탐색을 싸게 만들 *일반화 가능한 공간 지식*(폴더 정체·관습·죽은가지·
        주인 신호)만 추출한다 — 날 내용·이번에 찾은 특정 파일은 저장 안 함. 기존 지도를 함께
        넘겨 *새롭거나 교정된 것*만 내도록 한다(surprise/교정). dedup 은 저장소 UNIQUE upsert 가
        기계적으로 처리(재note=강화) → 2차 판정 LLM 불필요. 실패는 무시(파이프라인 불변).

        step 5(surface 카운터-패스): 기존 라벨을 *위반*하는 이질 내용을 만나면 그 항목에
        surface 표식 → 필터버블 반대힘([[project_augmentation_over_autonomy]]).
        """
        try:
            if not user_message or not ai_response:
                return
            msg = user_message.lower()
            if not any(cue in msg for cue in self._FORAGE_CUES):
                return  # 비forage 대화 — 증류 없음
            import sys, os, json
            bk = os.path.dirname(os.path.abspath(__file__))
            if bk not in sys.path:
                sys.path.insert(0, bk)
            # 하드웨어 자아 게이트(누가 포식) — 공간 body 와 분리(§1)
            try:
                from runtime_utils import detect_body
                hw = detect_body().get("profile") or "mac"
            except Exception:
                hw = "mac"
            if hw == "phone":
                return  # 폰 자아는 미디어-한정(A3 후속)
            # 2차 싼 게이트(매체 무관): 응답이 실제 navigable/반구조 공간을 뒤졌나(맛집·영상 검색 등 LLM 낭비 차단).
            #   디스크 경로·URL·코드 구성·확장자를 한 집합으로 — per-medium 분기 없음(§9).
            ar_l = ai_response.lower()
            if not (self._FORAGE_EVIDENCE_RE.search(ai_response)
                    or any(w in ar_l for w in self._FORAGE_EVIDENCE_WORDS)):
                return  # 포식 흔적 없음 — 증류 스킵(LLM 호출 안 함)
            import forage_memory
            from consciousness_agent import lightweight_ai_call

            # 1) 기존 지도(전 공간) 요약 → "이미 아는 것"으로 (델타만 추출하도록). body 표기로 공간 구분.
            known = forage_memory.recall(body=None, query=None, limit=40)
            known_lines = []
            for m in known.get("map", []):
                known_lines.append(f'- [{m.get("body","?")}/{m["kind"]}] {m["locus"]}: {m["claim"]}')
            for o in known.get("owner", []):
                known_lines.append(f'- [owner:{o["facet"]}] {o["value"]}')
            known_text = "\n".join(known_lines) if known_lines else "(아직 없음)"

            # 2) 경량 LLM 으로 *일반화 가능한 공간 지식* 델타 추출 — ★공간-중립 단일 프롬프트.
            #   매체별 분기 없음: AI 가 무엇을 포식했는지 *명명*(space)한다(forager=AI, §9 불변 2축).
            extract_prompt = f"""이번 대화는 어떤 공간을 *포식*(이미 있는 걸 찾기)한 것이다 — 디스크 폴더·코드레포·웹·책·외장볼륨 중 하나.
미래의 탐색을 싸게 만들 **일반화 가능한 공간 지식**만 추출하라. 이번에 찾은 특정 항목·날 내용은 제외하고, *다음에도 쓸* 지도만:

먼저 **space**(무엇을 포식했나)를 명명하라:
- "mac"=내 홈 디스크 / "code:<레포명>"=코드레포 / "web"=웹 / "book:<제목>"=책 / "disk:<라벨>"=외장볼륨

그다음 지도(공간 종류에 맞게 자연히 채워라):
- map.identity: "이 위치 = X"(폴더/모듈/1차출처의 정체 — 예 "발표자료 폴더", "backend/=라우터", "내 논문=NYU Scholars")
- map.convention: 주인의 정리·명명·탐색 관습(예 "발표=장소+날짜", "IBL 액션=src에 정의→build로 생성", "동명이인=분야어로 좁힘")
- map.dead_branch: "여기엔 그것 없음"(+ prune_reason: 왜 아마 없나 — 폐기가능)
- map.substrate: 기질 가용성(예 "EXIF 색인 없음", "1500줄 파일제한", "이 사이트=페이월")
- owner.{{identity|domain|affiliation|signal|lexicon|habit}}: 주인이 *누구인가* 모델(정체·분야·소속·내용지문·어휘매핑·*개인 정리습관*) — ★몸 독립, 모든 공간 공유. 웹 포식이면 특히 값지다(다음 검색 중의성 해소). ⚠️owner 는 주인이 *누구인가*만 — *어떻게 검색·탐색하나*(방법·기법)는 owner 아니라 map.convention.

규칙:
- **이미 아는 것과 같으면 내지 마라**(새롭거나 교정된 것만).
- **owner vs convention 경계**: 검색·탐색 *방법/기법*(예 "흔한 이름은 전공·소속 등 비식별 고유값으로 좁혀라", "동명이인 주의", "본명이 남는 공개기록 우선")은 *주인이 누구인가*가 아니다 → 그 공간의 map.convention 으로(owner 금지). owner.habit/lexicon 은 *주인 자신*에 관한 것만(예 "이력서를 docx+pdf 쌍으로 관리"=정리습관 / "Amari=甘利俊一"=어휘매핑).
- prior_class: 동질이라 싸게 재검증되면 "structural", 의미·정체 주장이면 "semantic".
- surface: *이미 아는 라벨을 위반*하는 이질 내용을 봤다면(예 "연구 폴더인 줄 알았는데 개인 투자 메모") 그 locus/owner value 를 surface 에 적고 why.
- 확실치 않으면 비워라. JSON 으로만 응답.

이미 아는 지도(전 공간):
{known_text[:1500]}

사용자: {user_message[:300]}
AI 답변: {ai_response[:1400]}

응답 형식(빈 배열 허용):
{{"space":"mac|code:<repo>|web|book:<title>|disk:<label>",
 "map":[{{"locus":"위치(파일시스템이면 절대경로)","kind":"identity|convention|dead_branch|substrate","claim":"...","prior_class":"structural|semantic","prune_reason":"(dead_branch면)","generalizes":true}}],
 "owner":[{{"facet":"domain|identity|...","value":"...","prior_class":"semantic"}}],
 "surface":[{{"locus":"(있으면)","value":"(owner면)","why":"..."}}]}}"""

            resp = lightweight_ai_call(
                prompt=extract_prompt,
                system_prompt="포식 지도 증류기. 포식한 공간을 명명하고 일반화 가능한 공간 지식 델타만 JSON으로. 특정 항목·날 내용 금지.",
                role="background",
            )
            if not resp:
                return
            rc = resp.strip()
            if rc.startswith("```"):
                rc = rc.split("\n", 1)[-1]
                if rc.endswith("```"):
                    rc = rc[:-3]
                rc = rc.strip()
            data = json.loads(rc)
            if not isinstance(data, dict):
                return

            # 공간 = AI 가 명명(없으면 mac). 매체가 늘어도 분기 없음 — 라벨 그대로 body 키.
            body = self._normalize_space(data.get("space"), ai_response, user_message)
            prov = {"query": user_message[:120]}
            # 파일시스템 공간(code:): LLM 이 상대경로를 줄 수 있음 → 레포 루트로 정규화(freshness 정확).
            #   glob(*)·절대경로·비경로(web/book locus)는 그대로.
            repo_root = self._repo_root_path(ai_response, user_message) if body.startswith("code") else None
            def _norm_locus(loc: str) -> str:
                if (repo_root and loc and not loc.startswith("/")
                        and not loc.startswith("__") and "*" not in loc):
                    return os.path.join(repo_root, loc)
                return loc
            noted = 0
            for m in (data.get("map") or [])[:6]:
                locus, kind, claim = m.get("locus"), m.get("kind"), m.get("claim")
                if not locus or not kind or not claim:
                    continue
                locus = _norm_locus(locus)
                r = forage_memory.note_map(
                    body=body, locus=locus, kind=kind, claim=claim,
                    prior_class=m.get("prior_class") or "structural",
                    confidence=0.7, provenance=dict(prov),
                    prune_reason=m.get("prune_reason"),
                    generalizes=bool(m.get("generalizes")))
                if r.get("success"):
                    noted += 1
                    tag = " ⇧territory(빈도 결정화)" if r.get("promoted_territory") else ""
                    print(f"[포식기억] {r['action']} map[{kind}]{tag}: \"{claim[:48]}\"")
            for o in (data.get("owner") or [])[:4]:
                facet, value = o.get("facet"), o.get("value")
                if not facet or not value:
                    continue
                r = forage_memory.note_owner(
                    facet=facet, value=value,
                    prior_class=o.get("prior_class") or "semantic",
                    confidence=0.65, provenance=dict(prov))
                if r.get("success"):
                    noted += 1
                    print(f"[포식기억] {r['action']} owner[{facet}]: \"{value[:48]}\"")

            # step 5: surface — 기존 라벨 의심 표식(이질 내용 발견).
            #   위반은 폴더 라벨(map)일 수도, *주인모델*(owner)일 수도 → 둘 다 독립 표식.
            for s in (data.get("surface") or [])[:4]:
                why = s.get("why") or ""
                loc, val = s.get("locus"), s.get("value")
                marked = []
                if loc:  # 위반된 폴더 라벨
                    for x in forage_memory.recall(body=body, query=loc, limit=5).get("map", []):
                        if x["locus"] == loc:
                            forage_memory.mark_surface(entry_id=x["id"], table="forage_map", on=True)
                            marked.append(f"map#{x['id']}")
                if val:  # 위반된 주인모델 라벨 — 가장 관련된 semantic 하나(구조적은 surface 무의미)
                    for o in forage_memory.recall(body=body, query=val, limit=5).get("owner", []):
                        if o.get("prior_class") == "semantic":
                            forage_memory.mark_surface(entry_id=o["id"], table="owner_model", on=True)
                            marked.append(f"owner#{o['id']}")
                            break
                if marked:
                    print(f"[포식기억] surface 표식({','.join(marked)}): \"{why[:48]}\"")

            if noted:
                print(f"[포식기억] 증류 {noted}건: \"{user_message[:40]}\"")
        except json.JSONDecodeError:
            print("[포식기억] JSON 파싱 실패 (무시)")
        except Exception as e:
            print(f"[포식기억] 증류 실패 (무시): {e}")

    def _consciousness_clarification(self, consciousness_output: dict) -> Optional[str]:
        """의식이 needs_clarification=true로 판단했다면 사용자에게 보낼 질문을 반환.

        반환값이 None이 아니면 호출자는 실행 에이전트 호출을 건너뛰고 이 문자열을
        그대로 응답으로 노출해야 한다 (평가 루프도 안 탄다).

        Returns:
            clarification_question 문자열 또는 None
        """
        if not consciousness_output:
            return None
        if not consciousness_output.get("needs_clarification"):
            return None
        question = consciousness_output.get("clarification_question", "")
        if isinstance(question, str) and question.strip():
            return question.strip()
        # needs_clarification=true인데 질문이 비어있으면 task_framing 폴백
        task_framing = consciousness_output.get("task_framing", "")
        if isinstance(task_framing, str) and task_framing.strip():
            return task_framing.strip()
        return None

    def _apply_consciousness_to_history(self, history: list, consciousness_output: dict) -> list:
        """의식 에이전트의 판단에 따라 히스토리를 편집합니다.

        history_summary가 있으면 원본 히스토리를 요약으로 대체합니다.
        요약이 비어있으면 원본 히스토리를 그대로 반환합니다.
        """
        if not consciousness_output:
            return history

        history_summary = consciousness_output.get("history_summary", "")
        if not history_summary:
            return history

        # 원본 히스토리를 의식 에이전트의 요약으로 대체
        return [{"role": "user", "content": f"[이전 대화 요약: {history_summary}]"}]

    def _get_agent_count(self) -> int:
        """프로젝트 내 활성 에이전트 수 반환"""
        try:
            import yaml
            agents_file = self.project_path / "agents.yaml"
            if agents_file.exists():
                with open(agents_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    agents = data.get("agents", [])
                    return sum(1 for a in agents if a.get("active", True))
        except Exception:
            pass
        return 1

    def _build_execute_ibl_tool(self) -> Optional[dict]:
        """ibl_nodes.yaml에서 execute_ibl 도구 정의를 동적 생성.
        tool_loader.build_execute_ibl_tool() 공유 함수 사용.
        에이전트의 allowed_nodes 설정을 반영하여 허용된 노드만 포함.
        """
        from tool_loader import build_execute_ibl_tool
        allowed_nodes = self.config.get("allowed_nodes")
        return build_execute_ibl_tool(allowed_nodes=allowed_nodes)

    def _build_ibl_tools(self) -> list:
        """에이전트 도구 구성: IBL + 쉘 + 인지 도구

        에이전트는 두 종류의 실행 도구를 가진다:
        1. execute_ibl - 인디비즈 고유 기능 (전문 용어/지름길)
        2. run_command - 쉘. Python/Node.js 코드는 [self:write]로 파일에 쓴 뒤
           `run_command`로 실행하는 write→run 패턴을 사용한다.
           이스케이프 충돌·traceback 손실 문제가 사라진다.
        """
        import json as _json

        tools = []
        pkg_base = Path(__file__).parent.parent / "data" / "packages" / "installed" / "tools"

        # 1) IBL 도구 — ibl_nodes.yaml에서 description 동적 생성
        ibl_tool = self._build_execute_ibl_tool()
        if ibl_tool:
            tools.append(ibl_tool)

        # 2) 쉘 + 인지 도구
        lang_tools = [
            ("system_essentials", "run_command"),
            # 에이전트 인지 도구 — IBL 경유 불가 (파라미터 구조 불일치)
            ("system_essentials", "todo_write"),
            ("system_essentials", "ask_user_question"),
            ("system_essentials", "enter_plan_mode"),
            ("system_essentials", "exit_plan_mode"),
        ]
        for pkg_id, tool_name in lang_tools:
            tool_json = pkg_base / pkg_id / "tool.json"
            if tool_json.exists():
                try:
                    with open(tool_json, 'r', encoding='utf-8') as f:
                        pkg_data = _json.load(f)
                    for tool_def in pkg_data.get("tools", []):
                        if tool_def.get("name") == tool_name:
                            tools.append(tool_def)
                            break
                except Exception as e:
                    print(f"[AgentRunner] {pkg_id}/tool.json 로드 실패: {e}")

        # 3) 가이드 검색 도구 (복잡한 작업 전에 매뉴얼 찾기)
        tools.append({
            "name": "read_guide",
            "description": "가이드 파일을 읽는 도구. 검색, 투자 분석, 동영상 제작, 웹사이트 빌드 등 복잡한 작업의 단계별 가이드가 저장되어 있다. 작업 전에 이 도구로 가이드를 읽어라. 예: query='검색'이면 검색 가이드를 읽음.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색 키워드 (예: 동영상, 투자분석, 홈페이지, 음악)"
                    },
                    "read": {
                        "type": "boolean",
                        "description": "true(기본): 가이드 내용까지 반환, false: 목록만 반환"
                    }
                },
                "required": ["query"]
            }
        })

        print(f"[AgentRunner] {self.config.get('name')}: IBL + 쉘 모드 (도구 {len(tools)}개)")
        return tools

    def _get_available_tools(self) -> list:
        """에이전트가 사용할 수 있는 도구 이름 목록 반환

        IBL(도메인 특화) + 쉘 + 가이드 검색 + 인지 도구.
        Python/Node.js 코드 실행은 write→run 패턴(`[self:write]` → `run_command`)으로 한다.
        """
        return ["execute_ibl", "run_command", "read_guide",
                "todo_write", "ask_user_question", "enter_plan_mode", "exit_plan_mode"]

    def augment_with_ibl_references(self, user_message: str) -> str:
        """사용자 메시지에 IBL 참조 용례를 주입 (RAG)

        유사한 과거 IBL 용례를 검색하여 AI가 참고할 수 있도록 메시지 앞에 추가.
        실패 시 원본 메시지 그대로 반환 (graceful degradation).
        """
        try:
            from ibl_usage_rag import IBLUsageRAG
            rag = IBLUsageRAG()
            allowed_nodes = self.config.get("allowed_nodes")
            if allowed_nodes:
                from ibl_access import resolve_allowed_nodes
                allowed_set = resolve_allowed_nodes(allowed_nodes)
            else:
                allowed_set = None
            return rag.inject_references(user_message, allowed_set)
        except Exception:
            return user_message

    # ============================================================
    # Reflex 임계값 — 단계 0 결과의 top_score가 이 값 이상이면
    # 무의식(경량 AI) 호출을 건너뛰고 즉시 EXECUTE.
    # 분기는 호출 측(_process_channel_message)이 책임진다.
    # 0.88 → 0.85: 한계 사례(0.85~0.88)도 학습된 패턴이면 EXECUTE로 흘림.
    # ============================================================
    REFLEX_SCORE_THRESHOLD = 0.85

    # 의식 토글 OFF 일 때 분류기(경량 LLM) 대신 쓰는 세션 리셋 키워드 — 고정밀로 추림
    # (unconscious_prompt.md 의 SESSION_RESET 트리거에서). 리셋은 파괴적이므로 보수적:
    # 애매한 단어(맨 "리셋"/"초기화" 단독 — 액션 명령과 충돌)는 일부러 제외, 애매하면 EXECUTE.
    _RESET_PHRASES = (
        "새세션", "세션시작", "세션끝", "세션초기화", "세션리셋", "세션그만",
        "처음부터다시", "깨끗하게시작", "여기까지하자",
        "그만하자", "다른이야기하자", "새작업으로넘어가",
    )

    def _is_reset_keyword(self, message: str) -> bool:
        """의식 OFF 에서 분류기를 스킵하므로, 세션 리셋만 비-LLM 키워드로 대체 탐지(토큰 0)."""
        low = (message or "").lower().replace(" ", "")
        return any(p in low for p in self._RESET_PHRASES)

    def _tag_override(self, message: str) -> Optional[str]:
        """명령에 박힌 명시 태그로 판정을 강제한다 — 사용자 결정이므로 Reflex·분류를 모두 이긴다.
        #think → THINK, #execute → EXECUTE (대소문자 무시). 둘 다면 #think 우선(보수적)."""
        low = (message or "").lower()
        if "#think" in low:
            return "THINK"
        if "#execute" in low:
            return "EXECUTE"
        return None

    def _decide_request_type(self, message: str, hippocampus_score: float,
                             top_code: str) -> tuple:
        """요청 판정 단일 진입점 — 명시 태그(무조건) → Reflex(해마 고확신) → 무의식 분류.

        4개 호출처(시스템AI×2·프로젝트 에이전트·채널)가 같은 결정을 쓰도록 중앙화.
        print 로 남기는 판정 로그는 episode_logger 가 정규식으로 읽어 episode_summary 에
        unconscious_decision 으로 적재하므로 형식([무의식] 분류: / [연상→실행])을 보존한다.

        Returns: (request_type, reflex_hint)  # reflex_hint 는 Reflex EXECUTE 일 때만 top_code
        """
        tag = self._tag_override(message)
        if tag:
            # 태그 강제 — episode 추출이 잡도록 "[무의식] 분류: X" 형식 유지(+강제 표기)
            print(f"[무의식] 분류: {tag} (태그 #{tag.lower()} 강제 — Reflex·분류 무시)")
            return tag, None
        if (hippocampus_score or 0) >= self.REFLEX_SCORE_THRESHOLD and top_code:
            print(f"[연상→실행] Reflex EXECUTE (score={hippocampus_score:.3f})")
            return "EXECUTE", top_code
        # 의식 토글 OFF → 무의식 분류(THINK 판정)를 건너뛰고 바로 EXECUTE. 반사는 위에서 이미 처리됨.
        # SESSION_RESET 만 비-LLM 키워드로 살림(분류기가 잡던 걸 OFF 에서 대체). 확정 2026-06-30.
        try:
            from model_resolver import consciousness_enabled
            _conscious = consciousness_enabled()
        except Exception:
            _conscious = True
        if not _conscious:
            if self._is_reset_keyword(message):
                print("[무의식] 분류: SESSION_RESET (키워드 · 의식 OFF)")
                return "SESSION_RESET", None
            print("[무의식] 분류: EXECUTE (의식 OFF — THINK 경로 차단)")
            return "EXECUTE", None
        request_type = self._classify_request(message)
        print(f"[무의식] 분류: {request_type}")
        return request_type, None

    def _classify_request(self, user_message: str,
                          execution_memory: str = "") -> str:
        """사용자 요청을 SESSION_RESET / EXECUTE / THINK로 분류한다.

        무의식 에이전트 — 경량 AI 호출만 담당. Reflex 판정은
        호출 측에서 단계 0(_build_execution_memory)의 top_score로 미리 분기한다.

        execution_memory는 받지만 분류 입력에 합치지 않는다.
        unconscious_prompt.md 규칙: "현재 메시지만으로 판단한다."
        연상기억을 합치면 짧은 명령도 입력이 부풀어 모델이 단순 EXECUTE 판단을 못함.
        (인터페이스 호환을 위해 파라미터는 유지)

        Returns:
            "SESSION_RESET" / "EXECUTE" / "THINK"
        """
        try:
            from consciousness_agent import lightweight_ai_call, get_unconscious_prompt

            system_prompt = get_unconscious_prompt()
            response = lightweight_ai_call(user_message, system_prompt=system_prompt)

            if response is None:
                return "THINK"  # AI 미준비 시 안전하게 판단형으로

            result = response.strip().upper()
            # SESSION_RESET 우선 검사 (EXECUTE 키워드가 들어있는 경우와 충돌 방지)
            if "SESSION_RESET" in result or "RESET" == result:
                return "SESSION_RESET"
            return "EXECUTE" if "EXECUTE" in result else "THINK"

        except Exception as e:
            self._log(f"[무의식] 분류 실패: {e}")
            return "THINK"  # 실패 시 안전하게 판단형으로

    # ============================================================
    # Goal 평가 루프 — 의식 에이전트의 달성 기준 기반 자동 평가
    # ============================================================

    def _extract_achievement_criteria(self, consciousness_output: dict,
                                       tool_results_str: str = "") -> Optional[str]:
        """의식 에이전트 출력에서 달성 기준을 추출한다.

        1차: achievement_criteria 필드 (별도 필드)
        2차: task_framing에서 "달성 기준:" 이후 텍스트 (하위 호환)
        3차: 도구 실행 결과에 박힌 [ACHIEVEMENT_CRITERIA:node:action] ... [/ACHIEVEMENT_CRITERIA]
             마커 — 액션 메타데이터 자동 보강 (ibl_actions.yaml의 achievement_criteria 필드)
        """
        # 1차: consciousness_output의 별도 필드
        if consciousness_output:
            criteria = consciousness_output.get("achievement_criteria", "")
            if isinstance(criteria, list):
                criteria = ", ".join(str(c) for c in criteria if c)
            if criteria and isinstance(criteria, str) and criteria.strip():
                return criteria.strip()

            # 2차: task_framing에서 추출 (하위 호환)
            task_framing = consciousness_output.get("task_framing", "")
            if "달성 기준:" in task_framing:
                return task_framing.split("달성 기준:")[-1].strip().rstrip(".")
            if "달성기준:" in task_framing:
                return task_framing.split("달성기준:")[-1].strip().rstrip(".")

        # 3차: 도구 실행 결과에 박힌 액션 메타 마커 (achievement_criteria 마커 등)
        if tool_results_str:
            marker_pat = re.compile(
                r"\[ACHIEVEMENT_CRITERIA:([^\]]+)\]\s*(.+?)\s*\[/ACHIEVEMENT_CRITERIA\]",
                re.DOTALL,
            )
            matches = marker_pat.findall(tool_results_str)
            if matches:
                # 여러 액션이 연달아 실행되면 모든 criteria를 묶음
                parts = [f"[{action}] {body.strip()}" for action, body in matches]
                return "\n".join(parts)

        return None

    def _collect_created_files(self, response: str,
                                tool_calls: Optional[List[Dict[str, Any]]] = None) -> str:
        """생성/수정된 파일 경로를 찾아 내용을 읽는다.

        1차: tool_calls(있으면)에서 Write/Edit/MultiEdit/NotebookEdit 같은 파일 변경 도구의
             input.file_path 등을 직접 수집. IBL execute_ibl `[self:write]` 같은 케이스도
             input.params.path 등에서 추출. 응답 텍스트에 안 보여도 누락 안 됨.
        2차: 응답 텍스트에서 절대 경로 정규식 fallback — 1차에서 못 찾은 경로 보강용.

        Args:
            response: 에이전트 최종 응답 텍스트
            tool_calls: `{name, input, result, ...}` 리스트 (선택)
        """
        import os

        paths_seen: List[str] = []
        seen_set: set = set()

        def _add(path: str):
            if path and path not in seen_set and path.startswith("/"):
                seen_set.add(path)
                paths_seen.append(path)

        # 1차: tool_calls에서 직접 수집
        if tool_calls:
            for entry in tool_calls:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name") or entry.get("tool_name") or ""
                inp = entry.get("input") or {}
                if not isinstance(inp, dict):
                    continue

                # 표준 Write/Edit 류
                if name in _FILE_WRITE_TOOL_NAMES or name.endswith("/Write") or name.endswith("/Edit"):
                    for key in _FILE_PATH_INPUT_KEYS:
                        v = inp.get(key)
                        if isinstance(v, str):
                            _add(v)

                # IBL self:write 같은 케이스: execute_ibl({node:"self", action:"write", params:{path:...}})
                if name in ("execute_ibl", "mcp__indiebizos__execute_ibl"):
                    params = inp.get("params") or {}
                    if isinstance(params, dict):
                        for key in _FILE_PATH_INPUT_KEYS:
                            v = params.get(key)
                            if isinstance(v, str):
                                _add(v)

        # 2차: 응답 텍스트에서 절대 경로 fallback (1차에서 못 잡은 경우 보강)
        path_pattern = re.compile(r'(/[^\s"\'<>]+\.\w{1,10})')
        for p in path_pattern.findall(response or ""):
            _add(p)

        files_content = []
        for path in paths_seen:
            if os.path.isfile(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if len(content) > 10000:
                        content = content[:10000] + "\n\n... (10000자 초과, 생략됨)"
                    files_content.append(f"### {os.path.basename(path)} ({path})\n```\n{content}\n```")
                except Exception:
                    pass

        return "\n\n".join(files_content) if files_content else ""

    _VISUAL_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".webp": "image/webp", ".gif": "image/gif"}

    def _collect_visual_artifacts(self, response: str,
                                   tool_calls: Optional[List[Dict[str, Any]]] = None,
                                   max_images: int = 3) -> List[Dict[str, str]]:
        """생성된 시각 산출물(이미지)을 멀티모달 평가용으로 수집한다 (G 루프 보편 백스톱).

        _collect_created_files는 파일을 UTF-8 텍스트로 읽어 이미지를 조용히 버린다 —
        이게 평가자가 픽셀을 못 보던 물리적 원인. 여기서는 이미지 경로를 따로 모아
        base64로 인코딩해 평가자(경량 비전 모델)가 직접 보게 한다.

        수집원: tool_calls의 input(파일 경로 키)·result(산출 경로, 예 image_path)·응답 텍스트.
        반환: [{"base64","media_type","_path"}], 최신순 max_images개.
        """
        import os, base64 as _b64
        cand: List[str] = []
        seen: set = set()

        def _add(p):
            if (isinstance(p, str) and p.startswith("/")
                    and os.path.splitext(p)[1].lower() in self._VISUAL_EXTS
                    and p not in seen):
                seen.add(p)
                cand.append(p)

        img_re = re.compile(r'(/[^\s"\'<>]+\.(?:png|jpe?g|webp|gif))', re.IGNORECASE)

        if tool_calls:
            for entry in tool_calls:
                if not isinstance(entry, dict):
                    continue
                inp = entry.get("input") or {}
                if isinstance(inp, dict):
                    for key in _FILE_PATH_INPUT_KEYS:
                        _add(inp.get(key))
                    params = inp.get("params")
                    if isinstance(params, dict):
                        for key in _FILE_PATH_INPUT_KEYS:
                            _add(params.get(key))
                res = entry.get("result")
                if isinstance(res, str):
                    for m in img_re.findall(res):
                        _add(m)

        for m in img_re.findall(response or ""):
            _add(m)

        # 실존+크기 검증을 max_images 슬라이스 *전에* 수행 — 그래야 상한이 진짜
        # 이미지에만 쓰인다. (상대경로 'slides/s.png' 안의 '/s.png' 조각 같은 가짜
        # 후보가 창을 갉아먹어 실제 이미지가 덜 첨부되던 것을 막는다.)
        valid = [p for p in cand
                 if os.path.isfile(p) and os.path.getsize(p) <= 6 * 1024 * 1024]
        # 최신순 max_images개 (마지막 산출물이 보통 최종본)
        chosen = valid[-max_images:] if len(valid) > max_images else valid
        artifacts: List[Dict[str, str]] = []
        for path in chosen:
            try:
                with open(path, "rb") as f:
                    b64 = _b64.b64encode(f.read()).decode("utf-8")
                mt = self._VISUAL_EXTS.get(os.path.splitext(path)[1].lower(), "image/png")
                artifacts.append({"base64": b64, "media_type": mt, "_path": path})
            except Exception:
                pass
        if len(valid) > len(artifacts) and artifacts:
            self._log(f"[GoalEval] 시각 산출물 {len(valid)}개 중 {len(artifacts)}개만 평가 첨부(상한)")
        return artifacts

    _evaluator_prompt_cache: str = ""

    @classmethod
    def _load_evaluator_prompt(cls) -> str:
        """평가 에이전트 프롬프트 파일을 로드한다 (캐시). 시스템 구조 문서 포함."""
        if not cls._evaluator_prompt_cache:
            base = Path(__file__).parent.parent / "data"
            prompt_path = base / "common_prompts" / "evaluator_prompt.md"
            try:
                cls._evaluator_prompt_cache = prompt_path.read_text(encoding='utf-8')
            except FileNotFoundError:
                cls._evaluator_prompt_cache = "달성 기준의 모든 항목을 엄격히 평가하라."
            # 시스템 구조 문서(정체성 코어)만 항상 주입 — 디렉토리/파일 트리는
            # codebase_map 가이드로 분리(get_system_structure_core)
            try:
                from prompt_builder import get_system_structure_core
                structure = get_system_structure_core()
            except Exception:
                structure = ""
            if structure:
                cls._evaluator_prompt_cache += f"\n\n<system_structure>\n{structure}\n</system_structure>"
            # IBL 카탈로그(12_ibl_only, ~15K) 주입 폐지 (2026-06-28) — 평가는 IBL 체계 전문이
            # 아니라 criteria + action_ledger(실제 호출 사실) + capability_focus(추천 도구)로 판정한다.
            # evaluator_prompt.md 어디도 IBL 카탈로그를 참조하지 않아 dead weight 였다.
        return cls._evaluator_prompt_cache

    def _evaluate_achievement(self, user_message: str, criteria: str,
                               response: str, created_files: str,
                               consciousness_output: dict = None,
                               tool_results_str: str = "",
                               action_ledger: str = "",
                               execution_memory: str = "",
                               visual_artifacts: list = None) -> tuple:
        """평가 AI로 달성 기준 충족 여부를 판단한다.

        의식 에이전트의 출력(task_framing, capability_focus)과 action_ledger
        (실제 호출된 액션의 사실 기록)를 활용하여 결과물뿐 아니라
        도구 활용의 적절성까지 평가한다.

        Returns:
            (achieved: bool, feedback: str, severity: int)
            severity: 0=N/A(achieved), 1=경미, 2=중대, 3=치명
        """
        evaluator_system_prompt = self._load_evaluator_prompt()

        # 메시지에는 평가 대상 데이터만
        prompt = (
            f"## 사용자 요청\n{user_message}\n\n"
            f"## 달성 기준\n{criteria}\n\n"
        )

        # 검증용 액션 원장 — 기준 직후에 배치(인접성). 에이전트의 '서술'이 아니라
        # 실제 호출 로그에서 추출한 '사실'. 안 한 일의 부재를 평가자가 볼 수 있게 한다.
        if action_ledger:
            prompt += (
                "## 실제 실행된 액션 원장 (전수 · 검증 기준)\n"
                "아래는 에이전트가 *실제로 호출한* 액션의 전수 목록이다 — 에이전트의 서술이 아니라 "
                "도구 호출 로그에서 추출한 사실. 달성 기준이 특정 액션을 요구하면(예: 특정 파일 읽기, "
                "grep/검색, 특정 도구 실행), **그 액션이 이 목록에 실제로 있는지로 판정하라.** "
                "목록에 없으면 그 단계는 *수행되지 않은 것*이다 — 에이전트 응답이 '했다'고 말해도 "
                "이 원장에 없으면 안 한 것으로 간주하라.\n"
                f"{action_ledger}\n\n"
            )

        # 의식 에이전트의 메타 판단을 평가 맥락으로 제공
        if consciousness_output:
            task_framing = consciousness_output.get("task_framing", "")
            if task_framing:
                prompt += f"## 문제 정의 (의식 에이전트 판단)\n{task_framing}\n\n"

            history_summary = consciousness_output.get("history_summary", "")
            if history_summary:
                prompt += f"## 이전 대화 맥락\n{history_summary}\n\n"

            # self_awareness 출력 필드 폐지 (2026-06-28) — task_framing 으로 흡수.
            cap_focus = consciousness_output.get("capability_focus", {})
            if isinstance(cap_focus, dict):
                hint = cap_focus.get("hint", "")
                actions = cap_focus.get("highlight_actions", [])
                if hint or actions:
                    prompt += "## 도구 활용 맥락\n"
                    if actions:
                        prompt += f"- 추천된 도구: {', '.join(actions)}\n"
                    if hint:
                        prompt += f"- 접근 방향: {hint}\n"
                    prompt += "\n"

            # world_state 출력 필드 폐지 (2026-06-28) — task_framing 으로 흡수.

        # 연상기억(execution_memory=해마 IBL 레퍼런스) 주입 폐지 (2026-06-28) — 평가는
        # action_ledger(실제 호출 사실)와 capability_focus(추천 도구)로 도구 적절성을 판정한다.
        # 과거 코드 사례 블록은 "기준 충족 여부" 판단에 불필요했다.

        if tool_results_str:
            prompt += f"## 도구 실행 결과\n{tool_results_str}\n\n"

        prompt += f"## 에이전트 응답\n{response[:8000]}\n\n"

        if created_files:
            prompt += f"## 생성된 파일 내용\n{created_files}\n\n"

        if visual_artifacts:
            import os as _os
            names = ", ".join(_os.path.basename(a.get("_path", "")) for a in visual_artifacts)
            prompt += (
                f"## 시각 산출물 검수 ({len(visual_artifacts)}개 첨부: {names})\n"
                "아래에 **실제 생성된 이미지**가 첨부되어 있다. 텍스트 설명이 아니라 이미지를 "
                "직접 보고 달성 기준 충족을 판단하라 — 레이아웃·가독성·의도 표현·잘림/깨짐/빈 영역 등 "
                "실제 시각 품질을 확인할 것.\n\n"
            )

        prompt += "위 정보를 바탕으로 평가하세요. 도구 실행 결과가 있으면 실제로 작업이 수행되었는지 확인하세요."

        # 평가 입력 가시화 — 평가자에게 충분한 컨텍스트가 전달되는지 진단.
        # 어제 208번 같은 오판(도구 결과가 평가자에 부족하게 전달되어 "상상 보고" 판정) 검출용.
        _tool_results_info = f"{len(tool_results_str)}자" if tool_results_str else "없음"
        _created_files_info = f"{len(created_files)}자" if created_files else "없음"
        _ledger_info = f"{action_ledger.count(chr(10)) + 1}줄" if action_ledger else "없음"
        self._log(
            f"[GoalEval] 평가 입력: prompt={len(prompt)}자, "
            f"criteria={len(criteria)}자, response={len(response)}자, "
            f"tool_results={_tool_results_info}, action_ledger={_ledger_info}, "
            f"created_files={_created_files_info}"
        )

        try:
            # 평가기 = 의식 모델과 동일(system_ai_config). 평가 프롬프트의 정교한 루브릭(원장
            # 교차검증·열린문제 노력선·표면 vs 실질)을 경량 flash-lite 가 실행하지 못해 거짓합격을
            # 달성 기준 평가는 모델 기어 '평가' 축(role=evaluate)으로 해소된다 —
            # 기어 프리셋상 평가 축은 경량 티어(과거 opus 고정 → 경량 개선). system_ai_call 은
            # role 만 다를 뿐 lightweight_ai_call 과 같은 계약(prompt/system_prompt/images).
            from consciousness_agent import system_ai_call

            eval_images = None
            if visual_artifacts:
                eval_images = [{"base64": a["base64"], "media_type": a["media_type"]}
                               for a in visual_artifacts]
            eval_response = system_ai_call(prompt, system_prompt=evaluator_system_prompt,
                                           images=eval_images, role="evaluate")
            if eval_response is None or not eval_response.strip():
                self._log("[GoalEval] AI 응답 없음 (API 오류 등), 통과 처리")
                return True, "평가 스킵 (AI 응답 없음)", 0

            self._log(f"[GoalEval] 평가 응답: {eval_response[:200]}")

            lines = eval_response.strip().split('\n')
            first_line = lines[0].strip().upper()
            achieved = "ACHIEVED" in first_line and "NOT" not in first_line

            # Failure Severity 파싱 (NOT_ACHIEVED일 때)
            severity = 0
            if not achieved and len(lines) > 1:
                second_line = lines[1].strip().upper()
                if "SEVERITY:" in second_line:
                    try:
                        severity = int(second_line.split("SEVERITY:")[-1].strip()[0])
                        severity = max(1, min(3, severity))
                    except (ValueError, IndexError):
                        severity = 2  # 파싱 실패 시 중간값
                else:
                    severity = 2  # severity 미표기 시 중간값

            return achieved, eval_response, severity

        except Exception as e:
            self._log(f"[GoalEval] 평가 오류: {e}")
            return True, f"평가 오류 (통과 처리): {e}", 0

    def _run_goal_evaluation_loop(self, user_message: str, criteria: str,
                                   initial_response: str, history: list,
                                   consciousness_output: dict = None,
                                   max_rounds: int = 2,
                                   tool_results: list = None,
                                   tool_calls: list = None,
                                   execution_memory: str = "") -> str:
        """달성 기준 기반 평가 루프.

        Args:
            user_message: 사용자 원래 요청
            criteria: 달성 기준
            initial_response: 에이전트 첫 응답
            history: 대화 히스토리
            consciousness_output: 의식 에이전트 출력 (task_framing, capability_focus 등)
            max_rounds: 최대 평가 횟수 (기본 2)
            tool_results: 도구 실행 결과 문자열 리스트 (legacy — 이름·인풋 없음)
            tool_calls: 도구 호출 구조화 이력 `{name,input,result,is_error}` 리스트.
                tool_results보다 우선 사용된다. 둘 다 있으면 tool_calls 사용.
                평가자가 시퀀스 자체(어떤 도구를 어떤 순서로)를 판단 근거로 쓸 수 있다.
            execution_memory: 실행기억 (도구/사례/implementation)

        Returns:
            최종 응답 텍스트
        """
        import time as _time
        from thread_context import set_goal_eval_outcome, clear_goal_eval_outcome
        # 이번 평가의 판정을 초기화 — 증류 게이트가 직전 메시지의 stale 판정을 보지 않도록.
        clear_goal_eval_outcome()
        response = initial_response

        # 도구 호출 trace를 직렬화 — 시퀀스 자체는 어떤 경우에도 보존됨.
        # tool_calls가 우선; 없으면 tool_results(legacy) 사용.
        trace_source: list = tool_calls if tool_calls else (tool_results or [])
        tool_results_str = serialize_tool_trace(trace_source)
        # 검증용 액션 원장 — execute_ibl code에서 [node:action]+대상을 전수 추출.
        # serialize_tool_trace가 못 보여주던 '실제 호출된 IBL 액션'을 평가자에게 노출한다.
        action_ledger = build_action_ledger(trace_source)
        # _collect_created_files용: tool_calls가 있으면 그쪽도 활용.
        _trace_dicts = tool_calls if tool_calls else None

        # ★거짓 '허위보고' 버그 근본 수정: 재실행 호출을 self.ai.get_last_tool_calls()로만
        # 읽었는데 gemini provider는 _last_tool_calls를 안 채워 빈 결과 → action_ledger가 초기
        # 호출에 멈춤 → "재실행했는데 원장에 없으니 조작"이라는 거짓 양성(루프가 영원히 통과 못 함).
        # thread_context는 실행기(execute_tool/ibl_engine)가 채우므로 provider와 무관하게 모든
        # 라운드를 담는 진실 소스 → 여기서 델타를 떠 원장에 누적한다.
        try:
            from thread_context import get_tool_calls as _get_tc
        except Exception:
            _get_tc = None

        def _tc_calls():
            """thread_context의 execute_tool 레벨 호출만 (ibl_engine 레벨 ibl: 중복 제외)."""
            if not _get_tc:
                return []
            try:
                return [c for c in (_get_tc() or [])
                        if not str(c.get("tool_name", "")).startswith("ibl:")]
            except Exception:
                return []

        # 초기 trace가 비면(예: gemini 비-streaming 경로는 provider 호출이력을 안 줌) thread_context로 시드.
        if not trace_source:
            _seed = _tc_calls()
            if _seed:
                trace_source = list(_seed)
                tool_results_str = serialize_tool_trace(trace_source)
                action_ledger = build_action_ledger(trace_source)
                _trace_dicts = trace_source
        _tc_seen = len(_tc_calls())

        for round_num in range(1, max_rounds + 1):
            self._log(f"[GoalEval] 라운드 {round_num}/{max_rounds} 평가 시작")
            eval_start = _time.time()

            # 생성된 파일 수집 (tool_calls의 file_path를 우선 활용)
            created_files = self._collect_created_files(response, tool_calls=_trace_dicts)
            # 시각 산출물(이미지) 수집 — 평가자가 픽셀을 직접 보게 (G 루프 보편 백스톱)
            visual_artifacts = self._collect_visual_artifacts(response, tool_calls=_trace_dicts)

            # 달성 여부 평가 (criteria + action_ledger(실제 호출 사실) + capability_focus + 시각 산출물)
            # execution_memory(해마)는 평가에 불필요해 미전달 (2026-06-28).
            achieved, feedback, severity = self._evaluate_achievement(
                user_message, criteria, response, created_files,
                consciousness_output=consciousness_output,
                tool_results_str=tool_results_str,
                action_ledger=action_ledger,
                visual_artifacts=visual_artifacts,
            )

            eval_time = _time.time() - eval_start
            severity_label = {0: "-", 1: "LOW", 2: "MED", 3: "HIGH"}.get(severity, "?")
            self._log(
                f"[GoalEval] 라운드 {round_num}: "
                f"{'ACHIEVED' if achieved else 'NOT_ACHIEVED'} "
                f"(severity={severity_label}, {eval_time:.1f}초)"
            )

            if achieved:
                set_goal_eval_outcome(True, 0)
                return response

            # 마지막 라운드면 그냥 반환 — 미달성으로 끝났음을 증류 게이트에 알린다.
            if round_num >= max_rounds:
                set_goal_eval_outcome(False, severity)
                self._log(f"[GoalEval] 라운드 소진, 현재 응답 반환 (미달성 → 증류 제외)")
                return response

            # 피드백을 주입하여 재실행 — severity에 따라 전략 분기
            self._log(f"[GoalEval] 재실행 시작 (severity={severity_label}, 피드백 주입)")

            if severity >= 3:
                # 치명적: 전략 전환 유도
                retry_directive = (
                    "⚠️ 이전 접근 방식이 근본적으로 잘못되었습니다. "
                    "동일한 방법을 반복하지 마세요.\n"
                    "아래 피드백의 '대안 전략'을 참고하여 완전히 다른 접근법으로 시도하세요. "
                    "이전 결과물은 폐기하고 처음부터 다시 작업하세요."
                )
            elif severity >= 2:
                # 중대: 접근법 부분 수정
                retry_directive = (
                    "핵심적인 부분이 미흡합니다. "
                    "이전 작업의 기본 틀은 유지하되, 접근 방식을 수정하세요. "
                    "특히 피드백에서 지적한 도구 활용이나 핵심 기준을 중점적으로 보완하세요."
                )
            else:
                # 경미: 기존 방식 보완
                retry_directive = (
                    "이전 작업 결과를 최대한 활용하고, 부족한 부분만 보완하세요."
                )

            feedback_message = (
                f"[평가 피드백] 이전 응답이 달성 기준을 충족하지 못했습니다. "
                f"(심각도: {severity_label})\n\n"
                f"달성 기준: {criteria}\n\n"
                f"부족한 점:\n{feedback}\n\n"
                f"{retry_directive}\n\n"
                f"⚠️ 중요: 이 재실행은 비대화형 모드입니다. "
                f"ask_user_question을 사용하지 마세요. 사용자에게 질문할 수 없습니다. "
                f"현재 가진 정보만으로 최선의 결과를 만드세요."
            )

            # 피드백을 히스토리에 추가하여 재실행
            retry_history = history + [
                {"role": "assistant", "content": response[:8000]},
                {"role": "user", "content": feedback_message}
            ]

            try:
                retry_response = self.ai.process_message_with_history(
                    message_content=feedback_message,
                    history=retry_history,
                    task_id=f"goal_retry_{round_num}"
                )
                # 재실행 결과가 비어있으면 (503 등) 이전 응답 유지
                if retry_response and retry_response.strip():
                    response = retry_response
                    self._log(f"[GoalEval] 재실행 완료: {len(response)}자")
                    # ★재실행이 만든 새 도구 호출을 누적해 ledger·trace 를 갱신한다.
                    # 안 하면 다음 라운드 평가가 라운드 1의 stale 원장으로 새 응답을
                    # 판정 → 실제로 크롤링/검색을 해놓고도 "원장에 없으니 안 했다 = 조작"
                    # 이라는 거짓 양성이 난다(재실행 루프가 영원히 통과 못 함).
                    # 소스: thread_context 델타(provider 독립) 우선, 비면 provider
                    # get_last_tool_calls 폴백(claude_code MCP 경로 대비). '델타 우선,
                    # 없으면 폴백'이라 둘 다 채우는 provider여도 이중계상되지 않는다.
                    _all_tc = _tc_calls()
                    _new_calls = _all_tc[_tc_seen:]
                    _tc_seen = len(_all_tc)
                    if not _new_calls:
                        try:
                            _new_calls = self.ai.get_last_tool_calls() or []
                        except Exception:
                            _new_calls = []
                    if _new_calls:
                        if trace_source and isinstance(trace_source[0], dict):
                            trace_source = list(trace_source) + list(_new_calls)
                        else:
                            trace_source = list(_new_calls)
                        tool_results_str = serialize_tool_trace(trace_source)
                        action_ledger = build_action_ledger(trace_source)
                        _trace_dicts = trace_source
                else:
                    self._log(f"[GoalEval] 재실행 결과 비어있음, 이전 응답 유지 ({len(response)}자)")
            except Exception as e:
                self._log(f"[GoalEval] 재실행 실패: {e}")
                return initial_response

        return response
