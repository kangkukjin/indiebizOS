"""ODsay 대중교통 경로 → items. 자동차 경로로 폴백하지 않는다."""
from datetime import datetime, timezone
import math

from common.api_client import api_call
from common.auth_manager import check_api_key


def _error(message, kind='provider_error', **extra):
    return {'success': False, 'error': message, 'error_type': kind,
            'mode': 'transit', 'source': 'odsay', 'items': [], **extra}


def _coord(value, geocode):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('출발지와 목적지를 장소명 또는 경도,위도로 지정하세요.')
    if ',' in value:
        pieces = value.split(',')
        if len(pieces) != 2:
            raise ValueError('좌표는 경도,위도 형식입니다.')
        try:
            lng, lat = map(float, pieces)
        except ValueError:
            raise ValueError('좌표는 숫자 경도,위도 형식입니다.')
        label = value
    else:
        result = geocode(value)
        if not result:
            raise ValueError(f'장소를 찾을 수 없습니다: {value}')
        lng, lat, label = result
    if not all(math.isfinite(v) for v in [lng, lat]) or not -180 <= lng <= 180 or not -90 <= lat <= 90:
        raise ValueError('좌표 범위를 벗어났습니다.')
    return lng, lat, label


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f'제공사 응답의 {name}이 유효한 수치가 아닙니다.')
    return value


def normalize(payload):
    if not isinstance(payload, dict):
        return _error('ODsay 응답이 객체가 아닙니다.', 'invalid_response')
    if payload.get('error'):
        err = payload['error']
        code = err.get('code') if isinstance(err, dict) else None
        # 공통 HTTP 오류에 URL/인증 쿼리가 포함될 수 있어 전문을 재노출하지 않는다.
        return _error('ODsay 경로 조회에 실패했습니다.' + (f' (code={code})' if isinstance(code, (str, int)) and len(str(code)) < 12 else ''),
                      'no_route' if str(code) in ('3','4','5','6','-98','-99') else 'provider_error', provider_code=code if isinstance(code, int) else None)
    result = payload.get('result')
    if not isinstance(result, dict) or not isinstance(result.get('path'), list):
        return _error('ODsay 경로 목록이 없습니다.', 'invalid_response')
    if result.get('searchType') not in (0, 1, 2):
        return _error('ODsay 경로 종류를 해석할 수 없습니다.', 'invalid_response')
    if not result['path']:
        return _error('검색된 대중교통 경로가 없습니다.', 'no_route')
    if result['searchType'] != 0:
        return _error('도시간 구간만 반환되었습니다. 터미널까지/터미널 이후 연결을 포함한 완전 경로는 아직 지원하지 않습니다.',
                      'incomplete_route', partial=True,
                      items=[{'complete': False, 'search_type': result['searchType'], 'provider_route': p}
                             for p in result['path'] if isinstance(p, dict)])
    items, rejected = [], []
    for i, path in enumerate(result['path']):
        try:
            if not isinstance(path, dict) or not isinstance(path.get('info'), dict):
                raise ValueError('요약 정보가 없습니다.')
            info, segments = path['info'], path.get('subPath')
            if not isinstance(segments, list) or not segments:
                raise ValueError('이동 구간이 없습니다.')
            for seg in segments:
                if not isinstance(seg, dict) or seg.get('trafficType') not in (1, 2, 3):
                    raise ValueError('지원 밖 이동 수단입니다.')
                _number(seg.get('sectionTime'), 'sectionTime')
            items.append({'route_index': i, 'complete': True, 'path_type': path.get('pathType'),
                          'duration_min': _number(info.get('totalTime'), 'totalTime'),
                          'walking_distance_m': _number(info.get('totalWalk'), 'totalWalk'),
                          'fare_krw': _number(info.get('payment'), 'payment'),
                          'transfer_count': max(0, sum(s['trafficType'] in (1, 2) for s in segments)-1),
                          'segments': segments, 'provider_info': info})
        except (ValueError, TypeError) as exc:
            rejected.append({'route_index': i, 'error': str(exc)})
    if not items:
        return _error('유효한 대중교통 경로를 해석하지 못했습니다.', 'invalid_response', rejected=rejected)
    return {'success': True, 'source': 'odsay', 'mode': 'transit', 'items': items,
            'total': len(items), 'partial': bool(rejected), 'rejected': rejected,
            'live_arrival': False, 'observed_at': datetime.now(timezone.utc).isoformat(),
            'note': '도시내 경로의 제공사 예상 시간입니다. 실시간 도착·출발시각별 경로·좌석 예약은 포함하지 않습니다.'}


def route(params, geocode):
    if any(k in params for k in ('waypoints', 'avoid', 'priority')):
        return _error('waypoints/avoid/priority는 자동차 옵션입니다. 대중교통 결과는 table:sort로 정렬하세요.', 'invalid_params')
    try:
        start = _coord(params.get('origin'), geocode)
        end = _coord(params.get('destination'), geocode)
    except ValueError as exc:
        return _error(str(exc), 'invalid_params')
    ready, _ = check_api_key('odsay')
    if not ready:
        return _error('ODSAY_API_KEY가 필요합니다. 좌표 대신 장소명을 쓰면 KAKAO_REST_API_KEY도 필요합니다.', 'credentials_missing')
    payload = api_call('odsay', '/v1/api/searchPubTransPathT',
                       params={'SX': start[0], 'SY': start[1], 'EX': end[0], 'EY': end[1],
                               'SearchType': 0, 'SearchPathType': 0, 'output': 'json'}, timeout=20)
    result = normalize(payload)
    result['origin'] = {'lng': start[0], 'lat': start[1], 'name': start[2]}
    result['destination'] = {'lng': end[0], 'lat': end[1], 'name': end[2]}
    return result
