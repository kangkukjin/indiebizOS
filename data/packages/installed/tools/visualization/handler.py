"""
Visualization Tools Handler
범용 데이터 시각화 도구 패키지
"""
import json
import os
from pathlib import Path

current_dir = Path(__file__).parent


import sys

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend"))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
from common.pkg_utils import load_sibling

def load_module(module_name):
    """같은 디렉토리의 형제 모듈 로드 — 정본은 common.pkg_utils.load_sibling (감사 ⑥)"""
    return load_sibling(__file__, module_name)


def get_definitions():
    """tool.json에서 도구 정의 반환"""
    tool_json_path = current_dir / "tool.json"
    with open(tool_json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _resolve_data_file(data_file: str, context) -> str:
    """data_file 상대경로를 context.project_path 기준 절대경로로 변환. 절대경로는 그대로."""
    if not data_file:
        return None
    if Path(data_file).is_absolute():
        return data_file
    resolved = context.resolve_path(data_file)
    if os.path.exists(resolved):
        return resolved
    return data_file  # 그대로 반환 (에러는 도구에서 처리)


def _extract_table_from_prev(prev):
    """>> 파이프로 들어온 이전 액션 결과에서 표준 table 통화를 추출 (있으면).

    prev는 문자열(JSON) 또는 dict. {table:{columns,rows}} 형태면 그 table 반환.
    """
    if not prev:
        return None
    obj = prev
    if isinstance(prev, str):
        try:
            obj = json.loads(prev)
        except Exception:
            return None
    if isinstance(obj, dict):
        t = obj.get("table")
        if isinstance(t, dict) and t.get("rows"):
            return t
        # 단일 통화 items(행 dict) → table 재구성: 첫 dict의 키 순서=열(첫 열=x축 라벨, 나머지=수치 시리즈).
        items = obj.get("items")
        if isinstance(items, list) and items and all(isinstance(x, dict) for x in items):
            cols = list(items[0].keys())
            return {"columns": cols, "rows": [[d.get(c) for c in cols] for d in items]}
    return None


def _extract_ohlc_from_prev(prev):
    """>> 파이프 이전 결과에서 OHLC 리스트(캔들스틱용)를 제네릭 추출.
    table 통화(종가만)는 캔들스틱을 못 담으므로, open/high/low/close 키를 가진 dict 리스트를
    찾는다(stock history의 prices 등). 통화 필드를 늘리지 않고 기존 데이터를 인식만."""
    if not prev:
        return None
    obj = prev
    if isinstance(prev, str):
        try:
            obj = json.loads(prev)
        except Exception:
            return None

    def _is_ohlc_list(v):
        return (isinstance(v, list) and v and isinstance(v[0], dict)
                and all(k in v[0] for k in ("open", "high", "low", "close")))

    # 최상위 + 한 단계 깊이(data/prices 등 흔한 중첩)에서 탐색
    stack = [obj]
    if isinstance(obj, dict):
        stack += [v for v in obj.values() if isinstance(v, (dict, list))]
        for v in obj.values():
            if isinstance(v, dict):
                stack += list(v.values())
    for v in stack:
        if _is_ohlc_list(v):
            return v
    return None


def _diagnose_no_data(tool_input: dict, chart_type: str):
    """차트 입력이 비었을 때 '왜' 비었는지 가른다 (29회차 B29-1).

    "입력이 아예 없다"와 "통화는 왔는데 그릴 축이 없다"는 다른 사건이다. 뒤엣것을
    앞엣것으로 보고하면 사용자는 자기가 주지도 않은 data/data_file 을 찾아 헤맨다.
    세 상태를 구별한다 — ①통화 미도착(판단 불가 → None, 기존 경로에 맡김)
    ②도착했으나 0행 ③행은 있으나 이 차트가 쓸 축/값이 없음.
    """
    _t = tool_input.get("table")
    if not isinstance(_t, dict):
        _t = _extract_table_from_prev(tool_input.get("_prev_result"))
    if not isinstance(_t, dict):
        # _extract_table_from_prev 는 *그릴 수 있는* 표만 만들어 주므로 빈 items 를 먼저
        # 버린다 — 그래서 "0행이 도착했다"는 사실이 여기까지 오지 못했다. 통화가 왔다는
        # 사실 자체는 봉투를 직접 봐야 안다(0행도 엄연히 도착한 통화다).
        _prev = tool_input.get("_prev_result")
        if isinstance(_prev, str):
            try:
                _prev = json.loads(_prev)
            except Exception:
                _prev = None
        if isinstance(_prev, dict) and isinstance(_prev.get("items"), list):
            _t = {"columns": [], "rows": []}
        else:
            return None
    cols = list(_t.get("columns") or [])
    rows = list(_t.get("rows") or [])
    if not rows:
        return {"success": False, "rows_in": 0, "columns": cols,
                "error": ("입력 0행 — 그릴 내용이 없습니다. [table:chart] 는 앞 단계 통화를 "
                          "받았지만 행이 하나도 없습니다"
                          + (f"(열: {cols})" if cols else "")
                          + ". 앞 단계의 필터·검침을 보세요.")}
    if chart_type == "candlestick":
        return {"success": False, "rows_in": len(rows), "columns": cols,
                "error": (f"입력 {len(rows)}행이 왔지만 캔들스틱이 쓸 open/high/low/close 열을 "
                          f"찾지 못했습니다. 현재 열: {cols}.")}
    if len(cols) < 2:
        return {"success": False, "rows_in": len(rows), "columns": cols,
                "error": (f"입력 {len(rows)}행이 왔지만 값 열이 없습니다 — 첫 열은 x축/라벨이라 "
                          f"최소 2열이 필요합니다. 현재 열: {cols}. 값 열을 함께 남기세요 "
                          "(예: [table:select]{columns: [\"라벨열\", \"값열\"]}).")}
    return {"success": False, "rows_in": len(rows), "columns": cols,
            "error": (f"입력 {len(rows)}행·열 {cols} 이 왔지만 '{chart_type}' 차트가 쓸 수 있는 "
                      "값을 한 칸도 못 찾았습니다(값 칸이 비었거나 숫자가 아님).")}


def _table_to_chart_data(table: dict, chart_type: str) -> dict:
    """표준 테이블 통화 → 차트 입력 변환.

    통화: {"columns": ["연도","GDP","인구"], "rows": [["2020",1.6,51],["2021",1.8,51.2]]}
      - 첫 열 = x축/범주, 나머지 열 = 각 시리즈(열 머리글 = 시리즈 이름).
    반환: {"data", "series_names"?, "x_label"?, "y_label"?}.
    """
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    if not rows:
        return {}
    out: dict = {}
    if chart_type == "heatmap":
        # 표=행렬: 첫 열=행 라벨(y), 나머지 열 머리글=열 라벨(x), 값=2D 행렬
        out["data"] = [[v for v in r[1:]] for r in rows]
        out["y_labels"] = [str(r[0]) for r in rows]
        if len(cols) > 1:
            out["x_labels"] = [str(c) for c in cols[1:]]
        return out
    if chart_type in ("pie", "bar"):
        # 첫 열=라벨, 두번째 열=값 (단일 시리즈)
        out["data"] = [{"label": str(r[0]), "value": r[1]} for r in rows if len(r) > 1]
        if len(cols) > 1:
            out["y_label"] = cols[1]
    else:  # line/scatter — 다중 시리즈 지원 ({x, s1, s2} 행 dict, x외 키=시리즈)
        xkey = str(cols[0]) if cols else "x"
        vcols = [str(c) for c in cols[1:]] if len(cols) > 1 else ["y"]
        data = []
        for r in rows:
            d = {xkey: r[0]}
            for i, vc in enumerate(vcols):
                d[vc] = r[i + 1] if (i + 1) < len(r) else None
            data.append(d)
        out["data"] = data
        out["series_names"] = vcols
        if cols:
            out["x_label"] = str(cols[0])
    return out


# --- chart_type 별 렌더러 (각각 모듈 로드 + 직접 호출·return) ---
# 2026-07-02: 옛 `tool_name = type_map[chart_type]` 재할당+fall-through(변종2)를
# chart_type → 렌더러 함수 직접-return(변종1)으로 전환. 레거시 내부 tool명(line_chart 등)은
# 더 이상 tool_name으로 부활하지 않으므로 tool.json에서도 은퇴 — chart 하나만 IBL 진입점.

def _render_line(tool_input, data_file):
    tool = load_module("tool_line")
    return tool.create_line_chart(
        data=tool_input.get("data"),
        data_file=data_file,
        title=tool_input.get("title"),
        x_label=tool_input.get("x_label"),
        y_label=tool_input.get("y_label"),
        series_names=tool_input.get("series_names"),
        bands=tool_input.get("bands"),
        annotations=tool_input.get("annotations"),
        output_format=tool_input.get("output_format", "png"),
        output_path=tool_input.get("output_path"))


def _render_bar(tool_input, data_file):
    tool = load_module("tool_bar")
    return tool.create_bar_chart(
        data=tool_input.get("data"),
        data_file=data_file,
        title=tool_input.get("title"),
        x_label=tool_input.get("x_label"),
        y_label=tool_input.get("y_label"),
        series_names=tool_input.get("series_names"),
        horizontal=tool_input.get("horizontal", False),
        stacked=tool_input.get("stacked", False),
        bands=tool_input.get("bands"),
        annotations=tool_input.get("annotations"),
        output_format=tool_input.get("output_format", "png"),
        output_path=tool_input.get("output_path"))


def _render_candlestick(tool_input, data_file):
    tool = load_module("tool_candlestick")
    return tool.create_candlestick_chart(
        data=tool_input.get("data"),
        data_file=data_file,
        title=tool_input.get("title"),
        show_volume=tool_input.get("show_volume", True),
        ma_periods=tool_input.get("ma_periods"),
        output_format=tool_input.get("output_format", "png"),
        output_path=tool_input.get("output_path"))


def _render_pie(tool_input, data_file):
    tool = load_module("tool_pie")
    return tool.create_pie_chart(
        data=tool_input.get("data"),
        title=tool_input.get("title"),
        show_percentage=tool_input.get("show_percentage", True),
        donut=tool_input.get("donut", False),
        output_format=tool_input.get("output_format", "png"),
        output_path=tool_input.get("output_path"))


def _render_scatter(tool_input, data_file):
    tool = load_module("tool_scatter")
    return tool.create_scatter_plot(
        data=tool_input.get("data"),
        data_file=data_file,
        title=tool_input.get("title"),
        x_label=tool_input.get("x_label"),
        y_label=tool_input.get("y_label"),
        show_trendline=tool_input.get("show_trendline", False),
        bands=tool_input.get("bands"),
        annotations=tool_input.get("annotations"),
        output_format=tool_input.get("output_format", "png"),
        output_path=tool_input.get("output_path"))


def _render_heatmap(tool_input, data_file):
    tool = load_module("tool_heatmap")
    return tool.create_heatmap(
        data=tool_input.get("data"),
        title=tool_input.get("title"),
        x_labels=tool_input.get("x_labels"),
        y_labels=tool_input.get("y_labels"),
        color_scale=tool_input.get("color_scale", "viridis"),
        show_values=tool_input.get("show_values", True),
        output_format=tool_input.get("output_format", "png"),
        output_path=tool_input.get("output_path"))


def _render_multi(tool_input, data_file):
    tool = load_module("tool_multi")
    return tool.create_multi_chart(
        charts=tool_input.get("charts"),
        title=tool_input.get("title"),
        layout=tool_input.get("layout", "auto"),
        output_format=tool_input.get("output_format", "png"),
        output_path=tool_input.get("output_path"))


# chart_type → 렌더러. 미지의 chart_type 은 line 으로 폴백(옛 type_map.get 기본값 보존).
_RENDERERS = {
    "line": _render_line,
    "bar": _render_bar,
    "pie": _render_pie,
    "scatter": _render_scatter,
    "heatmap": _render_heatmap,
    "multi": _render_multi,
    "candlestick": _render_candlestick,
}


def execute(tool_input: dict, context):
    """도구 실행 진입점 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name

    # data_file 경로 해석
    data_file = _resolve_data_file(tool_input.get("data_file"), context)

    # 산출 경로 — 형제 emitter 와 같은 해소기 하나를 쓴다 (ToolContext.resolve_output_path,
    # 2026-08-23 J29-1). 옛 코드는 여기서 basename() 으로 디렉토리를 **말없이** 버려
    # spreadsheet(경로 존중)·document(버리되 고지)와 셋이 다 달랐다. 이제 규약은 하나 —
    # "준 경로는 지킨다, bare 파일명만 outputs/ 로".
    # (낱말 `path` 는 ibl_actions.yaml 의 aliases 로 여기 닿기 전에 output_path 로
    #  정규화된다 — 어휘는 데이터에 산다. 29회차 F29-1)
    output_base = context.output_dir()
    raw_output = tool_input.get("output_path")
    if raw_output:
        _res = context.resolve_output_path(raw_output)
        if _res.get("error"):
            return json.dumps({"success": False, "error": _res["error"]}, ensure_ascii=False)
        tool_input["output_path"] = _res["path"]
    else:
        # output_path 미지정 시 프로젝트 outputs 폴더 사용 (하위 렌더러가 이름을 짓는다)
        tool_input["output_path"] = output_base

    try:
        # 범용 chart 액션: chart_type으로 분기
        if tool_name == "chart":
            # spec 통과 — Plotly figure JSON(data+layout)이 오면 그래픽 문법 전체를 그대로 렌더.
            # 이중축·로그축·복합 음영 등 chart_type knob으로 안 되는 롱테일을 *선언형 데이터*로 흡수
            # (matplotlib 코드 이탈 대체 — 포터블·캐시·검증가능). 흔한 차트는 아래 chart_type 경로.
            _spec = tool_input.get("spec")
            if _spec:
                tool = load_module("tool_spec")
                return tool.render_spec(
                    _spec, title=tool_input.get("title"),
                    output_format=tool_input.get("output_format", "png"),
                    output_path=tool_input.get("output_path"))
            chart_type = tool_input.get("chart_type", "line")
            # (아래 통화/데이터 정규화 후, chart_type → 렌더러 함수 직접-return)
            # 모델이 table 통화를 data: 키에 {columns,rows} 로 넣는 흔한 실수 → table 로 인식.
            # (안 그러면 하위 렌더러가 dict 를 행 리스트로 오인 → KeyError(0)='도구 실행 중 오류 발생: 0')
            _maybe = tool_input.get("data")
            if isinstance(_maybe, dict) and _maybe.get("rows") and _maybe.get("columns"):
                tool_input["table"] = _maybe
                tool_input["data"] = None
            # 캔들스틱: table 통화(종가만)로 불가 → _prev_result에서 OHLC 리스트 제네릭 수용
            # (stock history prices 등 open/high/low/close 보유 리스트). 통화 필드 안 늘림.
            if chart_type == "candlestick" and not tool_input.get("data"):
                _ohlc = _extract_ohlc_from_prev(tool_input.get("_prev_result"))
                if _ohlc:
                    tool_input["data"] = _ohlc
            # >> 파이프: 이전 액션 결과(_prev_result)에 table 통화가 있으면 자동 수용
            # → [sense:world_bank]{...} >> [table:chart]{title,chart_type} 가 무reshape로 흐름.
            if not tool_input.get("table") and not tool_input.get("data"):
                _pt = _extract_table_from_prev(tool_input.get("_prev_result"))
                if _pt:
                    tool_input["table"] = _pt
            # 표준 테이블 통화(table currency) → 차트 입력. 데이터 소스가 공유 통화를
            # 그대로 흘려보내면 손으로 reshape 없이 차트가 됨 (sense:* >> table:chart).
            _table = tool_input.get("table")
            if isinstance(_table, dict) and _table.get("rows") and not tool_input.get("data"):
                _conv = _table_to_chart_data(_table, chart_type)
                if _conv.get("data") is not None:
                    tool_input["data"] = _conv["data"]
                for _k in ("series_names", "x_label", "y_label", "x_labels", "y_labels"):
                    if _conv.get(_k) and not tool_input.get(_k):
                        tool_input[_k] = _conv[_k]
            # flat data + labels 정규화: 코퍼스/사용자는 data:[10,20,30] + labels:[...]로 쓰나
            # 차트 도구는 dict 리스트를 기대 → 종류별 키로 변환 (pie/bar={label,value}, line/scatter={x,y}).
            _d = tool_input.get("data")
            if isinstance(_d, list) and _d and not isinstance(_d[0], dict):
                _labels = tool_input.get("labels") or [str(i + 1) for i in range(len(_d))]
                if chart_type in ("pie", "bar"):
                    tool_input["data"] = [{"label": l, "value": v} for l, v in zip(_labels, _d)]
                elif chart_type in ("line", "scatter"):
                    tool_input["data"] = [{"x": l, "y": v} for l, v in zip(_labels, _d)]
            # 입력 진단 정직화 (29회차 B29-1) — 렌더러에 넘기면 공용 로더가
            # "데이터가 비어있습니다. data 또는 data_file을 제공하세요" 하나로 뭉갠다.
            if not tool_input.get("data") and not data_file:
                _diag = _diagnose_no_data(tool_input, chart_type)
                if _diag:
                    return _diag
            renderer = _RENDERERS.get(chart_type, _render_line)
            return renderer(tool_input, data_file)

        else:
            return {
                "success": False,
                "error": f"알 수 없는 도구입니다: {tool_name}"
            }

    except ImportError as e:
        return {
            "success": False,
            "error": f"필요한 라이브러리가 설치되지 않았습니다: {str(e)}. pip install matplotlib plotly 실행이 필요합니다."
        }
    except FileNotFoundError as e:
        return {
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"도구 실행 중 오류 발생: {str(e)}"
        }
