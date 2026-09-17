"""T3 죽은 이음매 경고 · 타입 검사의 없는 op 거절 · pipe_in 선언의 부패 방지 (2026-09-18)."""
import os, re, sys, glob
sys.path.insert(0, os.path.dirname(__file__)); import boot_paths  # noqa
from ibl_typecheck import typecheck_code

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _warn(code):
    return [i["message"] for i in typecheck_code(code)["issues"] if i["severity"] == "warning" and "이음매" in i["message"]]


def test_empty_non_consumer_after_seam_warns():
    assert _warn('[sense:here] >> [sense:restaurant]{}')
    assert _warn('[sense:weather]{city: "서울"} >> [table:brief]{instruction: "한 줄"} >> [self:notify_user]{}')


def test_legit_seams_stay_quiet():
    assert not _warn('[sense:search]{query: "AI"} >> [self:write]{path: "a.md"}')                     # pipe_in 소비자
    assert not _warn('[sense:search]{query: "AI"} >> [table:take]{n: 3} >> [table:brief]{instruction: "요지"}')
    assert not _warn('[engines:web]{op: "build", site_id: "s"} >> [engines:web]{op: "deploy", site_id: "s"}')   # 성공 의존
    assert not _warn('[limbs:android]{op: "snapshot"} >> [limbs:android]{op: "tap", query: "전송"}')
    assert not _warn('[sense:here] ; [sense:restaurant]{}')                                           # 문장 경계는 이음매 아님
    assert not _warn('[sense:realty]{region: "청주"} >> [table:take]{n: 3} >> [self:notify_user]{message: "$items.title"}')


def test_unknown_op_is_a_typecheck_error():
    r = typecheck_code('[sense:stock]{op: "nope", ticker: "005930"}')
    assert not r["ok"] and any("사용 가능" in i["message"] for i in r["issues"])
    assert typecheck_code('[sense:stock]{op: "quote", ticker: "005930"}')["ok"]


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
