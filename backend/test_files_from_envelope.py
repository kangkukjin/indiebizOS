"""files_from 봉투 회귀 — 큰 본문은 도구 호출 JSON 을 통과하지 않는다 (ep2356).

사고(2026-08-30, ep2356): 60KB 한글 마크다운을 인라인 files 로 실었더니 tool_use
JSON 자체가 하네스에서 파싱 실패(InputValidationError) — 서버는 호출을 받지도 못했다.
수리 = files_from(경로 참조): 본문은 임시 파일에, 호출 JSON 에는 경로 한 줄만.

이 시험은 병합 함수(_resolve_files_from)의 계약을 못박는다:
번호 연속·오류 정직 거절(침묵 스킵 금지)·상한·UTF-8 왕복.
표면 3벌(스키마/REST/MCP)의 파라미터 실존은 test_surface_param_parity.py 가 집행한다.

실행: python3 backend/test_files_from_envelope.py  (또는 pytest)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

import system_tools_ibl as sti  # noqa: E402


def _tmp(content: str, suffix=".md") -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False,
                                    encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def test_inline_only_passthrough():
    merged, err = sti._resolve_files_from(["A"], None)
    assert err is None and merged == ["A"]
    merged, err = sti._resolve_files_from(None, None)
    assert err is None and merged == []


def test_paths_appended_after_inline_numbering():
    p = _tmp("경로 본문 — 따옴표 \" 와 \\ 역슬래시, 한글 60KB 부류")
    try:
        merged, err = sti._resolve_files_from(["인라인"], [p])
        assert err is None
        assert merged[0] == "인라인"          # $file:0
        assert merged[1].startswith("경로 본문")  # $file:1 — 번호 연속
    finally:
        os.unlink(p)


def test_korean_content_roundtrip():
    body = "# 부동산 발굴 보고서 — 서울 은평·서대문\n" * 2000  # ~수십 KB 한글
    p = _tmp(body)
    try:
        merged, err = sti._resolve_files_from(None, [p])
        assert err is None and merged == [body]
    finally:
        os.unlink(p)


def test_missing_path_is_honest_error():
    merged, err = sti._resolve_files_from(None, ["/no/such/file_ep2356.md"])
    assert err and "없습니다" in err  # 침묵 스킵 금지


def test_non_list_and_non_str_rejected():
    _, err = sti._resolve_files_from(None, "path.md")
    assert err
    _, err = sti._resolve_files_from(None, [123])
    assert err


def test_cap_enforced():
    p = _tmp("x" * (sti._FILES_FROM_CAP_BYTES + 1))
    try:
        _, err = sti._resolve_files_from(None, [p])
        assert err and "상한" in err
    finally:
        os.unlink(p)


def test_substitution_uses_merged_list():
    """병합된 목록이 기존 $file:N 치환기와 그대로 맞물린다."""
    p = _tmp("본문B")
    try:
        merged, err = sti._resolve_files_from(["본문A"], [p])
        assert err is None
        params = {"content": "$file:0 / $file:1"}
        sti._replace_file_refs_in_dict(params, merged)
        assert params["content"] == "본문A / 본문B"
    finally:
        os.unlink(p)


if __name__ == "__main__":
    # 러너는 하나 — pytest 에 위임 (test_single_runner 규약).
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))


# ── $file:N 치환 자체의 계약 (2026-09-06 ep2884) ──────────────────────────────
# 옛 판은 인덱스 순서로 str.replace 를 반복해 `$file:1` 이 `$file:10` 의 접두를 먼저 먹었다
# (시험 파일 제안에 episode_logger 본문+"0" 이 실렸다). 한 패스 정규식으로 못박는다.

def _steps(**params):
    return [{"node": "self", "action": "write", "params": dict(params)}]


def test_file_ref_two_digit_index_is_one_token():
    files = [f"F{i}" for i in range(12)]
    st = _steps(content="$file:10", old="$file:1", both="$file:11/$file:1/$file:0")
    unresolved = sti._replace_file_refs_in_steps(st, files)
    assert unresolved == set()
    assert st[0]["params"]["content"] == "F10", st[0]["params"]
    assert st[0]["params"]["old"] == "F1"
    assert st[0]["params"]["both"] == "F11/F1/F0"


def test_file_ref_inserted_content_is_not_rescanned():
    # 0번 본문이 "$file:1" 이라는 글자를 품어도 1번 내용으로 다시 치환되지 않는다
    files = ["본문에 $file:1 이라는 글자", "B"]
    st = _steps(content="$file:0")
    sti._replace_file_refs_in_steps(st, files)
    assert st[0]["params"]["content"] == "본문에 $file:1 이라는 글자"


def test_file_ref_out_of_range_is_reported_not_silently_written():
    files = ["A"]
    st = _steps(content="$file:0 + $file:7", nested={"k": ["$file:3"]})
    unresolved = sti._replace_file_refs_in_steps(st, files)
    assert unresolved == {"$file:7", "$file:3"}
    assert st[0]["params"]["content"] == "A + $file:7"      # 범위 밖은 그대로(호출자가 거절)


def test_file_ref_recurses_branches_and_fallback_chain():
    files = ["X", "Y"]
    st = [{"type": "parallel", "branches": _steps(content="$file:0"),
           "_fallback_chain": _steps(content="$file:1")}]
    sti._replace_file_refs_in_steps(st, files)
    assert st[0]["branches"][0]["params"]["content"] == "X"
    assert st[0]["_fallback_chain"][0]["params"]["content"] == "Y"
