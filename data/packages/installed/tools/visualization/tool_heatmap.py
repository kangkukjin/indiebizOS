"""
히트맵 도구
상관관계, 밀도, 행렬 데이터 시각화용
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


def create_heatmap(data, title: str = None, x_labels: list = None,
                   y_labels: list = None, color_scale: str = "viridis",
                   show_values: bool = True, output_format: str = "png",
                   output_path: str = None):
    """
    히트맵 생성

    Args:
        data: 2D 배열 또는 [{row, col, value}, ...] 형태
        title: 차트 제목
        x_labels: X축 레이블들
        y_labels: Y축 레이블들
        color_scale: 색상 스케일 (viridis, plasma, inferno, blues, reds 등)
        show_values: 셀에 값 표시 여부
        output_format: 출력 형식 (png, html, base64)
        output_path: 저장 경로

    Returns:
        dict: 결과 정보
    """
    if not data:
        return {"success": False, "error": "데이터가 비어있습니다."}

    common = _load_common()

    # 데이터 형식 변환 (딕셔너리 리스트 → 2D 배열)
    if isinstance(data[0], dict):
        data, x_labels, y_labels = _convert_dict_to_matrix(data, x_labels, y_labels)

    try:
        return _create_with_plotly(data, title, x_labels, y_labels, color_scale,
                                   show_values, output_format, output_path, common)
    except ImportError:
        return _create_with_matplotlib(data, title, x_labels, y_labels, color_scale,
                                       show_values, output_format, output_path, common)


def _convert_dict_to_matrix(data, x_labels, y_labels):
    """딕셔너리 리스트를 2D 행렬로 변환"""
    # 고유 행/열 추출
    rows = sorted(set(item.get('row') for item in data))
    cols = sorted(set(item.get('col') for item in data))

    if not x_labels:
        x_labels = cols
    if not y_labels:
        y_labels = rows

    # 행렬 생성
    matrix = [[0] * len(cols) for _ in range(len(rows))]
    row_idx = {r: i for i, r in enumerate(rows)}
    col_idx = {c: i for i, c in enumerate(cols)}

    for item in data:
        r = item.get('row')
        c = item.get('col')
        v = item.get('value', 0)
        if r in row_idx and c in col_idx:
            matrix[row_idx[r]][col_idx[c]] = v

    return matrix, x_labels, y_labels


def _create_with_plotly(data, title, x_labels, y_labels, color_scale,
                        show_values, output_format, output_path, common):
    """Plotly로 히트맵 생성"""
    import plotly.graph_objects as go

    # 값 텍스트
    text = [[str(round(v, 2)) if v is not None else '' for v in row] for row in data] if show_values else None

    fig = go.Figure(data=go.Heatmap(
        z=data,
        x=x_labels,
        y=y_labels,
        colorscale=color_scale,
        text=text,
        texttemplate="%{text}" if show_values else None,
        textfont={"size": 10},
        hovertemplate='%{y} - %{x}<br>값: %{z}<extra></extra>'
    ))

    fig.update_layout(
        title=dict(text=title, x=0.5) if title else None,
        template='plotly_white',
        font=dict(family='Apple SD Gothic Neo, Nanum Gothic, sans-serif'),
        xaxis=dict(side='bottom'),
        yaxis=dict(autorange='reversed')  # y축 위에서 아래로
    )

    result = common.save_plotly_figure(fig, output_path, output_format)

    image_tag = result.get("image_tag", "")
    summary = f"히트맵 생성 완료 ({len(data)}x{len(data[0])} 행렬)"
    if image_tag:
        summary += f"\n\n{image_tag}"

    return {
        "success": True,
        "data": result,
        "summary": summary
    }


def _create_with_matplotlib(data, title, x_labels, y_labels, color_scale,
                            show_values, output_format, output_path, common):
    """matplotlib로 히트맵 생성"""
    import matplotlib.pyplot as plt
    import numpy as np

    common.setup_matplotlib_font()

    fig, ax = plt.subplots(figsize=(10, 8))

    # 색상맵 매핑
    cmap_map = {
        'viridis': 'viridis',
        'plasma': 'plasma',
        'inferno': 'inferno',
        'magma': 'magma',
        'blues': 'Blues',
        'reds': 'Reds',
        'greens': 'Greens'
    }
    cmap = cmap_map.get(color_scale.lower(), 'viridis')

    # 히트맵 그리기
    im = ax.imshow(data, cmap=cmap, aspect='auto')

    # 컬러바
    cbar = ax.figure.colorbar(im, ax=ax)

    # 레이블 설정
    if x_labels:
        ax.set_xticks(np.arange(len(x_labels)))
        ax.set_xticklabels(x_labels, rotation=45, ha='right')
    if y_labels:
        ax.set_yticks(np.arange(len(y_labels)))
        ax.set_yticklabels(y_labels)

    # 셀 값 표시
    if show_values:
        for i in range(len(data)):
            for j in range(len(data[0])):
                value = data[i][j]
                if value is not None:
                    # 배경색에 따라 텍스트 색상 조정
                    text_color = 'white' if value > (max(max(row) for row in data) / 2) else 'black'
                    ax.text(j, i, f'{value:.1f}' if isinstance(value, float) else str(value),
                           ha='center', va='center', color=text_color, fontsize=9)

    if title:
        ax.set_title(title, fontsize=14, fontweight='bold')

    plt.tight_layout()

    result = common.save_figure(fig, output_path, output_format)

    image_tag = result.get("image_tag", "")
    summary = f"히트맵 생성 완료 ({len(data)}x{len(data[0])} 행렬)"
    if image_tag:
        summary += f"\n\n{image_tag}"

    return {
        "success": True,
        "data": result,
        "summary": summary
    }
