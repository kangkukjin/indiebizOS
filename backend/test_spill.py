"""common.spill — 스필 루트 시임과 gc(최상위 24h·하위 트리 7일) 계약."""
import os
import time

import pytest

from common import spill


def _touch(path, age_s):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    t = time.time() - age_s
    os.utime(path, (t, t))


def test_gc_is_top_level_only_and_gc_evidence_walks_subtrees_7d(tmp_path, monkeypatch):
    root = tmp_path / "spill"
    monkeypatch.setattr(spill, "_root", lambda: str(root))
    day = 24 * 3600
    _touch(root / "old_top.json", 2 * day)                                   # 최상위 24h 초과 → 삭제
    _touch(root / "new_top.json", 60)                                        # 최상위 신선 → 유지
    _touch(root / "tool_evidence" / "ns1" / "a.evidence.json", 8 * day)      # 하위 7일 초과 → 삭제, 빈 ns 제거
    _touch(root / "tool_evidence" / "ns2" / "b.evidence.json", 2 * day)      # 하위 7일 안 → 유지(최상위 24h 규칙 적용 안 됨)
    _touch(root / "supervision" / "turn1" / "events.jsonl", 9 * day)         # 삭제, 빈 턴 제거
    _touch(root / "supervision" / "turn2" / "events.jsonl", 60)              # 유지
    assert spill.gc() == 1                                                   # 티켓 경로의 gc 는 최상위만(싸게)
    assert not (root / "old_top.json").exists() and (root / "new_top.json").exists()
    assert (root / "tool_evidence" / "ns1" / "a.evidence.json").exists()
    assert spill.gc_evidence() == 2
    assert not (root / "tool_evidence" / "ns1").exists()
    assert (root / "tool_evidence" / "ns2" / "b.evidence.json").exists()
    assert not (root / "supervision" / "turn1").exists()
    assert (root / "supervision" / "turn2" / "events.jsonl").exists()
    assert (root / "tool_evidence").exists() and (root / "supervision").exists()   # 상위 디렉터리는 남긴다


def test_gc_keeps_running_ticket_whose_owner_is_alive(tmp_path, monkeypatch):
    root = tmp_path / "spill"
    monkeypatch.setattr(spill, "_root", lambda: str(root))
    import json
    p = root / "ticket_abc.json"
    _touch(p, 3 * 24 * 3600)
    monkeypatch.setattr("common.completion_contract.owner_alive", lambda owner: True)
    p.write_text(json.dumps({"status": "running", "owner": {"pid": os.getpid()}}))
    t = time.time() - 3 * 24 * 3600
    os.utime(p, (t, t))
    assert spill.gc() == 0 and p.exists()


def test_maintenance_bundle_wires_spill_gc_evidence():
    """일일 유지보수 번들이 spill.gc 를 부른다 — 번들 자체를 실행하지 않는다(실 포식·기억 정리가 돌아
    145초 걸리고 라이브 저장소를 만진다, 2026-10-04 실측). 배선은 소스로 확인한다."""
    import inspect
    from cognition import world_pulse_health as wph
    src = inspect.getsource(wph.run_maintenance_bundle)
    assert "spill.gc_evidence(" in src and "result['spill']" in src


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23 규약)
    import sys
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
