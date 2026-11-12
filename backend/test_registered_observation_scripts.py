"""수집 원문 다시 읽기·웹 화면 확인 등록 스크립트의 값 계약(2026-11-12).

두 스크립트는 되풀이되던 셸 이음매(저장 JSON을 매번 새 코드로 파싱, 브라우저 기동·오류 수집을 매번 새로 작성)를
이름 하나로 묶은 관측 도구다. 여기서는 네트워크·브라우저 없이 입력 검증과 저장본 읽기만 확인한다.
"""
import importlib.util
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "data/scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def saved(tmp_path, monkeypatch):
    from common import spill
    monkeypatch.setattr(spill, "_root", lambda: str(tmp_path))
    rows = [{"type": "heading", "text": "제목", "url": "https://fixture.test/a", "paragraph_index": 1},
            {"type": "paragraph", "text": "앞 문단", "url": "https://fixture.test/a", "paragraph_index": 2},
            {"type": "paragraph", "text": "핵심 근거 42%", "url": "https://fixture.test/a", "paragraph_index": 3},
            {"type": "paragraph", "text": "뒤 문단", "url": "https://fixture.test/a", "paragraph_index": 4}]
    path = tmp_path / "20261112_000000_crawl_source_abcdef.json"
    path.write_text(json.dumps({"success": True, "url": "https://fixture.test/a", "title": "제목",
                                "text": "\n".join(r["text"] for r in rows), "items": rows}, ensure_ascii=False))
    return str(path)


def test_find_returns_matching_paragraphs_with_context_and_their_source(saved):
    out = _load("collected_source").run({"op": "find", "paths": [saved], "pattern": "[0-9]+%", "context": 1, "limit": 5})
    assert out["ok"] and out["failed"] == 0
    assert [row["paragraph_index"] for row in out["items"]] == [2, 3, 4]
    assert all(row["source_path"] == saved and row["url"] == "https://fixture.test/a" for row in out["items"])
    assert out["sources"][0]["paragraphs"] == 4 and out["sources"][0]["match_info"]["total_matches"] == 1


def test_range_and_info_read_the_same_saved_source_without_matching(saved):
    module = _load("collected_source")
    ranged = module.run({"op": "range", "paths": [saved], "start": 2, "end": 3})
    assert [row["text"] for row in ranged["items"]] == ["앞 문단", "핵심 근거 42%"]
    info = module.run({"op": "info", "paths": [saved]})
    assert info["items"] == [] and info["sources"][0]["title"] == "제목" and info["sources"][0]["chars"] > 0


def test_unreadable_sources_are_reported_per_path_not_hidden(saved, tmp_path):
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}")
    missing = str(tmp_path / "gone.json")
    out = _load("collected_source").run({"op": "info", "paths": [saved, str(outside), missing]})
    assert out["ok"] is False and out["failed"] == 2
    assert [row["ok"] for row in out["sources"]] == [True, False, False]
    assert "밖" in out["sources"][1]["error"] and "다시 수집" in out["sources"][2]["error"]


def test_omitted_matches_are_marked_as_the_callers_selection(saved):
    out = _load("collected_source").run({"op": "find", "paths": [saved], "pattern": "문단", "limit": 1})
    assert len(out["items"]) == 1 and out["truncated"] is True
    assert out["truncations"] == [{"scope": "selection", "source": "collected_source.find",
                                   "unit": "matches", "omitted": 1}]


@pytest.mark.parametrize("args,needle", [
    ({"op": "find", "paths": ["x"]}, "pattern"),
    ({"op": "read", "paths": ["x"]}, "op"),
    ({"op": "info", "paths": []}, "paths"),
    ({"op": "range", "paths": ["x"], "start": 3, "end": 2}, "end"),
])
def test_collected_source_rejects_incomplete_requests(args, needle):
    with pytest.raises(ValueError, match=needle):
        _load("collected_source").run(args)


@pytest.mark.parametrize("args,needle", [
    ({"url": "ftp://fixture.test/"}, "url"),
    ({"url": "https://fixture.test/", "viewport": "wide"}, "viewport"),
    ({"url": "https://fixture.test/", "timeout_ms": 10}, "timeout_ms"),
    ({"url": "https://fixture.test/", "evaluate": "document.title"}, "evaluate"),
])
def test_page_check_validates_before_starting_a_browser(args, needle):
    with pytest.raises(ValueError, match=needle):
        _load("web_page_check").run(args)


def test_both_scripts_are_registered_with_a_declared_contract():
    registry = yaml.safe_load((ROOT / "data/scripts/registry.yaml").read_text())
    assert registry["수집원문"]["file"] == "collected_source.py"
    assert registry["수집원문"]["callable_contract"]["enums"]["op"] == ["info", "find", "range"]
    assert registry["웹화면확인"]["file"] == "web_page_check.py"
    assert registry["웹화면확인"]["callable_contract"]["required"] == ["url"]
    # 수집 관용구는 순수 값 연산으로 남는다. 파일을 읽는 일은 수집원문이 맡는다.
    assert registry["수집관용구"]["callable_contract"]["effects"] == ["pure"]
    assert registry["수집관용구"]["callable_contract"]["params"]["head"] == "Number"
