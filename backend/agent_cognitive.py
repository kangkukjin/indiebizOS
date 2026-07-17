"""
agent_cognitive.py - 인지/AI 초기화 믹스인 (합성 지점)
IndieBiz OS Core

AgentRunner의 인지 관련 메서드를 분리한 Mixin 클래스.
2026-07-17 모듈화(1500줄 규칙): 2455줄 단일 파일을 응집 클러스터로 분할 —
  cognitive_trace.py          도구 trace 직렬화·액션 원장·자기반성 메시지 (모듈 함수)
  cognitive_recall.py         0단계 연상 회상 (해마+심층+포식+디스크골격)
  cognitive_consciousness.py  의식·무의식 분류·framing 캐시·SESSION_RESET
  cognitive_distill.py        턴 종료 후 증류 (심층+포식+_after_response)
  cognitive_eval.py           Goal 평가 루프 (달성기준·산출물 수집·평가자)
이 파일에는 코어(AI 초기화·프롬프트 빌드·IBL 도구 구성)와 믹스인 합성만 남는다.
★기존 import 경로 유지: 외부는 계속 `from agent_cognitive import ...` 로 가져간다
(아래 재수출). 새 코드는 정의 모듈에서 직접 import 해도 된다.
"""

import json
from pathlib import Path
from typing import Optional

from ai_agent import AIAgent

# ── 재수출 (기존 import 경로 호환) ──────────────────────────────
# agent_pipeline·test_evaluator_trace 등이 agent_cognitive 에서 가져가던 이름들.
from cognitive_trace import (  # noqa: F401
    serialize_tool_trace,
    build_action_ledger,
    build_reflection_message,
    _brief_input,
    _normalize_tool_entry,
    _merge_keywords,
    _unwrap_payload,
    _result_evidence,
    _FILE_PATH_INPUT_KEYS,
    _FILE_WRITE_TOOL_NAMES,
)
from cognitive_consciousness import (  # noqa: F401
    SESSION_RESET_RESPONSE,
    handle_session_reset,
    framing_cache_get,
    framing_cache_set,
    clear_framing_cache,
    CognitiveConsciousnessMixin,
)
from cognitive_recall import CognitiveRecallMixin  # noqa: F401
from cognitive_distill import CognitiveDistillMixin  # noqa: F401
from cognitive_eval import CognitiveEvalMixin  # noqa: F401


class AgentCognitiveMixin(
    CognitiveRecallMixin,
    CognitiveConsciousnessMixin,
    CognitiveDistillMixin,
    CognitiveEvalMixin,
):
    """AgentRunner의 인지/AI 초기화 관련 메서드 모음.

    무의식 에이전트(분류), 의식 에이전트(메타 판단), 평가 에이전트(달성 기준 검증),
    IBL 도구 구성, 실행기억 생성 등 3단 인지 아키텍처의 핵심 로직을 담당한다.
    회상/의식/증류/평가는 부모 믹스인(cognitive_*.py)에 있고, 여기엔 코어만.
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
                                      execution_memory: str = "", extra_role: str = "",
                                      allowed_set=None) -> tuple:
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
            extra_role=extra_role,
            allowed_set=allowed_set,
        )

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
