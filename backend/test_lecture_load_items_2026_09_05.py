"""[self:lecture]{op:"load"} 의 통화 = items (2026-09-05, ep2858 검토 수리).

  실측: 모델이 `[self:lecture]{op: "load", lecture_id} >> [table:take]{n: -6}` 로 마지막 6장을 집으려 했는데
  선언이 effect 라 타입검사가 거절했다. 몸은 deck 전문(dict)만 냈으니 선언은 정직했고, 틀린 것은 통화 설계다 —
  덱을 로드하면 슬라이드가 items 여야 뒤에 take·select·each 가 붙는다.
  L1  핸들러 load 가 items=슬라이드 행(slide_order 순, 순번·slide_id·제목·layout·speaker_note·png_file)을 내고 deck 전문은 옆 키에 남긴다.
  L2  사전이 load 를 items(액션 returns 상속)·읽기(side_effect false)·exempt(lecture_id 필요)로 선언한다.
  L3  타입검사가 `load >> [table:take]` 를 통과시키고, 액션 fixture(list) 가 낸 관측 열을 load 문장에 빌려주지 않는다.
임시 강의 폴더만(실 outputs 무접촉). 실행: .venv/bin/python -m pytest backend/test_lecture_load_items_2026_09_05.py -q
"""
import importlib.util
import json
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

_PKG = os.path.join(os.path.dirname(BACKEND), "data", "packages", "installed", "tools", "lecture_workspace")


def _pkg_handler():
    if _PKG not in sys.path:
        sys.path.insert(0, _PKG)
    spec = importlib.util.spec_from_file_location("tool_handler_lecture_workspace_under_test", os.path.join(_PKG, "handler.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- L1
def test_l1_load_emits_slide_rows_in_order(tmp_path, monkeypatch):
    H = _pkg_handler()
    store = H.lecture_store
    root = tmp_path / "lectures"
    (root / "lec1").mkdir(parents=True)
    deck = {"lecture_id": "lec1", "title": "강의", "slide_order": ["s002", "s001"],
            "slides": {"s001": {"id": "s001", "title": "첫 장", "layout": "hero", "png_file": "slides/s001.png", "speaker_note": "안녕"},
                       "s002": {"id": "s002", "title": "둘째 장", "layout": "factbox", "png_file": "slides/s002.png"}}}
    (root / "lec1" / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(store, "write_root", lambda: root)
    monkeypatch.setattr(store, "search_roots", lambda: [root])
    out = json.loads(H._lecture_load({"lecture_id": "lec1"}))
    assert out["success"] is True
    assert [r["slide_id"] for r in out["items"]] == ["s002", "s001"]           # slide_order 순
    assert out["items"][0]["순번"] == 1 and out["items"][0]["제목"] == "둘째 장"
    assert out["items"][1]["speaker_note"] == "안녕" and out["items"][1]["png_file"].endswith("s001.png")
    assert out["deck"]["title"] == "강의" and out["lecture_dir"].endswith("lec1")   # 전문·경로는 그대로
    from ibl_envelope import classify_currency
    assert classify_currency(out)[0] == "items"


# ---------------------------------------------------------------- L2
def test_l2_declaration_load_is_items_read_exempt():
    import yaml
    from ibl_ops import op_returns, op_exempt, op_side_effect
    d = yaml.safe_load(open(os.path.join(_PKG, "ibl_actions.yaml"), encoding="utf-8"))
    act = d["actions"]["lecture"]
    assert act["returns"] == "items"
    assert "load" not in (act["ops"].get("returns") or {})                     # 액션 returns(items) 상속
    assert op_returns(act, "load") == "items" and op_returns(act, "create") == "effect"
    assert op_side_effect(act, "load") is False and op_side_effect(act, "delete") is True
    assert op_exempt(act, "load")


# ---------------------------------------------------------------- L3
def test_l3_typecheck_passes_load_pipe_and_does_not_borrow_list_columns(monkeypatch):
    import ibl_access
    import ibl_typecheck as TC
    monkeypatch.setattr(ibl_access, "_return_shapes",
                        lambda: {"self:lecture": {"kind": "items", "keys": ["title", "meta", "summary", "url"]}})
    r = TC.typecheck_code('[self:lecture]{op: "load", lecture_id: "x"} >> [table:take]{n: -6}')
    assert r["ok"] and not [i for i in r["issues"] if i["severity"] == "error"], r["issues"]
    assert r["types"][0].startswith("(1) items")
    r2 = TC.typecheck_code('[self:lecture]{op: "load", lecture_id: "x"} >> [table:select]{columns: ["제목", "speaker_note"]}')
    assert not r2["issues"], r2["issues"]                                         # list 의 관측 열로 경고하지 않는다
    r3 = TC.typecheck_code('[self:lecture]{op: "list"} >> [table:select]{columns: ["없는열"]}')
    assert any(i["severity"] == "warning" for i in r3["issues"])                  # fixture op 자신은 종전대로 관측 열


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
