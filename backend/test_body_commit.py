"""[self:body] op:commit 각인 배터리 (2026-08-27 신설 — docs/SELF_EVOLUTION_AUTOMATION_HANDOFF.md A-5)

    C1. paths 누락·빈 배열 = 거절 (전부-커밋 굴절 없음)
    C2. 저장소 밖 경로 = 거절
    C3. 지정 경로에 변화 없음 = 거절 (빈 커밋 금지)
    C4. 저자 미설정 = 정직한 안내 (특정인 폴백 금지)
    C5. 공유 인덱스 불가침 — 남의 스테이징을 만지지도, 함께 커밋하지도 않는다
    C6. pre-commit 관문 거부 = 커밋 부재 + 거부문 동봉
    C7. 성공 통화 1행 + 메시지 원문 보존(서명 주입 금지) + 신규·삭제 경로
    C8. 이식성 리터럴 부재 — 소스에 원격 호스트·홈 절대경로·push 가 없다

실행: .venv/bin/python -m pytest backend/test_body_commit.py
"""
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile

_BACKEND = os.path.dirname(os.path.abspath(__file__))
_MOD = os.path.join(_BACKEND, "..", "data", "packages", "installed",
                    "tools", "system_essentials", "body_ops.py")


def _load():
    spec = importlib.util.spec_from_file_location("body_commit_under_test", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(root, *args):
    subprocess.run(["git", "-C", root] + list(args), check=True, capture_output=True)


def _make_repo(configure_author=True):
    """임시 저장소: 커밋 1개(tracked.py·other.py) — 각 시험이 제 몸을 받는다(각인은 상태를 바꾼다)."""
    root = tempfile.mkdtemp(prefix="body_commit_")
    _git(root, "init", "-q")
    if configure_author:
        _git(root, "config", "user.name", "t")
        _git(root, "config", "user.email", "t@t")
    for name in ("tracked.py", "other.py"):
        with open(os.path.join(root, name), "w") as f:
            f.write("v1\n")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "생성")
    return root


def _fresh(configure_author=True):
    m = _load()
    r = _make_repo(configure_author)
    m._repo_root = lambda: r
    return m, r


def _head_count(root):
    out = subprocess.run(["git", "-C", root, "rev-list", "--count", "HEAD"],
                         capture_output=True, text=True)
    return int(out.stdout.strip())


def test_c1_paths_required():
    mod, root = _fresh()
    try:
        for bad in ({}, {"paths": []}, {"paths": ["  "]}):
            out = mod.op_commit({"message": "m", **bad})
            assert out["success"] is False and "paths" in out["message"], out
        out = mod.op_commit({"paths": ["tracked.py"]})  # message 누락도 거절
        assert out["success"] is False and "message" in out["message"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_c2_outside_repo_refused():
    mod, root = _fresh()
    try:
        out = mod.op_commit({"message": "m", "paths": ["../밖.py"]})
        assert out["success"] is False and "저장소 밖" in out["message"]
        out = mod.op_commit({"message": "m", "paths": [tempfile.gettempdir()]})
        assert out["success"] is False and "저장소 밖" in out["message"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_c3_no_change_refused():
    mod, root = _fresh()
    try:
        before = _head_count(root)
        out = mod.op_commit({"message": "m", "paths": ["tracked.py"]})
        assert out["success"] is False and "변화가 없습니다" in out["message"]
        assert _head_count(root) == before
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_c4_author_unset_guidance():
    mod, root = _fresh(configure_author=False)
    saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")}
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull   # 시험 기계의 전역 저자가 새지 않게 격리
    os.environ["GIT_CONFIG_SYSTEM"] = os.devnull
    try:
        with open(os.path.join(root, "tracked.py"), "a") as f:
            f.write("v2\n")
        out = mod.op_commit({"message": "m", "paths": ["tracked.py"]})
        assert out["success"] is False and "git config user.name" in out["message"], out
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(root, ignore_errors=True)


def test_c5_shared_index_untouched():
    mod, root = _fresh()
    try:
        # 남(다른 세션)이 공유 인덱스에 other.py 를 스테이징해 둔 상황
        with open(os.path.join(root, "other.py"), "a") as f:
            f.write("남의 작업\n")
        _git(root, "add", "other.py")

        with open(os.path.join(root, "tracked.py"), "a") as f:
            f.write("내 수리\n")
        out = mod.op_commit({"message": "수리", "paths": ["tracked.py"]})
        assert out["success"] is True, out

        # 계약: 남의 스테이징(other.py) 생존 + 내 경로는 유령 스테이징 없음(커밋 후 동기화)
        #       + 내 커밋에 남의 파일 부재
        staged = subprocess.run(["git", "-C", root, "diff", "--cached", "--name-only"],
                                capture_output=True, text=True).stdout.split()
        assert staged == ["other.py"], staged
        shown = subprocess.run(["git", "-C", root, "show", "--name-only", "--format=", "HEAD"],
                               capture_output=True, text=True).stdout.split()
        assert shown == ["tracked.py"], shown
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_c6_precommit_gate_rejection():
    mod, root = _fresh()
    try:
        hooks = os.path.join(root, ".git", "hooks")
        hook = os.path.join(hooks, "pre-commit")
        with open(hook, "w") as f:
            f.write("#!/bin/sh\necho '관문 거부: 시험용'\nexit 1\n")
        os.chmod(hook, os.stat(hook).st_mode | stat.S_IXUSR)
        with open(os.path.join(root, "tracked.py"), "a") as f:
            f.write("v2\n")
        before = _head_count(root)
        out = mod.op_commit({"message": "m", "paths": ["tracked.py"]})
        assert out["success"] is False and "커밋되지 않았습니다" in out["message"]
        assert "관문 거부: 시험용" in out["message"]   # 거부문 원문 동봉 — 침묵 실패 금지
        assert _head_count(root) == before
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_c7_success_currency_and_verbatim_message():
    mod, root = _fresh()
    try:
        with open(os.path.join(root, "tracked.py"), "a") as f:
            f.write("v2\n")
        with open(os.path.join(root, "새파일.py"), "w") as f:
            f.write("신규\n")
        os.unlink(os.path.join(root, "other.py"))
        msg = "각인 시험: 수정+신규+삭제\n\n둘째 줄"
        out = mod.op_commit({"message": msg, "paths": ["tracked.py", "새파일.py", "other.py"]})
        assert out["success"] is True and out["total"] == 1, out
        row = out["items"][0]
        assert row["커밋"] and row["파일수"] == 3 and row["저자"] == "t"
        assert sorted(row["파일"]) == ["other.py", "tracked.py", "새파일.py"]
        assert row["관문"] in ("없음", "통과")
        body = subprocess.run(["git", "-C", root, "log", "-1", "--format=%B"],
                              capture_output=True, text=True).stdout.strip()
        assert body == msg   # 원문 그대로 — 서명·Co-Authored-By 주입 금지 (이식성 계명 4)
        # 작업트리에 남긴 것 없음 (임시 인덱스·잠금 전부 회수)
        assert not os.path.exists(os.path.join(root, ".git", "ibl_body_commit.lock"))
        status = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                                capture_output=True, text=True).stdout.strip()
        assert status == "", status
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_c8_portability_no_personal_literals():
    src = open(_MOD, encoding="utf-8").read()
    lowered = src.lower()
    for banned in ("github", "gitlab", "http://", "https://",
                   "/users/", "c:\\", "/home/",
                   os.path.basename(os.path.expanduser("~")).lower()):  # 이 몸 주인의 계정명
        assert banned not in lowered, f"이식성 위반 리터럴: {banned}"
    # push 는 낱말이 없다 — 전파 서브커맨드가 소스에 존재하지 않아야 한다
    assert '"push"' not in src and "'push'" not in src


if __name__ == "__main__":                      # 러너는 하나 — pytest
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + sys.argv[1:]))
