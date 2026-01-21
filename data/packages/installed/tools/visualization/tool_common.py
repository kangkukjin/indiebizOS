"""
시각화 공통 유틸리티
"""
import os
import json
import base64
from pathlib import Path
from datetime import datetime

MAX_POINTS = 300  # 최대 데이터 포인트 수


def load_data_from_file(file_path: str) -> list:
    """파일에서 데이터 로드 (JSON/CSV)"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    suffix = path.suffix.lower()

    if suffix == '.json':
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    elif suffix == '.csv':
        import csv
        data = []
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                converted = {}
                for k, v in row.items():
                    try:
                        converted[k] = float(v) if '.' in v else int(v)
                    except (ValueError, TypeError):
                        converted[k] = v
                data.append(converted)
        return data
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {suffix}")


def sample_data(data: list, max_points: int = MAX_POINTS) -> tuple:
    """
    데이터 샘플링 - 일정 간격으로 추출하되 처음과 끝은 유지

    Returns:
        (sampled_data, original_count, was_sampled)
    """
    original_count = len(data)
    if original_count <= max_points:
        return data, original_count, False

    step = (original_count - 1) / (max_points - 1)
    indices = [int(i * step) for i in range(max_points - 1)]
    indices.append(original_count - 1)
    indices = sorted(set(indices))

    return [data[i] for i in indices], original_count, True


def load_and_sample(data: list = None, data_file: str = None, max_points: int = MAX_POINTS) -> tuple:
    """
    데이터 로드 및 샘플링 통합 함수

    Returns:
        (data, original_count, was_sampled, error_message)
    """
    if data_file:
        try:
            data = load_data_from_file(data_file)
        except Exception as e:
            return None, 0, False, f"파일 로드 실패: {e}"

    if not data:
        return None, 0, False, "데이터가 비어있습니다. data 또는 data_file을 제공하세요."

    sampled_data, original_count, was_sampled = sample_data(data, max_points)
    return sampled_data, original_count, was_sampled, None

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
        return {"format": "png", "path": output_path, "image_tag": f"[IMAGE:{output_path}]"}

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
        return {"format": "png", "path": output_path, "image_tag": f"[IMAGE:{output_path}]"}

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
