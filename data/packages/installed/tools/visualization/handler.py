"""
Visualization Tools Handler
범용 데이터 시각화 도구 패키지
"""
import json
import os
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


def _resolve_data_file(data_file: str, context) -> str:
    """data_file 상대경로를 context.project_path 기준 절대경로로 변환. 절대경로는 그대로."""
    if not data_file:
        return None
    if Path(data_file).is_absolute():
        return data_file
    resolved = context.resolve_path(data_file)
    if os.path.exists(resolved):
        return resolved
    return data_file  # 그대로 반환 (에러는 도구에서 처리)


def execute(tool_input: dict, context):
    """도구 실행 진입점 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name

    # data_file 경로 해석
    data_file = _resolve_data_file(tool_input.get("data_file"), context)

    # output_path를 프로젝트 outputs 폴더 기준으로 강제
    output_base = context.output_dir()
    raw_output = tool_input.get("output_path")
    if raw_output:
        # 파일명만 추출하여 프로젝트 outputs에 저장
        tool_input["output_path"] = os.path.join(output_base, os.path.basename(raw_output))
    else:
        # output_path 미지정 시 프로젝트 outputs 폴더 사용
        tool_input["output_path"] = output_base

    try:
        # 범용 chart 액션: chart_type으로 분기
        if tool_name == "chart":
            chart_type = tool_input.get("chart_type", "line")
            type_map = {
                "line": "line_chart", "bar": "bar_chart", "pie": "pie_chart",
                "scatter": "scatter_plot", "heatmap": "heatmap", "multi": "multi_chart",
                "candlestick": "candlestick_chart",
            }
            tool_name = type_map.get(chart_type, "line_chart")

        if tool_name == "line_chart":
            tool = load_module("tool_line")
            return tool.create_line_chart(
                data=tool_input.get("data"),
                data_file=data_file,
                title=tool_input.get("title"),
                x_label=tool_input.get("x_label"),
                y_label=tool_input.get("y_label"),
                series_names=tool_input.get("series_names"),
                output_format=tool_input.get("output_format", "png"),
                output_path=tool_input.get("output_path")
            )

        elif tool_name == "bar_chart":
            tool = load_module("tool_bar")
            return tool.create_bar_chart(
                data=tool_input.get("data"),
                data_file=data_file,
                title=tool_input.get("title"),
                x_label=tool_input.get("x_label"),
                y_label=tool_input.get("y_label"),
                series_names=tool_input.get("series_names"),
                horizontal=tool_input.get("horizontal", False),
                stacked=tool_input.get("stacked", False),
                output_format=tool_input.get("output_format", "png"),
                output_path=tool_input.get("output_path")
            )

        elif tool_name == "candlestick_chart":
            tool = load_module("tool_candlestick")
            return tool.create_candlestick_chart(
                data=tool_input.get("data"),
                data_file=data_file,
                title=tool_input.get("title"),
                show_volume=tool_input.get("show_volume", True),
                ma_periods=tool_input.get("ma_periods"),
                output_format=tool_input.get("output_format", "png"),
                output_path=tool_input.get("output_path")
            )

        elif tool_name == "pie_chart":
            tool = load_module("tool_pie")
            return tool.create_pie_chart(
                data=tool_input.get("data"),
                title=tool_input.get("title"),
                show_percentage=tool_input.get("show_percentage", True),
                donut=tool_input.get("donut", False),
                output_format=tool_input.get("output_format", "png"),
                output_path=tool_input.get("output_path")
            )

        elif tool_name == "scatter_plot":
            tool = load_module("tool_scatter")
            return tool.create_scatter_plot(
                data=tool_input.get("data"),
                data_file=data_file,
                title=tool_input.get("title"),
                x_label=tool_input.get("x_label"),
                y_label=tool_input.get("y_label"),
                show_trendline=tool_input.get("show_trendline", False),
                output_format=tool_input.get("output_format", "png"),
                output_path=tool_input.get("output_path")
            )

        elif tool_name == "heatmap":
            tool = load_module("tool_heatmap")
            return tool.create_heatmap(
                data=tool_input.get("data"),
                title=tool_input.get("title"),
                x_labels=tool_input.get("x_labels"),
                y_labels=tool_input.get("y_labels"),
                color_scale=tool_input.get("color_scale", "viridis"),
                show_values=tool_input.get("show_values", True),
                output_format=tool_input.get("output_format", "png"),
                output_path=tool_input.get("output_path")
            )

        elif tool_name == "multi_chart":
            tool = load_module("tool_multi")
            return tool.create_multi_chart(
                charts=tool_input.get("charts"),
                title=tool_input.get("title"),
                layout=tool_input.get("layout", "auto"),
                output_format=tool_input.get("output_format", "png"),
                output_path=tool_input.get("output_path")
            )

        else:
            return {
                "success": False,
                "error": f"알 수 없는 도구입니다: {tool_name}"
            }

    except ImportError as e:
        return {
            "success": False,
            "error": f"필요한 라이브러리가 설치되지 않았습니다: {str(e)}. pip install matplotlib plotly 실행이 필요합니다."
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
