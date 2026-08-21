"""IndieBiz OS MCP Server — Claude Code에서 IBL 명령을 실행할 수 있게 해주는 MCP 서버.

외부 사용 (Claude Desktop): project_path를 호출 시 명시.
내부 사용 (indiebizOS가 spawn한 Claude Code): INDIEBIZOS_PROJECT_PATH env로 기본값 주입.
"""
import json
import os
import urllib.request

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

# ── 신원 주입: 두 전송 경로 대응 ──────────────────────────────────────────
# stdio  : 부모가 매 spawn 마다 env(INDIEBIZOS_*)로 주입 → 위 DEFAULT_* 가 그 값.
# http(/mcp): 단일 공유 인스턴스라 env 로는 per-call 신원을 못 실음 → 매 요청 HTTP 헤더로 받는다.
#   부모(claude_code 프로바이더)가 spawn 마다 config 헤더(X-IndieBiz-Agent-Id/-Project-Path)를 실어 보낸다.
# 우선순위: 명시 인자 > HTTP 헤더 > env 기본값. (헤더가 없으면 stdio 동작 그대로 = 하위호환.)
_HDR_AGENT = "x-indiebiz-agent-id"
_HDR_PROJECT = "x-indiebiz-project-path"
_HDR_TASK = "x-indiebiz-task-id"
_HDR_ORIGIN = "x-indiebiz-task-origin"


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


def _trim_for_agent(raw: str) -> str:
    """에이전트에게 줄 응답에서 중복 필드(final_result) 제거.

    파이프라인(>> & ??) 결과에서 final_result는 마지막 step의 '사본'이다 —
    results[-1]에 이미 같은 내용이 들어있고, final_result는 내부 소비자(프론트엔드 UI 펼침·
    웹소켓·캘린더 Goal)를 위한 출력 계약이다. 에이전트(LLM)는 results를 직접 읽으므로
    final_result는 순수 중복 → 토큰만 ~2배로 부풀린다(대형 step에서 한도 초과·파일덤프 유발).
    따라서 '에이전트 경계'인 여기서만 벗겨낸다 — REST 봉투를 받는 내부 계약은 그대로 둔다.
    파싱 불가/형태 불일치면 원본 그대로 반환(graceful). 재직렬화는 ensure_ascii=False
    (한글이 \\uXXXX로 부풀지 않도록).
    """
    try:
        data = json.loads(raw)
    except Exception:
        return raw
    # ★2026-08-22 M1 봉투 다이어트: results[] 가 step *요약*이면(_results_summarized) final_result
    # 가 유일한 원형 — 지우면 데이터가 사라진다. 옛 모양(verbose)일 때만 중복 제거.
    if (isinstance(data, dict) and "final_result" in data
            and isinstance(data.get("results"), list) and data["results"]
            and not data.get("_results_summarized")):
        data.pop("final_result", None)
        raw = json.dumps(data, ensure_ascii=False)
    return _budget_for_agent(raw, data if isinstance(data, dict) else None)


# 에이전트에게 줄 응답의 크기 예산(문자). MCP 도구 결과가 호스트(claude_code) 한도를
# 넘으면 파일덤프→jq 우회 루프에 빠지므로, 그 전에 여기서 우아하게 줄인다.
_AGENT_BUDGET_CHARS = 24_000


def _condense_items(obj, cap: int):
    """재귀 축약: 중첩 JSON 문자열을 관통(파싱→축약→compact 재직렬화)하며
    items 배열을 cap 개로 줄인다(_omitted_items 로 생략 수 노출, total 필드는 보존).

    병렬(&) 결과는 'JSON문자열-in-리스트-in-문자열'로 겹치고(지도 수확과 같은 지형),
    각 겹이 indent 직렬화라 compact 재직렬화만으로도 크게 준다.
    """
    if isinstance(obj, str):
        s = obj.lstrip()
        if s[:1] in ("[", "{"):
            try:
                parsed = json.loads(obj)
            except Exception:
                return obj
            return json.dumps(_condense_items(parsed, cap), ensure_ascii=False)
        return obj
    if isinstance(obj, list):
        return [_condense_items(x, cap) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "items" and isinstance(v, list) and len(v) > cap:
                out[k] = [_condense_items(x, cap) for x in v[:cap]]
                out["_omitted_items"] = len(v) - cap
            else:
                out[k] = _condense_items(v, cap)
        return out
    return obj


def _budget_for_agent(raw: str, parsed=None) -> str:
    """예산 초과 응답을 단계 축약. 층 선택 원칙: 여기는 '에이전트 경계' —
    REST/프론트/웹소켓이 받는 원본 계약은 건드리지 않는다."""
    if len(raw) <= _AGENT_BUDGET_CHARS:
        return raw
    if parsed is None:
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
    if parsed is not None:
        for cap in (10, 5, 3, 1):
            slim = _condense_items(parsed, cap)
            out = json.dumps(slim, ensure_ascii=False)
            if len(out) <= _AGENT_BUDGET_CHARS:
                if isinstance(slim, dict):
                    slim["_trimmed"] = (f"결과가 커서 items 를 소스당 {cap}개로 줄였습니다"
                                        " — 전체 개수는 total/_omitted_items 참조, "
                                        "더 필요하면 limit·필터로 범위를 좁혀 다시 실행하세요")
                    out = json.dumps(slim, ensure_ascii=False)
                return out
        raw = json.dumps(_condense_items(parsed, 1), ensure_ascii=False)
    # 구조 축약으로도 안 줄면(거대 텍스트 등) 꼬리 절단 — 파일덤프보다 낫다.
    head = raw[:_AGENT_BUDGET_CHARS]
    return head + f" …[{len(raw) - len(head)}자 생략 — 범위를 좁혀 다시 실행하세요]"


# ── 이미지 봉투 승격 (2026-08-14, 클로드 코드 경로 대칭) ──────────────────────
# 인프로세스 경로는 수확 관문(system_tools._harvest_images)이 image_data 봉투를
# 진짜 이미지 블록으로 승격하지만, 이 MCP 경로는 /ibl/execute 직행이라 봉투가
# 텍스트로 남는다 — base64 가 24k 예산 꼬리 절단에 걸리면 모델이 잘린 base64
# 쓰레기를 본다(445,625자 사건의 CC판). 여기(에이전트 경계)서 같은 계약으로
# 수확해 MCP ImageContent 로 승격한다. 봉투 계약·상한은 system_tools 와 동일
# 유지 의무 — {"image_data": {"b64", "media_type", ...메타}}, 상한 4장, 본문엔
# b64 뺀 메타를 `image` 키로 남김. ★예산(_budget_for_agent)보다 먼저 돌 것.
# (공용 코어 추출은 직결 경로 정리 때 — 지금은 mcp_server 무의존성 유지가 우선.)

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


def _post_backend(path: str, payload: dict, timeout: int) -> str:
    """백엔드 REST 로의 blocking HTTP POST. 반드시 워커 스레드에서 부를 것.

    ★이벤트 루프에서 직접 부르면 안 된다: FastMCP 는 동기 툴을 루프 위에서 그대로
    실행하는데, HTTP 마운트(/mcp)일 때 이 서버는 백엔드와 *같은 프로세스·같은 루프*라
    자기가 막은 루프가 처리해야 할 /ibl/execute 응답을 기다리는 자기 교착이 된다
    (모든 호출이 urllib timeout 까지 동결 — 라이브 검증에서 실측 120초). stdio 는
    별도 프로세스라 우연히 무사했을 뿐, 같은 이유로 blocking 은 스레드로 뺀다.
    """
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps({"error": e.read().decode()})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def execute_ibl(code: str, project_path: str = "", ctx: Context = None):
    # ★반환 타입 주석 없음이 의도: str 로 못박으면 FastMCP 구조화 출력 검증이
    # 이미지 블록 리스트 반환(위 images 분기)을 거부한다. 텍스트뿐이면 str 그대로.
    """IBL 코드를 실행합니다.

    예시:
        [sense:web_search]{query: "AI 뉴스"}
        [limbs:play_youtube]{query: "Queen Bohemian Rhapsody"}
        [sense:radio]{op: "search", name: "KBS"}
        [limbs:radio]{op: "play", station_id: "kbs_coolfm"}

    project_path를 비워두면 현재 호출 컨텍스트의 프로젝트가 사용됩니다.
    """
    # ctx 는 FastMCP 가 자동 주입(모델에 노출 안 됨). HTTP 경로면 헤더에서 신원을 꺼낸다.
    h_agent, h_project, h_task, h_origin = _http_identity(ctx)
    effective_path = project_path or h_project or DEFAULT_PROJECT_PATH
    agent_id = h_agent or DEFAULT_AGENT_ID
    task_id = h_task or DEFAULT_TASK_ID
    origin = h_origin or DEFAULT_TASK_ORIGIN
    payload = {"code": code, "project_path": effective_path}
    if agent_id:
        payload["agent_id"] = agent_id  # 신원이 있을 때만 전달 (없으면 현 동작 그대로)
    if task_id:
        payload["task_id"] = task_id  # 태스크 컨텍스트 복원 (시스템 AI cross 위임 체인)
    if origin:
        payload["origin"] = origin  # 태스크 출처 복원 — 원장 행위자·자기수정 게이트 축
    raw = await anyio.to_thread.run_sync(
        lambda: _post_backend("/ibl/execute", payload, 120)
    )
    # 이미지 봉투 승격은 예산 절단보다 먼저 — base64 를 들어낸 정리본에 예산을 적용해야
    # 봉투가 잘려 이미지가 유실되거나 base64 조각이 모델에 새는 일이 없다.
    cleaned, images = _harvest_images_for_mcp(raw)
    text = _trim_for_agent(cleaned)
    # 반복 호출 가드 — 조언은 예산 밖 부록(±200자)이라 절단과 무관.
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


if __name__ == "__main__":
    mcp.run()
