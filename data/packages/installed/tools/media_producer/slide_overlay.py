"""통짜 이미지 슬라이드 위 결정론 텍스트 오버레이 합성.

이미지 모델을 부르지 않는다 — 현재 슬라이드 PNG를 전면 배경으로 깔고
Playwright(Chromium)가 글자만 얹어 같은 크기 PNG로 다시 찍는다.
그림 픽셀은 그대로, 비용은 렌더 1회(토큰 0).

호출자(lecture_workspace handler)가 원본 PNG({slide_id}.base.png)를 보존하고
오버레이 목록을 deck 메타에 들고 있다가 매번 원본에서 재합성한다 —
글자가 글자 위에 겹겹이 구워지는 사고를 원리적으로 막는 구조.
"""
import base64
import html as _html
import json
import os
import re

# 3×3 위치 어휘 → CSS 배치. (수평, 수직)
POSITIONS = {
    "top-left": ("left", "top"),
    "top": ("center", "top"),
    "top-right": ("right", "top"),
    "left": ("left", "middle"),
    "center": ("center", "middle"),
    "right": ("right", "middle"),
    "bottom-left": ("left", "bottom"),
    "bottom": ("center", "bottom"),
    "bottom-right": ("right", "bottom"),
}

SIZES = {"small": "2.0vw", "medium": "2.9vw", "large": "4.0vw"}
SIZE_VW = {"small": 2.0, "medium": 2.9, "large": 4.0}  # 키워드 → vw 수치 (자유 크기와 한 축)

# ★style="…" 큰따옴표 속성 안에 그대로 들어가는 문자열 — 폰트명 인용은 반드시 작은따옴표
#  (큰따옴표를 쓰면 속성이 조기 종료돼 위치 선언 전체가 유실된다 — 실측 버그)
_FONT_STACK = (
    "Pretendard, 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif"
)
_FONT_STACK_SERIF = (
    "'Noto Serif KR', 'Nanum Myeongjo', AppleMyungjo, Batang, serif"
)
# 서체 어휘 — 웹폰트는 Google Fonts CDN(기존 slide_styles/shadcn_design 선례,
# Playwright networkidle 이 로드 대기). 오프라인이면 시스템 스택으로 자연 폴백.
FONTS = {
    "sans": _FONT_STACK,                                        # 고딕 (기본)
    "serif": _FONT_STACK_SERIF,                                 # 명조
    "gowun": "'Gowun Batang', 'Noto Serif KR', serif",          # 고운바탕 (부드러운 바탕)
    "jua": "'Jua', 'Noto Sans KR', sans-serif",                 # 주아 (둥근 제목)
    "black": "'Black Han Sans', 'Noto Sans KR', sans-serif",    # 블랙한산스 (헤드라인)
    "pen": "'Nanum Pen Script', cursive",                       # 나눔 손글씨 펜
    "brush": "'Nanum Brush Script', cursive",                   # 나눔 붓글씨
}
FONT_LINK = (
    "https://fonts.googleapis.com/css2?"
    "family=Noto+Sans+KR:wght@400;600&family=Noto+Serif+KR:wght@400;600"
    "&family=Gowun+Batang:wght@400;700&family=Jua&family=Black+Han+Sans"
    "&family=Nanum+Pen+Script&family=Nanum+Brush+Script&display=swap"
)


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _size_vw_of(ov: dict) -> float:
    """오버레이 글자 크기(vw 수치) — size_vw(자유값) 우선, 없으면 키워드."""
    try:
        v = float(ov.get("size_vw") or 0)
        if 0.5 <= v <= 12:
            return v
    except (TypeError, ValueError):
        pass
    return SIZE_VW.get(ov.get("size") or "small", SIZE_VW["small"])


def _width_of(ov: dict):
    """글상자 폭(슬라이드 폭의 %, 5~100) — 주면 그 폭에서 자동 줄바꿈(2~3줄 만들기).

    없으면 None → 옛 기본값(max-width:70%)으로 그린다(기존 오버레이 무손상).
    """
    try:
        w = float(ov.get("width"))
    except (TypeError, ValueError):
        return None
    if not (5 <= w <= 100):
        return None
    return round(w, 2)


def _free_xy_of(ov: dict):
    """자유 좌표 (x, y — 박스 좌상단, 슬라이드 폭·높이의 %) 또는 None."""
    try:
        x, y = float(ov.get("x")), float(ov.get("y"))
    except (TypeError, ValueError):
        return None
    if not (-10 <= x <= 110 and -10 <= y <= 110):
        return None
    return (x, y)


def _overlay_css(ov: dict) -> str:
    """오버레이 1건의 위치·스타일 CSS 선언. x/y(자유 좌표)가 있으면 9방(position)보다 우선."""
    font_stack = FONTS.get(ov.get("font") or "sans", _FONT_STACK)
    weight = "400" if ov.get("weight") == "normal" else "600"
    box_w = _width_of(ov)
    decls = ["position:absolute",
             # 폭을 정하면 그 안에서 줄바꿈, 안 정하면 옛 기본(내용 폭, 70% 상한)
             (f"width:{box_w}%" if box_w is not None else "max-width:70%"),
             "white-space:pre-line", "overflow-wrap:break-word",
             "line-height:1.35", f"font-weight:{weight}",
             f"font-family:{font_stack}",
             f"font-size:{_size_vw_of(ov)}vw"]
    xy = _free_xy_of(ov)
    if xy is not None:
        # 자유 배치 — 드래그 편집기가 놓은 좌상단 그대로 (변환 없음, 좌측 정렬)
        decls += [f"left:{xy[0]}%", f"top:{xy[1]}%", "text-align:left"]
    else:
        h, v = POSITIONS.get(ov.get("position") or "bottom-right", POSITIONS["bottom-right"])
        margin = "3.2%"
        if h == "left":
            decls += [f"left:{margin}", "text-align:left"]
        elif h == "right":
            decls += [f"right:{margin}", "text-align:right"]
        else:
            decls += ["left:50%", "text-align:center"]
        vmargin = "4.5%"
        if v == "top":
            decls.append(f"top:{vmargin}")
        elif v == "bottom":
            decls.append(f"bottom:{vmargin}")
        else:
            decls.append("top:50%")
        # 가운데 정렬 transform (양축 조합)
        tx = "-50%" if h == "center" else "0"
        ty = "-50%" if v == "middle" else "0"
        if tx != "0" or ty != "0":
            decls.append(f"transform:translate({tx},{ty})")

    color = (ov.get("color") or "white").strip()
    if not re.fullmatch(r"white|black|#[0-9a-fA-F]{3,8}", color):
        color = "white"  # style 속성에 그대로 들어가는 값 — 어휘 밖이면 기본색
    dark_text = color in ("black", "#000", "#000000", "#111", "#111111")
    if color == "white":
        color = "#ffffff"
    elif color == "black":
        color = "#111111"
    if ov.get("chip"):
        bg = "rgba(255,255,255,.78)" if dark_text else "rgba(12,12,14,.58)"
        decls += [f"color:{color}", f"background:{bg}",
                  "padding:.45em .9em", "border-radius:.45em",
                  "backdrop-filter:blur(2px)"]
    elif ov.get("shadow"):
        # 그림자=선택 사항 (기본 없음 — 그림 속 다른 글자와 이질감을 만들던 효과)
        shadow = (
            "0 1px 3px rgba(255,255,255,.65), 0 0 14px rgba(255,255,255,.45)"
            if dark_text
            else "0 1px 3px rgba(0,0,0,.6), 0 0 14px rgba(0,0,0,.45)"
        )
        decls += [f"color:{color}", f"text-shadow:{shadow}"]
    else:
        decls.append(f"color:{color}")
    return ";".join(decls)


def _build_html(base_png_path: str, overlays: list, width: int, height: int) -> str:
    divs = []
    for ov in overlays:
        text = _html.escape(str(ov.get("text") or "")).strip()
        if not text:
            continue
        divs.append(f'<div style="{_overlay_css(ov)}">{text}</div>')
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="{FONT_LINK}" rel="stylesheet">
<style>
html,body{{margin:0;padding:0}}
#stage{{position:relative;width:{width}px;height:{height}px;overflow:hidden}}
#stage>img{{position:absolute;inset:0;width:100%;height:100%}}
</style></head><body>
<div id="stage"><img src="data:image/png;base64,{_b64(base_png_path)}">{''.join(divs)}</div>
</body></html>"""


def compose(base_png_path: str, overlays: list, out_path: str) -> str:
    """원본 PNG + 오버레이 목록 → out_path 에 같은 크기 합성 PNG.

    base 를 메모리로 읽은 뒤 찍으므로 out_path == base_png_path 여도 안전.
    반환은 JSON 문자열 {success, image_path, width, height}.
    """
    if not os.path.exists(base_png_path):
        return json.dumps({"success": False, "error": f"원본 이미지 없음: {base_png_path}"},
                          ensure_ascii=False)
    try:
        from PIL import Image
        with Image.open(base_png_path) as im:
            width, height = im.size
    except Exception as e:
        return json.dumps({"success": False, "error": f"이미지 크기 판독 실패: {e}"},
                          ensure_ascii=False)

    html_doc = _build_html(base_png_path, overlays, width, height)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": width, "height": height},
                            device_scale_factor=1)
            pg.set_content(html_doc, wait_until="networkidle")
            # 웹폰트 완주 대기 (오프라인이면 즉시 resolve → 시스템 폴백으로 진행)
            try:
                pg.evaluate("() => document.fonts.ready.then(() => true)")
            except Exception:
                pass
            pg.wait_for_timeout(150)
            pg.screenshot(path=out_path, clip={"x": 0, "y": 0,
                                               "width": width, "height": height})
            b.close()
    except Exception as e:
        return json.dumps({"success": False, "error": f"오버레이 합성 실패: {e}"},
                          ensure_ascii=False)
    return json.dumps({"success": True, "image_path": out_path,
                       "width": width, "height": height}, ensure_ascii=False)
