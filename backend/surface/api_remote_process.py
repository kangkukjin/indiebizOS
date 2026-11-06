"""Resident process websocket; device credentials authorize only its own job."""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import limb_keys
import remote_process_sessions as service

router = APIRouter()


@router.websocket('/limb/resident/process/{sid}')
async def process_socket(socket: WebSocket, sid: str):
    await socket.accept()
    tasks = []
    send_lock = asyncio.Lock()
    async def send(value):
        async with send_lock: await socket.send_json(value)
    try:
        auth = await asyncio.wait_for(socket.receive_json(), 10)
        rec = await asyncio.to_thread(limb_keys.resident_auth, auth.get('key'), auth.get('installation_id'))
        task_id = 'remoteprocess_' + sid
        ready = await asyncio.to_thread(service.attach, task_id, rec['device_id'])
        await send(ready)
        if ready['type'] == 'complete':
            return
        async def receive():
            while True:
                message = await socket.receive_json()
                await asyncio.to_thread(service.receive, task_id, message, ready['transport'])
                if message['type'] == 'exit':
                    await send({'type': 'complete'})
                    return
        async def transmit():
            ticks = 0
            while True:
                for message in await asyncio.to_thread(service.take, task_id, ready['transport']): await send(message)
                if ticks % 25 == 0:
                    await asyncio.to_thread(limb_keys.resident_auth, auth.get('key'), auth.get('installation_id'))
                    await send({'type': 'heartbeat'})
                ticks += 1
                await asyncio.sleep(.1)
        tasks = [asyncio.create_task(receive()), asyncio.create_task(transmit())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done: task.result()
    except (WebSocketDisconnect, ValueError, RuntimeError, PermissionError, asyncio.TimeoutError, KeyError):
        pass
    finally:
        for task in tasks: task.cancel()
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)
        try: await socket.close()
        except RuntimeError: pass
