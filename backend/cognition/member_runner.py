"""공통 인지 러너의 회원 표면. 도구·프롬프트 공급원만 제한한다."""
import json

from agent_runner import AgentRunner


class MemberRunner(AgentRunner):
    def _sync_execution_gear(self):
        # 세션은 턴마다 폐기된다. 초기화 때 중앙 실행 기어를 이미 해소했다.
        return

    def _build_ibl_tools(self):
        tool = self._build_execute_ibl_tool()
        if tool:
            properties = tool['input_schema']['properties']
            tool['input_schema']['properties'] = {k: v for k, v in properties.items() if k in {'code', 'edition', 'inputs', 'check', 'resume', 'reuse', 'describe', 'read_result'}}
            properties['code']['description'] = '현재 회원 카탈로그에 있는 액션만 실행한다. 예: [sense:search]{source:"ddg",query:"AI news",limit:5}. describe는 계약 조회이며 code를 함께 주면 조회 성공 후 한 번 실행한다.'
        tools = [tool] if tool else []
        tools.append({"name": "ask_user_question", "description": "작업에 필요한 정보가 빠졌을 때 클라이언트에게 질문하고 현재 턴을 끝낸다. 다음 답변은 같은 작업에서 이어진다.",
                      "input_schema": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}})
        import member_runtime
        if (member_runtime.current() or {}).get("shell_available", False):
            tools.append({"name": "run_command", "description": "회원의 선택한 PC 작업 폴더에서 명령 실행. 로컬 승인 필요. 허브에서는 실행하지 않는다.",
                      "input_schema": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}})
        if (member_runtime.current() or {}).get("javascript_available", False):
            tools.append({"name": "run_javascript", "description": "회원 브라우저에서 JavaScript를 실행해 입력 데이터를 계산/변환한다. input 인자, return 값. 네트워크·DOM·OS 파일 접근 없음. 파일은 IBL로 읽고 결과를 IBL로 저장한다. 회원 승인 필요.",
                          "input_schema": {"type": "object", "properties": {"code": {"type": "string"}, "input": {}}, "required": ["code"]}})
        from member_local_tools import definitions
        tools.extend(definitions(member_runtime.current() or {}))
        return tools

    def _get_available_tools(self):
        import member_runtime
        from member_local_tools import definitions
        return [t["name"] for t in definitions(member_runtime.current() or {})] + ["execute_ibl", "ask_user_question"] + (["run_command"] if (member_runtime.current() or {}).get("shell_available", False) else []) + (["run_javascript"] if (member_runtime.current() or {}).get("javascript_available", False) else [])

    def _build_agent_prompt_split(self, role, consciousness_output=None, execution_memory=""):
        from ibl_access import build_environment
        environment = build_environment(allowed_nodes=self.config.get("allowed_nodes"), expose_idioms=False, compact=True)
        # 주인용 교재의 미공개 낱말·허브 경로 예제를 회원에게 실행 예제로 소개하지 않는다.
        catalogue = '<ibl_actions>' + environment.split('<ibl_actions>', 1)[1] if '<ibl_actions>' in environment else ''
        from runtime_utils import get_base_path
        compact = (get_base_path() / "data/common_prompts/fragments/12_ibl_compact.md").read_text()
        grammar = compact.split("<!-- MEMBER_GRAMMAR:START -->", 1)[1].split("<!-- MEMBER_GRAMMAR:END -->", 1)[0]
        stable = role + "\n\n" + grammar + "\n" + catalogue
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
            self._record_model('execution', self.ai.provider_name, self.ai.model)

    def _record_model(self, role, provider, model):
        import member_runtime
        state = member_runtime.current()
        if state is not None:
            item = {'role': role, 'provider': provider, 'model': model}
            if item not in state.setdefault('models', []):
                state['models'].append(item)

    def _role_provider(self, role):
        from model_resolver import resolve
        from providers import create_initialized_provider
        import principal
        descriptor = resolve(role)
        self._record_model(role, descriptor['provider'], descriptor['model'])
        return create_initialized_provider(descriptor['provider'], api_key=descriptor.get('api_key', ''),
            model=descriptor['model'], system_prompt='', project_path=str(self.project_path),
            agent_id=principal.current().key(), isolated_session=True, no_tools=True)


    def _member_tool(self, tool_name, tool_input, work_dir=None, agent_id=None, **kwargs):
        import member_activity
        import member_runtime
        import re
        state = member_runtime.current() or {}
        base = state.get('audit_base')
        action_id = None
        if base:
            label = tool_name
            if tool_name == 'execute_ibl':
                label += ' (문장에 포함: ' + ', '.join(dict.fromkeys(re.findall(r'\[([a-z_]+:[a-z_]+)\]', str(tool_input.get('code', ''))))) + ')'
            action_id = member_activity.start_action(base, state['task_id'], label.strip())
        status = 'failed'
        try:
            raw = MemberRunner._execute_member_tool(self, tool_name, tool_input, work_dir, agent_id, **kwargs)
            try:
                value = json.loads(raw) if isinstance(raw, str) else raw
            except (ValueError, TypeError):
                value = {}
            status = 'failed' if isinstance(value, dict) and (value.get('success') is False or value.get('error')) else 'completed'
            return raw
        finally:
            if action_id is not None:
                member_activity.finish_action(base, action_id, status)

    def _execute_member_tool(self, tool_name, tool_input, work_dir=None, agent_id=None, **kwargs):
        from member_local_tools import execute, NAMES
        if tool_name in NAMES:
            result = execute(tool_name, tool_input)
            if tool_name == 'computer':
                from image_envelopes import harvest_images
                if result.get('b64'):
                    result['image_data'] = {'b64': result.pop('b64'), 'media_type': result.get('media_type', 'image/png')}
                text, images = harvest_images(json.dumps(result, ensure_ascii=False))
                return {'content': text,
                        'images': [{'base64': i['b64'], 'media_type': i.get('media_type', 'image/png')} for i in images]}
            return json.dumps(result, ensure_ascii=False)
        if tool_name == "ask_user_question":
            import member_runtime
            question = str(tool_input.get("question") or "").strip()
            if not question or len(question) > 4000:
                return json.dumps({"success": False, "error": "질문은 1~4000자여야 합니다"})
            member_runtime.current()["input_required"] = question
            return json.dumps({"success": True, "input_required": question}, ensure_ascii=False)
        if tool_name == "run_javascript":
            import member_runtime
            from member_bridge import request
            state = member_runtime.current() or {}
            if not state.get("local_task_id") or not state.get("javascript_available"):
                return json.dumps({"success": False, "error_type": "permission", "error": "브라우저 작업 공간이 필요합니다"})
            return json.dumps(request({"op": "javascript", "code": str(tool_input.get("code", "")), "input": tool_input.get("input")}, timeout=130), ensure_ascii=False)
        if tool_name == "run_command":
            from member_bridge import request
            import member_runtime
            state = member_runtime.current() or {}
            if not state.get("local_task_id") or not state.get("shell_available"):
                return json.dumps({"success": False, "error_type": "permission", "error": "PC 작업 공간이 연결된 작업에서만 명령을 실행합니다"})
            timeout = min(300, max(1, int(tool_input.get("timeout") or 120)))
            return json.dumps(request({"op": "shell", "cmd": str(tool_input.get("command", "")),
                                       "timeout": timeout}, timeout=timeout + 125), ensure_ascii=False)
        if tool_name != "execute_ibl":
            return json.dumps({"success": False, "error_type": "permission",
                               "error": "회원에게 발행되지 않은 도구입니다"}, ensure_ascii=False)
        from system_tools_ibl import _execute_ibl_unified
        import principal
        import member_runtime
        if tool_input.get('read_result') is not None or tool_input.get('describe') is not None:
            if tool_input.get('read_result') is not None and (
                    tool_input.get('code') or tool_input.get('pipeline') or tool_input.get('describe') is not None):
                return json.dumps({'success': False, 'executed': False,
                                   'error': 'read_result는 code·pipeline·describe와 함께 사용할 수 없습니다'})
            try:
                from model_result_view import read_result, describe_actions
                if tool_input.get('read_result') is not None:
                    value = read_result(tool_input['read_result'])
                else:
                    from member_profile import visible
                    from ibl_registry import load_nodes_installed
                    names = tool_input['describe']
                    if not isinstance(names, list) or not 1 <= len(names) <= 6:
                        raise ValueError('액션 1~6개를 조회하세요')
                    nodes = load_nodes_installed().get('nodes', {})
                    for name in names:
                        node, action = name.split(':', 1)
                        cfg = nodes.get(node, {}).get('actions', {}).get(action, {})
                        if not visible(node, action, cfg):
                            raise ValueError('외부사용자에게 공개되지 않은 액션입니다')
                    if not tool_input.get('code'):
                        value = describe_actions(names, self.config.get('allowed_nodes'), edition=tool_input.get('edition', 2))
                if not tool_input.get('code'):
                    return json.dumps(value, ensure_ascii=False)
            except (ValueError, KeyError, TypeError, OSError):
                return json.dumps({'success': False, 'executed': False, 'error': '현재 회원 턴에서 해당 계약/결과를 조회할 수 없습니다'}, ensure_ascii=False)
        # Model authoring uses the same language boundary as the owner. No paths,
        # actor claims or owner libraries are accepted from the tool payload.
        from ibl_edition import authoring_request
        from ibl_member_library import library
        request = authoring_request({k: v for k, v in tool_input.items()
                                     if k in {"code", "edition", "inputs", "declared_inputs", "check", "resume", "files", "describe"}})
        if len(json.dumps(request, ensure_ascii=False).encode()) > 4 * 1024 * 1024:
            return json.dumps({"success": False, "error": "입력은 합계 4MB 이하여야 합니다"}, ensure_ascii=False)
        source = getattr(self, "config", {}).get("_member_sentences", "")
        sources = getattr(self, "config", {}).get("_member_libraries", [source])
        sources = [item for item in sources if item]
        with library(sources):
            return _execute_ibl_unified(request, str(self.project_path),
                agent_id=principal.current().key(), cancel_check=member_runtime.current()["cancel"].is_set)

    def _classify_request(self, user_message, execution_memory=""):
        from consciousness_agent import call_oneshot_provider
        result = call_oneshot_provider(self._role_provider("classify"), user_message,
            system_prompt="요청 분류: 단순 실행은 EXECUTE, 계획이 필요하면 THINK. 한 단어만 출력.")
        return "THINK" if "THINK" in str(result) else "EXECUTE"

    @staticmethod
    def _validate_member_framing(value):
        """회원 계획도 공통 실행기가 읽는 자료형을 지킨다. 잘못된 형은 모델이 정정한다."""
        if not isinstance(value, dict) or not isinstance(value.get('task_framing'), str):
            raise ValueError('task_framing 문자열을 포함한 JSON 객체가 필요합니다')
        for key in ('approach', 'history_summary', 'imagined_ibl'):
            if value.get(key) is not None and not isinstance(value[key], str):
                raise ValueError(f'{key}는 문자열이어야 합니다')
        criteria = value.get('achievement_criteria')
        if criteria is not None and not (isinstance(criteria, str) or
                isinstance(criteria, list) and all(isinstance(x, str) for x in criteria)):
            raise ValueError('achievement_criteria는 문자열 또는 문자열 목록이어야 합니다')
        if value.get('criteria') is not None and not (isinstance(value['criteria'], list) and
                all(isinstance(x, dict) and isinstance(x.get('text'), str) for x in value['criteria'])):
            raise ValueError('criteria는 text 문자열을 갖는 객체 목록이어야 합니다')
        for key in ('capability_focus', 'ibl_focus'):
            focus = value.get(key)
            if focus is None:
                continue
            if not isinstance(focus, dict):
                raise ValueError(f'{key}는 highlight_actions와 hint를 갖는 객체여야 합니다')
            if focus.get('hint') is not None and not isinstance(focus['hint'], str):
                raise ValueError(f'{key}.hint는 문자열이어야 합니다')
            actions = focus.get('highlight_actions')
            if actions is not None and not (isinstance(actions, list) and all(isinstance(x, str) for x in actions)):
                raise ValueError(f'{key}.highlight_actions는 문자열 목록이어야 합니다')

    def _run_consciousness(self, user_message, history, execution_memory="", repair=False, revision=None):
        from consciousness_agent import ConsciousnessAgent
        agent = ConsciousnessAgent.__new__(ConsciousnessAgent)
        agent._prompt_mtime = None
        # 주인용 싱글턴의 프롬프트/사전을 회원과 공유하지 않는다.
        agent._provider = self._role_provider("consciousness")
        agent._prompt_path = None
        agent._prompt = ("회원의 요청에 대한 작업 규정자다. JSON으로 task_framing, approach, achievement_criteria, "
                         "assumptions를 반환한다. task_framing·approach·achievement_criteria는 문자열, assumptions는 문자열 목록이다. "
                         "achievement_criteria는 요청의 완료 조건이다. 선택 필드 imagined_ibl·history_summary는 문자열, "
                         "capability_focus는 {highlight_actions:[문자열],hint:문자열} 객체다. "
                         "허브 하네스 변경은 허용되지 않는다.\n" + self._build_system_prompt(self._load_role()))
        agent._supervisor_prompt = agent._prompt
        return agent.process(user_message=user_message, history=history,
            associative_memory=execution_memory, world_pulse="", agent_name="회원도우미",
            agent_role=self._load_role(), agent_notes="", available_tools=self._get_available_tools(),
            repair=False, revision=revision, validate_framing=self._validate_member_framing)

    def _associate(self, message, **kwargs):
        # 로컬 SQLite 회상은 세션 입구에서 받아 회원 문맥으로만 전달한다 — 주인 기억(1상)은 돌지 않고,
        # 회원 턴도 공통 흐름의 분류 뒤 제시 기록을 확정한다.
        from associative_recall import stub
        return stub(self.config.get("_member_memory", ""))(self, message, **kwargs)

    def select_local_memory(self, message):
        """회원 원문만 선별한다. 주인 기억을 검색하거나 허브 증류 큐에 적재하지 않는다."""
        from memory_evidence import durable_source_units, select_units
        from consciousness_agent import call_oneshot_provider
        units = durable_source_units(message)
        if not any(u["eligible"] for u in units):
            return []
        raw = call_oneshot_provider(self._role_provider("background"), json.dumps(units, ensure_ascii=False),
            system_prompt='미래 협업에 반복해서 필요한 사용자 자신의 사실·지속 선호·확정 결정만 선택한다. '
            '인용·보고서·타인/AI 의견·일시적 사실·요청은 제외한다. eligible=true 중에서만 고른다. '
            '원문을 재작성하지 않고 {"source_ids":[정수]} JSON만 반환한다. 없으면 빈 목록이다.', role="member_memory")
        try:
            selected = select_units(json.loads(raw or "{}").get("source_ids"), units)
            return [u["text"] for u in selected if u["eligible"]]
        except (ValueError, TypeError, AttributeError):
            return []
