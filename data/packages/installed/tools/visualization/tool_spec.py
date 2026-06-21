"""Plotly figure spec 직접 렌더.

그래픽 문법 전체(이중축·구간 음영·주석·로그축·subplot 등)를 선언형 JSON(data+layout)으로
받아 그대로 그린다. knob을 어휘로 하나씩 늘리는 대신(트레드밀) spec을 통과시킨다.
spec은 *코드가 아니라 데이터*라 포터블(plotly.js로 폰/웹 렌더)·캐시·0토큰 앱모드·검증 가능.

흔한 차트는 chart_type(line/bar/...)로, 표현이 풍부한 롱테일은 spec으로.
"""
import json
from pathlib import Path
import importlib.util

current_dir = Path(__file__).parent


def _load_common():
    spec = importlib.util.spec_from_file_location("tool_common", current_dir / "tool_common.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_spec(spec, title=None, output_format="png", output_path=None):
    """Plotly figure spec(dict 또는 JSON 문자열) → 차트 산출물.

    spec = {"data": [<trace>, ...], "layout": {...}}  (Plotly figure 구조)
    이중축: trace에 yaxis="y2" + layout.yaxis2={overlaying:"y", side:"right"}.
    구간 음영: layout.shapes=[{type:"rect", x0,x1, yref:"paper", y0:0,y1:1, fillcolor,...}].
    주석: layout.annotations=[{x, y, text, ...}].
    """
    common = _load_common()
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except Exception as e:
            return {"success": False, "error": f"spec JSON 파싱 실패: {e}. spec은 Plotly figure JSON이어야 합니다."}
    if not isinstance(spec, dict) or not isinstance(spec.get("data"), list):
        return {"success": False,
                "error": "spec은 Plotly figure JSON이어야 합니다: {\"data\":[...트레이스], \"layout\":{...}}."}

    try:
        import plotly.graph_objects as go
    except ImportError:
        return {"success": False, "error": "plotly가 필요합니다(spec 렌더). pip install plotly kaleido."}

    try:
        fig = go.Figure(spec)
        layout = spec.get("layout") or {}
        # 제목: 인자로 들어온 게 있고 spec에 없으면 보충
        if title and not layout.get("title"):
            fig.update_layout(title=dict(text=title, x=0.5))
        # 한글 폰트: spec이 지정 안 했을 때만 기본값 (spec 우선)
        if not layout.get("font"):
            fig.update_layout(font=dict(family='Apple SD Gothic Neo, Nanum Gothic, sans-serif'))
        if not layout.get("template"):
            fig.update_layout(template='plotly_white')

        result = common.save_plotly_figure(fig, output_path, output_format)
        image_tag = result.get("image_tag", "")
        summary = f"spec 차트 생성 완료 ({len(spec.get('data', []))}개 트레이스)"
        if image_tag:
            summary += f"\n\n{image_tag}"
        return {"success": True, "data": result, "summary": summary}
    except Exception as e:
        return {"success": False, "error": f"spec 렌더 실패: {e}"}
