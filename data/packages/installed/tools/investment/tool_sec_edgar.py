"""
SEC EDGAR 도구
미국 증권거래위원회(SEC) 전자공시시스템에서 기업 공시를 조회합니다.

API 문서: https://www.sec.gov/edgar/sec-api-documentation
인증 불필요 (무료)
"""
import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta
from pathlib import Path

# SEC API 기본 설정
SEC_BASE_URL = "https://data.sec.gov"
SEC_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
USER_AGENT = "IndieBizOS/1.0 (contact@example.com)"  # SEC 요구사항

# CIK 캐시
CIK_CACHE_PATH = Path(__file__).parent / "cik_cache.json"


def _load_cik_cache():
    """CIK 캐시 로드"""
    if CIK_CACHE_PATH.exists():
        try:
            with open(CIK_CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cik_cache(cache: dict):
    """CIK 캐시 저장"""
    try:
        with open(CIK_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _get_cik(symbol: str):
    """티커 심볼로 CIK 조회"""
    symbol = symbol.upper()

    # 캐시 확인
    cache = _load_cik_cache()
    if symbol in cache:
        return cache[symbol]

    try:
        # SEC 회사 티커 목록에서 조회
        url = f"{SEC_BASE_URL}/files/company_tickers.json"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)

        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))

        for item in data.values():
            if item.get("ticker", "").upper() == symbol:
                cik = str(item.get("cik_str", "")).zfill(10)
                # 캐시 저장
                cache[symbol] = cik
                _save_cik_cache(cache)
                return cik

        return None

    except Exception:
        return None


def _api_request(url: str):
    """SEC API 요청"""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception:
        return None


def get_filings(symbol: str, filing_type: str = None, count: int = 10):
    """
    SEC 공시 목록 조회

    Args:
        symbol: 티커 심볼 (예: AAPL, MSFT)
        filing_type: 공시 유형 (10-K, 10-Q, 8-K 등). None이면 전체
        count: 조회할 공시 수

    Returns:
        공시 목록
    """
    symbol = symbol.upper()

    # CIK 조회
    cik = _get_cik(symbol)
    if not cik:
        return {
            "success": False,
            "error": f"'{symbol}'의 CIK를 찾을 수 없습니다. 올바른 미국 주식 티커인지 확인하세요."
        }

    # 회사 제출 내역 조회
    url = f"{SEC_BASE_URL}/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={filing_type or ''}&dateb=&owner=include&count={count}&output=atom"

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)

        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8')

        # Atom XML 파싱 (간단 파싱)
        filings = []
        import re

        # entry 추출
        entries = re.findall(r'<entry>(.*?)</entry>', content, re.DOTALL)

        for entry in entries[:count]:
            title = re.search(r'<title[^>]*>(.*?)</title>', entry)
            updated = re.search(r'<updated>(.*?)</updated>', entry)
            link = re.search(r'<link[^>]*href="([^"]*)"', entry)
            summary = re.search(r'<summary[^>]*>(.*?)</summary>', entry, re.DOTALL)

            filing = {
                "title": title.group(1) if title else "",
                "date": updated.group(1)[:10] if updated else "",
                "url": link.group(1) if link else "",
                "summary": summary.group(1).strip()[:200] if summary else ""
            }

            # 공시 유형 추출
            if filing["title"]:
                type_match = re.match(r'(\d+-[KQ]|8-K|[A-Z0-9-]+)', filing["title"])
                if type_match:
                    filing["type"] = type_match.group(1)

            filings.append(filing)

        if not filings:
            # JSON API로 대체 시도
            return _get_filings_json(cik, symbol, filing_type, count)

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "cik": cik,
                "filings": filings
            },
            "summary": f"{symbol}의 SEC 공시 {len(filings)}건 조회 완료"
        }

    except Exception as e:
        # JSON API로 대체 시도
        return _get_filings_json(cik, symbol, filing_type, count)


def _get_filings_json(cik: str, symbol: str, filing_type: str = None, count: int = 10):
    """JSON API로 공시 조회 (대체)"""
    try:
        url = f"{SEC_BASE_URL}/submissions/CIK{cik}.json"
        data = _api_request(url)

        if not data:
            return {
                "success": False,
                "error": f"SEC API 응답 오류"
            }

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        descriptions = recent.get("primaryDocDescription", [])

        filings = []
        for i in range(min(len(forms), count * 2)):  # 더 많이 조회 후 필터링
            form = forms[i] if i < len(forms) else ""

            # 공시 유형 필터링
            if filing_type and filing_type.upper() not in form.upper():
                continue

            accession = accessions[i].replace("-", "") if i < len(accessions) else ""

            filing = {
                "type": form,
                "date": dates[i] if i < len(dates) else "",
                "description": descriptions[i] if i < len(descriptions) else "",
                "accession": accessions[i] if i < len(accessions) else "",
                "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form}&dateb=&owner=include&count=1"
            }

            if accession:
                filing["document_url"] = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}"

            filings.append(filing)

            if len(filings) >= count:
                break

        company_name = data.get("name", symbol)

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "company_name": company_name,
                "cik": cik,
                "filings": filings
            },
            "summary": f"{company_name}({symbol})의 SEC 공시 {len(filings)}건 조회"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"SEC 공시 조회 오류: {str(e)}"
        }


def get_company_info(symbol: str):
    """
    SEC에 등록된 회사 정보 조회

    Args:
        symbol: 티커 심볼

    Returns:
        회사 기본 정보
    """
    symbol = symbol.upper()

    cik = _get_cik(symbol)
    if not cik:
        return {
            "success": False,
            "error": f"'{symbol}'의 CIK를 찾을 수 없습니다."
        }

    try:
        url = f"{SEC_BASE_URL}/submissions/CIK{cik}.json"
        data = _api_request(url)

        if not data:
            return {
                "success": False,
                "error": "SEC API 응답 오류"
            }

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "cik": cik,
                "company_name": data.get("name"),
                "sic": data.get("sic"),
                "sic_description": data.get("sicDescription"),
                "state": data.get("stateOfIncorporation"),
                "fiscal_year_end": data.get("fiscalYearEnd"),
                "exchanges": data.get("exchanges", []),
                "phone": data.get("phone"),
                "address": {
                    "street": data.get("addresses", {}).get("business", {}).get("street1"),
                    "city": data.get("addresses", {}).get("business", {}).get("city"),
                    "state": data.get("addresses", {}).get("business", {}).get("stateOrCountry"),
                    "zip": data.get("addresses", {}).get("business", {}).get("zipCode")
                }
            },
            "summary": f"{data.get('name')} ({symbol}) - {data.get('sicDescription', 'N/A')}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"회사 정보 조회 오류: {str(e)}"
        }


def get_10k_sections(symbol: str, year: int = None):
    """
    10-K 보고서의 주요 섹션 정보 안내

    Args:
        symbol: 티커 심볼
        year: 연도 (기본: 최근)

    Returns:
        10-K 섹션 안내
    """
    # 최신 10-K 조회
    result = get_filings(symbol, "10-K", count=3)

    if not result.get("success"):
        return result

    filings = result["data"].get("filings", [])
    if not filings:
        return {
            "success": False,
            "error": f"{symbol}의 10-K 보고서를 찾을 수 없습니다."
        }

    latest = filings[0]

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "latest_10k": latest,
            "sections_guide": {
                "Item 1": "Business - 회사의 사업 개요, 비즈니스 모델, 경쟁 현황",
                "Item 1A": "Risk Factors - 사업 및 투자 위험 요소",
                "Item 1B": "Unresolved Staff Comments",
                "Item 2": "Properties - 자산 및 시설",
                "Item 3": "Legal Proceedings - 법적 분쟁",
                "Item 4": "Mine Safety Disclosures",
                "Item 5": "Market for Registrant's Common Equity - 주식 시장 정보",
                "Item 6": "Selected Financial Data - 주요 재무 데이터 (5년)",
                "Item 7": "MD&A - 경영진의 재무상태 및 영업실적 분석",
                "Item 7A": "Quantitative and Qualitative Disclosures About Market Risk",
                "Item 8": "Financial Statements - 재무제표",
                "Item 9": "Changes in and Disagreements With Accountants",
                "Item 10": "Directors, Executive Officers - 이사 및 임원 정보",
                "Item 11": "Executive Compensation - 임원 보상",
                "Item 12": "Security Ownership - 주식 소유 현황",
                "Item 13": "Certain Relationships and Related Transactions",
                "Item 14": "Principal Accounting Fees and Services",
                "Item 15": "Exhibits, Financial Statement Schedules"
            }
        },
        "summary": f"{symbol}의 최신 10-K ({latest.get('date', 'N/A')}) - SEC 웹사이트에서 전문 확인 가능"
    }
