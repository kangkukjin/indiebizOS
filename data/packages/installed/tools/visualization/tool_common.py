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
        if not output_path:
            output_path = generate_output_path("chart", "png")
        else:
            # output_path가 디렉토리면 그 안에 파일 생성
            if os.path.isdir(output_path):
                from datetime import datetime as dt
                timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
                output_path = os.path.join(output_path, f"chart_{timestamp}.png")
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        # 절대 경로로 변환하여 반환 (에이전트 간 경로 혼동 방지)
        abs_path = os.path.abspath(output_path)
        return {"format": "png", "path": abs_path, "image_tag": f"[IMAGE:{abs_path}]"}

    else:
        plt.close(fig)
        return {"format": output_format, "error": f"지원하지 않는 형식: {output_format}"}


def save_plotly_figure(fig, output_path: str = None, output_format: str = "png"):
    """Plotly figure 저장"""
    if output_format == "html":
        if not output_path:
            output_path = generate_output_path("chart", "html")
        else:
            if os.path.isdir(output_path):
                from datetime import datetime as dt
                timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
                output_path = os.path.join(output_path, f"chart_{timestamp}.html")
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.write_html(output_path)
        # 절대 경로로 변환하여 반환 (에이전트 간 경로 혼동 방지)
        return {"format": "html", "path": os.path.abspath(output_path)}

    elif output_format == "base64":
        img_bytes = fig.to_image(format="png", scale=2)
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return {"format": "base64", "data": img_base64, "mime_type": "image/png"}

    elif output_format == "png":
        if not output_path:
            output_path = generate_output_path("chart", "png")
        else:
            if os.path.isdir(output_path):
                from datetime import datetime as dt
                timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
                output_path = os.path.join(output_path, f"chart_{timestamp}.png")
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.write_image(output_path, scale=2)
        # 절대 경로로 변환하여 반환 (에이전트 간 경로 혼동 방지)
        abs_path = os.path.abspath(output_path)
        return {"format": "png", "path": abs_path, "image_tag": f"[IMAGE:{abs_path}]"}

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


# ───────── 구간 음영(band) · 이벤트 표시(annotation) 공통 (line/scatter/bar 공유) ─────────

# 옅은 색 순환 (plotly rgba / matplotlib hex)
BAND_COLORS = [
    "rgba(31,119,180,0.10)", "rgba(255,127,14,0.10)", "rgba(44,160,44,0.10)",
    "rgba(214,39,40,0.10)", "rgba(148,103,189,0.10)", "rgba(140,86,75,0.10)",
    "rgba(227,119,194,0.10)", "rgba(127,127,127,0.10)",
]
BAND_COLORS_MPL = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
]


def num(v):
    """숫자/숫자형 문자열이면 float, 아니면 None."""
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def coerce_x(x_values):
    """x 값 전체가 숫자형이면 숫자 리스트로 변환(연도 등) → band/annotation이 선과 같은 좌표계.
    하나라도 숫자가 아니면 원본 그대로(범주축). 반환 (values, is_numeric)."""
    nums = [num(v) for v in x_values]
    if x_values and all(n is not None for n in nums):
        return [int(n) if n == int(n) else n for n in nums], True
    return list(x_values), False


def band_bounds(band):
    """band dict → (from, to, label, color). from/to=start/end/x0/x1, label=name/text 별칭."""
    x0 = band.get("from", band.get("start", band.get("x0")))
    x1 = band.get("to", band.get("end", band.get("x1")))
    label = band.get("label") or band.get("name") or band.get("text")
    return x0, x1, label, band.get("color")


def anno_point(anno):
    """annotation dict → (x, text). text=label 별칭."""
    return anno.get("x"), (anno.get("text") or anno.get("label") or "")


def apply_bands_plotly(fig, bands, annotations, x_numeric):
    """plotly figure에 구간 음영(add_vrect)·이벤트선(add_vline) 적용.
    x_numeric면 좌표를 숫자로 변환, 아니면(범주축) 원 라벨 그대로. 개별 실패는 건너뜀."""
    for i, band in enumerate(bands or []):
        if not isinstance(band, dict):
            continue
        x0, x1, label, color = band_bounds(band)
        if x0 is None or x1 is None:
            continue
        if x_numeric:
            x0 = num(x0) if num(x0) is not None else x0
            x1 = num(x1) if num(x1) is not None else x1
        try:
            fig.add_vrect(x0=x0, x1=x1, layer="below", line_width=0,
                          fillcolor=color or BAND_COLORS[i % len(BAND_COLORS)],
                          annotation_text=label or "", annotation_position="top left",
                          annotation=dict(font_size=11))
        except Exception:
            continue
    for anno in (annotations or []):
        if not isinstance(anno, dict):
            continue
        x, text = anno_point(anno)
        if x is None:
            continue
        if x_numeric and num(x) is not None:
            x = num(x)
        try:
            fig.add_vline(x=x, line_width=1, line_dash="dot", line_color="gray",
                          annotation_text=text, annotation_position="top",
                          annotation=dict(font_size=10))
        except Exception:
            continue


def apply_bands_mpl(ax, bands, annotations, x_values, x_numeric):
    """matplotlib ax에 구간 음영(axvspan)·이벤트선(axvline) 적용.
    x_numeric면 숫자 좌표, 아니면(범주/막대축) x_values 내 위치(index)로 매핑."""
    def _xpos(v):
        if x_numeric:
            return num(v)
        try:
            return list(x_values).index(v)
        except (ValueError, AttributeError):
            try:
                return [str(x) for x in x_values].index(str(v))
            except ValueError:
                return None

    ymax = ax.get_ylim()[1]
    for i, band in enumerate(bands or []):
        if not isinstance(band, dict):
            continue
        x0, x1, label, color = band_bounds(band)
        p0, p1 = _xpos(x0), _xpos(x1)
        if p0 is None or p1 is None:
            continue
        ax.axvspan(p0, p1, alpha=0.12, color=color or BAND_COLORS_MPL[i % len(BAND_COLORS_MPL)])
        if label:
            ax.text((p0 + p1) / 2, ymax, str(label), ha='center', va='bottom',
                    fontsize=9, clip_on=False)
    for anno in (annotations or []):
        if not isinstance(anno, dict):
            continue
        x, text = anno_point(anno)
        p = _xpos(x)
        if p is None:
            continue
        ax.axvline(p, ls=':', c='gray', lw=1)
        if text:
            ax.text(p, ymax, str(text), rotation=90, ha='right', va='top', fontsize=8, color='gray')


def apply_bands_plotly_indexed(fig, bands, annotations, labels):
    """범주축(막대) 전용 — 라벨→index 매핑 후 숫자 좌표로 shape를 그린다.
    막대를 x=index(0..n-1)로 그린 경우에 호출(범주축에 문자열 좌표 shape가 불안정한 문제 회피)."""
    idx = {str(l): i for i, l in enumerate(labels)}

    def pos(v):
        if v is None:
            return None
        if str(v) in idx:
            return idx[str(v)]
        n = num(v)
        return n if (n is not None and 0 <= n < len(labels)) else None

    for i, band in enumerate(bands or []):
        if not isinstance(band, dict):
            continue
        x0, x1, label, color = band_bounds(band)
        p0, p1 = pos(x0), pos(x1)
        if p0 is None or p1 is None:
            continue
        try:
            fig.add_vrect(x0=p0 - 0.5, x1=p1 + 0.5, layer="below", line_width=0,
                          fillcolor=color or BAND_COLORS[i % len(BAND_COLORS)],
                          annotation_text=label or "", annotation_position="top left",
                          annotation=dict(font_size=11))
        except Exception:
            continue
    for anno in (annotations or []):
        if not isinstance(anno, dict):
            continue
        x, text = anno_point(anno)
        p = pos(x)
        if p is None:
            continue
        try:
            fig.add_vline(x=p, line_width=1, line_dash="dot", line_color="gray",
                          annotation_text=text, annotation_position="top",
                          annotation=dict(font_size=10))
        except Exception:
            continue
