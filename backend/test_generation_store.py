"""봉인 세대 저장소(G1): 스냅샷 신원·복사 중 변경 거절·바이트 검증·데이터 뷰·잔류 회수."""
import os
import stat
import subprocess
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
import generation_store as gens


def _repo(tmp_path, git=True):
    root = tmp_path / "repo"
    (root / "backend/base").mkdir(parents=True)
    (root / "backend/app.py").write_text("value = 1\n")
    (root / "backend/base/util.py").write_text("x = 1\n")
    (root / "backend/test_app.py").write_text("def test(): pass\n")
    (root / "scripts").mkdir()
    (root / "scripts/tool.py").write_text("print(1)\n")
    (root / "data/packages/installed/tools/pkg/data").mkdir(parents=True)
    (root / "data/packages/installed/tools/pkg/handler.py").write_text("def h(): return 1\n")
    (root / "data/packages/installed/tools/pkg/data/state.json").write_text("{}")
    (root / "data/packages/installed/tools/pkg/cache.db").write_bytes(b"db")
    (root / "data/packages/not_installed").mkdir()
    (root / "data/ibl_nodes_src").mkdir()
    (root / "data/ibl_nodes_src/self.yaml").write_text("node: self\n")
    (root / "data/ibl_nodes.yaml").write_text("nodes: {}\n")
    (root / "data/guides").mkdir()
    (root / "data/guides/a.md").write_text("guide")
    (root / "data/world.db").write_bytes(b"live")
    (root / "frontend").mkdir()
    (root / ".env").write_text("SECRET=1\n")
    (root / "mcp_server.py").write_text("srv = 1\n")
    if git:
        for args in (["init", "-q"], ["config", "user.email", "t@example.test"], ["config", "user.name", "T"]):
            subprocess.run(["git", *args], cwd=root, check=True)
        (root / ".gitignore").write_text("*.db\n__pycache__/\ndata/world.db\n.env\n")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
    return root


def test_inventory_excludes_tests_caches_state_and_links_them(tmp_path):
    root = _repo(tmp_path)
    inv = gens.execution_inventory(root)
    files = set(inv["files"])
    assert {"backend/app.py", "backend/base/util.py", "scripts/tool.py", "mcp_server.py",
            "data/packages/installed/tools/pkg/handler.py", "data/ibl_nodes_src/self.yaml", "data/ibl_nodes.yaml"} <= files
    assert "backend/test_app.py" not in files
    assert "data/packages/installed/tools/pkg/cache.db" not in files
    assert "data/packages/installed/tools/pkg/data/state.json" not in files
    assert ".env" not in files and "data/guides/a.md" not in files


def test_publication_compares_non_code_and_deleted_paths_without_requiring_them_in_manifest(tmp_path):
    root = _repo(tmp_path)
    deleted = ['backend/base/util.py', 'data/guides/old.md']
    (root / deleted[0]).unlink()
    published = {rel: gens._sha(root / rel) for rel in ('backend/app.py', 'backend/test_app.py', 'data/guides/a.md')}
    store = tmp_path / 'store'
    manifest = gens.snapshot(root, store)
    generation = store / manifest['generation']
    assert gens.publication_conflicts(generation, published, deleted) == []
    (root / 'data/guides/a.md').write_text('concurrent edit')
    (root / deleted[1]).symlink_to(root / 'missing')
    assert gens.publication_conflicts(generation, published, deleted) == ['data/guides/a.md', 'data/guides/old.md']


def test_snapshot_is_idempotent_and_dirty_content_changes_identity(tmp_path):
    root = _repo(tmp_path)
    store = tmp_path / "store"
    first = gens.snapshot(root, store)
    assert gens.snapshot(root, store)["generation"] == first["generation"]
    assert first["base_commit"] and first["dirty_inputs"] == []
    (root / "backend/app.py").write_text("value = 2\n")   # 커밋 없는 편집 = 다른 세대
    second = gens.snapshot(root, store)
    assert second["generation"] != first["generation"]
    assert second["base_commit"] == first["base_commit"] and "backend/app.py" in second["dirty_inputs"]
    assert (store / first["generation"] / "backend/app.py").read_text() == "value = 1\n"
    assert (store / second["generation"] / "backend/app.py").read_text() == "value = 2\n"


def test_sealed_copy_is_readonly_and_verifies_bytes(tmp_path):
    root = _repo(tmp_path)
    manifest = gens.snapshot(root, tmp_path / "store")
    gen = tmp_path / "store" / manifest["generation"]
    app = gen / "backend/app.py"
    assert not (stat.S_IMODE(app.stat().st_mode) & 0o222)
    with pytest.raises(PermissionError):
        app.open("w")
    gens.verify(gen)
    os.chmod(app, 0o644)
    app.write_text("value = 999\n")
    with pytest.raises(gens.GenerationCorrupt):
        gens.verify(gen)


def test_same_size_same_mtime_different_bytes_is_a_different_generation(tmp_path):
    root = _repo(tmp_path)
    store = tmp_path / "store"
    first = gens.snapshot(root, store)
    app = root / "backend/app.py"
    st = app.stat()
    app.write_text("value = 2\n")  # 같은 길이
    os.utime(app, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert app.stat().st_size == st.st_size and app.stat().st_mtime_ns == st.st_mtime_ns
    assert gens.execution_inventory(root)["digest"] != first["source_digest"]
    assert gens.snapshot(root, store)["generation"] != first["generation"]


def test_change_during_copy_rejects_candidate(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    original = gens._populate
    def racing(source_root, target, files):
        links = original(source_root, target, files)
        (root / "backend/app.py").write_text("value = 3\n")  # 복사 뒤·재고 전 편집
        return links
    monkeypatch.setattr(gens, "_populate", racing)
    with pytest.raises(gens.CandidateChanged):
        gens.snapshot(root, tmp_path / "store")
    assert not list((tmp_path / "store").glob(".building-*"))
    monkeypatch.setattr(gens, "_populate", original)
    assert gens.snapshot(root, tmp_path / "store")["files"]["backend/app.py"]


def test_data_view_links_live_data_and_package_state_but_copies_code(tmp_path):
    root = _repo(tmp_path)
    manifest = gens.snapshot(root, tmp_path / "store")
    gen = tmp_path / "store" / manifest["generation"]
    assert (gen / "data/guides").is_symlink() and (gen / "data/guides/a.md").read_text() == "guide"
    assert (gen / "data/world.db").is_symlink()
    assert (gen / "data/packages/not_installed").is_symlink()
    assert (gen / "data/packages/installed/tools/pkg/data").is_symlink()
    assert (gen / "data/packages/installed/tools/pkg/cache.db").is_symlink()
    assert not (gen / "data/packages/installed/tools/pkg/handler.py").is_symlink()
    assert not (gen / "data/ibl_nodes.yaml").is_symlink()
    assert (gen / ".env").is_symlink() and (gen / "frontend").is_symlink()
    assert not (gen / ".git").exists() and not os.path.lexists(gen / ".worktrees")
    # 정본 데이터 쓰기가 세대 뷰로 보인다(데이터는 하나다).
    (root / "data/guides/b.md").write_text("new")
    assert (gen / "data/guides/b.md").read_text() == "new"


def test_residue_salvage_moves_generation_local_data_to_source(tmp_path):
    root = _repo(tmp_path)
    manifest = gens.snapshot(root, tmp_path / "store")
    gen = tmp_path / "store" / manifest["generation"]
    (gen / "data/leaked.json").write_text("{}")             # __file__ 기준 쓰기가 남긴 잔류
    (gen / "data/guides_extra").mkdir()
    (gen / "data/guides_extra/x.md").write_text("x")
    (root / "data/guides_extra").mkdir()                     # 정본에 이미 있는 경로는 덮지 않는다
    assert gens.residue(gen) == ["data/guides_extra", "data/leaked.json"]
    out = gens.salvage(gen, root)
    assert out["moved"] == ["data/leaked.json"] and out["kept"] == ["data/guides_extra"]
    assert (root / "data/leaked.json").exists()


def test_extra_code_files_are_reported_and_prune_keeps_referenced(tmp_path):
    root = _repo(tmp_path)
    store = tmp_path / "store"
    kept = gens.snapshot(root, store)["generation"]
    (store / kept / "backend/stray.py").write_text("x = 1\n")
    assert gens.extra_code_files(store / kept) == ["backend/stray.py"]
    olds = []
    for n in range(5):
        (root / "backend/app.py").write_text(f"value = {n + 10}\n")
        olds.append(gens.snapshot(root, store)["generation"])
    removed = gens.prune(store, keep={kept}, source_root=root, keep_latest=1)
    assert kept not in removed and set(removed) == set(olds[:-1])
    assert (store / kept).exists() and (store / olds[-1]).exists()


def test_rule_based_inventory_without_git_matches_scope(tmp_path):
    root = _repo(tmp_path, git=False)
    files = set(gens.execution_inventory(root)["files"])
    assert "backend/app.py" in files and "backend/test_app.py" not in files
    assert "data/packages/installed/tools/pkg/cache.db" not in files
    assert "data/packages/installed/tools/pkg/data/state.json" not in files


def test_environment_identity_and_python_executable_fallback(tmp_path):
    root = _repo(tmp_path)
    identity = gens.environment_identity(root)
    assert identity["python"] and identity.get("distributions")
    manifest = gens.snapshot(root, tmp_path / "store")
    gen = tmp_path / "store" / manifest["generation"]
    assert manifest["environment"]["isolation"] == "none"
    import sys
    assert gens.python_executable(gen) == sys.executable


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
