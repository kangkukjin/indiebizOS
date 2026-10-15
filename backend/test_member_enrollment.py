"""등록 응답 유실, 설치 증명, bearer 복사 및 요청 재생 차단."""
import boot_paths  # noqa: F401
import base64
import hashlib
import json
import time
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import limb_keys
import member_enrollment as enrollment
from api_member_desktop import router
from member_device_auth import MemberRoute


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    monkeypatch.delenv('INDIEBIZ_USERDATA', raising=False)
    monkeypatch.setattr(limb_keys, '_cache', None)
    issued = limb_keys.mint('member', member_pc={})
    private = Ed25519PrivateKey.generate()
    public = base64.b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    code = enrollment.issue(issued['device_id'])['code']
    data = dict(code=code, request_id=str(uuid.uuid4()), installation_id=str(uuid.uuid4()), public_key=public)
    proof = '\n'.join(('member-enroll-v1', code, data['request_id'], data['installation_id'], public))
    data['signature'] = base64.b64encode(private.sign(proof.encode())).decode()
    return issued, private, data


def signed(private, path, body, nonce=None):
    raw = json.dumps(body).encode()
    stamp, nonce = str(int(time.time())), nonce or uuid.uuid4().hex
    message = '\n'.join(('POST', path, hashlib.sha256(raw).hexdigest(), stamp, nonce))
    return dict(content=raw, headers={'content-type': 'application/json', 'x-member-time': stamp,
                'x-member-nonce': nonce, 'x-member-signature': base64.b64encode(private.sign(message.encode())).decode()})


def test_exchange_is_retryable_only_for_identical_installation(setup):
    old, private, request = setup
    first = enrollment.exchange(**request)
    assert enrollment.exchange(**request) == first
    assert limb_keys.validate(old['key']) is None
    assert first['device_id'] == old['device_id']
    with pytest.raises(ValueError):
        enrollment.exchange(**{**request, 'request_id': str(uuid.uuid4())})
    enrollment.issue(old['device_id'])
    with pytest.raises(ValueError):
        enrollment.exchange(**request)


def test_bound_key_requires_proof_and_nonce_cannot_replay(setup):
    _, private, request = setup
    issued = enrollment.exchange(**request)
    app = FastAPI()
    app.router.route_class = MemberRoute
    @app.post('/protected')
    def action(body: dict):
        return {'ok': bool(limb_keys.validate(body['key']))}
    with TestClient(app) as client:
        assert client.post('/protected', json={'key': issued['key']}).status_code == 401
        kwargs = signed(private, '/protected', {'key': issued['key']})
        assert client.post('/protected', **kwargs).json() == {'ok': True}
        assert client.post('/protected', **kwargs).status_code == 401
        altered = signed(private, '/protected', {'key': issued['key'], 'content': 'a'})
        altered['content'] = altered['content'].replace(b'"a"', b'"b"')
        assert client.post('/protected', **altered).status_code == 401


def test_expired_disabled_invite_never_exchanges(setup, monkeypatch):
    old, _, request = setup
    limb_keys.update_member_pc(old['device_id'], enabled=False)
    with pytest.raises(ValueError):
        enrollment.exchange(**request)
    limb_keys.update_member_pc(old['device_id'], enabled=True)
    monkeypatch.setattr(enrollment.time, 'time', lambda: 9999999999)
    with pytest.raises(ValueError):
        enrollment.exchange(**request)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
