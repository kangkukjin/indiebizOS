"""Owner screen sessions and the separately authenticated helper stream."""
import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

import limb_keys
import resident_screen as screen
import resident_terminal_lan as lan

router = APIRouter()


@router.post('/remote-pcs/screens')
def create(req: dict):
    try:
        return screen.create(req.get('target'), req.get('id'), lan.offer(helper_socket, channel='screen'), bool(req.get('reconnect')))
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete('/remote-pcs/screens/{sid}')
def close(sid: str):
    screen.close(sid)
    return {'closed': True}


async def _finish(ws, sid, side, tasks, token=None, code="transport_lost"):
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    screen.unwatch(sid, side, token)
    await asyncio.to_thread(screen.detach, sid, side, token, code)
    try:
        await ws.close()
    except (RuntimeError, WebSocketDisconnect):
        pass


@router.websocket('/limb/resident/screen/{sid}')
async def helper_socket(ws: WebSocket, sid: str):
    await ws.accept()
    tasks, attached, token, code = [], False, None, "transport_lost"
    try:
        auth = await asyncio.wait_for(ws.receive_json(), 10)
        rec = await asyncio.to_thread(limb_keys.resident_auth, auth.get('key'), auth.get('installation_id'))
        token = auth.get('connection')
        await asyncio.to_thread(screen.attach, sid, rec['device_id'], token)
        attached = True
        wake = asyncio.Event()
        screen.watch(sid, 'helper', asyncio.get_running_loop(), wake, token)
        await ws.send_json(screen.connection_policy(sid, 'lan' if ws.scope.get('terminal_lan') else 'public'))

        async def receive():
            while True:
                message = await ws.receive()
                if message['type'] == 'websocket.disconnect':
                    return
                if message.get('bytes') is not None:
                    screen.guarded(sid, 'helper', token, screen.put_frame, message['bytes'])
                elif message.get('text'):
                    # Worker diagnostics are not exposed as commands or persisted.
                    await asyncio.to_thread(screen.guarded, sid, 'helper', token, screen.device_status, json.loads(message['text']))

        async def send():
            while True:
                wake.clear()
                await asyncio.to_thread(limb_keys.resident_auth, auth.get('key'), auth.get('installation_id'))
                await asyncio.to_thread(screen.guarded, sid, 'helper', token, screen.status)
                for message in screen.guarded(sid, 'helper', token, screen.take):
                    await ws.send_json(message)
                    if message['type'] == 'close':
                        return
                await ws.send_json({'type': 'heartbeat'})
                try:
                    await asyncio.wait_for(wake.wait(), 1)
                except asyncio.TimeoutError:
                    pass

        tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
        pass
    except (ValueError, KeyError, TypeError):
        if attached:
            try:
                screen.current(sid, 'helper', token)
                await asyncio.to_thread(screen.close, sid, '화면 공유 권한 또는 입력 계약을 확인하세요.')
            except ValueError:
                pass
    finally:
        if attached:
            await _finish(ws, sid, 'helper', tasks, token, code)
        else:
            await ws.close()


@router.websocket('/remote-pcs/screens/{sid}/stream')
async def owner_socket(ws: WebSocket, sid: str):
    from api_websocket import _authorize_websocket
    from api_launcher_web import _CORS_ORIGINS_REF, is_external_request
    origin = ws.headers.get('origin')
    expected = str(ws.url).split('/remote-pcs/', 1)[0].replace('wss:', 'https:').replace('ws:', 'http:')
    local_file = origin == 'null' and not is_external_request(ws)
    if origin and not local_file and origin != expected and origin not in (_CORS_ORIGINS_REF or []):
        await ws.close(code=1008, reason='허용되지 않은 화면 공유 출처입니다.')
        return
    if not await _authorize_websocket(ws):
        return
    await ws.accept()
    tasks, attached = [], False
    token = None
    code = "transport_lost"
    try:
        raw_token = ws.query_params.get('connection')
        token = int(raw_token) if raw_token else None
        await asyncio.to_thread(screen.attach, sid, None, token)
        attached = True
        wake = asyncio.Event()
        screen.watch(sid, 'owner', asyncio.get_running_loop(), wake, token)

        async def receive():
            while True:
                message = await ws.receive_json()
                if not await _authorize_websocket(ws):
                    return
                if message.get('type') != 'heartbeat':
                    await asyncio.to_thread(screen.guarded, sid, 'owner', token, screen.input_message, message)

        async def send():
            serial, previous = 0, None
            while True:
                wake.clear()
                if not await _authorize_websocket(ws):
                    return
                state = await asyncio.to_thread(screen.guarded, sid, 'owner', token, screen.status, True)
                if state != previous:
                    await ws.send_json(state)
                    previous = state
                if state['state'] == 'closed':
                    return
                serial, data = screen.guarded(sid, 'owner', token, screen.frame, serial)
                if data:
                    await asyncio.wait_for(ws.send_bytes(data), 10)
                try:
                    await asyncio.wait_for(wake.wait(), 1)
                except asyncio.TimeoutError:
                    pass

        tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, KeyError, TypeError, RuntimeError):
        pass
    finally:
        if attached:
            await _finish(ws, sid, 'owner', tasks, token, code)
        else:
            await ws.close()
