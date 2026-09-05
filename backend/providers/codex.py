"""
codex.py - Codex CLI 프로바이더
IndieBiz OS Core

OpenAI Codex CLI 를 indiebizOS 의 provider 로 노출. `claude_code` 와 같은 자리
(아웃오브프로세스 CLI)이므로 몸통은 `cli_provider.CliSubprocessProvider` 를 공유하고,
여기에는 Codex 에만 있는 것만 둔다: 바이너리 탐지, ChatGPT 구독 인증, `codex exec --json`
이벤트 어휘(thread/turn/item), `-c` 인라인 설정 오버라이드, 도구 정책.

특성:
- 한계비용 0 (ChatGPT 구독 사용 시) — `~/.codex/auth.json` 의 로그인을 그대로 쓴다
- 인증: 구독 로그인이 기본. `OPENAI_API_KEY` 형식 키를 명시로 준 경우에만 API 과금 경로.
- 도구 브리지: MCP (stdio/HTTP 둘 다 지원) — `mcp_server.py` 를 claude_code 와 공유

★claude_code 와 다른 점 (설계 판단, 실측 근거 있음):
1. **시스템 프롬프트를 붙이는 자리가 없다.** Codex 에는 `--append-system-prompt` 등가물이
   없다(`model_instructions_file` 은 *교체*라 Codex 자신의 도구 사용 지침까지 날린다).
   그래서 fresh 턴의 프롬프트 머리에 실어 보내고, resume 턴에는 안 보낸다 — 스레드가
   이미 갖고 있다. 시스템 프롬프트가 바뀌면 세션 키가 바뀌어(_get_session_key 의 해시
   접미) 자동으로 fresh 로 끊긴다. 안 그러면 옛 지침을 문 스레드가 영영 이어진다.
2. **네이티브 도구를 골라 끌 수 없다.** Claude Code 는 `--disallowed-tools` 로 Read·Grep·
   WebSearch 를 막아 IBL 등가물을 강제하지만, Codex 의 파일 읽기·검색은 전부 shell 하나로
   들어온다 — shell 을 막으면 Codex 가 아무것도 못 한다. 그래서 여기서 하드 차단은
   web_search(설정으로 끔) 하나뿐이고, 나머지는 TOOL_POLICY 의 **문장**이 감당한다.
   즉 어휘 누수(IBL 대신 셸로 파일을 읽는 것) 방어가 claude_code 보다 구조적으로 약하다.
   누수가 실측되면 처방은 프롬프트 강화가 아니라 `[self:*]` 쪽 관측(episode_log) 으로 센 뒤
   판정할 것 — 여기 문장을 계속 붙이는 건 no_temporary_patches 위반이다.

config 예시 (data/system_ai_config.json 등):
  {
    "provider": "codex",
    "model": "gpt-5.6-sol:high", // `슬러그` 또는 `슬러그:추론강도` — _model_and_effort 참조
    "apiKey": ""                 // 비우면 ChatGPT 구독 로그인(~/.codex/auth.json) 사용
  }

모델 슬러그와 지원 추론강도의 **정본은 우리가 아니라 Codex** 다 —
`~/.codex/models_cache.json`(원격에서 갱신되는 캐시)에 산다. 여기에 목록을 베껴 두면
모델이 은퇴하거나 새로 나올 때 낡는다([[vision-gear-neutralization]] 과 같은 부류).
지금 무엇을 쓸 수 있는지는 그 파일을 읽어 볼 것.
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cli_provider import CliSessionStore, CliSubprocessProvider, _data_dir

__all__ = [
    "CodexProvider",
    "find_codex_binary",
    "clear_session_for_agent",
]


def _codex_home() -> Path:
    """Codex 의 상태 뿌리 (~/.codex 또는 CODEX_HOME)."""
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


# 롤아웃 꼬리를 몇 바이트나 읽을지 — 마지막 token_count 는 파일 끝에서 1KB 안쪽에 있다
# (실측 2026-08-31: 77MB 파일에서 EOF−787B). 256KB 면 여유가 크다.
_ROLLOUT_TAIL_BYTES = 256 * 1024


def read_thread_usage(thread_id: str) -> Optional[Dict[str, int]]:
    """스레드의 **현재 컨텍스트**와 스레드 누적 입력을 Codex 자신의 롤아웃에서 읽는다.

    왜 필요한가(실측 2026-08-31): `turn.completed` 의 `usage` 는 그 턴의 컨텍스트가 아니라
    스레드가 살아온 **모든 라운드의 입력 합계**(`total_token_usage`)다. 도구를 24번 쓴 턴은
    in=3,195,716 으로 보고되지만 실제 마지막 라운드 컨텍스트는 144,266 이었다. 이 합계를
    세션 크기로 오인하면 멀쩡한 세션이 매번 끊긴다(ep2442~2485 에서 19턴 중 7턴 오리셋).
    진짜 값은 롤아웃의 `token_count` 이벤트에 `last_token_usage` 로 들어 있다.

    Returns: {"context": 마지막 라운드 입력, "total": 스레드 누적 입력,
              "total_cached": 스레드 누적 캐시 적중 입력, "total_output": 스레드 누적 출력,
              "window": 모델 컨텍스트 창} — 못 읽으면 None (추정하지 않는다).
    누적 셋은 전부 턴 비용의 **기준선**이다(2026-09-06 실측: 롤아웃 대조에서 입력·캐시·출력이
    모두 턴을 넘어 단조 증가 — 출력 14→212→305). 입력만 빼고 출력·캐시를 누적 그대로 적으면
    작은 resume 턴이 in=0 out=235 처럼 지난 턴 출력을 제 몫으로 신고한다.
    """
    if not thread_id:
        return None
    try:
        hits = sorted(
            _codex_home().glob(f"sessions/**/rollout-*-{thread_id}.jsonl"),
            key=lambda q: q.stat().st_mtime, reverse=True)
        if not hits:
            return None
        path = hits[0]
        size = path.stat().st_size
        with open(path, "rb") as fh:
            if size > _ROLLOUT_TAIL_BYTES:
                fh.seek(size - _ROLLOUT_TAIL_BYTES)
                fh.readline()          # 잘린 첫 줄 버리기
            tail = fh.read()
        info = None
        for line in reversed(tail.splitlines()):
            if b'"token_count"' not in line:
                continue
            try:
                payload = json.loads(line.decode("utf-8", "replace")).get("payload") or {}
            except (ValueError, AttributeError):
                continue
            cand = payload.get("info") or {}
            if cand.get("last_token_usage"):
                info = cand
                break
        if not info:
            return None
        total = info.get("total_token_usage") or {}
        return {
            "context": int((info["last_token_usage"] or {}).get("input_tokens") or 0),
            "total": int(total.get("input_tokens") or 0),
            "total_cached": int(total.get("cached_input_tokens") or 0),
            "total_output": int(total.get("output_tokens") or 0),
            "window": int(info.get("model_context_window") or 0),
        }
    except OSError:
        return None


def find_codex_binary() -> Optional[str]:
    """codex CLI 위치 탐지 (크로스플랫폼).

    PATH → 아래 후보 순. 후보는 **OS 분기 없이 전부 나열**한다 — 공용 이음매
    `common.platform_utils.find_binary` 가 `shutil.which`(윈도우 .exe 자동) 뒤에
    후보를 `isfile` 로 걸러 주므로, 남의 OS 경로는 그냥 안 맞을 뿐이다.
    (날 `os.name` 분기를 두면 OS-가드가 이 파일을 이음매로 선언하라고 요구한다 —
    실제로는 이음매가 필요 없는 자리라 분기를 없애는 쪽이 맞다.)

    ★데스크톱 앱 번들 폴백이 필요한 이유(실측 2026-08-30): 맥에서 `codex` 는 PATH 에 없고
    ChatGPT.app 안에만 있다 — claude 의 데스크톱 번들 폴백과 같은 부류의 함정이다.
    이 폴백이 없으면 init_client 가 False → 사용자에겐 '인증 없음'으로 보인다.
    ★윈도우 경로는 미검증이다(맥에서만 실측). 윈도우에서 못 찾으면 PATH 설치를 안내할 것.
    """
    from common.platform_utils import find_binary

    candidates: List[str] = [
        # macOS — ChatGPT 데스크톱 앱 동봉 (실측 경로)
        "/Applications/ChatGPT.app/Contents/Resources/codex",
        str(Path.home() / "Applications" / "ChatGPT.app" / "Contents" / "Resources" / "codex"),
    ]
    # Windows — 환경변수가 없는 OS 에서는 후보가 안 생긴다(분기 없이 자연 소거)
    for var in ("LOCALAPPDATA", "PROGRAMFILES", "APPDATA"):
        base = os.environ.get(var)
        if base:
            candidates.append(str(Path(base) / "Programs" / "ChatGPT" / "resources" / "codex.exe"))
            candidates.append(str(Path(base) / "ChatGPT" / "resources" / "codex.exe"))

    return find_binary("codex", extra_paths=candidates)


def _stdio_bridge_command() -> Optional[List[str]]:
    """stdio MCP 브리지의 [command, *args].

    ★파일 이름이 `claude_code_mcp.json` 인 것은 역사일 뿐이다 — 내용(= mcp_server.py 를
    어떻게 띄우는가)은 프로바이더 무관이라 CLI 프로바이더들이 **한 파일을 공유**한다.
    두 벌로 갈라 두면 경로가 바뀔 때 한쪽만 고쳐져 조용히 죽는다.
    """
    from .cli_provider import ensure_mcp_bridge_config
    path = ensure_mcp_bridge_config()
    if not path or not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        srv = ((cfg.get("mcpServers") or {}).get("indiebizos") or {})
        cmd = srv.get("command")
        if not cmd:
            return None
        return [str(cmd)] + [str(a) for a in (srv.get("args") or [])]
    except (json.JSONDecodeError, OSError, AttributeError):
        return None


def _toml_str(s: str) -> str:
    """TOML 기본 문자열 리터럴 (역슬래시·따옴표 이스케이프)."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_inline_table(d: Dict[str, str]) -> str:
    """TOML 인라인 테이블 — `-c key={ "a" = "b" }` 로 넘기기 위함."""
    inner = ", ".join(f"{_toml_str(k)} = {_toml_str(v)}" for k, v in d.items())
    return "{ " + inner + " }"


_STORE = CliSessionStore("codex", "CodexProvider")


def clear_session_for_agent(session_key: str):
    """특정 agent의 Codex 세션 매핑 제거.

    ★프로바이더 무관 '새 대화'는 `providers.clear_cli_sessions_for_agent` 를 쓸 것.
    """
    _STORE.clear_agent(session_key)


class CodexProvider(CliSubprocessProvider):
    """Codex CLI(`codex exec`)를 subprocess로 호출하는 provider."""

    CLI_LABEL = "Codex"
    CLI_DISPLAY = "Codex"
    STATE_PREFIX = "codex"
    SESSION_STORE = _STORE

    # resume 실패 문구 (실측 2026-08-30):
    #   `Error: thread/resume: thread/resume failed: no rollout found for thread id <uuid> (code -32600)`
    # 'thread/resume' 만으로도 충분하지만, 문구가 바뀔 때를 대비해 두 갈래를 다 본다.
    SESSION_ISSUE_MARKERS = ("no rollout found", "thread/resume")

    # 도구 브리지의 MCP 서버 이름. Codex 가 모델에게 노출하는 실명은 `mcp__<server>__<tool>`
    # 이다 — claude_code 와 **같은 형태**다(실측 2026-08-30 연기시험: 모델이 자기 도구 목록을
    # `mcp__indiebizos__execute_ibl` 로 보고했다). 이벤트의 server/tool 필드에는 `mcp__`
    # 접두가 없으므로 _tool_name 이 다시 붙여 로그 실명을 CLI 양쪽에서 일치시킨다
    # (vocab_crystallization 이 두 프로바이더의 로그를 같은 잣대로 세려면 실명이 같아야 한다).
    MCP_SERVER_NAME = "indiebizos"
    MCP_TOOL_PREFIX = "mcp__indiebizos__"

    # Codex 의 추론강도 어휘 (`model_reasoning_effort`). 모델마다 지원 범위가 다르다 —
    # 실측 2026-08-31 `~/.codex/models_cache.json`: sol·terra 는 ultra 까지, luna 는 max 까지,
    # gpt-5.5/5.4 계열은 xhigh 까지. 여기서는 **철자만** 검사하고 모델별 지원 여부는 Codex 가
    # 판정하게 둔다 — 카탈로그는 원격에서 갱신되는 캐시라 우리가 베끼면 낡는다
    # (모델명 하드코딩이 은퇴로 죽는 것과 같은 부류).
    REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max", "ultra")

    # 리셋 임계는 **모델 창에서 파생**한다. 상속받는 300K(2026-09-06, 옛 500K)는 창 1M 짜리 Claude 기준이라
    # Codex(창 272K, 실효 95% = 258.4K)에서는 창보다 커서 관문이 영영 안 걸린다 — 실측
    # 2026-08-31 스토리텔러 스레드는 한 턴에 229,322/258,400(89%)까지 찼는데도 조용했다.
    # 창의 절반에서 끊는 이유는 claude_code 와 같다(비용·지연·낡은 tool_result 희석).
    # 창 값의 정본은 우리가 아니라 `~/.codex/models_cache.json` 이다(모델명 하드코딩 금지).
    WINDOW_RESET_RATIO = 0.5
    FALLBACK_CONTEXT_WINDOW = 272_000

    @property
    def SESSION_RESET_TOKEN_THRESHOLD(self) -> int:      # noqa: N802 (상속 상수 자리)
        window = self._observed_window or self._catalog_context_window()
        return int(window * self.WINDOW_RESET_RATIO)

    def _catalog_context_window(self) -> int:
        """models_cache.json 에서 현재 슬러그의 실효 컨텍스트 창을 읽는다."""
        try:
            slug, _ = self._model_and_effort()
            cache = json.loads(
                (_codex_home() / "models_cache.json").read_text(encoding="utf-8"))
            for entry in cache.get("models") or []:
                if entry.get("slug") != slug:
                    continue
                window = int(entry.get("context_window") or 0)
                pct = int(entry.get("effective_context_window_percent") or 100)
                if window:
                    return window * pct // 100
        except (OSError, ValueError, TypeError):
            pass
        return self.FALLBACK_CONTEXT_WINDOW

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._effective_key: Optional[str] = None
        # item.started 로 이미 tool_start 를 낸 아이템 id — item.completed 에서 중복 방출 방지.
        # ★턴마다 비운다(_reset_turn_state): Codex 의 아이템 id 는 `item_0`·`item_1` 로
        #   매 턴 처음부터 다시 매겨진다 — 잔재를 남기면 다음 턴의 같은 id 가 '이미 냈다'로
        #   오인돼 도구 호출 헤더가 통째로 사라진다.
        self._started_items: set = set()
        # 이 턴이 시작될 때의 스레드 누적 입력 — turn.completed 의 누적 합계에서 빼야
        # '이 턴이 쓴 토큰'이 나온다 (resume 스레드는 지난 턴들까지 합산돼 오기 때문).
        self._turn_base_total: int = 0
        # 같은 기준선의 캐시 적중·출력 몫 — 셋 다 스레드 생애 누적이라 셋 다 빼야 한다.
        self._turn_base_cached: int = 0
        self._turn_base_output: int = 0
        # 롤아웃에서 읽은 모델 컨텍스트 창 (리셋 임계의 근거)
        self._observed_window: int = 0

    # ================= 인증·바이너리 =================

    @classmethod
    def _find_binary(cls) -> Optional[str]:
        return find_codex_binary()

    def _resolve_auth(self) -> str:
        """인증 자료 해소.

        Codex 의 기본은 ChatGPT 구독 로그인(`~/.codex/auth.json`)이라 키가 필요 없다
        (model_resolver._NO_KEY_PROVIDERS 에 등록된 이유). 명시로 OpenAI 키를 준 경우에만
        API 과금 경로를 연다 — claude_code 의 구독/API 격리와 같은 규칙이다.
        """
        provided = (self.api_key or "").strip()
        if provided.startswith("sk-"):
            self._effective_key = provided
            return "config.api_key (OpenAI API 과금)"
        self._effective_key = None
        auth_path = _codex_home() / "auth.json"
        if provided:
            return "ChatGPT 구독 (config.api_key 는 비OpenAI 형식이라 무시)"
        return "ChatGPT 구독 (~/.codex/auth.json)" if auth_path.exists() else "없음"

    def _build_env(self) -> Dict[str, str]:
        """subprocess env — 신원(INDIEBIZOS_*)은 상위가 채우고, 여기선 과금 경로만 격리한다.

        ★claude_code 와 같은 사고 방어: `.env` 의 OPENAI_API_KEY 가 codex 서브프로세스에
        새어들면 구독 대신 API 로 과금된다. 명시로 키를 준 경우에만 그 경로를 연다.
        (OPENAI_API_KEY 는 os.environ 에 그대로 남아 *다른* 프로바이더에서는 계속 쓰인다.)
        """
        env = super()._build_env()
        if self._effective_key:
            env["OPENAI_API_KEY"] = self._effective_key
        else:
            env.pop("OPENAI_API_KEY", None)
            env.pop("CODEX_API_KEY", None)
        return env

    def _reset_turn_state(self) -> None:
        self._started_items.clear()
        self._turn_base_total = 0
        self._turn_base_cached = 0
        self._turn_base_output = 0

    def _measure_context_size(self, session_id: str) -> Optional[int]:
        """세션 크기를 Codex 의 롤아웃에서 실측한다 (read_thread_usage 참조).

        같은 읽기로 이 턴의 비용 기준선(_turn_base_total)도 잡는다 — 두 값이 같은
        파일의 같은 이벤트에서 나오므로 따로 저장해 둘 상태가 없다.
        """
        usage = read_thread_usage(session_id)
        if not usage:
            self._log(f"세션 {session_id[:8]}… 롤아웃을 못 읽음 — 컨텍스트 미측정")
            return None
        self._turn_base_total = usage["total"]
        self._turn_base_cached = usage.get("total_cached", 0)
        self._turn_base_output = usage.get("total_output", 0)
        if usage["window"]:
            self._observed_window = usage["window"]
        return usage["context"] or None

    # ================= 세션 =================

    def _get_session_key(self) -> str:
        """세션 키에 시스템 프롬프트 해시를 붙인다 (Codex 전용).

        이유: Codex 는 시스템 프롬프트를 fresh 턴의 프롬프트 머리로만 받는다(모듈 docstring
        ①). 프롬프트가 바뀌었는데 옛 스레드를 resume 하면 **영영 옛 지침으로 산다** —
        claude_code 는 매 턴 `--append-system-prompt` 로 다시 실어 이 문제가 없다.
        키에 해시를 섞으면 프롬프트가 바뀐 순간 저장된 세션이 안 잡혀 자동으로 fresh 가 된다.
        (옛 키의 잔재는 CliSessionStore.clear_agent 의 접두 스윕이 '새 대화' 때 함께 지운다.)
        """
        base = super()._get_session_key()
        digest = hashlib.md5((self.system_prompt or "").encode("utf-8")).hexdigest()[:8]
        return f"{base}#{digest}"

    # ================= 도구 브리지 =================

    def _mcp_bridge_acquire(self) -> Optional[str]:
        """Codex 는 브리지를 `-c` 인라인 오버라이드로 넘긴다 — 임시 파일이 없다.

        핸들로는 전송 방식만 돌려준다("http"/"stdio"/None). 실제 인자 조립은 _build_command.
        ★사용자의 `~/.codex/config.toml` 은 건드리지 않는다: 그 파일은 ChatGPT 데스크톱 앱이
        관리 중이고(플러그인·프로젝트 신뢰 목록), `codex mcp add` 로 쓰면 우리 브리지가
        사용자의 대화형 Codex 에도 영구히 붙는다.
        """
        if os.environ.get("INDIEBIZOS_MCP_HTTP", "0") == "1":
            return "http"
        return "stdio" if _stdio_bridge_command() else None

    def _mcp_bridge_release(self, handle: Optional[str]) -> None:
        return None  # 임시 파일 없음

    def _bridge_config_args(self, transport: Optional[str]) -> List[str]:
        """MCP 브리지를 `-c mcp_servers.<name>.*` 오버라이드로 조립."""
        if not transport:
            return []
        ns = f"mcp_servers.{self.MCP_SERVER_NAME}"
        args: List[str] = []
        if transport == "http":
            args += ["-c", f'{ns}.url={_toml_str("http://localhost:8765/mcp/")}']
            headers = self._identity_headers()
            if headers:
                args += ["-c", f"{ns}.http_headers={_toml_inline_table(headers)}"]
        else:
            cmd = _stdio_bridge_command()
            if not cmd:
                return []
            args += ["-c", f"{ns}.command={_toml_str(cmd[0])}"]
            if len(cmd) > 1:
                arr = "[" + ", ".join(_toml_str(a) for a in cmd[1:]) + "]"
                args += ["-c", f"{ns}.args={arr}"]
            # stdio 서버는 codex 의 자식이라 env 를 그대로 물려받는다 → 신원(INDIEBIZOS_*)은
            # _build_env 로 이미 전달된다. 여기서 다시 실을 필요 없다.
        # IBL 한 호출이 파이프라인 전체일 수 있어 기본 타임아웃으로는 짧다.
        args += ["-c", f"{ns}.startup_timeout_sec=30"]
        args += ["-c", f"{ns}.tool_timeout_sec={self.DEFAULT_TIMEOUT_SEC}"]
        return args

    def _image_prompt_prefix(self, image_paths: List[str]) -> str:
        img_lines = "\n".join(f"첨부 이미지 경로: {p}" for p in image_paths)
        return (
            f"{img_lines}\n"
            f"(위 이미지 파일을 볼 수 있다 — 이미지 보기 도구나 셸로 확인하라)\n\n"
        )

    # ================= 도구 정책 =================

    # ★Claude Code 의 DISALLOWED_TOOLS 에 해당하는 하드 차단이 Codex 엔 거의 없다.
    #   Codex 의 파일 읽기·검색·편집은 전부 shell/apply_patch 로 들어오고, 그 둘을 끄면
    #   Codex 는 아무 일도 못 한다. 설정으로 끌 수 있는 건 web_search 하나 —
    #   그건 IBL `[sense:search]` 와 1:1 중복이라 끈다(어휘 일관성·해마 학습 보존).
    TOOL_POLICY = (
        "\n\n# 도구 정책\n"
        f"IBL 실행 도구의 정확한 이름은 `{MCP_TOOL_PREFIX}execute_ibl` 다 — 이 이름 그대로 호출하라. "
        "다른 안내나 과거 용례에 `execute_ibl` 로 줄여 적힌 곳이 있어도, 실제 도구 이름은 "
        f"`{MCP_TOOL_PREFIX}execute_ibl` 뿐이다.\n"
        f"가이드 읽기 도구의 정확한 이름은 `{MCP_TOOL_PREFIX}read_guide` 다(맨이름 `read_guide` 아님). "
        "공용 프롬프트·IBL 액션 설명이 `read_guide(query=...)` 로 가르치는 곳은 모두 이 도구를 뜻한다 "
        "(셸로 data/guides 를 뒤지지 말 것 — 이 도구가 가이드 DB를 검색해 본문까지 준다).\n"
        "★파일 읽기·쓰기·편집·검색·웹은 셸이 아니라 IBL 로 하라. 이 CLI 에서는 셸이 유일한 "
        "파일 접근 통로라 기술적으로는 `cat`·`rg`·`sed` 가 되지만, **그렇게 하면 그 주행은 "
        "경험증류에 접지되지 않아 해마에 아무것도 남지 않는다**(실측 2026-08-18). 대신 "
        f"`{MCP_TOOL_PREFIX}execute_ibl` 로 "
        "`[self:read]`(파일 읽기)·`[self:write]`/`[self:edit]`(쓰기·편집)·`[self:grep]`(코드검색)·"
        "`[sense:search]`(웹검색 — source: ddg/naver/gnews)·`[sense:crawl]`(웹페이지) 을 호출하라.\n"
        "셸은 **IBL 에 등가물이 없는 일에만** 쓰는 탈출구다: `git`·프로세스 조회·AST 검사·"
        "임의 Python/Node 실행. 등가물이 있는 일을 셸로 하지 마라."
    )

    # ================= 모델·추론강도 =================

    def _model_and_effort(self) -> tuple:
        """설정의 `model` 을 (슬러그, 추론강도|None) 로 가른다.

        표기: `gpt-5.6-sol` 또는 `gpt-5.6-sol:high`.

        ★왜 별도 설정 칸이 아니라 `model` 한 칸에 싣는가:
        ①**프로바이더 캐시 키가 `bucket|provider|model|keyhash`** 다
          (model_resolver._provider_from_desc). 추론강도가 키 밖에 있으면 같은 슬러그를 쓰는
          두 티어(예: 고급=sol:max · 중급=sol:low)가 **캐시에서 충돌해** 먼저 만들어진 쪽의
          프로바이더를 조용히 나눠 쓴다 — 에러 없이 강도가 뒤바뀐다.
        ②`model` 칸은 이미 "이 CLI 의 모델 선택자"다 — claude_code 도 여기에 별칭 `opus` 를
          넣지 full 모델 ID 를 넣지 않는다. Codex 의 선택자가 2차원일 뿐이다.
        ③티어 설정 스키마·프로바이더 생성자 시그니처를 건드리지 않는다(다른 프로바이더 무영향).

        강도를 안 적으면 None → 오버라이드를 보내지 않고 사용자의 `~/.codex/config.toml`
        (`model_reasoning_effort`)을 그대로 따른다. 철자가 틀리면 경고 후 무시한다 —
        모르는 값을 그대로 흘리면 codex 가 통째로 거절해 턴이 죽는다.
        """
        raw = (self.model or "").strip()
        if ":" not in raw:
            return raw, None
        slug, _, effort = raw.rpartition(":")
        slug, effort = slug.strip(), effort.strip().lower()
        if effort not in self.REASONING_EFFORTS:
            self._log(
                f"알 수 없는 추론강도 '{effort}' 무시 — 가능한 값: "
                f"{', '.join(self.REASONING_EFFORTS)} (모델 설정 '{raw}')"
            )
            return raw, None
        return slug, effort

    # ================= 명령 조립 =================

    def _write_system_prompt_file(self) -> Optional[str]:
        """Codex 에는 시스템 프롬프트 파일을 받는 플래그가 없다 — 쓰지 않는다.

        내용은 _build_prompt_with_history 가 fresh 턴 프롬프트 머리에 싣는다.
        (상위 구현을 그대로 두면 매 호출 쓸모없는 temp 파일을 쓴다.)
        """
        return None

    def _build_prompt_with_history(self, message: str, history: List[Dict]) -> str:
        """fresh 턴 프롬프트 = 시스템 프롬프트 + 도구 정책 + 직렬화된 history + 현재 메시지.

        resume 턴은 상위 오케스트레이터가 이 함수를 부르지 않는다(스레드가 이미 안다).
        """
        body = super()._build_prompt_with_history(message, history)
        head = (self.system_prompt or "")
        if not getattr(self, "no_tools", False):
            head += self.TOOL_POLICY
        if not head.strip():
            return body
        return f"{head}\n\n---\n\n{body}"

    def _build_command(
        self,
        mcp_config_path: Optional[str] = None,
        stream: bool = False,
        resume_session_id: Optional[str] = None,
        system_prompt_file: Optional[str] = None,
        tools_mode: Optional[str] = None,
    ) -> List[str]:
        """`codex exec` 인자 조립. 유저 프롬프트는 argv 가 아니라 stdin(`-`) 으로 간다.

        인자 순서 주의(실측): 옵션은 `resume` 서브커맨드 **앞**에 와야 한다 —
        `codex exec [OPTIONS] resume <ID> [PROMPT]`. 뒤에 두면 clap 이 거절한다.

        tools_mode(원샷 다이어트): claude_code 만큼 깎이지 않는다. Codex 는 셸/편집 도구를
        끌 수 없으므로 ①MCP 브리지 미장착 ②web_search off 까지가 한계다.
        ★`--ignore-user-config` 는 **쓰지 않는다**(2026-08-31 실측 기각): 같은 원샷 질문에서
        17,222 → 16,270 토큰, 5.5% 절감뿐인데 대가로 사용자의 `model_reasoning_effort` 가
        빠져 **원샷만 모델 기본 강도로 조용히 떨어진다**(경로마다 다른 강도 = 재현 불가능한
        비용·품질). 남는 16K 는 Codex 자신의 기본 지침·AGENTS.md·작업공간 맥락이라
        어차피 이 플래그로는 못 깎는다.
        """
        cmd = [
            self._binary_path,
            "exec",
            "--json",
            # 프로젝트 폴더가 git 저장소가 아닐 수 있다 (에이전트 작업 폴더 전반).
            "--skip-git-repo-check",
            # 비대화 모드에서 승인 프롬프트로 멈추지 않도록 — claude_code 의
            # `--permission-mode bypassPermissions` 와 같은 자리다. 실행 통제는
            # indiebizOS 자체 게이트(IBL 승인·write_ledger)가 맡는다.
            "--dangerously-bypass-approvals-and-sandbox",
        ]

        # 사용자의 config.toml 에 있는 notify 훅(데스크톱 알림 클라이언트)은 백엔드 호출마다
        # 튀어나오면 안 된다 — 우리 서브프로세스에서만 끈다(사용자 파일은 안 건드림).
        cmd += ["-c", "notify=[]"]
        # web_search 는 IBL [sense:search] 와 1:1 중복 → 끄고 IBL 로 강제 (TOOL_POLICY 참조)
        cmd += ["-c", "tools.web_search=false"]

        # 원샷은 도구 브리지를 안 세운다(프로세스 기동 비용) — 그 외 다이어트 수단은 없다.
        if not tools_mode:
            cmd += self._bridge_config_args(mcp_config_path)

        slug, effort = self._model_and_effort()
        if slug:
            cmd += ["-m", slug]
        if effort:
            # 강도를 명시하면 경로(평소/원샷)와 무관하게 **결정적**이다. 안 적으면
            # 사용자의 ~/.codex/config.toml 을 따른다 — 그건 ChatGPT 데스크톱 앱이
            # 바꾸는 값이라, 재현 가능한 비용·품질을 원하면 티어에 적어 둘 것.
            cmd += ["-c", f"model_reasoning_effort={_toml_str(effort)}"]

        # 세션 이어가기 — 옵션 뒤, 프롬프트 앞
        if resume_session_id:
            cmd += ["resume", resume_session_id]

        # 프롬프트는 stdin (윈도우 argv 상한 회피 + 한글 보존)
        cmd += ["-"]
        return cmd

    # ================= 이벤트 번역 =================

    def _capture_session_id(self, event: Dict) -> Optional[str]:
        if event.get("type") == "thread.started":
            return event.get("thread_id")
        return None

    def _stream_error_text(self, event: Dict) -> Optional[str]:
        etype = event.get("type")
        if etype == "turn.failed":
            err = event.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err)
            return str(err or "")
        if etype == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "error":
                return str(item.get("message") or item.get("text") or "")
        return None

    # 도구로 취급하는 item 타입 → 로그·이벤트에 쓸 표시 이름.
    _TOOL_ITEM_NAMES = {
        "command_execution": "shell",
        "file_change": "apply_patch",
        "mcp_tool_call": "mcp",
        "web_search": "web_search",
        "todo_list": "todo",
    }

    @staticmethod
    def _tool_name(item: Dict) -> str:
        """item 에서 사람이 읽을 도구 이름. MCP 호출은 `<server>__<tool>` 로 복원한다.

        ★이 이름이 vocab_crystallization 의 결정화 재료다 — execute_ibl 호출이
        `indiebizos__execute_ibl` 로 찍혀야 IBL 사용이 집계된다.
        """
        itype = item.get("type") or ""
        if itype == "mcp_tool_call":
            server = item.get("server") or ""
            tool = item.get("tool") or item.get("name") or ""
            # 이벤트 필드에는 `mcp__` 접두가 없다 — 모델이 실제로 보는 실명으로 되돌린다.
            return f"mcp__{server}__{tool}" if server else str(tool)
        return CodexProvider._TOOL_ITEM_NAMES.get(itype, itype)

    @staticmethod
    def _tool_input(item: Dict) -> Any:
        """item 에서 도구 입력에 해당하는 부분."""
        itype = item.get("type") or ""
        if itype == "command_execution":
            return {"command": item.get("command")}
        if itype == "mcp_tool_call":
            return item.get("arguments")
        if itype == "web_search":
            return {"query": item.get("query")}
        if itype == "file_change":
            return {"changes": item.get("changes")}
        return {k: v for k, v in item.items() if k not in ("id", "type")}

    @staticmethod
    def _unwrap_mcp_content(raw: Any) -> tuple:
        """MCP 결과 봉투 `{content:[{type:text,text:…}], isError:bool}` → (본문 텍스트, isError).

        ★claude_code 와 모양을 맞추려고 벗긴다(실측 2026-08-30 연기시험): Claude CLI 는
        tool_result 블록의 text 조각을 이미 이어붙여 주는데, Codex 는 MCP 봉투를 통째로 준다.
        안 벗기면 ①로그 미리보기의 앞 60자를 봉투가 먹고 ②정직 표지 요약·지도 봉투 스캔이
        한 겹 더 깊은 곳을 파야 하며 ③MCP 의 isError 가 조용히 버려진다.
        """
        if not isinstance(raw, dict):
            return None, False
        blocks = raw.get("content")
        if not isinstance(blocks, list):
            return None, bool(raw.get("isError"))
        texts = [
            b.get("text", "") for b in blocks
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        if not texts:
            return None, bool(raw.get("isError"))
        return "\n".join(t for t in texts if t), bool(raw.get("isError"))

    @staticmethod
    def _tool_result(item: Dict) -> tuple:
        """item 에서 (결과 텍스트, is_error)."""
        itype = item.get("type") or ""
        status = str(item.get("status") or "").lower()
        is_error = status in ("failed", "errored", "not_found", "interrupted") or bool(
            item.get("declined"))
        if itype == "command_execution":
            exit_code = item.get("exit_code")
            if exit_code not in (None, 0):
                is_error = True
            return str(item.get("aggregated_output") or ""), is_error
        if itype == "mcp_tool_call":
            raw = item.get("structured_content")
            if raw is None:
                raw = item.get("content_meta")
            if raw is None:
                raw = item.get("result")
            text, mcp_error = CodexProvider._unwrap_mcp_content(raw)
            if text is not None:
                # MCP 프로토콜의 isError 는 봉투 안에만 있다 — item.status 는 '호출이
                # 성립했는가'라서, 도구가 실패를 반환해도 completed 로 온다.
                return text, (is_error or mcp_error)
            if isinstance(raw, (dict, list)):
                try:
                    return json.dumps(raw, ensure_ascii=False), (is_error or mcp_error)
                except (TypeError, ValueError):
                    return str(raw), (is_error or mcp_error)
            return str(raw or ""), (is_error or mcp_error)
        # 나머지는 봉투 전체를 결과로 (지도 봉투 스캔도 여기서 걸린다)
        try:
            return json.dumps(item, ensure_ascii=False), is_error
        except (TypeError, ValueError):
            return str(item), is_error

    def _translate_stream_event(
        self, event: Dict, accumulated_text: str, start_time: float
    ) -> List[tuple]:
        """Codex exec JSONL 이벤트 → indiebizOS provider 이벤트 형식 변환.

        Codex 어휘 (실측 2026-08-30, codex-cli 0.150.0-alpha.8):
          {"type":"thread.started","thread_id":"..."}
          {"type":"turn.started"}
          {"type":"item.started"|"item.updated"|"item.completed","item":{...}}
          {"type":"turn.completed","usage":{...}}
          {"type":"turn.failed","error":{...}}
        item.type ∈ agent_message · reasoning · command_execution · file_change ·
                    mcp_tool_call · web_search · todo_list · error

        ★claude_code 와 다른 결정적 차이: 텍스트가 토큰 단위로 흐르지 않고 **item 단위로
        완결돼 도착**한다(item.completed 의 text 통짜). 그래서 UI 스트리밍의 낱알이 굵다 —
        이건 CLI 의 성질이지 우리 배선의 결함이 아니다.

        Returns:
            [(event_dict, new_accumulated_text_or_None), ...]
        """
        out: List[tuple] = []
        etype = event.get("type")

        if etype == "item.started":
            item = event.get("item") or {}
            itype = item.get("type")
            if itype in self._TOOL_ITEM_NAMES:
                # 도구 호출 헤더를 결과보다 먼저 낸다 (긴 셸 명령의 진행 표시)
                iid = str(item.get("id") or "")
                if iid:
                    self._started_items.add(iid)
                name = self._tool_name(item)
                tinput = self._tool_input(item)
                self._log_tool_use(name, tinput)
                out.append((
                    {"type": "tool_start", "id": iid, "name": name, "input": tinput},
                    None,
                ))

        elif etype == "item.completed":
            item = event.get("item") or {}
            itype = item.get("type")
            iid = str(item.get("id") or "")

            if itype == "agent_message":
                text = item.get("text") or ""
                if text:
                    # ★문단 구분자를 우리가 넣는다(실측 2026-08-30 연기시험): claude_code 는
                    # 텍스트가 토큰 단위로 흘러 자연히 이어지지만, Codex 는 **완결된 메시지**가
                    # 통짜로 온다. 그냥 이으면 앞 메시지의 마침표에 다음 메시지가 달라붙어
                    # ("…하겠습니다.`mcp__…`") 최종 응답이 한 덩어리로 읽힌다.
                    if accumulated_text and not accumulated_text.endswith("\n"):
                        text = "\n\n" + text
                    out.append(({"type": "text", "content": text},
                                accumulated_text + text))
                    accumulated_text = accumulated_text + text

            elif itype == "reasoning":
                _t = item.get("text") or item.get("summary") or ""
                if isinstance(_t, list):
                    _t = " ".join(
                        (c.get("text", "") if isinstance(c, dict) else str(c)) for c in _t)
                _t_str = str(_t).strip()
                if _t_str:
                    out.append(({"type": "thinking", "content": _t_str}, None))

            elif itype == "error":
                out.append((
                    {"type": "error",
                     "content": f"Codex 응답 오류: {item.get('message') or item.get('text') or item}"},
                    None,
                ))

            elif itype in self._TOOL_ITEM_NAMES:
                name = self._tool_name(item)
                # item.started 를 못 본 경우(짧은 호출은 completed 만 온다) 헤더를 먼저 낸다 —
                # 안 그러면 process_message 의 start↔result 페어링이 한 칸씩 밀린다.
                if iid not in self._started_items:
                    tinput = self._tool_input(item)
                    self._log_tool_use(name, tinput)
                    out.append((
                        {"type": "tool_start", "id": iid, "name": name, "input": tinput},
                        None,
                    ))
                else:
                    self._started_items.discard(iid)
                result_text, is_error = self._tool_result(item)
                self._log_tool_result(result_text, is_error)
                out.append((
                    {"type": "tool_result", "id": iid, "name": name,
                     "result": result_text, "is_error": is_error},
                    None,
                ))

        elif etype == "turn.completed":
            latency_ms = (time.time() - start_time) * 1000
            usage = event.get("usage") or {}
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            cached = int(usage.get("cached_input_tokens") or 0)
            cache_write = int(usage.get("cache_write_input_tokens") or 0)
            # ★input_tokens 는 **컨텍스트 크기가 아니다**(실측 2026-08-31 롤아웃 대조):
            #  Codex 의 usage 는 스레드가 살아온 모든 라운드의 입력 **합계**
            #  (`total_token_usage`)다. 세션 크기 판정은 그래서 여기가 아니라 턴 시작의
            #  _measure_context_size(롤아웃 `last_token_usage`)가 맡는다 — 여기서 0 을
            #  남기면 상위의 record_size 가 그 실측값을 덮어쓰지 않는다.
            self._last_context_size = 0
            # 이 턴의 비용 = 누적 − 턴 시작 누적. 기준선을 못 잡았으면(fresh 턴이거나
            # 롤아웃을 못 읽음) 누적 그대로 — fresh 턴에서는 둘이 같다.
            # ★입력만이 아니라 캐시 적중·출력도 누적이다(2026-09-06 롤아웃 실측) — 옛 판은
            #  출력을 누적 그대로, 캐시는 아예 안 적어 [턴비용] 이 지난 턴 출력을 제 몫으로
            #  신고하고 캐시분은 0 으로 남겼다(claude_code 와 같은 사각지대).
            turn_input = max(0, input_tokens - self._turn_base_total)
            turn_cached = max(0, cached - self._turn_base_cached)
            turn_output = max(0, output_tokens - self._turn_base_output)
            # 턴 몫으로 환산한 뒤 벤더 모양(Codex exec: input 은 cached 포함) 그대로 초크포인트에.
            self.metrics.record_usage(latency_ms, {"input_tokens": turn_input, "output_tokens": turn_output,
                                                   "cached_input_tokens": turn_cached})
            # 누적 수치(input_tokens·cached·cache_write·output)는 전부 **스레드 생애 합계**다 —
            # 턴 몫과 섞어 적으면 다시 오독을 부르므로 괄호 안에 따로 묶는다.
            cache_info = (f" cached={cached} cache_write={cache_write}"
                          if (cached or cache_write) else "")
            self._log(
                f"turn.completed {latency_ms:.0f}ms "
                f"in={turn_input} out={turn_output} cache_read={turn_cached} "
                f"(스레드누적 in={input_tokens} out={output_tokens}{cache_info})"
            )
            out.append((
                {"type": "final", "content": self._finalize_text(accumulated_text.strip())},
                None,
            ))

        elif etype == "turn.failed":
            err = event.get("error")
            msg = err.get("message") if isinstance(err, dict) else err
            out.append(({"type": "error", "content": f"Codex 턴 실패: {msg}"}, None))

        return out
