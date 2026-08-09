"""
slide_edit_ops.py - 구워진(baked) 슬라이드의 부분 수정 op 묶음

handler.py 1500줄 규칙 분할(2026-08-10) — image_edit op 의 두 경로:
- instruction → 이미지 모델 최소 편집 (slide_native.edit_native_slide)
- overlay_text / overlay_set / overlay_clear → 결정론 '글자 얹기'
  (media_producer/slide_overlay.py 합성 — 원본 {sid}.base.png 보존·매번 재합성)

handler.py 가 import 해서 별칭(_slide_image_edit 등)으로 디스패치한다.
상태 전역 없음 — 순수 함수 + media_producer 모듈 로더만.
"""

from __future__ import annotations

import json
from pathlib import Path

import lecture_store

# 글자가 이미지에 구워진 레이아웃 — 필드 편집(✏️) 대신 image_edit 이 담당하는 부류
BAKED_LAYOUTS = ("native", "composite", "image")


def _ok(payload: dict) -> str:
    """성공 응답 — payload를 JSON 문자열로. (handler._ok 와 동일 계약)"""
    return json.dumps({"success": True, **payload}, ensure_ascii=False, indent=2)


def _err(message: str, **extra) -> str:
    """에러 응답. (handler._err 와 동일 계약)"""
    return json.dumps({"success": False, "error": message, **extra}, ensure_ascii=False, indent=2)


def load_slide_native():
    import importlib.util
    import sys as _sys
    path = Path(__file__).resolve().parent.parent / "media_producer" / "slide_native.py"
    spec = importlib.util.spec_from_file_location("slide_native", str(path))
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["slide_native"] = mod
    spec.loader.exec_module(mod)
    return mod


def load_slide_overlay():
    """결정론 텍스트 오버레이 합성기 (media_producer/slide_overlay.py) — 이미지 모델 우회."""
    import importlib.util
    import sys as _sys
    path = Path(__file__).resolve().parent.parent / "media_producer" / "slide_overlay.py"
    spec = importlib.util.spec_from_file_location("slide_overlay", str(path))
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["slide_overlay"] = mod
    spec.loader.exec_module(mod)
    return mod


def slide_image_edit(tool_input: dict) -> str:
    """통짜 이미지/업로드 이미지 슬라이드를 '부분 수정' — 다시 그리지 않고 현재 PNG를 편집.

    제목 한 줄만 바꾸려고 전체 재생성하면 비싸고 구도가 달라지는 문제를 해결.
    layout이 native/image인 슬라이드에만 적용(텍스트 슬라이드는 필드 편집 ✏️ 사용).

    두 경로:
    - instruction → 이미지 모델 최소 편집 (그림 자체를 바꿀 때. 픽셀 동일 비보장)
    - overlay_text / overlay_clear → 결정론 '글자 얹기' (이미지 모델 없이 글자만 합성.
      원본은 {slide_id}.base.png 로 보존, 목록은 meta.text_overlays — 매번 원본에서 재합성)
    """
    lecture_id = (tool_input.get("lecture_id") or "").strip()
    slide_id = (tool_input.get("slide_id") or "").strip()
    instruction = (tool_input.get("instruction") or "").strip()
    overlay_text = (tool_input.get("overlay_text") or "").strip()
    overlay_clear = bool(tool_input.get("overlay_clear"))
    overlay_set = tool_input.get("overlay_set")  # 전체 교체 (드래그 배치 편집기의 저장)
    if not lecture_id or not slide_id:
        return _err("lecture_id와 slide_id 모두 필수입니다.")
    if not instruction and not overlay_text and not overlay_clear and overlay_set is None:
        return _err("instruction(수정 요청) 또는 overlay_text(얹을 문구)가 필요합니다.")

    deck = lecture_store.read_deck(lecture_id)
    meta = deck.get("slides", {}).get(slide_id)
    if not meta:
        return _err(f"슬라이드 없음: {slide_id}", error_type="not_found")
    if meta.get("layout") not in BAKED_LAYOUTS:
        return _err(
            "이미지 부분 수정은 글자가 이미지에 구워진 슬라이드에서만 됩니다. "
            "텍스트 슬라이드는 필드 편집(✏️)을 쓰세요.",
            error_type="validation",
        )

    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    slides_dir_path = lecture_store.slides_dir(lecture_id)
    base_png = lecture_dir_path / (meta.get("png_file") or "")
    if not base_png.exists():
        return _err(f"원본 이미지가 없습니다: {base_png}")

    if overlay_text or overlay_clear or overlay_set is not None:
        return _overlay_text_edit(
            lecture_id, slide_id, deck, meta, base_png, slides_dir_path,
            overlay_text, overlay_clear, tool_input,
        )

    image_quality = (tool_input.get("image_quality") or "pro").strip()
    ti = {"instruction": instruction}
    if image_quality == "fast":
        ti["quality"], ti["image_size"] = "fast", "1K"
    else:
        ti["quality"], ti["image_size"] = "pro", "2K"

    sn = load_slide_native()
    result = json.loads(sn.edit_native_slide(ti, str(base_png), str(slides_dir_path), slide_id))
    if not result.get("success"):
        raise RuntimeError(result.get("message") or "이미지 편집 실패")

    # 얹었던 글자는 방금 모델이 본 픽셀에 구워졌다 — 원본 백업·목록 폐기 (다음 얹기의 중복 적용 방지)
    discard_overlay_state(slides_dir_path, slide_id, meta)

    # 썸네일 캐시 버스트 (PNG는 같은 경로로 덮어씀)
    from datetime import datetime
    deck["slides"][slide_id]["updated_at"] = datetime.now().isoformat(timespec="seconds")
    lecture_store.write_deck(lecture_id, deck)

    return _ok({
        "slide_id": slide_id,
        "mode": "image_edit",
        "png_file": meta.get("png_file"),
        "png_path": str(base_png.resolve()),
        "title": meta.get("title"),
    })


def discard_overlay_state(slides_dir_path, slide_id: str, meta: dict = None) -> None:
    """얹은 글자 상태 폐기 — PNG가 새 픽셀로 바뀔 때(재생성·이미지 모델 편집·삭제) 호출."""
    try:
        orig = Path(slides_dir_path) / f"{slide_id}.base.png"
        if orig.exists():
            orig.unlink()
    except Exception as e:
        print(f"[slide_overlay] base.png 정리 실패 (무시): {e}")
    if isinstance(meta, dict):
        meta.pop("text_overlays", None)


def _sanitize_overlay(entry: dict, so) -> tuple:
    """오버레이 1건 검증·정규화 — (정규화 dict, None) 또는 (None, 오류문)."""
    if not isinstance(entry, dict):
        return None, "오버레이 항목은 객체여야 합니다."
    text = str(entry.get("text") or "").strip()
    if not text:
        return None, "오버레이 text 는 비울 수 없습니다."
    out = {"text": text}
    xy = so._free_xy_of(entry)
    if xy is not None:
        out["x"], out["y"] = round(xy[0], 2), round(xy[1], 2)
    else:
        position = (entry.get("position") or "bottom-right").strip()
        if position not in so.POSITIONS:
            return None, f"알 수 없는 position: {position!r}. 사용 가능: {sorted(so.POSITIONS)} 또는 x/y(%)"
        out["position"] = position
    size_vw = entry.get("size_vw")
    if size_vw is not None:
        try:
            v = float(size_vw)
        except (TypeError, ValueError):
            return None, f"size_vw 는 숫자여야 합니다: {size_vw!r}"
        if not (0.5 <= v <= 12):
            return None, f"size_vw 범위(0.5~12) 밖: {v}"
        out["size_vw"] = round(v, 2)
    else:
        size = (entry.get("size") or "small").strip()
        if size not in so.SIZES:
            return None, f"알 수 없는 size: {size!r}. 사용 가능: {sorted(so.SIZES)} 또는 size_vw(숫자)"
        out["size"] = size
    font = (entry.get("font") or "sans").strip()
    if font not in so.FONTS:
        return None, f"알 수 없는 font: {font!r}. 사용 가능: {sorted(so.FONTS)}"
    if font != "sans":
        out["font"] = font
    if entry.get("weight") == "normal":  # 기본=600(semi-bold), normal 만 저장
        out["weight"] = "normal"
    if entry.get("shadow"):  # 기본=그림자 없음
        out["shadow"] = True
    out["color"] = str(entry.get("color") or "white").strip()
    out["chip"] = bool(entry.get("chip"))
    return out, None


def _overlay_text_edit(
    lecture_id: str, slide_id: str, deck: dict, meta: dict,
    current_png, slides_dir_path, overlay_text: str, overlay_clear: bool,
    tool_input: dict,
) -> str:
    """결정론 '글자 얹기' — 이미지 모델 없이 현재 슬라이드 위에 문구를 합성.

    첫 얹기 때 원본을 {slide_id}.base.png 로 보존하고, 이후엔 항상 원본에서
    전체 오버레이 목록을 재합성한다(글자가 글자 위에 겹겹이 구워지는 사고 방지).
    - overlay_text: 한 건 추가 (9방 position 또는 자유 x/y%)
    - overlay_set: 전체 교체 (드래그 배치 편집기의 저장 — 빈 목록=clear 와 동일)
    - overlay_clear=true: 원본 복원 + 목록 비우기
    """
    import shutil
    from datetime import datetime
    so = load_slide_overlay()
    orig = slides_dir_path / f"{slide_id}.base.png"
    overlays = list(meta.get("text_overlays") or [])
    overlay_set = tool_input.get("overlay_set")

    def _restore_original():
        if orig.exists():
            shutil.copy2(orig, current_png)
            orig.unlink()
        meta["text_overlays"] = []
        meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
        lecture_store.write_deck(lecture_id, deck)
        return _ok({
            "slide_id": slide_id, "mode": "text_overlay", "overlays": 0,
            "png_file": meta.get("png_file"),
            "png_path": str(Path(current_png).resolve()),
            "message": "얹은 글자를 지우고 원본을 복원했습니다.",
        })

    if overlay_set is not None:
        # ── 전체 교체 (배치 편집기 저장) ──
        if not isinstance(overlay_set, list):
            return _err("overlay_set 은 오버레이 객체 배열이어야 합니다.")
        clean = []
        for entry in overlay_set:
            out, err = _sanitize_overlay(entry, so)
            if err:
                return _err(err)
            clean.append(out)
        if not clean:
            return _restore_original()
        overlays = clean
    elif overlay_clear and not overlay_text:
        return _restore_original()
    else:
        # ── 한 건 추가 ──
        entry = {
            "text": overlay_text,
            "position": (tool_input.get("overlay_position") or "").strip() or None,
            "x": tool_input.get("overlay_x"),
            "y": tool_input.get("overlay_y"),
            "size": (tool_input.get("overlay_size") or "").strip() or None,
            "size_vw": tool_input.get("overlay_size_vw"),
            "font": (tool_input.get("overlay_font") or "").strip() or None,
            "color": (tool_input.get("overlay_color") or "white").strip(),
            "chip": bool(tool_input.get("overlay_chip")),
            "shadow": bool(tool_input.get("overlay_shadow")),
        }
        out, err = _sanitize_overlay(entry, so)
        if err:
            return _err(err)
        if overlay_clear:  # clear + text 동시 = 기존 것 지우고 이 문구 하나만
            overlays = []
        overlays.append(out)

    if not orig.exists():
        shutil.copy2(current_png, orig)
    result = json.loads(so.compose(str(orig), overlays, str(current_png)))
    if not result.get("success"):
        raise RuntimeError(result.get("error") or "글자 얹기 합성 실패")

    meta["text_overlays"] = overlays
    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    lecture_store.write_deck(lecture_id, deck)
    return _ok({
        "slide_id": slide_id, "mode": "text_overlay", "overlays": len(overlays),
        "text_overlays": overlays,
        "png_file": meta.get("png_file"),
        "png_path": str(Path(current_png).resolve()),
        "title": meta.get("title"),
    })
