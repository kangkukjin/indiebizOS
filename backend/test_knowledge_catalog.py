"""방법 이름 없이 검색·작은 주입·주체 경계·실제 의식/실행 전달 회귀."""
import json
import shutil
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
import boot_paths  # noqa: F401
import catalog_recall as recall
import knowledge_catalog as catalog
import principal
from test_episode3388_repairs import Runner, isolated  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def world(tmp_path):
    snapshot = catalog.load_snapshot(ROOT)
    for source in {e.source for e in snapshot.entries} | {catalog.CATALOG_PATH} | set(snapshot.files) | {e.path for e in snapshot.graph.evidence}:
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, target)
    catalog.build_index(tmp_path)
    return tmp_path


@pytest.fixture
def enabled(world, monkeypatch):
    (world / "data/world_pulse_config.json").write_text(json.dumps({
        "knowledge_catalog": {"enabled": True, "enabled_agents": ["study:agent_001"]}
    }), encoding="utf-8")
    monkeypatch.setattr(recall, "get_base_path", lambda: world)
    events = []
    monkeypatch.setattr(recall, "_record", lambda event: events.append(dict(event)))
    return SimpleNamespace(registry_key="study:agent_001"), events


# 작성 예문의 복사 대신 다른 문장으로 물으며, 적절한 허용 집합 중 하나면 성공이다.
CASES = [
    ("야간과 주간 교대에 필요한 인원을 공평하게 배정하고 싶어", {"ortools"}),
    ("고객 표에 결측치가 많고 중복된 행도 있어", {"pandas"}),
    ("CSV 파일 백 개를 SQL로 한꺼번에 조회할 수 있을까", {"duckdb"}),
    ("논문 DOI를 알 때 서지정보를 얻고 싶어", {"crossref", "openalex"}),
    ("회의 녹음을 시간 표시가 있는 자막으로 만들자", {"whisper"}),
    ("노래에서 보컬을 걷어내 반주만 남겨줘", {"demucs"}),
    ("사진의 촬영일과 GPS 기록으로 여행 경로를 정리해", {"exiftool"}),
    ("스캔 PDF를 검색 가능한 문서로 만들고 싶다", {"ocrmypdf", "paddleocr", "docling"}),
    ("사람 사이 관계망에서 중심성이 높은 사람을 찾아봐", {"networkx"}),
    ("과거 시계열을 회귀로 분석할까", {"statsmodels"}),
    ("베이지안 추론으로 확률모형의 불확실성을 표현하자", {"pymc"}),
    ("센서 메시지를 발행 구독 방식으로 모으자", {"mqtt"}),
    ("근무 표를 짜는 데 교대 조건이 많아", {"ortools"}),
    ("근무 표를 만들어 줘", {"ortools"}),
    ("수식의 미분과 적분을 기호로 계산해 줘", {"sympy"}),
    ("지도에서 위도와 경도에 따라 위치를 시각화해", {"geopandas", "osm"}),
]


@pytest.mark.parametrize("query,acceptable", CASES)
def test_name_free_queries(query, acceptable):
    snapshot = catalog.load_snapshot(ROOT)
    results, _ = catalog.search(ROOT, snapshot, query)
    assert {e.id for e, score in results[:4]} & acceptable


@pytest.mark.parametrize("query", ["안녕하세요", "고마워", "오늘은 기분이 좋아", "저녁 뭐 먹지",
                                      "사람답게 산다는 건 무엇일까", "지금 뭘 하고 있나?", "방금 말한 건 취소해"])
def test_irrelevant_queries_are_empty(query):
    assert catalog.search(ROOT, catalog.load_snapshot(ROOT), query)[0] == []


def test_alias_boundaries_and_spacing():
    assert catalog.mentions("기호 계산", "기호계산을 해줘")
    assert catalog.mentions("교대", "교대에서는")
    assert catalog.mentions("OR-Tools", "or-tools 사용")
    assert catalog.mentions("OR-Tools", "OR-Tools를 사용")
    assert not catalog.mentions("dot", "an anecdote")
    assert not catalog.mentions("교대", "교대생")


@pytest.mark.parametrize("query,irrelevant", [
    ("CSV 파일 백 개를 SQL로 한꺼번에 조회할 수 있을까", {"rclone"}),
    ("회의 녹음을 시간 표시가 있는 자막으로 만들자", {"xarray"}),
    ("스캔 PDF를 검색 가능한 문서로 만들고 싶다", {"typst", "quarto", "pikepdf"}),
])
def test_strong_matches_do_not_fill_with_generic_neighbors(query, irrelevant):
    results, _mode = catalog.search(ROOT, catalog.load_snapshot(ROOT), query)
    assert not {entry.id for entry, score in results} & irrelevant


def test_index_changed_and_broken_fallback(world):
    catalog.check_index(world)
    original = catalog.load_snapshot(world)
    path = world / catalog.CATALOG_PATH
    path.write_text(path.read_text().replace('"근무표"', '"당직"'), encoding="utf-8")
    current = catalog.load_snapshot(world)
    assert current.revision != original.revision
    assert catalog.search(world, current, "당직을 배정해")[1] == "lexical_fallback"
    with pytest.raises(ValueError, match="stale"):
        catalog.check_index(world)
    catalog.build_index(world)
    catalog.check_index(world)
    (world / catalog.INDEX_PATH).write_bytes(b"broken")
    rows, mode = catalog.search(world, current, "당직")
    assert mode == "lexical_fallback" and rows[0][0].id == "ortools"
    (world / catalog.INDEX_PATH).unlink()
    assert catalog.search(world, current, "당직")[1] == "lexical_fallback"


def test_source_drift_requires_review(world):
    source = world / "data/guides/world_tools.md"
    source.write_text(source.read_text() + "\n정정\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source changed"):
        catalog.check_index(world)


@pytest.mark.parametrize("mutation", ["duplicate", "empty", "path", "outside", "length"])
def test_invalid_catalog_rejected(world, mutation):
    import yaml
    path = world / catalog.CATALOG_PATH
    doc = yaml.safe_load(path.read_text())
    row = doc["entries"][0]
    if mutation == "duplicate":
        doc["entries"].append(dict(row))
    elif mutation == "empty":
        row["hint"] = " "
    elif mutation == "path":
        row["path"] = "wrong"
    elif mutation == "outside":
        row["source"]["path"] = "/etc/hosts"
    else:
        row["name"] = "a" * 61
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ValueError):
        catalog.load_snapshot(world)


def test_render_budget_and_xml():
    entries = [(catalog.Entry(str(i), ("분류<&>",), "A<&>", "설명" * 48, (), "source"), 10)
               for i in range(6)]
    snippet, ids, omitted = recall.render(entries)
    assert len(snippet) <= 600 and 0 < len(ids) <= 4
    assert "&lt;" in snippet and ElementTree.fromstring(snippet).tag == "method_map"
    assert all("설명" * 48 in line for line in snippet.splitlines() if line.startswith("-"))
    assert omitted
    assert recall.render(entries, max_chars=20)[0] == ""


def test_followup_and_topic_switch(enabled):
    runner, events = enabled
    history = [{"role": "user", "content": "간호사 근무표를 짜자"},
               {"role": "assistant", "content": "보컬 분리 Demucs"}]
    def run(message):
        return recall.recall_for_turn(runner, message, history, request_type="THINK")
    assert "OR-Tools" in run("그걸 구현해") and events[-1]["query_kind"] == "context"
    assert "Demucs" in run("이번에는 보컬 분리해") and "OR-Tools" not in run("이번에는 보컬 분리해")
    assert run("그럼 오늘은 기분이 좋아") == ""
    assert "OR-Tools" not in run("그걸 보컬 분리에 써봐")
    assert all("query" not in event for event in events)


def test_whole_history_budget():
    h = [{"role": "user", "content": "a" * 300}, {"role": "user", "content": "b" * 200}]
    assert recall.previous_query("그걸 해줘", h) == "b" * 200
    assert recall.previous_query("새 주제", h) == ""


def test_permissions_modes_and_live_toggle(enabled, world):
    runner, events = enabled
    def run(**kwargs):
        return recall.recall_for_turn(runner, "근무표", [], request_type=kwargs.pop("request_type", "THINK"), **kwargs)
    assert "OR-Tools" in run()
    with principal.narrow(principal.ANONYMOUS):
        assert run() == "" and events[-1]["status"] == "excluded"
    for kwargs in ({"force_role": "forage"}, {"reflex_hint": "code"}, {"context_update": True},
                   {"request_type": "SESSION_RESET"}):
        assert run(**kwargs) == ""
    runner.registry_key = "another:agent_001"
    assert run() == "" and events[-1]["status"] == "agent_disabled"
    runner.registry_key = "study:agent_001"
    config_path = world / "data/world_pulse_config.json"
    config_path.write_text('{"knowledge_catalog":{"enabled":false}}')
    assert run() == "" and events[-1]["status"] == "disabled"
    config_path.write_text('{"knowledge_catalog":{"enabled":true}}')
    assert run()
    (world / catalog.CATALOG_PATH).write_text("broken")
    assert run() == "" and events[-1]["status"] == "error"


def test_concurrent_turns_do_not_share_selection(enabled):
    runner, _events = enabled
    queries = ["근무표", "보컬", "안녕"] * 5
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda q: recall.recall_for_turn(runner, q, [], request_type="EXECUTE"), queries))
    for query, result in zip(queries, results):
        assert ("OR-Tools" in result) == (query == "근무표")
        assert ("Demucs" in result) == (query == "보컬")
        if query == "안녕":
            assert result == ""


def test_config_budget_cap_is_observable(enabled, world):
    runner, events = enabled
    (world / "data/world_pulse_config.json").write_text(json.dumps({"knowledge_catalog": {
        "enabled": True, "max_items": 99, "max_chars": 9999}}))
    snippet = recall.recall_for_turn(runner, "CSV 보컬 근무표 미분 회로 백업", [], request_type="THINK")
    assert len(snippet) <= 600 and events[-1]["count"] == 4
    assert events[-1]["clamped"] is True
    assert events[-1]["requested_budget"] == {"items": 99, "chars": 9999}
    assert events[-1]["effective_budget"] == {"items": 4, "chars": 600}


@pytest.mark.parametrize("route", ["THINK", "EXECUTE", "REPAIR"])
@pytest.mark.parametrize("presentation", ["names", "structure"])
def test_actual_pipeline_passes_identical_snippet_once(tmp_path, monkeypatch, isolated, enabled, world, route, presentation):
    (world / "data/world_pulse_config.json").write_text(json.dumps({
        "knowledge_catalog": {"enabled": True, "mode": presentation}}))
    plan_inputs, execution_inputs, searches, builds = [], [], [], []
    runner_info, _events = enabled
    real_search = recall.search
    def search(*args):
        searches.append(1)
        return real_search(*args)
    monkeypatch.setattr(recall, "search", search)
    def process(**kwargs):
        plan_inputs.append(kwargs)
        return {"task_framing": "근무표를 검토한다", "achievement_criteria": ""}
    def stream(**kwargs):
        execution_inputs.append(kwargs)
        yield {"type": "final", "content": "근무표 검토 결과"}
    monkeypatch.setattr("consciousness_agent.get_consciousness_agent",
                        lambda: SimpleNamespace(is_ready=True, process=process))
    monkeypatch.setattr("consciousness_agent.get_world_pulse_text", lambda: "")
    def split(role, consciousness, memory):
        from prompt_builder import _build_dynamic_context
        builds.append(memory)
        return "stable fixture", _build_dynamic_context(consciousness, execution_memory=memory)
    runner = Runner(tmp_path, stream)
    runner.registry_key = runner_info.registry_key
    runner._decide_request_type = lambda *args: (route, None)
    runner._build_system_prompt_split = split
    runner._build_execution_memory = lambda *a, **kw: ("original memory", 0, "")
    if route == "REPAIR":
        import thread_context
        thread_context.set_task_origin("user")
    events = list(runner.cognitive_stream("근무표를 짜줘", []))
    assert not [e for e in events if e["type"] == "error"], events
    assert len(searches) == 1 and len(execution_inputs) == 1
    memory = builds[0]
    assert "original memory" in memory and memory.count("<method_map>") == 1
    assert ("<world_data" in memory) == (presentation == "structure")
    if route != "EXECUTE":
        assert plan_inputs[0]["associative_memory"] == memory
    else:
        assert plan_inputs == []
    assert memory in execution_inputs[0]["message_content"]
    # 같은 조각으로 프롬프트를 재조립해도 다시 검색하거나 안정 prefix에 넣지 않는다.
    again = runner._refresh_execution_prompt("근무표", execution_memory=memory)
    assert again.count("<method_map>") == 1 and len(searches) == 1
    assert "method_map" not in runner.ai.system_prompt


def test_preparation_cancellation_is_not_hidden(enabled, monkeypatch):
    runner, events = enabled
    @contextmanager
    def preparation(name):
        raise RuntimeError("회상 시작 전에 작업이 취소되었습니다")
        yield  # pragma: no cover
    monkeypatch.setattr("supervision_bus.current", lambda: SimpleNamespace(preparation=preparation))
    with pytest.raises(RuntimeError, match="취소"):
        recall.recall_for_turn(runner, "근무표", [], request_type="THINK")
    assert events == []


def test_pipeline_cancel_after_catalog_stops_before_models(tmp_path, monkeypatch, isolated):
    cancelled, calls = [False], []
    def recall_and_cancel(*a, **kw):
        cancelled[0] = True
        return "<method_map>단서</method_map>"
    monkeypatch.setattr(recall, "recall_for_turn", recall_and_cancel)
    def stream(**kwargs):
        calls.append(kwargs)
        yield {"type": "final", "content": "실행되면 안 됨"}
    runner = Runner(tmp_path, stream)
    events = list(runner.cognitive_stream("근무표", [], cancel_check=lambda: cancelled[0]))
    assert calls == []
    assert any(e["type"] == "error" and "취소" in e["content"] for e in events)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
