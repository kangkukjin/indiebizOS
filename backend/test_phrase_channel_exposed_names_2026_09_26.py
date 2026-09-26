"""이름 채널은 상시 블록에 이미 실린 이름을 Top-k 자리에 다시 싣지 않는다(2026-09-26).

제시만 바뀌고, 증류 관문·귀속이 읽는 set_phrase_recall 에는 이 턴에 모델이 본 이름(새로 제시한 것 +
상시 블록에 있던 적중)을 종전대로 싣는다.
"""
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401

import ibl_access
import ibl_usage_rag as R


def _row(alias, score):
    return SimpleNamespace(alias=alias, score=score, ibl_code=f"[def:{alias}](){{}}", intent=alias,
                           source="manual_seed", success_rate=-1, avg_ms=-1, avg_tokens=-1,
                           signature="", returns="", category="phrase", topic="", id=alias)


@pytest.fixture
def channel(monkeypatch):
    ranked = [_row("상시A", 0.9), _row("상시B", 0.85), _row("새것C", 0.8), _row("새것D", 0.7),
              _row("새것E", 0.6), _row("낮음F", 0.3)]
    asked = {}

    def search(db, query, top_k, allowed_nodes=None, aliased_only=False, **_):
        asked["top_k"] = top_k
        return ranked[:top_k]

    monkeypatch.setattr(R, "_search_active", search)
    monkeypatch.setattr(R, "_current_phrase_rows", lambda db, res: res)
    monkeypatch.setattr(R, "_own_only", lambda res: res)
    monkeypatch.setattr(ibl_access, "exposed_idiom_names", lambda allowed: frozenset({"상시A", "상시B"}))
    return asked


def test_exposed_names_do_not_take_recall_slots(channel):
    fresh, seen = R.IBLUsageRAG().search_phrases_split("질의", None, k=2)
    assert [r.alias for r in fresh] == ["새것C", "새것D"]
    assert [r.alias for r in seen] == ["상시A", "상시B"]
    assert channel["top_k"] == 4            # 상시 이름 수만큼 넓게 찾는다
    assert [r.alias for r in R.IBLUsageRAG().search_phrases("질의", None, k=2)] == ["새것C", "새것D"]


def test_threshold_still_applies_after_exclusion(channel, monkeypatch):
    monkeypatch.setattr(ibl_access, "exposed_idiom_names", lambda allowed: frozenset())
    fresh, seen = R.IBLUsageRAG().search_phrases_split("질의", None, k=10)
    assert "낮음F" not in [r.alias for r in fresh] and seen == []


def test_no_exposed_block_keeps_old_behaviour(channel, monkeypatch):
    def broken(allowed):
        raise RuntimeError("지도 없음")
    monkeypatch.setattr(ibl_access, "exposed_idiom_names", broken)
    fresh, seen = R.IBLUsageRAG().search_phrases_split("질의", None, k=2)
    assert [r.alias for r in fresh] == ["상시A", "상시B"] and seen == []


def test_turn_recall_keeps_what_the_model_saw(channel, monkeypatch):
    import thread_context
    monkeypatch.setattr(R.IBLUsageRAG, "_is_ibl_relevant", lambda self, q: True)
    monkeypatch.setattr(R, "_principal_allows_recall", lambda: True)
    monkeypatch.setattr(R, "_top_for_execution", lambda results: (0.5, ""))
    detail = R.build_execution_memory_detail("관용구로 처리해줘", None, phrase_k=2)
    shown = [p["alias"] for p in detail["presented"] if p["kind"] == "phrase"]
    assert shown == ["새것C", "새것D"]
    assert set(thread_context.get_phrase_recall()) == {r.ibl_code for r in
                                                        [_row(a, 0) for a in ("상시A", "상시B", "새것C", "새것D")]}


def test_exposed_names_follow_the_budgeted_map(monkeypatch):
    monkeypatch.setattr(ibl_access, "_idioms_cache",
                        {"t": 0.0, "text": "", "key": None, "anchors": {}, "names": frozenset()})
    text = ibl_access.idioms_map(None)
    names = ibl_access.exposed_idiom_names(None)
    assert bool(text) == bool(names)
    assert all(f"[fn:{n}]" in text or n in text for n in names)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
