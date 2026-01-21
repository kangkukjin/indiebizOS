"""
DART OpenAPI 도구
금융감독원 전자공시시스템 API를 통해 한국 기업 정보를 조회합니다.

API 문서: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001
필요 환경변수: DART_API_KEY
"""
import os
import urllib.request
import urllib.parse
import json
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

DART_API_KEY = os.environ.get("DART_API_KEY", "")
BASE_URL = "https://opendart.fss.or.kr/api"

# 기업 코드 캐시 파일 경로
CORP_CODE_CACHE_PATH = Path(__file__).parent / "corp_code_cache.json"

# 대량 데이터 저장 경로
DATA_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "outputs" / "investment"
DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _save_large_data(data: dict, prefix: str, identifier: str) -> str:
    """대량 데이터를 파일로 저장하고 경로 반환"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{identifier}_{timestamp}.json"
    filepath = DATA_OUTPUT_DIR / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return str(filepath)


def _check_api_key():
    """API 키 확인"""
    if not DART_API_KEY:
        return {
            "success": False,
            "error": "DART_API_KEY 환경변수가 설정되지 않았습니다. https://opendart.fss.or.kr 에서 API 키를 발급받으세요."
        }
    return None


def _load_corp_codes():
    """기업 코드 목록 로드 (캐시 또는 API)"""
    # 캐시 확인
    if CORP_CODE_CACHE_PATH.exists():
        try:
            with open(CORP_CODE_CACHE_PATH, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                # 캐시가 7일 이내면 사용
                cache_time = datetime.fromisoformat(cache_data.get("cached_at", "2000-01-01"))
                if datetime.now() - cache_time < timedelta(days=7):
                    return cache_data.get("corps", {})
        except Exception:
            pass

    # API에서 다운로드
    error = _check_api_key()
    if error:
        return {}

    try:
        url = f"{BASE_URL}/corpCode.xml?crtfc_key={DART_API_KEY}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as response:
            zip_data = response.read()

        # ZIP 파일 해제
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            with zf.open("CORPCODE.xml") as xml_file:
                tree = ET.parse(xml_file)
                root = tree.getroot()

        # 기업 코드 파싱
        corps = {}
        for item in root.findall("list"):
            corp_code = item.findtext("corp_code", "")
            corp_name = item.findtext("corp_name", "")
            stock_code = item.findtext("stock_code", "")
            if corp_name:
                corps[corp_name] = {
                    "corp_code": corp_code,
                    "stock_code": stock_code.strip() if stock_code else None
                }

        # 캐시 저장
        cache_data = {
            "cached_at": datetime.now().isoformat(),
            "corps": corps
        }
        with open(CORP_CODE_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        return corps

    except Exception as e:
        return {}


def _find_corp_code(corp_name: str):
    """회사명으로 기업코드 찾기"""
    corps = _load_corp_codes()

    # 정확한 매칭
    if corp_name in corps:
        return corps[corp_name]["corp_code"]

    # 부분 매칭
    for name, info in corps.items():
        if corp_name in name or name in corp_name:
            return info["corp_code"]

    return None


def _api_request(endpoint: str, params: dict):
    """DART API 요청"""
    error = _check_api_key()
    if error:
        return error

    params["crtfc_key"] = DART_API_KEY
    url = f"{BASE_URL}/{endpoint}?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))

        # 상태 코드 확인
        status = data.get("status", "")
        if status == "000":
            return {"success": True, "data": data}
        elif status == "010":
            return {"success": False, "error": "등록되지 않은 API 키입니다."}
        elif status == "011":
            return {"success": False, "error": "API 사용 제한을 초과했습니다."}
        elif status == "013":
            return {"success": False, "error": "조회된 데이터가 없습니다."}
        elif status == "020":
            return {"success": False, "error": "필수 파라미터가 누락되었습니다."}
        else:
            return {"success": False, "error": f"API 오류 (status: {status}): {data.get('message', '')}"}

    except urllib.error.URLError as e:
        return {"success": False, "error": f"네트워크 오류: {str(e)}"}
    except json.JSONDecodeError:
        return {"success": False, "error": "API 응답 파싱 오류"}
    except Exception as e:
        return {"success": False, "error": f"요청 오류: {str(e)}"}


def get_company_info(corp_code: str = None, corp_name: str = None):
    """
    기업 개황 조회

    Args:
        corp_code: DART 고유번호 (8자리)
        corp_name: 회사명

    Returns:
        기업 기본정보 (대표자, 업종, 주소, 설립일 등)
    """
    # 기업코드 확인
    if not corp_code and corp_name:
        corp_code = _find_corp_code(corp_name)
        if not corp_code:
            return {
                "success": False,
                "error": f"'{corp_name}'에 해당하는 기업을 찾을 수 없습니다."
            }
    elif not corp_code:
        return {
            "success": False,
            "error": "corp_code 또는 corp_name을 입력해주세요."
        }

    result = _api_request("company.json", {"corp_code": corp_code})

    if not result.get("success"):
        return result

    data = result["data"]
    return {
        "success": True,
        "data": {
            "corp_code": data.get("corp_code"),
            "corp_name": data.get("corp_name"),
            "corp_name_eng": data.get("corp_name_eng"),
            "stock_code": data.get("stock_code"),
            "ceo_name": data.get("ceo_nm"),
            "corp_cls": data.get("corp_cls"),  # Y:유가, K:코스닥, N:코넥스, E:기타
            "jurir_no": data.get("jurir_no"),  # 법인등록번호
            "bizr_no": data.get("bizr_no"),  # 사업자등록번호
            "address": data.get("adres"),
            "homepage": data.get("hm_url"),
            "ir_url": data.get("ir_url"),
            "phone": data.get("phn_no"),
            "fax": data.get("fax_no"),
            "industry": data.get("induty_code"),
            "establishment_date": data.get("est_dt"),
            "accounting_month": data.get("acc_mt")
        },
        "summary": f"{data.get('corp_name')} ({data.get('stock_code', 'N/A')}) - 대표: {data.get('ceo_nm')}, 업종: {data.get('induty_code')}"
    }


def get_financial_statements(corp_code: str = None, corp_name: str = None,
                              year: str = None, report_type: str = "11011"):
    """
    재무제표 조회

    Args:
        corp_code: DART 고유번호
        corp_name: 회사명
        year: 사업연도 (YYYY)
        report_type: 보고서 유형 (11011:사업보고서, 11012:반기, 11013:1분기, 11014:3분기)

    Returns:
        재무제표 주요 계정과목
    """
    # 기업코드 확인
    if not corp_code and corp_name:
        corp_code = _find_corp_code(corp_name)
        if not corp_code:
            return {
                "success": False,
                "error": f"'{corp_name}'에 해당하는 기업을 찾을 수 없습니다."
            }
    elif not corp_code:
        return {
            "success": False,
            "error": "corp_code 또는 corp_name을 입력해주세요."
        }

    if not year:
        year = str(datetime.now().year - 1)

    params = {
        "corp_code": corp_code,
        "bsns_year": year,
        "reprt_code": report_type,
        "fs_div": "CFS"  # CFS:연결재무제표, OFS:개별재무제표
    }

    result = _api_request("fnlttSinglAcntAll.json", params)

    if not result.get("success"):
        # 연결재무제표 없으면 개별재무제표 조회
        params["fs_div"] = "OFS"
        result = _api_request("fnlttSinglAcntAll.json", params)

    if not result.get("success"):
        return result

    data = result["data"]
    items = data.get("list", [])

    # 주요 계정과목 분류
    balance_sheet = []  # 재무상태표
    income_statement = []  # 손익계산서
    cash_flow = []  # 현금흐름표

    for item in items:
        sj_div = item.get("sj_div")
        account = {
            "account_name": item.get("account_nm"),
            "current_amount": item.get("thstrm_amount"),
            "previous_amount": item.get("frmtrm_amount"),
            "before_previous_amount": item.get("bfefrmtrm_amount")
        }

        if sj_div == "BS":
            balance_sheet.append(account)
        elif sj_div == "IS":
            income_statement.append(account)
        elif sj_div == "CF":
            cash_flow.append(account)

    total_items = len(balance_sheet) + len(income_statement) + len(cash_flow)

    # 대량 데이터는 파일로 저장 (30개 초과시)
    if total_items > 30:
        full_data = {
            "corp_code": corp_code,
            "year": year,
            "report_type": report_type,
            "fs_div": params["fs_div"],
            "balance_sheet": balance_sheet,
            "income_statement": income_statement,
            "cash_flow": cash_flow
        }
        file_path = _save_large_data(full_data, "financial_statements", corp_code)

        # 주요 항목만 요약 (각 5개씩)
        return {
            "success": True,
            "data": {
                "corp_code": corp_code,
                "year": year,
                "report_type": report_type,
                "fs_div": params["fs_div"],
                "file_path": file_path,
                "total_items": total_items,
                "sample": {
                    "balance_sheet": balance_sheet[:5],
                    "income_statement": income_statement[:5],
                    "cash_flow": cash_flow[:5]
                }
            },
            "summary": f"{year}년 재무제표 - 재무상태표 {len(balance_sheet)}개, 손익계산서 {len(income_statement)}개, 현금흐름표 {len(cash_flow)}개 항목. 전체 데이터: {file_path}"
        }
    else:
        return {
            "success": True,
            "data": {
                "corp_code": corp_code,
                "year": year,
                "report_type": report_type,
                "fs_div": params["fs_div"],
                "balance_sheet": balance_sheet,
                "income_statement": income_statement,
                "cash_flow": cash_flow
            },
            "summary": f"{year}년 재무제표 조회 완료 (재무상태표 {len(balance_sheet)}개, 손익계산서 {len(income_statement)}개 항목)"
        }


def get_disclosures(corp_code: str = None, corp_name: str = None,
                    start_date: str = None, end_date: str = None,
                    pblntf_ty: str = None, count: int = 20):
    """
    공시 목록 조회

    Args:
        corp_code: DART 고유번호
        corp_name: 회사명
        start_date: 검색 시작일 (YYYYMMDD)
        end_date: 검색 종료일 (YYYYMMDD)
        pblntf_ty: 공시유형 (A:정기공시, B:주요사항보고, C:발행공시, D:지분공시, E:기타공시 등)
        count: 조회 개수

    Returns:
        공시 목록
    """
    # 기업코드 확인 (선택사항)
    if not corp_code and corp_name:
        corp_code = _find_corp_code(corp_name)
        if not corp_code:
            return {
                "success": False,
                "error": f"'{corp_name}'에 해당하는 기업을 찾을 수 없습니다."
            }

    # 날짜 기본값
    if not end_date:
        end_date = datetime.now().strftime("%Y%m%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

    params = {
        "bgn_de": start_date,
        "end_de": end_date,
        "page_count": str(count)
    }

    if corp_code:
        params["corp_code"] = corp_code

    if pblntf_ty:
        params["pblntf_ty"] = pblntf_ty

    result = _api_request("list.json", params)

    if not result.get("success"):
        return result

    data = result["data"]
    items = data.get("list", [])

    disclosures = []
    for item in items:
        disclosures.append({
            "rcept_no": item.get("rcept_no"),  # 접수번호
            "corp_name": item.get("corp_name"),
            "corp_code": item.get("corp_code"),
            "stock_code": item.get("stock_code"),
            "report_name": item.get("report_nm"),
            "rcept_dt": item.get("rcept_dt"),  # 접수일자
            "flr_nm": item.get("flr_nm"),  # 공시 제출인
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no')}"
        })

    return {
        "success": True,
        "data": {
            "total_count": data.get("total_count", len(disclosures)),
            "disclosures": disclosures
        },
        "summary": f"총 {data.get('total_count', len(disclosures))}건의 공시 중 {len(disclosures)}건 조회"
    }
