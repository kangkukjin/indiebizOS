"""몸 번들 파생의 두 성질 회귀 — 관문이 무관한 커밋을 막지 않고, 막을 땐 이유를 댄다 (2026-08-27)

실측 사건: 49회차 상상훈련 수리의 위탁 커밋이 `exit 1` 로 죽었다. 이유는 그 회차가
새로 만든 시험 파일 `backend/test_imagination_round49_repairs.py` 하나였다 —

  ① **글롭 전개.** `data/bodies/android.json` 의 `_force_exclude_glob: ["test_*"]` 은
     "이 파일들은 애초에 엔진 모듈이 아니다"라는 *선언*인데, 옛 파생기는 그 규칙을
     파일별 키로 펼쳐 매니페스트 blocklist 에 넣었다(128건 중 108건이 test_*).
     그래서 backend 에 시험 파일이 하나 생길 때마다 파생본이 흔들렸고, pre-commit 의
     드리프트 관문이 **폰과 아무 상관 없는 커밋**을 막았다.
  ② **이유 없는 신고.** 옛 `--check` 는 *판정*을 (engine_modules + blocklist 키)로
     내리면서 *설명*은 engine_modules 집합 차이만 출력했다. 이번처럼 차이가 blocklist
     쪽에만 있으면 "✗ 드리프트 … 재생성 필요" 한 줄만 나오고 무엇이 다른지가 **빈칸**.
     실패 원인이 로그에 없어 repair_sessions 원장 JSON 을 파야 알 수 있었다.

수리는 각각 파생기 쪽에서 닫았다 — 글롭은 규칙만 기록(`blocklist_globs`), 판정과 설명은
같은 목록(`diff_against`) 하나에서. 이 배터리는 그 두 성질을 못박는다:
못 돌리는 *능력*만 blocklist 에 남고, 드리프트 신고에는 반드시 이유 줄이 따라붙는다.

실행: .venv/bin/python -m pytest backend/test_body_bundle_derivation.py
"""
import copy
import fnmatch
import importlib.util
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_ROOT, "scripts", "build_body_bundle.py")


def _load():
    """scripts/build_body_bundle.py 를 모듈로 — iblbuild_common 이 옆에 있어야 한다."""
    sys.path.insert(0, os.path.join(_ROOT, "scripts"))
    spec = importlib.util.spec_from_file_location("_bbb_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bbb():
    return _load()


def _fake_body(mod, tmp_path, extra_files=()):
    """가짜 backend 트리 + 몸 프로파일을 깔고 derive() 결과를 돌려준다.

    실제 backend 를 쓰지 않는다 — 이 배터리가 지키는 것은 *파생 규칙*이지 현재
    저장소의 모듈 목록이 아니다(그건 pre-commit 의 --check 몫).
    """
    backend = tmp_path / "backend"
    bodies = tmp_path / "data" / "bodies"
    backend.mkdir(parents=True, exist_ok=True)
    bodies.mkdir(parents=True, exist_ok=True)

    (backend / "engine_core.py").write_text("import json\n", encoding="utf-8")
    (backend / "engine_extra.py").write_text("import engine_core\n", encoding="utf-8")
    (backend / "needs_torch.py").write_text("import torch\n", encoding="utf-8")
    (backend / "leans_on_torch.py").write_text("import needs_torch\n", encoding="utf-8")
    (backend / "test_alpha.py").write_text("import engine_core\n", encoding="utf-8")
    for name, body in extra_files:
        (backend / name).write_text(body, encoding="utf-8")

    (bodies / "fake.json").write_text(json.dumps({
        "absent_packages": ["torch"],
        "force_exclude": [],
        "_force_exclude_glob": ["test_*"],
    }, ensure_ascii=False), encoding="utf-8")

    mod.BACKEND = backend
    mod.BODIES = bodies
    return mod.derive("fake")


# ─────────────────────────────────────────────────────────────────────────────
# 성질 ① 글롭은 전개되지 않는다 — 시험 파일이 늘어도 파생본은 그대로
# ─────────────────────────────────────────────────────────────────────────────

def test_glob_rule_is_recorded_not_expanded(bbb, tmp_path):
    d = _fake_body(bbb, tmp_path)
    assert d["blocklist_globs"] == ["test_*"]
    offenders = [m for m in d["blocklist"]
                 if any(fnmatch.fnmatch(m, g) for g in d["blocklist_globs"])]
    assert offenders == [], f"글롭이 파일별 키로 전개됐다(덫 재발): {offenders}"


def test_glob_covered_module_is_not_bundled(bbb, tmp_path):
    """전개하지 않는다고 해서 폰에 실리는 건 아니다 — 엔진에서는 여전히 빠진다."""
    d = _fake_body(bbb, tmp_path)
    assert "test_alpha" not in d["engine_modules"]
    assert "engine_core" in d["engine_modules"]
    assert len(d["engine_modules"]) >= 2, "순서 성질을 볼 수 있으려면 엔진이 둘 이상"


def test_new_test_file_does_not_move_the_manifest(bbb, tmp_path):
    """★49회차를 막았던 바로 그 상황 — 시험 파일 추가는 매니페스트를 흔들지 않는다."""
    before = _fake_body(bbb, tmp_path)
    after = _fake_body(bbb, tmp_path, extra_files=[
        ("test_imagination_round99_repairs.py", "import engine_core\n"),
    ])
    assert bbb.diff_against(before, after) == [], "시험 파일 하나가 파생본을 흔들었다"
    assert before["counts"] == after["counts"]


def test_absent_capability_still_blocklisted_with_reason(bbb, tmp_path):
    """규칙만 기록한다고 '못 돌리는 능력' 판정이 느슨해지진 않는다(전이 포함)."""
    d = _fake_body(bbb, tmp_path)
    assert d["blocklist"]["needs_torch"].startswith("top-level import: torch")
    assert d["blocklist"]["leans_on_torch"] == "via needs_torch"


def test_engine_importing_a_test_module_is_loud(bbb, tmp_path):
    """엔진 모듈이 시험 파일을 최상위 import 하면 폰에서 즉사한다 — 조용히 넘기지 않는다."""
    d = _fake_body(bbb, tmp_path, extra_files=[
        ("sloppy.py", "import test_alpha\n"),
    ])
    assert d["blocklist"].get("sloppy") == "via test_alpha"
    assert "sloppy" not in d["engine_modules"]


# ─────────────────────────────────────────────────────────────────────────────
# 성질 ② 드리프트 신고에는 반드시 이유가 붙는다
# ─────────────────────────────────────────────────────────────────────────────

def test_identical_manifests_report_nothing(bbb, tmp_path):
    d = _fake_body(bbb, tmp_path)
    assert bbb.diff_against(copy.deepcopy(d), d) == []


@pytest.mark.parametrize("mutate,label", [
    (lambda c: c["engine_modules"].append("zzz_new"), "engine 추가"),
    (lambda c: c["engine_modules"].pop(), "engine 제거"),
    (lambda c: c["engine_modules"].reverse(), "engine 순서"),
    (lambda c: c["blocklist"].update({"zzz_blocked": "top-level import: torch"}), "blocklist 추가"),
    (lambda c: c["blocklist"].pop("needs_torch"), "blocklist 제거"),
    (lambda c: c["blocklist"].update({"needs_torch": "force_exclude (프로파일 명시)"}), "사유 변경"),
    (lambda c: c["blocklist_globs"].append("bench_*"), "글롭 규칙 변경"),
])
def test_every_drift_carries_a_reason(bbb, tmp_path, mutate, label):
    """★판정과 설명이 갈라져 '이유 빈칸'이 나오던 자리 — 어떤 차이든 줄이 따라붙는다."""
    derived = _fake_body(bbb, tmp_path)
    stale = copy.deepcopy(derived)
    mutate(stale)
    problems = bbb.diff_against(stale, derived)
    assert problems, f"{label}: 드리프트인데 이유가 빈칸이다"
    assert all(line.strip() for line in problems)


def test_reason_change_names_both_sides(bbb, tmp_path):
    derived = _fake_body(bbb, tmp_path)
    stale = copy.deepcopy(derived)
    stale["blocklist"]["needs_torch"] = "force_exclude (프로파일 명시)"
    line = " ".join(bbb.diff_against(stale, derived))
    assert "needs_torch" in line and "torch" in line


def test_missing_globs_field_in_old_manifest_is_a_named_drift(bbb, tmp_path):
    """수리 전 형식의 기록본을 만나면 '재생성하라'가 아니라 무엇이 없는지를 말한다."""
    derived = _fake_body(bbb, tmp_path)
    stale = copy.deepcopy(derived)
    del stale["blocklist_globs"]
    problems = bbb.diff_against(stale, derived)
    assert any("blocklist_globs" in p for p in problems)


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    raise SystemExit(pytest.main([__file__, "-q"]))
