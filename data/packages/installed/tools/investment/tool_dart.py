"""
DART OpenAPI 도구
금융감독원 전자공시시스템 API를 통해 한국 기업 정보를 조회합니다.

API 문서: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001
필요 환경변수: DART_API_KEY
"""
import os
import sys
import urllib.request
import urllib.parse
import json
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.auth_manager import check_api_key, get_api_key
from common.response_formatter import save_large_data

DART_API_KEY = os.environ.get("DART_API_KEY", "")
BASE_URL = "https://opendart.fss.or.kr/api"

# 기업 코드 캐시 파일 경로
CORP_CODE_CACHE_PATH = Path(__file__).parent / "corp_code_cache.json"


def _check_api_key():
    """API 키 확인 (common.auth_manager 위임)"""
    ok, err = check_api_key("dart")
    if not ok:
        return {"success": False, "error": err}
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
    """회사명 → (기업코드, 해소된_회사명, 거절봉투|None).

    ★세계 명사 해소 계약 (2026-08-24 #repair A2) — 추측 금지.
      옛 코드는 `if corp_name in name or name in corp_name` 로 **처음 걸린 것**을
      골랐다. dict 순회 순서라 '삼성전자'를 물으면 '삼성공조'·'삼성전자서비스'가
      먼저 나올 수 있고, 그 회사의 재무제표가 에러 없이 돌아온다. 이름을 못 대면
      후보를 들고 거절한다 — 본: real-estate tool_region_codes.resolve_region_code.

    우선순위: 정확 일치 > 접두 일치 > 포함(유일할 때만). 포함이 복수면 거절.
    """
    corps = _load_corp_codes()
    q = str(corp_name or "").strip()
    if not q:
        return None, None, None

    if q in corps:
        return corps[q]["corp_code"], q, None

    starts = [(n, i) for n, i in corps.items() if n.startswith(q)]
    if len(starts) == 1:
        return starts[0][1]["corp_code"], starts[0][0], None
    if len(starts) > 1:
        exacts = [x for x in starts if x[0] == q]
        if len(exacts) == 1:
            return exacts[0][1]["corp_code"], exacts[0][0], None
        return None, None, _corp_ambiguous(q, [n for n, _ in starts])

    contains = [(n, i) for n, i in corps.items() if q in n or n in q]
    if len(contains) == 1:
        return contains[0][1]["corp_code"], contains[0][0], None
    if len(contains) > 1:
        return None, None, _corp_ambiguous(q, [n for n, _ in contains])

    return None, None, None


def _corp_ambiguous(asked: str, names: list):
    """포함 매칭이 여럿 — 하나를 몰래 고르지 않고 후보를 돌려준다."""
    return {
        "success": False,
        "asked": asked,
        "candidates": sorted(names)[:12],
        "error": (f"'{asked}' 와 일치하는 기업이 여럿입니다({len(names)}건). "
                  f"정확한 회사명이나 corp_code 로 다시 부르세요."),
    }


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
    _resolved = None          # corp_code 직접 지정 경로에서도 정의돼야 한다
    if not corp_code and corp_name:
        corp_code, _resolved, _refused = _find_corp_code(corp_name)
        if _refused:
            return _refused          # 후보를 들고 거절 — 몰래 하나 고르지 않는다
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
        "summary": f"{data.get('corp_name')} ({data.get('stock_code', 'N/A')}) - 대표: {data.get('ceo_nm')}, 업종: {data.get('induty_code')}",
        # ★답이 자기가 무엇에 대한 답인지 말한다(반증 가능성)
        "resolved": _resolved or data.get("corp_name"),
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
    _resolved = None          # corp_code 직접 지정 경로에서도 정의돼야 한다
    if not corp_code and corp_name:
        corp_code, _resolved, _refused = _find_corp_code(corp_name)
        if _refused:
            return _refused          # 후보를 들고 거절 — 몰래 하나 고르지 않는다
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
        file_path = save_large_data(full_data, "investment", f"financial_{corp_code}")

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
            "summary": f"{year}년 재무제표 - 재무상태표 {len(balance_sheet)}개, 손익계산서 {len(income_statement)}개, 현금흐름표 {len(cash_flow)}개 항목. 전체 데이터: {file_path}",
            "resolved": _resolved,
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
            "summary": f"{year}년 재무제표 조회 완료 (재무상태표 {len(balance_sheet)}개, 손익계산서 {len(income_statement)}개 항목)",
            "resolved": _resolved,
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
    _resolved = None          # corp_code 직접 지정 경로에서도 정의돼야 한다
    if not corp_code and corp_name:
        corp_code, _resolved, _refused = _find_corp_code(corp_name)
        if _refused:
            return _refused          # 후보를 들고 거절 — 몰래 하나 고르지 않는다
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

    # 레코드 통화(비파괴) — 공시 목록 >> [table:document/spreadsheet]
    records = [{
        "title": d.get("report_name") or "(공시)",
        "meta": " · ".join(x for x in [d.get("corp_name"), d.get("rcept_dt"), d.get("flr_nm")] if x),
        "summary": "",
        "url": d.get("url") or "",
    } for d in disclosures]
    return {
        "success": True,
        "data": {
            "total_count": data.get("total_count", len(disclosures)),
            "disclosures": disclosures
        },
        "items": records,
        "summary": f"총 {data.get('total_count', len(disclosures))}건의 공시 중 {len(disclosures)}건 조회",
        "resolved": _resolved,
    }
