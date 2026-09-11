"""IndieBiz OS MCP Server — Claude Code에서 IBL 명령을 실행할 수 있게 해주는 MCP 서버.

외부 사용 (Claude Desktop): project_path를 호출 시 명시.
내부 사용 (indiebizOS가 spawn한 Claude Code): INDIEBIZOS_PROJECT_PATH env로 기본값 주입.
"""
import json
import os
import re
import sys
import urllib.request
from typing import Optional, List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
import boot_paths  # noqa: E402,F401

import anyio
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("indiebiz")
BASE = os.environ.get("INDIEBIZOS_BACKEND_URL", "http://localhost:8765")
# 내부 spawn 시 부모(indiebizOS)가 현재 작업 컨텍스트의 project_path를 env로 주입
DEFAULT_PROJECT_PATH = os.environ.get("INDIEBIZOS_PROJECT_PATH", ".")
# 내부 spawn 시 부모가 이 에이전트의 신원(agent_id)을 env로 주입.
# channel_send/read의 발신 신원 게이트에 사용된다. 외부(Claude Desktop) 사용 시엔 없음 → 신원 없음.
DEFAULT_AGENT_ID = os.environ.get("INDIEBIZOS_AGENT_ID", "")
# 내부 spawn 시 부모가 현재 태스크 ID를 env로 주입 (시스템 AI 위임 체인).
# threading.local 컨텍스트가 재진입 /ibl/execute 스레드에 없으므로 payload로 복원한다.
DEFAULT_TASK_ID = os.environ.get("INDIEBIZOS_TASK_ID", "")
# 태스크 출처('user'=사람의 직접 명령) — task_id 와 같은 부류. 쓰기 관문 원장(write_ledger)
# 행위자·자기수정 게이트의 축이라 재진입에서도 끊기면 안 된다 (2026-08-21).
DEFAULT_TASK_ORIGIN = os.environ.get("INDIEBIZOS_TASK_ORIGIN", "")
# 궤적 신원(부모 에피소드·부모 run) — task_id 와 같은 부류 (2026-08-29 척추).
# contextvar 는 프로세스 경계를 못 건너므로 부모(claude_code 프로바이더)가 env 로 주입,
# payload 로 복원해 재진입 실행의 사건이 부모 에피소드에 실리게 한다.
DEFAULT_EPISODE_ID = os.environ.get("INDIEBIZOS_EPISODE_ID", "")
DEFAULT_PARENT_RUN_ID = os.environ.get("INDIEBIZOS_PARENT_RUN_ID", "")

# ── 신원 주입: 두 전송 경로 대응 ──────────────────────────────────────────
# stdio  : 부모가 매 spawn 마다 env(INDIEBIZOS_*)로 주입 → 위 DEFAULT_* 가 그 값.
# http(/mcp): 단일 공유 인스턴스라 env 로는 per-call 신원을 못 실음 → 매 요청 HTTP 헤더로 받는다.
#   부모(claude_code 프로바이더)가 spawn 마다 config 헤더(X-IndieBiz-Agent-Id/-Project-Path)를 실어 보낸다.
# 우선순위: 명시 인자 > HTTP 헤더 > env 기본값. (헤더가 없으면 stdio 동작 그대로 = 하위호환.)
_HDR_AGENT = "x-indiebiz-agent-id"
_HDR_PROJECT = "x-indiebiz-project-path"
_HDR_TASK = "x-indiebiz-task-id"
_HDR_ORIGIN = "x-indiebiz-task-origin"
_HDR_EPISODE = "x-indiebiz-episode-id"
_HDR_PARENT_RUN = "x-indiebiz-parent-run-id"


def _http_identity(ctx):
    """HTTP 마운트 경로면 요청 헤더에서 (agent_id, project_path, task_id, origin)을 꺼낸다.
    stdio(요청 없음)면 (None,)*4 → 호출부가 env 기본값으로 폴백.

    ★HTTP 헤더는 ASCII 전용이라, 한글 agent_id("홈페이지")·프로젝트 경로는 퍼센트 인코딩으로
    실어 보낸다(프로바이더가 quote) → 여기서 unquote. ASCII 값은 unquote no-op."""
    from urllib.parse import unquote
    try:
        req = ctx.request_context.request if ctx is not None else None
        if req is not None:
            return (unquote(req.headers.get(_HDR_AGENT) or "") or None,
                    unquote(req.headers.get(_HDR_PROJECT) or "") or None,
                    unquote(req.headers.get(_HDR_TASK) or "") or None,
                    unquote(req.headers.get(_HDR_ORIGIN) or "") or None)
    except Exception:
        pass
    return (None, None, None, None)


def _http_trajectory(ctx):
    """HTTP 마운트 경로의 궤적 신원(episode_id, parent_run_id) — _http_identity 와 한 부류.
    stdio(요청 없음)면 (None, None) → 호출부가 env 기본값으로 폴백."""
    from urllib.parse import unquote
    try:
        req = ctx.request_context.request if ctx is not None else None
        if req is not None:
            return (unquote(req.headers.get(_HDR_EPISODE) or "") or None,
                    unquote(req.headers.get(_HDR_PARENT_RUN) or "") or None)
    except Exception:
        pass
    return (None, None)


def _trim_for_agent(raw: str, actions: int = 1) -> str:
    """최종 반환값을 보존하며 전달 예산에 맞춘다. 초과하면 중간 실행 기록부터 접는다."""
    budget = _agent_budget_chars(actions)
    from ibl_envelope import display_delivery_budget
    from ibl_result_transport import fit_tool_result
    display_budget = display_delivery_budget(raw, budget)
    if display_budget > budget:
        from common.spill import DISPLAY_MCP_OUTPUT_TOKENS
        budget = min(display_budget, _host_cap_chars(DISPLAY_MCP_OUTPUT_TOKENS))
    return fit_tool_result(raw, budget)


# 에이전트에게 줄 응답의 크기 예산(문자) — 2026-09-04 개정: 고정 24,000자 → **프로바이더 규칙과
# 같은 식**. in-process 프로바이더(anthropic/openai/ollama)는 액션당 MAX_TOOL_RESULT_LENGTH=16,000자
# × 문장의 액션 수로 자른다. 이 MCP 경계만 문장 크기와 무관한 24K 고정이라, 세 파일을 `&` 로 한
# 문장에 읽으면(실측 31,909자) 잘리고 에이전트가 파일을 하나씩 다시 읽었다(ep2800: 재읽기 4왕복).
# 그 뒤 에이전트는 큰 문장을 쓰면 벌 받는다는 걸 학습해 1액션 문장 60~75% 로 굳었다.
# 상한은 호스트 CLI 자체 한도(MAX_MCP_OUTPUT_TOKENS, 기본 25,000토큰 — 2.1.258 바이너리 실측) ×
# 실봉투 1.6자/토큰(실측 31,715자=19,425토큰). 호스트가 자기 한도로 구조 무지 절단을 하기 *전에*
# 여기서 원문 참조를 보존하는 구조 축약을 하는 것이 이 경계의 남은 역할이다 — 더 좁게 조이지 않는다.
# 큰 데이터를 줄이는 일은 언어(table:take/select/brief 등 원샷 낱말)의 몫이지 경계의 몫이 아니다.
_PER_ACTION_CHARS = 16_000          # = providers.*.MAX_TOOL_RESULT_LENGTH (test_agent_boundary_budget 이 동율 고정)
_HOST_MCP_TOKENS_DEFAULT = 25_000   # claude CLI MAX_MCP_OUTPUT_TOKENS 기본값
_CHARS_PER_TOKEN = 1.6              # 한글·JSON 혼합 실봉투 실측


def _host_cap_chars(default_tokens: int = _HOST_MCP_TOKENS_DEFAULT) -> int:
    """호스트 CLI 의 MCP 결과 한도(토큰)를 문자로 — env 로 올리면 여기도 따라 올라간다."""
    try:
        tokens = int(os.environ.get("MAX_MCP_OUTPUT_TOKENS") or 0)
    except ValueError:
        tokens = 0
    if tokens <= 0:
        tokens = default_tokens
    return int(tokens * _CHARS_PER_TOKEN)


def _agent_budget_chars(actions: int = 1) -> int:
    """문장의 액션 수에 비례, 호스트 한도 이하. 액션 0·음수는 1 로."""
    n = max(1, int(actions or 1))
    return min(_PER_ACTION_CHARS * n, _host_cap_chars())


_ACTION_HEAD_RE = re.compile(r"\[[a-z_]+:[a-z_]+\]")


def _count_actions(code: str) -> int:
    """IBL 코드의 액션 머리 수(문자열 안 머리는 과계수될 수 있으나 그건 예산을 넓힐 뿐)."""
    return max(1, len(_ACTION_HEAD_RE.findall(code or "")))


# ── 이미지 봉투 승격 (2026-08-14, 클로드 코드 경로 대칭) ──────────────────────
# 인프로세스 경로는 수확 관문(system_tools._harvest_images)이 image_data 봉투를
# 진짜 이미지 블록으로 승격하지만, 이 MCP 경로는 /ibl/execute 직행이라 봉투가
# 텍스트로 남는다 — base64 가 24k 예산 꼬리 절단에 걸리면 모델이 잘린 base64
# 쓰레기를 본다(445,625자 사건의 CC판). 여기(에이전트 경계)서 같은 계약으로
# 수확해 MCP ImageContent 로 승격한다. 봉투 계약·상한은 system_tools 와 동일
# 유지 의무 — {"image_data": {"b64", "media_type", ...메타}}, 상한 4장, 본문엔
# b64 뺀 메타를 `image` 키로 남김. ★전송 예산 적용보다 먼저 돌 것.
# (이미지 수확의 공용 코어 추출은 직결 경로 정리 때.)

_IMAGE_ENVELOPE_KEY = "image_data"
_MAX_TOOL_IMAGES = 4


def _pluck_image_envelopes(node, found, depth=0):
    """이미지 두 계약을 수확하는 재귀 (변이). 실전엔 두 형태가 공존한다(라이브 실측):
    ①수확 관문 봉투 {"image_data": {"b64", "media_type", ...}} (engines:image_gemini 등)
    ②프로바이더 계약 {"images": [{"base64", "media_type", ...}, ...]} (limbs:screen 등 —
      인프로세스 경로에선 프로바이더가 직접 소비하므로 관문이 안 다루지만, MCP 경계에선
      텍스트로 새므로 여기서 번역해야 한다). 수확 항목은 {b64, media_type} 로 정규화."""
    if depth > 16:
        return node
    if isinstance(node, dict):
        env = node.pop(_IMAGE_ENVELOPE_KEY, None)
        if isinstance(env, dict) and env.get("b64"):
            found.append(env)
            node["image"] = {k: v for k, v in env.items() if k != "b64"}
        imgs = node.get("images")
        if isinstance(imgs, list) and any(isinstance(i, dict) and i.get("base64") for i in imgs):
            metas = []
            for i in imgs:
                if isinstance(i, dict) and i.get("base64"):
                    found.append({"b64": i["base64"],
                                  "media_type": i.get("media_type", "image/png")})
                    meta = {k: v for k, v in i.items() if k != "base64"}
                    metas.append(meta or {"note": "이미지 블록으로 첨부됨"})
                else:
                    metas.append(i)
            node["images"] = metas
        for k in list(node.keys()):
            node[k] = _pluck_image_envelopes(node[k], found, depth + 1)
        return node
    if isinstance(node, list):
        return [_pluck_image_envelopes(v, found, depth + 1) for v in node]
    if isinstance(node, str) and (_IMAGE_ENVELOPE_KEY in node or '"base64"' in node):
        try:
            inner = json.loads(node)
        except (json.JSONDecodeError, TypeError):
            return node
        n_before = len(found)
        inner = _pluck_image_envelopes(inner, found, depth + 1)
        if len(found) > n_before:
            return json.dumps(inner, ensure_ascii=False)
        return node
    return node


def _harvest_images_for_mcp(raw: str):
    """(정리된 결과 문자열, [{b64, media_type}]) — 봉투 없으면 원본 그대로(비용 0)."""
    if not isinstance(raw, str) or (_IMAGE_ENVELOPE_KEY not in raw and '"base64"' not in raw):
        return raw, []
    try:
        tree = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw, []
    found = []
    tree = _pluck_image_envelopes(tree, found)
    if not found:
        return raw, []
    return json.dumps(tree, ensure_ascii=False), found[:_MAX_TOOL_IMAGES]


# ── 반복 호출 가드 (2026-08-14, 클로드 코드 경로 어댑터) ─────────────────────
# 공용 코어 = backend/base/repeat_guard.py (직결 경로 어댑터 system_tools.execute_tool 과
# 공유 — 정책 표류 방지, 렌더러 "공용 코어+두 어댑터" 선례). 이 서버는 stdio 모드에서
# backend 층 밖에서 돌므로 base 경로만 좁게 삽입해 임포트한다(boot_paths 전체를 안
# 끄는 것이 의도 — MCP 서버는 얇게 유지).
# stdio = CC 세션당 프로세스라 프로세스-로컬 체인 / HTTP(/mcp) = 공유 인스턴스라
# 신원(agent_id·task_id) 키로 분리. 인메모리 휴리스틱 — 재시작 시 리셋은 수용 비용.
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "base"))
from repeat_guard import advise as _repeat_advisory  # noqa: E402  (key, signature) -> str

# 표면 대기 상한은 backend/common/spill.py 가 소유한다(클라이언트 벽과 짝인 수라 한 곳에서만
# 정해져야 한다 — 여기서 따로 적으면 벽과 어긋나도 아무도 모른다). spill 은 stdlib 뿐이라
# 얇게 끌어와도 이 서버의 가벼움을 해치지 않는다.
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
from common.spill import TICKET_MAX_WAIT_S as _MAX_WAIT_S  # noqa: E402


def _post_backend(path: str, payload: dict, timeout: int) -> str:
    """백엔드 REST 로의 blocking HTTP POST. 반드시 워커 스레드에서 부를 것.

    ★이벤트 루프에서 직접 부르면 안 된다: FastMCP 는 동기 툴을 루프 위에서 그대로
    실행하는데, HTTP 마운트(/mcp)일 때 이 서버는 백엔드와 *같은 프로세스·같은 루프*라
    자기가 막은 루프가 처리해야 할 /ibl/execute 응답을 기다리는 자기 교착이 된다
    (모든 호출이 urllib timeout 까지 동결 — 라이브 검증에서 실측 120초). stdio 는
    별도 프로세스라 우연히 무사했을 뿐, 같은 이유로 blocking 은 스레드로 뺀다.
    """
    payload = dict(payload)
    parent = payload.pop("_runtime_parent", None) or os.environ.get("INDIEBIZ_RUNTIME_PARENT")
    headers = {"Content-Type": "application/json"}
    if parent:
        headers["X-Runtime-Parent"] = parent
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps({"error": e.read().decode()})
    except Exception as e:
        # ★타임아웃은 다른 실패와 다른 사건이다(F51-1): 실행은 백엔드에서 계속 돌고
        #   결말 봉투는 티켓으로 남는다. 뭉개면 호출자가 "실행이 죽었다"로 오독한다.
        #   read 타임아웃=TimeoutError(socket.timeout), connect 타임아웃=URLError(reason=...).
        _reason = getattr(e, "reason", None)
        if isinstance(e, TimeoutError) or isinstance(_reason, TimeoutError):
            return json.dumps({"error": "timed out", "_surface_timeout": True,
                               "_timeout_s": timeout})
        return json.dumps({"error": str(e)})


def _surface_timeout_envelope(ticket: str, timeout_s: int) -> str:
    """표면 대기가 끊겼을 때의 정직한 봉투(F51-1) — '죽었다'가 아니라 '기다림이 끝났다'.

    실행은 백엔드에서 계속 돌고, 최종 봉투는 티켓(data/spill/, 24h)으로 남는다.
    회수는 유한 대기의 반복이라 어떤 길이의 실행도 덮는다."""
    return json.dumps({
        "success": False, "surface_timeout": True, "ticket": ticket,
        "error": (f"표면 대기({timeout_s}초)가 실행보다 먼저 끝났습니다 — 실행은 백엔드에서 "
                  "계속 돌고 있고, 결과 봉투는 잃지 않습니다."),
        "note": (f'회수: execute_ibl{{code: "", recover: "{ticket}", wait: {_MAX_WAIT_S}}} — wait 초 '
                 f"동안 결말을 기다렸다가 돌려줍니다(≤{_MAX_WAIT_S}, 생략하면 즉답). 완료면 원 "
                 "봉투가, 아직 돌고 있으면 진행 상태(마지막 움직임 시각 포함)가 옵니다(보관 24h). "
                 "★셸 sleep 으로 기다리지 말 것 — 그 자리는 이 wait 가 맡는다."),
    }, ensure_ascii=False)


@mcp.tool()
async def execute_ibl(code: str, project_path: str = "",
                      resume: Optional[dict] = None,
                      files: Optional[List[str]] = None,
                      files_from: Optional[List[str]] = None,
                      recover: Optional[str] = None,
                      wait: float = 0,
                      check: bool = False,
                      describe: Optional[List[str]] = None,
                      read_result: Optional[dict] = None,
                      ctx: Context = None):
    # ★반환 타입 주석 없음이 의도: str 로 못박으면 FastMCP 구조화 출력 검증이
    # 이미지 블록 리스트 반환(위 images 분기)을 거부한다. 텍스트뿐이면 str 그대로.
    """IBL 코드를 실행합니다.

    예시:
        [sense:web_search]{query: "AI 뉴스"}
        [limbs:play_youtube]{query: "Queen Bohemian Rhapsody"}
        [sense:radio]{op: "search", name: "KBS"}
        [limbs:radio]{op: "play", station_id: "kbs_coolfm"}

    project_path를 비워두면 현재 호출 컨텍스트의 프로젝트가 사용됩니다.

    resume: 실패 봉투의 resume 값 그대로({from_step, prev_ref}) — 같은 code 를 그 step 부터
        다시 돈다(앞 단 재실행 없음, 스필 24h 유효). {vars_ref} 는 부분 실패 봉투의 산 변수 주입.
        ★턴 범위 변수(2026-09-06): 같은 턴 안에서는 resume 없이도 앞 호출의 `$이름 = …` 가 다음 호출에
        그대로 보인다 — 앞 결과(JSON·행·본문)를 다시 치지 말고 `$이름` 으로 가리킬 것. 봉투 turn_vars 가
        산 이름을 말한다. resume 은 턴을 넘는 24h 회수 자리.
    files: 긴 텍스트/코드를 IBL 파서 밖에서 전달. 코드에서 $file:0, $file:1 로 참조.
        ★수십 KB급 본문은 인라인 대신 files_from 으로 — 도구 호출 JSON 이 커지면
        호출 자체가 전송에서 깨진다(2026-08-30 ep2356, 60KB 실측).
    files_from: files 의 경로 참조판(로컬 파일 경로 목록) — 서버가 내용을 읽어 인라인
        files 뒤에 이어붙인다($file 번호 연속). 큰 본문의 정본 통로: 먼저 임시 파일에
        쓰고 여기에 경로만 싣는다.
    describe: code를 비우고 ["node:action"]으로 계약 조회(1~6개, 실행 없음).
    read_result: code를 비우고 {id,offset,limit,path?}로 기존 원문 회수. path는 키/인덱스 배열(예 ["final_result","items"]), 중첩 JSON을 해제한 값의 문자 페이지. 생략하면 원 봉투(재실행 없음).
    recover: 표면 타임아웃 봉투의 ticket 값 그대로 — 그 실행의 최종 봉투를 회수한다
        (code 는 무시됨, "" 로 두면 됨). 완료면 원 봉투, 실행 중이면 진행 상태,
        기록 없음이면 만료(24h)/미탑재를 정직하게 알린다(F51-1: 표면 대기가 끊겨도
        결과는 잃지 않는다).
    wait: recover 와 함께 — 결말이 날 때까지 **유한 대기**할 초. 기다렸는데도
        안 끝나면 진행 상태를 돌려준다(대기가 끝난 것이지 실행이 죽은 것이 아니다).
        ★처음 실행(code)에는 실을 필요가 없다(2026-09-07 개정): 표면이 언제나 상한까지
        기다리므로 느린 실행을 미리 알아맞혀 wait 를 실을 이유가 사라졌다. 옛 규약(기본
        120초 + 아는 호출만 늘리기)은 예측이 틀릴 때마다 회수 왕복을 물렸다.
        ★긴 실행을 기다릴 때 셸 `sleep` 을 쓰지 말 것 — 전경 sleep 은 막히고 배경
        sleep 은 즉시 돌아와, 대기가 몇 초 간격 폴링으로 무너진다(폴링 1회 = 모델
        왕복 1회. 2026-09-01 실측: 한 주행의 도구 호출 45건 중 16건이 기다림이었다).
        `[self:script]{op:"status", wait}` 와 같은 계약이다.

    check: **실행하지 않고** 정적 통화 검사만 — 문장별 마지막 통화·열(types: items⟨열⟩·prose·scalar·
        effect·?)과 문제(issues: error=실행하면 반드시 실패 / warning=아마)를 돌려준다(0토큰·부작용 0).
        긴 프로그램은 먼저 check 로 보고 초록이면 같은 code 를 실행한다 — 문법을 시험하려고 탐침
        문장을 돌리지 않는다. check 없이도 확정 error 는 실행 전에 error_type:"typecheck" 로 거절된다.

    ★2026-08-22 B23-1: 이 셋은 도구 스키마(tool_loader)와 엔진에는 있었는데 이 MCP 표면에만
    없어서, 봉투 note 가 안내하는 대로 보낸 resume 이 조용히 사라졌다. 표면은 도구 스키마와
    같은 파라미터 집합을 나른다 — 스키마에 새 파라미터를 넣을 때 여기와 api_ibl.IBLRequest 도
    함께 늘릴 것.
    """
    # ctx 는 FastMCP 가 자동 주입(모델에 노출 안 됨). HTTP 경로면 헤더에서 신원을 꺼낸다.
    h_agent, h_project, h_task, h_origin = _http_identity(ctx)
    effective_path = project_path or h_project or DEFAULT_PROJECT_PATH
    agent_id = h_agent or DEFAULT_AGENT_ID
    task_id = h_task or DEFAULT_TASK_ID
    origin = h_origin or DEFAULT_TASK_ORIGIN
    payload = {"code": code, "project_path": effective_path}
    try:
        request_context = ctx.request_context if ctx is not None else None
        runtime_parent = (request_context.request.headers.get("x-runtime-parent")
                          if request_context and request_context.request else None)
    except (AttributeError, LookupError):
        runtime_parent = None
    if runtime_parent:
        payload["_runtime_parent"] = runtime_parent
    if describe is not None:
        payload["describe"] = describe
    if read_result is not None:
        payload["read_result"] = read_result
    # 없을 때만 빼서 옛 호출의 payload 모양을 바꾸지 않는다(무회귀) — B23-1
    if resume is not None:
        payload["resume"] = resume
    if files is not None:
        payload["files"] = files
    if files_from is not None:
        payload["files_from"] = files_from
    if check:
        payload["check"] = True   # 정적 통화 검사만(실행 없음) — 2026-09-05
    if agent_id:
        payload["agent_id"] = agent_id  # 신원이 있을 때만 전달 (없으면 현 동작 그대로)
    if task_id:
        payload["task_id"] = task_id  # 태스크 컨텍스트 복원 (시스템 AI cross 위임 체인)
    if origin:
        payload["origin"] = origin  # 태스크 출처 복원 — 원장 행위자·자기수정 게이트 축
    # 궤적 신원 복원(2026-08-29 척추) — 이 실행을 부모 에피소드의 자식 run 으로 잇는다
    h_epi, h_prun = _http_trajectory(ctx)
    episode_id = h_epi or DEFAULT_EPISODE_ID
    parent_run_id = h_prun or DEFAULT_PARENT_RUN_ID
    if episode_id:
        try:
            payload["episode_id"] = int(episode_id)
        except (TypeError, ValueError):
            pass
    if parent_run_id:
        payload["parent_run_id"] = parent_run_id
    if recover:
        # 회수 경로(F51-1) — 실행이 아니라 조회. 신원·payload 는 필요 없다.
        # wait 를 주면 백엔드가 그만큼 유한 대기하므로 HTTP 대기도 그 위로 잡는다
        # (여기가 먼저 끊기면 유한 대기를 준 의미가 없다).
        _w = max(0.0, min(float(wait or 0), float(_MAX_WAIT_S)))
        raw = await anyio.to_thread.run_sync(
            lambda: _post_backend("/ibl/recover",
                                  {"ticket": recover, "wait": _w}, int(_w) + 30)
        )
    else:
        # 표면 티켓(F51-1) — 아래 대기(120초)가 실행보다 먼저 끝나도 백엔드가 이 티켓으로
        # 최종 봉투를 남긴다(data/spill/, 24h). hex 12자 = api_ibl 의 valid_ticket 계약.
        import uuid
        ticket = uuid.uuid4().hex[:12]
        payload["ticket"] = ticket
        # ★표면은 언제나 상한까지 기다린다(2026-09-07) — 호출자가 느림을 미리 알 필요가 없다.
        #   옛 규약은 기본 120초였고, 넘길 것을 *아는* 호출만 wait 로 늘리게 했다. 그러나
        #   느림은 호출 전에 알 수 있는 사실이 아니고(같은 [self:slide] 가 3초일 때도 120초일
        #   때도 있다), 틀리면 값이 왕복 한 번이다. 짧게 기다려 버는 것은 없으므로(위 spill.py
        #   주석) 예측을 요구하지 않고 늘 상한을 쓴다. wait 는 회수(recover) 쪽 파라미터로 남는다.
        _t = int(_MAX_WAIT_S)
        raw = await anyio.to_thread.run_sync(
            lambda: _post_backend("/ibl/execute", payload, _t)
        )
        try:
            if isinstance(raw, str) and json.loads(raw).get("_surface_timeout"):
                raw = _surface_timeout_envelope(ticket, _t)
        except Exception:
            pass
    # 이미지 봉투 승격은 예산 절단보다 먼저 — base64 를 들어낸 정리본에 예산을 적용해야
    # 봉투가 잘려 이미지가 유실되거나 base64 조각이 모델에 새는 일이 없다.
    cleaned, images = _harvest_images_for_mcp(raw)
    text = await anyio.to_thread.run_sync(lambda: _trim_for_agent(cleaned, _count_actions(code)))
    # 반복 호출 가드 — 조언은 예산 밖 부록(±200자)이라 절단과 무관.
    # ★회수(recover) 폴링은 반복이 정상 사용이라 가드를 안 태운다(F51-1).
    if not recover:
        guard_key = agent_id or task_id or "stdio"
        text += _repeat_advisory(guard_key, f"{code.strip()}|{effective_path}")
    if images:
        import base64 as _b64
        from mcp.server.fastmcp import Image as _McpImage
        blocks = [text]
        for env in images:
            try:
                fmt = (env.get("media_type") or "image/png").split("/")[-1]
                blocks.append(_McpImage(data=_b64.b64decode(env["b64"]), format=fmt))
            except Exception as e:
                blocks.append(f"[이미지 블록 변환 실패: {e}]")
        return blocks
    return text


@mcp.tool()
async def read_guide(query: str, read: bool = True) -> str:
    """작업 가이드(워크플로우·레시피)를 가이드 DB에서 검색해 읽습니다.

    복잡한 정기 작업(동향 보고서·작업계획서·출판·배포 등) 전에 관련 가이드를 먼저 확인하세요.
    많은 IBL 액션 설명도 "자세히 read_guide(query=...)" 로 이 도구를 가리킵니다.

    Args:
        query: 검색 키워드 (예: "AI 동향 보고서", "법률", "통계").
        read: True(기본)면 가장 잘 맞는 가이드 본문까지, False면 목록만 반환.

    ※ in-process 프로바이더(Gemini 등)는 이 도구를 자기 프로세스에서 직접 갖는다.
      이 MCP 노출은 아웃오브프로세스인 Claude Code 가 같은 능력을 갖게 하는 통로다.
    """
    return await anyio.to_thread.run_sync(
        lambda: _post_backend("/ibl/read_guide", {"query": query, "read": read}, 30)
    )


@mcp.tool()
async def reframe(broken_assumption: str, evidence: str, progress: str = "",
                  kind: str = "other", ctx: Context = None) -> str:
    """규정(현재 태스크·이 계획의 전제)이 실행 중 사실이 아니게 됐을 때 의식에게 재규정을 요청합니다.

    전제가 깨졌거나, 이 틀 안에서는 풀 수 없거나, 그대로 하면 위험하다는 것을 알게 됐을 때 부르세요.
    깨진 계획 위에 계속 짓거나 혼자 목표를 바꾸지 마세요 — 새 규정(문제·접근·전제·달성 기준)이
    돌아오고 작업은 그 자리에서 이어집니다(처음부터 다시 시작하지 않습니다). 사소한 오류·재시도로
    풀리는 실패에는 쓰지 않습니다. 한 턴에 최대 2회.

    Args:
        broken_assumption: 깨진 전제 또는 틀린 규정 한 문장('이 계획의 전제' 줄을 그대로 인용하면 좋다).
        evidence: 그것이 깨졌음을 보여주는 근거 — 실제 도구 결과·오류·수치를 3줄 안팎으로.
        progress: 지금까지 확보한 사실·산출물 요약(새 규정이 제약으로 흡수).
        kind: impossible(이 틀 안에서 불가) · dangerous(그대로 하면 위해) · wrong_problem(문제가 다른 것) · other.

    ※ in-process 프로바이더는 같은 도구를 자기 프로세스에서 직접 갖는다(system_tools 'reframe').
      이 MCP 노출은 아웃오브프로세스인 Claude Code 가 같은 능력을 갖게 하는 통로다(read_guide 와 동형).
    """
    h_agent, _h_project, h_task, _h_origin = _http_identity(ctx)
    payload = {
        "broken_assumption": broken_assumption, "evidence": evidence,
        "progress": progress or "", "kind": kind or "other",
        "agent_id": h_agent or DEFAULT_AGENT_ID or None,
        "task_id": h_task or DEFAULT_TASK_ID or None,
    }
    return await anyio.to_thread.run_sync(
        lambda: _post_backend("/ibl/reframe", payload, 240)
    )


@mcp.tool()
async def supervision(op: str, id: str = "", offset: int = 0, limit: int = 12000,
                      name: str = "", input: Optional[dict] = None, version: Optional[int] = None,
                      patches: Optional[List[dict]] = None, ctx: Context = None) -> str:
    """의식·실행 공유 작업대. 인계의 target_blocks 본문을 우선 사용하고 누락·변경된 블록만 response로 읽습니다.
    state/evidence로 상태·근거를 읽습니다. response는 id로 특정 블록을 읽습니다.
    의식은 execute(name,input)로 기존 도구를 사용합니다. 필요한 스키마는 evidence(id='tool:이름').
    보완할 때 patch(version,patches=[{id,hash,old_string,new_string}])로 변경 부분만 교체합니다.
    독립적인 여러 블록은 patches 한 배열, 같은 블록의 여러 수정은 replacements 배열로 묶습니다.
    장문 응답 전체를 다시 출력하지 마세요. 수정 불필요 시 keep.
    response의 offset은 블록 번호, evidence의 offset은 문자 위치입니다.
    """
    agent, _, task, _ = _http_identity(ctx)
    payload = {"op": op, "id": id, "offset": offset, "limit": limit, "name": name,
               "input": input or {}, "version": version, "patches": patches or []}
    req = {"agent_id": agent or DEFAULT_AGENT_ID, "task_id": task or DEFAULT_TASK_ID, "payload": payload}
    return await anyio.to_thread.run_sync(lambda: _post_backend("/ibl/supervision", req, 240))


@mcp.tool()
async def pursuit(op: str, id: str = "", section: str = "", title: str = "",
                  goal_criteria: str = "", progress: Optional[str] = None,
                  next: Optional[str] = None, open_questions: Optional[List[str]] = None,
                  artifacts: Optional[List[str]] = None, waiting_for: str = "", probe: str = "",
                  why: str = "", base_version: Optional[int] = None, event_key: str = "",
                  offset: int = 0, limit: int = 30, ctx: Context = None) -> str:
    """여러 턴의 과제를 읽고 진행을 기록합니다. read section=list는 전체 목차,
    id/section은 상세·events·turns. open은 title/goal_criteria로 명시 생성합니다.
    note는 progress/next/open_questions/artifacts를 고쳐 씁니다. wait는 조건 저장만.
    done은 전체 goal_criteria를 충족한 뒤 why와 함께 호출합니다.
    park/abandon/resume/goal은 상태·전체 목표 변경이며 why가 필요합니다.
    기억은 실행 권한이 아니며 현재 사용자 정정이 우선합니다.
    """
    h_agent, _, h_task, _ = _http_identity(ctx)
    fields = dict(op=op, id=id, section=section, title=title, goal_criteria=goal_criteria,
                  progress=progress, next=next, open_questions=open_questions, artifacts=artifacts,
                  waiting_for=waiting_for, probe=probe, why=why, base_version=base_version,
                  event_key=event_key, offset=offset, limit=limit)
    fields = {k: v for k, v in fields.items() if v is not None and (v != "" or k in {"progress", "next"})}
    payload = {"agent_id": h_agent or DEFAULT_AGENT_ID, "task_id": h_task or DEFAULT_TASK_ID,
               "payload": fields}
    return await anyio.to_thread.run_sync(lambda: _post_backend("/ibl/pursuit", payload, 60))


if __name__ == "__main__":
    mcp.run()
