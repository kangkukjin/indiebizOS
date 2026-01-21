"""
캔들스틱 차트 도구
주식/암호화폐 가격 변동 분석용
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


def create_candlestick_chart(data: list = None, data_file: str = None, title: str = None,
                              show_volume: bool = True, ma_periods: list = None,
                              output_format: str = "png", output_path: str = None):
    """
    캔들스틱 차트 생성

    Args:
        data: OHLC 데이터 [{date, open, high, low, close, volume}, ...]
        data_file: 데이터 파일 경로 (JSON/CSV) - 대량 데이터에 권장
        title: 차트 제목
        show_volume: 거래량 표시 여부
        ma_periods: 이동평균선 기간 목록 [5, 20, 60]
        output_format: 출력 형식 (png, html, base64)
        output_path: 저장 경로

    Returns:
        dict: 결과 정보
    """
    common = _load_common()

    # 데이터 로드 및 샘플링
    data, original_count, sampled, error = common.load_and_sample(data, data_file)
    if error:
        return {"success": False, "error": error}

    try:
        return _create_with_plotly(data, title, show_volume, ma_periods,
                                   output_format, output_path, common, sampled, original_count)
    except ImportError:
        return _create_with_matplotlib(data, title, show_volume, ma_periods,
                                       output_format, output_path, common, sampled, original_count)


def _calculate_ma(close_prices: list, period: int):
    """이동평균 계산"""
    ma = []
    for i in range(len(close_prices)):
        if i < period - 1:
            ma.append(None)
        else:
            avg = sum(close_prices[i - period + 1:i + 1]) / period
            ma.append(avg)
    return ma


def _create_with_plotly(data, title, show_volume, ma_periods, output_format, output_path, common, sampled=False, original_count=0):
    """Plotly로 캔들스틱 차트 생성"""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # 데이터 추출
    dates = [item.get('date') for item in data]
    opens = [item.get('open') for item in data]
    highs = [item.get('high') for item in data]
    lows = [item.get('low') for item in data]
    closes = [item.get('close') for item in data]
    volumes = [item.get('volume', 0) for item in data]

    # 서브플롯 설정
    if show_volume and any(v > 0 for v in volumes):
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                           vertical_spacing=0.03,
                           row_heights=[0.7, 0.3])
    else:
        fig = make_subplots(rows=1, cols=1)
        show_volume = False

    # 캔들스틱
    fig.add_trace(go.Candlestick(
        x=dates,
        open=opens,
        high=highs,
        low=lows,
        close=closes,
        name='가격',
        increasing_line_color=common.UP_COLOR,
        decreasing_line_color=common.DOWN_COLOR
    ), row=1, col=1)

    # 이동평균선
    if ma_periods:
        ma_colors = ['#FFA500', '#00CED1', '#9370DB', '#32CD32']
        for i, period in enumerate(ma_periods):
            ma_values = _calculate_ma(closes, period)
            fig.add_trace(go.Scatter(
                x=dates,
                y=ma_values,
                mode='lines',
                name=f'MA{period}',
                line=dict(color=ma_colors[i % len(ma_colors)], width=1)
            ), row=1, col=1)

    # 거래량
    if show_volume:
        colors = [common.UP_COLOR if closes[i] >= opens[i] else common.DOWN_COLOR
                  for i in range(len(closes))]
        fig.add_trace(go.Bar(
            x=dates,
            y=volumes,
            name='거래량',
            marker_color=colors,
            opacity=0.7
        ), row=2, col=1)

    # 레이아웃
    fig.update_layout(
        title=dict(text=title, x=0.5) if title else None,
        template='plotly_white',
        font=dict(family='Apple SD Gothic Neo, Nanum Gothic, sans-serif'),
        xaxis_rangeslider_visible=False,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=600 if show_volume else 400
    )

    fig.update_yaxes(title_text="가격", row=1, col=1)
    if show_volume:
        fig.update_yaxes(title_text="거래량", row=2, col=1)

    result = common.save_plotly_figure(fig, output_path, output_format)

    image_tag = result.get("image_tag", "")
    if sampled:
        summary = f"캔들스틱 차트 생성 완료 (원본 {original_count}개 → {len(data)}개로 샘플링)"
    else:
        summary = f"캔들스틱 차트 생성 완료 ({len(data)}개 데이터)"
    if ma_periods:
        summary += f", MA{ma_periods}"
    if image_tag:
        summary += f"\n\n{image_tag}"

    return {
        "success": True,
        "data": result,
        "summary": summary
    }


def _create_with_matplotlib(data, title, show_volume, ma_periods, output_format, output_path, common, sampled=False, original_count=0):
    """matplotlib로 캔들스틱 차트 생성"""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.lines import Line2D

    common.setup_matplotlib_font()

    # 거래량 유무에 따른 레이아웃
    volumes = [item.get('volume', 0) for item in data]
    has_volume = show_volume and any(v > 0 for v in volumes)

    if has_volume:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8),
                                        gridspec_kw={'height_ratios': [3, 1]},
                                        sharex=True)
    else:
        fig, ax1 = plt.subplots(figsize=(12, 6))
        ax2 = None

    # 데이터 추출
    dates = list(range(len(data)))
    date_labels = [item.get('date', '') for item in data]
    opens = [item.get('open') for item in data]
    highs = [item.get('high') for item in data]
    lows = [item.get('low') for item in data]
    closes = [item.get('close') for item in data]

    # 캔들스틱 그리기
    width = 0.6
    for i in range(len(data)):
        color = common.UP_COLOR if closes[i] >= opens[i] else common.DOWN_COLOR

        # 심지 (wick)
        ax1.plot([i, i], [lows[i], highs[i]], color=color, linewidth=1)

        # 몸통 (body)
        body_bottom = min(opens[i], closes[i])
        body_height = abs(closes[i] - opens[i])
        rect = mpatches.Rectangle((i - width/2, body_bottom), width, body_height,
                                   facecolor=color, edgecolor=color)
        ax1.add_patch(rect)

    # 이동평균선
    if ma_periods:
        ma_colors = ['#FFA500', '#00CED1', '#9370DB', '#32CD32']
        for i, period in enumerate(ma_periods):
            ma_values = _calculate_ma(closes, period)
            ax1.plot(dates, ma_values, color=ma_colors[i % len(ma_colors)],
                    linewidth=1, label=f'MA{period}')
        ax1.legend(loc='upper left')

    # 거래량
    if has_volume:
        colors = [common.UP_COLOR if closes[i] >= opens[i] else common.DOWN_COLOR
                  for i in range(len(closes))]
        ax2.bar(dates, volumes, color=colors, alpha=0.7, width=width)
        ax2.set_ylabel('거래량')
        ax2.grid(True, alpha=0.3)

    # 스타일 설정
    if title:
        ax1.set_title(title, fontsize=14, fontweight='bold')

    ax1.set_ylabel('가격')
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(-1, len(data))

    # x축 레이블
    if len(date_labels) > 20:
        step = len(date_labels) // 10
        tick_positions = list(range(0, len(date_labels), step))
        tick_labels = [date_labels[i] for i in tick_positions]
    else:
        tick_positions = dates
        tick_labels = date_labels

    if ax2:
        ax2.set_xticks(tick_positions)
        ax2.set_xticklabels(tick_labels, rotation=45, ha='right')
    else:
        ax1.set_xticks(tick_positions)
        ax1.set_xticklabels(tick_labels, rotation=45, ha='right')

    plt.tight_layout()

    result = common.save_figure(fig, output_path, output_format)

    image_tag = result.get("image_tag", "")
    if sampled:
        summary = f"캔들스틱 차트 생성 완료 (원본 {original_count}개 → {len(data)}개로 샘플링)"
    else:
        summary = f"캔들스틱 차트 생성 완료 ({len(data)}개 데이터)"
    if image_tag:
        summary += f"\n\n{image_tag}"

    return {
        "success": True,
        "data": result,
        "summary": summary
    }
