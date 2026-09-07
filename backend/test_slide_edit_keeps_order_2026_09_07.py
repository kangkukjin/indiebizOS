"""편집이 순서를 잃지 않는다 — [self:slide]{op:"edit"} 재등록의 자리 계약 (2026-09-07 보고 수리).

  실측: s004 를 편집했더니 slide_order 맨 뒤로 밀렸다(13장 덱). 다음 접합이 '마지막 장'에
  붙이는 인사말을 4번 장에 붙였다 — 렌더 결과가 조용히 망가지는 부류.
  뿌리: register_slide 가 insert_at=None 을 무조건 "끝에 append" 로 읽었다. 위치를 말하지
  않은 것과 끝으로 보내라는 것은 다른 말이다.
  L1  이미 slide_order 에 있는 슬라이드를 insert_at 없이 재등록하면 제자리를 지킨다.
  L2  insert_at 을 명시하면 그 자리로 옮긴다(이동 어휘는 살아 있다). 새 슬라이드는 끝에 붙는다.
  L3  같은 재등록이 사용자가 적어둔 speaker_note 를 덮지 않고, 핸들러 응답의 speaker_note 는
      **저장된 노트**다(AI 초안을 돌려주면 호출자가 멀쩡한 노트를 다시 쓴다).
임시 강의 폴더만(실 outputs 무접촉). 실행: .venv/bin/python -m pytest backend/test_slide_edit_keeps_order_2026_09_07.py -q
"""
import importlib.util
import json
import os
import sys

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

_PKG = os.path.join(os.path.dirname(BACKEND), "data", "packages", "installed", "tools", "lecture_workspace")


def _store():
    if _PKG not in sys.path:
        sys.path.insert(0, _PKG)
    spec = importlib.util.spec_from_file_location("lecture_store_under_test", os.path.join(_PKG, "lecture_store.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _deck(root, n=5, notes=True):
    (root / "lec1").mkdir(parents=True, exist_ok=True)
    order = [f"s{i:03d}" for i in range(1, n + 1)]
    deck = {
        "lecture_id": "lec1", "title": "강의", "slide_order": list(order),
        "slides": {
            sid: {"id": sid, "title": sid, "layout": "custom",
                  "spec_file": f"slides/{sid}.json", "png_file": f"slides/{sid}.png",
                  **({"speaker_note": f"원고 {sid}"} if notes else {})}
            for sid in order
        },
    }
    (root / "lec1" / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    return order


def _read(root):
    return json.loads((root / "lec1" / "deck.json").read_text(encoding="utf-8"))


def _bind(store, monkeypatch, root):
    monkeypatch.setattr(store, "write_root", lambda: root)
    monkeypatch.setattr(store, "search_roots", lambda: [root])


# ---------------------------------------------------------------- L1
def test_l1_reregister_keeps_position(tmp_path, monkeypatch):
    store = _store()
    root = tmp_path / "lectures"
    order = _deck(root)
    _bind(store, monkeypatch, root)

    store.register_slide("lec1", "s004", "새 제목", "custom",
                         "slides/s004.json", "slides/s004.png",
                         insert_at=None, speaker_note="AI 초안")

    assert _read(root)["slide_order"] == order, "편집이 슬라이드를 끝으로 밀었다"


# ---------------------------------------------------------------- L2
def test_l2_explicit_insert_at_still_moves(tmp_path, monkeypatch):
    store = _store()
    root = tmp_path / "lectures"
    _deck(root)
    _bind(store, monkeypatch, root)

    store.register_slide("lec1", "s004", "t", "custom",
                         "slides/s004.json", "slides/s004.png", insert_at=0)
    assert _read(root)["slide_order"] == ["s004", "s001", "s002", "s003", "s005"]

    store.register_slide("lec1", "s009", "새 장", "custom",
                         "slides/s009.json", "slides/s009.png", insert_at=None)
    assert _read(root)["slide_order"][-1] == "s009", "새 슬라이드는 끝에 붙는다"


# ---------------------------------------------------------------- L3
def test_l3_note_preserved_and_response_reports_stored_note(tmp_path, monkeypatch):
    store = _store()
    root = tmp_path / "lectures"
    _deck(root)
    _bind(store, monkeypatch, root)

    meta = store.register_slide("lec1", "s004", "t", "custom",
                                "slides/s004.json", "slides/s004.png",
                                insert_at=None, speaker_note="AI 초안")
    assert meta["speaker_note"] == "원고 s004", "사용자 노트가 AI 초안에 덮였다"
    assert _read(root)["slides"]["s004"]["speaker_note"] == "원고 s004"

    # 노트가 없던 장은 초안으로 시드된다(보존 규칙의 반대편)
    _deck(root, notes=False)
    meta2 = store.register_slide("lec1", "s004", "t", "custom",
                                 "slides/s004.json", "slides/s004.png",
                                 insert_at=None, speaker_note="AI 초안")
    assert meta2["speaker_note"] == "AI 초안"


def test_l3_handler_returns_stored_note_not_draft():
    """핸들러가 응답에 돌려주는 speaker_note 는 register 결과(저장본)여야 한다."""
    src = open(os.path.join(_PKG, "handler.py"), encoding="utf-8").read()
    assert '"speaker_note": ai_response.get("speaker_note")' not in src, \
        "응답이 AI 초안을 저장본인 양 돌려준다(부작용 정직성)"
    assert '"speaker_note": stored_note' in src


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
