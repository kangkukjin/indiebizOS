"""[self:grep] 2층 글롭 방언 드리프트 회귀 배터리 (2026-08-21 수리)

수리 신호(사용자 재보고): path=backend, file_pattern='*.py' 가 하위 디렉토리로
재귀하지 않고, 오류 없이 부분 결과를 전체인 양 반환.

진단: rg 고속 경로는 '--glob *.py' 를 gitignore 방언(전 깊이 basename 매칭)으로
읽는데, 파이썬 폴백은 glob.glob(root/'*.py', recursive=True) — recursive=True 는
'**' 를 켤 뿐이라 최상위만 봤다. 같은 질의가 어느 층을 타느냐(한글 패턴의
isascii 게이트·rg 부재·rg exit 2)에 따라 모집단이 조용히 갈리는 침묵 부분결과.
어휘 광고(ibl_actions.yaml)가 file_pattern='*.py' 를 예시로 들므로 rg 의미가 계약.

    T1. 한글 패턴 + '*.py' → 전 깊이 재귀 (신고된 버그 재현 케이스)
    T2. rg 경로 vs 파이썬 경로 파일 집합 동일 (방언 드리프트 재발 가드)
    T3. 구분자 있는 패턴('sub/*.py')의 앵커 의미 보존
    T4. '**/*.py' 명시 패턴 기존 동작 회귀 없음
    T5. cp949 옛 한글 파일 폴백 검색 유지 (2026-07-24 수리 회귀)

실행: python3 backend/test_grep_glob_dialect.py
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

_BACKEND = os.path.dirname(os.path.abspath(__file__))
_FS_GREP = os.path.join(_BACKEND, "..", "data", "packages", "installed",
                        "tools", "system_essentials", "fs_grep.py")


def _load_fs_grep():
    spec = importlib.util.spec_from_file_location("fs_grep_under_test", _FS_GREP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fs_grep = _load_fs_grep()

ASCII_MARK = "DIALECT_MARK_7f3a"
KO_MARK = "방언정렬마커"


def _make_tree():
    """3깊이 파이썬 파일 + 잡음 + cp949 파일이 든 임시 트리."""
    root = tempfile.mkdtemp(prefix="grep_dialect_")
    layout = {
        "a.py": f"top level\n{ASCII_MARK}\n{KO_MARK}\n",
        "sub/b.py": f"depth one\n{ASCII_MARK}\n{KO_MARK}\n",
        "sub/deep/c.py": f"depth two\n{ASCII_MARK}\n{KO_MARK}\n",
        "sub/noise.txt": f"{ASCII_MARK}\n{KO_MARK}\n",  # *.py 밖 — 매칭되면 안 됨
    }
    for rel, content in layout.items():
        fp = os.path.join(root, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(content)
    # 옛 한글(cp949) 파일 — 인코딩 폴백 회귀 가드
    with open(os.path.join(root, "sub", "old_cp949.py"), "wb") as f:
        f.write(f"# 옛 문서\n{KO_MARK}\n".encode("cp949"))
    return root


def _run(root, **kw):
    tool_input = {"pattern": kw.pop("pattern"), **kw}
    out = json.loads(fs_grep.run(tool_input, root))
    return out, {item["파일"] for item in out.get("items", [])}


PY_FILES = {"a.py", os.path.join("sub", "b.py"), os.path.join("sub", "deep", "c.py"),
            os.path.join("sub", "old_cp949.py")}


def test_t1_korean_pattern_recurses(root):
    """T1(신고 버그): 한글 패턴은 isascii 게이트로 파이썬 폴백 확정 — '*.py' 가 전 깊이."""
    out, files = _run(root, pattern=KO_MARK, path=root, file_pattern="*.py")
    assert files == PY_FILES, f"한글 패턴 '*.py' 재귀 실패: {sorted(files)}"
    assert os.path.join("sub", "deep", "c.py") in files


def test_t2_rg_py_dialect_equivalence(root):
    """T2(재발 가드): 같은 질의를 두 층에 강제 실행 — 파일 집합이 일치해야 한다."""
    if not fs_grep._RG_BIN:
        print("  (rg 부재 — T2 동일성 비교 생략, 파이썬 경로 단독 검증)")
        return
    args = (ASCII_MARK, root, "*.py", False, 100, 500, 40_000)
    rg_out = fs_grep._rg_grep(*args)
    assert rg_out is not None, "rg 경로 실행 실패"
    rg_files = {os.path.relpath(r[0], root) for r in rg_out[0]}
    py_rows = fs_grep._py_grep(*args)[0]
    py_files = {os.path.relpath(r[0], root) for r in py_rows}
    assert rg_files == py_files, f"방언 드리프트: rg={sorted(rg_files)} py={sorted(py_files)}"
    # cp949 파일은 ASCII 패턴이면 양쪽 다 바이트 동일이라 잡혀야 정상 — 단 이 파일엔
    # ASCII_MARK 가 없으므로 양쪽 다 빠지는 게 맞다(집합 동일성만이 계약).
    assert os.path.join("sub", "deep", "c.py") in py_files


def test_t3_anchored_pattern_preserved(root):
    """T3: 구분자 있는 'sub/*.py' 는 그 자리만 — '**/' 자동 접두가 앵커를 깨면 안 된다."""
    out, files = _run(root, pattern=KO_MARK, path=root, file_pattern="sub/*.py")
    expect = {os.path.join("sub", "b.py"), os.path.join("sub", "old_cp949.py")}
    assert files == expect, f"앵커 의미 훼손: {sorted(files)}"


def test_t4_explicit_doublestar_regression(root):
    """T4: 명시 '**/*.py' 기존 동작 회귀 없음."""
    out, files = _run(root, pattern=KO_MARK, path=root, file_pattern="**/*.py")
    assert files == PY_FILES, f"'**/*.py' 회귀: {sorted(files)}"


def test_t5_cp949_fallback_kept(root):
    """T5: cp949 옛 한글 파일이 인코딩 폴백으로 여전히 잡힌다 (07-24 수리 회귀 가드)."""
    out, files = _run(root, pattern=KO_MARK, path=root, file_pattern="*.py")
    assert os.path.join("sub", "old_cp949.py") in files, "cp949 폴백 회귀"


# pytest 수집 호환 — testpaths=backend 가 이 파일을 집으므로 root 를 fixture 로도 공급
try:
    import pytest

    @pytest.fixture(scope="module", name="root")
    def _root_fixture():
        r = _make_tree()
        yield r
        shutil.rmtree(r, ignore_errors=True)
except ImportError:
    pass


def main():
    root = _make_tree()
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    try:
        for name, fn in tests:
            try:
                fn(root)
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
