"""4083 실측 수리(2026-09-26): 줄 머리 연산자 이음(언어 개정) · 원장 select limit 의 선택 범위 표기."""
import importlib.util
import json
from pathlib import Path
import boot_paths  # noqa: F401
import pytest
from ibl_v2_ir import Fault
from ibl_v2_parser import parse
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def _value(code, inputs=None):
    out = Runtime(compile_program(code, inputs=inputs), inputs).run()
    assert out["success"], out.get("error")
    return out["value"]


def test_leading_operators_continue_the_previous_expression():
    assert _value("$a = 1\n$b = 2\nreturn [$a]\n  & [$b]") == [[1], [2]]
    assert _value("[def:더하기]($x){return $x + 1}\n$r = 1\n  >> [fn:더하기]{}\nreturn $r") == 2
    tree = parse("$x = 1\n  ?? 7")
    assert tree.data["statements"][0].data["value"].kind == "fallback"   # 줄 머리 ?? 도 한 식
    # 빈 줄이 끼어도 잇는다
    assert _value("$a = [1]\n\n  & [2]\nreturn $a") == [[1], [2]]


def test_plain_newlines_still_separate_statements():
    assert _value("$a = 1\n$b = 2\nreturn $a + $b") == 3
    with pytest.raises(Fault):
        parse("$a = 1\n* 2")   # `*` 는 문장을 시작할 수 없고 잇지도 않는다 — 종전대로 오류
    assert _value("return \"a & b\"") == "a & b"   # 문자열 안은 그대로


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("ledger_scope_probe", ROOT / "data/packages/installed/tools/system_essentials/ledger_ops.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_ROOT", tmp_path)
    return module


def test_select_limit_is_a_selection_scope_not_a_source_truncation(ledger, tmp_path):
    path = tmp_path / "rotation.json"
    path.write_text(json.dumps({"queue": [{"slug": f"s{i}", "verdict": "관심"} for i in range(5)]}), encoding="utf-8")
    out = ledger.op_select({"path": str(path), "target": "queue", "limit": 2, "fields": ["slug"]})
    assert out["success"] and out["count"] == 2 and out["total"] == 5 and out["truncated"]
    assert out["truncations"] == [{"scope": "selection", "unit": "rows", "retained": 2, "total": 5, "parameter": "limit"}]
    full = ledger.op_select({"path": str(path), "target": "queue"})
    assert not full["truncated"] and "truncations" not in full
    # IBL 봉투 해석기: 선택 범위 절단은 원천 불완전이 아니다
    from ibl_v2_adapters import decode_envelope
    value, evidence = decode_envelope(out, {"protocol": "legacy-envelope", "value_path": ""})
    assert value["count"] == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
