"""대규모 어휘의 검색·분야·간섭과 내용 기반 캐시의 갱신 계약."""
import os
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
import knowledge_catalog as catalog
from world_context import assemble
from test_knowledge_catalog import ROOT, world  # noqa: F401


@pytest.fixture(scope="module")
def snapshot():
    return catalog.load_snapshot(ROOT)


def test_atlas_names_reach_the_selected_excerpt(snapshot):
    entries = [e for e in snapshot.entries if e.id.startswith(("atlas.", "foundation.", "basics."))]
    assert len(entries) >= 1000
    assert len({e.source_section for e in entries}) >= 50
    failures = []
    for entry in entries:
        candidates, _ = catalog.search(ROOT, snapshot, entry.name)
        context, text = assemble(snapshot, candidates)
        if entry.id not in {n["id"] for n in context["nodes"]} or entry.name not in text:
            failures.append(entry.id)
    assert not failures, failures


@pytest.mark.parametrize("query,name", [
    ("ANOVA", "분산분석"), ("SLAM", "동시적 위치추정과 지도작성"),
    ("Dublin Core", "더블린 코어"), ("IRAC", "IRAC 법적 분석"),
    ("HPLC", "고성능 액체크로마토그래피"), ("PCA", "주성분분석"),
    ("NPV", "순현재가치"), ("QFD", "품질기능전개"),
    ("훈련 주기화", "훈련 주기화"), ("Periodization", "시대구분"),
    ("inference to best explanation", "가설추론"),
])
def test_aliases_are_bridges_without_duplicate_concepts(snapshot, query, name):
    candidates, _ = catalog.search(ROOT, snapshot, query)
    context, _ = assemble(snapshot, candidates)
    assert name in {n["name"] for n in context["nodes"]}


def test_new_fields_can_be_browsed_without_knowing_names(snapshot):
    for path in (("생활", "農業"), ("생활", "농업과 원예"), ("인문", "철학과 윤리"),
                 ("건강", "보건 연구"), ("공학", "로봇과 자동화"), ("예술과 표현", "음악과 소리")):
        if path[-1] == "農業":
            assert catalog.lookup(ROOT, op="browse", path=list(path))["status"] == "no_match"
            continue
        result = catalog.lookup(ROOT, op="browse", path=list(path), limit=50)
        assert result["status"] == "ok"
        # 한 단계 아래 주제가 생겨도 그 안의 항목으로 탐색이 이어진다.
        assert sum(1 if r["item_type"] == "entry" else r["entry_count"]
                   for r in result["items"]) >= 19


def test_same_size_same_mtime_edit_and_revert_updates_snapshot(world):
    path = world / "data/knowledge_catalog/atlas/01_reasoning.yaml"
    raw, st = path.read_bytes(), path.stat()
    before = catalog.load_snapshot(world)
    changed = raw.replace("연역".encode(), "연엑".encode(), 1)
    assert len(raw) == len(changed) and raw != changed
    path.write_bytes(changed)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    after = catalog.load_snapshot(world)
    assert before.revision != after.revision
    assert next(e.name for e in after.entries if e.id == "atlas.reasoning.deduction") == "연엑"
    path.write_bytes(raw)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert catalog.load_snapshot(world) == before


def test_warm_reads_do_not_reparse_unchanged_yaml(snapshot, monkeypatch):
    import yaml
    def unexpected(*args, **kwargs):
        raise AssertionError("unchanged catalog reparsed")
    catalog.load_snapshot(ROOT)
    monkeypatch.setattr(yaml, "safe_load", unexpected)
    assert catalog.load_snapshot(ROOT) == snapshot


def test_large_catalog_does_not_expand_house_excerpt(snapshot):
    candidates, _ = catalog.search(ROOT, snapshot, "집을 3차원 렌더링으로 그려보고 싶어")
    context, text = assemble(snapshot, candidates)
    assert {"blender", "threejs"} <= {n["id"] for n in context["nodes"]}
    assert len(text) <= 300


def test_editorial_seeds_and_external_relation_sources_are_distinct(snapshot):
    atlas = [e for e in snapshot.entries if e.id.startswith("atlas.")]
    assert all(e.source == "docs/world_map/I_atlas_editorial_2026_09_17.md" for e in atlas)
    evidence = {e.id: e for e in snapshot.graph.evidence}
    assert not evidence["ev.atlas.editorial"].url
    assert evidence["ev.atlas.stan"].url == "https://mc-stan.org/"
    assert all(e.current for e in evidence.values())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_same_word_different_world_senses_do_not_merge(snapshot):
    for query, expected, excluded in [
        ('유화 (회화)', '유화 (회화)', '유화 (조리)'),
        ('교정 (계측)', '교정 (계측)', '교정 (출판)'),
        ('지도에서 위도와 경도에 따라 위치를 시각화해', '위도와 경도', '경도 (재료)'),
    ]:
        candidates, _ = catalog.search(ROOT, snapshot, query)
        names = {e.name for e, _ in candidates[:4]}
        assert expected in names
        assert excluded not in names


def test_document_cache_handles_more_fragments_than_its_file_cache(tmp_path, monkeypatch):
    import json
    import yaml
    directory = tmp_path / 'data/knowledge_catalog'
    directory.mkdir(parents=True)
    fragments = []
    for n in range(64):
        fragment = directory / f'part_{n}.yaml'
        fragment.write_text(f'entries: []\n# fragment {n}\n')
        fragments.append(str(fragment.relative_to(tmp_path)))
    (directory / 'world.yaml').write_text(json.dumps({
        'version': 2, 'entries': [], 'fragments': fragments}))
    snapshot = catalog.load_snapshot(tmp_path)
    # A bounded per-file cache may evict the root on the initial parse; warm it once.
    assert catalog.load_snapshot(tmp_path) == snapshot
    def unexpected(*args, **kwargs):
        raise AssertionError('unchanged fragment batch reparsed')
    monkeypatch.setattr(yaml, 'safe_load', unexpected)
    assert catalog.load_snapshot(tmp_path) == snapshot
