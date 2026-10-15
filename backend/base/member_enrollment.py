"""회원 PC 일회 초대와 설치별 공개키. 원장은 기존 limb_keys 한 벌을 사용한다."""
import base64
import hashlib
import re
import secrets
import time
import uuid

import limb_keys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def issue(device_id):
    with limb_keys._lock:
        data = limb_keys._load()
        rec = limb_keys._find_locked(data, device_id)
        if not rec or not rec.get('member_pc') or rec.get('revoked'):
            raise ValueError('등록된 회원 PC가 필요합니다')
        code = base64.b32encode(secrets.token_bytes(10)).decode()
        rec['desktop_invite'] = {'digest': hashlib.sha256(code.encode()).hexdigest(),
                                 'until': time.time() + 600}
        limb_keys._save()
        return {'code': code, 'expires_at': rec['desktop_invite']['until']}


def exchange(code, request_id, installation_id, public_key, signature):
    if not re.fullmatch(r'[A-Z2-7]{16}', code):
        raise ValueError('등록 코드를 확인하세요')
    try:
        uuid.UUID(request_id)
        uuid.UUID(installation_id)
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True))
        proof = f'member-enroll-v1\n{code}\n{request_id}\n{installation_id}\n{public_key}'
        public.verify(base64.b64decode(signature, validate=True), proof.encode())
    except Exception as exc:
        raise ValueError('설치 증명을 확인할 수 없습니다') from exc
    digest = hashlib.sha256(code.encode()).hexdigest()
    with limb_keys._lock:
        data = limb_keys._load()
        rec = next((r for r in data['keys'].values()
                    if (r.get('desktop_invite') or {}).get('digest') == digest), None)
        if (not rec or rec.get('revoked') or not rec.get('member_pc', {}).get('enabled')
                or rec['desktop_invite']['until'] < time.time()):
            raise ValueError('만료되었거나 사용할 수 없는 등록 코드입니다')
        invite = rec['desktop_invite']
        binding = {'installation_id': installation_id, 'public_key': public_key}
        if invite.get('request_id'):
            if invite['request_id'] != request_id or rec.get('desktop') != binding:
                raise ValueError('이미 사용한 등록 코드입니다')
        else:
            del data['keys'][rec['key']]
            rec['key'] = 'limb_' + secrets.token_urlsafe(24)
            rec['desktop'] = binding
            rec['session'] = secrets.token_hex(8)
            rec['env'] = {}
            rec['last_used'] = None
            days = rec['member_pc'].get('ttl_days', 0)
            rec['expires_at'] = time.time() + days * 86400 if days else None
            invite['request_id'] = request_id
            data['keys'][rec['key']] = rec
        data.setdefault('member_hub_id', uuid.uuid4().hex)
        limb_keys._save()
        return {'success': True, 'key': rec['key'], 'device_id': rec['device_id'],
                'alias': rec['alias'], 'hub_id': data['member_hub_id']}
