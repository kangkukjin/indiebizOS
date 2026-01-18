import urllib.request
import urllib.parse
import json
import os

SERVICE_KEY = os.environ.get('DATA_GO_KR_API_KEY', '')
BASE_URL = 'https://apis.data.go.kr/B553077/api/open/sdsc2'

def search_commercial_district(lat: float = None, lng: float = None, radius: int = 500, region_code: str = None, indsLclsCd: str = None):
    """
    소상공인시장진흥공단 상가(상권)정보 조회
    
    Args:
        lat: 위도 (Radius 검색 시 필수)
        lng: 경도 (Radius 검색 시 필수)
        radius: 반경 (미터 단위, 기본 500m)
        region_code: 행정동 코드 10자리 (지역 검색 시 필수)
        indsLclsCd: 상권업종대분류코드 (I: 음식, Q: 숙박 등)
        
    Returns:
        dict: 상가 목록 및 통계 정보
    """
    try:
        if lat and lng:
            # 반경 기반 검색
            endpoint = f"{BASE_URL}/getStoreListInRadius"
            params = {
                'serviceKey': SERVICE_KEY,
                'radius': str(radius),
                'cx': str(lng),
                'cy': str(lat),
                'type': 'json'
            }
        elif region_code:
            # 지역(행정동) 기반 검색
            endpoint = f"{BASE_URL}/getStoreListInDong"
            params = {
                'serviceKey': SERVICE_KEY,
                'divId': 'adongCd',
                'key': region_code,
                'type': 'json'
            }
        else:
            return {
                "success": False,
                "error": "위도/경도(lat, lng) 또는 행정동 코드(region_code)가 필요합니다."
            }

        if indsLclsCd:
            params['indsLclsCd'] = indsLclsCd

        # API 호출
        url = endpoint + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read().decode('utf-8')
            
        result = json.loads(data)
        
        header = result.get('header', {})
        if header.get('resultCode') != '00':
            return {
                "success": False,
                "error": header.get('resultMsg', 'API 호출 오류'),
                "code": header.get('resultCode')
            }
            
        body = result.get('body', {})
        items = body.get('items', [])
        
        # 데이터 정제 (영문 키 사용 - show_location_map과 호환)
        stores = []
        for item in items:
            store = {
                "name": item.get('bizesNm'),  # 상호명
                "branch": item.get('brchNm'),  # 지점명
                "category": item.get('indsMclsNm'),  # 업종명
                "subcategory": item.get('indsSclsNm'),  # 상세업종
                "address": item.get('rdnmAdr') or item.get('lnoAdr'),  # 주소
                "lat": float(item.get('lat')) if item.get('lat') else None,  # 위도
                "lng": float(item.get('lon')) if item.get('lon') else None   # 경도 (lon -> lng로 통일)
            }
            stores.append(store)
            
        return {
            "success": True,
            "total_count": body.get('totalCount', len(stores)),
            "count": len(stores),
            "data": stores
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
