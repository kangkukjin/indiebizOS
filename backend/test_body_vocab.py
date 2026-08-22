"""[self:body] 몸 변화 회상 어휘 배터리 (2026-08-21 신설)

계약 프로브(체크리스트 5.5) — 통화 승격·절단 신고·실패의 정직성·이동 추적을 실측.

    T1. changes: 커밋 변화 + 미커밋 작업분, 영역 열, total/truncated 정직
    T2. changes: 이름변경이 상태=이동 + 이전경로 로 잡힘 (-M)
    T3. file: --follow 가 이동을 관통해 생성 커밋까지 (일생)
    T4. 정직 거절: git 없음 / file op path 누락 / 미추적 파일 구분 / 저장소 밖 경로
    T5. limit: 초과 요청 신고 후 상한 (침묵 클램프 금지) + 절단 truncated
    T6. path 스코프: 하위 폴더만
    T7. log: 커밋 단위 행 + 파일수

실행: python3 backend/test_body_vocab.py
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

_BACKEND = os.path.dirname(os.path.abspath(__file__))
_MOD = os.path.join(_BACKEND, "..", "data", "packages", "installed",
                    "tools", "system_essentials", "body_ops.py")


def _load():
    spec = importlib.util.spec_from_file_location("body_ops_under_test", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(root, *args):
    subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@t"]
                   + list(args), check=True, capture_output=True)


def _make_repo():
    """임시 저장소: 커밋 3개(생성→이동→수정) + 미커밋 1건."""
    root = tempfile.mkdtemp(prefix="body_vocab_")
    _git(root, "init", "-q")
    os.makedirs(os.path.join(root, "backend", "old"))
    with open(os.path.join(root, "backend", "old", "mod.py"), "w") as f:
        f.write("v1\n" * 30)
    with open(os.path.join(root, "readme.md"), "w") as f:
        f.write("hi\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "생성: mod.py")
    os.makedirs(os.path.join(root, "backend", "new"))
    _git(root, "mv", "backend/old/mod.py", "backend/new/mod.py")
    _git(root, "commit", "-qm", "이동: old→new 층 분리")
    with open(os.path.join(root, "backend", "new", "mod.py"), "a") as f:
        f.write("v2\n")
    _git(root, "commit", "-qam", "수정: v2")
    with open(os.path.join(root, "uncommitted.txt"), "w") as f:
        f.write("작업 중\n")
    return root


def test_t1_changes_currency(mod):
    out = mod.op_changes({"days": 30})
    assert out["success"] and out["total"] == len(out["items"]) or out["truncated"]
    files = {r["파일"] for r in out["items"]}
    assert "uncommitted.txt" in files, "미커밋 작업분 누락"
    assert any(r["상태"] == "미커밋" for r in out["items"])
    row = next(r for r in out["items"] if r["파일"] == "backend/new/mod.py" and r["상태"] == "수정")
    assert row["영역"] == "backend/new", f"영역 파생 오류: {row['영역']}"
    assert row["요지"] == "수정: v2" and row["커밋"] and row["시각"]


def test_t2_rename_detected(mod):
    out = mod.op_changes({"days": 30})
    moves = [r for r in out["items"] if r["상태"] == "이동"]
    assert moves, "이동이 안 잡힘 (-M 누락?)"
    assert moves[0]["파일"] == "backend/new/mod.py"
    assert moves[0]["이전경로"] == "backend/old/mod.py"


def test_t3_file_follow_lifetime(mod):
    out = mod.op_file({"path": "backend/new/mod.py"})
    assert out["success"] and out["total"] == 3, f"일생 3건이어야: {out['total']}"
    assert "생성" in out["text"] and "이동 1회" in out["text"]
    oldest = out["items"][-1]
    assert oldest["상태"] == "추가" and oldest["파일"] == "backend/old/mod.py", \
        "--follow 가 이동 전 원경로의 생성까지 못 갔음"


def test_t4_honest_refusals(mod):
    saved = mod._repo_root
    mod._repo_root = lambda: None
    try:
        out = mod.op_changes({})
        assert out["success"] is False and "git 저장소가 아닙니다" in out["message"]
    finally:
        mod._repo_root = saved
    out = mod.op_file({})
    assert out["success"] is False and "path" in out["message"], "path 누락 정직 거절 실패"
    out = mod.op_file({"path": "uncommitted.txt"})
    assert out["success"] and out["total"] == 0 and "커밋된 적 없음" in out["text"], \
        "미추적 파일 구분 보고 실패"
    out = mod.op_file({"path": "no/such/file.py"})
    assert out["total"] == 0 and "경로 확인" in out["text"]
    out = mod.op_changes({"path": "/etc"})
    assert out["success"] is False and "저장소 밖" in out["message"]


def test_t5_limit_honesty(mod):
    out = mod.op_changes({"days": 30, "limit": 5000})
    assert "limit 5000→1000" in out["text"], "상한 클램프 신고 누락 (침묵 클램프!)"
    out = mod.op_changes({"days": 30, "limit": 1})
    assert out["truncated"] is True and len(out["items"]) == 1 and out["total"] > 1
    assert "1건만 표시" in out["text"]


def test_t6_path_scope(mod):
    out = mod.op_changes({"days": 30, "path": "backend"})
    files = {r["파일"] for r in out["items"]}
    assert all(f.startswith("backend/") for f in files), f"스코프 누수: {files}"
    assert "readme.md" not in files and "uncommitted.txt" not in files


def test_t7_log_commits(mod):
    out = mod.op_log({"days": 30})
    assert out["success"] and out["total"] == 3
    assert [r["요지"] for r in out["items"]] == ["수정: v2", "이동: old→new 층 분리", "생성: mod.py"]
    assert out["items"][0]["파일수"] == 1 and out["items"][0]["커밋"]


def main():
    mod = _load()
    root = _make_repo()
    mod._repo_root = lambda: root  # 몸=임시 저장소로 주입
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    try:
        for name, fn in tests:
            try:
                fn(mod)
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(1 if failed else 0)


# pytest 수집 호환 — mod 를 fixture 로 공급 (test_grep_glob_dialect 선례)
try:
    import pytest

    @pytest.fixture(scope="module", name="mod")
    def _mod_fixture():
        m = _load()
        r = _make_repo()
        m._repo_root = lambda: r
        yield m
        shutil.rmtree(r, ignore_errors=True)
except ImportError:
    pass


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
