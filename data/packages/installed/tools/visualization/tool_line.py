"""
라인 차트 도구
시계열 데이터, 추이 분석용
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


def create_line_chart(data: list, title: str = None, x_label: str = None,
                      y_label: str = None, series_names: list = None,
                      output_format: str = "png", output_path: str = None):
    """
    라인 차트 생성

    Args:
        data: 데이터 배열 [{x: '2024-01', y: 100}, ...] 또는 [{x: '2024-01', y1: 100, y2: 200}, ...]
        title: 차트 제목
        x_label: X축 레이블
        y_label: Y축 레이블
        series_names: 시리즈 이름 목록
        output_format: 출력 형식 (png, html, base64)
        output_path: 저장 경로

    Returns:
        dict: 결과 정보
    """
    if not data:
        return {"success": False, "error": "데이터가 비어있습니다."}

    common = _load_common()

    try:
        # Plotly 사용 시도
        return _create_with_plotly(data, title, x_label, y_label, series_names,
                                   output_format, output_path, common)
    except ImportError:
        # matplotlib 폴백
        return _create_with_matplotlib(data, title, x_label, y_label, series_names,
                                       output_format, output_path, common)


def _create_with_plotly(data, title, x_label, y_label, series_names,
                        output_format, output_path, common):
    """Plotly로 라인 차트 생성"""
    import plotly.graph_objects as go

    fig = go.Figure()

    # 데이터 구조 분석
    sample = data[0]
    x_key = 'x' if 'x' in sample else 'date' if 'date' in sample else list(sample.keys())[0]

    # y 값 키들 찾기
    y_keys = [k for k in sample.keys() if k != x_key]
    if not y_keys:
        y_keys = ['y']

    # series_names가 있고 y_keys와 매칭 가능하면, series_names 순서로 정렬
    # series_names의 키워드가 y_keys에 포함되어 있는지 확인
    if series_names and len(series_names) == len(y_keys):
        # series_names에서 키워드 추출하여 y_keys 재정렬 시도
        reordered_keys = []
        for name in series_names:
            name_lower = name.lower()
            matched = None
            for yk in y_keys:
                yk_lower = yk.lower()
                # 키 이름이 시리즈 이름에 포함되거나 그 반대
                if yk_lower in name_lower or name_lower in yk_lower:
                    matched = yk
                    break
            if matched and matched not in reordered_keys:
                reordered_keys.append(matched)

        # 모든 키가 매칭되면 재정렬된 순서 사용
        if len(reordered_keys) == len(y_keys):
            y_keys = reordered_keys

    # x 값 추출
    x_values = [item.get(x_key) for item in data]

    # 각 시리즈 추가
    for i, y_key in enumerate(y_keys):
        y_values = [item.get(y_key) for item in data]

        # 시리즈 이름 결정
        if series_names and i < len(series_names):
            name = series_names[i]
        elif len(y_keys) == 1:
            name = title or "값"
        else:
            name = y_key

        fig.add_trace(go.Scatter(
            x=x_values,
            y=y_values,
            mode='lines+markers',
            name=name,
            line=dict(color=common.COLORS[i % len(common.COLORS)], width=2),
            marker=dict(size=6)
        ))

    # 레이아웃 설정
    fig.update_layout(
        title=dict(text=title, x=0.5) if title else None,
        xaxis_title=x_label,
        yaxis_title=y_label,
        template='plotly_white',
        font=dict(family='Apple SD Gothic Neo, Nanum Gothic, sans-serif'),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        hovermode='x unified'
    )

    # 저장
    result = common.save_plotly_figure(fig, output_path, output_format)

    return {
        "success": True,
        "data": result,
        "summary": f"라인 차트 생성 완료 ({len(data)}개 데이터 포인트, {len(y_keys)}개 시리즈)"
    }


def _create_with_matplotlib(data, title, x_label, y_label, series_names,
                            output_format, output_path, common):
    """matplotlib로 라인 차트 생성"""
    import matplotlib.pyplot as plt

    common.setup_matplotlib_font()

    fig, ax = plt.subplots(figsize=(10, 6))

    # 데이터 구조 분석
    sample = data[0]
    x_key = 'x' if 'x' in sample else 'date' if 'date' in sample else list(sample.keys())[0]
    y_keys = [k for k in sample.keys() if k != x_key]
    if not y_keys:
        y_keys = ['y']

    # series_names가 있고 y_keys와 매칭 가능하면, series_names 순서로 정렬
    if series_names and len(series_names) == len(y_keys):
        reordered_keys = []
        for name in series_names:
            name_lower = name.lower()
            matched = None
            for yk in y_keys:
                yk_lower = yk.lower()
                if yk_lower in name_lower or name_lower in yk_lower:
                    matched = yk
                    break
            if matched and matched not in reordered_keys:
                reordered_keys.append(matched)
        if len(reordered_keys) == len(y_keys):
            y_keys = reordered_keys

    x_values = [item.get(x_key) for item in data]

    # 각 시리즈 플롯
    for i, y_key in enumerate(y_keys):
        y_values = [item.get(y_key) for item in data]

        if series_names and i < len(series_names):
            name = series_names[i]
        elif len(y_keys) == 1:
            name = title or "값"
        else:
            name = y_key

        ax.plot(x_values, y_values, marker='o', markersize=4,
                color=common.COLORS[i % len(common.COLORS)], label=name, linewidth=2)

    # 스타일 설정
    if title:
        ax.set_title(title, fontsize=14, fontweight='bold')
    if x_label:
        ax.set_xlabel(x_label)
    if y_label:
        ax.set_ylabel(y_label)

    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)

    # x축 레이블 회전
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    # 저장
    result = common.save_figure(fig, output_path, output_format)

    return {
        "success": True,
        "data": result,
        "summary": f"라인 차트 생성 완료 ({len(data)}개 데이터 포인트)"
    }
