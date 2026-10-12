"""Owner-configured native desktop endpoints; no passwords or desktop proxying."""
import ipaddress
import json
import os
import re
import threading
from pathlib import Path

import resident_pcs
from runtime_utils import get_base_path

_lock = threading.RLock()


def _path():
    root = os.environ.get('INDIEBIZ_RUNTIME_STATE_DIR')
    return Path(root or Path(get_base_path()) / 'data') / 'remote_desktops.json'


def _host(value):
    if not isinstance(value, str):
        raise ValueError('접속 주소는 호스트 이름이나 IP로 입력하세요.')
    value = value.strip()
    if not value:
        return ''
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    labels = value.split('.')  # path-ok: DNS 호스트명의 레이블 검증이며 필드 경로가 아님.
    if len(value) > 253 or not all(
        re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
        for label in labels
    ):
        raise ValueError('접속 주소에는 URL·경로·계정·비밀번호를 넣을 수 없습니다.')
    return value.lower()


def validate(profile):
    if not isinstance(profile, dict) or profile.keys() - {'direct_host', 'tunnel_host', 'port'}:
        raise ValueError('invalid_desktop_profile')
    port = profile.get('port', 5900)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('invalid_desktop_port')
    direct = _host(profile.get('direct_host', ''))
    tunnel = _host(profile.get('tunnel_host', ''))
    if tunnel:
        try:
            ipaddress.ip_address(tunnel)
            is_ip = True
        except ValueError:
            is_ip = False
        if is_ip or '.' not in tunnel:
            raise ValueError('Cloudflare 공개 호스트 이름을 입력하세요.')
    return {'direct_host': direct, 'tunnel_host': tunnel, 'port': port}


def _load():
    path = _path()
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def get(target):
    rec = resident_pcs.resolve(target, active=False)
    if rec.get('revoked') or rec['registration']['state'] != 'active':
        raise ValueError('registration_closed')
    with _lock:
        return validate(_load().get(rec['device_id'], {}))


def save(target, profile):
    # A paused/offline helper does not stop the independent desktop connection.
    rec = resident_pcs.resolve(target, active=False)
    if rec.get('revoked') or rec['registration']['state'] != 'active':
        raise ValueError('registration_closed')
    profile = validate(profile)
    with _lock:
        data = _load()
        data[rec['device_id']] = profile
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        with temp.open('w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    return profile
