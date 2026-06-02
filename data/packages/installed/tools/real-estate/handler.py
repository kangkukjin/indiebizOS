import importlib.util
from pathlib import Path

current_dir = Path(__file__).parent

def load_module(module_name):
    module_path = current_dir / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def execute(tool_input: dict, context):
    """IndieBiz OS에서 도구를 호출할 때 실행되는 메인 핸들러 (ToolContext 기반 신규 시그니처).

    모든 도구가 기간 범위 조회를 지원 (start_month/end_month)
    """
    tool_name = context.tool_name

    if tool_name in ("realty_price", "apt_trade_price", "apt_rent_price", "house_trade_price", "house_rent_price"):
        region_code = tool_input.get("region_code")
        start_month = tool_input.get("start_month")
        end_month = tool_input.get("end_month")
        count_per_month = tool_input.get("count_per_month", 30)

        # region_code가 없으면 region(지역 이름)을 받아 내부에서 자동 해소한다.
        # 코드를 호출자가 미리 찾아 넣게 하지 않는다 — 로컬 매핑(+카카오)이라 비용 0~소.
        _resolved_region = None
        if not region_code:
            region_name = tool_input.get("region") or tool_input.get("region_name") or tool_input.get("city")
            if region_name:
                rc = load_module("tool_region_codes").resolve_region_code(region_name)
                if rc.get("code"):
                    region_code = rc["code"]
                    _matched = rc.get("matched") or region_name
                    _via = rc.get("via")  # 읍·면·동을 상위 시군구로 올린 경우
                    _resolved_region = f"{_matched} ({_via})" if _via and _via not in _matched else _matched
                else:
                    # 모호하거나 못 찾음 — 후보/안내를 그대로 돌려준다
                    return {"success": False, **rc}
        if not region_code:
            return {"success": False, "error": "region_code(5자리) 또는 region(시군구 이름, 예: 강남구·청주시흥덕구)이 필요합니다."}
        # 기간 기본값: "최근" 의도를 충족하도록 최근 3개월 (이번 달만 보면 월초엔 거래가 거의 없다)
        from datetime import datetime
        _now = datetime.now()
        if not end_month:
            end_month = _now.strftime("%Y%m")
        if not start_month:
            _y, _m = _now.year, _now.month - 2
            while _m <= 0:
                _m += 12
                _y -= 1
            start_month = f"{_y}{_m:02d}"

    if tool_name == "realty_price":
        rtype = tool_input.get("type", "apt")
        deal = tool_input.get("deal", "trade")
        _dispatch = {
            ("apt", "trade"): ("tool_apt_trade_range", "get_apt_trade_range"),
            ("apt", "rent"): ("tool_apt_rent", "get_apt_rent"),
            ("house", "trade"): ("tool_house_trade_range", "get_house_trade_range"),
            ("house", "rent"): ("tool_house_rent", "get_house_rent"),
            ("villa", "trade"): ("tool_villa_trade_range", "get_villa_trade_range"),
            ("villa", "rent"): ("tool_villa_rent", "get_villa_rent"),
        }
        sel = _dispatch.get((rtype, deal))
        if not sel:
            return {"success": False, "error": f"잘못된 조합: type={rtype}, deal={deal}. type은 apt|house|villa, deal은 trade|rent."}
        mod, fn = sel
        result = getattr(load_module(mod), fn)(region_code, start_month, end_month, count_per_month)
        # 공통 키 보강: type별로 명칭/면적 필드명이 달라(apt=아파트명/전용면적, house=주택유형/연면적,
        # villa=건물명/전용면적, 전월세=계약면적) 호출자가 균일하게 못 읽는다. 기존 키는 보존하고 공통 키만 추가.
        if isinstance(result, dict) and isinstance(result.get("data"), list):
            for it in result["data"]:
                if isinstance(it, dict):
                    it.setdefault("명칭", it.get("아파트명") or it.get("건물명") or it.get("주택유형") or "")
                    it.setdefault("면적", it.get("전용면적") or it.get("계약면적")
                                  or it.get("연면적") or it.get("대지면적") or it.get("대지권면적") or "")
        # dong: 법정동 이름으로 결과 좁히기 (실거래가는 시군구 단위라, 읍·면·동만 보려면 후필터)
        dong = tool_input.get("dong")
        if dong and isinstance(result, dict) and isinstance(result.get("data"), list):
            result["data"] = [it for it in result["data"] if dong in (it.get("법정동") or "")]
            if isinstance(result.get("summary"), dict):
                result["summary"]["총거래건수"] = len(result["data"])
                result["summary"]["동필터"] = dong
        # 이름→시군구 자동 해소가 일어났으면 어떤 지역으로 조회했는지 결과에 표기 (투명성)
        if isinstance(result, dict) and _resolved_region:
            result["조회지역"] = _resolved_region
        return result

    if tool_name == "apt_trade_price":
        tool = load_module("tool_apt_trade_range")
        return tool.get_apt_trade_range(region_code, start_month, end_month, count_per_month)

    elif tool_name == "apt_rent_price":
        tool = load_module("tool_apt_rent")
        return tool.get_apt_rent(region_code, start_month, end_month, count_per_month)

    elif tool_name == "house_trade_price":
        tool = load_module("tool_house_trade_range")
        return tool.get_house_trade_range(region_code, start_month, end_month, count_per_month)

    elif tool_name == "house_rent_price":
        tool = load_module("tool_house_rent")
        return tool.get_house_rent(region_code, start_month, end_month, count_per_month)

    elif tool_name == "get_region_codes":
        tool = load_module("tool_region_codes")
        city = tool_input.get("city", "")
        return tool.get_region_codes(city)

    elif tool_name == "search_commercial_district":
        tool = load_module("tool_commercial_district")
        lat = tool_input.get("lat")
        lng = tool_input.get("lng")
        radius = tool_input.get("radius", 500)
        region_code = tool_input.get("region_code")
        indsLclsCd = tool_input.get("indsLclsCd")
        return tool.search_commercial_district(lat=lat, lng=lng, radius=radius, region_code=region_code, indsLclsCd=indsLclsCd)

    else:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        }

def get_definitions():
    """모든 도구 정의 반환 - tool.json에서 읽음"""
    import json
    tool_json_path = current_dir / "tool.json"
    with open(tool_json_path, 'r', encoding='utf-8') as f:
        return json.load(f)
