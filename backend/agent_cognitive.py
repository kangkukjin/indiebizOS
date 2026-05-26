"""
agent_cognitive.py - 인지/AI 초기화 믹스인
IndieBiz OS Core

AgentRunner의 인지 관련 메서드를 분리한 Mixin 클래스.
무의식/의식/평가 에이전트 파이프라인, IBL 도구 구성, 실행기억 등
AI 인지 아키텍처에 해당하는 로직을 포함한다.
"""

import re
from pathlib import Path
from typing import Optional, List

from ai_agent import AIAgent


# ============================================================
# SESSION_RESET 핸들러 (모듈 레벨 — call site에서 직접 호출)
# ============================================================

SESSION_RESET_RESPONSE = "새 세션을 시작했습니다. 무엇을 도와드릴까요?"


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

            self.ai = AIAgent(
                ai_config=ai_config,
                system_prompt=system_prompt,
                agent_name=agent_name,
                agent_id=agent_id,
                project_path=str(self.project_path),
                tools=tools
            )

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

    def _build_execution_memory(self, user_message: str) -> tuple:
        """연상기억 생성 — 실행기억(해마) + 관련기억(심층 메모리)

        파이프라인의 모든 에이전트(무의식/의식/실행/평가)가 공유하는 통합 기억.
        사용자 명령 당 해마 검색은 단 1회. 호출 측은 반환된 top_score를 그대로 사용하여
        Reflex 분기, 경험 증류 판정 등에서 추가 검색을 피한다.

        Returns:
            (xml: str, top_score: float, top_code: str)
            - xml: <execution_memory> + <related_memory> 결합된 문자열 (없으면 "")
            - top_score: 해마 최고 점수 (없으면 0.0)
            - top_code: 해마 최고 점수 항목의 ibl_code (없으면 "")
        """
        try:
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

            if result:
                parts = []
                if "execution_memory" in result:
                    parts.append("실행기억")
                if "related_memory" in result:
                    parts.append("관련기억")
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

            results = memory_db.search(
                project_path=project_path,
                agent_id=agent_id,
                query=user_message,
                limit=3,
            )
            if not results:
                return ""

            # 전문 조회 (preview는 100자 잘림이므로)
            items = []
            for r in results:
                full = memory_db.read(project_path, agent_id, r["id"])
                if full:
                    cat = full.get("category", "")
                    kw = full.get("keywords", "")
                    content = full.get("content", "")
                    meta = f' category="{cat}"' if cat else ""
                    meta += f' keywords="{kw}"' if kw else ""
                    items.append(f"  <memory{meta}>{content}</memory>")

            if not items:
                return ""

            xml = (
                '<related_memory note="심층 메모리에서 연상된 관련 기억입니다. 참고용.">\n'
                + "\n".join(items)
                + "\n</related_memory>"
            )
            print(f"[연상:관련기억] {len(items)}건 검색됨: \"{user_message[:40]}\"")
            print(f"[연상:관련기억] 내용:\n{xml}")
            return xml

        except Exception as e:
            print(f"[연상:관련기억] 검색 실패 (무시): {e}")
            return ""

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

            result = agent.process(
                user_message=user_message,
                history=history,
                associative_memory=execution_memory,  # 연상기억(해마+심층메모리) 묶음
                guide_list=get_guide_list(user_message),
                world_pulse=get_world_pulse_text(),
                agent_name=agent_name,
                agent_role=agent_role,
                agent_notes=agent_notes,
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
[{{"content": "...", "keywords": "k1,k2", "category": "사용자선호|작업기록|의사결정|중요날짜"}}]
정보가 없으면 빈 배열 [] 반환.

사용자: {user_message[:500]}
AI: {ai_response[:500]}"""

            result = lightweight_ai_call(
                prompt=extract_prompt,
                system_prompt="사실 정보만 추출하라. JSON 배열로만 응답."
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

            for fact in facts[:5]:  # 최대 5개 조각
                content = fact.get("content", "").strip()
                keywords = fact.get("keywords", "").strip()
                category = fact.get("category", "").strip()
                if not content:
                    continue

                # 2단계: 기존 심층 메모리에서 유사 항목 검색
                existing = memory_db.search(
                    project_path=project_path,
                    agent_id=agent_id,
                    query=keywords or content,
                    limit=3,
                )

                if existing:
                    # 유사 항목 있음 → 경량 AI로 중복 판단
                    # 가장 유사한 항목의 전문 조회
                    top = memory_db.read(project_path, agent_id, existing[0]["id"])
                    if top:
                        dedup_prompt = (
                            f"기존 기억: {top['content'][:200]}\n"
                            f"새 정보: {content[:200]}\n"
                            "SAME(동일) / UPDATE(보충수정) / NEW(다른정보) 중 하나만 답하라."
                        )
                        judgment = lightweight_ai_call(
                            prompt=dedup_prompt,
                            system_prompt="SAME, UPDATE, NEW 중 하나만 답하라."
                        )
                        if judgment:
                            j = judgment.strip().upper()
                            if "SAME" in j:
                                # 동일 → used_at만 갱신
                                memory_db.update(project_path, agent_id, top["id"])
                                print(f"[심층메모리] SAME 스킵: \"{content[:50]}\"")
                                continue
                            elif "UPDATE" in j:
                                # 보충 → 기존 항목 업데이트
                                merged = f"{top['content']}\n[보충] {content}"
                                merged_kw = top.get("keywords", "")
                                if keywords:
                                    merged_kw = f"{merged_kw},{keywords}" if merged_kw else keywords
                                memory_db.update(
                                    project_path, agent_id, top["id"],
                                    content=merged, keywords=merged_kw,
                                )
                                updated_count += 1
                                print(f"[심층메모리] UPDATE: \"{content[:50]}\" → 기존 ID {top['id']}")
                                continue
                            # NEW → 아래에서 새로 저장

                # 유사 항목 없음 또는 NEW → 새로 저장
                memory_db.save(
                    project_path=project_path,
                    agent_id=agent_id,
                    content=content,
                    keywords=keywords,
                    category=category,
                )
                saved_count += 1
                print(f"[심층메모리] NEW [{category}]: \"{content[:50]}\" (kw: {keywords})")

            if saved_count or updated_count:
                print(f"[심층메모리] 저장 {saved_count}건, 업데이트 {updated_count}건: "
                      f"\"{user_message[:40]}\"")

        except json.JSONDecodeError:
            print(f"[심층메모리] JSON 파싱 실패 (무시)")
        except Exception as e:
            print(f"[심층메모리] 실패 (무시): {e}")

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

        # 3차: 도구 실행 결과에 박힌 액션 메타 마커 (lecture_pipeline 등)
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

    def _collect_created_files(self, response: str) -> str:
        """에이전트 응답에서 생성된 파일 경로를 찾아 내용을 읽는다."""
        import os

        # 절대 경로 패턴 매칭
        path_pattern = re.compile(r'(/[^\s"\'<>]+\.\w{1,10})')
        paths = path_pattern.findall(response)

        files_content = []
        for path in paths:
            if os.path.isfile(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if len(content) > 10000:
                        content = content[:10000] + "\n\n... (10000자 초과, 생략됨)"
                    files_content.append(f"### {os.path.basename(path)}\n```\n{content}\n```")
                except Exception:
                    pass

        return "\n\n".join(files_content) if files_content else ""

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
            # 시스템 구조 문서 항상 주입
            structure_path = base / "system_docs" / "system_structure.md"
            if structure_path.exists():
                structure = structure_path.read_text(encoding='utf-8')
                cls._evaluator_prompt_cache += f"\n\n<system_structure>\n{structure}\n</system_structure>"
            # IBL 환경 프롬프트 주입 — 평가 에이전트도 IBL 체계를 알아야 올바른 평가를 할 수 있다
            ibl_only_path = base / "common_prompts" / "fragments" / "12_ibl_only.md"
            if ibl_only_path.exists():
                ibl_only = ibl_only_path.read_text(encoding='utf-8')
                cls._evaluator_prompt_cache += f"\n\n{ibl_only}"
        return cls._evaluator_prompt_cache

    def _evaluate_achievement(self, user_message: str, criteria: str,
                               response: str, created_files: str,
                               consciousness_output: dict = None,
                               tool_results_str: str = "",
                               execution_memory: str = "") -> tuple:
        """평가 AI로 달성 기준 충족 여부를 판단한다.

        의식 에이전트의 출력(self_awareness, capability_focus, world_state)과
        실행기억(사용 가능한 도구, 코드 사례, implementation)을 활용하여
        결과물뿐 아니라 도구 활용의 적절성까지 평가한다.

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

        # 의식 에이전트의 메타 판단을 평가 맥락으로 제공
        if consciousness_output:
            task_framing = consciousness_output.get("task_framing", "")
            if task_framing:
                prompt += f"## 문제 정의 (의식 에이전트 판단)\n{task_framing}\n\n"

            history_summary = consciousness_output.get("history_summary", "")
            if history_summary:
                prompt += f"## 이전 대화 맥락\n{history_summary}\n\n"

            self_awareness = consciousness_output.get("self_awareness", "")
            if self_awareness:
                prompt += f"## 에이전트 자기 인식 (의식 에이전트 판단)\n{self_awareness}\n\n"

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

            world_state = consciousness_output.get("world_state", "")
            if world_state:
                prompt += f"## 세계 상태\n{world_state}\n\n"

        if execution_memory:
            # <execution_memory>(해마) + <related_memory>(심층메모리) 묶음 — 자식 태그가 self-describing
            prompt += f"## 연상기억\n{execution_memory}\n\n"

        if tool_results_str:
            prompt += f"## 도구 실행 결과\n{tool_results_str}\n\n"

        prompt += f"## 에이전트 응답\n{response[:8000]}\n\n"

        if created_files:
            prompt += f"## 생성된 파일 내용\n{created_files}\n\n"

        prompt += "위 정보를 바탕으로 평가하세요. 도구 실행 결과가 있으면 실제로 작업이 수행되었는지 확인하세요."

        # 평가 입력 가시화 — 평가자에게 충분한 컨텍스트가 전달되는지 진단.
        # 어제 208번 같은 오판(도구 결과가 평가자에 부족하게 전달되어 "상상 보고" 판정) 검출용.
        _tool_results_info = f"{len(tool_results_str)}자" if tool_results_str else "없음"
        _created_files_info = f"{len(created_files)}자" if created_files else "없음"
        self._log(
            f"[GoalEval] 평가 입력: prompt={len(prompt)}자, "
            f"criteria={len(criteria)}자, response={len(response)}자, "
            f"tool_results={_tool_results_info}, created_files={_created_files_info}"
        )

        try:
            from consciousness_agent import lightweight_ai_call

            eval_response = lightweight_ai_call(prompt, system_prompt=evaluator_system_prompt)
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
                                   execution_memory: str = "") -> str:
        """달성 기준 기반 평가 루프.

        Args:
            user_message: 사용자 원래 요청
            criteria: 달성 기준
            initial_response: 에이전트 첫 응답
            history: 대화 히스토리
            consciousness_output: 의식 에이전트 출력 (self_awareness, capability_focus 등)
            max_rounds: 최대 평가 횟수 (기본 2)
            tool_results: 도구 실행 이력 리스트
            execution_memory: 실행기억 (도구/사례/implementation)

        Returns:
            최종 응답 텍스트
        """
        import time as _time
        response = initial_response

        # 도구 실행 이력을 문자열로 변환
        tool_results_str = ""
        if tool_results:
            tool_entries = []
            for tr in tool_results:
                if isinstance(tr, str) and tr.strip():
                    # 너무 긴 결과는 truncate
                    entry = tr[:2000] if len(tr) > 2000 else tr
                    tool_entries.append(entry)
            if tool_entries:
                tool_results_str = "\n---\n".join(tool_entries[-5:])  # 최근 5개

        for round_num in range(1, max_rounds + 1):
            self._log(f"[GoalEval] 라운드 {round_num}/{max_rounds} 평가 시작")
            eval_start = _time.time()

            # 생성된 파일 수집
            created_files = self._collect_created_files(response)

            # 달성 여부 평가 (의식 에이전트의 자기 인식 + 도구 실행 이력 + 실행기억)
            achieved, feedback, severity = self._evaluate_achievement(
                user_message, criteria, response, created_files,
                consciousness_output=consciousness_output,
                tool_results_str=tool_results_str,
                execution_memory=execution_memory,
            )

            eval_time = _time.time() - eval_start
            severity_label = {0: "-", 1: "LOW", 2: "MED", 3: "HIGH"}.get(severity, "?")
            self._log(
                f"[GoalEval] 라운드 {round_num}: "
                f"{'ACHIEVED' if achieved else 'NOT_ACHIEVED'} "
                f"(severity={severity_label}, {eval_time:.1f}초)"
            )

            if achieved:
                return response

            # 마지막 라운드면 그냥 반환
            if round_num >= max_rounds:
                self._log(f"[GoalEval] 라운드 소진, 현재 응답 반환")
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
                else:
                    self._log(f"[GoalEval] 재실행 결과 비어있음, 이전 응답 유지 ({len(response)}자)")
            except Exception as e:
                self._log(f"[GoalEval] 재실행 실패: {e}")
                return initial_response

        return response
