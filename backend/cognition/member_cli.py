"""중앙 CLI 기어를 회원 도구 관문에 연결한다. 주인 MCP/내장 도구는 공급하지 않는다."""
import contextvars
import json
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from providers.claude_code import ClaudeCodeProvider


class MemberToolBridge:
    """턴 수명의 loopback MCP. 신원은 헤더가 아니라 생성한 턴 문맥에서만 온다."""
    def __init__(self, provider, execute_tool, cancel_check):
        self.context = contextvars.copy_context()
        self.provider = provider
        self.execute_tool = execute_tool
        self.cancel_check = cancel_check
        self.secret = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.closed = False
        self.images = getattr(provider, '_member_images', [])
        self.tools = {t['name']: t for t in provider.tools} if execute_tool and not getattr(provider, 'no_tools', False) else {}
        if self.images:
            self.tools['read_attached_image'] = {'description': '첨부 이미지 하나를 번호로 읽는다. 서버 파일을 읽지 않는다.',
                'input_schema': {'type': 'object', 'properties': {'index': {'type': 'integer'}}, 'required': ['index']}}
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_error(405)

            def do_POST(self):
                if self.path != '/mcp' or self.headers.get('Authorization') != 'Bearer ' + bridge.secret:
                    self.send_error(403)
                    return
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 8 * 1024 * 1024:
                    self.send_error(413)
                    return
                try:
                    message = json.loads(self.rfile.read(length))
                    with bridge.lock:
                        result = bridge.context.copy().run(bridge.dispatch, message)
                    body = json.dumps(result, ensure_ascii=False).encode() if result else b''
                    self.send_response(200 if result else 202)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (ValueError, TypeError):
                    self.send_error(400)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def dispatch(self, message):
        if 'id' not in message:
            return None
        method, params = message.get('method'), message.get('params') or {}
        result = {}
        if method == 'initialize':
            result = {'protocolVersion': params.get('protocolVersion', '2024-11-05'),
                      'capabilities': {'tools': {}}, 'serverInfo': {'name': 'member', 'version': '1'}}
        elif method == 'tools/list':
            result = {'tools': [{'name': name, 'description': t.get('description', ''),
                                 'inputSchema': t.get('input_schema', {})} for name, t in self.tools.items()]}
        elif method == 'tools/call':
            name, args = params.get('name'), params.get('arguments', {})
            try:
                if self.closed or (self.cancel_check and self.cancel_check()):
                    raise PermissionError('회원 작업이 종료됐습니다')
                if name not in self.tools or not isinstance(args, dict):
                    raise PermissionError('회원에게 발행되지 않은 도구입니다')
                if name == 'read_attached_image':
                    index = args.get('index')
                    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(self.images):
                        raise ValueError('첨부 이미지 번호 오류')
                    img = self.images[index]
                    return {'jsonrpc': '2.0', 'id': message['id'], 'result': {'content': [
                        {'type': 'image', 'data': img['base64'], 'mimeType': img.get('media_type', 'image/png')}]}}
                raw = self.provider._execute_tool_to_completion(self.execute_tool, name, args,
                                                                cancel_check=self.cancel_check)
                if isinstance(raw, dict) and 'images' in raw:
                    blocks = [{'type': 'text', 'text': str(raw.get('content', ''))}]
                    blocks += [{'type': 'image', 'data': i['base64'], 'mimeType': i.get('media_type', 'image/png')}
                               for i in raw['images']]
                else:
                    blocks = [{'type': 'text', 'text': raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)}]
                result = {'content': blocks}
            except Exception:
                result = {'content': [{'type': 'text', 'text': '회원 도구 실행 실패: 권한·연결·입력을 확인하세요.'}], 'isError': True}
        elif method != 'ping':
            return {'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': 'Unknown method'}}
        return {'jsonrpc': '2.0', 'id': message['id'], 'result': result}

    def config(self):
        return {'mcpServers': {'member': {'type': 'http',
                'url': f'http://127.0.0.1:{self.server.server_port}/mcp',
                'headers': {'Authorization': 'Bearer ' + self.secret}}}}

    def close(self):
        self.closed = True
        self.server.shutdown()
        self.server.server_close()
        with self.lock:
            pass  # 진행 중인 회원 도구가 끝난 뒤 턴 임시 경로를 회수한다.
        self.thread.join(timeout=2)


class MemberCliScope:
    """CLI 종류와 무관한 회원 턴의 신원·첨부·도구·임시 파일 수명."""
    def _prepare_launch_context(self, tools_mode):
        env = self._build_env()
        self._on_launch_environment(env)
        return env, str(self._member_root)

    def _mcp_bridge_release(self, handle):
        pass  # TemporaryDirectory가 프롬프트·설정·로그를 함께 회수한다.

    def _write_system_prompt_file(self):
        path = self._member_root / 'system-prompt.txt'
        path.write_text(self.system_prompt or '회원의 요청을 처리하세요.', encoding='utf-8')
        path.chmod(0o600)
        return str(path)

    def _save_images_to_temp(self, images):
        return []  # 이미지는 전용 MCP 도구에서만 제공한다.

    def process_message_stream(self, message, history=None, images=None, execute_tool=None, cancel_check=None):
        import member_runtime
        if not member_runtime.is_member() or not member_runtime.current():
            raise PermissionError('회원 턴 안에서만 생성하는 제공자입니다')
        self._member_images = images or []
        if images:
            message += f"\n첨부 이미지 {len(images)}개. read_attached_image(index=0부터)를 사용해 확인하세요."
        old_path = self.project_path
        with tempfile.TemporaryDirectory(prefix='indiebiz-member-') as root:
            self._member_root = Path(root)
            self.project_path = root
            self.disable_session_persistence = True
            self._member_bridge = MemberToolBridge(self, execute_tool, cancel_check)
            try:
                yield from super().process_message_stream(message, history, images, execute_tool, cancel_check)
            finally:
                self._member_bridge.close()
                self.project_path = old_path


class MemberClaudeProvider(MemberCliScope, ClaudeCodeProvider):
    """같은 모델·usage 번역기를 쓰되 도구/설정/세션은 회원 전용으로 제한한다."""
    TOOL_POLICY = ''

    def _build_command(self, mcp_config_path=None, stream=False, system_prompt_file=None, **kwargs):
        command = [self._binary_path, '--print', '--output-format', 'stream-json' if stream else 'json',
                   '--permission-mode', 'bypassPermissions', '--tools', '', '--strict-mcp-config',
                   '--setting-sources', '', '--disable-slash-commands', '--no-session-persistence',
                   '--model', self.model]
        if system_prompt_file:
            command += ['--system-prompt-file', system_prompt_file]
        else:
            command += ['--system-prompt', self.system_prompt or '회원의 요청을 처리하세요.']
        if stream:
            command.append('--verbose')
        if mcp_config_path:
            command += ['--mcp-config', mcp_config_path]
            names = [f'mcp__member__{name}' for name in self._member_bridge.tools]
            if names:
                command += ['--allowed-tools', ','.join(names)]
        return command

    def _build_env(self):
        inherited = super()._build_env()
        # 중앙 인증만 전달. 주인 MCP 인증·프로젝트 환경·개인 설정은 전달하지 않는다.
        env = {k: v for k, v in inherited.items() if k in {
            'PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'TEMP', 'TMP', 'SystemRoot', 'SYSTEMROOT',
            'CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'}}
        env['CLAUDE_CONFIG_DIR'] = str(self._member_root / 'config')
        env['CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS'] = '0'
        return env

    def _mcp_bridge_acquire(self):
        path = self._member_root / 'mcp.json'
        path.write_text(json.dumps(self._member_bridge.config()))
        path.chmod(0o600)
        return str(path)
