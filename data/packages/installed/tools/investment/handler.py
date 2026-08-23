"""
Investment Tools Handler
한국/미국 기업의 주가·시세·재무·공시·뉴스 + 암호화폐를 조회하는 투자 분석 도구.

2026-06-03 finance 어휘 정리: 옛 16개 도구를 단일 액션 op 분기로 통합.
- [sense:stock]{op}   → stock_op   (quote=현재가/history=이력/info/search/investors/news/earnings)
- [sense:company]{op} → company_op (profile/financials/disclosures)
- [sense:crypto]      → crypto_price (자산군 달라 별도 유지)
시장(kr/us)은 ticker로 자동판별(005930/한글=kr, 그외=us), market 파라미터로 강제 지정 가능.
"""
import os
import re
import sys
import json
import calendar
from datetime import datetime, timedelta, date
from pathlib import Path

current_dir = Path(__file__).parent

# 자기 디렉토리 경로 (동적 모듈 로드 시 필요)
_self_dir = os.path.abspath(os.path.dirname(__file__))
if _self_dir not in sys.path:
    sys.path.insert(0, _self_dir)

# common 유틸리티 경로
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.response_formatter import error_response


from common.pkg_utils import load_sibling

def load_module(module_name):
    """같은 디렉토리의 형제 모듈 로드 — 정본은 common.pkg_utils.load_sibling (감사 ⑥)"""
    return load_sibling(__file__, module_name)


def get_definitions():
    """tool.json에서 도구 정의 반환"""
    tool_json_path = current_dir / "tool.json"
    with open(tool_json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── 공통 유틸 ──────────────────────────────────────────

def _arg(ti: dict, *keys, default=None):
    """tool_input에서 별칭 키 중 첫 비어있지 않은 값을 반환 (ticker/symbol/query/corp_name 호환)."""
    for k in keys:
        v = ti.get(k)
        if v not in (None, ""):
            return v
    return default


def _detect_market(ticker, market=None) -> str:
    """시장 자동판별. market 명시값 우선, 없으면 ticker로 추정.
    - 6자리 숫자(005930) / .KS·.KQ 접미 / 한글 포함(회사명) → kr
    - 그 외 → us
    """
    if market:
        m = str(market).strip().lower()
        if m in ("kr", "ko", "kor", "korea", "한국", "코스피", "코스닥", "krx"):
            return "kr"
        if m in ("us", "usa", "미국", "나스닥", "nyse", "nasdaq", "global"):
            return "us"
    t = str(ticker or "").strip()
    if not t:
        return "us"
    if re.fullmatch(r"\d{6}", t):
        return "kr"
    if t.upper().endswith((".KS", ".KQ")):
        return "kr"
    if re.search(r"[가-힣]", t):
        return "kr"
    return "us"


def _looks_like_code(t) -> bool:
    """이미 종목코드/티커 형태인가 (해소 불필요)."""
    t = str(t or "").strip()
    if not t:
        return False
    if re.fullmatch(r"\d{6}", t):                       # KR 코드 005930
        return True
    if re.fullmatch(r"\d{6}\.(KS|KQ|ks|kq)", t):        # 102110.KS
        return True
    if re.fullmatch(r"[A-Za-z]{1,6}(\.[A-Za-z]{1,3})?", t):  # AAPL, BRK.B
        return True
    return False


def _resolve_ticker(ticker):
    """이름(예 'TIGER 200', '삼성전자')이면 search로 종목코드를 내부 해소.
    이미 코드/티커면 그대로. (호출자에게 코드를 떠넘기지 않는 '내부 해소' 원칙.)

    ★세계 명사 해소 계약 (2026-08-24 #repair A1) — 추측 금지.
      옛 코드는 `chosen = exact or starts or quotes[0]` 이었다. 즉 아무것도 안 맞으면
      **검색 결과의 첫 줄**을 골랐다: 'TIGER200' 을 물었는데 상장폐지된 동음 종목이
      1위면 그 종목의 시세가 에러 없이 돌아온다. 사용자는 자기가 물은 종목의 값을
      받았다고 믿을 뿐, 결과 안에 확인할 방법이 없다(반증 불가능한 답).
      정확/접두 일치가 없으면 **후보를 들고 거절**한다. 본: real-estate
      tool_region_codes.resolve_region_code.

    Returns: (해소된_심볼, 매칭된_이름 또는 None, 거절봉투 또는 None)
    """
    t = str(ticker or "").strip()
    # 코드/티커(005930·AAPL·102110.KS)가 아니면 모두 이름으로 보고 해소.
    #   "tiger200"(영숫자 혼합)·"TIGER 200"(공백)·"삼성전자"(한글) 모두 포함.
    if not t or _looks_like_code(t):
        return ticker, None, None
    try:
        tool = load_module("tool_yfinance")
        res = tool.search_stock(query=t, search_type="quotes")
        quotes = (res.get("data", {}) or {}).get("quotes", []) if isinstance(res, dict) else []
        if not quotes:
            return ticker, None, None   # 검색 자체가 빈손 — 코드일 수도 있으니 원문 유지
        norm = lambda s: re.sub(r"\s+", "", str(s or "")).strip().lower()  # 공백 제거 비교(TIGER 200 == TIGER200)
        q = norm(t)
        exact = [x for x in quotes if norm(x.get("name")) == q]
        starts = sorted([x for x in quotes if norm(x.get("name")).startswith(q)],
                        key=lambda x: len(norm(x.get("name"))))  # 질의로 시작하는 최단명 (TIGER200 > TIGER200IT)
        chosen = exact[0] if exact else (starts[0] if starts else None)
        if chosen is None:
            # ★추측하지 않는다 — 후보를 들고 거절한다.
            return ticker, None, {
                "success": False,
                "asked": t,
                "candidates": [{"name": x.get("name"), "symbol": x.get("symbol"),
                                "exchange": x.get("exchange")} for x in quotes[:8]],
                "error": (f"'{t}' 와 정확히·앞부분이 일치하는 종목이 없습니다. "
                          f"후보 중 하나의 이름이나 종목코드로 다시 부르세요."),
            }
        return chosen.get("symbol") or ticker, chosen.get("name"), None
    except Exception:
        return ticker, None, None


def _months_ago(d: date, n: int) -> date:
    """n개월 전 날짜 (월말 경계 안전)."""
    total = d.year * 12 + (d.month - 1) - n
    y, m = divmod(total, 12)
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _resolve_period(ti: dict):
    """상대 기간 period → start_date/end_date 자동 계산 (내부 해소).
    명시된 start_date가 있으면 건드리지 않음(우선). period 형식: 1mo/3mo/6mo/1y/5d/2w/ytd/max.
    절대 타임스탬프 대신 상대 표현을 쓰면 같은 의도→같은 IBL(해마 결정성) + 저장 IBL 불변.
    """
    if ti.get("start_date"):
        return
    period = str(ti.get("period") or "").strip().lower()
    if not period:
        return
    today = datetime.now().date()
    start = None
    if period == "ytd":
        start = date(today.year, 1, 1)
    elif period == "max":
        return  # 전체 — 도구 기본에 맡김
    else:
        # 영문 약식(3mo/3m/1y/5d/2w) + 한국어(3개월/3달/1년/2주/5일) 모두 관용 수용
        m = re.fullmatch(r"(\d+)\s*(개월|달|년|주|일|mo|months?|m|y|years?|w|weeks?|d|days?)", period)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            if unit in ("일",) or unit.startswith("d"):
                start = today - timedelta(days=n)
            elif unit in ("주",) or unit.startswith("w"):
                start = today - timedelta(weeks=n)
            elif unit in ("개월", "달") or unit in ("mo", "m") or unit.startswith("month"):
                start = _months_ago(today, n)
            elif unit in ("년",) or unit.startswith("y"):
                start = _months_ago(today, n * 12)
    if start:
        ti["start_date"] = start.isoformat()
        ti.setdefault("end_date", today.isoformat())


def _company_news(symbol, ti: dict):
    """종목 뉴스: Finnhub 우선, 실패/0건 시 Yahoo Finance 폴백 (옛 company_news 로직)."""
    if not symbol:
        return {"success": False, "error": "ticker(티커) 파라미터가 필요합니다. 예: 005930.KS (삼성전자), AAPL (애플)"}
    # 1차: Finnhub (날짜 범위 지정 가능, 전문 금융 뉴스)
    try:
        tool = load_module("tool_finnhub")
        result = tool.get_company_news(
            symbol=symbol,
            start_date=ti.get("start_date"),
            end_date=ti.get("end_date"),
        )
        if isinstance(result, dict) and result.get("success") and result.get("data", {}).get("count", 0) > 0:
            return result
        if isinstance(result, str) and "뉴스" in result and "0건" not in result:
            return result
    except Exception:
        pass
    # 2차: Yahoo Finance 폴백
    try:
        tool = load_module("tool_yfinance")
        return tool.get_stock_news(symbol=symbol)
    except Exception as e:
        return {"success": False, "error": f"뉴스 조회 실패 (Finnhub, Yahoo 모두): {str(e)}"}


# ── 단일 액션 op 디스패처 ───────────────────────────────

def _attach_price_table(result):
    """주가 이력 결과에 단일 통화 items(전 필드) + 표준 table(날짜·종가)을 덧붙인다.

    items = 원본 필드 그대로(date/open/high/low/close/volume — 파이프의 sort/filter 재료,
    2026-08-08: 생산자 직접 방출로 컷오버. 이전엔 derive_items 가 2열 table 을 그림자
    투영해 거래량이 표면·파이프에서 죽었다). table 은 날짜·종가 2열 유지 — chart 계약이
    "첫 열=x, 나머지 전부 시리즈"라 거래량 열을 섞으면 주가 선이 눌린다.
    실패해도 원본 그대로 반환(비파괴).
    """
    try:
        obj = result
        if isinstance(result, str):
            obj = json.loads(result)
        if not isinstance(obj, dict) or not obj.get("success"):
            return result
        data = obj.get("data") or {}
        prices = data.get("prices") or data.get("sample") or []
        rows = [[p.get("date"), p.get("close")] for p in prices
                if isinstance(p, dict) and p.get("close") is not None]
        if rows:
            obj["table"] = {"columns": ["날짜", "종가"], "rows": rows}
        if prices and not isinstance(obj.get("items"), list):
            obj["items"] = [dict(p) for p in prices if isinstance(p, dict)]
        # 절단 신고 최상위 승격(2026-08-08 — ⑥′ 계약 정렬): data.truncated 는 정직 사슬
        # (변환자 비파괴 승계·문서 꼬리·?? 빈손 술어)이 보는 **최상위 키**가 아니었다.
        # items=다운샘플 표본이므로 표본 위 집계가 "총 N거래일 중 일부" 표찰을 달고 나가고,
        # 에이전트는 표찰을 보고 max_points 를 올려 재호출할 수 있다(기본값은 채팅 경제 유지).
        if prices and "truncated" not in obj:
            obj["truncated"] = bool(data.get("truncated"))
            if obj["truncated"] and isinstance(data.get("total_days"), int) and "total" not in obj:
                obj["total"] = data["total_days"]
        return obj
    except Exception:
        return result


# 펀더멘털 dict 키 → 한글 지표명 (없는 키는 키 그대로 표시).
_COMPANY_LABELS = {
    # fmp (미국)
    "symbol": "종목코드", "company_name": "기업명", "price": "주가",
    "market_cap": "시가총액", "beta": "베타", "volume_avg": "평균거래량",
    "last_dividend": "최근배당", "range_52week": "52주 범위", "change": "변동",
    "change_percent": "변동률(%)", "currency": "통화", "exchange": "거래소",
    "industry": "업종", "sector": "섹터", "country": "국가", "employees": "임직원수",
    "ceo": "대표자", "website": "홈페이지", "ipo_date": "상장일",
    # dart (한국)
    "corp_name": "기업명", "corp_name_eng": "영문명", "stock_code": "종목코드",
    "ceo_name": "대표자", "address": "주소", "homepage": "홈페이지",
    "phone": "전화", "fax": "팩스", "establishment_date": "설립일",
    "accounting_month": "결산월",
}
# 표(2열)에 부적합해 제외할 키 (장문 텍스트·내부 식별자·불리언 노이즈).
_COMPANY_TABLE_SKIP = {
    "description", "corp_code", "jurir_no", "bizr_no", "is_etf",
    "is_actively_trading", "corp_cls", "ir_url",
}


def _attach_company_table(result):
    """기업 펀더멘털 결과(profile)에 표준 table 통화(지표·값 2열)를 덧붙인다.

    data dict의 각 항목을 한 행(지표명, 값)으로 펼침 — table:spreadsheet{table}/
    document{table}로 그대로 흐름, `>>` 자동 파이프 대상. 실패해도 원본 그대로(비파괴).
    """
    try:
        obj = result
        if isinstance(result, str):
            obj = json.loads(result)
        if not isinstance(obj, dict) or not obj.get("success"):
            return result
        data = obj.get("data")
        if not isinstance(data, dict) or not data:
            return result
        rows = []
        for key, val in data.items():
            if key in _COMPANY_TABLE_SKIP or val is None or val == "":
                continue
            rows.append([_COMPANY_LABELS.get(key, key), val])
        if rows:
            # 단일 통화 items(행 dict — 지표/값). 소비자가 items→table 재구성.
            obj["items"] = [{"지표": label, "값": val} for label, val in rows]
        return obj
    except Exception:
        return result


def _stock_common(ti: dict, op: str):
    """[sense:stock] 공용 전처리 — (ticker, market, 거절봉투|None) 반환.

    거절봉투가 있으면 op 함수는 **그것을 그대로 반환**한다(추측 금지 계약)."""
    ticker = _arg(ti, "ticker", "symbol", "query", "corp_name")
    # 이름→코드 내부 해소 (search는 이름 그대로 받으므로 제외). 코드면 그대로.
    if op != "search":
        ticker, _rname, _refused = _resolve_ticker(ticker)
        if _refused:
            return ticker, None, _refused
        if _rname:
            ti["_resolved_name"] = _rname   # 성공 봉투에 resolved 로 실린다(execute 말미)
    market = _detect_market(ticker, ti.get("market"))  # 해소된 코드로 시장 재판별
    # 상대기간 period → start/end_date 내부 해소 (quote=현재가는 yfinance period native라 제외)
    if op in ("history", "news", "earnings", "investors"):
        _resolve_period(ti)
    return ticker, market, None


def _stock_quote(ti: dict):
    """[sense:stock]{op:quote} — 현재가 스냅샷 (2026-06-15 quote로 복원, 옛 price)."""
    ticker, market, _refused = _stock_common(ti, "quote")
    if _refused:
        return _refused
    tool = load_module("tool_yfinance")
    return _attach_quote_items(tool.get_stock_price(
        symbol=ticker,
        period=ti.get("period", "5d"),
        interval=ti.get("interval", "1d"),
        max_points=ti.get("max_points", 10),
    ))


# items 행에서 제외할 data 키 — 목록·파생 메타(스냅샷 스칼라만 1행으로).
_QUOTE_ITEMS_SKIP = {"prices", "sample", "file_path", "truncated"}


def _attach_quote_items(result):
    """quote 스냅샷에 단일 통화 items(1행)를 덧붙인다 (2026-08-08, 실험 4).

    통화가 없으면 [A]&[B] >> [table:union] 같은 병렬 결합이 "통화 종류가 같아야"
    에러로 멈춘다(정직하지만 표현 불가). 스냅샷=1행 dict 는 자연스러운 items —
    previous_close 등 도메인 지식이 담긴 필드가 파이프로 흐른다. 비파괴.
    """
    try:
        obj = result
        if isinstance(result, str):
            obj = json.loads(result)
        if not isinstance(obj, dict) or not obj.get("success"):
            return result
        data = obj.get("data") or {}
        # current_price(주식) 외 current_price_usd/krw(코인)도 스냅샷 — F8(2026-08-16 상상훈련
        # 4회차): crypto 만 items 미방출이라 같은 "시세"인데 stock 과 조합 가능성이 갈렸다.
        _has_price = isinstance(data, dict) and any(
            data.get(k) is not None
            for k in ("current_price", "current_price_usd", "current_price_krw"))
        if _has_price and not isinstance(obj.get("items"), list):
            row = {k: v for k, v in data.items() if k not in _QUOTE_ITEMS_SKIP}
            # F1-스냅샷 canonical 병기 (2026-08-16 5회차): 같은 개념이 소스마다 다른 칸이면
            # union 행이 반쪽이 된다(crypto=krw/24h vs stock=current_price/change_percent 실측).
            # 원명 보존 + canonical 추가(제거 아님·병기).
            if row.get("current_price") is None:
                _cp = row.get("current_price_krw") or row.get("current_price_usd")
                if _cp is not None:
                    row["current_price"] = _cp
            if row.get("change_percent") is None and row.get("change_24h_percent") is not None:
                row["change_percent"] = row["change_24h_percent"]
            _nm = row.get("name") or row.get("symbol")
            if _nm:
                row.setdefault("name", _nm)
                row.setdefault("title", _nm)   # 칸 규약 1 (제목 칸)
            obj["items"] = [row]
        return obj
    except Exception:
        return result


def _stock_history(ti: dict):
    """[sense:stock]{op:history} — 기간별 주가 이력/차트 (2026-06-04 개명: 옛 price)."""
    ticker, market, _refused = _stock_common(ti, "history")
    if _refused:
        return _refused
    if str(ticker or "").startswith("^"):
        # 지수(^GSPC·^IXIC·^SOX…)는 FMP 무료 티어가 402(프리미엄 전용) → quote 와 같은
        # Yahoo chart 경로로 우회. 통화는 동일하게 data.prices 라 _attach_price_table 호환.
        tool = load_module("tool_yfinance")
        _res = tool.get_stock_price(
            symbol=ticker,
            period=ti.get("period", "1mo"),
            interval=ti.get("interval", "1d"),
            max_points=ti.get("max_points", 10),
        )
        return _attach_price_table(_res)
    if market == "kr":
        tool = load_module("tool_krx")
        price_symbol = re.sub(r"\.(KS|KQ)$", "", str(ticker or ""), flags=re.I)  # krx는 bare 6자리 코드
    else:
        tool = load_module("tool_fmp")
        price_symbol = ticker
    _res = tool.get_stock_price(
        symbol=price_symbol,
        start_date=ti.get("start_date"),
        end_date=ti.get("end_date"),
        max_points=ti.get("max_points", 10),
    )
    return _attach_price_table(_res)


def _stock_info(ti: dict):
    """[sense:stock]{op:info} — 종목 기본 정보."""
    ticker, market, _refused = _stock_common(ti, "info")
    if _refused:
        return _refused
    tool = load_module("tool_yfinance")
    result = tool.get_stock_info(symbol=ticker)
    # items 1행 병기 (2026-08-19 returns 드리프트 스윕 [B]): 선언·desc 는 info=items 를
    # 약속하는데 방출이 {success, data} 뿐이라 파이프가 굶었다 — quote·crypto 의 1행
    # 스냅샷 관례로 동기화(원 data 키 보존).
    parsed = result
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except Exception:
            return result
    if (isinstance(parsed, dict) and isinstance(parsed.get("data"), dict)
            and "items" not in parsed):
        # NaN/Inf 위생 (실측 2026-08-19): yfinance 가 간헐로 NaN 을 주면 FastAPI 응답
        # 인코더(allow_nan=False)가 500 을 낸다 — 정직한 null 로(정당한 결측 표현).
        def _clean(v):
            if isinstance(v, float) and (v != v or v == float("inf") or v == float("-inf")):
                return None
            if isinstance(v, dict):
                return {k: _clean(x) for k, x in v.items()}
            if isinstance(v, list):
                return [_clean(x) for x in v]
            return v
        parsed = _clean(parsed)
        d = parsed["data"]
        parsed["items"] = [{"title": d.get("symbol") or ticker, **d}]
        parsed["count"] = 1
        return json.dumps(parsed, ensure_ascii=False) if isinstance(result, str) else parsed
    return result


def _stock_search(ti: dict):
    """[sense:stock]{op:search} — 종목 검색 (이름 그대로, 해소 없음)."""
    ticker, market, _refused = _stock_common(ti, "search")
    if _refused:
        return _refused
    tool = load_module("tool_yfinance")
    return tool.search_stock(query=ticker, search_type=ti.get("search_type", "quotes"))


def _stock_investors(ti: dict):
    """[sense:stock]{op:investors} — KRX 투자자별 매매동향."""
    ticker, market, _refused = _stock_common(ti, "investors")
    if _refused:
        return _refused
    tool = load_module("tool_krx_investor")
    if ticker:  # 개별종목 매매동향
        return tool.get_stock_investor_trading(
            symbol=ticker,
            start_date=ti.get("start_date"),
            end_date=ti.get("end_date"),
        )
    # 전체시장 매매동향 — market은 STK/KSQ/ALL 의미 (kr/us 아님)
    mkt = ti.get("market")
    if mkt not in ("STK", "KSQ", "ALL"):
        mkt = "STK"
    return tool.get_market_investor_trading(
        market=mkt,
        start_date=ti.get("start_date"),
        end_date=ti.get("end_date"),
    )


def _stock_news(ti: dict):
    """[sense:stock]{op:news} — 종목 뉴스 (Finnhub→Yahoo 폴백)."""
    ticker, market, _refused = _stock_common(ti, "news")
    if _refused:
        return _refused
    return _company_news(ticker, ti)


def _stock_earnings(ti: dict):
    """[sense:stock]{op:earnings} — 실적 캘린더 (Finnhub)."""
    ticker, market, _refused = _stock_common(ti, "earnings")
    if _refused:
        return _refused
    tool = load_module("tool_finnhub")
    return tool.get_earnings_calendar(
        symbol=ticker,
        start_date=ti.get("start_date"),
        end_date=ti.get("end_date"),
    )


def _company_common(ti: dict):
    """[sense:company] 공용 전처리 (옛 _company_op 앞부분 그대로) — (ticker, market) 반환."""
    ticker = _arg(ti, "ticker", "corp_name", "symbol", "query", "company")  # query/company 추가(코퍼스가 기업명에 사용)
    market = _detect_market(ticker, ti.get("market"))
    return ticker, market


def _company_profile(ti: dict):
    """[sense:company]{op:profile} — 기업 개요 (kr=DART, us=FMP)."""
    ticker, market = _company_common(ti)
    if market == "kr":
        tool = load_module("tool_dart")
        return _attach_company_table(
            tool.get_company_info(corp_code=ti.get("corp_code"), corp_name=ticker)
        )
    tool = load_module("tool_fmp")
    return _attach_company_table(tool.get_company_profile(symbol=ticker))


def _company_financials(ti: dict):
    """[sense:company]{op:financials} — 재무제표 (kr=DART, us=FMP)."""
    ticker, market = _company_common(ti)
    if market == "kr":
        tool = load_module("tool_dart")
        return tool.get_financial_statements(
            corp_code=ti.get("corp_code"),
            corp_name=ticker,
            year=ti.get("year"),
            report_type=ti.get("report_type", "11011"),
        )
    tool = load_module("tool_fmp")
    return tool.get_financial_statements(
        symbol=ticker,
        statement_type=ti.get("statement_type", "income"),
        period=ti.get("period", "annual"),
        limit=ti.get("limit", 5),
    )


def _company_disclosures(ti: dict):
    """[sense:company]{op:disclosures} — 공시 (kr=DART, us=SEC EDGAR)."""
    ticker, market = _company_common(ti)
    if market == "kr":
        tool = load_module("tool_dart")
        return tool.get_disclosures(
            corp_code=ti.get("corp_code"),
            corp_name=ticker,
            start_date=ti.get("start_date"),
            end_date=ti.get("end_date"),
            pblntf_ty=ti.get("pblntf_ty"),
            count=ti.get("limit", ti.get("count", 20)),
        )
    tool = load_module("tool_sec_edgar")
    return tool.get_filings(
        symbol=ticker,
        filing_type=ti.get("filing_type"),
        count=ti.get("limit", ti.get("count", 10)),
    )


# 2026-06-03 dispatcher 표준화 → 2026-08-05 진짜 디스패처 전환.
# 값=실행 함수 참조. build_ibl_nodes.py --check 가 이 dict 키로 src.ops.values 와 정확 비교.
_OP_DISPATCHERS = {
    "stock_op": {
        "quote": _stock_quote, "history": _stock_history, "info": _stock_info,
        "search": _stock_search, "investors": _stock_investors,
        "news": _stock_news, "earnings": _stock_earnings,
    },
    "company_op": {"profile": _company_profile, "financials": _company_financials,
                   "disclosures": _company_disclosures},
}
_OP_DEFAULTS = {"stock_op": "quote", "company_op": "profile"}


def execute(tool_input: dict, context):
    """도구 실행 진입점 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    try:
        if tool_name in _OP_DISPATCHERS:
            op = (tool_input.get("op") or _OP_DEFAULTS[tool_name]).strip()
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if fn is None:
                return error_response(f"알 수 없는 op '{op}'. 사용 가능: {sorted(_OP_DISPATCHERS[tool_name])}")
            _out = fn(tool_input)
            # ★해소된 이름을 성공 봉투에 싣는다 — 답이 자기가 무엇에 대한 답인지 말해야
            #   사용자가 오매칭을 반증할 수 있다(세계 명사 해소 계약, 2026-08-24 #repair).
            _rn = tool_input.get("_resolved_name") or tool_input.get("_resolved")
            if _rn and isinstance(_out, dict) and _out.get("success") is not False:
                _out.setdefault("resolved", _rn)
            return _out

        elif tool_name == "crypto_price":
            tool = load_module("tool_yfinance")
            # F8: 스냅샷 1행 items 병기(stock quote 선례 동형) — 없으면 & 병렬 결합이 막힌다.
            return _attach_quote_items(tool.get_crypto_price(
                coin_id=tool_input.get("coin") or tool_input.get("coin_id") or "bitcoin",  # coin 우선(코퍼스/자연어), coin_id 별칭
                days=tool_input.get("days", 0),
                max_points=tool_input.get("max_points", 400),
            ))

        else:
            return error_response(f"알 수 없는 도구입니다: {tool_name}")

    except FileNotFoundError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f"도구 실행 중 오류 발생: {str(e)}")
