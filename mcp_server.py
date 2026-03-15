"""IndieBiz OS MCP Server — Claude Code에서 IBL 명령을 실행할 수 있게 해주는 MCP 서버"""
import json
import urllib.request
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("indiebiz")
BASE = "http://localhost:8765"

@mcp.tool()
def execute_ibl(code: str, project_path: str = ".") -> str:
    """IBL 코드를 실행합니다.

    예시:
        [sense:web_search]{query: "AI 뉴스"}
        [limbs:play_youtube]{query: "Queen Bohemian Rhapsody"}
        [sense:search_radio]{name: "KBS"}
        [limbs:radio_play]{station_id: "kbs_coolfm"}
    """
    data = json.dumps({"code": code, "project_path": project_path}).encode()
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
