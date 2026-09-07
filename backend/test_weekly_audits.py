"""weekly_audits 관문 — 주간 감사 넷의 공통 정형 (2026-09-07 신설).

★한 감사의 실패가 나머지를 삼키면 유지보수는 조용히 반만 돈다 — 그 격리를 시험한다.
"""
import boot_paths  # noqa: F401
import weekly_audits as WA


def test_감사_넷이_전부_배선돼_있다():
    keys = [k for k, _, _ in WA.AUDITS]
    assert keys == ["data_ownership", "doc_drift", "store_waste", "vocab_overlap"], keys
    for _, module, func in WA.AUDITS:
        mod = __import__(module, fromlist=[func])
        assert callable(getattr(mod, func)), f"{module}.{func} 없음"


def test_한_감사가_터져도_나머지는_돈다(monkeypatch):
    saved = []
    calls = []

    def fake(key):
        def _run():
            calls.append(key)
            if key == "doc_drift":
                raise RuntimeError("일부러 터뜨림")
            return {"node": "__static__", "action": key, "success": True}
        return _run

    monkeypatch.setattr(WA, "AUDITS", [(k, "weekly_audits", f"_fake_{k}") for k in
                                       ("data_ownership", "doc_drift", "store_waste")])
    for k in ("data_ownership", "doc_drift", "store_waste"):
        monkeypatch.setattr(WA, f"_fake_{k}", fake(k), raising=False)
    r = WA.run_weekly_audits(saved.append)
    assert calls == ["data_ownership", "doc_drift", "store_waste"], calls
    assert "doc_drift" not in r and "store_waste" in r, r
    assert [s["action"] for s in saved] == ["data_ownership", "store_waste"]


def test_카덴스_스킵은_원장에_남기지_않는다(monkeypatch):
    saved = []
    monkeypatch.setattr(WA, "AUDITS", [("store_waste", "weekly_audits", "_fake_skip")])
    monkeypatch.setattr(WA, "_fake_skip", lambda: {"skipped": "cadence"}, raising=False)
    r = WA.run_weekly_audits(saved.append)
    assert r["store_waste"] == {"skipped": "cadence"}
    assert saved == [], "안 돈 감사를 원장에 남겼다"


def test_경고_문구는_감사가_소유한다(monkeypatch, caplog):
    monkeypatch.setattr(WA, "AUDITS", [("store_waste", "weekly_audits", "_fake_msg")])
    monkeypatch.setattr(WA, "_fake_msg", lambda: {
        "node": "__static__", "action": "store_waste", "success": False,
        "error_message": "저장소 낭비 2건 / 회수 가능 133.0MB — store_waste_flags.json"}, raising=False)
    with caplog.at_level("WARNING"):
        WA.run_weekly_audits(lambda _: None)
    assert "회수 가능 133.0MB" in caplog.text, caplog.text


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
