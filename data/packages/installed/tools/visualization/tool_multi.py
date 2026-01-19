"""
멀티 차트 (대시보드) 도구
여러 차트를 하나의 이미지/페이지에 배치
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


def _load_chart_module(chart_type: str):
    """차트 타입별 모듈 로드"""
    module_map = {
        'line': 'tool_line',
        'bar': 'tool_bar',
        'candlestick': 'tool_candlestick',
        'pie': 'tool_pie',
        'scatter': 'tool_scatter',
        'heatmap': 'tool_heatmap'
    }

    module_name = module_map.get(chart_type)
    if not module_name:
        return None

    spec = importlib.util.spec_from_file_location(module_name, current_dir / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_multi_chart(charts: list, title: str = None, layout: str = "auto",
                       output_format: str = "png", output_path: str = None):
    """
    멀티 차트 (대시보드) 생성

    Args:
        charts: 차트 정의 배열 [{type: 'line', data: [...], title: '...'}, ...]
        title: 전체 대시보드 제목
        layout: 레이아웃 (auto, 2x2, 2x1, 1x2, 3x1, 1x3)
        output_format: 출력 형식 (png, html, base64)
        output_path: 저장 경로

    Returns:
        dict: 결과 정보
    """
    if not charts:
        return {"success": False, "error": "차트 정의가 비어있습니다."}

    common = _load_common()

    try:
        return _create_with_plotly(charts, title, layout, output_format, output_path, common)
    except ImportError:
        return _create_with_matplotlib(charts, title, layout, output_format, output_path, common)


def _determine_layout(n_charts: int, layout: str):
    """레이아웃 결정"""
    if layout == "auto":
        if n_charts == 1:
            return 1, 1
        elif n_charts == 2:
            return 1, 2
        elif n_charts <= 4:
            return 2, 2
        elif n_charts <= 6:
            return 2, 3
        else:
            return 3, 3
    else:
        parts = layout.split('x')
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
        return 2, 2


def _create_with_plotly(charts, title, layout, output_format, output_path, common):
    """Plotly로 멀티 차트 생성"""
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    n_charts = len(charts)
    rows, cols = _determine_layout(n_charts, layout)

    # 각 차트 유형 결정
    specs = []
    for i in range(rows):
        row_specs = []
        for j in range(cols):
            idx = i * cols + j
            if idx < n_charts:
                chart_type = charts[idx].get('type', 'line')
                if chart_type == 'pie':
                    row_specs.append({'type': 'pie'})
                else:
                    row_specs.append({'type': 'xy'})
            else:
                row_specs.append(None)
        specs.append(row_specs)

    # 서브타이틀
    subtitles = []
    for i, chart in enumerate(charts):
        subtitles.append(chart.get('title', f'차트 {i+1}'))

    fig = make_subplots(
        rows=rows, cols=cols,
        specs=specs,
        subplot_titles=subtitles[:n_charts]
    )

    # 각 차트 추가
    for idx, chart in enumerate(charts):
        row = idx // cols + 1
        col = idx % cols + 1

        chart_type = chart.get('type', 'line')
        data = chart.get('data', [])

        if chart_type == 'line':
            _add_line_trace(fig, data, row, col, common)
        elif chart_type == 'bar':
            _add_bar_trace(fig, data, row, col, chart.get('horizontal', False), common)
        elif chart_type == 'pie':
            _add_pie_trace(fig, data, row, col, common)
        elif chart_type == 'scatter':
            _add_scatter_trace(fig, data, row, col, common)

    # 레이아웃
    height = 400 * rows
    fig.update_layout(
        title=dict(text=title, x=0.5) if title else None,
        height=height,
        template='plotly_white',
        font=dict(family='Apple SD Gothic Neo, Nanum Gothic, sans-serif'),
        showlegend=False
    )

    result = common.save_plotly_figure(fig, output_path, output_format)

    return {
        "success": True,
        "data": result,
        "summary": f"대시보드 생성 완료 ({n_charts}개 차트, {rows}x{cols} 레이아웃)"
    }


def _add_line_trace(fig, data, row, col, common):
    """라인 트레이스 추가"""
    import plotly.graph_objects as go

    sample = data[0] if data else {}
    x_key = 'x' if 'x' in sample else 'date' if 'date' in sample else list(sample.keys())[0]
    y_keys = [k for k in sample.keys() if k != x_key]
    if not y_keys:
        y_keys = ['y']

    x_values = [item.get(x_key) for item in data]

    for i, y_key in enumerate(y_keys):
        y_values = [item.get(y_key) for item in data]
        fig.add_trace(
            go.Scatter(x=x_values, y=y_values, mode='lines+markers',
                      line=dict(color=common.COLORS[i % len(common.COLORS)])),
            row=row, col=col
        )


def _add_bar_trace(fig, data, row, col, horizontal, common):
    """막대 트레이스 추가"""
    import plotly.graph_objects as go

    sample = data[0] if data else {}
    label_key = 'label' if 'label' in sample else list(sample.keys())[0]
    value_keys = [k for k in sample.keys() if k != label_key]
    if not value_keys:
        value_keys = ['value']

    labels = [item.get(label_key) for item in data]

    for i, v_key in enumerate(value_keys):
        values = [item.get(v_key, 0) for item in data]

        if horizontal:
            fig.add_trace(
                go.Bar(y=labels, x=values, orientation='h',
                      marker_color=common.COLORS[i % len(common.COLORS)]),
                row=row, col=col
            )
        else:
            fig.add_trace(
                go.Bar(x=labels, y=values,
                      marker_color=common.COLORS[i % len(common.COLORS)]),
                row=row, col=col
            )


def _add_pie_trace(fig, data, row, col, common):
    """파이 트레이스 추가"""
    import plotly.graph_objects as go

    labels = [item.get('label', '') for item in data]
    values = [item.get('value', 0) for item in data]

    fig.add_trace(
        go.Pie(labels=labels, values=values,
               marker=dict(colors=common.COLORS[:len(labels)])),
        row=row, col=col
    )


def _add_scatter_trace(fig, data, row, col, common):
    """산점도 트레이스 추가"""
    import plotly.graph_objects as go

    x_values = [item.get('x') for item in data]
    y_values = [item.get('y') for item in data]

    fig.add_trace(
        go.Scatter(x=x_values, y=y_values, mode='markers',
                  marker=dict(color=common.COLORS[0], size=8)),
        row=row, col=col
    )


def _create_with_matplotlib(charts, title, layout, output_format, output_path, common):
    """matplotlib로 멀티 차트 생성"""
    import matplotlib.pyplot as plt

    common.setup_matplotlib_font()

    n_charts = len(charts)
    rows, cols = _determine_layout(n_charts, layout)

    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4 * rows))

    # axes를 1D로 변환
    if n_charts == 1:
        axes = [axes]
    else:
        axes = axes.flatten() if hasattr(axes, 'flatten') else [axes]

    for idx, chart in enumerate(charts):
        if idx >= len(axes):
            break

        ax = axes[idx]
        chart_type = chart.get('type', 'line')
        data = chart.get('data', [])
        chart_title = chart.get('title', '')

        if chart_type == 'line':
            _plot_line_matplotlib(ax, data, common)
        elif chart_type == 'bar':
            _plot_bar_matplotlib(ax, data, chart.get('horizontal', False), common)
        elif chart_type == 'pie':
            _plot_pie_matplotlib(ax, data, common)
        elif chart_type == 'scatter':
            _plot_scatter_matplotlib(ax, data, common)

        if chart_title:
            ax.set_title(chart_title, fontsize=11, fontweight='bold')

    # 빈 서브플롯 숨기기
    for idx in range(n_charts, len(axes)):
        axes[idx].set_visible(False)

    if title:
        fig.suptitle(title, fontsize=14, fontweight='bold')

    plt.tight_layout()

    result = common.save_figure(fig, output_path, output_format)

    return {
        "success": True,
        "data": result,
        "summary": f"대시보드 생성 완료 ({n_charts}개 차트)"
    }


def _plot_line_matplotlib(ax, data, common):
    """matplotlib 라인 플롯"""
    sample = data[0] if data else {}
    x_key = 'x' if 'x' in sample else list(sample.keys())[0]
    y_keys = [k for k in sample.keys() if k != x_key]
    if not y_keys:
        y_keys = ['y']

    x_values = [item.get(x_key) for item in data]

    for i, y_key in enumerate(y_keys):
        y_values = [item.get(y_key) for item in data]
        ax.plot(x_values, y_values, marker='o', markersize=3,
                color=common.COLORS[i % len(common.COLORS)])

    ax.tick_params(axis='x', rotation=45)
    ax.grid(True, alpha=0.3)


def _plot_bar_matplotlib(ax, data, horizontal, common):
    """matplotlib 막대 플롯"""
    sample = data[0] if data else {}
    label_key = 'label' if 'label' in sample else list(sample.keys())[0]
    value_keys = [k for k in sample.keys() if k != label_key]
    if not value_keys:
        value_keys = ['value']

    labels = [item.get(label_key) for item in data]
    values = [item.get(value_keys[0], 0) for item in data]

    if horizontal:
        ax.barh(labels, values, color=common.COLORS[0])
    else:
        ax.bar(labels, values, color=common.COLORS[0])
        ax.tick_params(axis='x', rotation=45)

    ax.grid(True, alpha=0.3)


def _plot_pie_matplotlib(ax, data, common):
    """matplotlib 파이 플롯"""
    labels = [item.get('label', '') for item in data]
    values = [item.get('value', 0) for item in data]

    ax.pie(values, labels=labels, colors=common.COLORS[:len(labels)],
           autopct='%1.1f%%', startangle=90)
    ax.axis('equal')


def _plot_scatter_matplotlib(ax, data, common):
    """matplotlib 산점도 플롯"""
    x_values = [item.get('x') for item in data]
    y_values = [item.get('y') for item in data]

    ax.scatter(x_values, y_values, c=common.COLORS[0], alpha=0.7)
    ax.grid(True, alpha=0.3)
