"""
Visualization Tools Handler
범용 데이터 시각화 도구 패키지
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


def _resolve_data_file(data_file: str, project_path: str = None) -> str:
    """
    data_file 경로를 절대 경로로 변환
    - 절대 경로면 그대로 반환
    - 상대 경로면 project_path 기준으로 변환
    """
    if not data_file:
        return None

    path = Path(data_file)
    if path.is_absolute():
        return data_file

    # 상대 경로인 경우 project_path 기준으로 변환
    if project_path:
        resolved = Path(project_path) / data_file
        if resolved.exists():
            return str(resolved)

    return data_file  # 그대로 반환 (에러는 도구에서 처리)


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
    # data_file 경로 해석
    data_file = _resolve_data_file(params.get("data_file"), project_path)

    # output_path를 프로젝트 outputs 폴더 기준으로 강제
    if project_path:
        import os
        output_base = os.path.join(project_path, "outputs")
        os.makedirs(output_base, exist_ok=True)
        raw_output = params.get("output_path")
        if raw_output:
            # 파일명만 추출하여 프로젝트 outputs에 저장
            params["output_path"] = os.path.join(output_base, os.path.basename(raw_output))
        else:
            # output_path 미지정 시 프로젝트 outputs 폴더 사용
            params["output_path"] = output_base

    try:
        if tool_name == "line_chart":
            tool = load_module("tool_line")
            return tool.create_line_chart(
                data=params.get("data"),
                data_file=data_file,
                title=params.get("title"),
                x_label=params.get("x_label"),
                y_label=params.get("y_label"),
                series_names=params.get("series_names"),
                output_format=params.get("output_format", "png"),
                output_path=params.get("output_path")
            )

        elif tool_name == "bar_chart":
            tool = load_module("tool_bar")
            return tool.create_bar_chart(
                data=params.get("data"),
                data_file=data_file,
                title=params.get("title"),
                x_label=params.get("x_label"),
                y_label=params.get("y_label"),
                series_names=params.get("series_names"),
                horizontal=params.get("horizontal", False),
                stacked=params.get("stacked", False),
                output_format=params.get("output_format", "png"),
                output_path=params.get("output_path")
            )

        elif tool_name == "candlestick_chart":
            tool = load_module("tool_candlestick")
            return tool.create_candlestick_chart(
                data=params.get("data"),
                data_file=data_file,
                title=params.get("title"),
                show_volume=params.get("show_volume", True),
                ma_periods=params.get("ma_periods"),
                output_format=params.get("output_format", "png"),
                output_path=params.get("output_path")
            )

        elif tool_name == "pie_chart":
            tool = load_module("tool_pie")
            return tool.create_pie_chart(
                data=params.get("data"),
                title=params.get("title"),
                show_percentage=params.get("show_percentage", True),
                donut=params.get("donut", False),
                output_format=params.get("output_format", "png"),
                output_path=params.get("output_path")
            )

        elif tool_name == "scatter_plot":
            tool = load_module("tool_scatter")
            return tool.create_scatter_plot(
                data=params.get("data"),
                data_file=data_file,
                title=params.get("title"),
                x_label=params.get("x_label"),
                y_label=params.get("y_label"),
                show_trendline=params.get("show_trendline", False),
                output_format=params.get("output_format", "png"),
                output_path=params.get("output_path")
            )

        elif tool_name == "heatmap":
            tool = load_module("tool_heatmap")
            return tool.create_heatmap(
                data=params.get("data"),
                title=params.get("title"),
                x_labels=params.get("x_labels"),
                y_labels=params.get("y_labels"),
                color_scale=params.get("color_scale", "viridis"),
                show_values=params.get("show_values", True),
                output_format=params.get("output_format", "png"),
                output_path=params.get("output_path")
            )

        elif tool_name == "multi_chart":
            tool = load_module("tool_multi")
            return tool.create_multi_chart(
                charts=params.get("charts"),
                title=params.get("title"),
                layout=params.get("layout", "auto"),
                output_format=params.get("output_format", "png"),
                output_path=params.get("output_path")
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
