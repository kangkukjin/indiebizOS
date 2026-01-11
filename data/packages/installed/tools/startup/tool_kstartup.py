"""
K-Startup 창업지원 사업공고 조회 모듈
창업진흥원 공공데이터 API 사용 (2024년 신규 API)
"""
import urllib.request
import urllib.parse
import json
import os

SERVICE_KEY = os.environ.get('DATA_GO_KR_API_KEY', '5d93a49043da935280488408c84d900a7c673384b77bb9668ea68f32227ee002')
BASE_URL = 'https://apis.data.go.kr/B552735/kisedKstartupService01'

# 신규 API 엔드포인트 (2024~)
ENDPOINTS = {
    'announcement': '/getAnnouncementInformation01',  # 지원사업 공고
    'business': '/getBusinessInformation01',          # 통합공고 지원사업
    'content': '/getContentInformation01',            # 콘텐츠 정보
    'statistics': '/getStatisticalInformation01',     # 통계보고서
}

def get_tool_definition():
    return {
        "name": "search_kstartup",
        "description": "K-Startup 창업지원 사업공고를 검색합니다. 창업진흥원에서 제공하는 창업지원 사업, 공고 정보를 조회할 수 있습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "검색 키워드 (예: 예비창업, 기술창업, 소상공인)"
                },
                "count": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                    "description": "조회할 건수"
                }
            },
            "required": []
        }
    }

def search_kstartup(keyword: str = "", count: int = 10):
    """
    K-Startup 창업지원 사업공고 검색 (신규 API)

    Args:
        keyword: 검색 키워드
        count: 조회 건수

    Returns:
        dict: 조회 결과
    """
    try:
        # 신규 API 엔드포인트 사용
        endpoint = f"{BASE_URL}{ENDPOINTS['announcement']}"

        params = {
            'serviceKey': SERVICE_KEY,
            'page': '1',
            'perPage': str(count),
            'returnType': 'json'
        }

        url = endpoint + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        req.add_header('Accept', 'application/json')

        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read().decode('utf-8')

        result = json.loads(data)

        # 신규 API 응답 구조
        items = result.get('data', [])
        total_count = result.get('totalCount', len(items))

        # 키워드 필터링 (API에서 직접 지원하지 않으면 클라이언트에서 필터링)
        if keyword and items:
            items = [item for item in items if keyword in str(item)]

        announcements = []
        for item in items:
            announcement = {
                "사업명": item.get('pblancNm', item.get('pblanc_nm', '')),
                "사업유형": item.get('bizPbancCtgryNm', item.get('biz_pbanc_ctgry_nm', '')),
                "주관기관": item.get('jrsdInsttNm', item.get('jrsd_instt_nm', '')),
                "접수시작일": item.get('reqstBeginDe', item.get('reqst_begin_de', '')),
                "접수마감일": item.get('reqstEndDe', item.get('reqst_end_de', '')),
                "공고상태": item.get('pblancSttusNm', item.get('pbanc_sttus_nm', '')),
                "상세URL": item.get('detailPageUrl', item.get('detail_page_url', '')),
            }
            announcements.append(announcement)

        return {
            "success": True,
            "source": "K-Startup (창업진흥원)",
            "keyword": keyword if keyword else "전체",
            "total_count": total_count,
            "count": len(announcements),
            "data": announcements
        }

    except urllib.error.HTTPError as e:
        return {
            "success": False,
            "error": f"HTTP Error {e.code}: {e.reason}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
