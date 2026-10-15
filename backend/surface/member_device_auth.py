"""설치에 묶인 회원 자격은 bearer 복사만으로 사용할 수 없다."""
import base64
import hashlib
import json
import threading
import time

from fastapi import HTTPException
from fastapi.routing import APIRoute
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import limb_keys

_lock = threading.Lock()
_nonces = {}


class MemberRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            body = await request.body()
            key = request.headers.get('x-member-key', '')
            if not key and body:
                try:
                    value = json.loads(body)
                    key = value.get('key', '') if isinstance(value, dict) else ''
                except ValueError:
                    pass
            rec = limb_keys.validate(key) if isinstance(key, str) else None
            binding = (rec or {}).get('desktop')
            if binding:
                stamp = request.headers.get('x-member-time', '')
                nonce = request.headers.get('x-member-nonce', '')
                message = '\n'.join((request.method, request.url.path + ("?" + request.url.query if request.url.query else ""),
                                     hashlib.sha256(body).hexdigest(), stamp, nonce))
                try:
                    if abs(time.time() - int(stamp)) > 90 or not 16 <= len(nonce) <= 80:
                        raise ValueError()
                    public = Ed25519PublicKey.from_public_bytes(base64.b64decode(binding['public_key'], validate=True))
                    public.verify(base64.b64decode(request.headers.get('x-member-signature', ''), validate=True), message.encode())
                    with _lock:
                        now = time.time()
                        for item, until in list(_nonces.items()):
                            if until < now:
                                del _nonces[item]
                        item = (rec['device_id'], nonce)
                        if item in _nonces or len(_nonces) >= 100000:
                            raise ValueError()
                        _nonces[item] = now + 180
                except Exception as exc:
                    raise HTTPException(401, '회원 PC 설치 증명이 필요합니다') from exc
            return await original(request)
        return handler
