"""
국토부 실거래가(RTMS) 공용 수집 — 페이징 · 잘림 신고 · 월 병렬

apt/house/villa × trade/rent 여섯 도구가 같은 관용구를 공유한다.
옛 코드는 pageNo 없이 numOfRows 한 장(기본 30)만 받아 초과분이 *조용히* 사라졌다
(2026-09-06 감사: 같은 패키지 tool_commercial_district 는 이미 pageNo·totalCount·truncated 를
알고 있었는데 실거래 6개 파일만 안 따랐다). 이 모듈이 그 관용구의 단일 자리다.

- cap=None → 그 달 전부(HARD_CAP 까지). cap=N → N 건에서 자르고 truncated 로 신고.
- 401/403 은 올린다(상위가 permission_error 로 안내). 그 외 오류는 부분 결과 + truncated.
"""
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

PAGE_SIZE = 1000          # 한 장 크게 받고 totalCount 까지 돈다
HARD_CAP_PER_MONTH = 5000 # 폭주 방어 — 넘으면 truncated 로 신고
MAX_PAGES = 20
MAX_WORKERS = 4           # 공공데이터포털 동시 호출 — 과하지 않게
TIMEOUT = 30
RETRIES = 2              # 공공데이터포털이 간헐적으로 30초 매달린다(2026-09-06 실측) — 한 번 더


def get_months_range(start_month: str, end_month: str) -> list:
    """시작월부터 종료월까지의 YYYYMM 목록"""
    months = []
    current = datetime.strptime(start_month, "%Y%m")
    end = datetime.strptime(end_month, "%Y%m")
    while current <= end:
        months.append(current.strftime("%Y%m"))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def get_text(item, tag) -> str:
    elem = item.find(tag)
    return elem.text.strip() if elem is not None and elem.text else ""


def _get(url: str) -> str:
    """GET 1회 + 타임아웃 재시도. 401/403 은 즉시 올린다."""
    last = None
    for _ in range(RETRIES):
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=TIMEOUT) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise
            last = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
    raise last


def fetch_month_paged(base_url: str, service_key: str, region_code: str, year_month: str,
                      cap, parse_item) -> dict:
    """한 달을 totalCount 까지 페이징. 반환 {"rows", "total", "truncated", "error"}.

    error 가 있으면 그 달은 불완전(타임아웃·파싱 실패) — 0건과 구분하려고 truncated 도 True."""
    try:
        limit = min(int(cap), HARD_CAP_PER_MONTH) if cap else HARD_CAP_PER_MONTH
    except (TypeError, ValueError):
        limit = HARD_CAP_PER_MONTH
    limit = max(1, limit)
    rows, total, page, error = [], 0, 1, None
    try:
        while True:
            params = {
                'serviceKey': service_key,
                'LAWD_CD': region_code,
                'DEAL_YMD': year_month,
                'pageNo': str(page),
                'numOfRows': str(min(PAGE_SIZE, limit - len(rows))),
            }
            root = ET.fromstring(_get(base_url + '?' + urllib.parse.urlencode(params)))
            result_code = root.find('.//resultCode')
            if result_code is None or result_code.text != '000':
                msg = get_text(root, './/resultMsg')
                if page == 1 and not (result_code is not None and 'NODATA' in (msg or '').upper()):
                    error = f"resultCode={getattr(result_code, 'text', None)} {msg}".strip()
                break
            tc = root.find('.//totalCount')
            if tc is not None and tc.text and tc.text.strip().isdigit():
                total = int(tc.text.strip())
            items = root.findall('.//item')
            for item in items:
                rows.append(parse_item(item, year_month))
            if (not items) or len(rows) >= limit or (total and len(rows) >= total) or page >= MAX_PAGES:
                break
            page += 1
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise  # 인증/미승인 — 상위에서 친절히 안내
        error = f"HTTP {e.code}"
    except Exception as e:  # 네트워크·파싱 오류 = 부분 결과 + error(0건과 구분)
        error = f"{type(e).__name__}: {e}"[:200]
    total = max(total, len(rows))
    return {"rows": rows, "total": total, "truncated": (len(rows) < total) or bool(error), "error": error}


def fetch_range(base_url: str, service_key: str, region_code: str, months: list,
                cap, parse_item):
    """여러 달 병렬 수집. 반환 (rows, months_with_data, total, truncated, errors). 월 순서 보존.
    errors = {YYYYMM: 사유} — 비어 있지 않으면 그 달들은 불완전(truncated 도 True)."""
    def one(m):
        return fetch_month_paged(base_url, service_key, region_code, m, cap, parse_item)
    workers = max(1, min(MAX_WORKERS, len(months)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(one, months))  # 예외(401/403)는 여기서 다시 올라온다
    rows, months_with_data, total, truncated, errors = [], [], 0, False, {}
    for m, r in zip(months, results):
        if r["rows"]:
            rows.extend(r["rows"])
            months_with_data.append(m)
        total += r["total"]
        truncated = truncated or r["truncated"]
        if r.get("error"):
            errors[m] = r["error"]
    return rows, months_with_data, total, truncated, errors
