"""긴문장 18회차 후속 수리 — 낭비의 뿌리와 부류 관문.

L18-1 도구 호출마다 인자 전체를 네 번 훑던 신원 계산 · L18-2 순수 변환자의 효과 선언(부류 관문) ·
L18-4 Python 계산의 통로를 가리키는 도구 정책 · L18-5 제시→사용 결합의 이름 · L18-7 거절된 프로그램의 조각 수정.
"""
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]
REPRO = ROOT / "docs/experiments/long_sentence_imagination/round_18/repro"


class _Store:
    def __init__(self):
        self.rows = {}

    def evidence(self, text):
        import hashlib
        key = hashlib.sha256(text.encode()).hexdigest()
        self.rows[key] = text
        return {"id": key, "chars": len(text)}

    def read_evidence_across_turns(self, key, offset, limit):
        if key not in self.rows:
            raise KeyError(key)
        return {"id": key, "text": self.rows[key], "chars": len(self.rows[key])}


# ---------------------------------------------------------------- L18-1
def _run(code, inputs=None, tmp_path=None):
    from ibl_v2_entry import handle_request
    request = {"edition": 2, "code": code, "inputs": inputs or {}}
    return handle_request(request, str(tmp_path)) if tmp_path else handle_request(request)


def test_call_identity_walks_arguments_once(monkeypatch):
    """신원 계산이 행 목록을 다시 훑지 않는다 — 큰 값은 digest_packed 한 번, digest 는 작은 신원만 받는다."""
    import ibl_v2_runtime as runtime
    from ibl_v2_ir import pack
    seen, packed_calls = [], []
    real_digest, real_packed = runtime.digest, runtime.digest_packed

    def digest(value):
        if not isinstance(value, str):
            seen.append(len(json.dumps(pack(value), ensure_ascii=False)))
        return real_digest(value)

    def digest_packed(packed):
        packed_calls.append(1)
        return real_packed(packed)

    monkeypatch.setattr(runtime, "digest", digest)
    monkeypatch.setattr(runtime, "digest_packed", digest_packed)
    rows = [{"id": f"T{i:05d}", "n": i, "owner": "팀가"} for i in range(1500)]
    out = _run('$a=$rows >> [table:select]{columns:["id","n"]}\n'
               '$b=$a >> [table:filter]{where:($r)=>$r.n>=1000}\nreturn len($b)', {"rows": rows})
    assert out["success"] and out["value"] == 500, out
    assert len(packed_calls) == 2                      # 도구 호출 두 번, 인자 직렬화도 두 번
    assert max(seen) < 20_000, max(seen)               # 그 밖의 지문은 행 목록을 품지 않는다


def test_same_arguments_keep_same_request_identity_and_changes_are_seen():
    code = '$rows >> [table:select]{columns:["n"]}'
    hashes = []
    for rows in ([{"n": 1}], [{"n": 1}], [{"n": 2}]):
        out = _run(code, {"rows": rows})
        assert out["success"], out
        hashes.append(next(e["request_hash"] for e in out["evidence"] if e.get("request_hash")))
    assert hashes[0] == hashes[1] != hashes[2]


def test_read_reuse_and_resume_survive_the_identity_change(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps([{"k": "x", "n": 1}, {"k": "x", "n": 2}]))
    from ibl_v2_entry import handle_request
    code = '$a=[self:read]{path:"a.json",format:"json"}\n$g=$a.data.items >> [table:groupby]{by:"k",agg:{n:["sum","n"]}}\nreturn $g.items'
    first = handle_request({"edition": 2, "code": code}, str(tmp_path))
    assert first["success"] and first["value"] == [{"k": "x", "n": 3}], first
    again = handle_request({"edition": 2, "code": code + "\n# 고친 뒤", "reuse": {"run_id": first["resume"]["run_id"]}},
                           str(tmp_path))
    assert again["success"] and again["reuse"]["reused_calls"] == 1, again
    resumed = handle_request({"edition": 2, "code": code, "resume": first["resume"]}, str(tmp_path))
    assert resumed["success"] and resumed["value"] == first["value"], resumed


def test_usage_points_at_slow_tool_lines_by_time():
    out = _run('$rows=[{n:1},{n:2}]\n$a=$rows >> [table:select]{columns:["n"]}\nreturn $a')
    lines = out["usage"]["tool_ms_by_line"]
    assert lines and lines[0]["line"] == 2 and lines[0]["calls"] == 1 and lines[0]["actions"] == ["table:select"], lines
    from model_result_view import model_usage
    usage = {"steps": 5, "rows": 0, "elapsed_ms": 61_000, "limits": {"steps": 1_000_000, "rows": 100_000},
             "tool_ms_by_line": [{"line": 37, "ms": 21_000, "calls": 8, "actions": ["table:join"], "source_hash": "s"}]}
    shown = model_usage(usage)
    assert shown["tool_ms_by_line"] == [{"line": 37, "ms": 21_000, "calls": 8, "actions": ["table:join"]}]
    assert "tool_ms_by_line" not in model_usage({**usage, "elapsed_ms": 900})


def test_inventory_is_validated_once_inside_a_tool_call(tmp_path, monkeypatch):
    """도구 호출 범위 안에서는 재고 검증(stat)을 한 번으로 묶고, 범위 밖과 무효화 뒤에는 다시 본다."""
    import vocabulary_state as VS
    package = tmp_path / "data/packages/installed/tools/demo"
    package.mkdir(parents=True)
    (package / "tool.json").write_text(json.dumps({"name": "demo_tool", "input_schema": {"type": "object"}}))
    assert VS.inventory(tmp_path)["tools"] == {"demo_tool": "demo"}
    (package / "tool.json").write_text(json.dumps({"name": "demo_renamed", "input_schema": {"type": "object"}}))
    assert VS.inventory(tmp_path)["tools"] == {"demo_renamed": "demo"}          # 범위 밖: 매번 검증
    with VS.inventory_scope():
        assert VS.inventory(tmp_path)["tools"] == {"demo_renamed": "demo"}
        (package / "tool.json").write_text(json.dumps({"name": "demo_third_name", "input_schema": {"type": "object"}}))
        assert VS.inventory(tmp_path)["tools"] == {"demo_renamed": "demo"}      # 같은 호출 안: 처음 본 재고
        VS.invalidate_inventory()
        assert VS.inventory(tmp_path)["tools"] == {"demo_third_name": "demo"}   # 몸 안의 변경은 곧바로
        monkeypatch.setattr(VS, "_SCOPE_WINDOW_S", 0.0)
        (package / "tool.json").write_text(json.dumps({"name": "demo_fourth_name", "input_schema": {"type": "object"}}))
        assert VS.inventory(tmp_path)["tools"] == {"demo_fourth_name": "demo"}  # 창이 지나면 다시 검증
    assert VS._scope.get() is None


# ---------------------------------------------------------------- L18-2
def test_every_table_transform_declares_its_effect():
    """부류 관문: 값을 받아 값을 내는 변환자가 unknown 으로 남으면 람다·조건 조합이 막힌다.
    unknown 은 기본값이 아니라 근거(관측 상태를 가진 호출)가 있는 선언이어야 한다."""
    import yaml
    nodes = yaml.safe_load((ROOT / "data/ibl_nodes.yaml").read_text(encoding="utf-8"))
    nodes = nodes.get("nodes", nodes)
    vague = []
    for node, body in nodes.items():
        for name, action in ((body or {}).get("actions") or {}).items():
            contract = action.get("callable_contract") if isinstance(action, dict) else None
            if (isinstance(contract, dict) and action.get("group") == "transform"
                    and contract.get("effects") == ["unknown"] and not contract.get("deferred_observation")):
                vague.append(f"{node}:{name}")
    assert not vague, f"효과 미선언 변환자: {vague}"


def test_dedup_composes_inside_a_lambda():
    from ibl_v2_entry import handle_request
    code = (REPRO / "dedup_in_lambda.ibl").read_text(encoding="utf-8")
    checked = handle_request({"edition": 2, "code": code, "check": True})
    assert not checked["issues"], checked["issues"]
    out = handle_request({"edition": 2, "code": code})
    assert out["success"] and out["value"] == [2], out


@pytest.mark.parametrize("code,expected", [
    ('$r=[{a:1,t:"x"},{a:1,t:"y"}] >> [table:rename]{map:{a:"b"}}\nreturn $r.items', [{"b": 1, "t": "x"}, {"b": 1, "t": "y"}]),
    ('$r=[{a:1}] >> [table:rename]{mapping:{a:"b"}}\nreturn $r.items', [{"b": 1}]),
    ('$r=[{k:[1,2]},{k:[3]}] >> [table:flatten]{field:"k"}\nreturn len($r.items)', 3),
    ('$r=[{n:1},{n:2}] >> [table:reduce]{step:"acc + n",init:0}\nreturn $r', None),
])
def test_purified_transforms_still_run(code, expected):
    out = _run(code)
    assert out["success"], out
    if expected is not None:
        assert out["value"] == expected, out


# ---------------------------------------------------------------- L18-4
def test_tool_policy_routes_task_python_to_script_not_shell():
    from providers.codex import CodexProvider
    from providers.claude_code import ClaudeCodeProvider
    for policy in (CodexProvider.TOOL_POLICY, ClaudeCodeProvider.TOOL_POLICY):
        assert "[self:script]" in policy and "~turn/" in policy
        assert "임의 Python" not in policy


def test_codex_session_key_follows_tool_policy(monkeypatch):
    """도구 정책은 fresh 턴 머리에만 실린다 — 정책이 바뀌면 옛 스레드를 잇지 않는다."""
    from providers.codex import CodexProvider
    provider = CodexProvider.__new__(CodexProvider)
    provider.system_prompt = "같은 시스템 프롬프트"
    monkeypatch.setattr(CodexProvider.__mro__[1], "_get_session_key", lambda self: "base", raising=False)
    before = provider._get_session_key()
    monkeypatch.setattr(CodexProvider, "TOOL_POLICY", CodexProvider.TOOL_POLICY + " 바뀐 문장")
    assert provider._get_session_key() != before and before.startswith("base#")


def test_script_guide_does_not_route_authoring_to_run_command():
    """Script 가이드와 가이드 목록 설명이 없는 도구(run_command)로 저작을 보내지 않는다 —
    ep4339: 가이드를 읽은 실행자가 run_command 를 찾다 없어서 셸로 갔다."""
    db = json.loads((ROOT / "data/guide_db.json").read_text(encoding="utf-8"))
    entry = next(g for g in db["guides"] if g.get("file") == "script.md")
    assert "~turn/" in entry["description"] and "저작·디버깅은 run_command" not in entry["description"]
    guide = (ROOT / "data/guides/script.md").read_text(encoding="utf-8")
    assert "write+run_command" not in guide and "run_command 로 스크립트" not in guide


# ---------------------------------------------------------------- L18-5
def test_usage_join_ignores_search_aliases(monkeypatch):
    from types import SimpleNamespace
    from catalog_recall import identity_names
    import associative_recall as AR
    duck = SimpleNamespace(name="DuckDB", aliases=["csv", "sql", "파일 집계"])
    cpm = SimpleNamespace(name="주공정법 (Critical Path Method)", aliases=["선후관계", "여유시간"])
    assert identity_names(duck) == ["DuckDB"]
    assert identity_names(cpm) == ["주공정법 (Critical Path Method)", "주공정법", "Critical Path Method"]
    join = {"names": {"duckdb": identity_names(duck), "critical_path": identity_names(cpm)}}
    untouched = AR._used_names([], join, {"response": "선후관계를 따라 계산했습니다",
                                         "ibl_codes": ['[self:read]{path:"inputs/tasks_a.csv"}']})
    assert untouched == {"used": [], "evidence": "mentioned"}
    named = AR._used_names([], join, {"response": "주공정법으로 임계 작업을 찾았습니다", "ibl_codes": ["import duckdb"]})
    assert sorted(named["used"]) == ["critical_path", "duckdb"]


# ---------------------------------------------------------------- L18-7
LONG = "$rows=[{a:1}]\n" + "\n".join(f"$v{i}={i}" for i in range(60)) + '\n$r=$rows >> [table:rename]{mapping:{a:"b"}}\nreturn $r.items'


def test_rejected_program_is_revised_by_fragment(monkeypatch):
    import model_result_view
    import system_tools_ibl as tools
    store = _Store()
    monkeypatch.setattr(model_result_view, "evidence_store", lambda: store)
    rejected = {"edition": 2, "mode": "check", "executed": False, "ok": False, "status": "invalid",
                "issues": [{"code": "UNKNOWN_ARGUMENT"}]}
    tools._offer_code_revision(rejected, LONG)
    handle = rejected["revise_args"]["code"]
    assert handle.startswith("$rejected:") and "다시 적지" in rejected["revise_hint"]
    resolved, error = tools._resolve_checked_code(
        {"code": handle, "code_edits": [{"old": "mapping:", "new": "map:"}], "check": True})
    assert error is None and resolved == {"code": LONG.replace("mapping:", "map:"), "check": True}
    # 거절분은 고칠 조각 없이 그대로 실행하지 않는다.
    _, error = tools._resolve_checked_code({"code": handle})
    assert error and "code_edits" in error
    # 통과분에도 같은 치환을 얹을 수 있다.
    passed = {"edition": 2, "mode": "check", "executed": False, "ok": True, "status": "valid"}
    tools._offer_checked_code(passed, LONG)
    resolved, error = tools._resolve_checked_code(
        {"code": passed["execute_args"]["code"], "code_edits": [{"old": "$v59=59", "new": "$v59=60"}]})
    assert error is None and "$v59=60" in resolved["code"]


def test_revision_handle_is_not_offered_for_short_or_passing_programs(monkeypatch):
    import model_result_view
    import system_tools_ibl as tools
    monkeypatch.setattr(model_result_view, "evidence_store", lambda: _Store())
    short = {"executed": False, "ok": False, "issues": [{"code": "X"}]}
    tools._offer_code_revision(short, "return $없는값")
    ran = {"executed": True, "success": False, "issues": [{"code": "X"}]}
    tools._offer_code_revision(ran, LONG)
    passed = {"executed": False, "ok": True, "issues": []}
    tools._offer_code_revision(passed, LONG)
    assert all("revise_args" not in result for result in (short, ran, passed))


@pytest.mark.parametrize("edits,fragment", [
    ([{"old": "없는 조각", "new": "x"}], "원문에 없습니다"),
    ([{"old": "$v", "new": "$w"}], "번 나옵니다"),
    ([{"old": "", "new": "x"}], "비어 있지 않은"),
    ([], "1~40개"),
    ([{"old": "mapping:", "new": "map:", "extra": 1}], "code_edits[0]"),
])
def test_code_edits_fail_loudly(edits, fragment):
    import system_tools_ibl as tools
    source, error = tools.apply_code_edits(LONG, edits)
    assert source == LONG and fragment in error
    everywhere, error = tools.apply_code_edits(LONG, [{"old": "$v", "new": "$w", "all": True}])
    assert error is None and "$v" not in everywhere


def test_code_edits_need_a_reference():
    import system_tools_ibl as tools
    request = {"code": "return 1", "code_edits": [{"old": "1", "new": "2"}]}
    assert "참조일 때" in tools._resolve_checked_code(request)[1]


def test_record_site_resolves_code_references_like_the_executor():
    """기록 자리(agent_pipeline tool_start)가 판본 정규화에 이어 code 참조도 원문으로 바꾼다 — 소비자마다가 아니라 한 자리."""
    import re
    src = (ROOT / "backend/cognition/agent_pipeline.py").read_text(encoding="utf-8")
    block = re.search(r'if et == "tool_start":(.*?)elif et == "tool_result":', src, re.DOTALL).group(1)
    resolve, append = block.find("_resolve_checked_code(_input)"), block.find('tool_calls_log.append({"tool_name": _name, "input": _input')
    assert 0 <= block.find("authoring_request(_input)") < resolve < append


def test_resolved_record_lets_recall_usage_see_the_program(monkeypatch):
    import episode_logger
    import model_result_view
    import system_tools_ibl as tools
    import associative_recall as AR
    store = _Store()
    monkeypatch.setattr(model_result_view, "evidence_store", lambda: store)
    monkeypatch.setattr(episode_logger, "record_trajectory_event", lambda *a, **k: None)
    program = 'return [fn:AI동향준비읽기]{폴더:"~workspace/outputs"}'
    passed = {"edition": 2, "mode": "check", "executed": False, "ok": True, "status": "valid"}
    tools._offer_checked_code(passed, program)
    raw = {"code": passed["execute_args"]["code"], "edition": 2}
    phrase = {"id": "4878", "kind": "phrase", "alias": "AI동향준비읽기",
              "code": '#!ibl edition=2\n[def:AI동향준비읽기]($폴더) {\n  return [self:list]{path:$폴더}\n}'}
    presented = [{"source": "hippocampus", "ids": ["4878"], "join": {"items": [phrase]}}]
    blind = AR.record_usage(presented, tool_calls=[{"tool_name": "execute_ibl", "input": raw, "success": True}])
    assert blind[0]["used"] == []
    resolved, error = tools._resolve_checked_code(raw)
    seen = AR.record_usage(presented, tool_calls=[{"tool_name": "execute_ibl", "input": resolved, "success": True}])
    assert error is None and seen[0]["used"] == ["4878"]


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
