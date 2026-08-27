"""[engines:render] 구현 — 자기 투영법을 가진 시각 형식의 결정론적 픽셀화.

지각 기관의 헌법: 여기엔 **판단이 없다**. HTML/PDF/SVG 처럼 "어떻게 픽셀이 되는가"가
형식 명세에 이미 정의된 것만 받는다(결정론적 투영). 시각 형태가 내재하지 않은 데이터
(CSV·표)를 그림으로 만드는 것은 표현 판단이 들어가는 생성 행위 — 이 낱말 밖이다.
심사 루프([engines:image_read]{op:"critic"})의 신뢰가 이 결정론에 걸려 있다.

handler.py 에서 spec-load 로 묶인다 (1500줄 규칙 — vision_read.py 와 같은 분리).
디스패치 표(_OP_DISPATCHERS)는 AST 가드 때문에 handler.py 에 남고, 구현만 여기 산다.

반환 통화: {"items":[{op,label,page,width,height,path}, …], "total": N, "message": …}
— 행 path 는 **절대 경로**. 인지층 GoalEval 의 시각 산출물 수집기가 결과 문자열에서
절대 이미지 경로를 긁어 평가자에게 첨부하므로, 절대 경로가 곧 검수 루프 연동이다.
"""
import os
import json
import uuid
import base64


def _err(message: str) -> str:
    """실패는 문자열이 아니라 계약으로 (B21-1 — 평문 오류는 성공으로 집계된다)."""
    return json.dumps({"success": False, "error": message}, ensure_ascii=False)


def _html_from_prev(prev) -> str:
    """파이프로 흘러온 통화를 렌더 가능한 HTML 조각으로 (V21-1 규약 — [self:write] 와 동일).

    받는 모양 세 가지: 이미 HTML 인 문자열 · 통화 봉투(message/items) · 평문.
    (handler.py 에서 이관, 2026-08-26 — render_html→render 승계와 함께 이 모듈로.)
    """
    from html import escape as _escape
    if prev is None:
        return ""
    s = prev if isinstance(prev, str) else json.dumps(prev, ensure_ascii=False)
    s = s.strip()
    if not s:
        return ""

    obj = None
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except Exception:
            obj = None

    if isinstance(obj, dict):
        items = obj.get("items")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            cols = list(items[0].keys())
            head = "".join(f"<th>{_escape(str(c))}</th>" for c in cols)
            rows = "".join(
                "<tr>" + "".join(f"<td>{_escape(str(r.get(c, '')))}</td>" for c in cols) + "</tr>"
                for r in items if isinstance(r, dict)
            )
            return ("<table style=\"border-collapse:collapse;font-family:sans-serif;font-size:15px\" "
                    "border=1 cellpadding=6>"
                    f"<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>")
        msg = obj.get("message")
        if isinstance(msg, str) and msg.strip():
            s = msg.strip()
        else:
            s = json.dumps(obj, ensure_ascii=False, indent=1)

    if "<" in s and ">" in s:      # 이미 HTML 조각이면 그대로
        return s
    return ("<div style=\"font-family:sans-serif;font-size:22px;line-height:1.6;"
            f"padding:40px;white-space:pre-wrap\">{_escape(s)}</div>")


def _image_data_uri(image_path):
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(image_path)[1].lower()
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml"}.get(ext, "image/png")
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return None


def _inline_assets(html: str, base_path: str) -> str:
    """문자열 HTML 의 상대 경로 이미지·배경을 base64 로 인라인 (파일 입력은 file:// 로드라 불필요)."""
    import re
    base_path = os.path.abspath(base_path)

    def _resolve(src):
        if src.startswith(("data:", "http://", "https://")):
            return None
        if src.startswith("file://"):
            src = src[7:]
        return src if os.path.isabs(src) else os.path.join(base_path, src)

    def replace_img_src(match):
        abs_path = _resolve(match.group(1))
        data = _image_data_uri(abs_path) if abs_path else None
        return f'src="{data}"' if data else match.group(0)

    def replace_bg_url(match):
        abs_path = _resolve(match.group(1))
        data = _image_data_uri(abs_path) if abs_path else None
        return f'url("{data}")' if data else match.group(0)

    html = re.sub(r'src=["\']([^"\']+)["\']', replace_img_src, html)
    html = re.sub(r'url\(["\']?([^"\')\s]+)["\']?\)', replace_bg_url, html)
    return html


# 기본 뷰포트 — 웹 검수의 최소 두 눈(데스크톱·모바일)은 viewports 파라미터로 준다.
_DEFAULT_VIEWPORT = {"width": 1280, "height": 720}


# ── 0층 기계 관측 (검수 비용 계층화, INSPECTION_COST_TIER 2026-08-27) ─────────
#
# 행 필드 `prescreen` = 렌더 중 공짜로 얻는 관측 사실의 요약 문자열("" = 깨끗).
# 판단(취향)이 아니라 관측의 기계 요약 — truncated 와 같은 정직층 부류. 합격/불합격
# 판정은 critic 층이 한다(prescreen 비었으면 비전 호출, 차 있으면 무비용 단락).
# 문자열 하나인 이유: [table:each] 의 $it.필드 치환이 문자열에서 안전하다.

def _clip(s, n=120):
    s = str(s).replace("\n", " ").strip()
    return s[:n] + ("…" if len(s) > n else "")


def _ink_ratio_from_samples(samples):
    """비백색 바이트 비율(표본) — 0 에 가까우면 백지 렌더. 정밀 측색이 아니라 존재 검사."""
    step = max(1, len(samples) // 100_000)
    sub = samples[::step]
    if not sub:
        return None
    return sum(1 for b in sub if b < 245) / len(sub)


def _ink_ratio_png(png_path):
    try:
        import fitz
        pix = fitz.Pixmap(png_path)
        return _ink_ratio_from_samples(pix.samples)
    except Exception:
        return None


def _blank_fact(ratio):
    if ratio is not None and ratio < 0.001:
        return f"빈 화면(잉크 {ratio * 100:.2f}%)"
    return None


def _web_prescreen_facts(events):
    """Playwright 이벤트 → 사실 문장들. 수집은 렌더가 이미 여는 페이지 위라 한계비용 0."""
    facts = []
    if events["pageerror"]:
        facts.append(f"페이지 예외 {len(events['pageerror'])}건: {_clip(events['pageerror'][0])}")
    if events["console"]:
        facts.append(f"콘솔 오류 {len(events['console'])}건: {_clip(events['console'][0])}")
    if events["reqfail"]:
        facts.append(f"요청 실패 {len(events['reqfail'])}건: {_clip(events['reqfail'][0], 100)}")
    return facts


def _attach_prescreen(row, facts):
    row["prescreen"] = "; ".join(f for f in facts if f)
    return row


# 수식 오류 표식 — criteria/sheet.yaml forbidden 의 0층 선행판(비전은 백업 그물).
_FORMULA_ERR_MARKERS = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NULL!", "#NUM!")


def _parse_viewports(tool_input):
    """viewports 파라미터 정규화 — [{width,height,label}] 또는 "1280x720" 문자열 혼용 수용."""
    raw = tool_input.get("viewports")
    if not raw:
        w = tool_input.get("width") or _DEFAULT_VIEWPORT["width"]
        h = tool_input.get("height") or _DEFAULT_VIEWPORT["height"]
        return [{"width": int(w), "height": int(h), "label": f"{w}x{h}"}], None
    if not isinstance(raw, list):
        raw = [raw]
    out = []
    for v in raw:
        if isinstance(v, str):
            try:
                w, h = v.lower().replace(" ", "").split("x", 1)
                out.append({"width": int(w), "height": int(h), "label": v.strip()})
            except Exception:
                return None, f"viewports 항목 해석 불가: {v!r} — \"1280x720\" 또는 {{width, height, label}}"
        elif isinstance(v, dict) and v.get("width") and v.get("height"):
            out.append({"width": int(v["width"]), "height": int(v["height"]),
                        "label": str(v.get("label") or f"{v['width']}x{v['height']}")})
        else:
            return None, f"viewports 항목 해석 불가: {v!r} — \"1280x720\" 또는 {{width, height, label}}"
    return out, None


def _out_stem(tool_input, src_path=None):
    op = tool_input.get("output_path")
    if op:
        return os.path.splitext(os.path.basename(op))[0]
    if src_path:
        return os.path.splitext(os.path.basename(src_path))[0]
    return f"render_{uuid.uuid4().hex[:8]}"


def _finish(rows, output_base, extra=None):
    # prescreen_flagged 는 필드가 정본(메시지에 안 넣는 이유: xlsx 가 위임 뒤 표식 스캔으로
    # 행 prescreen 을 더 채우므로, 문장에 박은 수는 낡을 수 있다).
    result = {"items": rows, "total": len(rows),
              "prescreen_flagged": sum(1 for r in rows if r.get("prescreen")),
              "message": f"렌더 완료: {len(rows)}장 → {os.path.abspath(output_base)}"}
    if extra:
        result.update(extra)
        if extra.get("truncated"):
            result["message"] += (f" (전체 {extra['total_pages']}페이지 중 {len(rows)}페이지만 렌더 — "
                                  f"나머지는 pages 또는 max_pages 로 지정)")
    return json.dumps(result, ensure_ascii=False)


def render_op_html(tool_input, output_base="."):
    """HTML(파일 path 또는 문자열 html, 생략 시 파이프 통화)→ 뷰포트별 PNG 1행."""
    from playwright.sync_api import sync_playwright

    src_path = tool_input.get("path")
    html = tool_input.get("html")
    if src_path:
        src_path = os.path.abspath(src_path)
        if not os.path.exists(src_path):
            return _err(f"파일이 없습니다: {src_path}")
    elif not html:
        # 파이프 싱크(V21-1) — html 생략 시 직전 통화를 받는다 ([self:write] 와 같은 규약).
        html = _html_from_prev(tool_input.get("_prev_result"))
    if not src_path and not html:
        return _err("path(HTML 파일) 또는 html(문자열)이 필요합니다 — 파이프로 통화를 흘려보내도 됩니다.")

    viewports, verr = _parse_viewports(tool_input)
    if verr:
        return _err(verr)
    full_page = tool_input.get("full_page", True)
    selector = tool_input.get("selector")
    scale = float(tool_input.get("scale", 1))
    base_path = tool_input.get("base_path")
    if html and base_path:
        html = _inline_assets(html, base_path)

    stem = _out_stem(tool_input, src_path)
    os.makedirs(output_base, exist_ok=True)
    rows = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for vp in viewports:
                page = browser.new_page(
                    viewport={"width": vp["width"], "height": vp["height"]},
                    device_scale_factor=scale)
                # 0층 관측 — 렌더가 이미 여는 페이지 위의 공짜 수집(비용 계층화)
                events = {"console": [], "pageerror": [], "reqfail": []}
                page.on("console",
                        lambda m, ev=events: ev["console"].append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e, ev=events: ev["pageerror"].append(str(e)))
                page.on("requestfailed",
                        lambda r, ev=events: ev["reqfail"].append(f"{r.url} ({r.failure})"))
                if src_path:
                    # file:// 로드 — 상대 경로 CSS/이미지가 자연 해소된다 (인라이닝 불필요)
                    page.goto("file://" + src_path)
                else:
                    page.set_content(html)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(500)  # 폰트/늦은 스타일 대기
                suffix = f"_{vp['label']}" if len(viewports) > 1 else ""
                out = os.path.abspath(os.path.join(output_base, f"{stem}{suffix}.png"))
                if selector:
                    el = page.query_selector(selector)
                    if not el:
                        browser.close()
                        return _err(f"셀렉터 '{selector}'를 찾을 수 없습니다.")
                    el.screenshot(path=out)
                else:
                    page.screenshot(path=out, full_page=bool(full_page))
                page.close()
                facts = _web_prescreen_facts(events) + [_blank_fact(_ink_ratio_png(out))]
                rows.append(_attach_prescreen(
                    {"op": "html", "label": vp["label"], "page": 1,
                     "width": vp["width"], "height": vp["height"], "path": out}, facts))
            browser.close()
        return _finish(rows, output_base)
    except Exception as e:
        return _err(f"HTML 렌더 실패: {e}")


def render_op_pdf(tool_input, output_base="."):
    """PDF 파일(path)→ 페이지별 PNG 1행 (PyMuPDF — 고유 페이지 크기 × scale, 뷰포트 비적용)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return _err("PyMuPDF(fitz)가 없습니다 — requirements-core 의존성 확인.")

    src_path = tool_input.get("path")
    if not src_path:
        return _err("path(PDF 파일 절대 경로)가 필요합니다.")
    src_path = os.path.abspath(src_path)
    if not os.path.exists(src_path):
        return _err(f"파일이 없습니다: {src_path}")

    scale = float(tool_input.get("scale", 2.0))  # 2.0 ≈ 144dpi
    max_pages = int(tool_input.get("max_pages", 20))
    want_pages = tool_input.get("pages")  # 1-기준 페이지 번호 목록 (선택)

    stem = _out_stem(tool_input, src_path)
    os.makedirs(output_base, exist_ok=True)
    rows = []
    try:
        doc = fitz.open(src_path)
        total_pages = doc.page_count
        if want_pages:
            targets = [int(n) for n in want_pages if 1 <= int(n) <= total_pages]
        else:
            targets = list(range(1, total_pages + 1))
        # 조용한 깎기 금지 — 상한을 넘으면 잘랐다고 명시 보고한다 (silent-clamp 부류)
        truncated = len(targets) > max_pages
        targets = targets[:max_pages]
        mat = fitz.Matrix(scale, scale)
        for n in targets:
            pix = doc.load_page(n - 1).get_pixmap(matrix=mat)
            out = os.path.abspath(os.path.join(output_base, f"{stem}_p{n}.png"))
            pix.save(out)
            facts = [_blank_fact(_ink_ratio_from_samples(pix.samples))]
            rows.append(_attach_prescreen(
                {"op": "pdf", "label": f"p{n}", "page": n,
                 "width": pix.width, "height": pix.height, "path": out}, facts))
        doc.close()
        return _finish(rows, output_base,
                       {"total_pages": total_pages, "truncated": truncated})
    except Exception as e:
        return _err(f"PDF 렌더 실패: {e}")


# ── op:xlsx — 장부 재계산+투영 (LibreOffice 헤드리스, RENDER_XLSX_HANDOFF 2026-08-26) ──
#
# 피드백 2층(수식 재계산 값 관찰)·3층(겉모습)을 외부 실행기 하나로 닫는다:
# xlsx → soffice(재계산+PDF 투영) → render_op_pdf 위임(픽셀화·정직 보고 승계).
# 원본 파일은 절대 불변 — 재계산은 LibreOffice 메모리 안에서만(지각 순수성).

# LibreOffice 는 xlsx 수식을 기본으로 재계산하지 않는다(저장된 캐시값 사용) — 이 시딩이
# 없으면 낡은 숫자가 찍힌 그림을 "관찰했다"고 믿는 침묵이 된다. 관문은
# backend/test_render_xlsx_contract.py (캐시 없는 수식 → PDF 텍스트에 계산값 필수).
_RECALC_XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
 <item oor:path="/org.openoffice.Office.Calc/Formula/Load">
  <prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop>
  <prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop>
 </item>
</oor:items>
"""


def _find_soffice():
    """soffice 실행 파일 탐색 — env 우선, 3 OS 후보 (windows-portability 위험지대)."""
    import shutil
    import sys as _sys
    cands = [os.environ.get("SOFFICE_PATH"), shutil.which("soffice")]
    if _sys.platform == "darwin":
        cands.append("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    elif os.name == "nt":
        cands += [r"C:\Program Files\LibreOffice\program\soffice.exe",
                  r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"]
    else:
        cands += ["/usr/bin/soffice", "/usr/local/bin/soffice", "/snap/bin/libreoffice"]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def _install_hint():
    import sys as _sys
    if _sys.platform == "darwin":
        return "brew install --cask libreoffice"
    if os.name == "nt":
        return "https://libreoffice.org 인스톨러"
    return "apt install libreoffice-calc"


# 맥 헤드리스 LibreOffice 는 시스템 폰트 폴백이 죽어 있다(2026-08-27 실측 — 폰트명을 명시해도
# 번들 라틴 폰트만 임베드되어 **한글이 텍스트 층에만 있고 픽셀에서 조용히 증발**했다).
# 프로파일 user/fonts 의 폰트는 직접 등록되므로, CJK 계 시스템 폰트를 심볼릭 링크로 주입한다.
# 관문 = test_render_xlsx_contract 의 한글 잉크 검사. 리눅스는 fontconfig(부족하면 fonts-nanum),
# 윈도우는 시스템 폰트가 정상 노출되므로 다윈만 후보를 둔다.
_FALLBACK_FONTS_DARWIN = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",     # 한글
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",             # 한글(본문용)
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",   # 광역 커버리지
]


def _link_fallback_fonts(profile_dir):
    import sys as _sys
    if _sys.platform != "darwin":
        return
    fonts_dir = os.path.join(profile_dir, "user", "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    for src in _FALLBACK_FONTS_DARWIN:
        if os.path.exists(src):
            try:
                os.symlink(src, os.path.join(fonts_dir, os.path.basename(src)))
            except OSError:
                pass


def render_op_xlsx(tool_input, output_base="."):
    """XLSX/XLSM 장부 → LibreOffice 재계산 → PDF → 페이지별 PNG (render_op_pdf 위임).

    결과 extra 에 pdf_path(절대 경로) 동봉 — [self:read]{path: pdf_path} 로 계산된
    숫자를 텍스트로 읽는 조합이 열린다(2층 텍스트 통로, 새 param 없이).
    """
    import shutil
    import subprocess

    src_path = tool_input.get("path")
    if not src_path:
        return _err("path(xlsx/xlsm 파일 경로)가 필요합니다.")
    src_path = os.path.abspath(src_path)
    if not os.path.exists(src_path):
        return _err(f"파일이 없습니다: {src_path}")
    if os.path.splitext(src_path)[1].lower() not in (".xlsx", ".xlsm"):
        return _err(f"xlsx/xlsm 만 지원합니다: {os.path.basename(src_path)} — "
                    "PDF 는 op:pdf, HTML 은 op:html, CSV·표 데이터는 시각 형태가 내재하지 않아 이 낱말 밖.")

    soffice = _find_soffice()
    if not soffice:
        return _err(f"LibreOffice(soffice)가 없습니다 — op:xlsx 는 장부 재계산·투영에 "
                    f"LibreOffice 헤드리스가 필요합니다. 설치: {_install_hint()}")

    try:
        timeout = int(tool_input.get("timeout", 120) or 120)
    except (TypeError, ValueError):
        timeout = 120

    stem = _out_stem(tool_input, src_path)
    os.makedirs(output_base, exist_ok=True)
    # 실행마다 임시 프로파일 — 사용자 프로파일 오염 0 · 동시 실행 레이스 0.
    work = os.path.join(output_base, f"_lo_{uuid.uuid4().hex[:8]}")
    profile = os.path.join(work, "profile")
    conv_out = os.path.join(work, "out")
    os.makedirs(os.path.join(profile, "user"), exist_ok=True)
    os.makedirs(conv_out, exist_ok=True)
    with open(os.path.join(profile, "user", "registrymodifications.xcu"), "w", encoding="utf-8") as f:
        f.write(_RECALC_XCU)
    _link_fallback_fonts(profile)

    profile_uri = "file://" + profile.replace(os.sep, "/")
    try:
        r = subprocess.run(
            [soffice, "--headless", "--norestore", f"-env:UserInstallation={profile_uri}",
             "--convert-to", "pdf", "--outdir", conv_out, src_path],
            capture_output=True, text=True, timeout=timeout)
        produced = os.path.join(conv_out, os.path.splitext(os.path.basename(src_path))[0] + ".pdf")
        if not os.path.exists(produced):
            # soffice 는 변환 실패에도 returncode 0 을 내기도 한다 — 판정은 산출 파일 실재로.
            tail = ((r.stderr or "") + (r.stdout or "")).strip()[-300:]
            return _err(f"xlsx→PDF 변환 실패 (soffice returncode={r.returncode}): {tail or '출력 없음'}")
        pdf_path = os.path.abspath(os.path.join(output_base, f"{stem}.pdf"))
        shutil.move(produced, pdf_path)
    except subprocess.TimeoutExpired:
        return _err(f"xlsx→PDF 변환 타임아웃({timeout}s) — timeout 파라미터로 늘리거나 장부 크기 확인.")
    except Exception as e:
        return _err(f"xlsx 렌더 실패: {e}")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    # 픽셀화는 pdf 경로 재사용 — scale·max_pages·pages·truncated 정직 보고 전부 승계.
    sub = dict(tool_input)
    sub["path"] = pdf_path
    sub.setdefault("output_path", stem)
    out = render_op_pdf(sub, output_base)
    try:
        result = json.loads(out)
    except Exception:
        return out
    if not result.get("items"):
        return out  # pdf 단계의 정직 오류 그대로
    for row in result["items"]:
        row["op"] = "xlsx"
    # 0층: 재계산 PDF 텍스트의 수식 오류 표식 — sheet.yaml forbidden 의 무비용 선행판
    try:
        import fitz
        doc = fitz.open(pdf_path)
        for row in result["items"]:
            text = doc.load_page(int(row["page"]) - 1).get_text()
            found = [m for m in _FORMULA_ERR_MARKERS if m in text]
            if found:
                fact = f"수식 오류 표식 노출: {', '.join(found)}"
                row["prescreen"] = "; ".join(x for x in [row.get("prescreen", ""), fact] if x)
        doc.close()
    except Exception:
        pass  # 표식 스캔 실패는 0층 공백일 뿐 — 렌더 결과 자체를 막지 않는다
    result["prescreen_flagged"] = sum(1 for r in result["items"] if r.get("prescreen"))
    result["pdf_path"] = pdf_path
    result["message"] += f" (재계산 PDF: {pdf_path} — 계산값 텍스트 확인은 [self:read])"
    if tool_input.get("viewports"):
        # 조용한 무시 금지 — 장부는 인쇄 투영이라 뷰포트 개념이 없다.
        result["note"] = "viewports 는 xlsx 에 적용되지 않습니다(형식 자체의 인쇄 투영을 따름)."
    return json.dumps(result, ensure_ascii=False)


def render_op_svg(tool_input, output_base="."):
    """SVG(파일 path 또는 문자열 svg)→ PNG 1행 (svg 요소 경계로 캡처)."""
    from playwright.sync_api import sync_playwright

    src_path = tool_input.get("path")
    svg = tool_input.get("svg")
    if src_path:
        src_path = os.path.abspath(src_path)
        if not os.path.exists(src_path):
            return _err(f"파일이 없습니다: {src_path}")
        with open(src_path, encoding="utf-8") as f:
            svg = f.read()
    if not svg or "<svg" not in svg:
        return _err("path(SVG 파일) 또는 svg(문자열, <svg …> 포함)가 필요합니다.")

    scale = float(tool_input.get("scale", 2))
    stem = _out_stem(tool_input, src_path)
    os.makedirs(output_base, exist_ok=True)
    out = os.path.abspath(os.path.join(output_base, f"{stem}.png"))
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport=dict(_DEFAULT_VIEWPORT),
                                    device_scale_factor=scale)
            page.set_content(f"<body style='margin:0;background:white'>{svg}</body>")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(300)
            el = page.query_selector("svg")
            if not el:
                browser.close()
                return _err("SVG 요소를 찾지 못했습니다 — 유효한 <svg> 마크업인지 확인.")
            box = el.bounding_box() or {}
            el.screenshot(path=out)
            browser.close()
        rows = [_attach_prescreen(
            {"op": "svg", "label": "svg", "page": 1,
             "width": int(box.get("width") or 0), "height": int(box.get("height") or 0),
             "path": out}, [_blank_fact(_ink_ratio_png(out))])]
        return _finish(rows, output_base)
    except Exception as e:
        return _err(f"SVG 렌더 실패: {e}")
