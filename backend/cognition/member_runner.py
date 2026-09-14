"""공통 인지 러너의 회원 표면. 도구·프롬프트 공급원만 제한한다."""
import json

from agent_runner import AgentRunner


class MemberRunner(AgentRunner):
    def _sync_execution_gear(self):
        # 턴마다 새 러너가 회원용 API 모델을 이미 해소했다. 주인 CLI 기어로 재전환하지 않는다.
        return

    def _resolve_execution_config(self, ai_config, agent_id):
        configured = self.config.get("_member_ai") or ai_config
        result = super()._resolve_execution_config(configured, agent_id)
        if str(result.get("provider", "")).replace("-", "_") in {"codex", "codex_cli", "claude_code", "claudecode"}:
            # 주인이 이미 구성한 API 보조 모델을 사용한다. CLI는 허브 네이티브 도구를 우회 실행한다.
            from model_resolver import resolve
            api = resolve("background")
            result = {**result, **{k: api[k] for k in ("provider", "model", "api_key") if k in api}}
        return result

    def _build_ibl_tools(self):
        tool = self._build_execute_ibl_tool()
        return [tool] if tool else []

    def _get_available_tools(self):
        return ["execute_ibl"]

    def _build_agent_prompt_split(self, role, consciousness_output=None, execution_memory=""):
        from ibl_access import build_environment
        stable = role + "\n\n" + build_environment(
            allowed_nodes=self.config.get("allowed_nodes"), expose_idioms=False)
        dynamic = execution_memory
        definitions = self.config.get("_member_sentences", "")
        if definitions:
            dynamic += "\n<member_definitions>\n" + definitions[:16000] + "\n</member_definitions>"
        if consciousness_output:
            dynamic += "\n<task>" + json.dumps(consciousness_output, ensure_ascii=False) + "</task>"
        return stable, dynamic

    def _build_system_prompt(self, role, consciousness_output=None, execution_memory=""):
        return "\n".join(self._build_agent_prompt_split(role, consciousness_output, execution_memory))

    def _init_ai(self):
        super()._init_ai()
        self.ai._custom_execute_tool = self._member_tool
        import principal
        self.ai.agent_id = principal.current().key()
        if self.ai._provider:
            self.ai._provider.agent_id = self.ai.agent_id

    def _member_tool(self, tool_name, tool_input, work_dir=None, agent_id=None, **kwargs):
        if tool_name != "execute_ibl":
            return json.dumps({"success": False, "error_type": "permission",
                               "error": "회원에게 발행되지 않은 도구입니다"}, ensure_ascii=False)
        from system_tools_ibl import _execute_ibl_unified
        import principal
        import member_runtime
        # 파일·resume·행위자 인자는 모델이 허브 경로/신원을 주입하는 경로가 되므로 받지 않는다.
        definitions = getattr(self, "config", {}).get("_member_sentences", "")
        if definitions.strip():
            from ibl_parser import parse
            # 로컬 문장은 정의만 앞에 붙인다. 등록 파일의 최상위 부작용을 매 호출마다 실행하지 않는다.
            try:
                if any(not step.get("_def") for step in parse(definitions)):
                    definitions = ""
            except Exception:
                definitions = ""
        return _execute_ibl_unified({"code": definitions + "\n" + str(tool_input.get("code", ""))},
            str(self.project_path), agent_id=principal.current().key(),
            cancel_check=member_runtime.current()["cancel"].is_set)

    def _classify_request(self, user_message, execution_memory=""):
        from consciousness_agent import call_oneshot_provider
        result = call_oneshot_provider(self.ai._provider, user_message,
            system_prompt="요청 분류: 단순 실행은 EXECUTE, 계획이 필요하면 THINK. 한 단어만 출력.")
        return "THINK" if "THINK" in str(result) else "EXECUTE"

    def _run_consciousness(self, user_message, history, execution_memory="", repair=False, revision=None):
        from consciousness_agent import ConsciousnessAgent
        agent = ConsciousnessAgent.__new__(ConsciousnessAgent)
        agent._prompt_mtime = None
        # 주인용 싱글턴의 프롬프트/사전을 회원과 공유하지 않는다.
        agent._provider = self.ai._provider.oneshot_view()
        agent._prompt_path = None
        agent._prompt = ("회원의 요청에 대한 작업 규정자다. JSON으로 task_framing, approach, achievement_criteria, "
                         "assumptions를 반환한다. achievement_criteria는 요청의 완료 조건이다. "
                         "허브 하네스 변경은 허용되지 않는다.\n" + self._build_system_prompt(self._load_role()))
        agent._supervisor_prompt = agent._prompt
        return agent.process(user_message=user_message, history=history,
            associative_memory=execution_memory, world_pulse="", agent_name="회원도우미",
            agent_role=self._load_role(), agent_notes="", available_tools=["execute_ibl"],
            repair=False, revision=revision)

    def _build_execution_memory(self, message, **kwargs):
        # 로컬 SQLite 회상은 세션 입구에서 받아 회원 문맥으로만 전달한다.
        return self.config.get("_member_memory", ""), 0.0, ""

    def select_local_memory(self, message):
        """회원 원문만 선별한다. 주인 기억을 검색하거나 허브 증류 큐에 적재하지 않는다."""
        from memory_evidence import durable_source_units, select_units
        from consciousness_agent import call_oneshot_provider
        units = durable_source_units(message)
        if not any(u["eligible"] for u in units):
            return []
        raw = call_oneshot_provider(self.ai._provider, json.dumps(units, ensure_ascii=False),
            system_prompt='미래 협업에 반복해서 필요한 사용자 자신의 사실·지속 선호·확정 결정만 선택한다. '
            '인용·보고서·타인/AI 의견·일시적 사실·요청은 제외한다. eligible=true 중에서만 고른다. '
            '원문을 재작성하지 않고 {"source_ids":[정수]} JSON만 반환한다. 없으면 빈 목록이다.', role="member_memory")
        try:
            selected = select_units(json.loads(raw or "{}").get("source_ids"), units)
            return [u["text"] for u in selected if u["eligible"]]
        except (ValueError, TypeError, AttributeError):
            return []
