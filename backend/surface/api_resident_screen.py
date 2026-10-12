"""Owner screen sessions and the separately authenticated helper stream."""
import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

import limb_keys
import resident_screen as screen
import resident_terminal_lan as lan

router = APIRouter()


@router.post('/remote-pcs/screens')
def create(req: dict):
    try:
        return screen.create(req.get('target'), req.get('id'), lan.offer(helper_socket, channel='screen'))
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete('/remote-pcs/screens/{sid}')
def close(sid: str):
    screen.close(sid)
    return {'closed': True}


async def _finish(ws, sid, side, tasks):
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    screen.unwatch(sid, side)
    reason = ("원격 PC의 연결이나 화면·입력 접근 권한을 확인한 뒤 다시 연결하세요."
              if side == "helper" else "화면 공유가 종료됐습니다.")
    await asyncio.to_thread(screen.close, sid, reason)
    try:
        await ws.close()
    except (RuntimeError, WebSocketDisconnect):
        pass


@router.websocket('/limb/resident/screen/{sid}')
async def helper_socket(ws: WebSocket, sid: str):
    await ws.accept()
    tasks, attached = [], False
    try:
        auth = await asyncio.wait_for(ws.receive_json(), 10)
        rec = await asyncio.to_thread(limb_keys.resident_auth, auth.get('key'), auth.get('installation_id'))
        await asyncio.to_thread(screen.attach, sid, rec['device_id'])
        attached = True
        wake = asyncio.Event()
        screen.watch(sid, 'helper', asyncio.get_running_loop(), wake)
        await ws.send_json({'type': 'ready'})

        async def receive():
            while True:
                message = await ws.receive()
                if message['type'] == 'websocket.disconnect':
                    return
                if message.get('bytes') is not None:
                    screen.put_frame(sid, message['bytes'])
                elif message.get('text'):
                    # Worker diagnostics are not exposed as commands or persisted.
                    await asyncio.to_thread(screen.close, sid, '원격 PC에서 화면 공유 권한을 허용한 뒤 다시 연결하세요.')
                    return

        async def send():
            while True:
                wake.clear()
                await asyncio.to_thread(limb_keys.resident_auth, auth.get('key'), auth.get('installation_id'))
                await asyncio.to_thread(screen.status, sid)
                for message in screen.take(sid):
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
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, KeyError, TypeError, RuntimeError):
        pass
    finally:
        if attached:
            await _finish(ws, sid, 'helper', tasks)
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
    try:
        await asyncio.to_thread(screen.attach, sid)
        attached = True
        wake = asyncio.Event()
        screen.watch(sid, 'owner', asyncio.get_running_loop(), wake)

        async def receive():
            while True:
                message = await ws.receive_json()
                if not await _authorize_websocket(ws):
                    return
                if message.get('type') != 'heartbeat':
                    await asyncio.to_thread(screen.input_message, sid, message)

        async def send():
            serial, previous = 0, None
            while True:
                wake.clear()
                if not await _authorize_websocket(ws):
                    return
                state = await asyncio.to_thread(screen.status, sid, True)
                if state != previous:
                    await ws.send_json(state)
                    previous = state
                if state['state'] == 'closed':
                    return
                serial, data = screen.frame(sid, serial)
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
            await _finish(ws, sid, 'owner', tasks)
        else:
            await ws.close()
