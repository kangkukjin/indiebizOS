"""
lecture_export.py - 강의 데크를 PDF / PPTX로 내보내기

저장 위치: {lecture_dir}/exports/{lecture_id}_{timestamp}.{pdf,pptx}

설계 원칙:
- 데크의 slide_order 순서대로 PNG를 모아서 합본
- PDF: PIL의 다중 페이지 저장 (의존성 추가 없음)
- PPTX: python-pptx로 1280×720 슬라이드에 PNG를 전체 배경으로 삽입
- 슬라이드 PNG가 없는 항목은 건너뜀 (경고)
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# lecture_store import
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
import lecture_store  # noqa: E402


def _collect_slide_pngs(deck: dict, lecture_dir: Path) -> list[Path]:
    """slide_order 순서대로 존재하는 PNG 경로 모음."""
    paths = []
    for sid in deck.get("slide_order", []):
        meta = deck.get("slides", {}).get(sid, {})
        rel = meta.get("png_file")
        if not rel:
            continue
        p = lecture_dir / rel
        if p.exists():
            paths.append(p)
    return paths


def _exports_dir(lecture_id: str) -> Path:
    d = lecture_store.lecture_dir(lecture_id) / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ─────────────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────────────

def export_pdf(lecture_id: str, output_path: Optional[Path] = None) -> dict:
    """슬라이드 데크를 PDF 한 파일로. PIL의 PDF 저장 기능 사용.

    Returns: {success, path, slide_count, skipped, format: "pdf"}
    """
    from PIL import Image

    deck = lecture_store.read_deck(lecture_id)
    lecture_dir = lecture_store.lecture_dir(lecture_id)
    pngs = _collect_slide_pngs(deck, lecture_dir)
    total_planned = len(deck.get("slide_order", []))
    skipped = total_planned - len(pngs)

    if not pngs:
        raise ValueError("내보낼 슬라이드가 없습니다 (PNG 없음)")

    if output_path is None:
        output_path = _exports_dir(lecture_id) / f"{lecture_id}_{_timestamp()}.pdf"

    # RGB로 변환 (PDF는 알파 채널 미지원)
    images = [Image.open(p).convert("RGB") for p in pngs]
    images[0].save(
        str(output_path),
        "PDF",
        save_all=True,
        append_images=images[1:] if len(images) > 1 else [],
        resolution=150.0,
    )

    return {
        "success": True,
        "format": "pdf",
        "path": str(output_path.resolve()),
        "slide_count": len(pngs),
        "skipped": skipped,
        "filename": output_path.name,
    }


# ─────────────────────────────────────────────────────────────────────
# PPTX (이미지 모드 — 디자인 완벽 보존, 편집 불가)
# ─────────────────────────────────────────────────────────────────────

def export_pptx(lecture_id: str, output_path: Optional[Path] = None) -> dict:
    """슬라이드 데크를 PPTX로 (이미지 모드).

    각 슬라이드 PNG를 통째 배경에 박아넣음. 디자인 완벽 보존하나 PPT에서 편집 불가.
    """
    try:
        from pptx import Presentation
        from pptx.util import Emu
    except ImportError:
        raise RuntimeError(
            "python-pptx 미설치. 'pip install python-pptx' 후 재시도하세요."
        )

    deck = lecture_store.read_deck(lecture_id)
    lecture_dir = lecture_store.lecture_dir(lecture_id)
    pngs = _collect_slide_pngs(deck, lecture_dir)
    total_planned = len(deck.get("slide_order", []))
    skipped = total_planned - len(pngs)

    if not pngs:
        raise ValueError("내보낼 슬라이드가 없습니다 (PNG 없음)")

    if output_path is None:
        output_path = _exports_dir(lecture_id) / f"{lecture_id}_{_timestamp()}.pptx"

    prs = Presentation()
    # 16:9 슬라이드 — 1280×720 픽셀에 가깝게.
    # PPT 표준 widescreen은 13.333" × 7.5" = 12,192,000 × 6,858,000 EMU
    prs.slide_width = Emu(12192000)
    prs.slide_height = Emu(6858000)
    blank_layout = prs.slide_layouts[6]  # blank

    for png_path in pngs:
        slide = prs.slides.add_slide(blank_layout)
        slide.shapes.add_picture(
            str(png_path), 0, 0,
            width=prs.slide_width,
            height=prs.slide_height,
        )

    prs.save(str(output_path))

    return {
        "success": True,
        "format": "pptx",
        "mode": "image",
        "path": str(output_path.resolve()),
        "slide_count": len(pngs),
        "skipped": skipped,
        "filename": output_path.name,
    }


# ─────────────────────────────────────────────────────────────────────
# PPTX (편집 가능 모드 — 텍스트박스로 분해)
# ─────────────────────────────────────────────────────────────────────
#
# 슬라이드 spec을 파싱해서 PPT 텍스트박스 + 이미지 객체로 분해.
# PPT에서 자유 위치 조정, 폰트 변경, 텍스트 편집 모두 가능.
# 디자인 시스템의 폰트·텍스처는 PPT가 재현 못 함 — 톤은 단순화됨.
#
# 좌표: 1280×720 px = 12192000×6858000 EMU. 1px = 9525 EMU.

# 1280×720 기준 위치 표 (px). 함수에서 EMU로 변환.
PX_TO_EMU = 9525
SLIDE_W_PX = 1280
SLIDE_H_PX = 720


def export_pptx_editable(lecture_id: str, output_path: Optional[Path] = None) -> dict:
    """슬라이드 spec → 편집 가능 PPTX. 텍스트박스 + 이미지로 분해.

    Layout별로 약속된 위치에 텍스트박스 배치. 일러스트 이미지는 별도 picture로 삽입.
    PPT에서 자유롭게 위치 조정·텍스트 편집 가능.
    """
    try:
        from pptx import Presentation
        from pptx.util import Emu, Pt
    except ImportError:
        raise RuntimeError(
            "python-pptx 미설치. 'pip install python-pptx' 후 재시도하세요."
        )

    deck = lecture_store.read_deck(lecture_id)
    lecture_dir = lecture_store.lecture_dir(lecture_id)

    slide_order = deck.get("slide_order", [])
    if not slide_order:
        raise ValueError("내보낼 슬라이드가 없습니다.")

    if output_path is None:
        output_path = _exports_dir(lecture_id) / f"{lecture_id}_{_timestamp()}_editable.pptx"

    prs = Presentation()
    prs.slide_width = Emu(SLIDE_W_PX * PX_TO_EMU)
    prs.slide_height = Emu(SLIDE_H_PX * PX_TO_EMU)
    blank_layout = prs.slide_layouts[6]

    placed = 0
    fallback_image = 0  # spec 파싱 실패 시 이미지로 fallback한 수

    for sid in slide_order:
        meta = deck.get("slides", {}).get(sid)
        if not meta:
            continue
        spec_file = lecture_dir / meta.get("spec_file", "")
        slide = prs.slides.add_slide(blank_layout)

        try:
            if not spec_file.exists():
                raise FileNotFoundError(f"spec 없음: {spec_file}")
            import json
            with open(spec_file, "r", encoding="utf-8") as f:
                spec = json.load(f)
            # 통째 이미지 슬라이드(native 통짜 / 옛 image 경로)는 구운 PNG라 분해 불가 — 편집모드에서도 비주얼 보존
            if spec.get("layout") in ("native", "image"):
                png = lecture_dir / meta.get("png_file", "")
                if png.exists():
                    slide.shapes.add_picture(
                        str(png), 0, 0, width=prs.slide_width, height=prs.slide_height
                    )
                    fallback_image += 1
                continue
            _populate_editable_slide(slide, spec, lecture_dir, Emu, Pt)
            placed += 1
        except Exception as e:
            # spec 파싱 실패 → PNG로 fallback
            print(f"[pptx_editable] {sid} fallback to image: {e}")
            png = lecture_dir / meta.get("png_file", "")
            if png.exists():
                slide.shapes.add_picture(
                    str(png), 0, 0,
                    width=prs.slide_width,
                    height=prs.slide_height,
                )
                fallback_image += 1

    prs.save(str(output_path))

    return {
        "success": True,
        "format": "pptx",
        "mode": "editable",
        "path": str(output_path.resolve()),
        "slide_count": placed + fallback_image,
        "editable_count": placed,
        "fallback_image_count": fallback_image,
        "filename": output_path.name,
    }


def _populate_editable_slide(slide, spec: dict, lecture_dir: Path, Emu, Pt):
    """단일 슬라이드에 layout별 텍스트박스·이미지 배치."""
    layout = spec.get("layout", "lecture_body")

    if layout in ("hero", "hero_illustration"):
        _add_image_if_any(slide, spec, "image_path", lecture_dir, 320, 100, 640, 360, Emu)
        _add_text(slide, spec.get("eyebrow"), 80, 60, 1120, 40, Emu, Pt, font_size=14, bold=False, gray=True)
        _add_text(slide, spec.get("title"), 80, 480, 1120, 100, Emu, Pt, font_size=48, bold=True, align="center")
        _add_text(slide, spec.get("subtitle"), 80, 590, 1120, 60, Emu, Pt, font_size=24, align="center", gray=True)

    elif layout == "quote":
        _add_text(slide, spec.get("quote"), 100, 180, 1080, 300, Emu, Pt, font_size=44, italic=True, align="center")
        _add_text(slide, spec.get("attribution"), 100, 500, 1080, 50, Emu, Pt, font_size=20, align="center", gray=True)
        _add_text(slide, spec.get("context"), 100, 560, 1080, 80, Emu, Pt, font_size=16, align="center", gray=True)

    elif layout == "split_concept":
        # 좌우 분할
        _add_image_if_any(slide, spec, "left_image_path", lecture_dir, 60, 100, 540, 360, Emu)
        _add_image_if_any(slide, spec, "right_image_path", lecture_dir, 680, 100, 540, 360, Emu)
        _add_text(slide, spec.get("eyebrow"), 80, 30, 1120, 30, Emu, Pt, font_size=14, gray=True)
        _add_text(slide, spec.get("left_title"), 60, 470, 540, 50, Emu, Pt, font_size=24, bold=True, align="center")
        _add_text(slide, spec.get("left_body"), 60, 525, 540, 100, Emu, Pt, font_size=16, align="center")
        _add_text(slide, spec.get("right_title"), 680, 470, 540, 50, Emu, Pt, font_size=24, bold=True, align="center")
        _add_text(slide, spec.get("right_body"), 680, 525, 540, 100, Emu, Pt, font_size=16, align="center")
        _add_text(slide, spec.get("conclusion"), 80, 640, 1120, 60, Emu, Pt, font_size=18, bold=True, align="center")

    elif layout == "comparison_table":
        _add_text(slide, spec.get("eyebrow"), 80, 40, 1120, 30, Emu, Pt, font_size=14, gray=True)
        _add_text(slide, spec.get("title"), 80, 75, 1120, 50, Emu, Pt, font_size=32, bold=True)
        # 표는 PPT 표 객체로
        headers = spec.get("headers") or []
        rows = spec.get("rows") or []
        if headers and rows:
            n_cols = len(headers)
            n_rows = len(rows) + 1  # +1 for header row
            try:
                table_shape = slide.shapes.add_table(
                    n_rows, n_cols,
                    Emu(80 * PX_TO_EMU), Emu(150 * PX_TO_EMU),
                    Emu(1120 * PX_TO_EMU), Emu(min(n_rows * 60, 500) * PX_TO_EMU),
                )
                tbl = table_shape.table
                # 헤더
                for ci, h in enumerate(headers):
                    cell = tbl.cell(0, ci)
                    cell.text = str(h)
                # 행
                for ri, row in enumerate(rows):
                    if not isinstance(row, list):
                        continue
                    for ci in range(min(n_cols, len(row))):
                        tbl.cell(ri + 1, ci).text = str(row[ci])
            except Exception as e:
                print(f"[pptx_editable] 표 생성 실패: {e}")

    elif layout == "factbox":
        _add_text(slide, spec.get("eyebrow"), 80, 40, 1120, 30, Emu, Pt, font_size=14, gray=True)
        _add_text(slide, spec.get("title"), 80, 75, 1120, 60, Emu, Pt, font_size=32, bold=True)
        _add_text(slide, spec.get("body"), 80, 145, 1120, 80, Emu, Pt, font_size=18)
        items = spec.get("items") or []
        if items:
            text = "\n".join(f"• {it}" for it in items if it)
            _add_text(slide, text, 80, 240, 1120, 400, Emu, Pt, font_size=20)
        _add_text(slide, spec.get("source"), 80, 660, 1120, 40, Emu, Pt, font_size=12, gray=True, italic=True)

    elif layout == "metaphor_story":
        _add_text(slide, spec.get("eyebrow"), 80, 40, 800, 30, Emu, Pt, font_size=14, gray=True)
        _add_text(slide, spec.get("title"), 80, 75, 1120, 60, Emu, Pt, font_size=32, bold=True)
        _add_text(slide, spec.get("label"), 950, 75, 250, 40, Emu, Pt, font_size=14, gray=True, align="right")
        _add_text(slide, spec.get("story"), 80, 160, 1120, 350, Emu, Pt, font_size=20)
        _add_text(slide, spec.get("takeaway"), 80, 540, 1120, 140, Emu, Pt, font_size=22, bold=True)

    elif layout in ("illustration_anchor", "illustration_background", "illustration_overlay"):
        # 상단 이미지 + 하단 텍스트
        _add_image_if_any(slide, spec, "image_path", lecture_dir, 80, 60, 1120, 380, Emu)
        _add_text(slide, spec.get("eyebrow"), 80, 460, 1120, 30, Emu, Pt, font_size=14, gray=True)
        _add_text(slide, spec.get("title"), 80, 495, 1120, 60, Emu, Pt, font_size=28, bold=True)
        _add_text(slide, spec.get("body"), 80, 565, 1120, 80, Emu, Pt, font_size=18)
        _add_text(slide, spec.get("takeaway") or spec.get("subtitle"),
                  80, 650, 1120, 50, Emu, Pt, font_size=16, bold=True, gray=True)

    else:
        # 기본: lecture_body 패턴 (comparison_iconic 등 미매핑 layout 포함)
        _add_text(slide, spec.get("eyebrow"), 80, 40, 1120, 30, Emu, Pt, font_size=14, gray=True)
        _add_text(slide, spec.get("title"), 80, 75, 1120, 70, Emu, Pt, font_size=36, bold=True)
        _add_text(slide, spec.get("body"), 80, 160, 1120, 100, Emu, Pt, font_size=18)
        bullets = spec.get("bullets") or []
        if bullets:
            text = "\n".join(f"• {b}" for b in bullets if b)
            _add_text(slide, text, 80, 280, 1120, 340, Emu, Pt, font_size=20)
        _add_text(slide, spec.get("quote"), 80, 630, 1120, 50, Emu, Pt, font_size=16, italic=True, gray=True)
        _add_text(slide, spec.get("footer"), 80, 680, 1120, 30, Emu, Pt, font_size=11, gray=True, align="right")


def _add_text(
    slide, text, x_px, y_px, w_px, h_px, Emu, Pt,
    font_size=18, bold=False, italic=False, align=None, gray=False,
):
    """텍스트박스 추가. 빈 텍스트는 무시."""
    if not text or not str(text).strip():
        return
    tb = slide.shapes.add_textbox(
        Emu(x_px * PX_TO_EMU), Emu(y_px * PX_TO_EMU),
        Emu(w_px * PX_TO_EMU), Emu(h_px * PX_TO_EMU),
    )
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = str(text)
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    if gray:
        from pptx.dml.color import RGBColor
        run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    if align == "center":
        from pptx.enum.text import PP_ALIGN
        p.alignment = PP_ALIGN.CENTER
    elif align == "right":
        from pptx.enum.text import PP_ALIGN
        p.alignment = PP_ALIGN.RIGHT


def _add_image_if_any(slide, spec, key, lecture_dir, x_px, y_px, w_px, h_px, Emu):
    """spec[key]에 일러스트 경로가 있으면 그림 추가. 없으면 무시."""
    path_str = spec.get(key)
    if not path_str:
        return
    p = Path(path_str)
    if not p.is_absolute():
        p = lecture_dir / path_str
    if not p.exists():
        return
    try:
        slide.shapes.add_picture(
            str(p),
            Emu(x_px * PX_TO_EMU), Emu(y_px * PX_TO_EMU),
            width=Emu(w_px * PX_TO_EMU), height=Emu(h_px * PX_TO_EMU),
        )
    except Exception as e:
        print(f"[pptx_editable] 이미지 삽입 실패 {key}: {e}")


# ─────────────────────────────────────────────────────────────────────
# 통합 진입점
# ─────────────────────────────────────────────────────────────────────

def export_deck(lecture_id: str, format: str) -> dict:
    """format에 따라 분기.

    format:
      - "pdf": 다중 페이지 PDF (PIL)
      - "pptx" 또는 "pptx_image": 통째 이미지 PPTX (디자인 완벽 보존, 편집 불가)
      - "pptx_editable": 텍스트박스로 분해된 PPTX (PPT에서 자유 편집 가능, 디자인 단순화)
    """
    fmt = (format or "").lower().strip()
    if fmt == "pdf":
        return export_pdf(lecture_id)
    elif fmt in ("pptx", "pptx_image"):
        return export_pptx(lecture_id)
    elif fmt == "pptx_editable":
        return export_pptx_editable(lecture_id)
    else:
        raise ValueError(
            f"지원하지 않는 형식: {format} (pdf/pptx/pptx_editable)"
        )
