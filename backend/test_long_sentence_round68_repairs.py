"""68회차(사진·음성 묶음 정리) 수리 회귀 — 모델 호출 없음.
L68-1 검사기 Union each · L68-2 NFC · L68-3 손상 이미지 거절 · L68-4 EXIF 직접 읽기 · L68-5 무음 전사 · L68-7 file_find truncations."""
import json
import os
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import boot_paths  # noqa: F401,E402


def _jpeg(tmp_path, name, stamp="2026:10:03 11:05:12", model="SM-J700F", size=(64, 48)):
    from PIL import Image, ExifTags
    im = Image.new("RGB", size, (200, 120, 80))
    ex = Image.Exif()
    ex[0x010F] = "samsung"
    ex[0x0110] = model
    ex.get_ifd(ExifTags.IFD.Exif)[0x9003] = stamp
    p = tmp_path / name
    im.save(p, "JPEG", exif=ex.tobytes())
    return p


def test_l68_1_each_over_union_of_empty_list_and_items_envelope_is_checked_not_crashed():
    from ibl_v2_entry import handle_request
    code = ('#!ibl edition=2\n$x = []\n'
            '[if:1 > 0] { $x = [{묘사들:"a"}] >> [table:ai]{instruction:"주제", schema:"주제(Text)", preserve_rows:true} }\n'
            'return $x >> [table:each]{ return $it.주제 }')
    out = handle_request({"code": code, "edition": 2, "check": True, "project_id": "수동모드"}, project_path=str(ROOT.parent))
    assert "기반 오류" not in (out.get("error") or ""), out.get("error")
    assert out.get("status") in ("valid", "incomplete"), out


def test_l68_1_rows_of_union_joins_element_types():
    from ibl_v2_compile import _rows_of
    from ibl_v2_types import Type, UNKNOWN, join
    empty = Type("List", item=UNKNOWN, positions=())
    env = Type("Record", (("items", Type("List", item=Type("Record", (("주제", Type("Text")),), open=False))),), open=False)
    rows = _rows_of(join(empty, env))
    assert rows.kind == "List" and rows.item.kind == "Record" and rows.positions is None


def test_l68_2_mdfind_paths_are_nfc(monkeypatch):
    import file_index
    nfd = unicodedata.normalize("NFD", "/tmp/IMG_0002 복사본.jpg")

    class Out:
        returncode, stdout = 0, nfd + "\n"
    monkeypatch.setattr(file_index.subprocess, "run", lambda *a, **k: Out())
    paths = file_index._run_mdfind("kMDItemContentTypeTree == 'public.image'c", "/tmp")
    assert paths == [unicodedata.normalize("NFC", nfd)]
    assert unicodedata.is_normalized("NFC", paths[0])


def test_l68_4_item_from_meta_reads_exif_and_pixels_when_index_is_silent(tmp_path, monkeypatch):
    import file_index
    p = _jpeg(tmp_path, "fresh.jpg")
    monkeypatch.setattr(file_index, "_mdls_meta", lambda path: {})  # 색인이 아직 모르는 파일
    item = file_index._item_from_meta(str(p), ("taken_at", "camera", "width", "height", "lat", "lng"))
    assert item["taken_at"].startswith("2026-10-03T11:05:12")
    assert item["camera"] == "SM-J700F" and item["width"] == 64 and item["height"] == 48
    assert "lat" not in item


def test_l68_4_exif_original_time_wins_over_index_file_date(tmp_path, monkeypatch):
    import file_index
    from datetime import datetime
    p = _jpeg(tmp_path, "indexed.jpg")
    monkeypatch.setattr(file_index, "_mdls_meta", lambda path: {"kMDItemContentCreationDate": datetime(2026, 1, 2, 3, 4, 5), "kMDItemPixelWidth": 999})
    item = file_index._item_from_meta(str(p), ("taken_at", "camera", "width", "height"))
    assert item["taken_at"].startswith("2026-10-03T11:05:12")  # EXIF 원본 시각이 색인의 파일 생성일보다 우선
    assert item["width"] == 999  # 색인이 준 크기는 유지
    assert item["camera"] == "SM-J700F" and item["height"] == 48  # 색인이 비운 칸만 EXIF 로


def test_l68_4_photo_record_carries_width_height():
    sys.path.insert(0, str(ROOT.parent / "data/packages/installed/tools/photo-manager"))
    import importlib
    handler = importlib.import_module("handler")
    rec = handler._photo_record({"path": "/tmp/a.jpg", "name": "a.jpg", "taken_at": "", "width": 10, "height": 7})
    assert rec["width"] == 10 and rec["height"] == 7 and rec["origin"] == "unknown"


def test_l68_3_extract_source_rejects_truncated_image(tmp_path):
    from ingest_engine import extract_source
    good = _jpeg(tmp_path, "good.jpg")
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(good.read_bytes()[:300])
    assert extract_source(path=str(good))["ok"] is True
    out = extract_source(path=str(bad))
    assert out["ok"] is False and "열 수 없습니다" in out["error"]


def test_l68_7_file_find_envelope_carries_truncations(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT.parent / "data/packages/installed/tools/system_essentials"))
    import importlib
    fs_meta = importlib.import_module("fs_meta")
    import file_index
    f = tmp_path / "x.txt"; f.write_text("x")
    res = {"success": True, "count": 2, "total": 2, "shown": 1, "truncated": True, "scope": str(tmp_path),
           "items": [{"path": str(f), "name": "x.txt", "size": 1, "mtime": "2026-10-14 00:00", "kind": "file", "ext": "txt"}],
           "truncations": [{"scope": "selection", "reason": "limit", "limit": 1, "retained": 1}]}
    monkeypatch.setattr(file_index, "query", lambda **k: res)
    out = json.loads(fs_meta._fs_meta_query({"path": str(tmp_path), "limit": 1}, str(tmp_path)))
    assert out["truncated"] is True and out["truncations"][0]["reason"] == "limit"


def test_l68_5_interaction_without_text_is_no_speech_not_error():
    sys.path.insert(0, str(ROOT.parent / "data/packages/installed/tools/android"))
    import importlib
    prov = importlib.import_module("android_audio_provider")
    out = prov._parse_interaction({"status": "completed", "steps": [], "outputs": []}, 3.0, False)
    assert out["text"] == "" and out["events"] == [] and out["no_speech"] is True


def test_l68_4_png_without_exif_keeps_index_date(tmp_path, monkeypatch):
    import file_index
    from datetime import datetime
    from PIL import Image
    p = tmp_path / "shot.png"
    Image.new("RGB", (8, 6), (1, 2, 3)).save(p)
    monkeypatch.setattr(file_index, "_mdls_meta", lambda path: {"kMDItemContentCreationDate": datetime(2026, 10, 1, 11, 15, 0)})  # mdls 는 UTC
    item = file_index._item_from_meta(str(p), ("taken_at", "camera", "width", "height"))
    assert item["taken_at"].startswith("2026-10-01") and "camera" not in item and item["width"] == 8


def test_l68_4_png_without_exif_and_silent_index_gets_file_birth_time(tmp_path, monkeypatch):
    import file_index, os
    from PIL import Image
    p = tmp_path / "shot.png"
    Image.new("RGB", (8, 6), (1, 2, 3)).save(p)
    t = 1791500000  # 2026-10-09 KST 어느 시각
    os.utime(p, (t, t))
    monkeypatch.setattr(file_index, "_mdls_meta", lambda path: {})
    item = file_index._item_from_meta(str(p), ("taken_at", "camera", "width", "height"))
    assert item["taken_at"] and "camera" not in item and item["width"] == 8


def test_l68_4_explicit_folder_query_merges_files_spotlight_does_not_know_yet(tmp_path, monkeypatch):
    import file_index
    a = _jpeg(tmp_path, "a.jpg"); b = _jpeg(tmp_path, "b 복사본.jpg", stamp="2026:10:04 15:20:33")
    (tmp_path / "notes.txt").write_text("x")
    monkeypatch.setattr(file_index, "_run_mdfind", lambda query, onlyin: [str(a)])  # 색인은 a 만 안다
    monkeypatch.setattr(file_index, "_mdls_meta", lambda path: {})
    res = file_index._spotlight_query("image", None, None, None, False, None, str(tmp_path), 50, "date", ("taken_at", "camera"))
    names = sorted(it["name"] for it in res["items"])
    assert names == ["a.jpg", "b 복사본.jpg"] and res["unindexed"] == 1 and res["count"] == 2
    assert all(it["taken_at"] for it in res["items"])


def test_l68_4_merge_is_skipped_for_date_or_gps_filters(tmp_path, monkeypatch):
    import file_index
    a = _jpeg(tmp_path, "a.jpg"); _jpeg(tmp_path, "b.jpg")
    monkeypatch.setattr(file_index, "_run_mdfind", lambda query, onlyin: [str(a)])
    monkeypatch.setattr(file_index, "_mdls_meta", lambda path: {})
    res = file_index._spotlight_query("image", None, "2026-10", None, False, None, str(tmp_path), 50, "date", ("taken_at",))
    assert [it["name"] for it in res["items"]] == ["a.jpg"] and "unindexed" not in res


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
