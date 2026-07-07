# MCP stdio → HTTP 전환 핸드오프

## 왜
내부 `claude_code` 에이전트의 IBL 도구(`mcp__indiebizos__execute_ibl`)가 stdio MCP 서버
(`mcp_server.py`)를 **매 호출 새로 spawn** → python 콜드스타트 + 핸드셰이크 완료 전에 첫
도구 호출이 나가는 **연결 레이스**로 `No such tool available: mcp__indiebizos__execute_ibl`
이 반복. (풀네임 에러 = 모델은 이름을 정확히 알았는데 그 시점에 등록 전 = naming/discovery 아닌
타이밍 문제.) 백엔드는 상시 떠 있으니 warm HTTP 엔드포인트로 바꾸면 콜드스타트가 사라져
레이스가 구조적으로 제거된다.

## 이미 된 것 (커밋됨)
- **backend `/mcp` 마운트** (`backend/api.py`, `de37ad7`): `mcp_server.mcp` 를 임포트,
  `streamable_http_path="/"` + `app.mount("/mcp", streamable_http_app())`, 세션 매니저를
  lifespan 에 배선. `transport_security` = DNS 리바인딩 방어 ON + `allowed_hosts` 를 localhost
  로 한정(터널 외부 Host 로 무단 IBL 실행 차단). **stdio config 는 그대로 = additive, 회귀 0.**
  격리 검증: initialize→tools/list 에 `execute_ibl`·`read_guide` 노출.
- **per-request 신원 통로** (`mcp_server.py`, `c5ffa2a`): `execute_ibl` 이 HTTP 헤더
  `X-IndieBiz-Agent-Id` / `X-IndieBiz-Project-Path` 에서 신원을 읽음(FastMCP `Context`).
  우선순위 = 명시 인자 > 헤더 > env. 헤더 없으면 env 폴백(stdio 하위호환).
  **★헤더는 ASCII 전용 → 한글 신원은 퍼센트 인코딩**(서버가 `unquote`). 격리 검증(한글 왕복).

## 남은 것 (part 2 — 실기 CLI 라이브 검증 필요)
`backend/providers/claude_code.py` 가 spawn 마다 **HTTP MCP config(인코딩 헤더 포함)** 를 쓰게
하고, 검증 후 기본 경로를 HTTP 로 전환.

### 1) 플래그 게이팅 (기본 stdio 유지)
`INDIEBIZOS_MCP_HTTP` env(기본 "0"). "1" 일 때만 HTTP config 사용 → 라이브 검증 전까지 회귀 0.

### 2) per-spawn HTTP config (★공유 파일 금지)
신원이 config 안에 들어가고 **동시에 여러 에이전트가 돌 수 있으므로**, 고정 파일 하나를
덮어쓰면 A/B 에이전트가 서로의 신원을 읽는 레이스가 난다. **spawn 마다 유니크 temp 파일**로
쓰고 실행 후 정리(`tempfile` + finally). 예:

```python
from urllib.parse import quote
def _http_mcp_config_path(self):
    if os.environ.get("INDIEBIZOS_MCP_HTTP", "0") != "1":
        return None  # 호출부에서 stdio(get_mcp_config_path())로 폴백
    headers = {}
    if self.agent_id:
        headers["X-IndieBiz-Agent-Id"] = quote(str(self.agent_id))
    if self.project_path and self.project_path != ".":
        headers["X-IndieBiz-Project-Path"] = quote(str(self.project_path))
    cfg = {"mcpServers": {"indiebizos": {
        "type": "http",
        "url": "http://localhost:8765/mcp/",   # ★트레일링 슬래시(mount /mcp + 내부 "/")
        "headers": headers,
    }}}
    # spawn 마다 유니크 파일 (동시 에이전트 신원 충돌 방지), 실행 후 삭제
    import tempfile, json
    fd, path = tempfile.mkstemp(prefix="ccmcp_", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f)
    return path
```
그리고 `_run` 흐름(현 `mcp_config_path = get_mcp_config_path()` 지점)에서:
```python
_http_cfg = self._http_mcp_config_path()
mcp_config_path = _http_cfg or get_mcp_config_path()
# ... 실행 후 finally 에서 _http_cfg 있으면 os.remove(_http_cfg)
```
HTTP 모드일 땐 `_build_env` 의 `INDIEBIZOS_AGENT_ID`/`INDIEBIZOS_PROJECT_PATH` 는 무의미
(env→stdio 통로라). 남겨둬도 무해(헤더가 우선). 굳이 안 지워도 됨.

### 3) ★반드시 실기 검증할 것 (여기서 못 함 — 이 환경엔 claude CLI 없음)
- **CLI HTTP MCP config 스키마**: 버전마다 `{"type":"http",...}` vs `{"transport":"http",...}`
  vs `--mcp-config` inline 등 다름. `claude mcp add --help` / 실제 버전 문서로 정확한 키 확인.
  **틀리면 내부 에이전트가 IBL 접근을 통째로 잃는다** → 반드시 플래그 ON 상태로 한 에이전트
  turn 을 돌려 `execute_ibl` 이 레이스 없이 잡히는지 확인 후에만 기본 전환.
- **URL/슬래시**: `/mcp` vs `/mcp/` (Starlette mount + 내부 "/" 라 `/mcp/` 가 직행). 307
  리다이렉트를 MCP 클라이언트가 따르는지 확인.
- **신원 왕복**: HTTP 모드에서 채널 발신(others:*)이 올바른 agent_id 로 게이트 통과하는지
  (한글 agent_id "홈페이지" 포함) — payload 에 헤더 신원이 실려야 함.
- **성능**: warm HTTP 라 첫 호출 레이스가 사라지는지(에피소드에서 반복되던 ToolSearch 폴백이
  안 뜨는지).

### 4) 전환 순서
1. 위 `_http_mcp_config_path` + finally 정리 구현(플래그 OFF 기본).
2. **백엔드 재시작**(api.py `/mcp` 마운트가 라이브가 되려면 필수 — `python api.py` 는 hot-reload 아님).
3. `INDIEBIZOS_MCP_HTTP=1` 로 한 turn 라이브 검증(위 4항목).
4. 통과하면 플래그 기본 "1" 로, 또는 stdio config 를 http 로 교체. 실패하면 플래그만 OFF(즉시 복구).

## 참고 파일
- `backend/api.py` (/mcp 마운트) · `mcp_server.py` (헤더 신원) · `backend/providers/claude_code.py`
  (`_build_command` 924행 `--mcp-config`, `_build_env` 951/956 env 신원, `get_mcp_config_path` 131행)
- `data/claude_code_mcp.json` (현 stdio config — fresh-read 라 교체 안전)
