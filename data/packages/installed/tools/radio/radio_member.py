"""회원 재생: 방송국 URL 해소만 허브에서, 재생/정지/상태는 회원 기기에서."""
from common.pkg_utils import load_singleton


def control(params, command, exchange, workspace):
    action = params.get('op') or 'play'
    if action not in ('play', 'stop', 'status', 'volume'):
        return {'success': False, 'error': '지원하지 않는 재생 동작'}
    command = {'op': 'media', 'action': action}
    if action == 'play':
        url = params.get('stream_url')
        if not url and params.get('station_id'):
            radio = load_singleton(__file__, 'tool_radio', module_key='_member_radio_catalog')
            url, error = radio._get_korean_stream_url(params['station_id'])
            if error:
                return {'success': False, 'error': error}
        command['url'] = url or ''
    if action == 'volume' and 'volume' not in params:
        return {'success': False, 'error': 'volume이 필요합니다'}
    if 'volume' in params:
        volume = params['volume']
        if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not 0 <= volume <= 100:
            return {'success': False, 'error': 'volume은 0~100 숫자여야 합니다'}
        command['volume'] = volume
    return exchange(command)
