"""가이드 하향 정규화 회귀 고정물 (docs/COMPONENT_APOPTOSIS_HANDOFF.md §B·§3, 2026-09-02)

관문의 본질: 모델은 압축만 하고, 통과 판정은 기계 대조다 — 압축본이 살아 있는 어휘 참조·절 제목·
살아 있는 코드 경로를 하나라도 잃으면 파일을 쓰지 않고 `unchecked` 로 남긴다(판정 불가 ≠ 무결).

실행: .venv/bin/python -m pytest backend/test_guide_downscale.py -q
"""
import json
import sys

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401,E402

import guide_downscale as GD  # noqa: E402

LIVE = {("self", "read"), ("self", "write"), ("sense", "search")}

ORIGINAL = """# 보고서 가이드

## 1. 수집
[sense:search]{query: "<주제>"} 로 모은다. 자세한 절차는 `backend/ibl/ibl_engine.py` 참조.

## 2. 저장
[self:write]{path: "<경로>"} 로 남긴다.
실측 2026-08-01: 서울만 집계됨.

## 3. 옛 방식
[self:ghost]{} 를 쓰라 (이 문장은 죽은 어휘를 정본처럼 가르친다).
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    guides = tmp_path / "guides"; guides.mkdir()
    monkeypatch.setattr(GD, "BASE", tmp_path)
    monkeypatch.setattr(GD, "GUIDES_DIR", guides)
    monkeypatch.setattr(GD, "NODES_PATH", tmp_path / "ibl_nodes.yaml")
    monkeypatch.setattr(GD, "RETIRED_CONTRACTS_PATH", tmp_path / "retired_contracts.yaml")
    monkeypatch.setattr(GD, "AUDIT_FLAGS_PATH", tmp_path / "guide_audit_flags.json")
    monkeypatch.setattr(GD, "STATE_PATH", tmp_path / "gd_state.json")
    monkeypatch.setattr(GD, "FLAGS_PATH", tmp_path / "gd_flags.json")
    # 절 귀속 DB 도 격리
    import guide_registry as GR
    monkeypatch.setattr(GR, "GUIDES_DIR", guides)
    monkeypatch.setattr(GR, "DB_PATH", tmp_path / "guide_usage.db")
    # 코드 경로 실존을 위한 가짜 backend
    (tmp_path / "backend" / "ibl").mkdir(parents=True)
    (tmp_path / "backend" / "ibl" / "ibl_engine.py").write_text("# x\n", encoding="utf-8")
    (tmp_path / "ibl_nodes.yaml").write_text(
        "nodes:\n  self:\n    actions:\n      read: {}\n      write: {}\n  sense:\n    actions:\n      search: {}\n",
        encoding="utf-8")
    (tmp_path / "retired_contracts.yaml").write_text(
        "retired:\n  - id: x\n    phrases: ['옛 방식']\n", encoding="utf-8")
    commits = []
    monkeypatch.setattr(GD, "COMMIT_FN", lambda paths, msg: (commits.append((paths, msg)) or True))
    p = guides / "report.md"
    p.write_text(ORIGINAL, encoding="utf-8")

    class E:
        pass
    e = E(); e.root = tmp_path; e.guides = guides; e.path = p; e.commits = commits
    return e


POLICY = {"guide_budget_bytes": 36000, "downscale_per_run": 2, "section_unused_min_turns": 3}


def test_markers_are_mechanical(env):
    m = GD.build_markers(ORIGINAL, "report.md", LIVE, POLICY)
    assert any("[self:ghost]" in x for x in m["dead_refs"])
    assert any("옛 방식" in x for x in m["retired_phrases"])
    assert not m["broken_paths"], "실존 경로는 끊긴 것이 아니다"
    assert m["unused_sections"] == [], "귀속이 돌지 않았으면 '미사용'을 말하지 않는다(못 봤음)"


def test_unused_sections_only_when_attribution_observed(env):
    import guide_registry as GR
    for _ in range(3):
        GR.record_section_use("report.md", {("sense", "search")})   # 1절만 쓰였다, 3턴 관측
    m = GD.build_markers(ORIGINAL, "report.md", LIVE, POLICY)
    assert "2. 저장" in m["unused_sections"] and "1. 수집" not in m["unused_sections"]


def test_verify_rejects_lost_action_heading_path_and_growth(env):
    ok = ORIGINAL.replace("[self:ghost]{} 를 쓰라 (이 문장은 죽은 어휘를 정본처럼 가르친다).", "(은퇴 — git 이력 참조)")
    assert GD.verify_compressed(ORIGINAL, ok, LIVE, None) is None
    no_action = ok.replace("[self:write]{path: \"<경로>\"} 로 남긴다.", "저장한다.")
    assert "어휘 참조 유실" in GD.verify_compressed(ORIGINAL, no_action, LIVE, None)
    no_heading = ok.replace("## 2. 저장\n", "")
    assert "절 제목 유실" in GD.verify_compressed(ORIGINAL, no_heading, LIVE, None)
    no_path = ok.replace(" 자세한 절차는 `backend/ibl/ibl_engine.py` 참조.", "")
    assert "코드 경로 유실" in GD.verify_compressed(ORIGINAL, no_path, LIVE, None)
    assert "더 짧아지지 않음" in GD.verify_compressed(ORIGINAL, ORIGINAL + "\n덧", LIVE, None)
    assert "예산" in GD.verify_compressed(ORIGINAL, ok, LIVE, 10)


def test_downscale_one_writes_only_when_gate_passes_and_keeps_lifecycle_mark(env):
    marked = "<!-- lifecycle: candidate since 2026-09-01 — e -->\n" + ORIGINAL
    env.path.write_text(marked, encoding="utf-8")
    good = ORIGINAL.replace("[self:ghost]{} 를 쓰라 (이 문장은 죽은 어휘를 정본처럼 가르친다).", "(은퇴)")
    seen = {}

    def fake_ai(prompt):
        seen["prompt"] = prompt
        return f"머리말\n<<<GUIDE>>>\n{good}\n<<<END>>>"

    r = GD.downscale_one("report.md", POLICY, LIVE, ai_call=fake_ai)
    assert r["ok"] and r["after"] < r["before"]
    txt = env.path.read_text(encoding="utf-8")
    assert txt.startswith("<!-- lifecycle: candidate since"), "표식은 기계 소유 — 모델을 거치지 않고 다시 붙는다"
    assert "[self:ghost]" not in txt and "## 2. 저장" in txt
    assert "<!-- lifecycle" not in seen["prompt"], "표식은 모델에 안 보인다"
    assert "[self:ghost]" in seen["prompt"] and "옛 방식" in seen["prompt"], "표식된 부류가 프롬프트에 실린다"


def test_downscale_one_leaves_file_untouched_on_gate_failure(env):
    bad = ORIGINAL.replace("## 2. 저장\n[self:write]{path: \"<경로>\"} 로 남긴다.\n", "")
    r = GD.downscale_one("report.md", POLICY, LIVE, ai_call=lambda p: f"<<<GUIDE>>>\n{bad}\n<<<END>>>")
    assert not r["ok"] and "유실" in r["reason"]
    assert env.path.read_text(encoding="utf-8") == ORIGINAL


def test_downscale_one_skips_clean_guide_within_budget(env):
    clean = ORIGINAL.replace("[self:ghost]{} 를 쓰라 (이 문장은 죽은 어휘를 정본처럼 가르친다).", "없음")
    clean = clean.replace("## 3. 옛 방식", "## 3. 기타")
    env.path.write_text(clean, encoding="utf-8")
    called = []
    r = GD.downscale_one("report.md", POLICY, LIVE, ai_call=lambda p: called.append(p))
    assert r.get("skipped") and not called, "예산 안·표식 없음 = 강한 시냅스, 건드리지 않는다(모델 호출 0)"


def test_pick_targets_budget_and_flags(env):
    big = env.guides / "big.md"
    big.write_text("# B\n" + ("x" * 500 + "\n") * 80, encoding="utf-8")      # 40KB > 36KB
    (env.guides / "small.md").write_text("# S\n", encoding="utf-8")
    (env.root / "guide_audit_flags.json").write_text(json.dumps({"flags": [{"guide": "report.md", "kind": "premise"}]}))
    t = GD.pick_targets(POLICY)
    names = [x["guide"] for x in t]
    assert names[0] == "big.md" and "report.md" in names and "small.md" not in names


def test_run_guide_downscale_commits_done_and_records_unchecked(env):
    big = env.guides / "big.md"
    big.write_text("# B\n\n## 절\n" + ("x" * 500 + "\n") * 80, encoding="utf-8")

    def fake_ai(prompt):
        if "big.md" in prompt:
            return "<<<GUIDE>>>\n# B\n\n## 절\n짧게.\n<<<END>>>"
        return "<<<GUIDE>>>\n# 깨진\n<<<END>>>"     # report.md 는 절 제목을 잃는다 → 탈락

    (env.root / "guide_audit_flags.json").write_text(json.dumps({"flags": [{"guide": "report.md", "kind": "premise"}]}))
    r = GD.run_guide_downscale(force=True, ai_call=fake_ai)
    assert [d["guide"] for d in r["done"]] == ["big.md"]
    assert any(u["guide"] == "report.md" for u in r["unchecked"])
    assert r["success"] is False and r["data_quality"] == "audit_incomplete", "판정 불가는 무결이 아니다"
    assert env.commits and env.commits[-1][0] == ["data/guides/big.md"]
    assert env.commits[-1][1].startswith("downscale(guide): big.md")
    assert env.path.read_text(encoding="utf-8") == ORIGINAL


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
