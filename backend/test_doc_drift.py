"""문서 드리프트 감사 배터리 (doc_drift.py) — T1~T6.

실행: python3 backend/test_doc_drift.py  (또는 pytest)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

from doc_drift import (  # noqa: E402
    _check_dates, _check_dead_refs, _check_stats_claims,
    _collect_ident_tokens, _is_historical, _mask, measure,
    _script_args_flags, _script_desc_args,
)

FACTS = {"node_count": 6, "total": 149, "tools_n": 41, "exts_n": 5}


def test_t1_stale_compound_claim_flagged():
    text = "시스템은 6노드 144 액션을 갖는다.\nIt has 6 nodes, 144 composable actions."
    flags = _check_stats_claims("x.md", text, FACTS)
    assert len(flags) == 2, flags
    assert flags[0]["kind"] == "stats_claim"
    # 정확한 현재값은 깃발 없음
    assert not _check_stats_claims("x.md", "6노드 149 액션", FACTS)


def test_t2_historical_lines_skipped():
    for line in [
        "*마지막 업데이트: 2026-08-17 — 당시 6노드 144 액션이었다*",
        "압축으로 163→144, 즉 6노드 144 액션이 됐다",
        "332개에서 144개로 줄었다 — 6노드 144 액션",
        "`old_action` 은퇴 — 당시 6노드 142 액션",
        "이전(2026-08-06) — 6노드 150 액션",
    ]:
        assert _is_historical(line), line
        assert not _check_stats_claims("x.md", line, FACTS), line


def test_t3_marker_and_fence_masked():
    text = ("<!-- IBL_STATS:START -->\n6노드 144 액션\n<!-- IBL_STATS:END -->\n"
            "```\n6노드 100 액션\n```\n본문 주장 6노드 149 액션")
    masked = _mask(text)
    assert "144" not in masked and "100" not in masked
    assert "149" in masked
    # 마스킹은 줄 수를 보존한다 (깃발 line 번호 정확성)
    assert masked.count("\n") == text.count("\n")


def test_t4_date_mismatch():
    doc = "---\nlast_updated: 2026-08-17\n---\n본문\n*마지막 업데이트: 2026-08-20 — x*\n"
    flags = _check_dates("x.md", doc)
    assert flags and flags[0]["kind"] == "date_mismatch"
    ok = "---\nlast_updated: 2026-08-21\n---\n*최종 업데이트: 2026-08-20 — x*\n"
    assert not _check_dates("x.md", ok)


def test_t5_dead_refs():
    # 죽은 식별자·죽은 파일은 깃발, 산 것·슬래시 축약 관용구는 통과
    # ※식별자 대조는 코드 *본문 문자열* 기준 — 주석·docstring 의 언급도 '산 것'으로
    #   친다(grep 수준 정밀도). 그래서 시험용 죽은 식별자는 이 파일에도 리터럴로 안
    #   적히도록 런타임에 조립한다(이 파일 자신이 코퍼스에 들어가 자기오염되기 때문).
    dead_fn = "zz_" + "dead" + "_fn" + "_qq"
    dead_py = "no_" + "such" + "_module" + "_xyz.py"
    tokens = _collect_ident_tokens(
        f"배관은 `{dead_fn}()` 가 담당하고 `{dead_py}` 를 읽는다.\n"
        "현행은 `world_pulse_health.run_maintenance_bundle` 이고 `doc_drift.py` 가 산다.\n"
        "표면 조립은 `launcher_surface_remote/phone.py` 두 모듈.\n"
    )
    flags = []
    _check_dead_refs(flags, {"x.md": tokens})
    claims = {f["claim"] for f in flags}
    assert f"{dead_fn}()" in claims, flags
    assert dead_py in claims, flags
    assert not any("run_maintenance_bundle" in c for c in claims), flags
    assert not any("doc_drift.py" == c for c in claims), flags
    assert not any("launcher_surface" in c for c in claims), flags


def test_t7_script_registry_args_drift():
    # 사고 재현(2026-08-30): 소스는 value 를 읽는데 설명 args 나열에 없다 → 깃발
    desc = "JSON 원장 갱신 — args: path, op(append|upsert|set), target(선택), item|items, key(기본 id)"
    src = 'args.get("path")\nargs.get("op")\nargs.get("target")\nargs.get("item")\n' \
          'args.get("items")\nargs.get("key")\n"value" not in args\nargs["value"]\n'
    flags = _script_args_flags("json원장", desc, src)
    assert len(flags) == 1 and "value" in flags[0]["claim"], flags
    # 설명에 value 가 오르면 깃발 0
    assert not _script_args_flags("json원장", desc + ", value(set 전용)", src)
    # 역방향: 설명에만 있는 인자(소스가 안 읽음)도 깃발
    ghost = _script_args_flags("x", "요약 — args: path, ghost_arg", 'args.get("path")')
    assert len(ghost) == 1 and "ghost_arg" in ghost[0]["claim"], ghost
    # 단어 경계 — 'n' 은 설명 산문의 부분 문자열('Wilson')로는 못 숨는다
    hid = _script_args_flags("y", "Wilson CI 측정 — args: relevant", 'args.get("relevant") or args.get("n")')
    assert len(hid) == 1 and hid[0]["claim"].endswith("args: n"), hid
    # 괄호 안 값 후보(append|upsert|set)·대괄호 예시는 인자로 오해하지 않는다
    toks = _script_desc_args("args: repos:[owner/repo,...] 또는 query, op(a|b), limit(기본 60). 꼬리 설명")
    assert toks == ["repos", "query", "op", "limit"], toks
    # 'args:' 나열이 아예 없고 소스도 인자를 안 읽으면 깃발 0
    assert not _script_args_flags("z", "인자 없는 요약 스크립트", "print(1)")


def test_t6_real_repo_clean():
    # 불변식: 실저장소는 깃발 0 을 유지한다 (2026-08-21 대청소 이후).
    # 깃발이 생기면 문서를 고치든 은퇴 표기를 하든 — 이 감사가 그 강제 장치다.
    r = measure()
    assert not r["flags"], r["flags"]
    assert not r["unchecked"], r["unchecked"]


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {t.__name__}: {e}")
    print(f"[test_doc_drift] {len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


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
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
