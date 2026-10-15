"""Codex의 추론·구독 인증은 중앙에서, 모든 도구 실행은 회원 관문에서."""
import json

from member_cli import MemberCliScope
from providers.codex import CodexProvider, _codex_home
from providers.cli_provider import CliSubprocessProvider


# 모델 카탈로그가 feature flag보다 우선하여 native 도구를 다시 켤 수 있다.
# 모델/추론강도/컨텍스트 속성만 계승하고 도구 선택자는 회원 계약으로 덮어쓴다.
_MODEL_FIELDS = {
    'slug', 'display_name', 'description', 'default_reasoning_level',
    'supported_reasoning_levels', 'shell_type', 'visibility', 'supported_in_api',
    'priority', 'support_verbosity', 'default_verbosity', 'truncation_policy',
    'context_window', 'max_context_window', 'effective_context_window_percent',
    'comp_hash', 'input_modalities', 'supports_image_detail_original',
    'supports_reasoning_summary_parameter', 'supports_reasoning_effort_updates',
    'default_reasoning_summary', 'use_responses_lite',
}


class MemberCodexProvider(MemberCliScope, CodexProvider):
    TOOL_POLICY = ''
    MCP_SERVER_NAME = 'member'
    MCP_TOOL_PREFIX = 'mcp__member__'
    DISABLED_FEATURES = (
        *CodexProvider.CODEX_DISABLED_FEATURES, 'shell_tool', 'unified_exec',
        'multi_agent', 'multi_agent_v2', 'code_mode', 'code_mode_only',
        'code_mode_host', 'shell_snapshot', 'view_image', 'skill_search',
        'memories', 'hooks', 'workspace_dependencies', 'tool_suggest',
        'default_mode_request_user_input', 'js_repl', 'sleep_tool',
    )

    def _write_model_catalog(self):
        slug, _ = self._model_and_effort()
        try:
            cache = json.loads((_codex_home() / 'models_cache.json').read_text(encoding='utf-8'))
            entry = next(m for m in cache['models'] if m.get('slug') == slug)
            model = {k: v for k, v in entry.items() if k in _MODEL_FIELDS}
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
            # 알 수 없는 모델의 native 기본값으로 되돌아가지 않는다.
            raise RuntimeError('중앙 Codex의 모델 목록을 갱신하고 회원 모델을 다시 선택하세요.') from exc
        model.update(
            base_instructions='회원 요청을 처리하세요. 실행은 제공된 회원 MCP 도구만 사용하세요.',
            apply_patch_tool_type=None, tool_mode='direct', multi_agent_version=None,
            experimental_supported_tools=[], node_repl_disabled=True,
            include_skills_usage_instructions=False, include_plugin_usage_instructions=False,
            include_apps_usage_instructions=False, supports_search_tool=False,
        )
        path = self._member_root / 'models.json'
        path.write_text(json.dumps({'models': [model]}, ensure_ascii=False), encoding='utf-8')
        path.chmod(0o600)
        return path

    def _build_env(self):
        inherited = super()._build_env()
        env = {k: v for k, v in inherited.items() if k in {
            'PATH', 'LANG', 'LC_ALL', 'SystemRoot', 'SYSTEMROOT',
            'OPENAI_API_KEY', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'}}
        home = self._member_root / 'home'
        codex_home = home / '.codex'
        codex_home.mkdir(parents=True, mode=0o700, exist_ok=True)
        auth = _codex_home() / 'auth.json'
        if not self._effective_key and auth.is_file():
            # 토큰 갱신은 중앙 인증과 공유하되 설정·MCP·스킬·과거 대화는 가져오지 않는다.
            (codex_home / 'auth.json').symlink_to(auth.resolve())
        env.update(HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(codex_home),
                   TMPDIR=str(self._member_root), TEMP=str(self._member_root), TMP=str(self._member_root),
                   INDIEBIZ_MEMBER_MCP_TOKEN=self._member_bridge.secret)
        return env

    def _mcp_bridge_acquire(self):
        return 'member'  # 중앙 기본 MCP를 시작하지 않는다.

    def _build_prompt_with_history(self, message, history):
        # 시스템 지침은 model_instructions_file로 전달하며 주인 repair 지침을 가져오지 않는다.
        return CliSubprocessProvider._build_prompt_with_history(self, message, history)

    def _build_command(self, mcp_config_path=None, system_prompt_file=None, **kwargs):
        slug, effort = self._model_and_effort()
        command = [self._binary_path, 'exec', '--json', '--skip-git-repo-check',
                   '--ignore-user-config', '--ignore-rules', '--strict-config',
                   '--sandbox', 'read-only', '-m', slug]
        settings = {
            'approval_policy': 'never', 'web_search': 'disabled', 'notify': [],
            'model_catalog_json': str(self._write_model_catalog()),
            'model_instructions_file': system_prompt_file or self._write_system_prompt_file(),
            'tools.experimental_request_user_input.enabled': False,
            'tools.update_plan.enabled': False,
        }
        settings.update({f'features.{name}': False for name in self.DISABLED_FEATURES})
        if effort:
            settings['model_reasoning_effort'] = effort
        if self._member_bridge.tools:
            from completion_lease import MCP_CLIENT_TIMEOUT_S
            settings.update({
                'mcp_servers.member.url': f'http://127.0.0.1:{self._member_bridge.server.server_port}/mcp',
                'mcp_servers.member.bearer_token_env_var': 'INDIEBIZ_MEMBER_MCP_TOKEN',
                'mcp_servers.member.required': True,
                'mcp_servers.member.tool_timeout_sec': MCP_CLIENT_TIMEOUT_S,
                'mcp_servers.member.enabled_tools': list(self._member_bridge.tools),
            })
            # 실행 승인은 회원 실행부가 소유한다. 중앙 CLI의 대화형 승인은 사용하지 않는다.
            for name in self._member_bridge.tools:
                settings[f'mcp_servers.member.tools.{name}.approval_mode'] = 'approve'
        for key, value in settings.items():
            command += ['-c', f'{key}={json.dumps(value, ensure_ascii=False)}']
        # private CODEX_HOME의 rollout으로 기존 라운드·usage 계측을 이어 쓴다.
        # 턴이 끝나면 MemberCliScope가 auth 링크와 rollout을 함께 회수한다.
        return command + ['-']
