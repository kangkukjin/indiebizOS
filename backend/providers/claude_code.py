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
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional
from urllib.parse import quote

from .base import BaseProvider


_IMG_EXT_BY_MEDIA = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

# 프론트엔드가 채팅 텍스트에서 인식하는 지도 봉투 타입 (chatUtils.parseMapData 계약).
_MAP_ENVELOPE_TYPES = ("route_map", "location_map")


def _extract_map_tags(tool_result_text: str) -> List[str]:
    """도구 결과 텍스트에서 지도 봉투(route_map/location_map)를 찾아 [MAP:{...}] 태그로 반환.

    IBL 실행 경로는 지도 결과를 map_data 키(봉투)로만 담고 [MAP:] 태그를 붙이지 않으며,
    파이프라인(`>>`)이면 봉투가 중첩 JSON 문자열 안에 있다. 그래서 문자열을 재귀적으로
    파싱해(안쪽 JSON 문자열도 다시 loads) `type in (route_map, location_map)`인 dict 를
    전부 찾아 프론트엔드 계약대로 [MAP:{clean json}] 로 직렬화한다. 중복은 제거.
    파싱 불가 조각은 조용히 건너뜀(graceful).
    """
    found: List[dict] = []
    seen: set = set()

    def walk(obj, depth=0):
        if depth > 8:
            return
        if isinstance(obj, dict):
            if obj.get("type") in _MAP_ENVELOPE_TYPES:
                key = json.dumps(obj, ensure_ascii=False, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    found.append(obj)
            for v in obj.values():
                walk(v, depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, depth + 1)
        elif isinstance(obj, str):
            s = obj.strip()
            if s.startswith(("{", "[")) and len(s) < 500_000:
                try:
                    walk(json.loads(s), depth + 1)
                except (json.JSONDecodeError, ValueError):
                    pass

    try:
        walk(json.loads(tool_result_text))
    except (json.JSONDecodeError, ValueError, TypeError):
        return []
    return [f"[MAP:{json.dumps(m, ensure_ascii=False)}]" for m in found]


def find_claude_binary() -> Optional[str]:
    """claude CLI 위치 탐지 (크로스플랫폼).

    탐색 순서:
    1. PATH의 claude / claude.exe (shutil.which)
    2. 데스크톱 앱 동봉 번들:
       - macOS:   ~/Library/Application Support/Claude/claude-code/<ver>/claude.app/Contents/MacOS/claude
       - Windows: %APPDATA%\\Claude\\claude-code\\<ver>\\claude.exe  (LOCALAPPDATA 폴백)

    번들 실행파일은 PATH에 없으므로(설치판) 이 2단계가 없으면 윈도우에선 'claude 못 찾음'
    → init_client 가 False 반환 → provider not-ready → 사용자에겐 '키/인증 없음'으로 보인다.
    """
    found = shutil.which("claude")
    if found:
        return found

    candidates: List[Path] = []
    if os.name == "nt":  # Windows — 번들 exe: <appdata>\Claude\claude-code\<ver>\claude.exe
        roots: List[Path] = []
        for var in ("APPDATA", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                roots.append(Path(base) / "Claude" / "claude-code")
        for root in roots:
            if root.exists():
                for version_dir in sorted(
                    (p for p in root.iterdir() if p.is_dir()), reverse=True
                ):
                    candidates.append(version_dir / "claude.exe")
    else:  # macOS 번들
        root = Path.home() / "Library" / "Application Support" / "Claude" / "claude-code"
        if root.exists():
            for version_dir in sorted(
                (p for p in root.iterdir() if p.is_dir()), reverse=True
            ):
                candidates.append(
                    version_dir / "claude.app" / "Contents" / "MacOS" / "claude"
                )

    for binary in candidates:
        # 윈도우 .exe 는 os.access(X_OK)가 신뢰불가 → 존재만 확인
        if binary.exists() and (os.name == "nt" or os.access(binary, os.X_OK)):
            return str(binary)

    return None


def _data_dir() -> Path:
    """데이터 디렉토리 경로. 다른 백엔드 모듈과 동일한 관례(runtime_utils.get_base_path)로
    해석한다 — 프로덕션(패키지 앱)에선 INDIEBIZ_BASE_PATH(=userData), 개발에선 repo 루트.

    ★윈도우 패키지 앱 버그 방지: 하드코딩 parents[2]/data 는 설치폴더(resources, 읽기전용)를
    가리켜, 사용자가 userData(%APPDATA%\\IndieBiz OS\\data)에 넣은 OAuth 토큰을 못 봤다.
    이 헬퍼로 통일해 토큰·세션·MCP 파일을 모두 userData 기준으로 읽는다. (맥/개발은 동일 경로.)
    """
    try:
        from runtime_utils import get_base_path
        return get_base_path() / "data"
    except Exception:
        return Path(__file__).resolve().parents[2] / "data"


def load_oauth_token_from_central_config() -> Optional[str]:
    """data/claude_code_config.json에서 OAuth 토큰 로드.

    Provider config에 api_key가 비어있을 때 fallback으로 사용.
    파일은 .gitignore 처리되며 600 권한 권장.
    """
    config_path = _data_dir() / "claude_code_config.json"
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
    mcp_path = _data_dir() / "claude_code_mcp.json"
    return str(mcp_path) if mcp_path.exists() else None


# ============ 세션 매핑 (--resume 연속성) ============
# Claude Code가 자기 과거 도구 호출·plan·파일 편집 이력을 기억하도록
# agent별로 session_id를 저장하고 다음 호출에 재사용한다.

def _session_map_path() -> Path:
    return _data_dir() / "claude_code_sessions.json"


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


# ============ 세션 컨텍스트 크기 추적 (크기 기반 리셋) ============
# --resume 은 CLI 가 디스크의 전체 트랜스크립트를 재생하므로 세션이 무한 성장한다.
# (indiebizOS 가 넘기는 5턴/요약 트림은 resume 경로에서 버려짐.) 의미 있는 장기
# 연속성은 이미 indiebizOS 기억층(연상·심층메모리·의식 요약·포식)이 주입하므로,
# raw 트랜스크립트가 임계 토큰을 넘으면 다음 턴에 fresh 세션으로 끊고 트림 히스토리로
# 재시드한다. 턴 수가 아니라 *실측 토큰*(in+cache_read+cache_create)에 거는 이유:
# 턴 크기가 비균일하다 — 이미지/긴 산출물 한 턴이 폭발 주범이지 턴 수가 아니다.
# ★임계값은 truncation 방어가 아니다: 모델(Opus 4.8)의 컨텍스트 윈도우는 1M 이라 이 값이
# 조절하는 건 천장이 아니라 비용/지연/품질(낡은 tool_result 희석)이다. 옛 150K(윈도우 15%)는
# goal-eval 재실행 3라운드를 태스크 도중에 끊어 탈선시켰다(episode 718). 300K(30%, 700K 여유)
# 로 올려 멀티라운드 루프가 in-session 으로 끝나게 한다. 되돌릴 때 "200K 벽" 가정 금지 — 옛
# Opus 200K 기억은 stale, 현 모델은 1M. 비용이 문제면 값 낮추기보다 낡은 tool_result 비우기.
SESSION_RESET_TOKEN_THRESHOLD = 300_000


def _session_size_path() -> Path:
    return _data_dir() / "claude_code_session_sizes.json"


def load_session_sizes() -> Dict[str, int]:
    p = _session_size_path()
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_session_sizes(m: Dict[str, int]):
    p = _session_size_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[ClaudeCodeProvider] 세션 크기 저장 실패: {e}")


def record_session_size(session_key: str, size: int):
    """직전 턴의 실측 컨텍스트 토큰 수를 기록 (다음 턴 리셋 판단용)."""
    if not session_key or size <= 0:
        return
    m = load_session_sizes()
    m[session_key] = int(size)
    save_session_sizes(m)


def clear_session_size(session_key: str):
    m = load_session_sizes()
    if session_key in m:
        del m[session_key]
        save_session_sizes(m)


class ClaudeCodeProvider(BaseProvider):
    """Claude Code CLI를 subprocess로 호출하는 provider."""

    DEFAULT_TIMEOUT_SEC = 600  # 10분

    # 서버측 일시 과부하(529 Overloaded / overloaded_error 등) 자동 재시도.
    # 본문이 아직 하나도 안 온(not committed) 경우에만 backoff 후 다시 호출한다.
    # 입력 크기와 무관한 서버 포화 신호라, 강의 저작처럼 "유효 JSON 한 방"이
    # 필요한 일회성 호출이 단 한 번의 과부하로 통째 실패하던 걸 흡수한다.
    OVERLOADED_MAX_RETRIES = 3
    OVERLOADED_BASE_DELAY_SEC = 2.0
    OVERLOADED_MAX_DELAY_SEC = 30.0

    @staticmethod
    def _is_overloaded_error(text: str) -> bool:
        """일시적 서버 과부하 에러인지 판정 (대소문자 무시).

        주의: 이 검사는 *에러 텍스트*(resume_err_text+stderr)에만 적용된다.
        'overloaded' 키워드가 1차 신호. '529'는 에러 맥락(error 동반)일 때만
        인정해 본문 숫자 등 우발적 부분일치 오탐을 막는다.
        """
        low = (text or "").lower()
        if "overloaded" in low:  # "API Error: 529 Overloaded" / overloaded_error 등
            return True
        return "529" in low and "error" in low

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._binary_path: Optional[str] = None
        self._effective_token: Optional[str] = None
        # 메타 역할(의식·평가 등) provider는 세션 연속성이 의미 없고
        # 메인 에이전트와 session_key가 충돌하므로 비활성화 가능.
        # 호출 측이 init_client 후 True로 설정.
        self.disable_session_persistence: bool = False
        # 직전 턴의 실측 컨텍스트 토큰 수(in+cache_read+cache_create) 릴레이.
        # _translate_stream_event 가 result 이벤트에서 채우고, 세션 저장부가 읽어 영속화.
        self._last_context_size: int = 0
        # 도구 실행 결과 (non-streaming 경로에서 evaluator가 사용).
        # process_message 시작 시 비워지고 stream 이벤트 소비 중 누적된다.
        self._last_tool_results: List[str] = []
        # 도구 호출 구조화 이력 ({name, input, result, is_error}) — evaluator 시퀀스 근거용.
        # tool_start와 tool_result를 인덱스로 페어링하여 누적한다.
        self._last_tool_calls: List[Dict[str, Any]] = []
        # 이번 턴 도구 결과에서 발견한 지도 봉투(route_map/location_map)를 [MAP:...] 태그로 모아,
        # 최종 응답 끝에 재주입한다. in-process 프로바이더(anthropic/gemini/openai/ollama)는
        # execute_tool 이 [MAP:] 태그를 붙이고 각자 재주입하지만, 아웃오브프로세스인 이 프로바이더는
        # CLI 서브프로세스가 도구 결과를 산문으로 요약하며 마커를 흘려버려 프론트 지도가 안 뜬다.
        # process_message_stream 시작 시 비워지고, tool_result 소비 중 누적된다.
        self._pending_map_tags: List[str] = []

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

        # 턴 시작 시 라운드별 컨텍스트 크기 릴레이 초기화 (이전 턴 값 잔류 방지)
        self._last_context_size = 0
        # 턴 시작 시 지도 태그 누적 초기화 (이전 턴 지도가 새 응답에 새는 것 방지)
        self._pending_map_tags = []

        # 1) 이미지 → 임시 파일 → 프롬프트에 path 주입
        image_paths: List[str] = self._save_images_to_temp(images or [])

        # 2) MCP 브리지: HTTP 우선(플래그 ON일 때) → stdio 폴백
        _http_cfg = self._http_mcp_config_path()
        mcp_config_path = _http_cfg or get_mcp_config_path()
        try:

            # 2.5) 시스템 프롬프트를 파일로 (윈도우 argv 상한 회피 — _build_command 주석 참조).
            #      리트라이 루프 전체에서 재사용(내용 불변). 실패 시 None → 인자 방식 폴백.
            system_prompt_file = self._write_system_prompt_file()

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
                # 크기 기반 리셋: 직전 턴 컨텍스트가 임계 초과면 fresh 로 끊는다.
                # fresh 경로는 _build_prompt_with_history 로 트림된 5턴 히스토리를 재시드하므로
                # 맥락은 indiebizOS 기억층 + 트림 히스토리로 이어진다 (raw 중복만 제거).
                if resume_session_id:
                    prev_size = int(load_session_sizes().get(session_key_val) or 0)
                    if prev_size > SESSION_RESET_TOKEN_THRESHOLD:
                        print(
                            f"[ClaudeCodeProvider] {self.agent_name}: 세션 컨텍스트 "
                            f"{prev_size:,} > {SESSION_RESET_TOKEN_THRESHOLD:,} 토큰 → fresh 리셋"
                        )
                        clear_session_for_agent(session_key_val)
                        clear_session_size(session_key_val)
                        stored_session_id = None
                        resume_session_id = None

            # 4~6) resume 시도 → 만료/무효 시 fresh 로 자동 재시도 (resume→fresh 1회)
            #      + 일시 서버 과부하(529 Overloaded) → backoff 후 재시도 (최대 N회)
            # CLI 가 `--resume <소멸한 세션>` 을 만나면 stdout JSON 이 아니라 stderr +
            # 종료코드 1("No conversation found with session ID")로 즉사한다. 첫 시도가
            # 그렇게 실패하면 그 에러를 사용자에게 노출하지 않고 삼킨 뒤(deferred) 매핑을
            # 폐기하고 fresh 로 한 번 더 돌린다. 그래야 stale 매핑이 고착되지 않는다.
            # 과부하(529)는 입력과 무관한 서버측 신호 → 본문 미수신이면 backoff 후 같은 호출 반복.
            resume_attempt = 0       # resume→fresh 폴백 횟수 (0 또는 1)
            overloaded_retries = 0   # 529 과부하 재시도 횟수
            while True:
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
                    system_prompt_file=system_prompt_file,
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
                    # ★유저 프롬프트는 argv 가 아니라 stdin 으로 넘긴다: 윈도우 명령줄 상한
                    #  (32,767자)에 걸려 [WinError 206]로 실행 자체가 실패하던 걸 회피. claude
                    #  --print 는 stdin EOF까지 읽은 뒤 응답하므로 먼저 써넣고 닫는다.
                    #  encoding=utf-8 명시: 윈도우 기본 로케일 인코딩(cp949 등)으로 stdin/stdout이
                    #  깨지지 않도록(한글 프롬프트·응답 JSON 보존).
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        cwd=cwd,
                        env=env,
                    )
                except FileNotFoundError as e:
                    self.metrics.record_error()
                    yield {"type": "error", "content": f"Claude Code 바이너리 실행 실패: {e}"}
                    return

                # 유저 프롬프트 주입 후 stdin 닫기 (EOF 신호 → claude 가 응답 시작)
                try:
                    if proc.stdin:
                        proc.stdin.write(full_prompt)
                        proc.stdin.close()
                except (BrokenPipeError, OSError) as e:
                    print(f"[ClaudeCode/{self.agent_name}] stdin 프롬프트 쓰기 실패: {e}")

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
                            # 아직 본문이 안 왔으면(committed=False) 터미널 에러/final 은 보류.
                            # resume 실패(만료 세션)·일시 과부하(529) 둘 다 본문 도착 전에만
                            # 재시도 가능하므로, 보류해 두고 스트림 종료 후 재시도 여부를 판단한다.
                            if not committed and t2 in ("error", "final"):
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

                if resume_attempt == 0 and resume_failed:
                    # 매핑 폐기 + fresh 재시도 (보류했던 에러는 버린다 → 사용자에 미노출)
                    resume_attempt += 1
                    if session_key_val:
                        clear_session_for_agent(session_key_val)
                    print(
                        f"[ClaudeCodeProvider] {self.agent_name}: 저장된 세션"
                        f"({(stored_session_id or '')[:8]}...) 만료/무효 → fresh 재시도"
                    )
                    resume_session_id = None
                    stored_session_id = None
                    continue

                # --- 일시 서버 과부하(529 Overloaded) → backoff 후 재시도 ---
                # 본문 미수신(not committed) + 과부하 신호일 때만. 보류한 에러는 버리고
                # (continue 시 deferred 가 다음 루프 진입부에서 초기화됨) 잠시 쉰 뒤 같은 호출 반복.
                # 한 번의 transient 과부하가 강의 저작 같은 일회성 호출을 통째 실패시키던 걸 흡수.
                if (
                    not committed
                    and self._is_overloaded_error(combined)
                    and overloaded_retries < self.OVERLOADED_MAX_RETRIES
                ):
                    delay = min(
                        self.OVERLOADED_BASE_DELAY_SEC * (2 ** overloaded_retries),
                        self.OVERLOADED_MAX_DELAY_SEC,
                    )
                    overloaded_retries += 1
                    self.metrics.record_retry()
                    print(
                        f"[ClaudeCodeProvider] {self.agent_name}: 서버 과부하(529) → "
                        f"{delay:.0f}초 후 재시도 {overloaded_retries}/{self.OVERLOADED_MAX_RETRIES}"
                    )
                    time.sleep(delay)
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
                    # 컨텍스트 크기 기록 — resume 세션은 매 턴 성장하므로 id 변동과 무관하게
                    # 매번 갱신해 다음 턴 리셋 판단의 최신 값을 유지한다.
                    record_session_size(session_key_val, self._last_context_size)
                break
        finally:
            if _http_cfg:
                try:
                    os.remove(_http_cfg)
                except OSError:
                    pass

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
            # 라운드별 컨텍스트 크기 추적 — 매 assistant 라운드의 입력 컨텍스트
            # (in+cache_read+cache_create)를 갱신해 *마지막* 라운드 값을 남긴다.
            # result 이벤트의 usage 는 라운드 누적이라 세션 크기를 7배 부풀린다(버그).
            # 마지막 라운드 컨텍스트 = 다음 --resume 에서 재생될 트랜스크립트 크기 근사.
            _u = msg.get("usage") or {}
            if _u:
                self._last_context_size = (
                    int(_u.get("input_tokens") or 0)
                    + int(_u.get("cache_read_input_tokens") or 0)
                    + int(_u.get("cache_creation_input_tokens") or 0)
                )
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
                # 지도 봉투(route_map/location_map)를 캡처해 최종 응답 끝에 재주입 예약.
                # CLI 서브프로세스는 결과를 산문으로 요약하며 마커를 흘려버리므로 여기서 붙잡는다.
                if not is_error:
                    try:
                        for tag in _extract_map_tags(result_text):
                            if tag not in self._pending_map_tags:
                                self._pending_map_tags.append(tag)
                    except Exception:
                        pass
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
            # _last_context_size 는 assistant 라운드별로 갱신됨(마지막 라운드 = 세션 크기).
            # result.usage 는 라운드 누적이라 여기서 쓰면 안 된다.
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
                final_content = (final_text or "").strip()
                # 이번 턴에 캡처한 지도 태그를 최종 응답 끝에 재주입 → 프론트 parseMapData 가 렌더.
                if self._pending_map_tags:
                    final_content = (final_content + "\n\n" + "\n".join(self._pending_map_tags)).strip()
                    self._pending_map_tags = []
                out.append(({"type": "final", "content": final_content}, None))

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
    #   MCP execute_ibl 은 deferred(ToolSearch 경유, 2.1.205 실측)인데 네이티브는 eager 라,
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
        # MCP — 가이드 읽기 브리지. in-process 프로바이더(Gemini 등)는 read_guide 를 자기
        # 프로세스에서 직접 갖지만, 아웃오브프로세스인 Claude Code 는 MCP 로만 닿아 가이드 읽기
        # 통로가 없었다(read_guide 호출이 'No such tool' 로 실패→file_find 우회 헛걸음). 이 한 줄이 메운다.
        # ★Claude Code 한정 — IBL 어휘로 승격하지 않으므로 다른 프로바이더 표면엔 영향 없음.
        "mcp__indiebizos__read_guide",
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
    #
    # 도구 이름 정규화: Claude Code 에서 IBL 실행기는 MCP 브리지로 노출되므로 정확한 이름이
    # `mcp__indiebizos__execute_ibl` 다(맨이름 `execute_ibl` 아님). 그런데 공용 프롬프트·해마
    # 용례·system_docs 는 다른 프로바이더 기준이라 맨이름을 수십 번 가르친다 → 모델이 첫 호출에
    # 맨이름을 써 `No such tool available: execute_ibl` → ToolSearch round-trip 낭비.
    # append 는 시스템 프롬프트 *맨 뒤*에 붙으므로, 여기서 정규화 이름을 명시해 앞쪽 priming 을 덮는다.
    # (공용 프롬프트는 손대지 않는다 — 거긴 맨이름이 정답인 프로바이더들이 공유한다.)
    TOOL_POLICY = (
        "\n\n# 도구 정책\n"
        "IBL 실행 도구의 정확한 이름은 `mcp__indiebizos__execute_ibl` 다 — 이 이름 그대로 호출하라. "
        "다른 안내나 과거 용례에 `execute_ibl` 로 줄여 적힌 곳이 있어도, 실제 도구 이름은 "
        "`mcp__indiebizos__execute_ibl` 뿐이다(맨이름 `execute_ibl` 은 존재하지 않아 호출이 실패한다).\n"
        "가이드 읽기 도구의 정확한 이름은 `mcp__indiebizos__read_guide` 다(맨이름 `read_guide` 아님). "
        "공용 프롬프트·IBL 액션 설명이 `read_guide(query=...)` 로 가르치는 곳은 모두 이 도구를 뜻하니, "
        "`mcp__indiebizos__read_guide` 로 호출하라(file_find 로 data/guides 를 뒤지지 말 것 — 이 도구가 가이드 DB를 검색해 본문까지 준다).\n"
        "★이 두 MCP 도구는 이 CLI 에서 **deferred** 다 — 세션 시작 직후엔 스키마가 로드돼 있지 않아, "
        "곧장 호출하면 `No such tool available` 로 한 번 실패한다. 그러니 **이번 턴 첫 IBL/가이드 호출 전에 딱 한 번** "
        "아래 형태로 정확한 풀네임을 실어 `ToolSearch` 로 스키마를 먼저 로드한 뒤, 위 정확한 이름으로 호출하라:\n"
        "`ToolSearch{query: \"select:mcp__indiebizos__execute_ibl,mcp__indiebizos__read_guide\"}`\n"
        "(select 에는 반드시 `mcp__indiebizos__` 풀네임을 써라 — 맨이름 `execute_ibl` 로 찾으면 'no matching deferred tools' 만 나온다.) "
        "resume 로 이어지는 턴이라도 이 프로세스엔 스키마가 새로 로드돼야 하니, 과거에 성공했더라도 이번 턴 첫 호출 전 ToolSearch 를 한 번 하라.\n"
        "파일 읽기·웹 검색·grep 은 네이티브 도구가 아니라 IBL 로 하라. "
        "`Read`/`WebSearch`/`WebFetch`/`Grep`/`Glob` 은 비활성화돼 있다 — 대신 "
        "`mcp__indiebizos__execute_ibl` 로 "
        "`[self:read]`(파일)·`[sense:search_ddg/news/scholar/naver]`(웹검색)·`[sense:crawl]`(웹페이지)·"
        "`[self:grep]`(코드검색) 을 호출하라. "
        "셸·코드 실행(`Bash`)은 그대로 사용 가능하다 — IBL 에 등가물이 없는 탈출구다."
    )

    def _write_system_prompt_file(self) -> Optional[str]:
        """시스템 프롬프트+도구정책을 에이전트별 고정 임시 파일에 쓰고 경로를 반환.

        --append-system-prompt-file 로 넘기기 위함(윈도우 argv 상한 회피 — _build_command 참조).
        에이전트별 고정 경로에 매 호출 덮어써 리트라이 간 재사용하므로 별도 정리가 필요 없다
        (누적되지 않고 덮어써짐). 생성 실패 시 None → 호출 측이 인자 방식으로 폴백.
        """
        text = (self.system_prompt or "") + self.TOOL_POLICY
        safe = re.sub(
            r"[^A-Za-z0-9_.-]", "_",
            str(self.agent_id or self.agent_name or "default"),
        )[:60]
        path = os.path.join(tempfile.gettempdir(), f"claude_code_sys_{safe}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return path
        except OSError as e:
            print(f"[ClaudeCodeProvider] {self.agent_name}: 시스템 프롬프트 파일 생성 실패({e}) → 인자 폴백")
            return None

    def _http_mcp_config_path(self) -> Optional[str]:
        """HTTP MCP config 를 spawn 마다 유니크 temp 파일로 쓴다 (플래그 ON일 때만).

        INDIEBIZOS_MCP_HTTP="1" 이 아니면 None → 호출부에서 stdio(get_mcp_config_path())로 폴백.
        신원(agent_id/project_path)은 config 안 헤더로 실린다. 동시에 여러 에이전트가
        돌 수 있으므로 고정 파일을 덮어쓰면 서로의 신원을 읽는 레이스가 난다 → spawn 마다
        유니크 파일로 쓰고 실행 후 finally 에서 정리한다.
        ★헤더는 ASCII 전용이라 한글 신원은 quote() 로 퍼센트 인코딩(서버가 unquote).
        """
        if os.environ.get("INDIEBIZOS_MCP_HTTP", "0") != "1":
            return None
        headers: Dict[str, str] = {}
        if self.agent_id:
            headers["X-IndieBiz-Agent-Id"] = quote(str(self.agent_id))
        if self.project_path and self.project_path != ".":
            headers["X-IndieBiz-Project-Path"] = quote(str(self.project_path))
        cfg = {"mcpServers": {"indiebizos": {
            "type": "http",
            # ★트레일링 슬래시: backend mount /mcp + 내부 streamable_http_path "/" → /mcp/ 가 직행
            "url": "http://localhost:8765/mcp/",
            "headers": headers,
        }}}
        fd, path = tempfile.mkstemp(prefix="ccmcp_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return path

    def _build_command(
        self,
        mcp_config_path: Optional[str] = None,
        stream: bool = False,
        resume_session_id: Optional[str] = None,
        system_prompt_file: Optional[str] = None,
    ) -> List[str]:
        """공통 CLI 인자 구성 (positional prompt는 호출 측에서 append).

        --no-session-persistence는 일부러 빼놓음 — Claude Code가 디스크에 세션을 저장해야
        다음 호출 시 --resume으로 자기 과거를 이어볼 수 있음.

        --allowed-tools 는 built-in 도구(Bash/Write/Edit 등)를 eager-load + 권한 부여한다.
        ★단, CLI 2.1.205 에서 **MCP 도구(execute_ibl/read_guide)는 --allowed-tools 에 넣어도
        여전히 deferred** 다(allowed=권한이지 schema eager-load 아님, init tools 목록에 안 뜸).
        그래서 첫 사용 전 ToolSearch 1회 왕복이 CLI 구조상 불가피 — TOOL_POLICY 가 모델에게
        "곧장 호출" 대신 "먼저 ToolSearch(풀네임 select) 후 호출" 하도록 안내해 헛발질(No such tool)을 없앤다.
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

        # 시스템 프롬프트 + Claude Code 전용 도구 정책(차단 네이티브 → IBL 등가물 안내).
        # ★파일 경로로 넘긴다(--append-system-prompt-file): 윈도우 명령줄 상한(32,767자)에
        #  ~62K 시스템 프롬프트를 인자로 실으면 [WinError 206]로 실행 자체가 실패한다. 파일
        #  생성이 실패했을 때만 인자 방식으로 폴백(맥 등 상한 큰 OS는 어느 쪽이든 무해).
        if system_prompt_file:
            cmd += ["--append-system-prompt-file", system_prompt_file]
        else:
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
        # ★구독(OAuth) vs API 과금 경로를 코드로 격리한다. 기본은 "구독만" —
        #  .env 의 ANTHROPIC_API_KEY 가 claude 서브프로세스에 새어들어 구독 대신 API 로
        #  과금되는 것을 원천 차단한다(토큰 로딩이 실패해 _effective_token 이 None 인 코너 포함).
        #  명시적으로 API 키(sk-ant-api…)를 준 경우에만 API 과금 경로를 연다.
        #  ANTHROPIC_API_KEY 는 os.environ(.env)에 그대로 남아 *다른* 프로바이더에서는 계속 쓰인다.
        tok = self._effective_token
        if tok and tok.startswith("sk-ant-api"):
            env["ANTHROPIC_API_KEY"] = tok
            env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        else:
            env.pop("ANTHROPIC_API_KEY", None)
            if tok:  # sk-ant-oat… (구독 토큰)
                env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
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
