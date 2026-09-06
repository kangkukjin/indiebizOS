"""세상의 도구 지도 + [self:install_lib] 확인·승인 흐름 가드 (2026-09-06).

사용자 판정: 세상(몸 밖 도구)의 지도를 두고 일하다 참조하며, 필요하면 설치 허락을 요구한다 —
완전 자동 설치는 아니다. 이 시험은 그 세 다리를 고정한다:
  ① 지도가 있고 등록돼 있으며 실행자 프롬프트가 그 입구를 가리킨다
  ② check:true 는 부작용 0 (등록·알림·pip 없음) · 이미 있으면 승인 없이 installed
  ③ 승인 없이는 pip 가 돌지 않고, AI 봉투에 우회(curl) 안내가 없다 · 승인 뒤엔 설치되고 승인이 소비된다
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


class _NotifStub:
    def __init__(self):
        self.sent = []

    def create(self, **kw):
        self.sent.append(kw)
        return kw


@pytest.fixture
def gate(monkeypatch, tmp_path):
    """상태 파일·pip·알림을 전부 임시화한다 — 실제 원장·실제 설치·실제 알림에 닿지 않는다."""
    import install_approvals
    import runtime_utils
    import notification_manager
    monkeypatch.setattr(install_approvals, "_STATE_PATH", tmp_path / "install_approvals.json")
    pip_calls = []
    monkeypatch.setattr(runtime_utils, "install_python_dependency",
                        lambda pkg, timeout=300: (pip_calls.append(pkg) or {"success": True, "message": "ok"}))
    stub = _NotifStub()
    monkeypatch.setattr(notification_manager, "get_notification_manager", lambda: stub)
    import ibl_routing
    return ibl_routing, install_approvals, pip_calls, stub


MISSING = "definitely-not-a-real-dist-zz9"


def test_check_is_side_effect_free(gate):
    ibl_routing, ia, pip_calls, stub = gate
    r = ibl_routing._install_lib({"package": MISSING, "check": True})
    assert r["success"] is True and r["status"] == "missing" and r["installed"] is False
    assert ia.list_state() == {"pending": {}, "approved": {}}
    assert pip_calls == [] and stub.sent == []


def test_installed_answers_without_approval(gate):
    ibl_routing, ia, pip_calls, stub = gate
    r = ibl_routing._install_lib({"package": "pip"})  # 이 몸에 반드시 있는 배포판
    assert r["status"] == "installed" and r["success"] is True and r.get("version")
    assert ia.list_state()["pending"] == {} and pip_calls == [] and stub.sent == []


def test_request_registers_pending_without_pip_and_without_bypass_hint(gate):
    ibl_routing, ia, pip_calls, stub = gate
    r = ibl_routing._install_lib({"package": MISSING, "reason": "격자 계산"})
    assert r["approval_required"] is True and r["status"] == "pending" and r["success"] is False
    assert MISSING in ia.list_state()["pending"]
    assert ia.list_state()["pending"][MISSING]["reason"] == "격자 계산"
    assert pip_calls == []
    assert len(stub.sent) == 1 and "도구 관리" in stub.sent[0]["message"] and "격자 계산" in stub.sent[0]["message"]
    assert "curl" not in json.dumps(r, ensure_ascii=False)  # 승인 채널은 사람 것 — AI 봉투에 우회 안내 없음
    # check 로 물으면 pending 이라 답한다
    assert ibl_routing._install_lib({"package": MISSING, "check": True})["status"] == "pending"


def test_approved_then_install_consumes_approval(gate):
    ibl_routing, ia, pip_calls, stub = gate
    ibl_routing._install_lib({"package": MISSING})
    ia.approve(MISSING)  # 사람 채널(HTTP → 도구 관리 창)이 하는 일
    assert ibl_routing._install_lib({"package": MISSING, "check": True})["status"] == "approved"
    r = ibl_routing._install_lib({"package": MISSING})
    assert r["success"] is True and r["status"] == "installed" and pip_calls == [MISSING]
    assert ia.list_state() == {"pending": {}, "approved": {}}


def test_world_tools_map_registered_and_pointed_to():
    guide = ROOT / "data" / "guides" / "world_tools.md"
    assert guide.exists() and guide.stat().st_size <= 36000
    text = guide.read_text(encoding="utf-8")
    assert "check: true" in text and "자동 설치는 없다" in text
    db = json.loads((ROOT / "data" / "guide_db.json").read_text(encoding="utf-8"))
    entry = next(g for g in db["guides"] if g["id"] == "world_tools")
    assert entry["file"] == "world_tools.md" and entry.get("topic")
    frag = (ROOT / "data" / "common_prompts" / "fragments" / "12_ibl_only.md").read_text(encoding="utf-8")
    assert "world_tools.md" in frag and "check: true" in frag and "자동 설치는 없다" in frag
    src = (ROOT / "data" / "ibl_nodes_src" / "self.yaml").read_text(encoding="utf-8")
    assert "check:true" in src.split("install_lib:", 1)[1].split("group:", 1)[0]


if __name__ == "__main__":
    pytest.main([__file__])
