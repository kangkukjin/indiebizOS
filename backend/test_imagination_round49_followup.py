"""49회차 후속 — 48회차 이월 미수리분 집행 회귀 (2026-08-27).

사용자가 V49-1 을 안 A(블록은 스코프를 만들지 않는다)로 판정하면서 "나머지 미수리도
함께 고치라"고 지시한 턴의 가드. 원장에 이미 적혀 있던 항목만 다룬다.

  F48-4 교재 드리프트 — `[repeat: N]{…} >> 변환자` 는 **거절되지 않는다.**
     교재는 33회차 실측을 인용해 "collect 없으면 스칼라 봉투라 정직하게 거절된다"고
     가르쳤으나 구현 계약(`_execute_repeat` 독스트링)은 "통화: 마지막 회차 items,
     collect:true 면 전 회차 이어붙임" 이고 실측도 `success:true`. 교재를 고쳤다.

  F48-5 교재 드리프트 — `_ok` 로 거르면 **0건이 아니라 명시 거절**이다.
     실측: `filter: '_ok' 필드가 어느 행에도 없습니다. 사용 가능한 필드: [...]`.
     구현이 더 정직하므로("0건"은 '없다'와 '그 필드가 없다'를 못 가른다) 교재를 고쳤다.

  F48-6 emitter 0행 규약 불일치 — **spreadsheet 만 빈 파일을 만들고 success** 를 냈다.
     실측: 0행 입력 → 4,785바이트 xlsx 생성. chart·document 는 `rows_in: 0` 으로
     정직 거절한다(chart 는 이 턴 이전에 이미 고쳐져 있었다 — 원장의 "chart 는 데이터가
     비어있습니다만 낸다"는 서술은 그 사이 낡았다).

  F48-7 표지 승격 규칙 불일치 — 파이프 표지는 최상위로 오르는데 **마지막 통화의 표지**
     (error_count·errors·rows_replaced·passthrough_rows·rows_in·truncated)는
     `final_result` JSON 문자열 안에만 살았다. 교재는 "보고 전에 이 키들을 확인하라"고
     한 줄로 가르치는데 읽는 쪽은 두 규칙을 외워야 했다.

  관문 `scripts/check_honesty_propagation.py` — 48회차가 "다음 수리 턴의 첫 항목"으로
     지목한 밭 이관(가이드 §4-3). 표지를 손으로 열거하는 자리의 **탄생을 차단**한다.
"""
import importlib.util
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401,E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAG = os.path.join(ROOT, "data", "common_prompts", "fragments", "12_ibl_only.md")


# ─────────────────── F48-4 · F48-5 교재 드리프트 ───────────────────

def test_F48_4_교재가_repeat_통화를_구현대로_가르친다():
    src = open(FRAG, encoding="utf-8").read()
    assert "repeat 은 언제나 items 를 낸다" in src
    # 옛 거짓 문구가 남아 있으면 안 된다
    assert "collect: true` 일 때만** items" not in src


def test_F48_4_구현_계약과_교재가_같은_말을_한다():
    """교재만 고치고 구현을 안 봤으면 이 시험이 잡는다 — 독스트링이 계약의 정본."""
    import ibl_control_blocks
    doc = ibl_control_blocks._execute_repeat.__doc__ or ""
    assert "마지막 회차 items" in doc and "collect:true" in doc, doc


def test_F48_5_교재가_ok_필터를_명시_거절로_가르친다():
    src = open(FRAG, encoding="utf-8").read()
    assert "0건이 아니라 **명시 거절**" in src
    assert "그 필드로 거르려 하면 0건이 나온다" not in src


# ─────────────────── F48-6 emitter 0행 규약 ───────────────────

def _spreadsheet(tool_input):
    from packages.installed.tools.system_essentials import office_ops  # noqa
    return office_ops


def _office_ops():
    path = os.path.join(ROOT, "data", "packages", "installed", "tools",
                        "system_essentials", "office_ops.py")
    spec = importlib.util.spec_from_file_location("_office_ops_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("payload,label", [
    ({"items": []}, "인라인 0행"),
    ({"_prev_result": json.dumps({"items": [], "count": 0})}, "파이프 0행 통화"),
    ({"_prev_result": json.dumps({"table": {"columns": ["a", "b"], "rows": []}})}, "0행 표 통화"),
])
def test_F48_6_spreadsheet_는_0행에_빈_파일을_만들지_않는다(tmp_path, payload, label):
    """형제 emitter(chart·document)와 같은 `rows_in: 0` 정직 거절.

    ★파일이 만들어지지 않는 것까지가 수리다 — 산출물이 남으면 거절이 무의미하다
    (읽는 쪽은 파일을 보고 '됐다'고 읽는다).
    """
    office_ops = _office_ops()
    out_path = tmp_path / "empty.xlsx"
    ti = {**payload, "path": str(out_path)}
    res = office_ops.spreadsheet(ti, str(tmp_path), lambda *_a, **_k: None, context=None)
    obj = json.loads(res) if isinstance(res, str) else res
    assert obj.get("success") is False, (label, obj)
    assert obj.get("rows_in") == 0, (label, obj)
    assert not out_path.exists(), f"{label}: 거절했는데 파일이 생겼다"


def test_F48_6_행이_있으면_종전대로_만든다(tmp_path):
    """대조군 — 0행 관문이 정상 경로를 막지 않는다."""
    office_ops = _office_ops()
    out_path = tmp_path / "ok.xlsx"
    res = office_ops.spreadsheet(
        {"items": [{"a": 1, "b": 2}], "path": str(out_path)},
        str(tmp_path), lambda *_a, **_k: None, context=None)
    obj = json.loads(res) if isinstance(res, str) else res
    assert obj.get("success") is not False, obj
    assert out_path.exists()


def test_F48_6_입력이_아예_없는_것과_0행은_다른_사건이다(tmp_path):
    """`rows_in` 계약의 핵심 — '안 왔다'와 '왔는데 0행'을 가른다."""
    office_ops = _office_ops()
    assert office_ops._empty_currency_columns({}) is None                      # 입력 없음
    assert office_ops._empty_currency_columns({"items": []}) == []             # 0행 통화
    assert office_ops._empty_currency_columns({"items": [{"a": 1}]}) is None   # 행 있음
    assert office_ops._empty_currency_columns(
        {"_prev_result": json.dumps({"table": {"columns": ["x"], "rows": []}})}) == ["x"]


# ─────────────────── F48-7 표지 최상위 승격 ───────────────────

def test_F48_7_마지막_통화의_표지가_봉투_최상위로_오른다(tmp_path):
    """종전엔 `error_count`/`errors` 가 final_result JSON **문자열 안**에만 살아서,
    읽는 쪽이 파이프 표지와 통화 표지의 **두 규칙**을 동시에 외워야 했다.

    픽스처는 결정론이어야 한다 — 옛 판은 /tmp 의 첫 두 항목이 읽기 실패하리라
    가정했고, 둘 다 읽히는 날 error_count=0 으로 무너졌다(2026-08-30 실측).
    한 행은 실재하는 파일, 한 행은 없는 경로로 부분 실패를 스스로 만든다.
    """
    from ibl_parser import parse
    from workflow_engine import execute_pipeline
    ok_file = tmp_path / "ok.txt"
    ok_file.write_text("살아있는 행", encoding="utf-8")
    code = (f'[table:take]{{items: [{{"url": "{ok_file}"}}, '
            f'{{"url": "{tmp_path}/없는파일.txt"}}], n: 2}} '
            '>> [table:each]{do: "[self:read]{path: \\"$it.url\\"}"}')
    env = execute_pipeline(parse(code), ROOT, agent_id="test")
    assert "error_count" in env, list(env)
    assert env["error_count"] > 0, env["error_count"]
    assert "errors" in env, list(env)
    assert "warning" in env and "부분 실패" in env["warning"], env.get("warning")


def test_F48_7_승격은_표지_목록_한_벌을_따른다():
    """승격 대상이 손으로 적혀 있으면 표지를 늘렸을 때 또 뒤처진다 — markers_of 위임 확인."""
    import inspect
    import workflow_engine
    src = inspect.getsource(workflow_engine.execute_pipeline)
    assert "_honesty_markers_of(prev_result)" in src, "승격이 표지 단일 소스를 안 쓴다"


# ─────────────────── 관문: 표지 전파 ───────────────────

def _gate():
    path = os.path.join(ROOT, "scripts", "check_honesty_propagation.py")
    spec = importlib.util.spec_from_file_location("_hp_gate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_관문_현재_저장소는_통과한다():
    gate = _gate()
    hits = gate.scan(gate._markers())
    assert hits == [], hits


def test_관문_이빨_손으로_적은_표지_목록을_잡는다(tmp_path):
    """이 관문이 막으려는 바로 그 모양 — 경계가 표지를 손으로 열거하는 자리."""
    gate = _gate()
    pkg = tmp_path / "backend"
    pkg.mkdir()
    (pkg / "boundary.py").write_text(
        'KEYS = ("error_count", "errors", "truncated")\n', encoding="utf-8")
    gate.ROOT = tmp_path
    gate.SCAN_ROOTS = [pkg]
    hits = gate.scan(gate._markers())
    assert any(r == "A" for _f, _l, r, _m in hits), hits


def test_관문_사유를_단_자리는_통과시킨다(tmp_path):
    """사유 없는 억제는 불가, 사유 있으면 통과 — 값·경로 관문과 같은 규약."""
    gate = _gate()
    pkg = tmp_path / "backend"
    pkg.mkdir()
    (pkg / "boundary.py").write_text(
        '# hp-ok: 이 목록은 문서 예시라 표지 배관이 아니다\n'
        'KEYS = ("error_count", "errors", "truncated")\n', encoding="utf-8")
    gate.ROOT = tmp_path
    gate.SCAN_ROOTS = [pkg]
    assert gate.scan(gate._markers()) == []


def test_관문이_pre_commit_에_배선돼_있다():
    hook = open(os.path.join(ROOT, "scripts", "git-hooks", "pre-commit"), encoding="utf-8").read()
    assert "check_honesty_propagation.py" in hook


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
