"""
claude_code.py - Claude Code CLI 프로바이더
IndieBiz OS Core

Claude Code를 indiebizOS의 provider로 노출. 다른 provider와 동일한 인터페이스이므로
시스템 AI·중급·프로젝트 에이전트 어디서든 드롭다운으로 선택 가능.

★몸통은 `cli_provider.CliSubprocessProvider` 에 있다 — 세션 영속·신원 전파·스트림
오케스트레이션·지도 재주입·로그 절단은 아웃오브프로세스 CLI 라면 벤더 무관이라 거기 산다.
이 파일에는 **Claude Code 에만 있는 것**만 남는다: 바이너리 탐지, OAuth/API 과금 격리,
stream-json 이벤트 어휘, --allowed-tools 계열 플래그, 네이티브 도구 정책.

특성:
- 한계비용 0 (Claude Max 플랜 사용 시) — 토큰 기반 과금 안 함
- 강력한 에이전틱 코딩/조사 능력 (Read·Edit·Bash·Grep 내장)
- CLAUDE.md 자동 로드 (cwd 기준)
- 인증: 토큰 → CLAUDE_CODE_OAUTH_TOKEN 또는 ANTHROPIC_API_KEY (subprocess env)

지원 기능:
- IBL 액션 호출: data/claude_code_mcp.json MCP 브리지로 execute_ibl 노출
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

import json
import os
import hashlib
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cli_provider import (
    CliSessionStore,
    CliSubprocessProvider,
    _data_dir,
    # 재수출 — 옛 임포트 경로(`from providers.claude_code import _TOOLUSE_CAP`)를 지킨다.
    _TOOLUSE_CAP,
    _TOOLUSE_CAP_IBL,
    _TOOLRESULT_CAP,
    _TOOLRESULT_CAP_ERROR,
    _extract_map_tags,
    _failure_digest,
    _preview_with_signals,
)

__all__ = [
    "ClaudeCodeProvider",
    "find_claude_binary",
    "load_oauth_token_from_central_config",
    "get_mcp_config_path",
    "load_session_map", "save_session_map", "clear_session_for_agent",
    "load_session_sizes", "save_session_sizes",
    "record_session_size", "clear_session_size",
    "SESSION_RESET_TOKEN_THRESHOLD",
]


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
    """IBL MCP 설정 파일 경로 — 없거나 깨졌으면 이 몸의 값으로 파생 생성 후 반환."""
    from .cli_provider import ensure_mcp_bridge_config
    mcp_path = ensure_mcp_bridge_config()
    return str(mcp_path) if mcp_path else None


# ============ 세션 상태 저장소 ============
# 실체는 cli_provider.CliSessionStore. 아래 모듈 함수들은 옛 임포트 경로를 지키는 얇은 껍질이다
# (api_agents·api_system_ai·cognitive_consciousness 가 clear_session_for_agent 를 부른다).
_STORE = CliSessionStore("claude_code", "ClaudeCodeProvider")

SESSION_RESET_TOKEN_THRESHOLD = CliSubprocessProvider.SESSION_RESET_TOKEN_THRESHOLD


def load_session_map() -> Dict[str, str]:
    return _STORE.load_map()


def save_session_map(m: Dict[str, str]):
    _STORE.save_map(m)


def clear_session_for_agent(session_key: str):
    """특정 agent의 세션 매핑 제거. UI '새 대화' 등에서 호출.

    ★프로바이더 무관 리셋이 필요하면 `providers.clear_cli_sessions_for_agent` 를 쓸 것 —
    이 함수는 Claude Code 매핑만 비운다.
    """
    _STORE.clear_agent(session_key)


def load_session_sizes() -> Dict[str, int]:
    return _STORE.load_sizes()


def save_session_sizes(m: Dict[str, int]):
    _STORE.save_sizes(m)


def record_session_size(session_key: str, size: int):
    """직전 턴의 실측 컨텍스트 토큰 수를 기록 (다음 턴 리셋 판단용)."""
    _STORE.record_size(session_key, size)


def clear_session_size(session_key: str):
    _STORE.clear_size(session_key)


class ClaudeCodeProvider(CliSubprocessProvider):
    """Claude Code CLI를 subprocess로 호출하는 provider."""

    CLI_LABEL = "ClaudeCode"
    CLI_DISPLAY = "Claude Code"
    STATE_PREFIX = "claude_code"
    SESSION_STORE = _STORE

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._effective_token: Optional[str] = None
        self._mcp_temp_path: Optional[str] = None

    # ================= 인증·바이너리 =================

    @classmethod
    def _find_binary(cls) -> Optional[str]:
        return find_claude_binary()

    def _resolve_auth(self) -> str:
        """토큰 우선순위 해소 + 로그용 출처 설명 반환.

        1. provider config의 api_key (단, sk-ant- 형식일 때만 — 다른 provider 키가 폴백으로
           잘못 흘러들어오는 경우 방어)
        2. 중앙 config 파일 (data/claude_code_config.json)의 OAuth 토큰
        """
        provided_key = (self.api_key or "").strip()
        if provided_key.startswith("sk-ant-"):
            self._effective_token = provided_key
            return "config.api_key"

        self._effective_token = load_oauth_token_from_central_config()
        if provided_key and not self._effective_token:
            return "config.api_key (비Anthropic 형식 무시, 중앙 토큰 없음)"
        if provided_key:
            return "중앙 OAuth (config.api_key는 비Anthropic 형식이라 무시)"
        if self._effective_token:
            return "data/claude_code_config.json"
        return "없음"

    def _build_env(self) -> Dict[str, str]:
        """subprocess에 전달할 env 구성.

        - OAuth 토큰 (sk-ant-oat...) → CLAUDE_CODE_OAUTH_TOKEN (Max/Pro 구독 빌링)
        - API 키 (sk-ant-api...) → ANTHROPIC_API_KEY (per-call 빌링)
        - 신원(INDIEBIZOS_*) 은 상위(CliSubprocessProvider)가 채운다.
        """
        env = super()._build_env()
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
        return env

    # ================= 세션 =================

    def _is_session_issue(self, combined: str) -> bool:
        """resume 실패(세션 만료/무효) 판정 — Claude CLI 의 문구."""
        low = (combined or "").lower()
        return ("no conversation found" in low) or (
            "session" in low and ("not found" in low or "invalid" in low)
        )

    # ================= 도구 브리지 =================

    def _mcp_bridge_acquire(self) -> Optional[str]:
        """MCP 브리지: HTTP 우선(플래그 ON일 때) → stdio 폴백."""
        self._mcp_temp_path = self._http_mcp_config_path()
        return self._mcp_temp_path or get_mcp_config_path()

    def _mcp_bridge_release(self, handle: Optional[str]) -> None:
        """HTTP 모드에서 spawn 마다 만든 유니크 temp config 정리 (stdio 경로는 영속 파일)."""
        if self._mcp_temp_path:
            try:
                os.remove(self._mcp_temp_path)
            except OSError:
                pass
            self._mcp_temp_path = None

    def _http_mcp_config_path(self) -> Optional[str]:
        """HTTP MCP config 를 spawn 마다 유니크 temp 파일로 쓴다 (플래그 ON일 때만).

        INDIEBIZOS_MCP_HTTP="1" 이 아니면 None → 호출부에서 stdio(get_mcp_config_path())로 폴백.
        신원(agent_id/project_path)은 config 안 헤더로 실린다. 동시에 여러 에이전트가
        돌 수 있으므로 고정 파일을 덮어쓰면 서로의 신원을 읽는 레이스가 난다 → spawn 마다
        유니크 파일로 쓰고 실행 후 정리한다.
        """
        if os.environ.get("INDIEBIZOS_MCP_HTTP", "0") != "1":
            return None
        cfg = {"mcpServers": {"indiebizos": {
            "type": "http",
            # ★트레일링 슬래시: backend mount /mcp + 내부 streamable_http_path "/" → /mcp/ 가 직행
            "url": "http://localhost:8765/mcp/",
            "headers": self._identity_headers(),
        }}}
        fd, path = tempfile.mkstemp(prefix="ccmcp_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return path

    def _image_prompt_prefix(self, image_paths: List[str]) -> str:
        img_lines = "\n".join(f"첨부 이미지 경로: {p}" for p in image_paths)
        return (
            f"{img_lines}\n"
            f"(위 이미지 파일을 Read 도구로 읽어 시각 내용을 확인할 수 있다)\n\n"
        )

    # ================= 도구 정책 =================

    # eager 도구 목록(권한 + `--tools` 내장 집합의 원천).
    # --allowed-tools 는 restrictive이므로 Claude Code가 흔히 쓰는 built-in + MCP IBL을 명시.
    # 이 목록에 없는 도구는 사용 불가 (트레이드오프: 속도 향상 vs 도구 범위 제한).
    # 더 많은 도구가 필요해지면 여기에 추가.
    # 원칙: IBL 어휘를 *중복(그림자)* 하는 네이티브는 여기서 빼고 DISALLOWED 로 하드 차단한다.
    #   중복 네이티브를 남기면 모델이 IBL 대신 그쪽으로 새는 회귀가 생긴다(Read·WebSearch 실측 누수).
    #   (MCP deferred 문제는 `--tools` 로 해소 — EAGER_BUILTIN_TOOLS 주석 참조.)
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
        # MCP — 턴 안 재규정 브리지(reframe.py). read_guide 와 같은 이유로 MCP 로만 닿는다.
        "mcp__indiebizos__reframe",
    ]

    # `--tools` 에 실을 내장 도구 = EAGER_TOOLS 중 내장(MCP 이름 제외). 2026-09-04 실측(CLI 2.1.258):
    # `--allowed-tools` 만 주면 내장 36개 + ToolSearch 가 뜨고 MCP 두 도구는 deferred 라 매 에피소드
    # 첫 왕복이 ToolSearch(스키마 로드)였다. `--tools` 로 내장을 이 목록으로 좁히면 ToolSearch 자체가
    # 사라지고 MCP 두 도구가 init 부터 eager 로 뜬다(왕복 1회 절감 + 왕복당 컨텍스트 45K→20K 토큰).
    # 환경변수(ENABLE_TOOL_SEARCH)는 쓰지 않는다 — 플래그 하나가 더 좁고 이식성 있다.
    EAGER_BUILTIN_TOOLS = [t for t in EAGER_TOOLS if not t.startswith("mcp__")]

    # 명시적으로 차단할 도구 — 우회 로드되더라도 호출 거부됨.
    # AskUserQuestion: indiebizOS UI 미연결, 응답 채널 없음 → IBL [user:ask] 사용.
    # 아래 네이티브들은 IBL 액션과 1:1 중복이라, 모델이 IBL 대신 새지 못하게 강제로 막는다.
    DISALLOWED_TOOLS = [
        "AskUserQuestion",          # → IBL [user:ask] / [self:ask_user]
        "Read",                     # → [self:read]
        "Grep", "Glob",             # → [self:grep]
        "WebSearch",                # → [sense:search]{source: ddg/naver/gnews/...}
        "WebFetch",                 # → [sense:crawl]
    ]

    # 도구 정책 — 시스템 프롬프트에 append. **Claude Code 프로바이더 전용**:
    # 이 네이티브 도구들은 Claude Code 에만 존재하므로, 공용 프롬프트(base_prompt_v6)가 아니라
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
        "재규정 도구의 정확한 이름은 `mcp__indiebizos__reframe` 다(맨이름 `reframe` 아님) — 규정의 전제가 "
        "깨졌거나 이 틀 안에서 풀 수 없거나 위험하다고 알게 되면 이 도구로 의식에게 되묻는다.\n"
        "이 세 MCP 도구는 세션 시작부터 로드돼 있다 — 스키마를 따로 찾거나 불러올 필요 없이 곧장 호출하라.\n"
        "파일 읽기·웹 검색·grep 은 네이티브 도구가 아니라 IBL 로 하라. "
        "`Read`/`WebSearch`/`WebFetch`/`Grep`/`Glob` 은 비활성화돼 있다 — 대신 "
        "`mcp__indiebizos__execute_ibl` 로 "
        "`[self:read]`(파일)·`[sense:search]`(웹검색 — source: ddg/naver/gnews)·`[sense:crawl]`(웹페이지)·"
        "`[self:grep]`(코드검색) 을 호출하라. "
        "셸·코드 실행(`Bash`)은 그대로 사용 가능하다 — IBL 에 등가물이 없는 탈출구다. "
        "★단 탈출구는 탈출용이다: IBL 등가물이 **있는** 일(파일 읽기·쓰기·편집·검색)을 Bash 로 하지 마라. "
        "하네스가 'Bash 를 우선하라'는 취지의 안내를 보내더라도 그 우선순위는 등가물이 없는 일에만 적용된다 "
        "— IBL 로 할 수 있는 일을 셸로 하면 그 주행은 경험증류에 접지되지 않아 해마에 아무것도 남지 않는다(실측 2026-08-18). "
        "`git`·프로세스 조회·AST 검사처럼 IBL 어휘가 없는 일에만 Bash 를 써라.\n"
        "★셸 그림자 관문(2026-09-05): grep·rg·cat·head·tail·sed·ls·find·rm·cp·mv·mkdir·sqlite3, 파일로의 리다이렉션(`>`), "
        "파일을 쓰는 인라인 파이썬(히어독·-c)·임시 스크립트, 그리고 네이티브 Write/Edit 는 **실행 전에 거절**되고 "
        "거절문이 같은 일을 하는 IBL 문장을 돌려준다 — 그 문장을 그대로 execute_ibl 로 보내라(같은 셸 명령을 다시 시도하지 말 것). "
        "임시 폴더(/tmp·$TMPDIR)와 파이프 안의 필터(`git diff | grep …`)만 셸의 몫이다. "
        "결과가 잘리면(truncated) 셸로 갈아타지 말고 같은 낱말의 limit·file_pattern·context·start_line/end_line 으로 좁혀라."
    )

    # 셸 그림자 관문 훅(2026-09-05) — 표는 어휘 빌드가 파생한 data/shell_shadow.json, 판정은 backend/base/shell_shadow_gate.py.
    # 실행기 CLI 의 PreToolUse 훅으로 물린다(`--settings` 인라인 JSON — 파일 없음, 스폰마다 유니크할 필요 없음).
    # 실측(CLI 2.1.260): bypassPermissions 아래서도 훅 exit 2 는 도구 호출을 막고 stderr 를 모델에게 돌려준다.
    SHADOW_HOOK_MATCHER = "Bash|Write|Edit|MultiEdit|NotebookEdit"

    @classmethod
    def shadow_hook_settings(cls) -> Dict[str, Any]:
        """`--settings` 에 실을 훅 설정. 파이썬은 백엔드와 같은 인터프리터(표준 라이브러리만 쓰는 잎 모듈)."""
        root = Path(__file__).resolve().parents[2]
        gate = root / "backend" / "base" / "shell_shadow_gate.py"
        command = f'"{sys.executable}" "{gate}" "{root}"'
        return {"hooks": {"PreToolUse": [{
            "matcher": cls.SHADOW_HOOK_MATCHER,
            "hooks": [{"type": "command", "command": command, "timeout": 15}],
        }]}}

    # ================= 세션 =================

    @classmethod
    def tool_policy_fingerprint(cls) -> str:
        """도구 집합·정책의 지문 — EAGER/DISALLOWED 목록 + TOOL_POLICY 본문의 md5 앞 8자."""
        blob = ("|".join(cls.EAGER_TOOLS) + "||" + "|".join(cls.DISALLOWED_TOOLS) + "||" + cls.TOOL_POLICY
                + "||hook:" + cls.SHADOW_HOOK_MATCHER)
        return hashlib.md5(blob.encode("utf-8")).hexdigest()[:8]

    def _get_session_key(self) -> str:
        """세션 키에 도구 정책 지문을 붙인다 (codex 의 시스템 프롬프트 해시와 같은 선례).

        이유(2026-09-04, ep2811 실측): `--tools` 로 ToolSearch 를 없애고 TOOL_POLICY 에서 그 지시를
        지운 뒤에도, resume 된 세션은 옛 트랜스크립트(ToolSearch 를 시키던 정책 + 실제 ToolSearch
        호출들)를 다시 재생해 첫 왕복을 존재하지 않는 도구 호출로 날렸다. 시스템 프롬프트는 매 턴
        다시 실리지만 **습관은 트랜스크립트에 산다**. 도구 집합·정책이 바뀌면 키가 바뀌어 옛
        세션이 안 잡히고 자동으로 fresh 가 된다. 옛 키 잔재는 CliSessionStore.clear_agent 의
        `키#…` 접두 스윕이 '새 대화' 때 함께 지운다.
        """
        base = super()._get_session_key()
        return f"{base}#{self.tool_policy_fingerprint()}"

    # ================= 명령 조립 =================

    def _build_command(
        self,
        mcp_config_path: Optional[str] = None,
        stream: bool = False,
        resume_session_id: Optional[str] = None,
        system_prompt_file: Optional[str] = None,
        tools_mode: Optional[str] = None,
    ) -> List[str]:
        """공통 CLI 인자 구성 (유저 프롬프트는 stdin 으로 간다).

        tools_mode(2026-08-21, 원샷 다이어트): None=평소(eager 내장 도구+MCP) / "none"=`--tools ""`
        (도구 스키마 0 — 원샷 텍스트 호출) / "read"=`--tools Read`(원샷이 이미지를 봐야 할 때만).
        실측: 같은 한 줄 질문이 평소 29.5K 컨텍스트·$0.30, 도구 없음 3.9K·$0.04.

        --no-session-persistence는 일부러 빼놓음 — Claude Code가 디스크에 세션을 저장해야
        다음 호출 시 --resume으로 자기 과거를 이어볼 수 있음.

        --allowed-tools 는 권한(permission)이고 스키마 로드가 아니다 — CLI 2.1.205~258 실측:
        allowed 만 주면 내장 36개+ToolSearch 가 eager, MCP 두 도구는 deferred 라 매 에피소드 첫
        왕복이 ToolSearch 였다. `--tools EAGER_BUILTIN_TOOLS` 로 내장을 좁히면(2026-09-04) ToolSearch
        가 사라지고 MCP 도구가 init 부터 뜬다. 그래서 TOOL_POLICY 는 "곧장 호출"이라고 말한다.
        """
        cmd = [
            self._binary_path,
            "--print",
            "--output-format", "stream-json" if stream else "json",
            # 비대화 모드에서 권한 프롬프트로 멈추지 않도록 — MCP 호출은 indiebizOS 자체 게이트
            "--permission-mode", "bypassPermissions",
        ]
        if tools_mode == "none":
            cmd += ["--tools", ""]                  # 원샷: 도구 스키마 0
        elif tools_mode == "read":
            cmd += ["--tools", "Read"]              # 원샷+이미지: 파일 읽기만
        if tools_mode:
            # 원샷은 CLAUDE.md·settings 도 안 읽는다(모델·권한은 인자로 명시됨) — cwd 의
            # 프로젝트 지침 ~3.4K 가 "2문장 요약해" 에 따라붙던 것(실측 8.5K→5.1K).
            cmd += ["--setting-sources", ""]
        else:
            cmd += [
                # 내장 도구 집합 자체를 좁힌다 → ToolSearch 소멸 + MCP eager (위 docstring)
                "--tools", ",".join(self.EAGER_BUILTIN_TOOLS),
                # 권한: 내장 + MCP IBL 브리지
                "--allowed-tools", ",".join(self.EAGER_TOOLS),
                # 명시 차단: indiebizOS UI와 연결되지 않은 도구 (AskUserQuestion 등)
                "--disallowed-tools", ",".join(self.DISALLOWED_TOOLS),
                # 셸 그림자 관문 — Bash·Write·Edit 호출 전에 어휘 파생표로 판정(shadow_hook_settings 참조)
                "--settings", json.dumps(self.shadow_hook_settings(), ensure_ascii=False),
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
            cmd += ["--append-system-prompt",
                    (self.system_prompt or "") + ("" if tools_mode else self.TOOL_POLICY)]

        # MCP 브리지 (IBL execute_ibl 등) — 도구 없는 원샷은 브리지도 안 세운다(프로세스 기동 비용)
        if mcp_config_path and tools_mode is None:
            cmd += ["--mcp-config", mcp_config_path]

        return cmd

    # ================= 이벤트 번역 =================

    def _stream_error_text(self, event: Dict) -> Optional[str]:
        if event.get("type") == "result" and event.get("is_error"):
            return str(event.get("result") or "")
        return None

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
            # 모델 응답 1건 = 실행 라운드 1건 — 스텝 원장에 찍는다(cli_provider._note_model_round 주석).
            # 이 줄이 없던 동안 Claude Code 주행의 execution 라운드는 0건으로 남았다(2026-09-06 실측).
            self._note_model_round(msg.get("model"))
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
            # 마지막 턴의 stop_reason 포착 (2026-08-29 ⑫) — max_tokens 절단이 종전엔
            # 여기서 버려져 침묵했다(실측 ep2307: 서로 다른 두 세대가 같은 ~11K자에서
            # 문장 중간 절단, 표지 없음 → GoalEval 재실행이 전체 재작성→재절단 루프).
            if msg.get("stop_reason"):
                self._last_stop_reason = msg.get("stop_reason")
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
                    self._log_tool_use(tool_name, tool_input)
                    out.append((
                        {
                            "type": "tool_start",
                            "id": block.get("id", ""),
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
                self._log_tool_result(result_text, is_error)
                out.append((
                    {
                        "type": "tool_result",
                        "id": block.get("tool_use_id", ""),  # start↔result 페어링 키
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
            # 캐시 통계 — prefix 분리 작업의 실효성 측정.
            # cache_read = 캐시 hit으로 즉시 처리된 input (저렴, 빠름)
            # cache_create = 새로 캐시에 쓰인 input (write 비용)
            cache_read = int(usage.get("cache_read_input_tokens") or 0)
            cache_create = int(usage.get("cache_creation_input_tokens") or 0)
            # _last_context_size 는 assistant 라운드별로 갱신됨(마지막 라운드 = 세션 크기).
            # result.usage 는 라운드 누적이라 *세션 크기*로는 쓰면 안 되지만, 턴 원장이
            # 원하는 것이 바로 그 누적(이 턴의 모델 소요 합)이다.
            # ★2026-09-06 실측: 여기가 cache_read·cache_create 를 안 넘겨 Claude Code 턴의
            # [턴비용]·해마 avg_tokens·turn_budget 고정물이 캐시분을 못 봤다 — 16일치
            # 캐시 읽기 13.99억 토큰(전체 비용의 95%)이 원장에 0 으로 남았고, 토큰
            # 선택압이 가장 큰 비용을 못 본 채 돌았다. Anthropic 은 input_tokens 에 캐시분이
            # 빠져 있으므로 원장의 input 은 전체 프롬프트(=input+cache_read+cache_create)로
            # 적어 다른 벤더와 같은 뜻으로 맞춘다(providers/anthropic.py 와 같은 규약).
            self.metrics.record_usage(latency_ms, usage)   # 규약은 base.normalize_usage 한 곳
            err_flag = " (error)" if event.get("is_error") else ""
            cache_info = (f" cache_read={cache_read} cache_create={cache_create}"
                          if (cache_read or cache_create) else "")
            self._log(
                f"result{err_flag} {latency_ms:.0f}ms "
                f"in={input_tokens} out={output_tokens}{cache_info}"
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
                _truncated = self._last_stop_reason == "max_tokens"
                _fin = {"type": "final", "content": self._finalize_text((final_text or "").strip())}
                if _truncated:
                    _fin["truncated_output"] = True
                out.append((_fin, None))

        return out
