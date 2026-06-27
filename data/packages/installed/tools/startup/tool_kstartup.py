"""
K-Startup 창업지원 사업공고 조회 모듈
창업진흥원 공공데이터 API 사용 (2024년 신규 API)
"""
import os
import sys
import json

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.auth_manager import check_api_key

# 신규 API 엔드포인트 (2024~)
ENDPOINTS = {
    'announcement': '/B552735/kisedKstartupService01/getAnnouncementInformation01',  # 지원사업 공고
    'business': '/B552735/kisedKstartupService01/getBusinessInformation01',          # 통합공고 지원사업
    'content': '/B552735/kisedKstartupService01/getContentInformation01',            # 콘텐츠 정보
    'statistics': '/B552735/kisedKstartupService01/getStatisticalInformation01',     # 통계보고서
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

def _map_announcement(item: dict) -> dict:
    """API 원본(snake_case) → 표준 공고 dict. 과거 camelCase 매핑은
    전부 빈값을 만들어 제목·기관이 사라지던 침묵 함정이었음.
    제목에 &apos; 등 HTML 엔티티가 섞여 와 unescape."""
    import html
    return {
        "사업명": html.unescape(item.get('biz_pbanc_nm', '') or ''),
        "사업유형": item.get('supt_biz_clsfc', ''),
        "주관기관": item.get('pbanc_ntrp_nm', '') or item.get('sprv_inst', ''),
        "접수시작일": item.get('pbanc_rcpt_bgng_dt', ''),
        "접수마감일": item.get('pbanc_rcpt_end_dt', ''),
        "공고상태": '진행중' if item.get('rcrt_prgs_yn') == 'Y' else '마감',
        "상세URL": item.get('detl_pg_url', ''),
    }


def _fetch_kstartup_raw(cond_keyword: str, count: int):
    """단일 cond LIKE 로 공고 원본 리스트 조회. (items, error, match_total) 반환."""
    params = {'page': '1', 'perPage': str(count), 'returnType': 'json'}
    # 서버사이드 검색: 사업명에 키워드 LIKE (data.go.kr cond 필터).
    # 과거엔 keyword를 무시하고 perPage개만 받아 사후 필터 → 최근 N개에 단어가
    # 없으면 0건이 되는 함정이 있었음. 서버에서 직접 검색.
    if cond_keyword:
        params['cond[biz_pbanc_nm::LIKE]'] = cond_keyword
    result = api_call(
        "data_go_kr", ENDPOINTS['announcement'],
        params=params, extra_headers={'Accept': 'application/json'}, timeout=30,
    )
    if isinstance(result, dict) and "error" in result:
        return None, result["error"], None
    if isinstance(result, str):
        result = json.loads(result)
    items = result.get('data', [])
    total = result.get('matchCount') if cond_keyword else result.get('totalCount')
    return items, None, total


def search_kstartup(keyword: str = "", count: int = 10):
    """K-Startup 창업지원 사업공고 검색 (신규 API).

    keyword 가 여러 단어면 OR 의미로 토큰별 LIKE 를 합집합한다 — cond LIKE 는
    구(phrase) 전체 부분일치라 "AI 인공지능 딥테크" 한 덩어리로는 0건이 나오던
    함정 때문. "AI"(영문)와 "인공지능"(한글)은 LIKE 상 서로 안 잡혀 합집합이 더 넓다.
    """
    try:
        ok, err = check_api_key("data_go_kr")
        if not ok:
            return {"success": False, "error": err}

        tokens = (keyword or "").split()
        if len(tokens) <= 1:
            items, ferr, total = _fetch_kstartup_raw(keyword, count)
            if ferr:
                return {"success": False, "error": ferr}
        else:
            # 다중 키워드 = OR 합집합 (pbanc_sn 중복 제거, 최대 4토큰).
            seen, items, total = set(), [], 0
            for tok in tokens[:4]:
                part, ferr, t = _fetch_kstartup_raw(tok, max(count, 20))
                if ferr or not part:
                    continue
                for it in part:
                    key = it.get('pbanc_sn')
                    if key is None:
                        key = it.get('biz_pbanc_nm')
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(it)
            total = len(items)
            items = items[:count]

        if total is None:
            total = len(items)
        announcements = [_map_announcement(it) for it in items]

        return {
            "success": True,
            "source": "K-Startup (창업진흥원)",
            "keyword": keyword if keyword else "전체",
            "total_count": total,
            "count": len(announcements),
            "data": announcements
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
