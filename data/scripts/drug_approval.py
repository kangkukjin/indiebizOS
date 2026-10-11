"""MFDS approved products, including prescription products; no patient-record writes.

Official schema: https://www.data.go.kr/data/15095677/openapi.do (2026-10-12).
The registered script uses JSON stdin/stdout; authentication stays in api_client.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import boot_paths  # noqa: E402,F401
from common.api_client import api_call  # noqa: E402

ENDPOINT = '/1471000/DrugPrdtPrmsnInfoService08/getDrugPrdtPrmsnDtlInq08'
SOURCE = 'https://www.data.go.kr/data/15095677/openapi.do'


def lookup(args):
    if not isinstance(args, dict):
        return {'success': False, 'error': '입력은 query 또는 id를 담은 객체입니다.', 'items': []}
    query, item_id = args.get('query'), args.get('id')
    page, limit = args.get('page', 1), args.get('limit', 20)
    if (not (query or item_id)
            or query and not isinstance(query, str) or item_id and not isinstance(item_id, str)
            or type(page) is not int or page < 1 or type(limit) is not int or not 1 <= limit <= 100):
        return {'success': False, 'error': 'query 또는 id와 page>=1, limit 1~100이 필요합니다.', 'items': []}
    params = {'type': 'json', 'pageNo': page, 'numOfRows': limit}
    if query:
        params['item_name'] = query
    if item_id:
        params['item_seq'] = item_id
    raw = api_call('data_go_kr', ENDPOINT, params=params)
    failure = {'success': False, 'error_code': 'SOURCE_UNAVAILABLE', 'items': [],
               'source_complete': False, 'source_url': SOURCE,
               'error': '허가정보 원천을 확인하지 못했습니다. DATA_GO_KR_API_KEY 설정과 해당 API 활용승인을 확인하세요. 검색 결과 없음이 아닙니다.'}
    if not isinstance(raw, dict) or raw.get('error') or raw.get('success') is False:
        return failure
    response = raw.get('response', raw)
    if not isinstance(response, dict):
        return failure
    header, body = response.get('header', {}), response.get('body', {})
    if not isinstance(header, dict) or str(header.get('resultCode')) not in ('00', '0', '0000') or not isinstance(body, dict):
        return failure
    try:
        total = int(body['totalCount'])
        if total < 0:
            return failure
    except (KeyError, TypeError, ValueError):
        return failure
    rows = body.get('items')
    if isinstance(rows, dict):
        rows = rows.get('item', rows)
        rows = rows if isinstance(rows, list) else [rows]
    if rows in (None, '') and total == 0:
        rows = []
    if not isinstance(rows, list) or any(not isinstance(r, dict) or not r.get('ITEM_SEQ') or not r.get('ITEM_NAME') for r in rows):
        return failure
    items = []
    for row in rows:
        key = str(row['ITEM_SEQ'])
        items.append({'id': key, 'title': row['ITEM_NAME'], 'manufacturer': row.get('ENTP_NAME'),
                      'classification': row.get('ETC_OTC_CODE') or row.get('SPCLTY_PBLC'),
                      'ingredients_text': row.get('MAIN_ITEM_INGR'),
                      'permit_date': row.get('ITEM_PERMIT_DATE'),
                      'cancel_date': row.get('CANCEL_DATE'), 'cancel_status': row.get('CANCEL_NAME'),
                      'url': 'https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq=' + key,
                      'raw': row})
    more = page * limit < total
    return {'success': True, 'items': items, 'count': len(items), 'total': total,
            'source_complete': True, 'source_url': SOURCE, 'page': page, 'limit': limit,
            'has_more': more, 'next_page': page + 1 if more else None,
            'coverage': '식약처 의약품 제품 허가정보(전문·일반). 검색 결과는 후보이며 동일 제품·함량은 id와 원문으로 확인.',
            'note': '조회 범위의 결과이며 약의 존재 전체·현재 유통·처방 적합성을 판정하지 않습니다.'}


if __name__ == '__main__':
    print(json.dumps(lookup(json.load(sys.stdin)), ensure_ascii=False))
