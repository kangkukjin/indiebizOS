"""설정으로 발행한 HTTP 연결. URL·자격은 운영자 정의가 소유한다."""
import os
from urllib.parse import quote, urlparse

from common.record_contract import fail


def _request(method, url, config, *, payload=None, effect_id=None):
    import httpx
    if urlparse(url).scheme != 'https' or urlparse(url).username:
        fail('validation', '외부 업무 연결은 사용자 정보 없는 HTTPS URL이어야 합니다.')
    headers = {'Accept': 'application/json'}
    if config.get('credential_env'):
        token = os.environ.get(config['credential_env'])
        if not token:
            fail('forbidden', '외부 연결 자격을 설정하세요.')
        headers['Authorization'] = 'Bearer ' + token
    if effect_id and config.get('idempotency_header'):
        headers[config['idempotency_header']] = effect_id
    timeout = config.get('timeout', 15)
    if type(timeout) not in (int, float) or not 1 <= timeout <= 30:
        fail('validation', '외부 연결 timeout은 1~30초입니다.')
    # 전송 중 예외는 dispatch가 unknown으로 기록. 리다이렉트에 자격을 넘기지 않는다.
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        with client.stream(method, url, json=payload, headers=headers) as response:
            content = bytearray()
            for part in response.iter_bytes():
                content.extend(part)
                if len(content) > 262144:
                    return {'status': 'unknown', 'reason': 'response_too_large'}
            import json
            try:
                data = json.loads(content) if content else {}
            except ValueError:
                return {'status': 'unknown', 'reason': 'non_json_response', 'http_status': response.status_code}
            if not isinstance(data, dict):
                return {'status': 'unknown', 'reason': 'invalid_response'}
            # 비동기 202/HTTP 오류를 업무 성공으로 간주하지 않는다.
            if 200 <= response.status_code < 300 and response.status_code != 202 and data.get('status') in {'succeeded', 'failed', 'unknown'}:
                return {'status': data['status'], 'data': data, 'http_status': response.status_code}
            return {'status': 'unknown', 'data': data, 'http_status': response.status_code}


def send(payload, effect_id, config):
    return _request('POST', config.get('url', ''), config, payload=payload, effect_id=effect_id)


def lookup(effect_id, config):
    template = config.get('lookup_url')
    if not template:
        return None
    return _request('GET', template.replace('{effect_id}', quote(effect_id, safe='')), config)


def register():
    from record_dispatch import register_adapter
    register_adapter('http', send, lookup=lookup, idempotent=False)
