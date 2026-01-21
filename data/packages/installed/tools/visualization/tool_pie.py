"""
파이 차트 도구
구성비, 비율 분석용
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


def create_pie_chart(data: list, title: str = None, show_percentage: bool = True,
                     donut: bool = False, output_format: str = "png",
                     output_path: str = None):
    """
    파이 차트 생성

    Args:
        data: 데이터 배열 [{label: '항목1', value: 30}, ...]
        title: 차트 제목
        show_percentage: 퍼센트 표시 여부
        donut: 도넛 차트 여부
        output_format: 출력 형식 (png, html, base64)
        output_path: 저장 경로

    Returns:
        dict: 결과 정보
    """
    if not data:
        return {"success": False, "error": "데이터가 비어있습니다."}

    common = _load_common()

    try:
        return _create_with_plotly(data, title, show_percentage, donut,
                                   output_format, output_path, common)
    except ImportError:
        return _create_with_matplotlib(data, title, show_percentage, donut,
                                       output_format, output_path, common)


def _create_with_plotly(data, title, show_percentage, donut, output_format, output_path, common):
    """Plotly로 파이 차트 생성"""
    import plotly.graph_objects as go

    # 데이터 추출
    labels = [item.get('label', item.get('name', '')) for item in data]
    values = [item.get('value', 0) for item in data]

    # 도넛 차트 설정
    hole = 0.4 if donut else 0

    # 텍스트 정보
    if show_percentage:
        textinfo = 'label+percent'
    else:
        textinfo = 'label+value'

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=hole,
        textinfo=textinfo,
        textposition='outside',
        marker=dict(colors=common.COLORS[:len(labels)]),
        pull=[0.02] * len(labels)  # 살짝 분리
    )])

    fig.update_layout(
        title=dict(text=title, x=0.5) if title else None,
        template='plotly_white',
        font=dict(family='Apple SD Gothic Neo, Nanum Gothic, sans-serif'),
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.02
        )
    )

    result = common.save_plotly_figure(fig, output_path, output_format)

    image_tag = result.get("image_tag", "")
    summary = f"파이 차트 생성 완료 ({len(data)}개 항목)"
    if image_tag:
        summary += f"\n\n{image_tag}"

    return {
        "success": True,
        "data": result,
        "summary": summary
    }


def _create_with_matplotlib(data, title, show_percentage, donut, output_format, output_path, common):
    """matplotlib로 파이 차트 생성"""
    import matplotlib.pyplot as plt

    common.setup_matplotlib_font()

    fig, ax = plt.subplots(figsize=(10, 8))

    # 데이터 추출
    labels = [item.get('label', item.get('name', '')) for item in data]
    values = [item.get('value', 0) for item in data]
    colors = common.COLORS[:len(labels)]

    # 퍼센트 표시 함수
    def make_autopct(values):
        def autopct(pct):
            total = sum(values)
            val = int(round(pct * total / 100.0))
            if show_percentage:
                return f'{pct:.1f}%\n({val:,})'
            else:
                return f'{val:,}'
        return autopct

    # 파이 차트
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct=make_autopct(values),
        startangle=90,
        explode=[0.02] * len(values),
        pctdistance=0.75
    )

    # 도넛 차트
    if donut:
        centre_circle = plt.Circle((0, 0), 0.4, fc='white')
        ax.add_patch(centre_circle)

    # 스타일
    for autotext in autotexts:
        autotext.set_fontsize(9)

    if title:
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

    ax.axis('equal')
    plt.tight_layout()

    result = common.save_figure(fig, output_path, output_format)

    image_tag = result.get("image_tag", "")
    summary = f"파이 차트 생성 완료 ({len(data)}개 항목)"
    if image_tag:
        summary += f"\n\n{image_tag}"

    return {
        "success": True,
        "data": result,
        "summary": summary
    }
