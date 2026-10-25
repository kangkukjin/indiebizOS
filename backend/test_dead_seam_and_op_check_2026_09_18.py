"""T3 죽은 이음매 경고 · 타입 검사의 없는 op 거절 · pipe_in 선언의 부패 방지 (2026-09-18)."""
import os, re, sys, glob
sys.path.insert(0, os.path.dirname(__file__)); import boot_paths  # noqa
from ibl_typecheck import typecheck_code

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))










def test_pipe_in_declaration_matches_handlers_that_read_prev():
    """소비자 선언의 부패 방지: 패키지가 _prev_result 를 읽는데 그 패키지의 비변환 액션 어디에도
    pipe_in/flow 선언이 없으면 T3 가 정당한 이음매를 죽었다고 말하게 된다."""
    import yaml
    missing = []
    for ya in glob.glob(os.path.join(ROOT, "data/packages/installed/tools/*/ibl_actions.yaml")):
        pkg = os.path.dirname(ya)
        reads = any("_prev_result" in line and not line.lstrip().startswith("#")
                    for f in glob.glob(os.path.join(pkg, "*.py")) for line in open(f, encoding="utf-8", errors="ignore"))
        if not reads:
            continue
        text = open(ya, encoding="utf-8").read()
        if not re.search(r"^\s+pipe_in:\s*true", text, re.M) and "returns: transform" not in text and not re.search(r"^\s+flow:", text, re.M):
            missing.append(os.path.basename(pkg))
    assert not missing, f"_prev_result 를 읽는데 소비자 선언이 없는 패키지: {missing}"


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
