"""수리적용상태 스크립트의 git 열 — "라이브가 더러운가"가 아니라 "이 변경 내용이 HEAD 에 있는가".

2026-08-24 실측: 66파일이 커밋 0건인데 기계 생성 절이 전부 '커밋됨'이라 적었다.
원인은 git status(라이브 더러움)로 판정한 것 — 격리에만 있는 새 내용은 라이브가 깨끗해서
'커밋됨'이 됐다. 판정을 내용 blob 비교로 바꾼 뒤, 그 상태를 fixture 로 못 박는다.
"""
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401,E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "data", "scripts", "수리적용상태.py")


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("repair_status", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def repo(tmp_path):
    """커밋 1개 있는 임시 저장소 — a.txt 는 커밋됨, 작업트리에서 a.txt 수정·b.txt 신규."""
    r = str(tmp_path)
    def g(*a):
        return subprocess.run(["git", *a], cwd=r, capture_output=True, text=True, check=True).stdout
    g("init", "-q")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    open(os.path.join(r, "a.txt"), "w").write("v1\n")
    g("add", "a.txt"); g("commit", "-qm", "init")
    return r


def test_git_column_judges_content_not_live_dirtiness(repo):
    mod = _load()
    mod.ROOT = repo
    dirty = {}  # 라이브가 '깨끗하다'고 가정해도 판정이 바뀌면 안 된다

    # 격리 사본(다른 디렉토리)에만 새 내용이 있고 라이브 a.txt 는 옛 판 그대로
    iso = tempfile.mkdtemp()
    open(os.path.join(iso, "a.txt"), "w").write("v2\n")
    open(os.path.join(iso, "b.txt"), "w").write("new\n")

    assert mod._git_state("a.txt", os.path.join(iso, "a.txt"), dirty) == "미커밋(HEAD와 다름)"
    assert mod._git_state("b.txt", os.path.join(iso, "b.txt"), dirty) == "신규(미커밋)"
    # 같은 내용이면 라이브 적용 전이라도 커밋됨
    open(os.path.join(iso, "a.txt"), "w").write("v1\n")
    assert mod._git_state("a.txt", os.path.join(iso, "a.txt"), dirty) == "커밋됨"
    # 내용이 없으면 판단하지 않는다(미상)
    assert mod._git_state("c.txt", os.path.join(iso, "c.txt"), dirty) == "—"


def test_live_applied_but_uncommitted_is_not_reported_committed(repo):
    """라이브에 적용됐지만 미커밋 — 2026-08-24 의 실제 상태. '커밋됨'이면 기계가 거짓말한 것."""
    mod = _load()
    mod.ROOT = repo
    live = os.path.join(repo, "a.txt")
    open(live, "w").write("v2\n")   # 적용됨(라이브=격리), 커밋 안 됨
    assert mod._git_state("a.txt", live, {}) == "미커밋(HEAD와 다름)"


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__]))
