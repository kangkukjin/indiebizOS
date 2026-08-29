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
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"OK — files_from 봉투 {len(fns)}/{len(fns)} 통과")
