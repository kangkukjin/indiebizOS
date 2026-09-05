"""
cli_provider.py - 아웃오브프로세스 CLI 프로바이더의 공통 몸통
IndieBiz OS Core

`claude_code` 가 개척한 "CLI 를 subprocess 로 띄워 provider 계약에 맞추는" 자리의
**벤더 무관 부분**을 여기 모은다. 두 번째 CLI(codex)를 붙이면서 갈라진 것이 아니라,
같은 몸통에 어댑터만 둘이 되도록 뽑아낸 것이다.

여기 사는 것(= 벤더가 바뀌어도 같은 것):
- 세션 영속(resume 매핑 + 크기 기반 리셋)과 그 상태 파일 규약
- 신원 전파(에피소드·run·task·origin·agent_id) — 프로세스 경계를 못 건너는 contextvar 를
  spawn 시점에 떠서 env/헤더로 동봉
- 스트림 오케스트레이션: spawn → stdin 프롬프트 → JSONL 소비 → 이벤트 번역 →
  resume 실패 폴백 → 일시 과부하 backoff → result 미도달 시 본문 승격
- **무출력 마감**(2026-09-01): 자식이 파이프를 연 채 침묵하면 읽기·쓰기가 영원히 블록된다.
  프로세스에 감시를 걸어 유한한 정직 실패로 착지시킨다(STREAM_IDLE_TIMEOUT_SEC 참조)
- 로그 절단 폭과 정직 표지 요약(실패 신호가 절단에 삼켜지지 않게)
- 지도 봉투([MAP:]) 재주입 — CLI 가 도구 결과를 산문으로 요약하며 마커를 흘리는 문제
- 이미지 임시 파일화, history 직렬화

서브클래스가 채우는 것(= 벤더마다 다른 것):
- `_find_binary()` · `_resolve_auth()` · `_build_command()` · `_build_env()`
- `_translate_stream_event()` — 벤더 JSONL 어휘 → 내부 이벤트 어휘
- `_mcp_bridge_acquire()/_release()` — 도구 브리지를 CLI 에 물리는 방식
- 도구 정책 상수(EAGER/DISALLOWED/TOOL_POLICY) — CLI 의 네이티브 도구 표면에 결박된 문자열

★이 파일을 고칠 때: 여기 있는 주석의 대부분은 실사고 기록이다(에피소드 번호가 붙은
것들). 벤더 하나에서만 겪은 사고라도 원인이 "아웃오브프로세스"라면 여기 남는다 —
그래야 다음 CLI 가 같은 사고를 다시 겪지 않는다.
"""

import base64
import json
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional
from urllib.parse import quote

from .base import BaseProvider, note_execution_call
from episode_logger import truncate_for_log, record_trajectory_event, notify_round
from seam_metrics import SeamTracker   # 셸↔IBL 이음매 관측(2026-09-05) — 값이 온전한 유일한 자리
from ibl_honesty import HONESTY_KEYS   # 정직 표지 목록의 단일 소스 (손으로 적지 않는다)

# 로그 절단 폭 — 회고 가치 대 로그 예산의 값. 자른 자리는 truncate_for_log 가 반드시
# `…(+N자)` 표식을 남기므로, 읽는 쪽은 "짧다"와 "잘렸다"를 추정 없이 가른다.
#
# ★execute_ibl 만 폭이 다른 이유(2026-08-22 실측): IBL 코드는 **조합 구조가 사는 자리**라
# 뒷부분이 잘리면 `>>`·`&`·`??` 를 셀 수 없어 조합률 지표가 통째로 하한이 된다
# (창 1,720건 중 436건=25% 가 300자에서 잘렸다). 400건 표본의 실제 길이 분포는
# p50=125 · p90=957 · p95=1,473 · p98=3,273 이고, 그 위의 꼬리는 전부
# [self:edit]·[self:write]·[self:patch] 의 **내용** payload(최대 51,987자)다.
# 그래서 '면제'가 아니라 폭이다 — 무제한은 예산의 대부분을 편집 payload 에 쓰고
# (표본 합계 6배), 2,000자는 호출의 97%를 온전히 담으면서 episode_log 총량을
# 약 +5% 늘린다(측정: log 10.3M자 중 tool_use 18.8% · 그중 execute_ibl 8.7%).
_TOOLUSE_CAP = 300
_TOOLUSE_CAP_IBL = 2000
_TOOLRESULT_CAP = 300
# ★결과 폭이 두 벌인 이유(2026-08-28 실측): 원장이 자기 실패를 못 보는 것이 이 로그의 가장 큰
# 결함이었다. 최근 200 에피소드에서 tool_result 4,103줄 중 2,281줄(55.6%)이 300자에서 잘렸고,
# (error) 태그 줄도 43줄 중 21줄(49%)이 잘렸다. 잘리는 자리는 하필 봉투의 정직 표지
# (success:false·error·_fallback_used·error_count·errors·skipped_steps·condition_errors·
# halted·branches_failed·truncated …)가 사는 뒤쪽이라, vocab_crystallization 의 실패
# 스캐너는 '있는 실패'를 못 본다. 무제한 확대는 답이 아니다 — 같은 표본의 숨은 글자 합계가
# 7.8M자(절단분 1건당 평균 3,438자)라 로그 예산이 무너진다. 그래서 실패 신호만 우선 건진다:
#   ① (error) 줄은 폭 자체를 넓힌다 — 평문 traceback 은 키가 없어 요약이 안 되므로 본문이
#      유일한 단서다.
#   ② 나머지는 300자 머리에 '정직 표지 요약'을 이어 붙인다. 살아있는 표지가 없는 성공 결과는
#      요약이 비어 폭도 예전 그대로다(비용은 실패한 결과에만 붙는다).
_TOOLRESULT_CAP_ERROR = 2000
_FAILDIGEST_CAP = 240


# 봉투의 정직 표지 — 절단에 삼켜지면 안 되는 키들. 값이 '살아있을' 때만 요약에 싣는다
# (truncated:false · error_count:0 처럼 죽은 값은 신호가 아니라 잡음이다).
# ★목록을 손으로 적지 않는다(scripts/check_honesty_propagation.py 관문): 정본은
# ibl_honesty.HONESTY_KEYS 한 벌이고, 여기서는 **엔진 봉투 밖** — 외부 CLI 의 결과
# 텍스트에만 나타나는 신호만 더한다. 첫 판(2026-08-28)은 이 목록을 손으로 적다가
# rows_replaced 를 빠뜨렸고 관문이 그걸 잡았다 — 정본이 자라면 이 스캐너도 같이 자란다.
_RESULT_ONLY_SIGNALS = (
    "error", "error_type", "success", "warning",
    "branches_honesty", "criteria_verdict", "approval_required",
)
_HONESTY_KEYS = tuple(dict.fromkeys(HONESTY_KEYS + _RESULT_ONLY_SIGNALS))
_HONESTY_RE = re.compile(
    '"(' + "|".join(_HONESTY_KEYS) + ')"\\s*:\\s*'
    '("[^"]{0,160}"|\\[[^\\]]{0,160}\\]?|\\{[^}]{0,160}\\}?|[-\\w.]+)'
)
_DEAD_VALUE_RE = re.compile(
    '^(false|null|none|0|0[.]0|\\[\\]|\\{\\}|"")$', re.IGNORECASE)


def _failure_digest(text: str, cap: int = _FAILDIGEST_CAP) -> str:
    """결과 본문 전체에서 살아있는 정직 표지만 추려 한 줄로 (없으면 빈 문자열).

    절단된 뒷쪽에 실패가 숨는 것을 막는 장치라 본문 **전체**를 훑는다 — 머리에 이미
    보이는 표지가 중복될 수 있지만, 못 보는 것보다 싸다."""
    flat = (text or "").replace('\\"', '"')   # 중첩 JSON 이스케이프 평탄화
    parts: List[str] = []
    seen = set()
    for key, val in _HONESTY_RE.findall(flat):
        v = val.strip()
        live = not _DEAD_VALUE_RE.match(v)
        if key == "success":        # success 는 false 일 때만 신호
            live = v.lower() == "false"
        elif key == "truncated":    # truncated 는 true 일 때만 신호
            live = v.lower() == "true"
        if not live or key in seen:
            continue
        seen.add(key)
        # 표기는 JSON 짝("키": 값)으로 맞춘다 — 기존 실패 스캐너
        # (vocab_crystallization._CC_RESULT_FAIL_RE 의 '"success": false')가
        # 요약에서도 그대로 걸리도록.
        parts.append(f'"{key}": {truncate_for_log(v, 80)}')
    if not parts:
        return ""
    return " ⚠signals " + truncate_for_log(" · ".join(parts), cap)


def _preview_with_signals(flat: str, cap: int) -> str:
    """로그용 미리보기 — cap 자 머리 + (잘렸다면) 정직 표지 요약 + 절단 표식.

    요약을 절단 경계에 끼우고 폭을 요약 길이만큼만 늘려 자르므로, 표식의 N 은 원문
    숨김량 그대로이고 표식은 문자열 끝에 남는다 — truncate_for_log 의 읽는 쪽 계약
    (TRUNC_MARK_RE 가 끝에 걸림 = 절단분)이 깨지지 않는다."""
    digest = _failure_digest(flat) if len(flat) > cap else ""
    return truncate_for_log(flat[:cap] + digest + flat[cap:], cap + len(digest))


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
        # 상한 16: CLI relay 는 MCP str 반환을 {"result": "<json>"} 로 한 겹 더 감싸고
        # (문자열+dict = +2 깊이), 병렬(`&`) 파이프라인은 봉투를 깊이 9까지 밀어넣는다
        # (에피소드 802 실측). 옛 상한 8은 이 조합에서 1칸 모자라 지도가 조용히 유실됐다.
        if depth > 16:
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


def ensure_mcp_bridge_config() -> Optional[Path]:
    """CLI 프로바이더 공유 stdio MCP 브리지 설정(claude_code_mcp.json)을 파생 보장.

    ★이 파일은 2026-05 맥에서 손으로 한 번 만든 뒤 어디에도 생성자가 없었다 — git 밖
      (data/*.json 무시)이라 새 몸(윈도우 설치)엔 존재하지 않고, 두 CLI 프로바이더가
      조용히 MCP 없이 떴다(2026-08-31 윈도우 실측: execute_ibl 부재). 경로·인터프리터는
      설치본마다 다르므로(하부/상부 이음매) 몸이 자기 값으로 파생한다:
      command=sys.executable(이 백엔드의 파이썬 — 윈도우 임베디드/맥 .venv),
      script=백엔드 옆 루트의 mcp_server.py(개발=repo 루트, 패키지=resources 루트).

    재생성 조건 = 없거나 **깨졌을 때만**(command 미해석 또는 script 미실존 — 다른 몸의
    절대경로 포함). 이 몸에서 실제로 도는 커스텀 설정은 존중해 덮지 않는다.
    반환: 설정 파일 경로(보장 실패 시에도 기존 파일이 있으면 그 경로), 둘 다 없으면 None.
    """
    import shutil
    import sys
    path = _data_dir() / "claude_code_mcp.json"
    server = Path(__file__).resolve().parents[2] / "mcp_server.py"

    def _broken() -> bool:
        try:
            with open(path, "r", encoding="utf-8") as f:
                srv = ((json.load(f).get("mcpServers") or {}).get("indiebizos") or {})
            cmd = str(srv.get("command") or "")
            if not cmd or not (Path(cmd).exists() or shutil.which(cmd)):
                return True
            scripts = [a for a in (srv.get("args") or []) if str(a).endswith(".py")]
            return any(not Path(str(a)).exists() for a in scripts)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return True

    if path.exists() and not _broken():
        return path
    if not server.exists():
        return path if path.exists() else None   # 파생 재료가 없으면 손대지 않는다
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"indiebizos": {
                "command": sys.executable,
                "args": [str(server)],
            }}}, f, ensure_ascii=False, indent=2)
        print(f"[MCP] 브리지 설정 파생 생성: {path} (python={sys.executable})")
        return path
    except OSError as e:
        print(f"[MCP] 브리지 설정 생성 실패(무시): {e}")
        return path if path.exists() else None


# ============ 세션 상태 저장소 (--resume 연속성 + 크기 기반 리셋) ============
# CLI 가 자기 과거 도구 호출·plan·파일 편집 이력을 기억하도록 agent별로 세션 id를
# 저장하고 다음 호출에 재사용한다. 프로바이더마다 파일이 갈리는 이유는 세션 id 의
# 발급자가 다르기 때문 — 한 파일에 섞으면 claude 세션 id 를 codex 에 먹이게 된다.

_SESSION_STORES: List["CliSessionStore"] = []


class CliSessionStore:
    """`data/<prefix>_sessions.json` · `data/<prefix>_session_sizes.json` 한 쌍.

    생성만 하면 전역 목록에 등록되어 `clear_sessions_for_agent()`(프로바이더 무관
    '새 대화')가 이 저장소도 함께 비운다 — 새 CLI 프로바이더를 추가할 때 UI 리셋
    배선을 따로 기억하지 않아도 되도록.
    """

    def __init__(self, prefix: str, label: str):
        self.prefix = prefix
        self.label = label
        _SESSION_STORES.append(self)

    # --- 경로 ---
    def map_path(self) -> Path:
        return _data_dir() / f"{self.prefix}_sessions.json"

    def size_path(self) -> Path:
        return _data_dir() / f"{self.prefix}_session_sizes.json"

    # --- 공통 입출력 ---
    @staticmethod
    def _load(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, path: Path, m: Dict[str, Any], what: str):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"[{self.label}] {what} 저장 실패: {e}")

    # --- 세션 매핑 ---
    def load_map(self) -> Dict[str, str]:
        return self._load(self.map_path())

    def save_map(self, m: Dict[str, str]):
        self._save(self.map_path(), m, "세션 매핑")

    def clear_agent(self, session_key: str):
        """특정 agent의 세션 매핑 제거. UI '새 대화' 등에서 호출.

        ★접두 스윕: 프로바이더가 세션 키를 파생시켜 쓸 수 있다(예: codex 는 시스템 프롬프트
        해시를 `키#해시` 로 붙인다 — CodexProvider._get_session_key 참조). 호출부는 그
        파생을 모르고 평범한 registry_key 를 넘기므로, 정확히 같은 키 + `키#…` 파생분을
        함께 지운다. 안 그러면 '새 대화'가 파생 키를 못 찾아 옛 스레드가 살아남는다.
        """
        m = self.load_map()
        prefix = f"{session_key}#"
        victims = [k for k in m if k == session_key or k.startswith(prefix)]
        if victims:
            for k in victims:
                del m[k]
            self.save_map(m)

    # --- 컨텍스트 크기 ---
    def load_sizes(self) -> Dict[str, int]:
        return self._load(self.size_path())

    def save_sizes(self, m: Dict[str, int]):
        self._save(self.size_path(), m, "세션 크기")

    def record_size(self, session_key: str, size: int):
        """직전 턴의 실측 컨텍스트 토큰 수를 기록 (다음 턴 리셋 판단용)."""
        if not session_key or size <= 0:
            return
        m = self.load_sizes()
        m[session_key] = int(size)
        self.save_sizes(m)

    def clear_size(self, session_key: str):
        m = self.load_sizes()
        prefix = f"{session_key}#"     # clear_agent 와 같은 접두 스윕 규약
        victims = [k for k in m if k == session_key or k.startswith(prefix)]
        if victims:
            for k in victims:
                del m[k]
            self.save_sizes(m)


def clear_sessions_for_agent(session_key: str):
    """등록된 **모든** CLI 프로바이더의 세션 매핑을 비운다 (프로바이더 무관 '새 대화').

    호출부(UI 리셋·SESSION_RESET 분류)는 지금 어떤 프로바이더가 걸려 있는지 모르고,
    알 필요도 없다 — 기어가 턴 사이에 바뀔 수도 있다. 그래서 '이 키의 CLI 세션 전부'를
    끊는다. 존재하지 않는 매핑은 no-op 이라 비용은 파일 읽기 몇 번뿐이다.
    """
    for store in _SESSION_STORES:
        try:
            store.clear_agent(session_key)
            store.clear_size(session_key)
        except Exception as e:      # 한 저장소의 손상이 다른 저장소를 막지 않게
            print(f"[cli_provider] {store.label} 세션 클리어 실패 (무시): {e}")


class CliSubprocessProvider(BaseProvider):
    """CLI 를 subprocess 로 호출하는 프로바이더의 공통 몸통.

    서브클래스는 아래 훅만 채우면 된다 — 스트림 오케스트레이션·세션·신원은 상속된다.
    """

    # --- 서브클래스가 덮는 표식 ---
    CLI_LABEL = "CLI"            # 로그 태그 `[<LABEL>/<agent>]` — ★vocab_crystallization
                                 #   이 이 태그로 tool_use/tool_result 를 판독한다.
                                 #   새 값을 쓰면 그쪽 _CLI_LABELS 에도 등록할 것.
    CLI_DISPLAY = "CLI"          # 사용자에게 보이는 이름
    STATE_PREFIX = "cli"         # data/<prefix>_sessions.json
    SESSION_STORE: Optional[CliSessionStore] = None   # 서브클래스가 생성해 붙인다

    DEFAULT_TIMEOUT_SEC = 600  # 10분 — 스트림이 EOF 로 끝난 뒤 종료를 기다리는 한도

    # ★무출력 마감 (2026-09-01 실측 수리 — ep 유튜브팁 배관 사고).
    # 사고: `[table:each]` 2행째의 `[self:struct]` 원샷이 **23분 동안 무한 대기**했다.
    # 거절도 실패도 아니고 그냥 안 돌아왔다. 원인은 이 파일에 있었다 —
    # 옛 코드의 유일한 시간 한도는 `proc.wait(timeout=DEFAULT_TIMEOUT_SEC)` 였는데,
    # 그 자리는 **stdout 이 이미 EOF 로 닫힌 뒤**다. 즉 한도가 지키던 것은
    # "다 뱉고 안 죽는 자식"(사실상 안 일어나는 사건)이었고, 진짜로 멈추는 자리
    # (`for raw_line in proc.stdout` 의 블로킹 읽기 = 자식이 파이프를 연 채 침묵)는
    # 아무 한도도 없는 무한 대기였다. 한도가 있다는 착시가 10개월 산 셈이다.
    # ★규율: **읽기·쓰기 블로킹에는 마감이 붙는다.** 프로세스를 죽이면 파이프가 닫혀
    # 두 블로킹(stdin 쓰기·stdout 읽기)이 함께 풀리므로, 감시는 프로세스 하나에 건다.
    # 값은 관대하게 — 도구를 오래 도는 에이전트 런의 침묵(긴 Bash·큰 편집)을 죽이면
    # 안 된다. "한 줄도 안 오는 10분"은 정상 실행에 존재하지 않는다(실측: 성공한
    # 같은 부류 호출 67초).
    STREAM_IDLE_TIMEOUT_SEC = 600      # 출력 한 줄도 없는 침묵의 한도
    STREAM_IDLE_POLL_SEC = 5.0         # 감시 스레드의 확인 주기

    # 서버측 일시 과부하(529 Overloaded / overloaded_error 등) 자동 재시도.
    # 본문이 아직 하나도 안 온(not committed) 경우에만 backoff 후 다시 호출한다.
    # 입력 크기와 무관한 서버 포화 신호라, 강의 저작처럼 "유효 JSON 한 방"이
    # 필요한 일회성 호출이 단 한 번의 과부하로 통째 실패하던 걸 흡수한다.
    OVERLOADED_MAX_RETRIES = 3
    OVERLOADED_BASE_DELAY_SEC = 2.0
    OVERLOADED_MAX_DELAY_SEC = 30.0

    # --resume 은 CLI 가 디스크의 전체 트랜스크립트를 재생하므로 세션이 무한 성장한다.
    # (indiebizOS 가 넘기는 5턴/요약 트림은 resume 경로에서 버려짐.) 의미 있는 장기
    # 연속성은 이미 indiebizOS 기억층(연상·심층메모리·의식 요약·포식)이 주입하므로,
    # raw 트랜스크립트가 임계 토큰을 넘으면 다음 턴에 fresh 세션으로 끊고 트림 히스토리로
    # 재시드한다. 턴 수가 아니라 *실측 토큰*(in+cache_read+cache_create)에 거는 이유:
    # 턴 크기가 비균일하다 — 이미지/긴 산출물 한 턴이 폭발 주범이지 턴 수가 아니다.
    # ★임계값은 truncation 방어가 아니다: 모델의 컨텍스트 윈도우는 1M 이라 이 값이
    # 조절하는 건 천장이 아니라 비용/지연/품질(낡은 tool_result 희석)이다. 옛 150K(윈도우 15%)는
    # goal-eval 재실행 3라운드를 태스크 도중에 끊어 탈선시켰다(episode 718) → 300K(30%).
    # 2026-07-28 사용자 결정으로 500K(50%, 여유 500K)로 재상향 — 리셋 빈도 축소가 목적.
    # 2026-09-06 사용자 결정으로 300K 로 되돌림 — 16일 실측: Claude Code 876턴이 캐시 읽기
    # 13.99억 토큰, 시스템 AI 라운드당 컨텍스트 29만(일반 코딩 세션의 3~5배). fresh 리셋
    # 7회 직후 턴에 품질 저하 신호 없음(평가된 3건 전부 ACHIEVED). 대신 리셋이 **작업
    # 경계**를 존중하도록 판정을 _should_reset_session 으로 옮겼다 — ep718 부류(재실행
    # 도중 절단)는 임계값이 아니라 타이밍 문제였다.
    # 트레이드: 세션이 길수록 턴당 캐시 읽기 비용과 낡은 tool_result 희석은 커진다.
    # 되돌릴 때 "200K 벽" 가정 금지 — 옛 200K 기억은 stale, 현 모델은 1M.
    # 턴 *안*의 tool_result 는 CLI 가 트랜스크립트를 소유해 여기서 못 비운다 — 그 비용은
    # 결과를 처음부터 작게(파일 스필·라운드 축소) 만드는 쪽의 몫이다.
    SESSION_RESET_TOKEN_THRESHOLD = 300_000
    # 작업 경계 유예의 상한 — 유예는 한 턴뿐이고 이 배수를 넘으면 무조건 끊는다
    # (유예가 무한 성장의 뒷문이 되지 않도록).
    SESSION_RESET_GRACE_MULTIPLIER = 2

    # resume 실패 판정용 마커 — 이 문구가 에러 텍스트에 있으면 '세션이 사라졌다'로 보고
    # 매핑을 폐기한 뒤 fresh 로 한 번 더 돌린다. rate limit·인증 같은 일시 오류로는
    # 멀쩡한 매핑을 버리지 않도록 **세션 소멸에만** 걸리는 문구를 쓴다.
    SESSION_ISSUE_MARKERS: tuple = ()

    # 도구 정책 — 시스템 프롬프트 뒤에 append. CLI 의 네이티브 도구 표면에 결박된
    # 문자열이라 서브클래스가 각자 쓴다(공용 프롬프트는 손대지 않는다).
    TOOL_POLICY = ""

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

    def _is_session_issue(self, combined: str) -> bool:
        """에러 텍스트가 '세션 만료/무효' 신호인가 (SESSION_ISSUE_MARKERS 기반)."""
        low = (combined or "").lower()
        return any(m in low for m in self.SESSION_ISSUE_MARKERS)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._binary_path: Optional[str] = None
        # 메타 역할(의식·평가 등) provider는 세션 연속성이 의미 없고
        # 메인 에이전트와 session_key가 충돌하므로 비활성화 가능.
        # 호출 측이 init_client 후 True로 설정.
        self.disable_session_persistence: bool = False
        # 직전 턴의 실측 컨텍스트 토큰 수 릴레이.
        # _translate_stream_event 가 채우고, 세션 저장부가 읽어 영속화.
        self._last_context_size: int = 0
        # 마지막 턴의 stop_reason (출력 절단 신고용). 벤더가 주지 않으면 None.
        self._last_stop_reason: Optional[str] = None
        # 도구 실행 결과 (non-streaming 경로에서 evaluator가 사용).
        # process_message 시작 시 비워지고 stream 이벤트 소비 중 누적된다.
        self._last_tool_results: List[str] = []
        # 도구 호출 구조화 이력 ({name, input, result, is_error}) — evaluator 시퀀스 근거용.
        # tool_start와 tool_result를 인덱스로 페어링하여 누적한다.
        self._last_tool_calls: List[Dict[str, Any]] = []
        # 이번 턴 도구 결과에서 발견한 지도 봉투(route_map/location_map)를 [MAP:...] 태그로 모아,
        # 최종 응답 끝에 재주입한다. in-process 프로바이더(anthropic/gemini/openai/ollama)는
        # execute_tool 이 [MAP:] 태그를 붙이고 각자 재주입하지만, 아웃오브프로세스인 이 부류는
        # CLI 서브프로세스가 도구 결과를 산문으로 요약하며 마커를 흘려버려 프론트 지도가 안 뜬다.
        # process_message_stream 시작 시 비워지고, tool_result 소비 중 누적된다.
        self._pending_map_tags: List[str] = []

    # ================= 서브클래스 훅 =================

    @classmethod
    def _find_binary(cls) -> Optional[str]:
        """CLI 실행파일 경로. 못 찾으면 None."""
        raise NotImplementedError

    def _resolve_auth(self) -> str:
        """인증 자료를 내부 상태에 세팅하고, 로그용 출처 설명을 반환."""
        return "없음"

    def _build_command(
        self,
        mcp_config_path: Optional[str] = None,
        stream: bool = False,
        resume_session_id: Optional[str] = None,
        system_prompt_file: Optional[str] = None,
        tools_mode: Optional[str] = None,
    ) -> List[str]:
        """CLI 인자 조립. 유저 프롬프트는 argv 가 아니라 stdin 으로 간다."""
        raise NotImplementedError

    def _translate_stream_event(
        self, event: Dict, accumulated_text: str, start_time: float
    ) -> List[tuple]:
        """벤더 JSONL 이벤트 → indiebizOS provider 이벤트 형식 변환.

        Returns: [(event_dict, new_accumulated_text_or_None), ...]
        """
        raise NotImplementedError

    def _capture_session_id(self, event: Dict) -> Optional[str]:
        """이벤트에서 세션 id 를 뽑는다 (벤더마다 키가 다름)."""
        return event.get("session_id")

    def _stream_error_text(self, event: Dict) -> Optional[str]:
        """이벤트가 터미널 에러를 담고 있으면 그 텍스트 (resume 실패 판정 재료)."""
        return None

    def _mcp_bridge_acquire(self) -> Optional[str]:
        """도구 브리지 핸들(보통 config 파일 경로). 필요 없으면 None."""
        return None

    def _mcp_bridge_release(self, handle: Optional[str]) -> None:
        """임시 핸들 정리 (temp 파일 삭제 등)."""
        return None

    def _should_reset_session(self, prev_size: int) -> tuple:
        """크기 임계를 넘은 세션을 이번 호출에서 끊을지 — (끊는가, 로그 사유 또는 "").

        임계 이하면 (False, "") 로 침묵. 임계 초과면 원칙은 fresh 리셋이되 **작업 경계**를
        존중한다(2026-09-06 사용자 결정, 임계 500K→300K 와 함께):
        ① 같은 인지 턴의 두 번째 이후 실행 호출(goal 재실행·자기반성·약속 재시도)은
           절대 끊지 않는다 — ep718 의 뿌리(임계 자체가 아니라 태스크 도중의 리셋).
        ② 직전 턴이 절단(max_tokens)·마감 실패로 끝났으면 다음 턴은 그 일을 잇는
           요청일 공산이 크다("마저 완성해") — 한 턴 유예. 단 유예는 임계의
           SESSION_RESET_GRACE_MULTIPLIER 배까지만(무한 성장 뒷문 금지).
        리셋을 미룬 이유는 로그에 남긴다 — 침묵하면 '왜 안 끊겼나'를 못 되짚는다."""
        thr = int(self.SESSION_RESET_TOKEN_THRESHOLD)
        if prev_size <= thr:
            return False, ""
        if int(getattr(self, "_execution_call_ordinal", 0) or 0) > 0:
            return False, "같은 턴의 재호출(작업 진행 중) — 리셋 유예"
        if getattr(self, "_prev_turn_incomplete", False) and prev_size <= thr * self.SESSION_RESET_GRACE_MULTIPLIER:
            return False, "직전 턴 미완(절단·마감) — 한 턴 유예"
        return True, "fresh 리셋"

    def _measure_context_size(self, session_id: str) -> Optional[int]:
        """세션의 *현재* 컨텍스트 토큰 수를 벤더가 직접 잴 수 있으면 재서 돌려준다.

        기본은 None = "못 잰다" → 리셋 판정은 지난 턴 끝에 기록해 둔 값(_store)을 쓴다.
        벤더가 턴 usage 를 **컨텍스트 크기가 아니라 라운드/스레드 누적 합계**로 주는 경우
        (Codex 의 total_token_usage) 그 값을 세션 크기로 오인하면 도구를 몇 번만 써도
        임계를 넘어 멀쩡한 세션이 끊긴다 — 그런 벤더가 이 자리를 덮어쓴다.
        """
        return None

    def _note_model_round(self, model: Optional[str] = None) -> int:
        """벤더 어댑터가 '모델 응답 1건'을 본 자리에서 부른다 — 실행 라운드를 프로바이더 무관
        스텝 원장(episode_logger.notify_round)에 찍는다.

        ★2026-09-06 실측(연구 에이전트 09-06 에피소드 11건): model.round 42건이 전부 DeepSeek
        무의식 분류·배경 원샷이고 **execution 라운드는 0건**. in-process 프로바이더는 자기 도구
        루프에서 notify_round 를 부르지만, CLI 서브프로세스는 루프가 CLI 안에 살아 아무도 안
        불렀다 — 스텝 원장을 만든 이유(정규식 회수가 gemini→claude_code 전환에 끊긴 사고,
        episode_logger 주석 A)가 새 프로바이더에서 같은 모양으로 재발한 것. 그래서 가장 많이
        쓰는 경로에서 '왕복 대비 IBL' 효율 지표가 계산 불능이었고, 에피소드통계의 라운드 열이
        Claude Code 주행마다 비어 있었다.

        라운드 경계는 벤더 어휘라 서브클래스가 판정해 부른다(claude_code = `assistant` 이벤트
        1건 = API 응답 1건, --include-partial-messages 미사용이라 중복 없음). Codex exec JSONL 은
        turn/item 단위만 노출해 API 응답 경계가 없다 — 그 어댑터는 경계가 생기면 여기를 부른다.
        budget 은 CLI 가 자기 루프 상한을 노출하지 않아 0(=상한 미상)으로 둔다.
        """
        self._model_rounds = int(getattr(self, "_model_rounds", 0) or 0) + 1
        try:
            notify_round(self.CLI_DISPLAY, str(model or self.model or ""), self._model_rounds, 0)
        except Exception:
            pass  # 관측 기록 실패가 스트림 번역을 끊으면 안 된다 (_log_tool_use 의 seam 기록과 같은 규율)
        return self._model_rounds

    def _reset_turn_state(self) -> None:
        """턴 시작 시 어댑터가 들고 있는 턴-국소 상태를 비운다.

        ★서브클래스가 이벤트 페어링용 캐시를 들고 있으면 반드시 여기서 비울 것:
        벤더가 아이템 id 를 턴마다 재사용하면(Codex 는 `item_0`·`item_1` 로 매 턴 리셋된다)
        지난 턴의 잔재가 이번 턴의 같은 id 를 이미 처리한 것으로 오인해 도구 호출 헤더가
        조용히 사라진다 → process_message 의 start↔result 페어링이 한 칸씩 밀린다.
        """
        return None

    def _image_prompt_prefix(self, image_paths: List[str]) -> str:
        """이미지 경로를 프롬프트 머리에 어떻게 알릴지 (CLI 의 읽기 수단이 다름)."""
        img_lines = "\n".join(f"첨부 이미지 경로: {p}" for p in image_paths)
        return f"{img_lines}\n\n"

    # ================= 공통 몸통 =================

    def _log(self, msg: str):
        print(f"[{self.CLI_LABEL}/{self.agent_name}] {msg}")

    @property
    def _store(self) -> CliSessionStore:
        if self.SESSION_STORE is None:
            raise RuntimeError(f"{type(self).__name__}: SESSION_STORE 미설정")
        return self.SESSION_STORE

    def init_client(self) -> bool:
        """CLI 바이너리 탐지 + 인증 자료 해소."""
        self._binary_path = self._find_binary()
        if not self._binary_path:
            print(
                f"[{self.CLI_LABEL}] {self.CLI_DISPLAY} CLI를 찾을 수 없음. "
                f"설치 여부를 확인하십시오."
            )
            return False

        token_source = self._resolve_auth()

        # BaseProvider.is_ready 만족을 위한 마커
        self._client = {"binary": self._binary_path}
        print(
            f"[{self.CLI_LABEL}] {self.agent_name}: 초기화 완료 "
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
        _pair_cursor = 0  # id 없는 결과의 도착 순서 페어링 커서 (n번째 결과 = n번째 호출)
        for event in self.process_message_stream(message, history, images, execute_tool):
            etype = event.get("type")
            if etype == "text":
                final_text += event.get("content", "")
            elif etype == "tool_start":
                # 호출 헤더(이름·인풋) 우선 적재 — 결과는 다음 tool_result 이벤트에서 채운다.
                self._last_tool_calls.append({
                    "id": event.get("id", ""),
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
                # tool_use_id로 페어링 — 병렬 호출 시 옛 [-1] 페어링은 A의 결과를 B에
                # 붙이고 B의 결과(실패 포함)를 유실했다(2026-08-15 수리). id가 비면
                # 도착 순서 커서로 폴백 (결과는 tool_start 순서대로 도착한다).
                _rid = event.get("id", "")
                _slot = None
                if _rid:
                    _slot = next(
                        (tc for tc in self._last_tool_calls if tc.get("id") == _rid),
                        None,
                    )
                if _slot is None and _pair_cursor < len(self._last_tool_calls):
                    _slot = self._last_tool_calls[_pair_cursor]
                _pair_cursor += 1
                if _slot is not None:
                    _slot["result"] = _result
                    _slot["is_error"] = bool(event.get("is_error", False))
            elif etype == "final":
                final_text = event.get("content", final_text)
            elif etype == "error":
                return event.get("content", f"[{self.CLI_DISPLAY} 오류]")
        return final_text or f"[{self.CLI_DISPLAY}가 빈 응답을 반환했습니다]"

    def process_message_stream(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None,
        cancel_check: Callable = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """스트리밍 호출. CLI 의 JSONL 출력을 파싱하여 이벤트 yield.

        Yields:
            {"type": "text", "content": "..."}
            {"type": "tool_start", "name": "...", "input": {...}}
            {"type": "tool_result", "name": "...", "result": "...", "is_error": bool}
            {"type": "thinking", "content": "..."}
            {"type": "final", "content": "..."}
            {"type": "error", "content": "..."}
        """
        # ★턴 상태 초기화는 **어떤 조기 반환보다도 먼저** 한다: "이 함수에 들어오면 턴
        #  상태가 비어 있다"가 조건 없는 불변식이어야, 실패한 턴의 잔재가 다음 턴에
        #  섞이지 않는다(조건부로 두면 '초기화 안 된 턴' 뒤에 옛 지도 태그·페어링 캐시가
        #  살아남는다).
        # 직전 턴이 미완으로 끝났나 — 출력 절단(max_tokens)·마감 실패(deadline). 리셋
        # 판정(_should_reset_session)이 '작업 경계' 유예에 쓴다. 아래 초기화보다 먼저 찍는다.
        self._prev_turn_incomplete = bool(
            getattr(self, "_last_stop_reason", None) == "max_tokens"
            or getattr(self, "last_failure_kind", None))
        # 이 호출이 인지 턴에서 몇 번째 실행 호출인가(0=첫 호출). goal 재실행·자기반성·
        # 약속 재시도는 1 이상 — 같은 작업의 연속이라 세션을 끊지 않는다.
        self._execution_call_ordinal = note_execution_call()
        # 라운드별 컨텍스트 크기 릴레이 (이전 턴 값 잔류 방지)
        self._last_context_size = 0
        # 실패 범주도 턴 상태다 — 지난 턴의 마감이 이번 턴 판단에 새면 안 된다.
        self.last_failure_kind = None
        # 지도 태그 누적 (이전 턴 지도가 새 응답에 새는 것 방지)
        self._pending_map_tags = []
        self._seam = SeamTracker()          # 이 턴의 셸↔IBL 이음매(인접·모델 경유)
        self._model_rounds = 0              # 이 턴의 모델 응답(실행 라운드) 계수 — _note_model_round 가 올린다
        # 벤더 어댑터가 턴 사이에 들고 있는 상태도 함께 비운다
        self._reset_turn_state()

        if not self._client:
            yield {"type": "error",
                   "content": f"{self.CLI_DISPLAY} provider가 초기화되지 않았습니다."}
            return

        # 1) 이미지 → 임시 파일 → 프롬프트에 path 주입
        image_paths: List[str] = self._save_images_to_temp(images or [])

        # 2) 도구 브리지 확보 (벤더마다 방식이 다름 — 파일/인라인)
        mcp_config_path = self._mcp_bridge_acquire()
        try:
            # 2.5) 시스템 프롬프트를 파일로 (윈도우 argv 상한 회피).
            #      리트라이 루프 전체에서 재사용(내용 불변). 실패 시 None → 인자 방식 폴백.
            system_prompt_file = self._write_system_prompt_file()

            # 3) 세션 연속성 결정 (--resume)
            # 정책: history가 비어있으면 새 대화로 간주하여 fresh session, 아니면 저장된 id로 resume.
            # 단, disable_session_persistence가 True면 (의식·평가 등 메타 역할) 항상 fresh.
            if self.disable_session_persistence:
                session_key_val = None
                session_map = {}
                stored_session_id = None
                resume_session_id = None
            else:
                session_key_val = self._get_session_key()
                session_map = self._store.load_map()
                stored_session_id = session_map.get(session_key_val)
                resume_session_id = stored_session_id if (history and stored_session_id) else None
                # history 없으면 (= 새 대화) 기존 매핑 무효화
                if not history and stored_session_id:
                    self._store.clear_agent(session_key_val)
                    stored_session_id = None
                # 크기 기반 리셋: 직전 턴 컨텍스트가 임계 초과면 fresh 로 끊는다.
                # fresh 경로는 _build_prompt_with_history 로 트림된 히스토리를 재시드하므로
                # 맥락은 indiebizOS 기억층 + 트림 히스토리로 이어진다 (raw 중복만 제거).
                if resume_session_id:
                    # 벤더가 세션을 직접 잴 수 있으면 그 실측이 저장값을 이긴다
                    # (_measure_context_size 참조 — 저장값은 '지난 턴 끝'의 추정이다).
                    measured = self._measure_context_size(resume_session_id)
                    if measured:
                        self._store.record_size(session_key_val, measured)
                    prev_size = int(
                        measured or self._store.load_sizes().get(session_key_val) or 0)
                    do_reset, why = self._should_reset_session(prev_size)
                    if why:
                        print(f"[{self.CLI_LABEL}] {self.agent_name}: 세션 컨텍스트 "
                              f"{prev_size:,} > {self.SESSION_RESET_TOKEN_THRESHOLD:,} 토큰 → {why}")
                    if do_reset:
                        self._store.clear_agent(session_key_val)
                        self._store.clear_size(session_key_val)
                        stored_session_id = None
                        resume_session_id = None

            # 4~6) resume 시도 → 만료/무효 시 fresh 로 자동 재시도 (resume→fresh 1회)
            #      + 일시 서버 과부하(529 Overloaded) → backoff 후 재시도 (최대 N회)
            # CLI 가 사라진 세션의 resume 을 만나면 stdout JSON 이 아니라 stderr +
            # 종료코드 1 로 즉사한다. 첫 시도가 그렇게 실패하면 그 에러를 사용자에게
            # 노출하지 않고 삼킨 뒤(deferred) 매핑을 폐기하고 fresh 로 한 번 더 돌린다.
            # 그래야 stale 매핑이 고착되지 않는다.
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
                    full_prompt = self._image_prompt_prefix(image_paths) + full_prompt

                _tools_mode = None
                if getattr(self, "no_tools", False):
                    _tools_mode = "read" if image_paths else "none"
                cmd = self._build_command(
                    mcp_config_path=mcp_config_path,
                    stream=True,
                    resume_session_id=resume_session_id,
                    system_prompt_file=system_prompt_file,
                    tools_mode=_tools_mode,
                )

                _sp_len = len(self.system_prompt or "")
                _msg_len = len(full_prompt or "")
                _resumed = "resume" if resume_session_id else "new"
                self._log(
                    f"call: session={_resumed} "
                    f"system_prompt={_sp_len}자 message={_msg_len}자"
                )

                env = self._build_env()
                start = time.time()
                cwd = self.project_path if self.project_path and self.project_path != "." else None
                try:
                    # ★유저 프롬프트는 argv 가 아니라 stdin 으로 넘긴다: 윈도우 명령줄 상한
                    #  (32,767자)에 걸려 [WinError 206]로 실행 자체가 실패하던 걸 회피. CLI 는
                    #  stdin EOF까지 읽은 뒤 응답하므로 먼저 써넣고 닫는다.
                    #  encoding=utf-8 명시: 윈도우 기본 로케일 인코딩(cp949 등)으로 stdin/stdout이
                    #  깨지지 않도록(한글 프롬프트·응답 JSON 보존).
                    def _spawn():
                        # cmd[0]=self._binary_path 를 참조하도록 매 호출 시 갱신값을 반영
                        return subprocess.Popen(
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

                    proc = _spawn()
                except FileNotFoundError as e:
                    # 세션 도중 데스크톱 앱이 자동 업데이트되면 init 때 캐시한
                    # self._binary_path(버전 폴더 포함)가 삭제되어 spawn이 [Errno 2]로 터진다.
                    # 바이너리를 재해석해 새 버전 경로로 갱신하고 1회 재시도.
                    new_bin = self._find_binary()
                    if new_bin and new_bin != self._binary_path:
                        self._log(
                            f"바이너리 경로 재해석: {self._binary_path} → {new_bin} "
                            f"(자동 업데이트 감지, 재시도)"
                        )
                        self._binary_path = new_bin
                        self._client = {"binary": new_bin}
                        cmd[0] = new_bin
                        try:
                            proc = _spawn()
                        except FileNotFoundError as e2:
                            self.metrics.record_error()
                            yield {"type": "error",
                                   "content": f"{self.CLI_DISPLAY} 바이너리 실행 실패(재해석 후에도): {e2}"}
                            return
                    else:
                        self.metrics.record_error()
                        yield {"type": "error",
                               "content": f"{self.CLI_DISPLAY} 바이너리 실행 실패: {e}"}
                        return

                # ── 무출력 감시 (STREAM_IDLE_TIMEOUT_SEC 참조) ──────────────────
                # stdin 쓰기 **전에** 건다: 큰 프롬프트(자막 전문 등)는 파이프 버퍼를
                # 넘겨 자식이 읽어 주기를 기다리며 블로킹하므로, 그 자리도 자식이
                # 침묵하면 무한 대기다. 감시는 프로세스를 죽여 두 블로킹을 함께 푼다.
                _idle = {"last": time.time(), "fired": 0.0}
                _idle_stop = threading.Event()

                def _idle_watch(_p=None):
                    while not _idle_stop.wait(self.STREAM_IDLE_POLL_SEC):
                        if proc.poll() is not None:
                            return
                        silent = time.time() - _idle["last"]
                        if silent > self.STREAM_IDLE_TIMEOUT_SEC:
                            _idle["fired"] = silent
                            self._log(f"무출력 {int(silent)}초 — 프로세스 종료(마감)")
                            try:
                                proc.kill()
                            except Exception:
                                pass
                            return

                _idle_thread = threading.Thread(
                    target=_idle_watch, daemon=True,
                    name=f"{self.STATE_PREFIX}-idle-watchdog")
                _idle_thread.start()

                # 유저 프롬프트 주입 후 stdin 닫기 (EOF 신호 → CLI 가 응답 시작)
                try:
                    if proc.stdin:
                        proc.stdin.write(full_prompt)
                        proc.stdin.close()
                except (BrokenPipeError, OSError) as e:
                    self._log(f"stdin 프롬프트 쓰기 실패: {e}")

                accumulated_text = ""
                self._last_stop_reason = None   # 이번 attempt 의 마지막 턴 stop_reason (절단 신고용)
                captured_session_id: Optional[str] = None
                committed = False          # 실제 본문(text/tool/thinking)을 하나라도 받았나
                final_seen = False         # 이번 attempt 에서 final 을 방출했나
                resume_err_text = ""       # stdout 에러 텍스트 (보통 비어있음)
                deferred: List[Dict] = []  # resume 시도 중 보류한 터미널 이벤트(error/final)
                try:
                    for raw_line in proc.stdout:
                        _idle["last"] = time.time()     # 한 줄 = 살아 있다는 신호
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

                        sid = self._capture_session_id(event)
                        if sid:
                            captured_session_id = sid

                        err_text = self._stream_error_text(event)
                        if err_text:
                            resume_err_text = err_text

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
                                if t2 == "final":
                                    final_seen = True
                                yield out_event

                    proc.wait(timeout=self.DEFAULT_TIMEOUT_SEC)

                    if _idle["fired"]:
                        # 감시가 죽인 것이므로 EOF 는 "끝"이 아니라 "끊김"이다 —
                        # 조용히 빈 응답·재시도 루프로 흘려보내지 않는다(무한 대기의
                        # 자리를 무한 재시도로 옮기는 꼴). 실패는 여기서 끝난다.
                        self.metrics.record_error()
                        self.last_failure_kind = "deadline"
                        _got = len(accumulated_text)
                        yield {"type": "error",
                               "content": (f"{self.CLI_DISPLAY} 무응답 마감 — "
                                           f"{int(_idle['fired'])}초 동안 출력이 한 줄도 오지 않아 "
                                           f"프로세스를 종료했습니다"
                                           f"(총 {int(time.time() - start)}초 경과, 수신 {_got}자). "
                                           f"모델 호출이 멈춘 것이지 거절된 것이 아닙니다 — "
                                           f"같은 호출을 다시 시도하거나 입력을 줄이세요.")}
                        return

                except subprocess.TimeoutExpired:
                    proc.kill()
                    self.metrics.record_error()
                    yield {"type": "error",
                           "content": f"{self.CLI_DISPLAY} 호출 타임아웃 ({self.DEFAULT_TIMEOUT_SEC}초)"}
                    return
                except Exception as e:
                    self.metrics.record_error()
                    yield {"type": "error", "content": f"{self.CLI_DISPLAY} 스트림 오류: {e}"}
                    return
                finally:
                    _idle_stop.set()          # 감시 해제 (프로세스보다 먼저 — 오살 방지)
                    if proc.poll() is None:
                        proc.kill()

                # 비정상 종료 시 stderr 확보 (resume 실패 메시지가 여기에 담긴다)
                stderr_text = ""
                if proc.returncode is not None and proc.returncode != 0 and not accumulated_text:
                    stderr_text = (proc.stderr.read() if proc.stderr else "").strip()

                # --- resume 실패 판정 (stdout 에러 텍스트 + stderr 종합) ---
                combined = (resume_err_text + " " + stderr_text)
                # session 만료/무효일 때만 재시도 — rate limit·인증 등 일시적 에러로는
                # 멀쩡한 매핑을 폐기하지 않는다 (그 에러는 그대로 사용자에게 보고).
                resume_failed = (
                    is_resume_attempt and not committed and self._is_session_issue(combined)
                )

                if resume_attempt == 0 and resume_failed:
                    # 매핑 폐기 + fresh 재시도 (보류했던 에러는 버린다 → 사용자에 미노출)
                    resume_attempt += 1
                    if session_key_val:
                        self._store.clear_agent(session_key_val)
                    print(
                        f"[{self.CLI_LABEL}] {self.agent_name}: 저장된 세션"
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
                        f"[{self.CLI_LABEL}] {self.agent_name}: 서버 과부하(529) → "
                        f"{delay:.0f}초 후 재시도 {overloaded_retries}/{self.OVERLOADED_MAX_RETRIES}"
                    )
                    time.sleep(delay)
                    continue

                # --- 최종 attempt: 결과 확정 ---
                for ev in deferred:          # 보류했던 터미널 이벤트 방출
                    # ★본문이 온 뒤라면, 본문 이전에 보류된 *빈* final 은 이미 무효다.
                    #  그대로 흘리면 맨 마지막에 도착해 진짜 최종 응답을 덮는다 —
                    #  2026-08-19 ep1253·1254: resume 직후 `result in=0 out=0` 이 보류됐다가
                    #  22분치 작업의 최종 보고를 빈 문자열로 덮어써 사용자가 아무 말도 못 받았다.
                    if (committed and ev.get("type") == "final"
                            and not (ev.get("content") or "").strip()):
                        continue
                    if ev.get("type") == "final":
                        final_seen = True
                    yield ev
                # ★터미널 이벤트 없이 스트림이 끝난 경우(프로세스가 조용히 사라짐):
                #  흘러나온 본문이라도 최종으로 올린다 — 안 그러면 한 턴이 통째로 증발한다
                #  (2026-08-19 ep1251: 22분 작업 뒤 result 미도달 → 최종 0자).
                if not final_seen and accumulated_text.strip():
                    self._log(
                        f"종결 이벤트 없이 종료 — 누적 본문 {len(accumulated_text)}자를 최종으로 승격")
                    yield {"type": "final", "content": accumulated_text.strip()}
                if proc.returncode not in (0, None) and not accumulated_text and not deferred:
                    yield {
                        "type": "error",
                        "content": f"{self.CLI_DISPLAY} 종료 코드 {proc.returncode}: {stderr_text[:500]}",
                    }

                # 세션 매핑 갱신 (disable_session_persistence면 스킵)
                if not self.disable_session_persistence and session_key_val:
                    if captured_session_id and captured_session_id != stored_session_id:
                        session_map[session_key_val] = captured_session_id
                        self._store.save_map(session_map)
                        print(
                            f"[{self.CLI_LABEL}] {self.agent_name}: 세션 저장 "
                            f"({session_key_val} → {captured_session_id[:8]}...)"
                        )
                    # 컨텍스트 크기 기록 — resume 세션은 매 턴 성장하므로 id 변동과 무관하게
                    # 매번 갱신해 다음 턴 리셋 판단의 최신 값을 유지한다.
                    self._store.record_size(session_key_val, self._last_context_size)
                break
        finally:
            self._mcp_bridge_release(mcp_config_path)

    # ================= 공통 헬퍼 =================

    def _finalize_text(self, final_content: str) -> str:
        """최종 응답 확정 — 절단 신고 + 지도 태그 재주입 (벤더 공통 마감).

        서브클래스의 _translate_stream_event 가 종결 이벤트를 만들 때 부른다.
        """
        _truncated = self._last_stop_reason == "max_tokens"
        if _truncated and final_content:
            # 절단의 정직 신고 + 처방 (2026-08-29 ⑫): 표지 없는 절단은 읽는 쪽
            # (사용자·GoalEval·다음 턴)이 "짧게 완결"로 오독한다. 처방을 표지에
            # 싣는 이유 — 재실행이 전체를 다시 쓰면 같은 상한에서 또 잘린다.
            final_content += (
                "\n\n⚠ 이 응답은 출력 토큰 상한에서 절단되었습니다(stop_reason="
                "max_tokens) — 마지막 부분이 미완일 수 있습니다. 이어쓸 때는 전체 "
                "재작성 대신 **잘린 지점 이후의 미완 부분만** 이어서 출력하십시오.")
        # 이번 턴에 캡처한 지도 태그를 최종 응답 끝에 재주입 → 프론트 parseMapData 가 렌더.
        if self._pending_map_tags:
            final_content = (final_content + "\n\n" + "\n".join(self._pending_map_tags)).strip()
            self._pending_map_tags = []
        return final_content

    def _log_tool_use(self, tool_name: str, tool_input: Any):
        """도구 호출을 episode_logger 가 캡처할 형식으로 찍는다.

        ★형식 고정: vocab_crystallization 이 `[<LABEL>/<agent>] tool_use <name> <json>` 을
        정규식으로 판독해 어휘 결정화 재료를 뽑는다. 형식을 바꾸면 그쪽도 같이 고칠 것.
        """
        try:
            input_repr = json.dumps(tool_input, ensure_ascii=False)
        except (TypeError, ValueError):
            input_repr = str(tool_input)
        _cap = (_TOOLUSE_CAP_IBL if str(tool_name).endswith("execute_ibl")
                else _TOOLUSE_CAP)
        self._log(f"tool_use {tool_name} {truncate_for_log(input_repr, _cap)}")
        # 이음매 관측(2026-09-05): 앞 호출이 셸이고 이 호출이 IBL(또는 그 반대)이면 — 앞 **결과 전문**의 값이 이 입력에
        # 되찍혔는지 본다. 궤적 이벤트(seam) + 로그 한 줄로 남겨 사후 지표가 절단된 로그에 기대지 않게 한다.
        try:
            _obs = self._seam.on_tool_use(tool_name, tool_input)
            if _obs:
                record_trajectory_event("seam", _obs)
                if _obs.get("carried"):
                    self._log(f"이음매 {_obs['from']}->{_obs['to']} 모델 경유 {_obs['values']}값 — 값이 컨텍스트를 거쳐 되찍힘(파일로 건네면 사라질 왕복)")
        except Exception:
            pass

    def _log_tool_result(self, result_text: str, is_error: bool):
        """도구 결과를 찍고, 지도 봉투를 캡처해 최종 응답 재주입을 예약한다."""
        # 머리는 자르되 **실패 신호는 삼키지 않는다**. (error) 줄은 폭 자체가 넓고
        # (평문 traceback 은 본문이 유일한 단서), 나머지는 300자 머리에 정직 표지 요약을 잇는다.
        try:
            self._seam.on_tool_result(result_text)     # 이음매 관측용 결과 전문(절단 전)
        except Exception:
            pass
        _cap = _TOOLRESULT_CAP_ERROR if is_error else _TOOLRESULT_CAP
        result_preview = _preview_with_signals(result_text.replace("\n", " "), _cap)
        err_tag = " (error)" if is_error else ""
        self._log(f"tool_result{err_tag} {result_preview}")
        # 지도 봉투(route_map/location_map)를 캡처해 최종 응답 끝에 재주입 예약.
        # CLI 서브프로세스는 결과를 산문으로 요약하며 마커를 흘려버리므로 여기서 붙잡는다.
        if not is_error:
            try:
                for tag in _extract_map_tags(result_text):
                    if tag not in self._pending_map_tags:
                        self._pending_map_tags.append(tag)
            except Exception:
                pass

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

    def _write_system_prompt_file(self) -> Optional[str]:
        """시스템 프롬프트+도구정책을 (에이전트, 스레드)별 고정 임시 파일에 쓰고 경로를 반환.

        인자가 아니라 파일로 넘기기 위함(윈도우 argv 상한 회피).
        고정 경로에 매 호출 덮어써 리트라이 간 재사용하므로 별도 정리가 필요 없다
        (누적되지 않고 덮어써짐). 생성 실패 시 None → 호출 측이 인자 방식으로 폴백.

        ★스레드 식별자가 경로에 들어가는 이유 (2026-08-31): 종전엔 키가 agent_id 뿐이라
        **같은 에이전트의 동시 턴이 한 파일을 공유**했다. 시스템 AI 는 러너가 싱글턴이라
        채팅 턴과 위임/스케줄러 턴이 둘 다 agent_id="system_ai" 로 온다 — 각 턴의 의식
        framing·실행기억이 박힌 서로 다른 프롬프트가 같은 경로를 덮어써, 나중에 spawn 하는
        subprocess 가 **남의 턴 프롬프트**를 읽을 수 있었다. 객체를 사유화해도(turn_ai_scope)
        이 파일이 새면 소용없다 — 격리는 가장 바깥 경계까지 가야 한다.
        턴은 한 스레드가 처음부터 끝까지 몰고(WS 두 경로 모두 워커 스레드에서 drain),
        한 스레드에 동시 턴은 없다. 그래서 스레드 식별자면 충분하고, 파일 수도 워커
        스레드 수로 묶인다(내용 해시로 가르면 턴마다 새 파일이 쌓인다).
        """
        # 도구 없는 원샷에는 도구 정책(차단 네이티브→IBL 안내)이 무의미 — 싣지 않는다
        text = (self.system_prompt or "") + ("" if getattr(self, "no_tools", False) else self.TOOL_POLICY)
        safe = re.sub(
            r"[^A-Za-z0-9_.-]", "_",
            str(self.agent_id or self.agent_name or "default"),
        )[:60]
        path = os.path.join(
            tempfile.gettempdir(),
            f"{self.STATE_PREFIX}_sys_{safe}_t{threading.get_ident():x}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return path
        except OSError as e:
            self._log(f"시스템 프롬프트 파일 생성 실패({e}) → 인자 폴백")
            return None

    # --- 신원 전파: 프로세스 경계를 못 건너는 것들을 spawn 시점에 뜬다 ---

    @staticmethod
    def _current_task_id() -> Optional[str]:
        """spawn 시점(요청 워커 스레드)의 task_id.

        threading.local 은 subprocess→MCP→HTTP 재진입 스레드로 전파되지 않으므로,
        여기서 떠서 env(stdio)/헤더(HTTP)로 동봉한다 — agent_id 전파와 같은 부류.
        시스템 AI cross 위임(_execute_call_project_agent)이 부모 task 를 찾는 데 필요."""
        try:
            from thread_context import get_current_task_id
            return get_current_task_id()
        except Exception:
            return None

    @staticmethod
    def _current_trajectory_identity() -> dict:
        """spawn 시점(요청 워커 스레드)의 episode/run 신원 — task_id 와 같은 부류.

        contextvar(에피소드·궤적)는 subprocess→MCP→HTTP 재진입을 못 건너므로,
        여기서 떠서 env(stdio)/헤더(HTTP)로 동봉한다. 재진입 /ibl/execute 가 이 값을
        채택하면 그 실행의 ibl.*·side_effect.* 사건이 부모 에피소드 척추에 실린다
        (없던 시절 98.4%가 고아 run — 2026-08-29 실측). 에피소드 밖 spawn(스케줄러
        직행 등)은 빈 dict → 미동봉(fail-closed)."""
        try:
            from episode_logger import current_trajectory_identity
            return current_trajectory_identity() or {}
        except Exception:
            return {}

    @staticmethod
    def _current_task_origin() -> Optional[str]:
        """spawn 시점(요청 워커 스레드)의 task_origin — task_id 와 같은 부류.

        이게 없던 시절 아웃오브프로세스 실행의 재진입 /ibl/execute 는 출처를 몰라,
        사람 명령에서 온 쓰기까지 전부 무출처로 원장(write_ledger)에 남았다
        (2026-08-21 실측). 부모가 안 세운 경우(스케줄러 등)는 None → 미동봉(fail-closed)."""
        try:
            from thread_context import get_task_origin
            return get_task_origin()
        except Exception:
            return None

    def _identity_env(self) -> Dict[str, str]:
        """재진입 IBL 실행이 복원할 신원 — env 통로 (서브클래스 _build_env 가 합친다)."""
        env: Dict[str, str] = {}
        if self.project_path and self.project_path != ".":
            env["INDIEBIZOS_PROJECT_PATH"] = str(self.project_path)
        # 발신 신원: subprocess 가 MCP→/ibl/execute로 IBL을 돌릴 때 자기 agent_id를 갖고 가게 한다.
        # in-process 프로바이더는 execute_tool(..., self.agent_id)로 직접 넘기지만,
        # 아웃오브프로세스인 이 부류는 env가 유일한 통로. channel_send/read의 신원 게이트
        # (시스템 AI=system_ai, 프로젝트 에이전트=자기 계정)에 필요.
        if self.agent_id:
            env["INDIEBIZOS_AGENT_ID"] = str(self.agent_id)
        # 태스크 컨텍스트: 시스템 AI cross 위임의 부모 task_id 도 같은 통로로 동봉.
        task_id = self._current_task_id()
        if task_id:
            env["INDIEBIZOS_TASK_ID"] = str(task_id)
        # 태스크 출처: 'user'(사람의 직접 명령) 여부가 원장 행위자·자기수정 게이트의 축.
        origin = self._current_task_origin()
        if origin:
            env["INDIEBIZOS_TASK_ORIGIN"] = str(origin)
        # 궤적 신원(에피소드·부모 run): contextvar 도 프로세스 경계를 못 건넌다.
        ident = self._current_trajectory_identity()
        if ident.get("episode_id") is not None:
            env["INDIEBIZOS_EPISODE_ID"] = str(ident["episode_id"])
        if ident.get("run_id"):
            env["INDIEBIZOS_PARENT_RUN_ID"] = str(ident["run_id"])
        return env

    def _identity_headers(self) -> Dict[str, str]:
        """같은 신원의 HTTP 헤더 통로 (warm HTTP MCP 브리지용).

        ★헤더는 ASCII 전용이라 한글 신원은 quote() 로 퍼센트 인코딩(서버가 unquote).
        """
        headers: Dict[str, str] = {}
        if self.agent_id:
            headers["X-IndieBiz-Agent-Id"] = quote(str(self.agent_id))
        if self.project_path and self.project_path != ".":
            headers["X-IndieBiz-Project-Path"] = quote(str(self.project_path))
        task_id = self._current_task_id()
        if task_id:
            headers["X-IndieBiz-Task-Id"] = quote(str(task_id))
        origin = self._current_task_origin()
        if origin:
            headers["X-IndieBiz-Task-Origin"] = quote(str(origin))
        ident = self._current_trajectory_identity()
        if ident.get("episode_id") is not None:
            headers["X-IndieBiz-Episode-Id"] = quote(str(ident["episode_id"]))
        if ident.get("run_id"):
            headers["X-IndieBiz-Parent-Run-Id"] = quote(str(ident["run_id"]))
        return headers

    def _build_env(self) -> Dict[str, str]:
        """subprocess에 전달할 env — 기본은 상속 환경 + 신원. 인증은 서브클래스가 덧쓴다."""
        env = os.environ.copy()
        env.update(self._identity_env())
        return env

    def _save_images_to_temp(self, images: List[Dict]) -> List[str]:
        """base64 이미지를 임시 파일로 저장하고 경로 리스트 반환.

        images 형식: [{"base64": "...", "media_type": "image/png"}, ...]
        CLI 의 파일 읽기 도구가 vision으로 이미지 내용을 읽는다.
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
                fd, path = tempfile.mkstemp(suffix=ext, prefix=f"{self.STATE_PREFIX}_img_")
                with os.fdopen(fd, "wb") as f:
                    f.write(base64.b64decode(b64))
                paths.append(path)
            except (ValueError, OSError) as e:
                self._log(f"이미지 저장 실패: {e}")
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
