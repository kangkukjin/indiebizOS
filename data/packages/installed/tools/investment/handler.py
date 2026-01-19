"""
Investment Tools Handler
한국/미국 기업의 주가, 재무제표, 공시정보, 뉴스를 조회하는 투자 분석 도구
"""
import json
import importlib.util
from pathlib import Path

current_dir = Path(__file__).parent


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


def execute(tool_name: str, params: dict, project_path: str = None):
    """
    도구 실행 진입점

    Args:
        tool_name: 실행할 도구 이름
        params: 도구 파라미터
        project_path: 프로젝트 경로 (선택사항)

    Returns:
        dict: {"success": bool, "data": ..., "error": ...}
    """
    try:
        # 한국 기업 관련 도구
        if tool_name == "kr_company_info":
            tool = load_module("tool_dart")
            return tool.get_company_info(
                corp_code=params.get("corp_code"),
                corp_name=params.get("corp_name")
            )

        elif tool_name == "kr_financial_statements":
            tool = load_module("tool_dart")
            return tool.get_financial_statements(
                corp_code=params.get("corp_code"),
                corp_name=params.get("corp_name"),
                year=params.get("year"),
                report_type=params.get("report_type", "11011")
            )

        elif tool_name == "kr_disclosures":
            tool = load_module("tool_dart")
            return tool.get_disclosures(
                corp_code=params.get("corp_code"),
                corp_name=params.get("corp_name"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
                pblntf_ty=params.get("pblntf_ty"),
                count=params.get("count", 20)
            )

        elif tool_name == "kr_stock_price":
            tool = load_module("tool_krx")
            return tool.get_stock_price(
                symbol=params.get("symbol"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date")
            )

        # 미국 기업 관련 도구
        elif tool_name == "us_company_profile":
            tool = load_module("tool_fmp")
            return tool.get_company_profile(
                symbol=params.get("symbol")
            )

        elif tool_name == "us_financial_statements":
            tool = load_module("tool_fmp")
            return tool.get_financial_statements(
                symbol=params.get("symbol"),
                statement_type=params.get("statement_type", "income"),
                period=params.get("period", "annual"),
                limit=params.get("limit", 5)
            )

        elif tool_name == "us_sec_filings":
            tool = load_module("tool_sec_edgar")
            return tool.get_filings(
                symbol=params.get("symbol"),
                filing_type=params.get("filing_type"),
                count=params.get("count", 10)
            )

        elif tool_name == "us_stock_price":
            tool = load_module("tool_fmp")
            return tool.get_stock_price(
                symbol=params.get("symbol"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date")
            )

        # 공통 도구 (뉴스, 실적)
        elif tool_name == "company_news":
            tool = load_module("tool_finnhub")
            return tool.get_company_news(
                symbol=params.get("symbol"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date")
            )

        elif tool_name == "earnings_calendar":
            tool = load_module("tool_finnhub")
            return tool.get_earnings_calendar(
                symbol=params.get("symbol"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date")
            )

        else:
            return {
                "success": False,
                "error": f"알 수 없는 도구입니다: {tool_name}"
            }

    except FileNotFoundError as e:
        return {
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"도구 실행 중 오류 발생: {str(e)}"
        }
