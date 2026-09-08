"""파일 읽기 범위 계약. 잘못된 범위를 다른 범위로 조용히 바꾸지 않는다."""
import re


def normalize_read_range(params):
    """정수/정수 문자열을 검사하고 1-기반 줄 범위를 offset/limit으로 바꾼다.

    offset/start는 0-기반, start_line/end_line은 1-기반 양끝 포함이다.
    limit=0은 빈 범위이며 생략(None)의 전체 읽기와 구별한다.
    tail은 앞쪽 기준 범위와 함께 지정할 수 없다(한쪽을 조용히 무시하지 않는다).
    """
    out = dict(params)
    for key in ('offset', 'start', 'start_line', 'end_line', 'end', 'limit', 'tail'):
        value = params.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not (isinstance(value, int) or
                isinstance(value, str) and re.fullmatch(r'[+-]?\d+', value.strip())):
            raise ValueError(f'{key}는 정수여야 합니다.')
        value = int(value)
        minimum = 1 if key in ('start_line', 'end_line', 'tail') else 0
        if value < minimum:
            raise ValueError(f'{key}는 {minimum} 이상이어야 합니다.')
        out[key] = value
    if out.get('tail') is not None and any(out.get(k) is not None for k in (
            'offset', 'start', 'start_line', 'end_line', 'end', 'limit')):
        raise ValueError('tail은 offset/start/start_line/end_line/end/limit와 함께 지정할 수 없습니다.')
    starts = [out[k] for k in ('offset', 'start') if out.get(k) is not None]
    if out.get('start_line') is not None:
        starts.append(out['start_line'] - 1)
    if starts and any(v != starts[0] for v in starts):
        raise ValueError('offset/start와 start_line이 서로 다른 시작 위치를 가리킵니다.')
    offset = starts[0] if starts else 0
    if starts:
        out['offset'] = offset
    lengths = [out['limit']] if out.get('limit') is not None else []
    for key in ('end_line', 'end'):
        if out.get(key) is not None:
            length = out[key] - offset
            if length < (1 if key == 'end_line' else 0):
                raise ValueError(f'{key}가 시작 위치보다 앞섭니다.')
            lengths.append(length)
    if lengths:
        if any(v != lengths[0] for v in lengths):
            raise ValueError('limit와 끝 위치가 서로 다른 읽기 범위를 가리킵니다.')
        out['limit'] = lengths[0]
    return out


def text_read_bounds(params, total_lines):
    """검사된 범위를 텍스트·문단 모드가 똑같이 적용한다. end는 슬라이스의 배타 끝."""
    tail = params.get('tail')
    if tail is not None:
        return max(0, total_lines - tail), total_lines, True
    offset = params.get('offset') or 0
    limit = params.get('limit')
    end = min(offset + limit, total_lines) if limit is not None else total_lines
    return offset, end, offset > 0 or limit is not None
