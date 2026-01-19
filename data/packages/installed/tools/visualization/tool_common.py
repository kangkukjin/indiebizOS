"""
시각화 공통 유틸리티
"""
import os
import base64
from pathlib import Path
from datetime import datetime

# 기본 출력 경로 (indiebizOS/data/outputs/charts)
def _get_output_dir():
    """출력 디렉토리 경로 반환"""
    # 패키지 위치에서 data 폴더 찾기
    # tool_common.py -> visualization -> tools -> installed -> packages -> data
    current = Path(__file__).resolve()

    # indiebizOS의 data 폴더 찾기
    for parent in current.parents:
        if parent.name == "data" and (parent / "packages").exists():
            return parent / "outputs" / "charts"

    # 못 찾으면 사용자 홈 디렉토리에 생성
    return Path.home() / "indiebizOS_outputs" / "charts"

DEFAULT_OUTPUT_DIR = _get_output_dir()

# 한글 폰트 설정
def setup_matplotlib_font():
    """matplotlib 한글 폰트 설정"""
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    # macOS 한글 폰트
    font_paths = [
        '/System/Library/Fonts/AppleSDGothicNeo.ttc',
        '/System/Library/Fonts/Supplemental/AppleGothic.ttf',
        '/Library/Fonts/NanumGothic.ttf',
        '/Library/Fonts/NanumGothic.otf',
    ]

    font_found = False
    for font_path in font_paths:
        if os.path.exists(font_path):
            font_prop = fm.FontProperties(fname=font_path)
            plt.rcParams['font.family'] = font_prop.get_name()
            font_found = True
            break

    if not font_found:
        # 기본 sans-serif 사용
        plt.rcParams['font.family'] = 'sans-serif'

    # 마이너스 기호 깨짐 방지
    plt.rcParams['axes.unicode_minus'] = False


def generate_output_path(prefix: str = "chart", ext: str = "png") -> str:
    """출력 파일 경로 생성"""
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(DEFAULT_OUTPUT_DIR / f"{prefix}_{timestamp}.{ext}")




def save_figure(fig, output_path: str = None, output_format: str = "png"):
    """
    matplotlib figure 저장

    Args:
        fig: matplotlib figure 객체
        output_path: 저장 경로
        output_format: png, html, base64

    Returns:
        dict: 결과 정보
    """
    import matplotlib.pyplot as plt

    if output_format == "base64":
        import io
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)
        return {
            "format": "base64",
            "data": img_base64,
            "mime_type": "image/png"
        }

    elif output_format == "png":
        # 항상 기본 디렉토리에 저장
        output_path = generate_output_path("chart", "png")
        fig.savefig(output_path, dpi=150, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        return {"format": "png", "path": output_path}

    else:
        plt.close(fig)
        return {"format": output_format, "error": f"지원하지 않는 형식: {output_format}"}


def save_plotly_figure(fig, output_path: str = None, output_format: str = "png"):
    """Plotly figure 저장"""
    if output_format == "html":
        output_path = generate_output_path("chart", "html")
        fig.write_html(output_path)
        return {"format": "html", "path": output_path}

    elif output_format == "base64":
        img_bytes = fig.to_image(format="png", scale=2)
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return {"format": "base64", "data": img_base64, "mime_type": "image/png"}

    elif output_format == "png":
        output_path = generate_output_path("chart", "png")
        fig.write_image(output_path, scale=2)
        return {"format": "png", "path": output_path}

    else:
        return {"format": output_format, "error": f"지원하지 않는 형식: {output_format}"}


# 기본 색상 팔레트
COLORS = [
    '#2E86AB',  # 파랑
    '#A23B72',  # 자주
    '#F18F01',  # 주황
    '#C73E1D',  # 빨강
    '#3B1F2B',  # 짙은 보라
    '#95C623',  # 연두
    '#5C4D7D',  # 보라
    '#E84855',  # 분홍빨강
    '#2D3047',  # 남색
    '#93B7BE',  # 청회색
]

# 상승/하락 색상
UP_COLOR = '#E84855'    # 빨강 (상승)
DOWN_COLOR = '#2E86AB'  # 파랑 (하락)

# Plotly 템플릿 설정
PLOTLY_TEMPLATE = {
    'layout': {
        'font': {'family': 'Apple SD Gothic Neo, Nanum Gothic, sans-serif'},
        'paper_bgcolor': 'white',
        'plot_bgcolor': 'white',
        'colorway': COLORS,
    }
}
