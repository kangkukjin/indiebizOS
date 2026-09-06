"""렌더 예산·변화 없음 관문 + archviz 채점표 (2026-09-06, ep2910: 41분·렌더 27회에 그림이 안 변함).

관문은 bpy 없이 돈다(loader 주입). 채점표는 critic 의 로더로 extends 사슬이 풀려야 한다.
"""
import importlib.util
import os

import boot_paths  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "data", "packages", "installed", "tools", "house-designer")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _load("render_gate_probe", os.path.join(PKG, "render_gate.py"))


def _loader_factory(table):
    return lambda path, size: table.get(path)


def test_g1_budget_refuses_after_limit_and_force_bypasses():
    ledger = {}
    now = 1000.0
    for i in range(G.RENDER_BUDGET):
        ok, _ = G.check_before(ledger, "d.json", "sw", now=now + i)
        assert ok
        ledger.setdefault("d.json", []).append({"ts": now + i, "view": "sw", "out": f"/x/{i}.png", "delta": 0.5})
    ok, why = G.check_before(ledger, "d.json", "sw", now=now + 100)
    assert not ok and "예산 초과" in why and "사용자에게 보여" in why
    ok, why = G.check_before(ledger, "d.json", "sw", now=now + 100, force=True)
    assert ok and "--force" in why
    ok, _ = G.check_before(ledger, "d.json", "sw", now=now + G.BUDGET_WINDOW_S + 200)     # 창이 지나면 다시 허용
    assert ok


def test_g2_still_streak_refuses_only_same_view(tmp_path):
    a = tmp_path / "a.png"; b = tmp_path / "b.png"; c = tmp_path / "c.png"
    for p in (a, b, c):
        p.write_bytes(b"x")
    px = {str(a): [0.5] * 10, str(b): [0.5] * 10, str(c): [0.9] * 10}
    loader = _loader_factory(px)
    ledger = {}
    e1 = G.record_after(ledger, "d.json", "sw", str(a), loader, now=1.0)
    assert e1["delta"] is None and "첫 렌더" in G.note(e1)
    e2 = G.record_after(ledger, "d.json", "sw", str(b), loader, now=2.0)
    assert e2["delta"] == 0.0 and "변화 없음" in G.note(e2)
    ok, _ = G.check_before(ledger, "d.json", "sw", now=3.0)
    assert ok                                                   # 아직 1회
    e3 = G.record_after(ledger, "d.json", "sw", str(a), loader, now=3.0)
    assert e3["delta"] == 0.0
    ok, why = G.check_before(ledger, "d.json", "sw", now=4.0)
    assert not ok and "변화 없음" in why
    ok, _ = G.check_before(ledger, "d.json", "ne", now=4.0)     # 다른 시점은 별개
    assert ok
    e4 = G.record_after(ledger, "d.json", "sw", str(c), loader, now=5.0)   # 실제로 바뀐 그림
    assert e4["delta"] > G.DELTA_MIN and "변화 Δ" in G.note(e4)
    ok, _ = G.check_before(ledger, "d.json", "sw", now=6.0)
    assert ok


def test_g3_ledger_roundtrip(tmp_path):
    ledger = {"d.json": [{"ts": 1.0, "view": "sw", "out": "/x.png", "delta": None}]}
    G.save_ledger(str(tmp_path), ledger)
    assert G.load_ledger(str(tmp_path)) == ledger
    assert G.load_ledger(str(tmp_path / "none")) == {}


def test_g4_archviz_criteria_chain_loads():
    vr = _load("vision_read_probe", os.path.join(ROOT, "data", "packages", "installed", "tools", "media_producer", "vision_read.py"))
    draft, err = vr._load_criteria("archviz_draft")
    assert err is None and "초안" in draft["intro"] and 5 <= len(draft["checks"]) <= 8
    prop, err = vr._load_criteria("archviz")
    assert err is None and len(prop["checks"]) > len(draft["checks"]) and "제안" in prop["intro"]
    final, err = vr._load_criteria("archviz_final")
    assert err is None and len(final["checks"]) > len(prop["checks"]) and "최종" in final["intro"]
    # 초안 채점표는 세부 사실감을 감점하지 말라고 판정기에 말한다 — ep2910 의 이진 "없음" 반복이 여기서 끝난다
    assert "감점하지" in draft["intro"]


def test_g5_cli_stdin_does_not_block_on_open_pipe(monkeypatch):
    """하네스·에이전트 셸의 열린 파이프 stdin 에서 read() 가 영원히 막히던 자리(09-06 실측 10분 대기)."""
    import io
    import sys
    cli = _load("arch_render_cli_probe", os.path.join(ROOT, "data", "scripts", "arch_render_cli.py"))

    class _OpenPipe(io.StringIO):
        def isatty(self):
            return False

        def fileno(self):
            r, w = os.pipe()          # 아무것도 쓰이지 않은 파이프 — select 가 0.3초 안에 비었다고 답해야 한다
            self._keep = (r, w)
            return r

    monkeypatch.setattr(sys, "stdin", _OpenPipe(""))
    assert cli.read_stdin_args() == {}


def test_g6_guide_registered_and_wired():
    import json
    db = json.load(open(os.path.join(ROOT, "data", "guide_db.json"), encoding="utf-8"))
    lst = db if isinstance(db, list) else db["guides"]
    g = next((x for x in lst if x.get("id") == "arch_render"), None)
    assert g and g["file"] == "arch_render.md" and os.path.exists(os.path.join(ROOT, "data", "guides", g["file"]))
    text = open(os.path.join(ROOT, "data", "guides", "arch_render.md"), encoding="utf-8").read()
    for must in ("archviz_draft", "60분 8회", "--sun always", "![외관]("):
        assert must in text


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
