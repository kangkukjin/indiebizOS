"""
산점도 도구
변수 간 관계, 분포 분석용
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


def create_scatter_plot(data: list, title: str = None, x_label: str = None,
                        y_label: str = None, show_trendline: bool = False,
                        output_format: str = "png", output_path: str = None):
    """
    산점도 생성

    Args:
        data: 데이터 배열 [{x: 10, y: 20, label: '항목1', size: 5}, ...]
        title: 차트 제목
        x_label: X축 레이블
        y_label: Y축 레이블
        show_trendline: 추세선 표시 여부
        output_format: 출력 형식 (png, html, base64)
        output_path: 저장 경로

    Returns:
        dict: 결과 정보
    """
    if not data:
        return {"success": False, "error": "데이터가 비어있습니다."}

    common = _load_common()

    try:
        return _create_with_plotly(data, title, x_label, y_label, show_trendline,
                                   output_format, output_path, common)
    except ImportError:
        return _create_with_matplotlib(data, title, x_label, y_label, show_trendline,
                                       output_format, output_path, common)


def _create_with_plotly(data, title, x_label, y_label, show_trendline,
                        output_format, output_path, common):
    """Plotly로 산점도 생성"""
    import plotly.graph_objects as go

    x_values = [item.get('x') for item in data]
    y_values = [item.get('y') for item in data]
    labels = [item.get('label', '') for item in data]
    sizes = [item.get('size', 10) for item in data]

    # 크기 정규화
    if max(sizes) > 50:
        sizes = [s / max(sizes) * 30 + 5 for s in sizes]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=x_values,
        y=y_values,
        mode='markers',
        text=labels,
        marker=dict(
            size=sizes,
            color=common.COLORS[0],
            opacity=0.7,
            line=dict(width=1, color='white')
        ),
        hovertemplate='%{text}<br>X: %{x}<br>Y: %{y}<extra></extra>'
    ))

    # 추세선
    if show_trendline and len(x_values) > 1:
        import numpy as np
        x_arr = np.array([v for v in x_values if v is not None])
        y_arr = np.array([y_values[i] for i, v in enumerate(x_values) if v is not None])

        if len(x_arr) > 1:
            z = np.polyfit(x_arr, y_arr, 1)
            p = np.poly1d(z)
            x_line = np.linspace(min(x_arr), max(x_arr), 100)

            fig.add_trace(go.Scatter(
                x=x_line,
                y=p(x_line),
                mode='lines',
                name='추세선',
                line=dict(color='red', dash='dash', width=2)
            ))

    fig.update_layout(
        title=dict(text=title, x=0.5) if title else None,
        xaxis_title=x_label,
        yaxis_title=y_label,
        template='plotly_white',
        font=dict(family='Apple SD Gothic Neo, Nanum Gothic, sans-serif'),
        showlegend=show_trendline
    )

    result = common.save_plotly_figure(fig, output_path, output_format)

    return {
        "success": True,
        "data": result,
        "summary": f"산점도 생성 완료 ({len(data)}개 데이터 포인트)"
    }


def _create_with_matplotlib(data, title, x_label, y_label, show_trendline,
                            output_format, output_path, common):
    """matplotlib로 산점도 생성"""
    import matplotlib.pyplot as plt
    import numpy as np

    common.setup_matplotlib_font()

    fig, ax = plt.subplots(figsize=(10, 8))

    x_values = [item.get('x') for item in data]
    y_values = [item.get('y') for item in data]
    labels = [item.get('label', '') for item in data]
    sizes = [item.get('size', 50) for item in data]

    # 크기 정규화
    if max(sizes) > 200:
        sizes = [s / max(sizes) * 150 + 20 for s in sizes]

    ax.scatter(x_values, y_values, s=sizes, c=common.COLORS[0],
               alpha=0.7, edgecolors='white', linewidths=1)

    # 레이블 표시 (선택적)
    for i, label in enumerate(labels):
        if label:
            ax.annotate(label, (x_values[i], y_values[i]),
                       xytext=(5, 5), textcoords='offset points', fontsize=8)

    # 추세선
    if show_trendline and len(x_values) > 1:
        x_arr = np.array([v for v in x_values if v is not None])
        y_arr = np.array([y_values[i] for i, v in enumerate(x_values) if v is not None])

        if len(x_arr) > 1:
            z = np.polyfit(x_arr, y_arr, 1)
            p = np.poly1d(z)
            x_line = np.linspace(min(x_arr), max(x_arr), 100)
            ax.plot(x_line, p(x_line), 'r--', linewidth=2, label='추세선')
            ax.legend()

    if title:
        ax.set_title(title, fontsize=14, fontweight='bold')
    if x_label:
        ax.set_xlabel(x_label)
    if y_label:
        ax.set_ylabel(y_label)

    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    result = common.save_figure(fig, output_path, output_format)

    return {
        "success": True,
        "data": result,
        "summary": f"산점도 생성 완료 ({len(data)}개 데이터 포인트)"
    }
