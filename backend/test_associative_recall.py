"""원격 장치 소개: 사용자 배치 정보와 접속 상태를 분리하고 등록 경계를 보존한다."""
import boot_paths  # noqa: F401
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import associative_recall as recall
import device_registry
import limb_keys


def test_device_context_keeps_offline_description_and_escapes_markup(monkeypatch):
    records = [
        {"device_id": "phone", "alias": '폰"<&', "registration": {
            "state": "active", "kind": "phone", "capabilities": {"sdk": 35},
            "context": '스피커 <연결> & 사용자 설명'}},
        {"device_id": "pc", "alias": "office", "registration": {
            "state": "active", "kind": "pc", "paused": True,
            "capabilities": {"os": "windows"}, "context": "작은방 프린터"}},
        {"device_id": "removed", "alias": "removed", "registration": {
            "state": "removed", "context": "제거된 장치"}},
        {"device_id": "member", "alias": "member", "member_id": "m", "registration": {
            "state": "active", "context": "회원 장치"}},
        {"device_id": "expired", "alias": "expired", "expired": True,
         "registration": {"context": "만료된 장치"}},
    ]
    monkeypatch.setattr(limb_keys, "list_keys", lambda **kw: records)
    monkeypatch.setattr(device_registry, "live_with_capability", lambda _: [
        {"device_id": "phone", "alias": '폰"<&'},
        {"device_id": "removed", "alias": "removed"},
        {"device_id": "member", "alias": "member"},
    ])
    req = recall.RecallRequest(None, "거실 음악을 꺼줘", [])
    block = recall._connected_limbs(req, None)
    rows = ET.fromstring(block.text).findall("limb")
    assert len(rows) == 2
    assert rows[0].attrib["name"] == '폰"<&'
    assert rows[0].attrib["os"] == "android"
    assert rows[0].attrib["control_guide"] == "android_control.md"
    assert rows[0].attrib["connected"] == "true"
    assert rows[0].text == '스피커 <연결> & 사용자 설명'
    assert rows[1].attrib["connected"] == "false"
    assert rows[1].attrib["paused"] == "true"
    assert rows[1].attrib["os"] == "windows"
    assert rows[1].attrib["control_guide"] == "pc_control.md"
    assert "def run" not in block.text
    assert rows[1].text == "작은방 프린터"


def test_device_context_respects_vocabulary_gate(monkeypatch):
    monkeypatch.setattr(recall, "_allowed_set", lambda _: {"self"})
    req = recall.RecallRequest(SimpleNamespace(), "프린터", [])
    assert recall._connected_limbs(req, None) is None


def test_device_context_with_no_known_devices_is_empty(monkeypatch):
    monkeypatch.setattr(limb_keys, "list_keys", lambda **kw: [])
    monkeypatch.setattr(device_registry, "live_with_capability", lambda _: [])
    assert recall._connected_limbs(recall.RecallRequest(None, "상태", []), None) is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
