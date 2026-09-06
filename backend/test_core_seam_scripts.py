"""등록 스크립트의 코어/사용자 이음매 회귀 (2026-09-02).

패키지(.origin)·계기(yaml origin: user)에는 코어 이탈 수단이 있었는데 등록 스크립트에는 없어
data/scripts/ 에 등록하면 무조건 코어(=배포 동봉)가 됐다. registry.yaml 항목의 `origin: user` 가
매니페스트 core.scripts 에서 빼고, 설치 필터가 그 파일을 `!scripts/<파일>` 로 제외한다.

실행: .venv/bin/python -m pytest backend/test_core_seam_scripts.py -q
"""
import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_registry_origin_user_opts_out(tmp_path):
    bcm = _load("build_core_manifest")
    reg = tmp_path / "registry.yaml"
    reg.write_text(
        "공용절차:\n  description: '누구나'\n  file: 공용절차.py\n  interpreter: python\n"
        "가족전용:\n  description: '나만'\n  file: 가족전용.py\n  origin: user\n  interpreter: python\n"
        "따옴표:\n  file: '따옴표.py'\n  origin: \"user\"\n",
        encoding="utf-8")
    assert bcm._registry_user_scripts(reg) == {"가족전용.py", "따옴표.py"}
    assert bcm._registry_user_scripts(tmp_path / "없음.yaml") == set()


def test_dist_filter_excludes_only_noncore_scripts(tmp_path, monkeypatch):
    bdf = _load("build_dist_filter")
    d = tmp_path / "data" / "scripts"; d.mkdir(parents=True)
    for n in ("공용절차.py", "가족전용.py", "registry.yaml", ".hidden"):
        (d / n).write_text("", encoding="utf-8")
    monkeypatch.setattr(bdf, "REPO_ROOT", tmp_path)
    assert bdf._noncore_script_excludes({"scripts": {"공용절차.py"}}) == ["!scripts/가족전용.py"]
    # 옛 매니페스트(scripts 범주 없음)는 전부 빼는 사고 대신 무제외
    assert bdf._noncore_script_excludes({"scripts": None}) == []


def test_dist_filter_nfd_disk_name_matches_nfc_manifest(tmp_path, monkeypatch):
    """맥 파일시스템의 NFD 한글 이름이 git(NFC) 매니페스트와 일치해야 한다 — 실측: 정규화 없이
    비교해 코어 스크립트 10개를 통째로 설치에서 뺐다."""
    import unicodedata
    bdf = _load("build_dist_filter")
    d = tmp_path / "data" / "scripts"; d.mkdir(parents=True)
    nfd = unicodedata.normalize("NFD", "나레이션생성.py")
    (d / nfd).write_text("", encoding="utf-8")
    monkeypatch.setattr(bdf, "REPO_ROOT", tmp_path)
    assert bdf._noncore_script_excludes({"scripts": {"나레이션생성.py"}}) == []
    assert bdf._noncore_script_excludes({"scripts": set()}) == ["!scripts/나레이션생성.py"]


def test_live_manifest_has_scripts_category():
    import json
    m = json.load(open(os.path.join(ROOT, "data", "core_manifest.json"), encoding="utf-8"))
    assert "scripts" in m["core"] and "scripts" in m["retired"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ── 설치 파일 data 스테이지 (2026-09-06: ../data 통째 denylist 가 18GB·개인 자료를 실었다) ──

def test_dist_stage_ships_only_git_tracked_data(tmp_path, monkeypatch):
    """스테이지엔 git 이 추적하는 data/ 파일만 온다 — 미추적(백업·원장·기억)은 이름을 몰라도 빠진다."""
    import subprocess
    repo = tmp_path / "repo"
    (repo / "data" / "guides").mkdir(parents=True)
    (repo / "data" / "guides" / "a.md").write_text("tracked", encoding="utf-8")
    (repo / "data" / "_backups").mkdir()
    (repo / "data" / "_backups" / "README.md").write_text("tracked readme", encoding="utf-8")
    (repo / "data" / "_backups" / "2026_big.db").write_bytes(b"x" * 1000)      # 미추적
    (repo / "data" / "ibl_usage.db").write_bytes(b"y" * 1000)                   # 미추적
    (repo / "data" / "한글폴더").mkdir()
    (repo / "data" / "한글폴더" / "문서.md").write_text("nfc", encoding="utf-8")  # 추적, 한글 경로
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": os.environ.get("PATH", "")}
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "add", "data/guides/a.md", "data/_backups/README.md", "data/한글폴더/문서.md"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "t"], cwd=repo, check=True, env=env)

    bds = _load("build_dist_stage")
    monkeypatch.setattr(bds, "REPO_ROOT", repo)
    monkeypatch.setattr(bds, "DATA_DIR", repo / "data")
    monkeypatch.setattr(bds, "STAGE_ROOT", repo / "frontend" / ".dist_stage")
    monkeypatch.setattr(bds, "STAGE_DATA", repo / "frontend" / ".dist_stage" / "data")
    assert bds.build_stage() == 0
    staged = sorted(str(p.relative_to(repo / "frontend" / ".dist_stage" / "data")) for p in (repo / "frontend" / ".dist_stage" / "data").rglob("*") if p.is_file())
    assert staged == ["_backups/README.md", "guides/a.md", "한글폴더/문서.md"]


def test_dist_stage_check_refuses_whole_data_source(tmp_path, monkeypatch):
    """package.json 의 data 항목이 ../data 통째로 돌아가면 --check 가 막는다."""
    bds = _load("build_dist_stage")
    fe = tmp_path / "frontend"; fe.mkdir()
    pkg = fe / "package.json"
    (fe / ".gitignore").write_text(".dist_stage\n", encoding="utf-8")
    monkeypatch.setattr(bds, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(bds, "PKG_JSON", pkg)
    pkg.write_text(json.dumps({"build": {"extraResources": [{"from": "../data", "to": "data"}]}}), encoding="utf-8")
    assert bds.check() == 1
    pkg.write_text(json.dumps({"build": {"extraResources": [{"from": ".dist_stage/data", "to": "data"}]}}), encoding="utf-8")
    assert bds.check() == 0
