"""가지 문서 기질(tree_doc) — 세 트리 기억이 공유하는 문서 공통부의 계약(2026-09-18 ④).

표식·절 나누기·바꾸기·요약·갱신 기록·도장·세 갈래 동기화 계획. 줄 문법·식별·검증·저장은 여기 없다(호출자 몫).
세 모듈(hippo_tree·memory_tree·forage_doc)이 실제로 이 기질 위에 있는지도 여기서 못 박는다 — 사본이 되살아나면 실패.
"""
import os
import re
import sys
import time

import pytest
import boot_paths  # noqa: F401

import tree_doc as T


def test_marker_line_and_regex_round_trip_and_tolerate_trailing_attrs():
    line = T.marker_line("forage-doc", body="mac", root="/Users/u/Desktop")
    assert line == '<!-- forage-doc body="mac" root="/Users/u/Desktop" -->'
    rx = T.marker_re("forage-doc", "body", "root")
    assert rx.search(line).groups() == ("mac", "/Users/u/Desktop")
    assert rx.search('<!-- forage-doc body="web" root="a.com" dir_id="x1" -->').groups() == ("web", "a.com")   # 옛 뒤 속성
    assert rx.search('<!-- hippo-topic topic="x" -->') is None
    assert T.read_marker(line + "\n# 제목\n", "forage-doc", ("body", "root")) == ("mac", "/Users/u/Desktop")
    assert T.read_marker("# 표식 없음\n", "forage-doc", ("body", "root")) is None


def test_read_marker_from_file_and_ensure_marker(tmp_path):
    p = tmp_path / "memory.md"
    p.write_text('<!-- memory-node agent="a" node="가족/어머니" -->\n# 기억\n', encoding="utf-8")
    assert T.read_marker(str(p), "memory-node", ("agent", "node")) == ("a", "가족/어머니")
    rx = T.marker_re("memory-node", "agent", "node")
    line = T.marker_line("memory-node", agent="a", node="가족")
    assert T.ensure_marker("# 없음\n", line, rx) == line + "\n# 없음\n"
    assert T.ensure_marker(line + "\n# 있음\n", line, rx) == line + "\n# 있음\n"


DOC = ("<!-- x -->\n# 제목\n> 요약\n\n## 기억\n<!-- 주석 -->\n- [a] 하나 ‹#1›\n- [b] 둘 ‹#2›\n\n"
       "## 주행\n### 2026-09-18\n1. `x`\n\n## 갱신 기록\n- 2026-09-01 가지 생성\n")


def test_split_section_returns_head_section_tail_and_falls_back_to_anchor():
    head, sec, tail = T.split_section(DOC, "## 기억")
    assert head.endswith("> 요약\n\n") and sec.startswith("## 기억\n") and "- [b] 둘" in sec and tail.startswith("## 주행")
    head, sec, tail = T.split_section(DOC, "## 관용구", anchors=("## 주행", T.LEDGER))
    assert sec == "" and tail.startswith("## 주행") and head.endswith("‹#2›\n\n")     # 없으면 첫 anchor 앞이 자리
    head, sec, tail = T.split_section("# 아무 절 없음\n", "## 기억")
    assert (head, sec, tail) == ("# 아무 절 없음\n", "", "")
    assert T.section_body(DOC, "## 기억") == "- [a] 하나 ‹#1›\n- [b] 둘 ‹#2›"          # 제목·주석 줄 제외


def test_replace_section_keeps_prose_and_ledger_and_creates_when_missing():
    new = "## 기억\n- [c] 셋 ‹#3›\n"
    out = T.replace_section(DOC, "## 기억", new)
    assert "- [c] 셋" in out and "- [a] 하나" not in out and "## 주행\n### 2026-09-18" in out and out.endswith("- 2026-09-01 가지 생성\n")
    assert "> 요약\n\n## 기억\n" in out                                                     # 절 앞은 빈 줄로
    made = T.replace_section("# 제목\n> 요약\n## 갱신 기록\n- x\n", "## 기억", new)
    assert made == "# 제목\n> 요약\n\n## 기억\n- [c] 셋 ‹#3›\n\n## 갱신 기록\n- x\n"       # 갱신 기록 앞에 끼운다
    assert T.replace_section("# 제목\n", "## 기억", new) == "# 제목\n\n## 기억\n- [c] 셋 ‹#3›\n"


def test_gist_skeleton_ledger_meta(tmp_path):
    p = tmp_path / "memory.md"
    p.write_text(T.skeleton("<!-- m -->", "기억 — 가족", "(한 줄 요약 — AI 가 채운다)", extra=["guide: a.md", ""], today="2026-09-18"),
                 encoding="utf-8")
    text = p.read_text(encoding="utf-8")
    assert text == "<!-- m -->\n# 기억 — 가족\n> (한 줄 요약 — AI 가 채운다)\nguide: a.md\n\n## 갱신 기록\n- 2026-09-18 가지 생성\n"
    assert T.gist_of(str(p)) == ""                                   # 자리표는 요약이 아니다
    p.write_text(text.replace("(한 줄 요약 — AI 가 채운다)", "가족 사실"), encoding="utf-8")
    assert T.gist_of(str(p)) == "가족 사실" and T.gist_of(str(tmp_path / "없음.md")) == ""
    assert T.append_ledger("# t\n", "- 2026-09-18 이사").endswith("\n\n## 갱신 기록\n- 2026-09-18 이사\n")
    assert T.append_ledger(text, "- 2026-09-19 갱신").endswith("- 2026-09-18 가지 생성\n- 2026-09-19 갱신\n")
    assert T.meta(["#7", "", "2026-09-18", None]) == "‹#7 · 2026-09-18›"
    assert T.one_line("  a\n  b \n") == "a b"


def test_stamp_and_staleness(tmp_path):
    p = tmp_path / "d.md"; p.write_text("x", encoding="utf-8")
    s = T.stamp_value(str(p))
    assert T.is_stale(str(p), s) is False and T.is_stale(str(p), None) and T.is_stale(str(p), "bad")
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert T.is_stale(str(p), s) is True
    assert T.is_stale(str(tmp_path / "없음.md"), s) is False


def test_plan_sync_three_way_with_pluggable_identity():
    existing = [{"id": 1, "content": "옛"}, {"id": 2, "content": "지울"}, {"id": 3, "content": "그대로"}]
    known = [{"id": 1, "content": "고친"}, {"id": 3, "content": "그대로"}, {"id": 99, "content": "색인에 없는 id"}]
    fresh = [{"content": "새 줄"}]
    plan = T.plan_sync(known, fresh, existing, key=lambda r: r["id"], changed=lambda k, r: k["content"] != r["content"])
    assert [k["id"] for k, _r in plan["update"]] == [1] and [r["id"] for r in plan["delete"]] == [2]
    assert [i["content"] for i in plan["insert"]] == ["색인에 없는 id", "새 줄"] and plan["unchanged"] == 1
    # 복합 식별자(포식: 장소·종류·문장) — 같은 줄은 늘 갱신
    ex = [{"id": 5, "locus": "/a", "kind": "identity", "claim": "x", "body": "mac"}]
    parsed = [{"locus": "/a", "kind": "identity", "claim": "x"}, {"locus": "/a", "kind": "convention", "claim": "y"}]
    plan = T.plan_sync(parsed, [], ex, key=lambda r: (r["locus"], r["kind"], r["claim"]), changed=lambda p, r: True)
    assert len(plan["update"]) == 1 and plan["update"][0][1]["id"] == 5 and len(plan["insert"]) == 1 and plan["delete"] == []


def test_three_tree_modules_have_no_private_copies():
    """사본이 되살아나면 여기서 잡는다 — 절 나누기·표식 정규식·요약·줄바꿈 접기는 기질 한 벌뿐이다."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = [os.path.join(root, "backend/datastore/hippo_tree.py"), os.path.join(root, "backend/datastore/forage_doc.py"),
             os.path.join(root, "data/packages/installed/tools/memory/memory_tree.py")]
    for f in files:
        src = open(f, encoding="utf-8").read()
        assert "import tree_doc" in src, f
        assert not re.search(r're\.search\(r"\(\?m\)\^## ', src), f"절 나누기 사본: {f}"
        assert "re.compile(r'<!--" not in src and 're.compile(r"<!--' not in src, f"표식 정규식 사본: {f}"
        assert "startswith(\"(한 줄 요약\")" not in src, f"요약 사본: {f}"
        assert "getmtime(path)))" not in src, f"도장 사본: {f}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
