"""[table:each] 통화 계약 — 성공은 통화로, 실패는 봉투로 (2026-08-23 언어 개정, 사용자 판정)

옛 계약: 출력 행 = `원 행 + _ok + (_error|_result)` 봉투. 명분은 "원 행 보존 =
`>> [table:filter]{where:"_ok == false"}` 로 실패만 추리기" 였다(설계 문서에 명시).

실측이 그 명분을 뒤집었다:
  · 코퍼스 3,582문장 중 `_ok` 를 쓴 문장 **0건** — 명분이 한 번도 실현되지 않았다.
  · `each` 문장 49건 중 15건이 `>> [table:flatten]` 동반, `flatten` 이 최다 후속(10건).
  · 8일간 `each` 실사용 7건 vs 접힐 수 있었던 연속 동일 액션 반복 700여 건.
→ **한 번도 안 쓰인 관용구를 위해 매번 쓰이는 관용구를 끊고 있었다.**

그리고 이 몸엔 이미 답이 있었다: halted_steps·skipped_steps·branches_failed·empty_notes 가
전부 **부분 실패는 봉투로** 나른다. each 만 2026-08-15 에 그 규약이 서기 전 만들어져 실패를
통화 안에 섞었고, IBL 에서 유일하게 통화-in/통화-out 이 아닌 변환자였다.

이 배터리가 지키는 것:
  ① do 가 통화를 내면 그 행들이 **감싸기 없이** 흐른다 (flatten 불필요).
  ② do 가 통화를 안 내면(효과·스칼라) **원 행**이 흐르고 봉투가 그 사실을 말한다.
  ③ 실패 행은 통화에 없고 봉투 errors + warning 에 있다 — 침묵 금지는 그대로.
  ④ `keep` 이 옛 `flatten{keep}` 의 능력을 잇는다 (개정이 능력을 없애지 않는다).
  ⑤ 옛 관용구 `each >> flatten` 은 **정직하게** 거절하고 참인 처방(flatten 을 빼라)을 말한다.

실행: .venv/bin/python -m pytest backend/test_each_currency_contract.py -q
"""
import importlib.util
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401

import ibl_engine  # noqa: E402
from ibl.ibl_exec_each import _execute_table_each  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKGS = os.path.join(_ROOT, "data", "packages", "installed", "tools")

PARENTS = [{"city": "수원"}, {"city": "용인"}]


def _run(do, params=None, result=None):
    """do 한 문장을 굳힌 실행기로 each 를 돌린다."""
    orig = ibl_engine.execute_ibl

    def _fake(ti, pp, agent_id=None, **kw):
        return dict(result) if isinstance(result, dict) else result
    ibl_engine.execute_ibl = _fake
    try:
        return _execute_table_each({"items": PARENTS, "do": do, **(params or {})}, ".")
    finally:
        ibl_engine.execute_ibl = orig


CURRENCY = {"success": True, "items": [{"date": "d1", "max_temp": 30}, {"date": "d2", "max_temp": 31}]}
EFFECT = {"success": True, "message": "알림 보냄"}
FAIL = {"success": False, "error": "고장"}


# ── ① 통화는 감싸기 없이 흐른다 ────────────────────────────────────────

def test_C1_통화_결과는_그대로_행이_된다():
    out = _run("[sense:weather]{city: $it.city}", result=CURRENCY)
    assert out["success"] is True
    assert [r["date"] for r in out["items"]] == ["d1", "d2", "d1", "d2"], out
    assert all("_ok" not in r and "_result" not in r for r in out["items"]), "옛 봉투가 남았다"
    assert out["rows_processed"] == 2 and out["ok_count"] == 2
    assert "passthrough_rows" not in out


def test_C2_뒤에_변환자를_바로_이을_수_있다():
    """이 개정의 목적 자체 — 옛 계약에선 여기서 파이프가 끊겼다."""
    out = _run("[sense:weather]{city: $it.city}", result=CURRENCY)
    cols = set(out["items"][0].keys())
    assert {"date", "max_temp"} <= cols, f"변환자가 쓸 열이 없다: {cols}"


# ── ② 통화가 아니면 원 행 + 고지 ───────────────────────────────────────

def test_C3_효과_결과는_원_행이_흐르고_봉투가_말한다():
    """종착 액션(notify·write)은 통화를 안 낸다. 빈손으로 두면 '어느 행에 대해
    실행됐는지'조차 안 보인다 — 그건 옛 봉투가 유일하게 잘하던 일이라 버리지 않는다."""
    out = _run("[self:notify_user]{message: $it.city}", result=EFFECT)
    assert [r["city"] for r in out["items"]] == ["수원", "용인"]
    assert out["passthrough_rows"] == 2
    assert "원 행" in out["message"], out
    # ★말없이 원 행을 흘리면 소비자가 그걸 do 의 결과로 오독한다
    assert "do 의 결과가 아닙니다" in out["message"]


# ── ③ 실패는 봉투로, 그러나 시끄럽게 ──────────────────────────────────

def test_C4_부분_실패는_통화에_없고_봉투에_있다():
    calls = {"n": 0}
    orig = ibl_engine.execute_ibl

    def _fake(ti, pp, agent_id=None, **kw):
        calls["n"] += 1
        return dict(CURRENCY) if calls["n"] == 1 else dict(FAIL)
    ibl_engine.execute_ibl = _fake
    try:
        out = _execute_table_each({"items": PARENTS, "do": "[sense:weather]{city: $it.city}"}, ".")
    finally:
        ibl_engine.execute_ibl = orig
    assert out["success"] is True                 # 부분 실패는 파이프를 끊지 않는다
    assert len(out["items"]) == 2                 # 성공분만
    assert all("_error" not in r for r in out["items"])
    assert out["error_count"] == 1 and out["ok_count"] == 1
    assert out["errors"][0]["city"] == "용인"      # 실패한 **원 행**이 봉투에
    assert "고장" in out["errors"][0]["_error"]
    # ★침묵 금지 — 통화만 보면 부분성이 안 보이므로 봉투가 크게 말해야 한다
    assert "warning" in out and "errors" in out["warning"], out


def test_C5_전_행_실패는_상위로_전파한다():
    out = _run("[sense:weather]{city: $it.city}", result=FAIL)
    assert out["success"] is False
    assert "전부 실패" in out["error"] and "고장" in out["error"]


def test_C6_입력_0행은_정당한_빈손이다():
    orig = ibl_engine.execute_ibl
    ibl_engine.execute_ibl = lambda *a, **k: dict(CURRENCY)
    try:
        out = _execute_table_each({"items": [], "do": "[sense:weather]{city: $it.city}"}, ".")
    finally:
        ibl_engine.execute_ibl = orig
    assert out["success"] is True and out["items"] == []


# ── ④ keep — 개정이 능력을 없애지 않는다 ──────────────────────────────

def test_C7_keep_이_옛_flatten_keep_을_잇는다():
    """`each >> flatten{keep:["city"]}` 이 하던 일(어느 부모에서 왔는지)을 이어받는다.
    부모 행이 아직 손에 있는 자리로 옮긴 것이지 없앤 게 아니다."""
    out = _run("[sense:weather]{city: $it.city}", params={"keep": ["city"]}, result=CURRENCY)
    assert all(r["city"] in ("수원", "용인") for r in out["items"])
    assert [r["city"] for r in out["items"]] == ["수원", "수원", "용인", "용인"]


def test_C8_keep_충돌은_조용히_덮지_않는다():
    """flatten 과 같은 규율 — 침묵 오선택 금지."""
    clash = {"success": True, "items": [{"city": "결과쪽-도시", "v": 1}]}
    out = _run("[sense:weather]{city: $it.city}", params={"keep": ["city"]}, result=clash)
    r = out["items"][0]
    assert r["city"] == "결과쪽-도시", "결과 값이 부모 값에 덮였다"
    assert r["city_2"] == "수원", r


# ── ⑤ 옛 관용구는 정직하게 거절하고 참인 처방을 말한다 ──────────────────

@pytest.fixture(scope="module")
def dops():
    p = os.path.join(_PKGS, "data-ops", "handler.py")
    if not os.path.exists(p):
        pytest.skip("data-ops 패키지 없음")
    spec = importlib.util.spec_from_file_location("_t_dops_cc", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_t_dops_cc"] = mod
    spec.loader.exec_module(mod)
    return mod


class _Ctx:
    def __init__(self, verb):
        self.tool_name = verb
        self.project_path = _ROOT
        self.agent_id = "test"

    def output_dir(self, name=None):
        return os.path.join(_ROOT, "outputs")


def test_C9_옛_관용구_each_flatten_은_참인_처방을_말한다(dops):
    """코퍼스가 3개월간 가르친 `each >> flatten` 이 이제 여기로 온다. "목록이 없다"만
    말하면 사용자는 field 를 고치려 든다 — 참인 처방은 **flatten 을 빼는 것**이다."""
    out = dops.execute({"_prev_result": {"items": [{"date": "d1", "max_temp": 30}]}},
                       _Ctx("data_flatten"))
    r = json.loads(out) if isinstance(out, str) else out
    assert r.get("success") is False
    assert "이미 평탄" in r["error"], r
    assert "flatten 없이 바로 이으세요" in r["error"]


def test_C10_field_를_지목한_경우는_옛_문구_그대로(dops):
    """이행 안내는 기본 field(_result)로 온 경우에만 — 진짜 중첩 목록을 펴려다 필드명을
    틀린 사람에게 'flatten 을 빼라'고 하면 그게 새 오진이다."""
    out = dops.execute({"field": "tags", "_prev_result": {"items": [{"tags": "문자열"}]}},
                       _Ctx("data_flatten"))
    r = json.loads(out) if isinstance(out, str) else out
    assert r.get("success") is False
    assert "이미 평탄" not in r["error"] and "목록을 가진 행이 없습니다" in r["error"]


def test_C11_카탈로그가_새_계약을_가르친다():
    import yaml
    d = yaml.safe_load(open(os.path.join(_ROOT, "data", "ibl_nodes.yaml"), encoding="utf-8"))
    td = d["nodes"]["table"]["actions"]["each"]["target_description"]
    assert "통화 그대로" in td, "카탈로그가 아직 옛 봉투를 가르친다"
    assert "flatten 불필요" in td
    assert "errors" in td and "passthrough_rows" in td
    assert "keep(" in td


def test_C12_통화_대체도_봉투가_말한다():
    """B32-1(32회차): 신고가 한 방향뿐이었다 — 스칼라→원행 통과는 말하고,
    do 가 통화를 내어 **원 행이 대체**되는 반대 방향은 침묵했다.
    실측(32회차): 2행을 넣었는데 10행이 나오고(각 행을 검색한 결과), 어느 행에서
    나왔는지가 통화에도 봉투에도 없었다. 행 수가 조용히 바뀌면 하류 판단이 틀린다."""
    out = _run("[sense:weather]{city: '$it.city'}", result=CURRENCY)
    assert out["rows_replaced"] == len(PARENTS), out
    msg = out.get("message") or ""
    assert "대체" in msg, f"대체 사실을 말하지 않는다: {msg}"
    assert "keep" in msg, f"정체를 지키는 법(keep)을 안 가리킨다: {msg}"
    assert "passthrough_rows" not in out, "통화를 냈는데 통과로 신고했다"


def test_C13_교재도_같은_계약을_가르친다():
    """F32-1(32회차): C11 은 yaml 카탈로그를 지켰지만 **항상 프롬프트에 주입되는
    교재**(12_ibl_only.md)는 아무도 안 보고 있었다 — 그사이 교재는 은퇴한 `_ok`/`_result`
    감싸기를 계속 가르쳐, 같은 문서가 124행과 199행에서 서로 다른 계약을 말했다.
    가르치는 자리가 둘이면 둘 다 지켜야 한다."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(root, "data", "common_prompts", "fragments", "12_ibl_only.md")
    src = open(p, encoding="utf-8").read()
    each_line = [ln for ln in src.splitlines() if "**고차**" in ln and "each{" in ln]
    assert each_line, "교재에서 each 설명을 못 찾았다"
    ln = each_line[0]
    assert "원 행에 `_ok`" not in ln, "교재가 은퇴한 _ok 감싸기 계약을 아직 가르친다"
    for token in ("rows_replaced", "passthrough_rows", "keep"):
        assert token in ln, f"교재가 {token} 를 가르치지 않는다"


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다(28회차).
    raise SystemExit(pytest.main([__file__, "-q"]))
