import urllib.request
import urllib.parse
import json
import os
import sys

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.auth_manager import get_api_key, check_api_key

SERVICE_KEY = get_api_key('DATA_GO_KR_API_KEY') or ''
BASE_URL = 'https://apis.data.go.kr/B553077/api/open/sdsc2'

def search_commercial_district(lat: float = None, lng: float = None, radius: int = 500, region_code: str = None, indsLclsCd: str = None, max_count: int = 10000):
    """
    소상공인시장진흥공단 상가(상권)정보 조회 — 전 페이지 수집

    storeListInRadius/storeListInDong은 페이지네이션(기본 numOfRows=10)이므로,
    pageNo를 돌며 totalCount(또는 max_count)까지 모두 모은다.

    Args:
        lat: 위도 (Radius 검색 시 필수)
        lng: 경도 (Radius 검색 시 필수)
        radius: 반경 (미터 단위, 기본 500m)
        region_code: 행정동 코드 10자리 (지역 검색 시 필수)
        indsLclsCd: 상권업종대분류코드 (I: 음식, Q: 숙박 등)
        max_count: 최대 수집 건수 안전캡 (기본 5000)

    Returns:
        dict: 상가 목록 및 통계 정보 (truncated=True면 max_count로 잘림)
    """
    key_ok, key_error = check_api_key("data_go_kr")
    if not key_ok:
        return {"success": False, "error": key_error}

    try:
        if lat and lng:
            endpoint = f"{BASE_URL}/storeListInRadius"
            base = {'serviceKey': SERVICE_KEY, 'radius': str(radius), 'cx': str(lng), 'cy': str(lat), 'type': 'json'}
        elif region_code:
            endpoint = f"{BASE_URL}/storeListInDong"
            base = {'serviceKey': SERVICE_KEY, 'divId': 'adongCd', 'key': region_code, 'type': 'json'}
        else:
            return {"success": False, "error": "위도/경도(lat, lng) 또는 행정동 코드(region_code)가 필요합니다."}

        if indsLclsCd:
            base['indsLclsCd'] = indsLclsCd

        PAGE_SIZE = 1000
        all_items = []
        total_count = 0
        page = 1
        while True:
            params = {**base, 'pageNo': str(page), 'numOfRows': str(PAGE_SIZE)}
            url = endpoint + '?' + urllib.parse.urlencode(params)
            with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))

            header = result.get('header', {})
            if header.get('resultCode') != '00':
                if page == 1:
                    return {"success": False, "error": header.get('resultMsg', 'API 호출 오류'), "code": header.get('resultCode')}
                break  # 이후 페이지 오류는 부분 결과로 종료

            body = result.get('body', {})
            items = body.get('items', []) or []
            if isinstance(items, dict):  # 단일 항목이 dict로 올 때 방어
                items = [items]
            total_count = body.get('totalCount', total_count) or len(all_items) + len(items)
            all_items.extend(items)

            if (not items) or len(all_items) >= total_count or len(all_items) >= max_count or page >= 30:
                break
            page += 1

        # 데이터 정제 (영문 키 사용 - show_location_map과 호환)
        stores = []
        for item in all_items[:max_count]:
            stores.append({
                "name": item.get('bizesNm'),
                "branch": item.get('brchNm'),
                "category": item.get('indsMclsNm'),
                "subcategory": item.get('indsSclsNm'),
                "address": item.get('rdnmAdr') or item.get('lnoAdr'),
                "lat": float(item.get('lat')) if item.get('lat') else None,
                "lng": float(item.get('lon')) if item.get('lon') else None,
            })

        return {
            "success": True,
            "total_count": total_count or len(stores),
            "count": len(stores),
            "truncated": len(stores) < (total_count or 0),
            "data": stores,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
