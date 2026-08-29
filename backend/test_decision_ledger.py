"""결정 원장(decision_ledger) 회상 관문.

D1. 정본 원장이 파싱되고 활성 항목이 스키마(ruling·keywords)를 갖춘다.
D2. 상시 다이제스트 — 무관 질의에도 scent 항목의 ruling 이 나온다(턴 중간 제안 방어).
D3. 질의 일치 — keywords 에 걸리면 상세(why·source)가 얹힌다. 무관 질의엔 상세 없음.
D4. 깨진 원장·부재 = 빈 문자열 (회상 파이프라인 불변, 침묵 크래시 금지).
D5. scent: false 항목은 다이제스트에서 빠지고 질의 일치 때만 나온다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

import decision_ledger  # noqa: E402


def _fresh():
    decision_ledger._cache["mtime"] = None
    decision_ledger._cache["entries"] = []


def test_d1_ledger_parses_with_schema():
    _fresh()
    entries = decision_ledger.load()
    assert entries, "정본 data/decisions.yaml 이 비었거나 파싱 실패"
    for e in entries:
        assert e.get("id") and e.get("ruling"), f"스키마 미달: {e.get('id')}"
        if e.get("status", "active") == "active":
            assert e.get("keywords"), f"활성 판정에 keywords 없음: {e['id']}"


def test_d2_digest_always_on():
    _fresh()
    xml = decision_ledger.scent_xml("오늘 날씨 어때")  # 완전 무관 질의
    assert "<decision_ledger" in xml
    assert "<ruling" in xml, "무관 질의에서 다이제스트가 비었다 — 상시 노출 계약 위반"


def test_d3_query_match_adds_detail():
    _fresh()
    hit = decision_ledger.scent_xml("카탈로그 스코핑을 capability_focus 로 좁히면 어떨까")
    assert 'id="node-scoping-rejected"' in hit
    assert "<detail" in hit, "키워드 일치인데 상세가 안 붙었다"
    miss = decision_ledger.scent_xml("오늘 날씨 어때")
    assert "<detail" not in miss, "무관 질의에 상세가 붙었다 — 토큰 낭비"


def test_d4_broken_or_missing_ledger_is_silent(tmp_path, monkeypatch):
    _fresh()
    bad = tmp_path / "decisions.yaml"
    bad.write_text("{: 이건 yaml 이 아님 ][", encoding="utf-8")
    monkeypatch.setattr(decision_ledger, "_LEDGER_PATH", str(bad))
    assert decision_ledger.scent_xml("아무거나") == ""
    monkeypatch.setattr(decision_ledger, "_LEDGER_PATH", str(tmp_path / "없음.yaml"))
    _fresh()
    assert decision_ledger.scent_xml("아무거나") == ""


def test_d5_scent_false_is_query_gated(tmp_path, monkeypatch):
    _fresh()
    ledger = tmp_path / "decisions.yaml"
    ledger.write_text(
        "- id: quiet-one\n  verdict: 보류\n  ruling: 조용한 판정\n"
        "  keywords: [특별단서]\n  status: active\n  scent: false\n",
        encoding="utf-8")
    monkeypatch.setattr(decision_ledger, "_LEDGER_PATH", str(ledger))
    assert decision_ledger.scent_xml("무관 질의") == ""
    _fresh()
    hit = decision_ledger.scent_xml("특별단서 관련 질문")
    assert 'id="quiet-one"' in hit and "<ruling" in hit


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
