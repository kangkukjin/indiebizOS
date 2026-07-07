"""IndieBiz OS MCP Server — Claude Code에서 IBL 명령을 실행할 수 있게 해주는 MCP 서버.

외부 사용 (Claude Desktop): project_path를 호출 시 명시.
내부 사용 (indiebizOS가 spawn한 Claude Code): INDIEBIZOS_PROJECT_PATH env로 기본값 주입.
"""
import json
import os
import urllib.request
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("indiebiz")
BASE = os.environ.get("INDIEBIZOS_BACKEND_URL", "http://localhost:8765")
# 내부 spawn 시 부모(indiebizOS)가 현재 작업 컨텍스트의 project_path를 env로 주입
DEFAULT_PROJECT_PATH = os.environ.get("INDIEBIZOS_PROJECT_PATH", ".")
# 내부 spawn 시 부모가 이 에이전트의 신원(agent_id)을 env로 주입.
# channel_send/read의 발신 신원 게이트에 사용된다. 외부(Claude Desktop) 사용 시엔 없음 → 신원 없음.
DEFAULT_AGENT_ID = os.environ.get("INDIEBIZOS_AGENT_ID", "")

# ── 신원 주입: 두 전송 경로 대응 ──────────────────────────────────────────
# stdio  : 부모가 매 spawn 마다 env(INDIEBIZOS_*)로 주입 → 위 DEFAULT_* 가 그 값.
# http(/mcp): 단일 공유 인스턴스라 env 로는 per-call 신원을 못 실음 → 매 요청 HTTP 헤더로 받는다.
#   부모(claude_code 프로바이더)가 spawn 마다 config 헤더(X-IndieBiz-Agent-Id/-Project-Path)를 실어 보낸다.
# 우선순위: 명시 인자 > HTTP 헤더 > env 기본값. (헤더가 없으면 stdio 동작 그대로 = 하위호환.)
_HDR_AGENT = "x-indiebiz-agent-id"
_HDR_PROJECT = "x-indiebiz-project-path"


def _http_identity(ctx):
    """HTTP 마운트 경로면 요청 헤더에서 (agent_id, project_path)를 꺼낸다.
    stdio(요청 없음)면 (None, None) → 호출부가 env 기본값으로 폴백.

    ★HTTP 헤더는 ASCII 전용이라, 한글 agent_id("홈페이지")·프로젝트 경로는 퍼센트 인코딩으로
    실어 보낸다(프로바이더가 quote) → 여기서 unquote. ASCII 값은 unquote no-op."""
    from urllib.parse import unquote
    try:
        req = ctx.request_context.request if ctx is not None else None
        if req is not None:
            return (unquote(req.headers.get(_HDR_AGENT) or "") or None,
                    unquote(req.headers.get(_HDR_PROJECT) or "") or None)
    except Exception:
        pass
    return (None, None)


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
    if (isinstance(data, dict) and "final_result" in data
            and isinstance(data.get("results"), list) and data["results"]):
        data.pop("final_result", None)
        return json.dumps(data, ensure_ascii=False)
    return raw


@mcp.tool()
def execute_ibl(code: str, project_path: str = "", ctx: Context = None) -> str:
    """IBL 코드를 실행합니다.

    예시:
        [sense:web_search]{query: "AI 뉴스"}
        [limbs:play_youtube]{query: "Queen Bohemian Rhapsody"}
        [sense:radio]{op: "search", name: "KBS"}
        [limbs:radio]{op: "play", station_id: "kbs_coolfm"}

    project_path를 비워두면 현재 호출 컨텍스트의 프로젝트가 사용됩니다.
    """
    # ctx 는 FastMCP 가 자동 주입(모델에 노출 안 됨). HTTP 경로면 헤더에서 신원을 꺼낸다.
    h_agent, h_project = _http_identity(ctx)
    effective_path = project_path or h_project or DEFAULT_PROJECT_PATH
    agent_id = h_agent or DEFAULT_AGENT_ID
    payload = {"code": code, "project_path": effective_path}
    if agent_id:
        payload["agent_id"] = agent_id  # 신원이 있을 때만 전달 (없으면 현 동작 그대로)
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE}/ibl/execute", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return _trim_for_agent(resp.read().decode())
    except urllib.error.HTTPError as e:
        return json.dumps({"error": e.read().decode()})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def read_guide(query: str, read: bool = True) -> str:
    """작업 가이드(워크플로우·레시피)를 가이드 DB에서 검색해 읽습니다.

    복잡한 정기 작업(동향 보고서·작업계획서·출판·배포 등) 전에 관련 가이드를 먼저 확인하세요.
    많은 IBL 액션 설명도 "자세히 read_guide(query=...)" 로 이 도구를 가리킵니다.

    Args:
        query: 검색 키워드 (예: "AI 동향 보고서", "법률", "통계").
        read: True(기본)면 가장 잘 맞는 가이드 본문까지, False면 목록만 반환.

    ※ in-process 프로바이더(Gemini 등)는 이 도구를 자기 프로세스에서 직접 갖는다.
      이 MCP 노출은 아웃오브프로세스인 Claude Code 가 같은 능력을 갖게 하는 통로다.
    """
    payload = json.dumps({"query": query, "read": read}).encode()
    req = urllib.request.Request(
        f"{BASE}/ibl/read_guide", data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps({"error": e.read().decode()})
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
