"""emitter 입력 진단의 정직성 + 병렬 타임아웃 신고 회귀 (29회차, 2026-08-23)

재현하는 결함(전부 실측):
  B29-1 **emitter 가 '입력 없음'과 '입력은 왔는데 못 쓴다'를 구별하지 않았다.**
     · `… >> [table:reduce]{init: 0, step: "acc + price", as: "총거래액"} >> [table:chart]`
       → reduce 는 `[{"총거래액": 1101000000}]` 을 **1행 확실히** 냈는데 chart 는
         "데이터가 비어있습니다. data 또는 data_file을 제공하세요" 라고 답했다.
         참인 원인은 "첫 열=x축 규약이라 1열짜리 통화엔 값 열이 없다" 였다.
     · `… >> [table:filter]{where: <0건>} >> [table:document]`
       → "blocks(문서 IR 블록 배열)가 필요합니다" — 같은 파이프가 행이 있을 땐 blocks 없이
         잘 흐른다. 사용자는 자기가 줄 필요도 없는 파라미터를 찾아 헤맨다.
     같은 노드의 형제 `[table:brief]` 는 이미 정직했다("입력 0행 — 종합할 내용이 없어
     AI 호출 생략"). 그 선례에 chart·document 를 맞춘 것이 이 수리다.

  B29-3 **병렬 타임아웃이 concurrent.futures 의 내부 문구를 그대로 흘렸다.**
     `[A] & [B] >> [table:join]` 에서 한 가지가 90초를 넘기면 봉투에
     "Step 1 병렬 실행 예외: 1 (of 2) futures unfinished" 가 실렸다.
     `as_completed(..., timeout=)` 자신의 TimeoutError 를 아무도 안 잡아 for 문 밖으로
     튀었고, 바로 아래에 저자가 써 둔 "미완료 브랜치 처리"(어느 가지가 몇 초에 걸렸는지
     말해 주는 정직한 신고)는 **한 번도 실행되지 않는 죽은 코드**였다.

실행: .venv/bin/python -m pytest backend/test_emitter_input_honesty.py
"""
import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKGS = os.path.join(_ROOT, "data", "packages", "installed", "tools")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── B29-1a: chart 의 입력 진단 ────────────────────────────────────────────

@pytest.fixture(scope="module")
def viz():
    p = os.path.join(_PKGS, "visualization", "handler.py")
    if not os.path.exists(p):
        pytest.skip("visualization 패키지가 설치돼 있지 않음")
    return _load("_it29_viz_handler", p)


def test_R1_chart_1열_통화는_빈_데이터가_아니다(viz):
    """reduce 산출(1열 1행)을 chart 가 '데이터 없음'으로 오진하지 않는다."""
    ti = {"_prev_result": {"items": [{"총거래액": 1101000000}]}}
    d = viz._diagnose_no_data(ti, "bar")
    assert d is not None and d["success"] is False
    assert d["rows_in"] == 1                      # 행이 왔다는 사실을 봉투가 말한다
    assert d["columns"] == ["총거래액"]
    assert "최소 2열" in d["error"]                # 참인 원인
    assert "data_file" not in d["error"]           # 사용자가 주지도 않은 파라미터를 지목하지 않는다


def test_R2_chart_0행은_0행이라고_말한다(viz):
    """★첫 수리는 이 칸을 놓쳤다 — 라이브 재현으로 잡혔다(29회차).

    `_extract_table_from_prev` 는 *그릴 수 있는* 표만 만들어 주느라 빈 items 를 먼저 버린다.
    그래서 "0행이 도착했다"는 사실이 진단기까지 오지 못하고 옛 공용 문구로 떨어졌다.
    이 시험의 첫 판은 `table` 로 우회해 통과해 버려 결함을 **가렸다** — 우회 없이 통화
    봉투 그대로(진짜 경로)를 준다.
    """
    d = viz._diagnose_no_data({"_prev_result": {"items": [], "count": 0}}, "bar")
    assert d is not None, "0행 통화가 도착했는데 진단기가 판단을 포기했다"
    assert d["rows_in"] == 0
    assert "0행" in d["error"]
    assert "data_file" not in d["error"]
    # 문자열(JSON) 봉투로 와도 같아야 한다 — 파이프는 둘 다 흘린다
    import json as _j
    d2 = viz._diagnose_no_data({"_prev_result": _j.dumps({"items": []})}, "bar")
    assert d2 is not None and d2["rows_in"] == 0


def test_R3_통화가_아예_안_왔으면_진단하지_않는다(viz):
    """판단 근거가 없을 때 있는 척하지 않는다 — 기존 안내 경로에 맡긴다."""
    assert viz._diagnose_no_data({}, "bar") is None


def test_R4_chart_가_형제와_같은_낱말_path_를_받는다(viz):
    """F29-1 — document·spreadsheet 는 path, chart 만 output_path 였다.

    고친 자리는 핸들러 코드가 아니라 **어휘 데이터**다: `ibl_actions.yaml` 의
    `aliases: {output_path: [path]}`. 런타임은 ibl_routing._normalize_param_aliases 가,
    검수의 '미인식 파라미터' 경고는 ibl_param_vocab 이 같은 선언 하나를 읽는다
    (IBL 헌법 '명사의 자리' — 어휘 이름을 엔진·핸들러 코드에 심지 않는다).
    """
    import yaml
    y = yaml.safe_load(open(os.path.join(_PKGS, "visualization", "ibl_actions.yaml"),
                            encoding="utf-8"))
    chart = ((y or {}).get("actions") or {}).get("chart")
    assert chart, "chart 액션 선언을 ibl_actions.yaml 에서 못 찾음"
    assert "path" in (chart.get("aliases") or {}).get("output_path", []), \
        "chart 가 형제 emitter 의 낱말 path 를 별칭으로 선언하지 않았다"
    # 파생물(tool.json)까지 별칭이 내려왔는지 — 안 내려오면 검수 경고가 계속 뜬다
    from ibl_param_vocab import _alias_keys
    assert "path" in _alias_keys(chart)


# ── B29-1b: document 의 입력 진단 ────────────────────────────────────────

def test_R5_document_0행은_blocks_탓이_아니다():
    p = os.path.join(_PKGS, "data-ops", "doc_build.py")
    if not os.path.exists(p):
        pytest.skip("data-ops 패키지가 설치돼 있지 않음")
    import json
    doc = _load("_it29_doc_build", p)
    out = doc.render_document({"items": [], "format": "markdown"}, output_base=".")
    r = json.loads(out) if isinstance(out, str) else out
    assert r.get("success") is False
    assert r.get("rows_in") == 0
    assert "0행" in r.get("error", "")
    assert "blocks(문서 IR" not in r.get("error", "")


# ── B29-3: 병렬 타임아웃 신고 ────────────────────────────────────────────

def test_R6_병렬_전체_타임아웃이_내부_문구를_흘리지_않는다(monkeypatch):
    import ibl_engine
    import workflow_parallel as wp

    monkeypatch.setattr(wp, "PARALLEL_BRANCH_TIMEOUT", 1)

    def _slow(tool_input, project_path=None):
        import time
        if tool_input.get("action") == "slow":
            time.sleep(5)                       # 타임아웃보다 확실히 길다
        return {"items": [{"x": 1}]}

    # _execute_parallel 은 호출 시점에 `from ibl_engine import execute_ibl` 한다 —
    # 그래서 패치는 원 모듈 쪽에 걸어야 한다.
    monkeypatch.setattr(ibl_engine, "execute_ibl", _slow)
    branches = [{"node": "sense", "action": "fast"}, {"node": "sense", "action": "slow"}]
    out = wp._execute_parallel(branches, None, "")   # prev_result 는 문자열 계약

    assert len(out) == 2
    errs = " ".join(str(r.get("error", "")) for r in out if isinstance(r, dict))
    assert "futures unfinished" not in errs      # 내부 문구 누출 금지
    assert "실행 시간 초과" in errs                # 정직한 신고가 실제로 실행된다
    assert "sense:slow" in errs                   # 어느 가지인지 말한다


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
