"""each 봉투를 만난 변환자가 **다음에 뭘 하라**까지 말한다 (2026-08-23)

실측한 마찰: `[table:each]` 는 통화를 그대로 내지 않는다. 행별 성패를 신고해야 하므로
원 행에 `_ok`/`_result`(또는 `_error`)를 씌운 **봉투**를 낸다 — 이건 버그가 아니라
의도된 설계다. 문제는 그 다음이다:

    [table:each]{…} >> [table:select]{columns:["date","max_temp"]}
    → select: 열 ['date','max_temp'] 이(가) 없습니다. 실제 열: ['city','_ok','_result']

*없는 것*과 *있는 것*까지는 정직한데 **다음에 뭘 하라**가 없다. 그래서 사용자는 자기 문장이
틀린 줄 알고 each 를 버리고 같은 액션을 N번 부르는 쪽으로 돌아간다.

실측 근거(2026-08-23): 8일간 `each` 실사용 **7건** vs "한 문장으로 접힐 수 있었던" 연속
동일 액션 반복 **700여 건**. 29회차 상상훈련(#19 each>sort · #24 each>since)도 이걸 두 번
밟고 **자기 저작 오류**로 계상해 갭 원장에 못 올렸다 — 정직한 오류문이 불완전하면 시스템의
마찰이 사용자 탓으로 계상된다.

★판정은 **모양으로만** 한다(헌법 '명사의 자리'): 앞 액션의 이름을 묻지 않고 봉투 표식 키의
존재만 본다. `[table:flatten]` 이 이미 같은 표식으로 자동 승격하므로 처방도 그것 하나다.

실행: .venv/bin/python -m pytest backend/test_each_envelope_remedy.py -q
"""
import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKGS = os.path.join(_ROOT, "data", "packages", "installed", "tools")


@pytest.fixture(scope="module")
def dops():
    p = os.path.join(_PKGS, "data-ops", "handler.py")
    if not os.path.exists(p):
        pytest.skip("data-ops 패키지 없음")
    spec = importlib.util.spec_from_file_location("_t_dops_each", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_t_dops_each"] = mod
    spec.loader.exec_module(mod)
    return mod


ENV_ROW = {"city": "수원", "_ok": True, "_result": {"date": "2026-08-23", "max_temp": 31.8}}


class _Ctx:
    def __init__(self, verb):
        self.tool_name = verb
        self.project_path = _ROOT
        self.agent_id = "test"

    def output_dir(self, name=None):
        return os.path.join(_ROOT, "outputs")


def _err(dops, verb, params):
    out = dops.execute({**params, "_prev_result": {"items": [ENV_ROW]}}, _Ctx("data_" + verb))
    if isinstance(out, str):
        import json
        out = json.loads(out)
    return out.get("error") or ""


# ── ① 처방이 실제로 붙는가 (형제 전수) ────────────────────────────────

@pytest.mark.parametrize("verb,params", [
    ("select", {"columns": ["date", "max_temp"]}),
    ("sort", {"by": "max_temp"}),
    ("rename", {"map": {"max_temp": "최고기온"}}),
    ("dedup", {"by": "date"}),
    ("filter", {"where": "max_temp > 30"}),
])
def test_N1_형제_변환자가_전부_처방을_말한다(dops, verb, params):
    """한 자리만 고치면 다음 사람이 다른 자리에서 같은 벽을 만난다 — 부류 전수."""
    e = _err(dops, verb, params)
    assert e, f"{verb}: 봉투를 받고도 에러를 안 냈다(조용한 오동작)"
    assert "table:flatten" in e, f"{verb}: 무엇이 없는지만 말하고 다음에 뭘 하라를 안 말했다 — {e}"
    assert "_result" in e


def test_N2_정직성_계약_셋을_다_지킨다(dops):
    """29회차가 세운 좋은 거절의 기준: 없는 것 + 있는 것 + 다음에 뭘 하라."""
    e = _err(dops, "select", {"columns": ["date"]})
    assert "date" in e                      # ① 없는 것
    assert "_ok" in e and "_result" in e     # ② 있는 것
    assert "flatten" in e                    # ③ 다음에 뭘 하라


# ── ② 오발 방지 — 봉투가 아닌 곳에 처방을 붙이지 않는다 ────────────────

def test_N3_평범한_0열_오류엔_처방이_안_붙는다(dops):
    """each 와 무관한 실수에 each 얘기를 하면 그게 새 잡음이다."""
    out = dops.execute({"columns": ["없는열"],
                        "_prev_result": {"items": [{"a": 1, "b": 2}]}}, _Ctx("data_select"))
    import json
    e = (json.loads(out) if isinstance(out, str) else out).get("error") or ""
    assert e and "flatten" not in e, e


def test_N4_ok_만_있고_result가_없으면_봉투가_아니다(dops):
    """모양 판정의 경계 — `_ok` 라는 이름을 쓰는 사용자 데이터가 있을 수 있다."""
    assert dops._each_envelope_remedy(["city", "_ok"]) == ""
    assert dops._each_envelope_remedy(["city", "_result"]) == ""
    assert dops._each_envelope_remedy([]) == ""
    assert dops._each_envelope_remedy(None) == ""
    # 실패 행만 온 경우(_error) 도 봉투다
    assert "flatten" in dops._each_envelope_remedy(["city", "_ok", "_error"])


# ── ③ 처방이 실제로 통하는가 (말만 하고 안 되면 더 나쁘다) ──────────────

def test_N5_처방대로_하면_진짜_풀린다(dops):
    """오류문이 시킨 대로 `>> [table:flatten]` 을 넣으면 통화가 복원되는지 —
    안내가 맞는지까지 봐야 안내다."""
    import json
    out = dops.execute({"_prev_result": {"items": [ENV_ROW]}}, _Ctx("data_flatten"))
    flat = json.loads(out) if isinstance(out, str) else out
    rows = flat.get("items") or []
    assert rows and "max_temp" in rows[0], f"flatten 이 원래 필드를 못 되살렸다: {flat}"
    out2 = dops.execute({"columns": ["date", "max_temp"], "_prev_result": flat}, _Ctx("data_select"))
    sel = json.loads(out2) if isinstance(out2, str) else out2
    assert sel.get("success") is not False, sel


# ── ④ 교재도 같은 것을 가르치는가 ──────────────────────────────────

def test_N6_카탈로그가_이어_쓰는_꼴을_보여준다():
    """★교재의 유일한 예시가 종착 액션으로 끝나서 '뒤를 잇는 법'을 한 번도 안 보여줬다.
    오류문만 고치고 교재를 두면 같은 벽을 계속 처음 만난다."""
    import yaml
    d = yaml.safe_load(open(os.path.join(_ROOT, "data", "ibl_nodes.yaml"), encoding="utf-8"))
    td = d["nodes"]["table"]["actions"]["each"]["target_description"]
    assert "table:flatten" in td, "카탈로그가 each 뒤에 무엇이 오는지 안 가르친다"
    assert "봉투" in td, "카탈로그가 결과가 통화가 아니라는 사실을 안 말한다"


def test_N7_스칼라_필드엔_여전히_정직하게_거절한다(dops):
    """레코드를 받아들이되 스칼라까지 감싸면 field 오타가 조용히 '성공'이 된다 —
    정직한 거절이 사라지는 자리. 경계를 시험이 지킨다."""
    import json
    out = dops.execute({"field": "title",
                        "_prev_result": {"items": [{"title": "그냥 문자열"}]}}, _Ctx("data_flatten"))
    r = json.loads(out) if isinstance(out, str) else out
    assert r.get("success") is False, f"스칼라를 조용히 행으로 위장했다: {r}"
    assert "목록을 가진 행이 없습니다" in r["error"]


def test_N8_목록형_결과는_전과_같이_펼쳐진다(dops):
    """레코드 수용이 기존 목록 펼치기를 건드리지 않았는지 (회귀)."""
    import json
    rows = [{"c": "수원", "_ok": True, "_result": {"items": [{"d": 1}, {"d": 2}]}}]
    out = dops.execute({"_prev_result": {"items": rows}}, _Ctx("data_flatten"))
    r = json.loads(out) if isinstance(out, str) else out
    assert [x["d"] for x in r["items"]] == [1, 2], r


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다(28회차).
    raise SystemExit(pytest.main([__file__, "-q"]))
