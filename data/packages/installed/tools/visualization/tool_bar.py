"""
막대 차트 도구
항목별 비교 분석용
"""
from pathlib import Path
import importlib.util

current_dir = Path(__file__).parent


def _load_common():
    """공통 모듈 로드"""
    spec = importlib.util.spec_from_file_location("tool_common", current_dir / "tool_common.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_bar_chart(data: list, title: str = None, x_label: str = None,
                     y_label: str = None, series_names: list = None,
                     horizontal: bool = False, stacked: bool = False,
                     output_format: str = "png", output_path: str = None):
    """
    막대 차트 생성

    Args:
        data: 데이터 배열 [{label: '항목1', value: 100}, ...] 또는 다중 시리즈
        title: 차트 제목
        x_label: X축 레이블
        y_label: Y축 레이블
        series_names: 시리즈 이름 목록
        horizontal: 가로 막대 여부
        stacked: 누적 막대 여부
        output_format: 출력 형식 (png, html, base64)
        output_path: 저장 경로

    Returns:
        dict: 결과 정보
    """
    if not data:
        return {"success": False, "error": "데이터가 비어있습니다."}

    common = _load_common()

    try:
        return _create_with_plotly(data, title, x_label, y_label, series_names,
                                   horizontal, stacked, output_format, output_path, common)
    except ImportError:
        return _create_with_matplotlib(data, title, x_label, y_label, series_names,
                                       horizontal, stacked, output_format, output_path, common)


def _create_with_plotly(data, title, x_label, y_label, series_names,
                        horizontal, stacked, output_format, output_path, common):
    """Plotly로 막대 차트 생성"""
    import plotly.graph_objects as go

    fig = go.Figure()

    # 데이터 구조 분석
    sample = data[0]
    label_key = 'label' if 'label' in sample else 'name' if 'name' in sample else list(sample.keys())[0]
    value_keys = [k for k in sample.keys() if k != label_key]
    if not value_keys:
        value_keys = ['value']

    labels = [item.get(label_key) for item in data]

    # 각 시리즈 추가
    for i, v_key in enumerate(value_keys):
        values = [item.get(v_key, 0) for item in data]

        if series_names and i < len(series_names):
            name = series_names[i]
        elif len(value_keys) == 1:
            name = ""
        else:
            name = v_key

        if horizontal:
            fig.add_trace(go.Bar(
                y=labels,
                x=values,
                name=name,
                orientation='h',
                marker_color=common.COLORS[i % len(common.COLORS)]
            ))
        else:
            fig.add_trace(go.Bar(
                x=labels,
                y=values,
                name=name,
                marker_color=common.COLORS[i % len(common.COLORS)]
            ))

    # 레이아웃 설정
    barmode = 'stack' if stacked else 'group'

    fig.update_layout(
        title=dict(text=title, x=0.5) if title else None,
        xaxis_title=y_label if horizontal else x_label,
        yaxis_title=x_label if horizontal else y_label,
        template='plotly_white',
        font=dict(family='Apple SD Gothic Neo, Nanum Gothic, sans-serif'),
        barmode=barmode,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ) if len(value_keys) > 1 else dict(visible=False)
    )

    result = common.save_plotly_figure(fig, output_path, output_format)

    return {
        "success": True,
        "data": result,
        "summary": f"막대 차트 생성 완료 ({len(data)}개 항목, {len(value_keys)}개 시리즈)"
    }


def _create_with_matplotlib(data, title, x_label, y_label, series_names,
                            horizontal, stacked, output_format, output_path, common):
    """matplotlib로 막대 차트 생성"""
    import matplotlib.pyplot as plt
    import numpy as np

    common.setup_matplotlib_font()

    fig, ax = plt.subplots(figsize=(10, 6))

    # 데이터 분석
    sample = data[0]
    label_key = 'label' if 'label' in sample else 'name' if 'name' in sample else list(sample.keys())[0]
    value_keys = [k for k in sample.keys() if k != label_key]
    if not value_keys:
        value_keys = ['value']

    labels = [item.get(label_key) for item in data]
    x = np.arange(len(labels))
    width = 0.8 / len(value_keys)

    # 각 시리즈 플롯
    bottom = np.zeros(len(labels)) if stacked else None

    for i, v_key in enumerate(value_keys):
        values = [item.get(v_key, 0) for item in data]

        if series_names and i < len(series_names):
            name = series_names[i]
        elif len(value_keys) == 1:
            name = ""
        else:
            name = v_key

        if horizontal:
            if stacked:
                ax.barh(labels, values, label=name, color=common.COLORS[i % len(common.COLORS)],
                        left=bottom)
                bottom = bottom + np.array(values)
            else:
                ax.barh(x + i * width, values, width, label=name,
                        color=common.COLORS[i % len(common.COLORS)])
        else:
            if stacked:
                ax.bar(labels, values, label=name, color=common.COLORS[i % len(common.COLORS)],
                       bottom=bottom)
                bottom = bottom + np.array(values)
            else:
                ax.bar(x + i * width, values, width, label=name,
                       color=common.COLORS[i % len(common.COLORS)])

    # 스타일 설정
    if title:
        ax.set_title(title, fontsize=14, fontweight='bold')

    if horizontal:
        if y_label:
            ax.set_xlabel(y_label)
        if x_label:
            ax.set_ylabel(x_label)
        if not stacked and len(value_keys) > 1:
            ax.set_yticks(x + width * (len(value_keys) - 1) / 2)
            ax.set_yticklabels(labels)
    else:
        if x_label:
            ax.set_xlabel(x_label)
        if y_label:
            ax.set_ylabel(y_label)
        if not stacked and len(value_keys) > 1:
            ax.set_xticks(x + width * (len(value_keys) - 1) / 2)
            ax.set_xticklabels(labels, rotation=45, ha='right')
        else:
            plt.xticks(rotation=45, ha='right')

    if len(value_keys) > 1:
        ax.legend()

    ax.grid(True, alpha=0.3, axis='y' if not horizontal else 'x')
    plt.tight_layout()

    result = common.save_figure(fig, output_path, output_format)

    return {
        "success": True,
        "data": result,
        "summary": f"막대 차트 생성 완료 ({len(data)}개 항목)"
    }
