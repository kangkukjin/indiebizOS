"""수리 사본의 문서 계수는 적용 후 커밋 인덱스와 같고 Git 메타데이터를 쓰지 않는다."""
import subprocess
from pathlib import Path

import pytest
import boot_paths  # noqa: F401


@pytest.fixture
def candidate_repo(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    monkeypatch.delenv("INDIEBIZ_REPAIR_CHILD", raising=False)
    import iblbuild_docs
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    def write(relative):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# sample\n")
    git("init")
    for name in ("backend/base/old.py", "backend/cognition/kept.py", "data/guides/old.md"):
        write(name)
    (tmp_path / ".gitignore").write_text("scratch.py\nignored.md\n")
    git("add", ".")
    for name in ("backend/ibl/new.py", "backend/ibl/scratch.py", "backend/test_new.py",
                 "data/guides/new.md", "data/guides/second.md", "data/guides/ignored.md"):
        write(name)
    (tmp_path / "backend/base/old.py").unlink()
    (tmp_path / "data/guides/old.md").unlink()
    return tmp_path, iblbuild_docs, git


def test_repair_candidate_counts_match_eventual_index_without_writing_it(candidate_repo, monkeypatch):
    root, build, git = candidate_repo
    data = {"nodes": {"self": {"actions": {}}}}
    normal = build.collect_doc_facts(root, data)
    assert normal["layers"]["base"] == 1 and normal["layers"]["ibl"] == 0
    index = (root / ".git/index").read_bytes()
    monkeypatch.setenv("INDIEBIZ_REPAIR_CHILD", "1")
    candidate = build.collect_doc_facts(root, data)
    assert candidate["backend_py"] == 2
    assert candidate["layers"]["base"] == 0 and candidate["layers"]["ibl"] == 1
    assert candidate["guides_n"] == 2
    assert (root / ".git/index").read_bytes() == index
    git("add", "-A")
    monkeypatch.delenv("INDIEBIZ_REPAIR_CHILD")
    committed = build.collect_doc_facts(root, data)
    for field in ("backend_py", "layers", "guides_n"):
        assert committed[field] == candidate[field]


def test_empty_candidate_does_not_count_ignored_scratch(candidate_repo, monkeypatch):
    root, build, _ = candidate_repo
    for relative in ("backend/cognition/kept.py", "backend/ibl/new.py", "backend/test_new.py"):
        (root / relative).unlink()
    monkeypatch.setenv("INDIEBIZ_REPAIR_CHILD", "1")
    facts = build.collect_doc_facts(root, {"nodes": {"self": {"actions": {}}}})
    assert facts["backend_py"] == 0


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
