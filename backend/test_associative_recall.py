"""원격 장치 소개: 사용자 배치 정보와 접속 상태를 분리하고 등록 경계를 보존한다."""
import boot_paths  # noqa: F401
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import associative_recall as recall
import device_registry
import limb_keys
import hardware_registry
import pytest


@pytest.fixture(autouse=True)
def isolated_hardware(monkeypatch):
    monkeypatch.setattr(hardware_registry, "devices", lambda: [])


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
    assert len(rows) == 3
    assert rows[0].attrib["device_id"] == "__local__"   # 본체 행이 맨 앞(§5.1)
    assert rows[1].attrib["name"] == '폰"<&'
    assert rows[1].attrib["os"] == "android"
    assert rows[1].attrib["control_guide"] == "android_control.md"
    assert rows[1].attrib["connected"] == "true"
    assert rows[1].text == '스피커 <연결> & 사용자 설명'
    assert rows[2].attrib["connected"] == "false"
    assert rows[2].attrib["paused"] == "true"
    assert rows[2].attrib["os"] == "windows"
    assert rows[2].attrib["control_guide"] == "pc_control.md"
    assert "def run" not in block.text
    assert rows[2].text == "작은방 프린터"


def test_device_context_respects_vocabulary_gate(monkeypatch):
    monkeypatch.setattr(recall, "_allowed_set", lambda _: {"self"})
    req = recall.RecallRequest(SimpleNamespace(), "프린터", [])
    assert recall._connected_limbs(req, None) is None


def test_driver_brief_is_shared_by_devices_and_comes_from_guide(monkeypatch, tmp_path):
    import guide_registry
    from hashlib import sha256
    import json
    directory = tmp_path / "guides"
    directory.mkdir()
    content = '# Driver\n## Short\nCall "driver"; verify <actual> & recover.\n## Long\nDetails'
    (directory / "robot.md").write_text(content)
    (tmp_path / "guide_db.json").write_text(json.dumps({"guides": [{
        "file": "robot.md", "control_platforms": ["robot-os"], "control_brief_section": "Short"}]}))
    monkeypatch.setattr(guide_registry, "DATA_PATH", tmp_path)
    monkeypatch.setattr(guide_registry, "GUIDES_DIR", directory)
    records = [{"device_id": name, "alias": name, "registration": {
        "state": "active", "capabilities": {"os": "robot-os"}}} for name in ("one", "two")]
    monkeypatch.setattr(limb_keys, "list_keys", lambda **kw: records)
    monkeypatch.setattr(device_registry, "live_with_capability", lambda _: records)
    block = recall._connected_limbs(recall.RecallRequest(None, "anything", []), None)
    root = ET.fromstring(block.text)
    briefs = root.findall("control_brief")
    assert len(briefs) == 1
    assert briefs[0].attrib == {"file": "robot.md", "section": "Short",
                                "content_hash": sha256(content.encode()).hexdigest()}
    assert briefs[0].text == '## Short\nCall "driver"; verify <actual> & recover.'
    assert all(r.attrib["control_guide"] == "robot.md" for r in root.findall("limb")[1:])
    previous = SimpleNamespace(blocks=[recall.Block('reusable_capabilities', '', '',
                                                   meta={'control_briefs': ['robot.md']})])
    deduped = recall._connected_limbs(recall.RecallRequest(None, 'anything', []), previous)
    assert not ET.fromstring(deduped.text).findall('control_brief')
    assert 'control_guide="robot.md"' in deduped.text
    monkeypatch.setattr(limb_keys, "list_keys", lambda **kw: [])
    assert not ET.fromstring(recall._connected_limbs(
        recall.RecallRequest(None, "anything", []), None).text).findall("control_brief")


def test_reusable_discovery_adds_only_selected_briefs_within_existing_budget(monkeypatch):
    import guide_registry
    import reusable_catalog
    row = {'id': 'script:one', 'contract_known': True, 'contract': {}}
    brief = {'file': 'one.md', 'text': 'Call, verify, recover.'}
    seen = []
    monkeypatch.setattr(reusable_catalog, 'candidates', lambda q: [dict(row)])

    def selected(names):
        seen.append(list(names))
        return [brief]

    monkeypatch.setattr(guide_registry, 'callable_control_briefs', selected)
    req = recall.RecallRequest(None, 'request', [])
    block = recall._reusable_capabilities(req, None)
    assert seen == [['script:one']]
    assert brief['text'] in block.text and block.meta['control_briefs'] == ['one.md']
    brief['text'] = 'x' * 5000
    block = recall._reusable_capabilities(req, None)
    assert block.meta['control_briefs'] == [] and 'x' * 5000 not in block.text
    row['error'] = 'not allowed'
    recall._reusable_capabilities(req, None)
    assert seen[-1] == []


def test_device_context_with_no_known_devices_still_introduces_local_body(monkeypatch):
    """CONTROL_DRIVER_DESIGN_2026_10_20 §5.1 — 본체는 드라이버(`fn:PC제어` __local__)가 있는데 소개에
    없어 AI 가 화면 조작으로 가던 유일한 면. 등록 장치가 없어도 본체 행 하나는 소개한다."""
    from common.platform_utils import host_os
    monkeypatch.setattr(limb_keys, "list_keys", lambda **kw: [])
    monkeypatch.setattr(device_registry, "live_with_capability", lambda _: [])
    block = recall._connected_limbs(recall.RecallRequest(None, "상태", []), None)
    rows = ET.fromstring(block.text).findall("limb")
    assert [r.attrib["device_id"] for r in rows] == ["__local__"]
    local = rows[0].attrib
    assert local["adapter"] == "local" and local["connected"] == "true" and local["name"] == "본체"
    assert local["os"] == host_os()
    if host_os() in ("darwin", "windows"):
        assert local["control_guide"] == "pc_control.md"
    assert "__local__" in block.text and "상태 조회는 본체([sense:host])" in block.text
    assert "[limbs:screen] 탐색으로 간다" in block.text


def test_device_rows_expose_observation_count_only(monkeypatch):
    """관측은 개수만 행에, 본문은 다룰 때 읽는다(§5.3)."""
    records = [{"device_id": "pc", "alias": "office", "registration": {
        "state": "active", "kind": "pc", "capabilities": {"os": "windows"}, "context": "서재",
        "observations": [{"observation_id": "obs_1", "fact": "비밀 사실", "observed_at": "2026-10-20T10:00",
                          "environment": {"device": "pc"}, "status": "valid"}]}}]
    monkeypatch.setattr(limb_keys, "list_keys", lambda **kw: records)
    monkeypatch.setattr(device_registry, "live_with_capability", lambda _: [])
    block = recall._connected_limbs(recall.RecallRequest(None, "상태", []), None)
    pc = [r for r in ET.fromstring(block.text).findall("limb") if r.attrib["device_id"] == "pc"][0]
    assert pc.attrib["observations"] == "1"
    assert "비밀 사실" not in block.text


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))


@pytest.mark.parametrize("channel", list(recall.CHANNELS))
@pytest.mark.parametrize("route", ["THINK", "EXECUTE", "REFLEX", "REPAIR", "CONTEXT_UPDATE"])
def test_retired_world_catalog_is_not_searched_or_presented(monkeypatch, channel, route):
    """모든 공통 진입점에서 기존 기억은 남고 방법 목록은 분류 후에도 추가되지 않는다."""
    from dataclasses import replace
    import episode_logger
    expected = {"hippocampus", "reusable_capabilities", "memory_map", "recalled_memory",
                "guide_map", "connected_limbs", "pending_repair", "decision_ledger"}
    calls, events = [], []
    def read(source):
        def run(*args, **kwargs):
            calls.append(source.name)
            return recall.Block(source.name, source.tag, f"<{source.tag}>기존 기억</{source.tag}>")
        return run
    monkeypatch.setattr(recall, "_principal_ok", lambda: True)
    monkeypatch.setattr(recall, "SOURCES", tuple(replace(s, fn=read(s)) if s.fn else s for s in recall.SOURCES))
    monkeypatch.setattr(episode_logger, "record_trajectory_event", lambda kind, data: events.append((kind, data)))
    result = recall.begin(None, "직원 근무표를 제약을 지키며 짜야 한다", channel=channel)
    result.attach("pursuit", "<pursuit>현재 과제</pursuit>")
    result.route(route)
    assert set(calls) == expected and len(calls) == len(expected)
    assert {b["source"] for b in result.presented()} == expected | {"pursuit"}
    assert "현재 과제" in result.text() and "기존 기억" in result.text()
    result.route(route)
    assert len(events) == 1 and events[0][0] == "recall.presented"
    assert not {"method_map", "world_memory"} & set(recall.USAGE)
