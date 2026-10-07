"""Archive selection is independent of whether paths were expanded or explicit."""
import importlib.util
from pathlib import Path
import zipfile

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def archive():
    spec = importlib.util.spec_from_file_location("archive_script_under_test", ROOT / "data/scripts/압축.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    for name, data in {"team/keep.txt": b"keep\r\n", "team/internal/note.txt": b"private",
                       "team/internal/nested/empty.txt": b"", "team/draft.tmp": b"draft",
                       "team/internal_x/keep.txt": b"near", "guide.txt": b"guide"}.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("pattern", ["internal", "*/internal/*", "team/internal"])
def test_excludes_are_applied_to_direct_and_expanded_paths(archive, source, tmp_path, explicit, pattern):
    paths = [str(p) for p in source.rglob("*") if p.is_file()] if explicit else [str(source)]
    result = archive.op_pack({"paths": paths, "base": str(source),
                              "exclude": [pattern, "*.tmp"], "output": str(tmp_path / "out.zip")})
    assert result.get("success", True), result
    expected = {"team/keep.txt", "team/internal_x/keep.txt", "guide.txt"}
    with zipfile.ZipFile(result["output"]) as z:
        assert set(z.namelist()) == expected
        assert all(z.read(name) == (source / name).read_bytes() for name in expected)


def test_excluded_directory_is_not_walked(archive, source, tmp_path, monkeypatch):
    real_walk = archive.os.walk
    visited = []

    def observe(*args, **kwargs):
        for row in real_walk(*args, **kwargs):
            visited.append(Path(row[0]).relative_to(source).as_posix())
            yield row

    monkeypatch.setattr(archive.os, "walk", observe)
    archive.op_pack({"paths": [str(source)], "base": str(source), "exclude": ["*/internal/*"],
                     "output": str(tmp_path / "out.zip")})
    assert "team/internal" not in visited
    assert "team/internal_x" in visited


def test_direct_excluded_root_is_not_walked(archive, source, tmp_path, monkeypatch):
    real_walk = archive.os.walk
    visited = []

    def observe(path, *args, **kwargs):
        visited.append(Path(path))
        yield from real_walk(path, *args, **kwargs)

    monkeypatch.setattr(archive.os, "walk", observe)
    result = archive.op_pack({"paths": [str(source / "team/internal"), str(source / "guide.txt")],
                              "base": str(source), "exclude": ["*/internal/*"],
                              "output": str(tmp_path / "out.zip")})
    assert [r["name"] for r in result["items"]] == ["guide.txt"]
    assert not visited


def test_overlap_include_and_empty_files_still_roundtrip(archive, source, tmp_path):
    empty = source / "empty.txt"
    empty.write_bytes(b"")
    paths = [str(source), str(empty), str(source / "team/keep.txt"), str(source)]
    result = archive.op_pack({"paths": paths, "base": str(source), "include": ["*.txt"],
                              "exclude": ["internal"], "output": str(tmp_path / "out.zip")})
    expected = {"team/keep.txt", "team/internal_x/keep.txt", "guide.txt", "empty.txt"}
    with zipfile.ZipFile(result["output"]) as z:
        assert set(z.namelist()) == expected
        assert len(z.namelist()) == len(expected)
    unpacked = archive.op_unpack({"path": result["output"], "out_dir": str(tmp_path / "restored")})
    assert unpacked["count"] == len(expected)
    assert all((tmp_path / "restored" / n).read_bytes() == (source / n).read_bytes() for n in expected)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
