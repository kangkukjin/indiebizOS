"""IndieBiz OS MCP Server — Claude Code에서 IBL 명령을 실행할 수 있게 해주는 MCP 서버.

외부 사용 (Claude Desktop): project_path를 호출 시 명시.
내부 사용 (indiebizOS가 spawn한 Claude Code): INDIEBIZOS_PROJECT_PATH env로 기본값 주입.
"""
import json
import os
import urllib.request
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("indiebiz")
BASE = os.environ.get("INDIEBIZOS_BACKEND_URL", "http://localhost:8765")
# 내부 spawn 시 부모(indiebizOS)가 현재 작업 컨텍스트의 project_path를 env로 주입
DEFAULT_PROJECT_PATH = os.environ.get("INDIEBIZOS_PROJECT_PATH", ".")
# 내부 spawn 시 부모가 이 에이전트의 신원(agent_id)을 env로 주입.
# channel_send/read의 발신 신원 게이트에 사용된다. 외부(Claude Desktop) 사용 시엔 없음 → 신원 없음.
DEFAULT_AGENT_ID = os.environ.get("INDIEBIZOS_AGENT_ID", "")
# 폰-자아 away-case: 부모가 "1"로 주입하면 IBL 실행을 폰 역방향 WS 로 보내라고 백엔드에 신호.
ROUTE_TO_PHONE = os.environ.get("INDIEBIZOS_ROUTE_TO_PHONE", "") == "1"


@mcp.tool()
def execute_ibl(code: str, project_path: str = "") -> str:
    """IBL 코드를 실행합니다.

    예시:
        [sense:web_search]{query: "AI 뉴스"}
        [limbs:play_youtube]{query: "Queen Bohemian Rhapsody"}
        [sense:radio]{op: "search", name: "KBS"}
        [limbs:radio]{op: "play", station_id: "kbs_coolfm"}

    project_path를 비워두면 현재 호출 컨텍스트의 프로젝트가 사용됩니다.
    """
    effective_path = project_path or DEFAULT_PROJECT_PATH
    payload = {"code": code, "project_path": effective_path}
    if DEFAULT_AGENT_ID:
        payload["agent_id"] = DEFAULT_AGENT_ID  # env에 신원이 주입됐을 때만 전달 (없으면 현 동작 그대로)
    if ROUTE_TO_PHONE:
        payload["route_to_phone_ws"] = True  # 폰-자아 away-case: 백엔드가 폰 WS 로 릴레이
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE}/ibl/execute", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps({"error": e.read().decode()})
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
