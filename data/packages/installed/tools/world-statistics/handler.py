"""세계은행 국가별 경제·사회 지표 조회."""
import json
import requests

# ── 내부 해소 테이블 (자연어 지표·국가명 → World Bank 코드) ────────────
# 흔한 케이스만 큐레이션. 미등록 입력은 원시 코드로 간주하고 그대로 통과.
_WB_INDICATORS = {
    "gdp": "NY.GDP.MKTP.CD", "국내총생산": "NY.GDP.MKTP.CD",
    "1인당gdp": "NY.GDP.PCAP.CD", "인당gdp": "NY.GDP.PCAP.CD",
    "gdppercapita": "NY.GDP.PCAP.CD",
    "gdp성장률": "NY.GDP.MKTP.KD.ZG", "경제성장률": "NY.GDP.MKTP.KD.ZG",
    "gdpgrowth": "NY.GDP.MKTP.KD.ZG", "성장률": "NY.GDP.MKTP.KD.ZG",
    "인구": "SP.POP.TOTL", "population": "SP.POP.TOTL", "총인구": "SP.POP.TOTL",
    "인구증가율": "SP.POP.GROW", "populationgrowth": "SP.POP.GROW",
    "인플레이션": "FP.CPI.TOTL.ZG", "물가": "FP.CPI.TOTL.ZG",
    "물가상승률": "FP.CPI.TOTL.ZG", "inflation": "FP.CPI.TOTL.ZG",
    "실업률": "SL.UEM.TOTL.ZS", "unemployment": "SL.UEM.TOTL.ZS",
    "기대수명": "SP.DYN.LE00.IN", "lifeexpectancy": "SP.DYN.LE00.IN",
    "수출": "NE.EXP.GNFS.CD", "exports": "NE.EXP.GNFS.CD",
    "수입": "NE.IMP.GNFS.CD", "imports": "NE.IMP.GNFS.CD",
    "1인당소득": "NY.GNP.PCAP.CD", "gnipercapita": "NY.GNP.PCAP.CD",
    "출산율": "SP.DYN.TFRT.IN", "fertility": "SP.DYN.TFRT.IN",
    "도시인구비율": "SP.URB.TOTL.IN.ZS", "urban": "SP.URB.TOTL.IN.ZS",
    "정부부채": "GC.DOD.TOTL.GD.ZS", "governmentdebt": "GC.DOD.TOTL.GD.ZS",
    "co2": "EN.ATM.CO2E.PC", "이산화탄소": "EN.ATM.CO2E.PC", "탄소배출": "EN.ATM.CO2E.PC",
}
_WB_COUNTRIES = {
    "한국": "KOR", "대한민국": "KOR", "korea": "KOR", "southkorea": "KOR", "rok": "KOR",
    "북한": "PRK", "northkorea": "PRK",
    "미국": "USA", "usa": "USA", "us": "USA", "unitedstates": "USA", "america": "USA",
    "일본": "JPN", "japan": "JPN",
    "중국": "CHN", "china": "CHN",
    "독일": "DEU", "germany": "DEU",
    "영국": "GBR", "uk": "GBR", "unitedkingdom": "GBR", "britain": "GBR",
    "프랑스": "FRA", "france": "FRA",
    "인도": "IND", "india": "IND",
    "러시아": "RUS", "russia": "RUS",
    "캐나다": "CAN", "canada": "CAN",
    "호주": "AUS", "australia": "AUS",
    "브라질": "BRA", "brazil": "BRA",
    "이탈리아": "ITA", "italy": "ITA",
    "스페인": "ESP", "spain": "ESP",
    "멕시코": "MEX", "mexico": "MEX",
    "인도네시아": "IDN", "indonesia": "IDN",
    "베트남": "VNM", "vietnam": "VNM",
    "대만": "TWN", "taiwan": "TWN",
    "싱가포르": "SGP", "singapore": "SGP",
    "태국": "THA", "thailand": "THA",
}


def _norm_wb_key(s: str) -> str:
    return "".join(str(s).lower().split())


def _resolve_wb_indicator(indicator: str) -> str:
    """지표명(자연어)→World Bank 코드. 이미 코드(점 포함)면 그대로."""
    if not indicator:
        return indicator
    if "." in indicator:  # NY.GDP.MKTP.CD 같은 원시 코드
        return indicator
    return _WB_INDICATORS.get(_norm_wb_key(indicator), indicator)


def _resolve_wb_country(country: str) -> str:
    """국가명(자연어)→ISO3. 'all'/2~3자 코드/숫자는 그대로."""
    if not country or country == "all":
        return country or "all"
    key = _norm_wb_key(country)
    if key in _WB_COUNTRIES:
        return _WB_COUNTRIES[key]
    # ISO2/ISO3/숫자 코드로 보이면 대문자로 통과
    if country.isalpha() and len(country) in (2, 3):
        return country.upper()
    return country


def _fetch_world_bank_data(tool_input: dict) -> str:
    """World Bank API를 사용하여 국가별 지표 데이터를 가져옵니다."""
    indicator = _resolve_wb_indicator(tool_input.get("indicator"))
    country = _resolve_wb_country(tool_input.get("country", "all"))
    date = tool_input.get("date")
    per_page = tool_input.get("per_page", 50)

    # API URL 구성
    # 예: http://api.worldbank.org/v2/country/KOR/indicator/NY.GDP.MKTP.CD?format=json&date=2010:2022
    url = f"http://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
    params = {
        "format": "json",
        "per_page": per_page
    }
    if date:
        params["date"] = date

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # World Bank API 응답 구조: [metadata, data_list]
        if not data or len(data) < 2 or not data[1]:
            return json.dumps({"success": False,
                               "error": f"지표 '{indicator}'(국가: {country})에 대한 데이터를 찾을 수 없습니다."},
                              ensure_ascii=False)

        data_list = data[1]

        indicator_name = data_list[0].get("indicator", {}).get("value", indicator)
        country_name = (data_list[0].get("country", {}) or {}).get("value", country)

        # 표준 테이블 통화 + 사람용 요약을 함께 산출
        rows = []
        summary = [f"### World Bank 데이터: {indicator_name} ({country_name})\n"]
        for entry in data_list:
            year = entry.get("date")
            value = entry.get("value")
            if value is not None:
                rows.append([year, value])
                if isinstance(value, (int, float)):
                    fv = f"{value:,.2f}".rstrip('0').rstrip('.')
                else:
                    fv = str(value)
                summary.append(f"- {year}: {fv}")
            else:
                summary.append(f"- {year}: 데이터 없음")

        # 연도 오름차순 (차트/표에 자연스러운 시간 순서; WB는 보통 내림차순 반환)
        rows.sort(key=lambda r: str(r[0]))

        return json.dumps({
            "success": True,
            "indicator": indicator_name,
            "country": country_name,
            # 단일 통화 items(행 dict) — 첫 키=연도(x축 라벨), 둘째=지표값(수치 시리즈).
            # 소비자(chart/spreadsheet)가 items→table 재구성(키 순서=열). §3 table 흡수.
            "items": [{"연도": r[0], indicator_name: r[1]} for r in rows],
            "summary": "\n".join(summary),
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": f"World Bank API 요청 오류: {str(e)}"}, ensure_ascii=False)


def execute(tool_input: dict, context):
    if context.tool_name == "fetch_world_bank_data":
        return _fetch_world_bank_data(tool_input)
    return json.dumps({"success": False, "error": f"Unknown tool: {context.tool_name}"}, ensure_ascii=False)
