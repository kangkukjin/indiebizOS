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
import importlib.util
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


def load_module(module_name: str):
    """동적 모듈 로드"""
    module_path = current_dir / f"{module_name}.py"
    if not module_path.exists():
        raise FileNotFoundError(f"모듈을 찾을 수 없습니다: {module_name}")

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    Returns: (해소된_심볼, 매칭된_이름 또는 None)
    """
    t = str(ticker or "").strip()
    # 코드/티커(005930·AAPL·102110.KS)가 아니면 모두 이름으로 보고 해소.
    #   "tiger200"(영숫자 혼합)·"TIGER 200"(공백)·"삼성전자"(한글) 모두 포함.
    if not t or _looks_like_code(t):
        return ticker, None
    try:
        tool = load_module("tool_yfinance")
        res = tool.search_stock(query=t, search_type="quotes")
        quotes = (res.get("data", {}) or {}).get("quotes", []) if isinstance(res, dict) else []
        if not quotes:
            return ticker, None
        norm = lambda s: re.sub(r"\s+", "", str(s or "")).strip().lower()  # 공백 제거 비교(TIGER 200 == TIGER200)
        q = norm(t)
        exact = [x for x in quotes if norm(x.get("name")) == q]
        starts = sorted([x for x in quotes if norm(x.get("name")).startswith(q)],
                        key=lambda x: len(norm(x.get("name"))))  # 질의로 시작하는 최단명 (TIGER200 > TIGER200IT)
        chosen = exact[0] if exact else (starts[0] if starts else quotes[0])
        return chosen.get("symbol") or ticker, chosen.get("name")
    except Exception:
        return ticker, None


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
    """주가 이력 결과에 표준 table 통화(날짜·종가 시계열)를 덧붙인다.

    table:chart{table:...}/spreadsheet{table:...}로 그대로 흘려보냄 + `>>` 자동 파이프 대상.
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


def _stock_op(ti: dict):
    """[sense:stock]{op} — 주식 시세·거래 데이터."""
    op = (ti.get("op") or _OP_DEFAULTS["stock_op"]).strip()
    ticker = _arg(ti, "ticker", "symbol", "query", "corp_name")
    # 이름→코드 내부 해소 (search는 이름 그대로 받으므로 제외). 코드면 그대로.
    if op != "search":
        ticker, _ = _resolve_ticker(ticker)
    market = _detect_market(ticker, ti.get("market"))  # 해소된 코드로 시장 재판별
    # 상대기간 period → start/end_date 내부 해소 (quote=현재가는 yfinance period native라 제외)
    if op in ("history", "news", "earnings", "investors"):
        _resolve_period(ti)

    if op == "quote":  # 현재가 스냅샷 (2026-06-15 quote로 복원, 옛 price)
        tool = load_module("tool_yfinance")
        return tool.get_stock_price(
            symbol=ticker,
            period=ti.get("period", "5d"),
            interval=ti.get("interval", "1d"),
            max_points=ti.get("max_points", 10),
        )
    if op == "history":  # 기간별 주가 이력/차트 (2026-06-04 개명: 옛 price)
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
    if op == "info":
        tool = load_module("tool_yfinance")
        return tool.get_stock_info(symbol=ticker)
    if op == "search":
        tool = load_module("tool_yfinance")
        return tool.search_stock(query=ticker, search_type=ti.get("search_type", "quotes"))
    if op == "investors":
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
    if op == "news":
        return _company_news(ticker, ti)
    if op == "earnings":
        tool = load_module("tool_finnhub")
        return tool.get_earnings_calendar(
            symbol=ticker,
            start_date=ti.get("start_date"),
            end_date=ti.get("end_date"),
        )
    return error_response(f"알 수 없는 op '{op}'. 사용 가능: {sorted(_OP_DISPATCHERS['stock_op'])}")


def _company_op(ti: dict):
    """[sense:company]{op} — 기업 펀더멘털 (정보·재무·공시)."""
    op = (ti.get("op") or _OP_DEFAULTS["company_op"]).strip()
    ticker = _arg(ti, "ticker", "corp_name", "symbol", "query", "company")  # query/company 추가(코퍼스가 기업명에 사용)
    market = _detect_market(ticker, ti.get("market"))

    if op == "profile":
        if market == "kr":
            tool = load_module("tool_dart")
            return _attach_company_table(
                tool.get_company_info(corp_code=ti.get("corp_code"), corp_name=ticker)
            )
        tool = load_module("tool_fmp")
        return _attach_company_table(tool.get_company_profile(symbol=ticker))
    if op == "financials":
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
    if op == "disclosures":
        if market == "kr":
            tool = load_module("tool_dart")
            return tool.get_disclosures(
                corp_code=ti.get("corp_code"),
                corp_name=ticker,
                start_date=ti.get("start_date"),
                end_date=ti.get("end_date"),
                pblntf_ty=ti.get("pblntf_ty"),
                count=ti.get("count", 20),
            )
        tool = load_module("tool_sec_edgar")
        return tool.get_filings(
            symbol=ticker,
            filing_type=ti.get("filing_type"),
            count=ti.get("count", 10),
        )
    return error_response(f"알 수 없는 op '{op}'. 사용 가능: {sorted(_OP_DISPATCHERS['company_op'])}")


# 2026-06-03 dispatcher 표준화 — 단일 액션 op 키 메타데이터.
# 값은 None — 분기 로직은 _stock_op/_company_op 함수 안에 유지.
# build_ibl_nodes.py --check 가 이 dict 키로 src.ops.values 와 정확 비교.
_OP_DISPATCHERS = {
    "stock_op": {
        "quote": None, "history": None, "info": None, "search": None,
        "investors": None, "news": None, "earnings": None,
    },
    "company_op": {"profile": None, "financials": None, "disclosures": None},
}
_OP_DEFAULTS = {"stock_op": "quote", "company_op": "profile"}


def execute(tool_input: dict, context):
    """도구 실행 진입점 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    try:
        if tool_name == "stock_op":
            return _stock_op(tool_input)

        elif tool_name == "company_op":
            return _company_op(tool_input)

        elif tool_name == "crypto_price":
            tool = load_module("tool_yfinance")
            return tool.get_crypto_price(
                coin_id=tool_input.get("coin") or tool_input.get("coin_id") or "bitcoin",  # coin 우선(코퍼스/자연어), coin_id 별칭
                days=tool_input.get("days", 0),
                max_points=tool_input.get("max_points", 400),
            )

        else:
            return error_response(f"알 수 없는 도구입니다: {tool_name}")

    except FileNotFoundError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f"도구 실행 중 오류 발생: {str(e)}")
