"""
claude_code.py - Claude Code CLI 프로바이더
IndieBiz OS Core

Claude Code를 indiebizOS의 provider로 노출. 다른 provider와 동일한 인터페이스이므로
시스템 AI·중급·프로젝트 에이전트 어디서든 드롭다운으로 선택 가능.

특성:
- 한계비용 0 (Claude Max 플랜 사용 시) — 토큰 기반 과금 안 함
- 강력한 에이전틱 코딩/조사 능력 (Read·Edit·Bash·Grep 내장)
- CLAUDE.md 자동 로드 (cwd 기준)
- 인증: 토큰 → CLAUDE_CODE_OAUTH_TOKEN 또는 ANTHROPIC_API_KEY (subprocess env)

지원 기능:
- IBL 액션 호출: data/claude_code_mcp.json MCP 브리지로 execute_ibl 노출 → 311 액션 접근
- 이미지 입력: base64 → 임시 파일 → Claude Code Read 도구로 시각 처리
- 스트리밍: process_message_stream (--output-format stream-json)
- 대화 히스토리: 매 호출 stateless, history는 프롬프트에 텍스트로 직렬화 주입

config 예시 (data/system_ai_config.json 등):
  {
    "provider": "claude_code",
    "model": "sonnet",          // 또는 "opus", "haiku", 또는 full name
    "apiKey": ""                 // 비우면 data/claude_code_config.json의 OAuth 토큰 자동 사용
  }
"""

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

from .base import BaseProvider


_IMG_EXT_BY_MEDIA = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def find_claude_binary() -> Optional[str]:
    """claude CLI 위치 탐지.

    탐색 순서:
    1. PATH에 claude
    2. Claude Desktop 번들 (macOS): ~/Library/Application Support/Claude/claude-code/*/claude.app/...
    """
    found = shutil.which("claude")
    if found:
        return found

    bundle_root = Path.home() / "Library" / "Application Support" / "Claude" / "claude-code"
    if bundle_root.exists():
        version_dirs = sorted(
            (p for p in bundle_root.iterdir() if p.is_dir()),
            reverse=True,
        )
        for version_dir in version_dirs:
            binary = version_dir / "claude.app" / "Contents" / "MacOS" / "claude"
            if binary.exists() and os.access(binary, os.X_OK):
                return str(binary)

    return None


def load_oauth_token_from_central_config() -> Optional[str]:
    """data/claude_code_config.json에서 OAuth 토큰 로드.

    Provider config에 api_key가 비어있을 때 fallback으로 사용.
    파일은 .gitignore 처리되며 600 권한 권장.
    """
    # backend/providers/claude_code.py 기준 ../../data/claude_code_config.json
    config_path = Path(__file__).resolve().parents[2] / "data" / "claude_code_config.json"
    if not config_path.exists():
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        token = data.get("oauth_token") or data.get("token") or data.get("apiKey")
        return token.strip() if token else None
    except (json.JSONDecodeError, OSError):
        return None


def get_mcp_config_path() -> Optional[str]:
    """IBL MCP 설정 파일 경로. 없으면 None."""
    mcp_path = Path(__file__).resolve().parents[2] / "data" / "claude_code_mcp.json"
    return str(mcp_path) if mcp_path.exists() else None


# ============ 세션 매핑 (--resume 연속성) ============
# Claude Code가 자기 과거 도구 호출·plan·파일 편집 이력을 기억하도록
# agent별로 session_id를 저장하고 다음 호출에 재사용한다.

def _session_map_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "claude_code_sessions.json"


def load_session_map() -> Dict[str, str]:
    p = _session_map_path()
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_session_map(m: Dict[str, str]):
    p = _session_map_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[ClaudeCodeProvider] 세션 매핑 저장 실패: {e}")


def clear_session_for_agent(session_key: str):
    """특정 agent의 세션 매핑 제거. UI '새 대화' 등에서 호출."""
    m = load_session_map()
    if session_key in m:
        del m[session_key]
        save_session_map(m)


class ClaudeCodeProvider(BaseProvider):
    """Claude Code CLI를 subprocess로 호출하는 provider."""

    DEFAULT_TIMEOUT_SEC = 600  # 10분

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._binary_path: Optional[str] = None
        self._effective_token: Optional[str] = None
        # 메타 역할(의식·평가 등) provider는 세션 연속성이 의미 없고
        # 메인 에이전트와 session_key가 충돌하므로 비활성화 가능.
        # 호출 측이 init_client 후 True로 설정.
        self.disable_session_persistence: bool = False
        # 도구 실행 결과 (non-streaming 경로에서 evaluator가 사용).
        # process_message 시작 시 비워지고 stream 이벤트 소비 중 누적된다.
        self._last_tool_results: List[str] = []
        # 도구 호출 구조화 이력 ({name, input, result, is_error}) — evaluator 시퀀스 근거용.
        # tool_start와 tool_result를 인덱스로 페어링하여 누적한다.
        self._last_tool_calls: List[Dict[str, Any]] = []

    def init_client(self) -> bool:
        """claude CLI 바이너리 탐지 + OAuth 토큰 로드 + 검증."""
        self._binary_path = find_claude_binary()
        if not self._binary_path:
            print(
                "[ClaudeCodeProvider] claude CLI를 찾을 수 없음. "
                "Claude Desktop 설치 또는 'npm install -g @anthropic-ai/claude-code' 필요"
            )
            return False

        # 토큰 우선순위:
        # 1. provider config의 api_key (단, sk-ant- 형식일 때만 — 다른 provider 키가 폴백으로
        #    잘못 흘러들어오는 경우 방어)
        # 2. 중앙 config 파일 (data/claude_code_config.json)의 OAuth 토큰
        provided_key = (self.api_key or "").strip()
        if provided_key.startswith("sk-ant-"):
            self._effective_token = provided_key
            token_source = "config.api_key"
        else:
            self._effective_token = load_oauth_token_from_central_config()
            if provided_key and not self._effective_token:
                token_source = f"config.api_key (비Anthropic 형식 무시, 중앙 토큰 없음)"
            elif provided_key:
                token_source = f"중앙 OAuth (config.api_key는 비Anthropic 형식이라 무시)"
            elif self._effective_token:
                token_source = "data/claude_code_config.json"
            else:
                token_source = "없음"

        # BaseProvider.is_ready 만족을 위한 마커
        self._client = {"binary": self._binary_path}
        print(
            f"[ClaudeCodeProvider] {self.agent_name}: 초기화 완료 "
            f"(binary={self._binary_path}, model={self.model or '기본'}, token={token_source})"
        )
        return True

    def process_message(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None,
    ) -> str:
        """동기 호출. 내부적으로 process_message_stream을 collect하여 최종 텍스트 반환.

        부수효과: tool_start/tool_result 이벤트를 self._last_tool_results와
        self._last_tool_calls에 누적해 non-streaming 호출 측(이메일 응답·시스템 AI 등)이
        evaluator에 호출 시퀀스를 통째로 전달할 수 있게 한다.
        """
        final_text = ""
        self._last_tool_results = []  # 턴 시작 시 초기화
        self._last_tool_calls = []  # 턴 시작 시 초기화
        for event in self.process_message_stream(message, history, images, execute_tool):
            etype = event.get("type")
            if etype == "text":
                final_text += event.get("content", "")
            elif etype == "tool_start":
                # 호출 헤더(이름·인풋) 우선 적재 — 결과는 다음 tool_result 이벤트에서 채운다.
                self._last_tool_calls.append({
                    "name": event.get("name", ""),
                    "input": event.get("input", {}),
                    "result": "",
                    "is_error": False,
                })
            elif etype == "tool_result":
                # evaluator 노출용 — 결과 텍스트는 legacy 리스트에도 보존.
                _result = event.get("result", "")
                if _result:
                    self._last_tool_results.append(_result)
                # 가장 최근 tool_start 항목에 결과를 페어링.
                # stream-json은 tool_result에 name이 없으므로(_translate_stream_event 참조)
                # 인덱스 기반 페어링이 정확하다 (Claude Code는 도구를 순차 실행).
                if self._last_tool_calls and not self._last_tool_calls[-1]["result"]:
                    self._last_tool_calls[-1]["result"] = _result
                    self._last_tool_calls[-1]["is_error"] = bool(event.get("is_error", False))
            elif etype == "final":
                final_text = event.get("content", final_text)
            elif etype == "error":
                return event.get("content", "[Claude Code 오류]")
        return final_text or "[Claude Code가 빈 응답을 반환했습니다]"

    def process_message_stream(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None,
        cancel_check: Callable = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """스트리밍 호출. stream-json 출력을 파싱하여 이벤트 yield.

        Yields:
            {"type": "text", "content": "..."}
            {"type": "tool_start", "name": "...", "input": {...}}
            {"type": "tool_result", "name": "...", "result": "...", "is_error": bool}
            {"type": "thinking", "content": "..."}
            {"type": "final", "content": "..."}
            {"type": "error", "content": "..."}
        """
        if not self._client:
            yield {"type": "error", "content": "Claude Code provider가 초기화되지 않았습니다."}
            return

        # 1) 이미지 → 임시 파일 → 프롬프트에 path 주입
        image_paths: List[str] = self._save_images_to_temp(images or [])

        # 2) MCP 브리지 (IBL execute_ibl 등) 자동 활성화
        mcp_config_path = get_mcp_config_path()

        # 3) 세션 연속성 결정 (--resume)
        # 정책: history가 비어있으면 새 대화로 간주하여 fresh session, 그렇지 않으면 저장된 session_id로 resume
        # 단, disable_session_persistence가 True면 (의식·평가 등 메타 역할) 항상 fresh.
        if self.disable_session_persistence:
            session_key_val = None
            session_map = {}
            stored_session_id = None
            resume_session_id = None
        else:
            session_key_val = self._get_session_key()
            session_map = load_session_map()
            stored_session_id = session_map.get(session_key_val)
            resume_session_id = stored_session_id if (history and stored_session_id) else None
            # history 없으면 (= 새 대화) 기존 매핑 무효화
            if not history and stored_session_id:
                clear_session_for_agent(session_key_val)
                stored_session_id = None

        # 4~6) resume 시도 → 만료/무효 시 fresh 로 자동 재시도 (최대 2회)
        # CLI 가 `--resume <소멸한 세션>` 을 만나면 stdout JSON 이 아니라 stderr +
        # 종료코드 1("No conversation found with session ID")로 즉사한다. 첫 시도가
        # 그렇게 실패하면 그 에러를 사용자에게 노출하지 않고 삼킨 뒤(deferred) 매핑을
        # 폐기하고 fresh 로 한 번 더 돌린다. 그래야 stale 매핑이 고착되지 않는다.
        for attempt in range(2):
            is_resume_attempt = bool(resume_session_id)

            # 프롬프트 빌드 — resume 면 CLI 가 자체 세션에서 history 를 알므로 현재 메시지만,
            # fresh 면 직렬화된 history 를 함께 보낸다.
            if resume_session_id:
                full_prompt = message
            else:
                full_prompt = self._build_prompt_with_history(message, history or [])

            if image_paths:
                img_lines = "\n".join(f"첨부 이미지 경로: {p}" for p in image_paths)
                full_prompt = (
                    f"{img_lines}\n"
                    f"(위 이미지 파일을 Read 도구로 읽어 시각 내용을 확인할 수 있다)\n\n"
                    f"{full_prompt}"
                )

            cmd = self._build_command(
                mcp_config_path=mcp_config_path,
                stream=True,
                resume_session_id=resume_session_id,
            )

            _sp_len = len(self.system_prompt or "")
            _msg_len = len(full_prompt or "")
            _resumed = "resume" if resume_session_id else "new"
            print(
                f"[ClaudeCode/{self.agent_name}] call: session={_resumed} "
                f"system_prompt={_sp_len}자 message={_msg_len}자"
            )

            env = self._build_env()
            start = time.time()
            cwd = self.project_path if self.project_path and self.project_path != "." else None
            try:
                proc = subprocess.Popen(
                    cmd + ["--", full_prompt],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    cwd=cwd,
                    env=env,
                )
            except FileNotFoundError as e:
                self.metrics.record_error()
                yield {"type": "error", "content": f"Claude Code 바이너리 실행 실패: {e}"}
                return

            accumulated_text = ""
            captured_session_id: Optional[str] = None
            committed = False          # 실제 본문(text/tool/thinking)을 하나라도 받았나
            resume_err_text = ""       # stdout result 에러 텍스트 (보통 비어있음)
            deferred: List[Dict] = []  # resume 시도 중 보류한 터미널 이벤트(error/final)
            try:
                for raw_line in proc.stdout:
                    if cancel_check and cancel_check():
                        proc.kill()
                        yield {"type": "error", "content": "사용자 취소"}
                        return

                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    sid = event.get("session_id")
                    if sid:
                        captured_session_id = sid

                    if event.get("type") == "result" and event.get("is_error"):
                        resume_err_text = str(event.get("result") or "")

                    yielded = self._translate_stream_event(event, accumulated_text, start)
                    for out_event, new_acc in yielded:
                        if new_acc is not None:
                            accumulated_text = new_acc
                        t2 = out_event.get("type")
                        if t2 in ("text", "tool_start", "tool_result", "thinking"):
                            committed = True
                        # resume 시도이고 아직 본문이 안 왔으면 터미널 에러/final 은 보류
                        if is_resume_attempt and not committed and t2 in ("error", "final"):
                            deferred.append(out_event)
                        else:
                            yield out_event

                proc.wait(timeout=self.DEFAULT_TIMEOUT_SEC)

            except subprocess.TimeoutExpired:
                proc.kill()
                self.metrics.record_error()
                yield {"type": "error", "content": f"Claude Code 호출 타임아웃 ({self.DEFAULT_TIMEOUT_SEC}초)"}
                return
            except Exception as e:
                self.metrics.record_error()
                yield {"type": "error", "content": f"Claude Code 스트림 오류: {e}"}
                return
            finally:
                if proc.poll() is None:
                    proc.kill()

            # 비정상 종료 시 stderr 확보 (resume 실패 메시지가 여기에 담긴다)
            stderr_text = ""
            if proc.returncode is not None and proc.returncode != 0 and not accumulated_text:
                stderr_text = (proc.stderr.read() if proc.stderr else "").strip()

            # --- resume 실패 판정 (stdout result 텍스트 + stderr 종합) ---
            combined = (resume_err_text + " " + stderr_text).lower()
            session_issue = ("no conversation found" in combined) or (
                "session" in combined
                and ("not found" in combined or "invalid" in combined)
            )
            # session 만료/무효일 때만 재시도 — rate limit·인증 등 일시적 에러로는
            # 멀쩡한 매핑을 폐기하지 않는다 (그 에러는 그대로 사용자에게 보고).
            resume_failed = is_resume_attempt and not committed and session_issue

            if attempt == 0 and resume_failed:
                # 매핑 폐기 + fresh 재시도 (보류했던 에러는 버린다 → 사용자에 미노출)
                if session_key_val:
                    clear_session_for_agent(session_key_val)
                print(
                    f"[ClaudeCodeProvider] {self.agent_name}: 저장된 세션"
                    f"({(stored_session_id or '')[:8]}...) 만료/무효 → fresh 재시도"
                )
                resume_session_id = None
                stored_session_id = None
                continue

            # --- 최종 attempt: 결과 확정 ---
            for ev in deferred:          # 보류했던 터미널 이벤트 방출
                yield ev
            if proc.returncode not in (0, None) and not accumulated_text and not deferred:
                yield {
                    "type": "error",
                    "content": f"Claude Code 종료 코드 {proc.returncode}: {stderr_text[:500]}",
                }

            # 세션 매핑 갱신 (disable_session_persistence면 스킵)
            if not self.disable_session_persistence and session_key_val:
                if captured_session_id and captured_session_id != stored_session_id:
                    session_map[session_key_val] = captured_session_id
                    save_session_map(session_map)
                    print(
                        f"[ClaudeCodeProvider] {self.agent_name}: 세션 저장 "
                        f"({session_key_val} → {captured_session_id[:8]}...)"
                    )
            break

    def _translate_stream_event(
        self, event: Dict, accumulated_text: str, start_time: float
    ) -> List[tuple]:
        """Claude Code stream-json 이벤트 → indiebizOS provider 이벤트 형식 변환.

        Returns:
            [(event_dict, new_accumulated_text_or_None), ...]
        """
        out: List[tuple] = []
        etype = event.get("type")

        if etype == "assistant":
            msg = event.get("message") or {}
            for block in msg.get("content", []):
                btype = block.get("type")
                if btype == "text":
                    text = block.get("text", "")
                    if text:
                        out.append(({"type": "text", "content": text}, accumulated_text + text))
                        accumulated_text = accumulated_text + text
                elif btype == "tool_use":
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    # episode_logger가 stdout을 캡처 → 회고 자료로 보존
                    try:
                        input_repr = json.dumps(tool_input, ensure_ascii=False)
                    except (TypeError, ValueError):
                        input_repr = str(tool_input)
                    if len(input_repr) > 300:
                        input_repr = input_repr[:300] + "..."
                    print(f"[ClaudeCode/{self.agent_name}] tool_use {tool_name} {input_repr}")
                    out.append((
                        {
                            "type": "tool_start",
                            "name": tool_name,
                            "input": tool_input,
                        },
                        None,
                    ))
                elif btype == "thinking":
                    # Anthropic 표준: {"type":"thinking","thinking":"...","signature":"..."}
                    _t = (
                        block.get("thinking")
                        or block.get("text")
                        or block.get("content")
                        or ""
                    )
                    if isinstance(_t, list):
                        _t = " ".join(
                            (c.get("text", "") if isinstance(c, dict) else str(c))
                            for c in _t
                        )
                    _t_str = str(_t).strip()
                    if not _t_str and block.get("signature"):
                        # signature만 있고 텍스트 비어있음 = Anthropic 안전 정책으로 redact됨
                        # (특히 opus는 thinking 텍스트가 거의 항상 redact됨)
                        # 사실 발생 자체는 회고에 의미 있으므로 명확한 마커로 기록.
                        _t_str = "[extended_thinking — 텍스트 redacted (Anthropic 안전 정책), signature만 보존됨]"
                    out.append((
                        {"type": "thinking", "content": _t_str},
                        None,
                    ))
                elif btype == "redacted_thinking":
                    out.append((
                        {"type": "thinking", "content": "[redacted_thinking — 안전 정책으로 감춰짐]"},
                        None,
                    ))

        elif etype == "user":
            # tool_result blocks (Claude Code가 자기 도구 호출한 결과)
            msg = event.get("message") or {}
            for block in msg.get("content", []):
                if block.get("type") != "tool_result":
                    continue
                result_content = block.get("content", "")
                if isinstance(result_content, list):
                    result_text = " ".join(
                        c.get("text", "") for c in result_content
                        if isinstance(c, dict) and c.get("type") == "text"
                    )
                else:
                    result_text = str(result_content)
                is_error = bool(block.get("is_error"))
                # episode_logger 캡처용 — 결과는 앞부분만
                result_preview = result_text.replace("\n", " ")
                if len(result_preview) > 300:
                    result_preview = result_preview[:300] + "..."
                err_tag = " (error)" if is_error else ""
                print(f"[ClaudeCode/{self.agent_name}] tool_result{err_tag} {result_preview}")
                out.append((
                    {
                        "type": "tool_result",
                        "name": "",  # stream-json의 tool_result에는 name 없음
                        "result": result_text,
                        "is_error": is_error,
                    },
                    None,
                ))

        elif etype == "result":
            final_text = event.get("result") or accumulated_text
            latency_ms = (time.time() - start_time) * 1000
            usage = event.get("usage") or {}
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            # 캐시 통계 — 어제 한 prefix 분리 작업의 실효성 측정.
            # cache_read = 캐시 hit으로 즉시 처리된 input (저렴, 빠름)
            # cache_create = 새로 캐시에 쓰인 input (write 비용)
            cache_read = int(usage.get("cache_read_input_tokens") or 0)
            cache_create = int(usage.get("cache_creation_input_tokens") or 0)
            self.metrics.record_request(latency_ms, input_tokens, output_tokens)
            err_flag = " (error)" if event.get("is_error") else ""
            cache_info = f" cache_read={cache_read} cache_create={cache_create}" if (cache_read or cache_create) else ""
            print(
                f"[ClaudeCode/{self.agent_name}] result{err_flag} "
                f"{latency_ms:.0f}ms in={input_tokens} out={output_tokens}{cache_info}"
            )

            if event.get("is_error"):
                if isinstance(final_text, str) and ("Not logged in" in final_text or "/login" in final_text):
                    out.append((
                        {
                            "type": "error",
                            "content": (
                                "Claude Code 인증 필요. 터미널에서 한 번 실행:\n"
                                f"  '{self._binary_path}' setup-token"
                            ),
                        },
                        None,
                    ))
                else:
                    out.append(({"type": "error", "content": f"Claude Code 응답 오류: {final_text}"}, None))
            else:
                out.append(({"type": "final", "content": (final_text or "").strip()}, None))

        return out

    def _get_session_key(self) -> str:
        """세션 매핑의 키. thread_context의 registry_key 우선, 없으면 agent_id/이름 폴백."""
        try:
            from thread_context import get_current_registry_key
            key = get_current_registry_key()
            if key:
                return key
        except ImportError:
            pass
        return self.agent_id or self.agent_name or "default"

    # ToolSearch 우회용 eager 도구 목록.
    # --allowed-tools 는 restrictive이므로 Claude Code가 흔히 쓰는 built-in + MCP IBL을 명시.
    # 이 목록에 없는 도구는 사용 불가 (트레이드오프: 속도 향상 vs 도구 범위 제한).
    # 더 많은 도구가 필요해지면 여기에 추가.
    # 원칙: IBL 어휘를 *중복(그림자)* 하는 네이티브는 여기서 빼고 DISALLOWED 로 하드 차단한다.
    #   Claude Code 2.1.170 에서 MCP execute_ibl 은 deferred(ToolSearch 경유)인데 네이티브는 eager 라,
    #   중복 네이티브를 남기면 모델이 IBL 대신 그쪽으로 새는 회귀가 생긴다(Read·WebSearch 실측 누수).
    #   → 누수 차단 = 어휘 일관성·해마 학습·폰 이식성·실행 통제(게이팅/로깅/압축) 보존.
    # 남기는 것: 셸 탈출구(Bash 계열 — IBL 에 등가물 없는 의도된 peer: Python/Node/임의 명령) +
    #   파일 쓰기/편집(셸 코드 작성-실행 루프의 짝) + execute_ibl.
    # 주의: 이 분리는 Claude Code 프로바이더 한정. 일반 프로바이더(Gemini 등)는 이런 네이티브가 애초에 없다.
    EAGER_TOOLS = [
        # 파일 쓰기/편집 — 셸 코드 루프(스크립트 작성→실행)의 일부
        "Write", "Edit", "MultiEdit", "NotebookEdit",
        # 셸 탈출구 — IBL 에 등가물 없는 의도된 peer (Python/Node/임의 명령). 일부러 IBL 어휘로 안 만듦.
        "Bash", "BashOutput", "KillShell",
        # 작업 관리
        "TodoWrite",
        # MCP — IBL 브리지 (5노드 전체)
        "mcp__indiebizos__execute_ibl",
    ]

    # 명시적으로 차단할 도구 — ToolSearch 등을 통해 우회 로드되더라도 호출 거부됨.
    # AskUserQuestion: indiebizOS UI 미연결, 응답 채널 없음 → IBL [user:ask] 사용.
    # 아래 네이티브들은 IBL 액션과 1:1 중복이라, 모델이 IBL 대신 새지 못하게 강제로 막는다.
    DISALLOWED_TOOLS = [
        "AskUserQuestion",          # → IBL [user:ask] / [self:ask_user]
        "Read",                     # → [self:read]
        "Grep", "Glob",             # → [self:grep]
        "WebSearch",                # → [sense:search_ddg/news/scholar/naver]
        "WebFetch",                 # → [sense:crawl]
    ]

    # 도구 정책 — 시스템 프롬프트에 append. **Claude Code 프로바이더 전용**:
    # 이 네이티브 도구들은 Claude Code 에만 존재하므로, 공용 프롬프트(base_prompt_v5)가 아니라
    # 여기서만 주입한다(Gemini 등 다른 프로바이더는 이런 도구가 없어 안내가 불필요·혼란).
    # 차단된 네이티브 대신 IBL 등가물을 첫 시도에 쓰게 해 헛걸음을 막는다.
    TOOL_POLICY = (
        "\n\n# 도구 정책\n"
        "파일 읽기·웹 검색·grep 은 네이티브 도구가 아니라 IBL 로 하라. "
        "`Read`/`WebSearch`/`WebFetch`/`Grep`/`Glob` 은 비활성화돼 있다 — 대신 execute_ibl 로 "
        "`[self:read]`(파일)·`[sense:search_ddg/news/scholar/naver]`(웹검색)·`[sense:crawl]`(웹페이지)·"
        "`[self:grep]`(코드검색) 을 호출하라. "
        "셸·코드 실행(`Bash`)은 그대로 사용 가능하다 — IBL 에 등가물이 없는 탈출구다."
    )

    def _build_command(
        self,
        mcp_config_path: Optional[str] = None,
        stream: bool = False,
        resume_session_id: Optional[str] = None,
    ) -> List[str]:
        """공통 CLI 인자 구성 (positional prompt는 호출 측에서 append).

        --no-session-persistence는 일부러 빼놓음 — Claude Code가 디스크에 세션을 저장해야
        다음 호출 시 --resume으로 자기 과거를 이어볼 수 있음.

        --allowed-tools 는 deferred tool loading(ToolSearch)을 우회하기 위함 —
        목록의 도구들은 eager-load되어 매 호출마다 ToolSearch round-trip이 사라짐.
        """
        cmd = [
            self._binary_path,
            "--print",
            "--output-format", "stream-json" if stream else "json",
            # 비대화 모드에서 권한 프롬프트로 멈추지 않도록 — MCP 호출은 indiebizOS 자체 게이트
            "--permission-mode", "bypassPermissions",
            # ToolSearch 우회: 자주 쓰는 도구를 eager-load
            "--allowed-tools", ",".join(self.EAGER_TOOLS),
            # 명시 차단: indiebizOS UI와 연결되지 않은 도구 (AskUserQuestion 등)
            "--disallowed-tools", ",".join(self.DISALLOWED_TOOLS),
        ]

        # stream-json 출력은 verbose 필수
        if stream:
            cmd += ["--verbose"]

        # 세션 이어가기 (Claude Code가 자기 과거 도구 호출·plan·파일 편집 이력을 봄)
        if resume_session_id:
            cmd += ["--resume", resume_session_id]

        if self.model:
            cmd += ["--model", self.model]

        # 시스템 프롬프트 + Claude Code 전용 도구 정책(차단 네이티브 → IBL 등가물 안내)
        cmd += ["--append-system-prompt", (self.system_prompt or "") + self.TOOL_POLICY]

        # MCP 브리지 (IBL execute_ibl 등)
        if mcp_config_path:
            cmd += ["--mcp-config", mcp_config_path]

        return cmd

    def _build_env(self) -> Dict[str, str]:
        """subprocess에 전달할 env 구성.

        - OAuth 토큰 (sk-ant-oat...) → CLAUDE_CODE_OAUTH_TOKEN (Max/Pro 구독 빌링)
        - API 키 (sk-ant-api...) → ANTHROPIC_API_KEY (per-call 빌링)
        - INDIEBIZOS_PROJECT_PATH → MCP 서버가 execute_ibl 기본 project_path로 사용
        """
        env = os.environ.copy()
        if self._effective_token:
            if self._effective_token.startswith("sk-ant-oat"):
                env["CLAUDE_CODE_OAUTH_TOKEN"] = self._effective_token
                env.pop("ANTHROPIC_API_KEY", None)
            else:
                env["ANTHROPIC_API_KEY"] = self._effective_token
        if self.project_path and self.project_path != ".":
            env["INDIEBIZOS_PROJECT_PATH"] = str(self.project_path)
        # 발신 신원: subprocess(claude)가 MCP→/ibl/execute로 IBL을 돌릴 때 자기 agent_id를 갖고 가게 한다.
        # in-process 프로바이더는 execute_tool(..., self.agent_id)로 직접 넘기지만, out-of-process인 이 프로바이더는
        # env가 유일한 통로. channel_send/read의 신원 게이트(시스템 AI=system_ai, 프로젝트 에이전트=자기 계정)에 필요.
        if self.agent_id:
            env["INDIEBIZOS_AGENT_ID"] = str(self.agent_id)
        return env

    def _save_images_to_temp(self, images: List[Dict]) -> List[str]:
        """base64 이미지를 임시 파일로 저장하고 경로 리스트 반환.

        images 형식: [{"base64": "...", "media_type": "image/png"}, ...]
        Claude Code의 Read 도구가 vision으로 이미지 내용을 읽음.
        """
        paths: List[str] = []
        for img in images:
            if not isinstance(img, dict):
                continue
            b64 = (img.get("base64") or "").strip()
            if not b64:
                continue
            media = (img.get("media_type") or "image/png").lower()
            ext = _IMG_EXT_BY_MEDIA.get(media, ".png")
            try:
                fd, path = tempfile.mkstemp(suffix=ext, prefix="claude_code_img_")
                with os.fdopen(fd, "wb") as f:
                    f.write(base64.b64decode(b64))
                paths.append(path)
            except (ValueError, OSError) as e:
                print(f"[ClaudeCodeProvider] {self.agent_name}: 이미지 저장 실패: {e}")
        return paths

    def _build_prompt_with_history(self, message: str, history: List[Dict]) -> str:
        """history를 텍스트로 직렬화해서 message 앞에 붙임 (stateless 모드)."""
        if not history:
            return message

        lines = ["[이전 대화]"]
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")

            # 복합 content (tool calls 등) → 텍스트만 추출
            if isinstance(content, list):
                parts = []
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") == "text":
                            parts.append(c.get("text", ""))
                        elif c.get("type") == "tool_use":
                            parts.append(f"[도구 호출: {c.get('name', '')}]")
                        elif c.get("type") == "tool_result":
                            tr = c.get("content", "")
                            if isinstance(tr, str):
                                parts.append(f"[도구 결과] {tr[:500]}")
                    elif isinstance(c, str):
                        parts.append(c)
                content = " ".join(parts)
            elif not isinstance(content, str):
                content = str(content)

            role_label = "사용자" if role == "user" else "어시스턴트"
            lines.append(f"{role_label}: {content}")

        lines.append("")
        lines.append("[현재 메시지]")
        lines.append(message)
        return "\n".join(lines)
