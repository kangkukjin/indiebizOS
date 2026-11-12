"""원격 장치 소개: 다섯 소개 범주만 제공하고 상태·계약 조회와 등록 경계를 보존한다."""
import boot_paths  # noqa: F401
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import associative_recall as recall
import device_registry
import limb_keys
import hardware_registry
import pytest


def test_function_use_requires_current_identity_and_separates_success():
    ref = {'scope_id': 'owner', 'function_id': 'function', 'revision': 'v2'}
    item = {'id': '5', 'alias': '재사용', 'code': '[fn:재사용]{}', 'function_ref': ref}
    ev = {'ibl_codes': ['#!ibl edition=2\n[fn:재사용]{}'], 'tool_calls': []}
    assert recall._used_hippocampus(['5'], {'items': [item]}, ev)['used'] == []
    def usage(**fields):
        return {'result': {'capability_usage': [{'function_ref': {**ref, 'name': '재사용'},
                                                'call_id': '1', 'run_id': 'run', **fields}]}}
    ev['tool_calls'] = [usage(success=False)]
    result = recall._used_hippocampus(['5'], {'items': [item]}, ev)
    assert result['attempted'] == ['5'] and result['successful'] == []
    ev['tool_calls'] = [usage(success=True, source_complete=True)]
    result = recall._used_hippocampus(['5'], {'items': [item]}, ev)
    assert result['used'] == result['successful'] == ['5']
    assert result['function_receipts'][0]['call_id'] == '1'
    ev['tool_calls'][0]['result']['capability_usage'][0]['function_ref']['revision'] = 'v1'
    assert recall._used_hippocampus(['5'], {'items': [item]}, ev)['used'] == []


@pytest.fixture(autouse=True)
def isolated_hardware(monkeypatch):
    monkeypatch.setattr(hardware_registry, "devices", lambda: [])


def test_device_context_keeps_offline_description_and_escapes_markup(monkeypatch):
    records = [
        {"device_id": "phone", "alias": '폰"<&', "registration": {
            "state": "active", "kind": "phone", "adapter": "indiebiz-v1", "capabilities": {"sdk": 35},
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
    assert "android_control" in rows[1].attrib["drivers"].split(",")
    assert rows[1].text == '스피커 <연결> & 사용자 설명'
    assert rows[2].attrib["os"] == "windows"
    assert "pc_control" in rows[2].attrib["drivers"].split(",")
    # 행의 속성은 식별·환경과 기기가 신고한 몸(body)·헬퍼 수단(own)까지다. 접속·설치 같은 상태는 싣지 않는다.
    assert all(set(row.attrib) <= {"name", "device_id", "kind", "os", "adapter", "body", "own", "drivers"}
               for row in rows)
    assert "def run" not in block.text
    assert rows[2].text == "작은방 프린터"


def test_device_context_respects_vocabulary_gate(monkeypatch):
    monkeypatch.setattr(recall, "_allowed_set", lambda _: {"self"})
    req = recall.RecallRequest(SimpleNamespace(), "프린터", [])
    assert recall._connected_limbs(req, None) is None


def test_driver_references_are_shared_and_follow_current_catalog(monkeypatch, tmp_path):
    import guide_registry
    import json
    directory = tmp_path / "guides"
    directory.mkdir()
    content = '# Driver\n## Short\nCall "driver"; verify <actual> & recover.'
    (directory / "robot.md").write_text(content)
    catalog = {"guides": [{"file": "robot.md", "driver": {
        "id": "robot", "platforms": ["robot-os"], "surfaces": ["os"],
        "brief_section": "Short", "callables": ["script:robot"]}}]}
    path = tmp_path / "guide_db.json"
    path.write_text(json.dumps(catalog))
    monkeypatch.setattr(guide_registry, "DATA_PATH", tmp_path)
    monkeypatch.setattr(guide_registry, "GUIDES_DIR", directory)
    records = [{"device_id": name, "alias": name, "registration": {
        "state": "active", "capabilities": {"os": "robot-os"}}} for name in ("one", "two")]
    monkeypatch.setattr(limb_keys, "list_keys", lambda **kw: records)
    monkeypatch.setattr(device_registry, "live_with_capability", lambda _: records)

    def read():
        return ET.fromstring(recall._connected_limbs(recall.RecallRequest(None, "anything", []), None).text)

    root = read()
    assert not root.findall("control_brief")
    assert root.find("driver").attrib == {"id": "robot", "guide": "robot.md", "surfaces": "os"}
    assert len(root.findall("driver")) == 1
    assert all(r.attrib["drivers"] == "robot" for r in root.findall("limb")[1:])
    assert content not in ET.tostring(root, encoding="unicode")
    # The reference resolves through the existing guide API; edits are not cached in the introduction.
    assert guide_registry.resolve_guide_reference("robot.md", catalog["guides"], directory)["content"] == content
    changed = content + "\nUpdated recovery condition."
    (directory / "robot.md").write_text(changed)
    assert guide_registry.resolve_guide_reference("robot.md", catalog["guides"], directory)["content"] == changed
    catalog["guides"][0]["driver"]["id"] = "robot-v2"
    path.write_text(json.dumps(catalog))
    assert read().find("driver").attrib["id"] == "robot-v2"
    # Legacy control_* registrations remain resolvable without installing any component.
    catalog["guides"] = [{"file": "robot.md", "control_platforms": ["robot-os"],
                           "control_brief_section": "Short"}]
    path.write_text(json.dumps(catalog))
    assert read().find("driver").attrib == {"id": "robot", "guide": "robot.md", "surfaces": "os"}
    assert guide_registry.device_drivers("robot-os", "resident-v1")["components"] == []
    catalog["guides"] = [{"file": "robot.md", "driver": {
        "id": "robot-v2", "platforms": ["robot-os"], "surfaces": ["os"]}}]
    # Ambiguous owners are absent in the introduction but explicit in driver detail.
    (directory / "other.md").write_text(content)
    catalog["guides"].append({**catalog["guides"][0], "file": "other.md"})
    path.write_text(json.dumps(catalog))
    assert not read().findall("driver")
    assert guide_registry.device_drivers("robot-os", "resident-v1")["conflicts"] == ["driver_conflict:robot-v2"]


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
    assert local["adapter"] == "local" and local["name"] == "본체"
    assert local["os"] == host_os()
    if host_os() in ("darwin", "windows"):
        assert "pc_control" in local["drivers"].split(",")
    assert "__local__" in block.text
    assert "limb:이름/ID" in block.text and "target:device_id" in block.text


def test_device_rows_introduce_the_indiebiz_body_and_the_helper_level_means(monkeypatch):
    """2026-11-12 사용자 결정 — 등록 기기에 IndieBiz OS 가 있으면 그 몸에 IBL 문장을 보내는 것이 기본 통로다.
    소개 행이 위치·용도만 말하던 때 중앙은 IndieBiz OS 가 도는 PC 의 재생기·브라우저를 직접 다뤘다(에피소드 6036·6038·6039).
    행은 기기의 신고대로 몸(body)과 헬퍼 수준 수단(own)을 나눠 싣고, 신고에 없는 것은 싣지 않는다."""
    def record(device_id, kind, capabilities, adapter="resident-v1"):
        return {"device_id": device_id, "alias": device_id, "registration": {
            "state": "active", "kind": kind, "adapter": adapter, "capabilities": capabilities, "context": "서재"}}
    records = [
        record("helper-only", "pc", {"os": "windows", "shell": True, "media_player": "C:\\tools\\mpv.exe",
                                     "interactive": True, "ibl": False,
                                     "media_session": {"speaker": True, "camera": False}}),
        record("pc-with-body", "pc", {"os": "linux", "shell": True, "ibl": True, "card": {"action_count": 58}}),
        record("phone", "phone", {"os": "android", "ibl": True, "python": "3.11", "ops": ["ibl", "media"],
                                  "card": {"action_count": 48}}, adapter="indiebiz-v1"),
        record("silent", "pc", {"os": "linux"}),
    ]
    monkeypatch.setattr(limb_keys, "list_keys", lambda **kw: records)
    monkeypatch.setattr(device_registry, "live_with_capability", lambda _: [])
    block = recall._connected_limbs(recall.RecallRequest(None, "상태", []), None)
    rows = {r.attrib["device_id"]: r.attrib for r in ET.fromstring(block.text).findall("limb")}
    assert rows["helper-only"]["own"] == "셸, 재생기 mpv, 화면, 스피커" and "body" not in rows["helper-only"]
    assert rows["pc-with-body"]["body"] == "IndieBiz OS(자체 어휘 58개)" and rows["pc-with-body"]["own"] == "셸"
    assert rows["phone"]["body"] == "IndieBiz OS(자체 어휘 48개)" and rows["phone"]["own"] == "Python, 재생기"
    assert not {"own", "body"} & set(rows["silent"]) and not {"own", "body"} & set(rows["__local__"])
    # 통로의 구조를 한 번 설명한다 — 몸에는 문장, 헬퍼 수단은 그 아래층.
    note = ET.fromstring(block.text).attrib["note"]
    assert '[limbs:guestpc]{op:"ibl",limb,code}' in note and "body 가 없는 기기의 길" in note


def test_device_rows_do_not_read_or_expose_observations(monkeypatch):
    """관측 개수와 본문은 기존 상세 조회에만 남긴다."""
    import control_observations
    monkeypatch.setattr(control_observations, "count", lambda *a: pytest.fail("observation lookup during introduction"))
    records = [{"device_id": "pc", "alias": "office", "registration": {
        "state": "active", "kind": "pc", "capabilities": {"os": "windows"}, "context": "서재",
        "observations": [{"observation_id": "obs_1", "fact": "비밀 사실", "observed_at": "2026-10-20T10:00",
                          "environment": {"device": "pc"}, "status": "valid"}]}}]
    monkeypatch.setattr(limb_keys, "list_keys", lambda **kw: records)
    monkeypatch.setattr(device_registry, "live_with_capability", lambda _: [])
    block = recall._connected_limbs(recall.RecallRequest(None, "상태", []), None)
    pc = [r for r in ET.fromstring(block.text).findall("limb") if r.attrib["device_id"] == "pc"][0]
    assert "observations" not in pc.attrib
    assert "비밀 사실" not in block.text


@pytest.mark.parametrize("count", [1, 10, 100, 1000])
def test_device_introduction_scales_only_rows_without_status_or_guide_reads(monkeypatch, count):
    import guide_registry
    import hardware_driver_status
    import resident_pcs
    from unittest.mock import Mock
    catalog = Mock(wraps=guide_registry.driver_catalog)
    monkeypatch.setattr(guide_registry, "driver_catalog", catalog)
    for module, name in [(guide_registry, "control_briefs"), (guide_registry, "device_drivers"),
                         (hardware_driver_status, "describe"), (resident_pcs, "devices")]:
        monkeypatch.setattr(module, name, lambda *a, **kw: pytest.fail("eager driver detail"))
    context = '위치 <&> / ' + '사용자 용도 설명 ' * 250
    records = [{"device_id": f"pc-{i}", "alias": "같은 이름", "registration": {
        "state": "active", "adapter": "resident-v1", "kind": "pc", "context": context,
        "paused": bool(i % 2), "generation": f"generation-{i}",
        "capabilities": {"os": "windows", "admin": True, "helper_sha256": "private-hash",
                         "service_scope": "user_login"}}} for i in range(count)]
    monkeypatch.setattr(limb_keys, "list_keys", lambda **kw: records)
    # Cached live presence affects inclusion only; offline described targets remain discoverable.
    monkeypatch.setattr(device_registry, "live_with_capability", lambda _: records[::2])
    block = recall._connected_limbs(recall.RecallRequest(None, "오늘 날씨", []), None)
    root = ET.fromstring(block.text)
    rows = root.findall("limb")
    assert len(rows) == count + 1 and len({r.attrib["device_id"] for r in rows}) == count + 1
    assert all(r.text == context for r in rows[1:])  # no silent clipping
    assert all(set(r.attrib) <= {"name", "device_id", "kind", "os", "adapter", "drivers"} for r in rows)
    refs = {r.attrib["id"]: r.attrib for r in root.findall("driver")}
    assert len(refs) == 3 and catalog.call_count == 1
    assert refs["remote_pc_execution"]["guide"] == "remote_pc_execution.md"
    assert all(set(r.attrib.get("drivers", "").split(",")) - {""} <= refs.keys() for r in rows)
    assert not root.findall("control_brief") and "private-hash" not in block.text


def test_device_introduction_preserves_scope_and_registration_boundaries(monkeypatch):
    records = []
    for identifier, os_name, scope, adapter in [
            ("user", "windows", "user_login", "resident-v1"),
            ("machine", "windows", "machine", "resident-v1"),
            ("mac", "darwin", "user_login", "resident-v1"),
            ("linux", "linux", "unknown", "resident-v1"),
            ("portable", "windows", "unknown", None),
            ("unknown", "unmapped-os", "unknown", "unmapped-adapter"),
            ("numeric-os", 42, "unknown", "unmapped-adapter")]:
        record = {"device_id": identifier, "alias": "중복 이름", "env": {"os": os_name}}
        if adapter:
            record["registration"] = {"state": "active", "adapter": adapter, "context": "사용자 설명",
                                      "capabilities": {"os": os_name, "service_scope": scope}}
        records.append(record)
    records.extend([
        {"device_id": "invite", "invitation": True, "registration": {"context": "초대"}},
        {"device_id": "expired", "expired": True, "registration": {"context": "만료"}},
        {"device_id": "removed", "registration": {"state": "removed", "context": "삭제"}},
        {"device_id": "member", "member_id": "m", "registration": {"context": "회원"}},
        {"device_id": "unseen", "registration": {"state": "active"}},
    ])
    monkeypatch.setattr(limb_keys, "list_keys", lambda **kw: records)
    monkeypatch.setattr(device_registry, "live_with_capability", lambda _: records[:-1])
    root = ET.fromstring(recall._connected_limbs(recall.RecallRequest(None, "장치", []), None).text)
    rows = {r.attrib["device_id"]: r.attrib for r in root.findall("limb")}
    assert set(rows) == {"__local__", "user", "machine", "mac", "linux", "portable", "unknown", "numeric-os"}
    assert "pc_control" in rows["user"]["drivers"].split(",")
    assert "pc_control" not in rows["machine"]["drivers"].split(",")
    assert rows["machine"]["drivers"] == rows["linux"]["drivers"] == "remote_pc_execution,remote_pc_installation"
    assert "drivers" not in rows["unknown"] and "drivers" not in rows["numeric-os"]
    assert rows["numeric-os"]["os"] == "42"
    assert rows["portable"]["adapter"] == "portable"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))


@pytest.mark.parametrize("channel", list(recall.CHANNELS))
@pytest.mark.parametrize("route", ["THINK", "EXECUTE", "REPAIR", "CONTEXT_UPDATE"])
def test_retired_catalogs_are_not_searched_or_presented(monkeypatch, channel, route):
    """모든 공통 진입점에서 기존 기억은 남고 방법·부품 후보는 분류 후에도 추가되지 않는다."""
    from dataclasses import replace
    import episode_logger
    expected = {"hippocampus", "memory_map", "recalled_memory",
                "guide_map", "connected_limbs", "pending_repair", "decision_ledger"}
    import reusable_catalog

    def unexpected_discovery(*args, **kwargs):
        pytest.fail("자동 회상에서 부품 후보나 설명을 조회했습니다")

    monkeypatch.setattr(reusable_catalog, "candidates", unexpected_discovery)
    monkeypatch.setattr(reusable_catalog, "discovery_payload", unexpected_discovery)
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
    assert "reusable_capabilities" not in result.text()
    result.route(route)
    assert len(events) == 1 and events[0][0] == "recall.presented"
    assert not {"method_map", "world_memory"} & set(recall.USAGE)
