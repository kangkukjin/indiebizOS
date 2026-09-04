"""해마 원장 구문 관문 회귀 — "이게 IBL 로 파싱되나"를 묻는 곳이 원장 문에 있어야 한다 (2026-09-02).

재현하는 결함(실측 id 4374): 반성기가 JSON 을 이중으로 감싼 출력을 내자 바깥 봉투는 정상
파싱됐고 `code` 칸에 안쪽 봉투가 통째로 들어갔다. 소유(code_is_own)·액션 실존
(_validate_ibl_actions)·인자(check_code_params) 세 게이트는 전부 `[node:action]` 정규식
수준이라 그 문자열을 통과시켰고, 인자 게이트는 파싱 실패를 [] 로 삼켰다. 그 행 하나가
pre-commit 코퍼스 검사(build_ibl_nodes --check)를 막아 저장소 전체의 커밋을 세웠다.

고정하는 계약 네 가지:
  G1  정규화는 *명백한* 포장(코드펜스·{"code": …} 봉투)만 벗기고 산문 접두는 벗기지 않는다
      — 어디까지가 코드인지 추측해 벗기면 창작이고, 창작된 용례는 해마가 영구 재생산한다.
  G2  원장 문(add_example / add_examples_batch)이 파싱 불가 용례를 거절한다. 검증자가
      비어 있으면 통과가 아니라 예외(fail-closed) — 등록을 잊으면 조용히 사라지는 관문은 주석이다.
  G3  배선처는 조립 뿌리 boot_paths 한 곳이다: `import boot_paths` 만으로 꽂히고(지연 import
      라 부트 비용 0), boot_paths 를 안 거친 프로세스는 문 앞에서 시끄럽게 죽는다.
      ★진입점마다 `import ibl_param_vocab` 를 손으로 심는 스윕은 샜다(패키지 설치·프로비전·
        수리 스크립트). 규칙은 파생본에 전개하지 않는다.
  G4  기록기(distill_experience)는 구문을 인자 게이트보다 *먼저* 묻는다 — 인자 게이트가
      파싱 실패를 [] 로 돌려주므로 순서가 곧 계약이다.
  G5  (2026-09-04, ep2777·2806) 증류 프롬프트에 `[node:action]` 형태 자리표를 두지 않는다 —
      경량 반성기가 자리표를 글자 그대로 베끼거나(`[node:self:edit]`), 실행 코드의
      `node:` 인자 값을 자리표의 node 자리에 대입한다(`[가족/어머니:memory]`). 09-03 부터
      `node` 가 [self:memory] 의 인자 이름이 되면서 낱말이 충돌한 것이 뿌리. 두 모양은
      구문 관문이 거절하고, 파싱은 되지만 실행에 없던 머리는 머리 접지 게이트가 거절한다.

실행: .venv/bin/python -m pytest backend/test_hippo_syntax_gate.py -q
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

BACKEND = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# 실측 원문(백업 data/_backups/2026-09-02_corpus_malformed_row/): code 칸에 들어앉은 안쪽 봉투.
MALFORMED_ROW = ('{"intent": "최근 출시된 AI 소프트웨어의 기능·평가·비교 조사", '
                 '"code": "[sense:search]{query: ""OpenClaw 2.0" AI release", limit: 10} '
                 '& [sense:search]{query: "OpenClaw 2.0 review", limit: 10}"}')
GOOD = '[sense:search]{query: "OpenClaw 2.0 review", limit: 10}'


# ---------------------------------------------------------------- G1 정규화
def test_g1_normalize_strips_only_obvious_wrapping():
    from ibl_param_vocab import normalize_corpus_code
    assert normalize_corpus_code(GOOD) == GOOD
    assert normalize_corpus_code("```ibl\n" + GOOD + "\n```") == GOOD
    assert normalize_corpus_code(json.dumps({"intent": "x", "code": GOOD})) == GOOD
    # 산문 접두·번호매김은 벗기지 않는다 — 창작 금지
    for prose in ("다음 코드를 실행: " + GOOD, "1. " + GOOD):
        assert normalize_corpus_code(prose) == prose


def test_g1_malformed_row_rejected_even_after_normalize():
    from ibl_param_vocab import normalize_corpus_code, code_syntax_error
    assert code_syntax_error(normalize_corpus_code(MALFORMED_ROW)) is not None
    assert code_syntax_error("") is not None
    for ok in (GOOD, "[sense:search]{query: \"a\"} >> [table:take]{n: 3}",
               "[self:time] & [self:time]"):
        assert code_syntax_error(ok) is None, ok


# ---------------------------------------------------------------- G2 원장 문
@pytest.fixture
def db(tmp_path, monkeypatch):
    """임시 DB 위의 IBLUsageDB — 라이브 해마·모델·vec 무접촉."""
    import ibl_usage_db as mod
    monkeypatch.setattr(mod, "DB_PATH", str(tmp_path / "usage.db"))
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "_start_background_model_load",
                        classmethod(lambda cls: None))
    monkeypatch.setattr(mod.IBLUsageDB, "_index_single", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.IBLUsageDB, "_index_batch", lambda self, *a, **k: None, raising=False)
    monkeypatch.setattr(mod.IBLUsageDB, "_is_foreign_vocab", staticmethod(lambda code: False))
    try:
        yield mod.IBLUsageDB()
    finally:
        mod.IBLUsageDB._instance = None


def _count(db):
    with db._get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM ibl_examples").fetchone()[0]


def test_g2_door_refuses_unparseable(db):
    assert db.add_example(intent="x", ibl_code=MALFORMED_ROW) == 0
    assert _count(db) == 0
    assert db.add_example(intent="x", ibl_code=GOOD) > 0
    assert _count(db) == 1


def test_g2_batch_drops_bad_keeps_good(db):
    n = db.add_examples_batch([
        {"intent": "a", "ibl_code": MALFORMED_ROW},
        {"intent": "b", "ibl_code": GOOD},
    ])
    assert n == 1 and _count(db) == 1


def test_g2_fail_closed_when_unregistered(db, monkeypatch):
    import ibl_usage_db as mod
    monkeypatch.setattr(mod, "_CODE_VALIDATOR", None)
    with pytest.raises(RuntimeError):
        db.add_example(intent="x", ibl_code=GOOD)
    # 검증자 자체가 고장 = 검증 불가 = 거절(침묵 통과 아님)
    def _broken(code):
        raise ValueError("boom")
    monkeypatch.setattr(mod, "_CODE_VALIDATOR", _broken)
    assert db.add_example(intent="x", ibl_code=GOOD) == 0
    assert _count(db) == 0


# ---------------------------------------------------------------- G3 배선처
def _fresh(code: str, *, layer_dirs_on_path: bool = False) -> str:
    """새 프로세스. layer_dirs_on_path=True 면 boot_paths 없이도 평면 이름이 풀리게 층 디렉토리를 직접 올린다."""
    pp = BACKEND if not layer_dirs_on_path else os.pathsep.join(
        [os.path.join(BACKEND, "datastore"), BACKEND])
    r = subprocess.run([PY, "-c", code], capture_output=True, text=True, timeout=120,
                       cwd=BACKEND, env={**os.environ, "PYTHONPATH": pp})
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout.strip()


def test_g3_boot_paths_wires_lazily():
    out = _fresh(
        "import sys, boot_paths, ibl_usage_db\n"
        "print(ibl_usage_db._CODE_VALIDATOR is not None, 'ibl_param_vocab' in sys.modules)\n"
        f"print(ibl_usage_db._syntax_reason({GOOD!r}) is None)\n"
        "print('ibl_param_vocab' in sys.modules)\n")
    assert out.splitlines() == ["True False", "True", "True"]


def test_g3_without_boot_paths_the_door_is_shut():
    out = _fresh(
        "import ibl_usage_db\n"
        "try:\n"
        f"    ibl_usage_db._syntax_reason({GOOD!r}); print('OPEN')\n"
        "except RuntimeError:\n"
        "    print('SHUT')\n", layer_dirs_on_path=True)
    assert out == "SHUT"


# ---------------------------------------------------------------- G4 기록기 순서
def test_g4_recorder_asks_syntax_before_params(monkeypatch, tmp_path):
    import types
    import ibl_usage_rag as rag
    import ibl_usage_db as mod
    import ibl_param_vocab as pv
    import thread_context

    # 전제 게이트 통과시키기
    monkeypatch.setattr(thread_context, "get_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(thread_context, "clear_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(mod.IBLUsageDB, "hippo_disabled", classmethod(lambda cls: False))

    # 반성기: 실측 그대로 JSON 을 이중으로 감싼 출력
    doubled = json.dumps({"intent": "최근 출시된 AI 소프트웨어 조사", "code": MALFORMED_ROW},
                         ensure_ascii=False)
    fake_ca = types.ModuleType("consciousness_agent")
    fake_ca.oneshot_ai_call = lambda **kw: doubled
    monkeypatch.setitem(sys.modules, "consciousness_agent", fake_ca)

    touched = []
    monkeypatch.setattr(pv, "check_code_params", lambda code: touched.append(("params", code)) or [])
    monkeypatch.setattr(mod.IBLUsageDB, "add_example",
                        lambda self, **kw: touched.append(("ledger", kw)) or 1)

    ok = rag.distill_experience(
        user_message="최근 나온 AI 소프트웨어 조사해줘",
        tool_calls=[{"tool_name": "execute_ibl", "input": {"code": GOOD}, "success": True}],
        top_score=0.0,
    )
    assert ok is False
    assert touched == [], f"구문 관문 뒤의 게이트·원장이 호출됐다: {touched}"


# ---------------------------------------------------------------- G5 자리표 충돌
# 실측 원문(ep2777·2806): 자리표 `[node:action]` 를 베낀 두 모양.
PLACEHOLDER_COPIES = ('[가족/어머니:memory]{op: "recall"}',
                      '[node:self:edit]{path: "backend/surface/api_config.py"}')
RECALL = '[self:memory]{op: "recall", node: "가족/어머니"}'


def test_g5_distill_prompt_has_no_shape_placeholder():
    import ibl_usage_rag as rag
    prompt = rag._build_distill_prompt("내 어머니 연세가 어떻게 되시지?", "  1. " + RECALL, "", "가족/어머니 (3)")
    assert "[node:" not in prompt, "형태 자리표가 다시 들어왔다 — 경량 모델이 글자 그대로 베낀다"
    assert RECALL in prompt and "가족/어머니 (3)" in prompt


def test_g5_placeholder_copies_are_refused():
    from ibl_param_vocab import normalize_corpus_code, code_syntax_error
    for bad in PLACEHOLDER_COPIES:
        assert code_syntax_error(normalize_corpus_code(bad)) is not None, bad
    assert code_syntax_error(RECALL) is None


def test_g5_unexecuted_head_is_refused_by_grounding():
    import ibl_usage_rag as rag
    calls = [RECALL]
    assert rag._heads_grounded(RECALL, calls)
    assert rag._heads_grounded('[self:memory]{op: "recall", node: "가족"}', calls)
    # 파싱은 되지만 이 주행에서 돌지 않은 머리 — 발명된 패턴
    assert not rag._heads_grounded('[self:time]', calls)
    assert not rag._heads_grounded(RECALL + ' >> [table:brief]{instruction: "요약"}', calls)
    assert not rag._heads_grounded("", calls)


def test_g5_recorder_drops_placeholder_copy_before_ledger(monkeypatch):
    import types
    import ibl_usage_rag as rag
    import ibl_usage_db as mod
    import ibl_param_vocab as pv
    import thread_context

    monkeypatch.setattr(thread_context, "get_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(thread_context, "clear_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(mod.IBLUsageDB, "hippo_disabled", classmethod(lambda cls: False))
    out = json.dumps({"intent": "어머니 정보 회상", "code": PLACEHOLDER_COPIES[0], "topic": "가족"},
                     ensure_ascii=False)
    fake_ca = types.ModuleType("consciousness_agent")
    fake_ca.oneshot_ai_call = lambda **kw: out
    monkeypatch.setitem(sys.modules, "consciousness_agent", fake_ca)
    touched = []
    monkeypatch.setattr(pv, "check_code_params", lambda code: touched.append(("params", code)) or [])
    monkeypatch.setattr(mod.IBLUsageDB, "add_example", lambda self, **kw: touched.append(("ledger", kw)) or 1)

    ok = rag.distill_experience(
        user_message="내 어머니 연세가 어떻게 되시지?",
        tool_calls=[{"tool_name": "execute_ibl", "input": {"code": RECALL}, "success": True}],
        top_score=0.0)
    assert ok is False and touched == []


# ---------------------------------------------------------------- G6 병렬 접지
def test_g6_parallel_only_composition_grounds_per_branch():
    """& 만의 합성은 가지별 접지(동시성 주장), 흐름 합성(>>)은 단일 호출 접지(종전) — 2026-09-04 ep2817."""
    import ibl_usage_rag as rag
    calls = ['[sense:stock]{op: "quote", ticker: "^TNX"} & [sense:stock]{op: "quote", ticker: "^TYX"}',
             '[sense:search]{source: "gnews", query: "treasury"}',
             '[self:memory]{op: "recall", node: "시장 기록"}']
    assert rag._composition_grounded('[sense:stock]{op: "quote", ticker: "^TNX"} & [sense:search]{source: "gnews", query: "x"}', calls)
    assert not rag._composition_grounded('[sense:stock]{op: "quote", ticker: "^TNX"} & [sense:realty]{region: "x"}', calls)
    # 흐름은 여전히 한 호출 안에 있었어야 한다
    assert not rag._composition_grounded('[sense:search]{source: "gnews", query: "x"} >> [self:memory]{op: "save", content: "y"}', calls)
    assert rag._composition_grounded('[sense:search]{source: "gnews", query: "x"}', calls)


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
