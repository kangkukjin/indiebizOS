"""자작 관문 가드 (2026-09-07).

사용자 판정: 어휘 우회(셸 그림자)·관용구 우회(fn_recognizer)에는 행동 순간의 관문이 있는데
**"세상에 이미 있는 걸 자작하고 있다"** 에는 없었다 — 지도와 규정 필드는 둘 다 *규정 순간*에
서고, 실측된 실패는 늘 *행동 순간*이었다. 이 시험이 고정하는 것:

  ① 임계 아래는 통과 — 짧은 스크립트는 자작이 아니다
  ② 임계를 넘고 확인이 없으면 **거절**하고, 거절문이 다음 한 걸음(지도·check)을 돌려준다
  ③ 확인하면(`install_lib`·지도 열람·read_guide) 그 턴 내내 걷힌다
  ④ 코드가 이미 지도의 도구를 쓰면 확인 없이도 통과 — 이미 세상 어깨 위다
  ⑤ 같은 파일 재작성은 두 번 세지 않는다 — 다듬기가 관문을 세우면 그게 새 침묵이다
  ⑥ 몸의 코드(RED·등록 스크립트·패키지)와 데이터·문서는 관할 밖
  ⑦ 턴이 바뀌면 원장이 걷힌다 · 신원 없는 호출은 세지 않는다
  ⑧ 지도에서 뽑은 이름에 영어 낱말·IBL 노드 같은 오탐이 섞이지 않는다
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "base"))

import selfbuild_gate as g  # noqa: E402

BIG = "\n".join(f"    line_{i} = compute({i})" for i in range(g.THRESHOLD_LINES + 20))
SMALL = "\n".join(f"    x{i} = {i}" for i in range(g.MIN_COUNTED_LINES + 2))


@pytest.fixture(autouse=True)
def _clean():
    g.reset("t1"); g.reset("t2")
    yield
    g.reset("t1"); g.reset("t2")


def _write(agent, path, body):
    return g.note_code_write(agent, str(ROOT / path), body, str(ROOT))


def test_small_write_passes():
    assert _write("t1", "outputs/tiny.py", SMALL) is None
    assert g.state("t1")["lines"] > 0


def test_threshold_refuses_and_returns_next_step():
    r = _write("t1", "outputs/toy.js", BIG)
    assert r and "자작 관문" in r
    assert "world_tools.md" in r and "check: true" in r     # 다음 한 걸음을 돌려준다
    assert "다시 보내라" in r                                # 저장되지 않았음을 말한다


@pytest.mark.parametrize("source", ["install_lib(trimesh)", "지도 열람", "read_guide(world_tools)"])
def test_consult_lifts_the_gate(source):
    g.note_consult("t1", source)
    assert _write("t1", "outputs/toy.js", BIG) is None
    assert g.state("t1")["consulted"] == source


def test_code_already_using_a_world_tool_passes():
    body = "import trimesh\n" + BIG
    assert _write("t1", "outputs/mesh.py", body) is None
    assert "trimesh" in str(g.state("t1")["consulted"])


def test_rewriting_the_same_file_is_not_counted_twice():
    half = "\n".join(f"    y{i} = {i}" for i in range(g.THRESHOLD_LINES - 10))
    assert _write("t1", "outputs/iter.py", half) is None
    assert _write("t1", "outputs/iter.py", half + "\n    z = 1") is None   # 다듬기
    assert g.state("t1")["lines"] < g.THRESHOLD_LINES + 10


def test_many_files_do_accumulate():
    part = "\n".join(f"    y{i} = {i}" for i in range(g.THRESHOLD_LINES // 2 + 5))
    assert _write("t1", "outputs/a.py", part) is None
    assert _write("t1", "outputs/b.py", part) is not None                  # 합이 임계를 넘는다


@pytest.mark.parametrize("rel", [
    "backend/base/x.py", "frontend/src/x.ts", "scripts/x.py",
    "data/scripts/x.py", "data/packages/installed/tools/x/handler.py",
])
def test_body_code_is_out_of_scope(rel):
    assert _write("t1", rel, BIG) is None


@pytest.mark.parametrize("rel", ["outputs/report.md", "outputs/rows.json", "outputs/a.csv"])
def test_data_and_docs_are_not_selfbuild(rel):
    assert _write("t1", rel, BIG) is None


def test_turn_boundary_and_anonymous_calls():
    part = "\n".join(f"    y{i} = {i}" for i in range(g.THRESHOLD_LINES // 2 + 5))
    assert _write("t1", "outputs/a.py", part) is None
    assert _write("t1", "outputs/b.py", part) is not None    # 누적이 임계를 넘었다
    g.reset("t1")
    assert g.state("t1") == {"lines": 0, "files": 0, "consulted": None, "fired": 0}
    assert _write("t1", "outputs/a.py", part) is None        # 새 턴은 처음부터 센다
    assert _write("", "outputs/toy.js", BIG) is None         # 신원 없는 호출은 세지 않는다
    assert g.state("") == {}


def test_map_names_are_clean():
    names = g._map_names(str(ROOT))
    assert {"blender", "trimesh", "three", "duckdb", "cv2", "rdkit"} <= names
    # 영어 낱말·IBL 노드·brew 옵션·예시 파일명이 도구로 오인되면 관문이 조용히 통과시킨다
    assert not ({"deal", "engines", "spatial", "no-quarantine", "out.stl", "table"} & names)


def test_gate_is_wired_to_the_write_sink():
    src = (ROOT / "data/packages/installed/tools/system_essentials/sink_ops.py").read_text(encoding="utf-8")
    assert "note_code_write" in src and "agent_id" in src
    routing = (ROOT / "backend/ibl/ibl_routing.py").read_text(encoding="utf-8")
    assert routing.count("note_consult") >= 3          # _route_handler · search_guide · install_lib


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
