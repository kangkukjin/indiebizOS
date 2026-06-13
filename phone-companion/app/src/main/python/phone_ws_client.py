"""phone_ws_client.py — 폰-자아 역방향 WS 클라이언트 (away-case: 폰이 NAT 뒤라도 작동).

폰이 LTE/외부 WiFi 면 맥이 폰을 dial 못 한다(공인 inbound 없음). 그래서 폰이 맥의 *기존*
Cloudflare 터널로 **outbound** WebSocket 을 열어둔다(폰이 거는 건 NAT 통과). 맥(claude_code)이
폰-자아의 몸에서 IBL 을 돌리려 하면 그 열린 길로 execute_ibl 을 보내고, 폰이 로컬 엔진으로 실행해
결과를 돌려준다. Cloudflare(맥 터널)가 중간 서버. 끊기면 재연결.

이 모듈은 이음매 *아래*(호스트/전송) — 폰 전용 transport 코드라 phone-companion 에 둔다(무포크 OK).
"""
import asyncio
import json
import os


async def run_ws_client(execute_local):
    """맥 역방향 WS 를 유지하며 들어오는 ibl_execute 를 폰 로컬에서 실행. 영구 재연결 루프.

    execute_local(code, agent_id) -> result(dict|str): 폰의 정본 엔진 동기 실행 콜백."""
    mac_url = (os.environ.get("INDIEBIZ_MAC_URL") or "").rstrip("/")
    if not mac_url:
        print("[phone-ws] INDIEBIZ_MAC_URL 미설정 — 역방향 채널 비활성(집밖 phone_only 불가)")
        return
    try:
        import websockets
    except Exception as e:
        print(f"[phone-ws] websockets 미가용 — 역방향 채널 비활성: {e}")
        return

    ws_base = mac_url.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_base}/ws/phone-self"

    while True:
        try:
            session = await _login(mac_url)
            if not session:
                print("[phone-ws] 맥 로그인 실패(비번/도달) — 10초 후 재시도")
                await asyncio.sleep(10)
                continue
            async with websockets.connect(f"{ws_url}?session={session}",
                                          ping_interval=30, ping_timeout=20,
                                          max_size=8 * 1024 * 1024) as ws:
                print(f"[phone-ws] 맥 역방향 채널 연결됨: {ws_url}")
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    if data.get("type") != "ibl_execute":
                        continue
                    rid = data.get("id")
                    code = data.get("code", "")
                    aid = data.get("agent_id") or "phone"
                    try:
                        result = await asyncio.to_thread(execute_local, code, aid)
                    except Exception as e:
                        result = {"error": f"폰 로컬 실행 실패: {e.__class__.__name__}: {e}"}
                    await ws.send(json.dumps({"type": "ibl_result", "id": rid,
                                              "result": result}, ensure_ascii=False))
        except Exception as e:
            print(f"[phone-ws] 채널 끊김/실패 — 8초 후 재연결: {e.__class__.__name__}: {e}")
            await asyncio.sleep(8)


async def _login(mac_url: str):
    """맥 원격 런처 세션 획득(WS 쿼리 인증용). 비번=INDIEBIZ_MAC_PASSWORD."""
    pw = os.environ.get("INDIEBIZ_MAC_PASSWORD")
    if not pw:
        return None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{mac_url}/launcher/auth/login", json={"password": pw})
            if r.status_code == 200:
                return (r.json() or {}).get("session_id")
    except Exception as e:
        print(f"[phone-ws] 로그인 오류: {e}")
    return None
