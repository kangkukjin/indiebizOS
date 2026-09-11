"""문서 드리프트 감사 배터리 (doc_drift.py) — T1~T6.

실행: python3 backend/test_doc_drift.py  (또는 pytest)
"""
import os
import sys
from pathlib import Path
import shutil
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

from doc_drift import (  # noqa: E402
    _check_dates, _check_dead_refs, _check_stats_claims,
    _collect_ident_tokens, _is_historical, _mask, measure,
    _script_args_flags, _script_desc_args, _untracked_script_flags,
)

FACTS = {"node_count": 6, "total": 149, "tools_n": 41, "exts_n": 5}


@pytest.fixture
def generated_docs(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    import iblbuild_docs as build
    import yaml
    shutil.copytree(root / "docs/generated_templates", tmp_path / "docs/generated_templates")
    for rel, *_ in build.DOC_TARGETS:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rel, dest)
    facts = build.collect_doc_facts(root, yaml.safe_load((root / "data/ibl_nodes.yaml").read_text()))
    return build, facts, tmp_path


def test_generated_markers_replace_arbitrary_old_prose_but_preserve_surroundings(generated_docs):
    build, facts, root = generated_docs
    for rel in dict.fromkeys(t[0] for t in build.DOC_TARGETS):
        expected, issues = build._render_doc(root, rel, facts)
        assert not issues
        original = (root / rel).read_text()
        for path, start, end, _ in build.DOC_TARGETS:
            if path == rel:
                pre, rest = original.split(start)
                _, post = rest.split(end)
                original = pre + start + "\n문장 형식도 숫자도 없는 오래된 구간\n" + end + post
        (root / rel).write_text(original)
        rendered, issues = build._render_doc(root, rel, facts)
        assert not issues and rendered == expected
        (root / rel).write_text(rendered)
        assert build._render_doc(root, rel, facts) == (rendered, [])


def test_generated_tables_follow_registry_sets_and_keep_curated_descriptions(generated_docs):
    build, facts, root = generated_docs
    facts["nodes"]["newnode"] = 9
    facts["node_descriptions"]["newnode"] = "새 노드 | 설명"
    facts["packages"] = [("newpkg", "New", "새 설명 | 전체"), ("radio", "ignored", "ignored")]
    readme, issues = build._render_doc(root, "README.md", facts)
    assert not issues and "| **newnode** | 9 | 새 노드 \\| 설명 |" in readme
    packages, issues = build._render_doc(root, "data/system_docs/packages.md", facts)
    assert not issues
    assert "| newpkg | New | 새 설명 \\| 전체 |" in packages
    assert "| radio | Radio | 인터넷 라디오 검색 및 재생 |" in packages
    assert "| android |" not in packages


def test_grammar_examples_parse_and_surfaces_share_operator_contracts(generated_docs):
    import json
    from ibl_parser import parse
    build, facts, root = generated_docs
    operators = json.loads((root / "docs/generated_templates/ibl_grammar.json").read_text())["operators"]
    assert {o["symbol"] for o in operators} == {">>", "&", "??", ";"}
    for entry in operators:
        assert parse(entry["example"])
    for rel in ("data/system_docs/ibl.md", "data/common_prompts/fragments/12_ibl_only.md",
                "data/common_prompts/fragments/12_ibl_compact.md"):
        rendered, issues = build._render_doc(root, rel, facts)
        assert not issues
        span = rendered.split("<!-- GRAMMAR_OPERATORS:START -->")[1].split("<!-- GRAMMAR_OPERATORS:END -->")[0]
        assert all(f"`{o['symbol']}`" in span for o in operators)
        assert "0건" in span  # 빈 결과 폴백을 실패 전용으로 축약하지 않는다.


@pytest.mark.parametrize("damage", ["missing", "duplicate", "reversed", "unknown_slot", "missing_template"])
def test_generated_docs_fail_honestly_on_broken_source(generated_docs, damage):
    build, facts, root = generated_docs
    rel = "README.md"
    path = root / rel
    text = path.read_text()
    start, end = build.IBL_STATS_START, build.IBL_STATS_END
    template = root / "docs/generated_templates/readme_en.md"
    if damage == "missing":
        text = text.replace(end, "")
    elif damage == "duplicate":
        text += end
    elif damage == "reversed":
        text = text.replace(start, "TEMP").replace(end, start).replace("TEMP", end)
    elif damage == "unknown_slot":
        template.write_text("{{unknown_fact}}")
    else:
        template.unlink()
    path.write_text(text)
    _, issues = build._render_doc(root, rel, facts)
    assert issues
    assert path.read_text() == text


def test_unchecked_document_is_not_reported_as_success(tmp_path, monkeypatch):
    import doc_drift
    monkeypatch.setattr(doc_drift, "_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(doc_drift, "_FLAGS_PATH", tmp_path / "flags.json")
    monkeypatch.setattr(doc_drift, "measure", lambda: {"flags": [], "unchecked": ["unreadable.md"]})
    result = doc_drift.run_doc_drift_check(force=True)
    assert not result["success"] and result["data_quality"] == "audit_incomplete"
    assert result["error_message"]
    assert doc_drift._should_run()  # 다음 유지보수 때 다시 검사한다.


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


def test_t8_registry_points_at_untracked_source():
    # 사고 재현(2026-09-07 b812bd68): 설명(registry.yaml)만 커밋하고 소스는 워킹 트리에
    # 두면 args 대조는 워킹 트리를 읽어 초록이 된다 — 초록의 근거가 저장소 밖에 선다.
    # 깨끗한 클론에서만 되살아나므로 '추적되는가' 를 따로 묻는다.
    tracked = {"산다.py"}
    flags = _untracked_script_flags([("등록", "없다.py"), ("멀쩡", "산다.py")], tracked)
    assert len(flags) == 1, flags
    assert flags[0]["kind"] == "script_untracked" and "없다.py" in flags[0]["claim"], flags
    # 소스가 같은 커밋에 실리면 깃발 0
    assert not _untracked_script_flags([("등록", "없다.py")], tracked | {"없다.py"})
    # file 이 빈 항목은 이 검사의 몫이 아니다(읽기 실패가 unchecked 로 잡는다)
    assert not _untracked_script_flags([("빈칸", "")], tracked)


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
