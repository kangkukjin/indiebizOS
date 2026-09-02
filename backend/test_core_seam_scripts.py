"""등록 스크립트의 코어/사용자 이음매 회귀 (2026-09-02).

패키지(.origin)·계기(yaml origin: user)에는 코어 이탈 수단이 있었는데 등록 스크립트에는 없어
data/scripts/ 에 등록하면 무조건 코어(=배포 동봉)가 됐다. registry.yaml 항목의 `origin: user` 가
매니페스트 core.scripts 에서 빼고, 설치 필터가 그 파일을 `!scripts/<파일>` 로 제외한다.

실행: .venv/bin/python -m pytest backend/test_core_seam_scripts.py -q
"""
import importlib.util
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
