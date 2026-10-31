"""Authenticated binary transfer, also reachable through the pinned LAN listener."""
import asyncio
import json
import struct
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import resident_pcs as pcs
import resident_transfer_io as transfer
import resident_terminal_lan as lan

router = APIRouter()


def offer():
    return {'version': 1, 'batch_bytes': transfer.BATCH,
            'lan': lan.offer(transfer_socket, channel='transfer')}


def sharing(device):
    import resident_screen
    with resident_screen._lock:
        return any(s.device == device and s.state == 'running'
                   for s in resident_screen._sessions.values())


@router.websocket('/limb/resident/transfer/{sid}')
async def transfer_socket(ws: WebSocket, sid: str):
    await ws.accept()
    try:
        auth = await asyncio.wait_for(ws.receive_json(), 10)
        row = await asyncio.to_thread(transfer.authorize, sid, auth.get('key'), auth.get('installation_id'))
        await ws.send_json({'type': 'ready', 'version': 1, 'batch_bytes': transfer.BATCH,
                            'route': 'lan' if ws.scope.get('terminal_lan') else 'public'})
        while True:
            message = await asyncio.wait_for(ws.receive(), 60)
            if message['type'] == 'websocket.disconnect':
                break
            row = await asyncio.to_thread(transfer.authorize, sid, auth.get('key'), auth.get('installation_id'))
            started = time.monotonic()
            data = message.get('bytes')
            count = 0
            if data is not None:
                if row['direction'] != 'from_pc' or not 8 < len(data) <= transfer.BATCH + 8:
                    raise ValueError('invalid_transfer_batch')
                offset = struct.unpack('!Q', data[:8])[0]
                out = await asyncio.to_thread(transfer.write, sid, offset, data[8:])
                count = len(data) - 8
            else:
                raw = message.get('text', '')
                if len(raw) > 4096:
                    raise ValueError('invalid_transfer_control')
                request = json.loads(raw)
                action = request.get('action', 'info')
                if action == 'read':
                    if row['direction'] != 'to_pc':
                        raise ValueError('transfer_wrong_direction')
                    offset = request.get('offset')
                    block = await asyncio.to_thread(transfer.read, sid, offset, request.get('chunk_size', transfer.BATCH))
                    if await asyncio.to_thread(sharing, row['device']):
                        await asyncio.sleep(len(block) / (512 * 1024))
                    await asyncio.wait_for(ws.send_bytes(struct.pack('!Q', offset) + block), 45)
                    continue
                if action == 'meta' and row['direction'] == 'from_pc':
                    out = await asyncio.to_thread(pcs.transfer_meta, sid, request.get('size'), request.get('sha256'))
                elif action == 'commit' and row['direction'] == 'from_pc':
                    out = await asyncio.to_thread(transfer.commit, sid)
                elif action == 'info':
                    out = row
                else:
                    raise ValueError('invalid_transfer_action')
            # Reserve bandwidth for interactive traffic. The helper also paces reads.
            active = await asyncio.to_thread(sharing, row['device'])
            out = {**out, 'batch_bytes': transfer.BATCH,
                   'interactive_rate': 512 * 1024 if active else 0,
                   'server_ms': round((time.monotonic() - started) * 1000, 2)}
            await asyncio.wait_for(ws.send_json(out), 45)
            if count and active:
                await asyncio.sleep(max(0, count / (512 * 1024) - (time.monotonic() - started)))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        # Fixed error codes only; never echo auth, payloads or filesystem paths.
        code = str(exc) if isinstance(exc, ValueError) and str(exc).replace('_', '').isalnum() else 'transfer_io_error'
        try:
            await ws.send_json({'error': code})
            await ws.close(code=1008)
        except (RuntimeError, WebSocketDisconnect):
            pass
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
