"""은퇴 계약 관문의 이빨 — 관문이 실제로 무는지, 면제가 사유를 강제하는지.

관문 자신이 회귀 없이 서 있으면 "통과"가 무엇을 뜻하는지 아무도 모른다.
동시성·침묵클램프 관문과 같은 규율(`test_concurrency_gate` 형).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_GATE = _ROOT / "scripts" / "check_retired_contracts.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("_t_retired_gate", _GATE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_t_retired_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gate():
    if not _GATE.exists():
        pytest.skip("관문 스크립트 없음")
    return _load_gate()


def test_현재_저장소는_잔재_없이_통과한다(gate, capsys):
    assert gate.main() == 0
    assert "잔재 없음" in capsys.readouterr().out


def test_등록부는_사유와_대체를_강제한다(gate, tmp_path, monkeypatch):
    """사유 없는 등록은 등록이 아니다 — 동결 목록 금지(silent_clamp 교리)."""
    bad = tmp_path / "retired.yaml"
    bad.write_text('retired:\n  - id: x\n    retired: "2026-01-01"\n    phrases: ["아무거나"]\n')
    monkeypatch.setattr(gate, "REGISTRY", bad)
    entries, problems = gate._load_registry()
    assert entries and problems
    assert any("reason" in m for m in problems)
    assert any("instead" in m for m in problems)


def test_잔재가_있으면_문다(gate, tmp_path, monkeypatch):
    """등록된 문구가 스캔 표면에 사유 없이 남아 있으면 관문이 실패해야 한다."""
    reg = tmp_path / "retired.yaml"
    reg.write_text(
        'retired:\n'
        '  - id: probe\n'
        '    retired: "2026-08-27"\n'
        '    reason: "관문 이빨 확인용"\n'
        '    instead: "참인 계약"\n'
        '    phrases: ["_은퇴문구_probe_"]\n')
    victim = tmp_path / "surface.py"
    victim.write_text("# 이 줄은 _은퇴문구_probe_ 를 아직 가르친다\n")

    monkeypatch.setattr(gate, "REGISTRY", reg)
    monkeypatch.setattr(gate, "_scan_files", lambda: [victim])
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    assert gate.main() == 1


def test_사유_있는_표식은_면제되고_빈_표식은_안_된다(gate, tmp_path, monkeypatch):
    reg = tmp_path / "retired.yaml"
    reg.write_text(
        'retired:\n'
        '  - id: probe\n'
        '    retired: "2026-08-27"\n'
        '    reason: "관문 이빨 확인용"\n'
        '    instead: "참인 계약"\n'
        '    phrases: ["_은퇴문구_probe_"]\n')
    monkeypatch.setattr(gate, "REGISTRY", reg)
    monkeypatch.setattr(gate, "ROOT", tmp_path)

    ok = tmp_path / "ok.py"
    ok.write_text("# _은퇴문구_probe_ 를 이름 불러 거절한다  # retired-ok: 이행 진단\n")
    monkeypatch.setattr(gate, "_scan_files", lambda: [ok])
    assert gate.main() == 0

    # 바로 윗줄 표식도 통과(check_concurrency 와 같은 규약)
    above = tmp_path / "above.py"
    above.write_text("# retired-ok: 이행 진단\n# _은퇴문구_probe_ 를 이름 불러 거절한다\n")
    monkeypatch.setattr(gate, "_scan_files", lambda: [above])
    assert gate.main() == 0

    # 사유 없는 빈 표식은 면제가 아니다
    empty = tmp_path / "empty.py"
    empty.write_text("# _은퇴문구_probe_  # retired-ok:\n")
    monkeypatch.setattr(gate, "_scan_files", lambda: [empty])
    assert gate.main() == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
