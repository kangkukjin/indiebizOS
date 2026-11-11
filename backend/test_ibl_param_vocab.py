"""업무 인자 허용은 액션 선언에 속하며 검사와 실행이 같은 계약을 따른다."""
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
import yaml

from ibl_param_vocab import allowed_param_keys, check_params
from ibl_v2_entry import handle_request


@pytest.mark.parametrize("config,schema,accepted", [
    ({"router": "handler", "tool": "example"}, {"query": {}}, False),
    ({"router": "handler", "tool": "example"}, {"target": {}}, True),
    ({"router": "handler", "tool": "example", "params": {"target": "string"}}, {}, True),
    ({"router": "handler", "tool": "example", "aliases": {"device": ["target"]}}, {}, True),
    ({"router": "handler", "tool": "example", "target_key": "target"}, {}, True),
    ({"router": "system", "open_params": False, "params": {"message": "string"}}, {}, False),
    ({"router": "system", "open_params": False, "params": {"target": "string"}}, {}, True),
])
def test_target_requires_action_declaration(config, schema, accepted):
    keys = allowed_param_keys("sample", "action", config, schema_keys=schema)
    assert ("target" in keys) is accepted


def test_catalog_target_contracts_have_action_owned_declarations():
    """설치 여부와 무관하게 전체 카탈로그의 추론·명시 계약을 대조한다."""
    from ibl_v2_contracts import declared_contract, handler_contract

    root = Path(__file__).resolve().parents[1]
    schemas = {}
    for folder in ("installed", "not_installed"):
        for path in (root / "data/packages" / folder / "tools").glob("*/ibl_actions.yaml"):
            source = yaml.safe_load(path.read_text()) or {}
            for tool in (source.get("tool_json") or {}).get("tools", []):
                schemas[tool["name"]] = (tool.get("input_schema") or {}).get("properties", {})
    catalog = yaml.safe_load((root / "data/ibl_nodes.yaml").read_text())
    for node, entry in catalog["nodes"].items():
        for action, config in entry.get("actions", {}).items():
            schema = schemas.get(config.get("tool"), {})
            declared = set(schema) | set(config.get("params") or {})
            for name, aliases in (config.get("aliases") or {}).items():
                declared.update([name, *aliases])
            if config.get("target_key"):
                declared.add(config["target_key"])
            contract = declared_contract(config) or handler_contract(node, action, config, schema)
            accepted = set(contract["params"]) | set(contract.get("aliases", {}))
            assert ("target" in accepted) == ("target" in declared), f"{node}:{action}"


@pytest.mark.parametrize("action,args", [
    ("limbs:youtube", 'op:"play",query:"OST"'),
    ("self:music", 'op:"stop"'),
    ("sense:stock", 'op:"quote",ticker:"005930"'),
    ("self:notify_user", 'message:"hello"'),
    ("limbs:os_open", 'path:"https://example.com/"'),
    ("sense:realty", 'op:"query",region:"서울"'),
    ("others:delegate", 'agent_id:"worker",message:"hello"'),
    ("others:ask", 'to:"fixture",message:"hello"'),
    ("table:ai", 'items:[],instruction:"분류"'),
    ("table:brief", 'items:[],instruction:"요약"'),
    ("table:chunk", 'text:"hello",size:10'),
    ("table:rename", 'items:[],map:{a:"b"}'),
    ("table:flatten", 'items:[],field:"rows"'),
    ("table:dedup", 'items:[],by:"id"'),
    ("table:since", 'items:[],key:"test"'),
    ("table:groupby", 'items:[],by:"kind"'),
])
def test_unknown_target_rejected_before_any_tool(action, args, monkeypatch, tmp_path):
    import ibl_engine

    calls = []
    monkeypatch.setattr(ibl_engine, "execute_ibl", lambda *a, **k: calls.append(a) or {"success": True})
    # 앞에 정상 부작용 액션이 있어도 전체 프로그램의 잘못된 인자를 먼저 거절해야 한다.
    code = ('[limbs:youtube]{op:"stop"}; '
            f'return [{action}]{{{args},target:"삼성0"}}')
    for check in (True, False):
        result = handle_request({"edition": 2, "code": code, "check": check}, str(tmp_path))
        assert result.get("ok") is False, result
        assert result.get("executed") is False, result
        assert any(i["code"] == "UNKNOWN_ARGUMENT" and "target" in i["message"]
                   for i in result["issues"]), result
    assert calls == []


@pytest.mark.parametrize("source,action,value", [
    ('return [sense:legal]{query:"손해배상",target:"prec"}', "legal", "prec"),
    ('return [self:limb]{op:"pause",target:"device-test",paused:true}', "limb", "device-test"),
    ('return [self:ledger]{op:"select",path:"ledger.json",target:"queue"}', "ledger", "queue"),
    ('return [engines:web]{op:"create",target:"page",project_name:"test",page_name:"home"}', "web", "page"),
    ('return [limbs:guestpc]{op:"info",target:"device-test"}', "guestpc", "device-test"),
])
def test_consumed_targets_reach_dispatch(source, action, value, monkeypatch, tmp_path):
    import ibl_engine

    calls = []
    monkeypatch.setattr(ibl_engine, "execute_ibl",
                        lambda step, *a, **k: calls.append(step) or {"success": True, "items": []})
    result = handle_request({"edition": 2, "code": source}, str(tmp_path))
    assert result.get("success") is True, result
    assert len(calls) == 1 and calls[0]["action"] == action
    canonical = "limb" if action == "guestpc" else "target"
    assert calls[0]["params"][canonical] == value
    if canonical != "target":
        assert "target" not in calls[0]["params"]


def test_target_in_dynamic_arguments_cannot_bypass_contract(monkeypatch, tmp_path):
    import ibl_engine

    calls = []
    def execute(step, *args, **kwargs):
        calls.append(step["action"])
        return {"data": {"op": "play", "query": "OST", "target": "삼성0"}}

    monkeypatch.setattr(ibl_engine, "execute_ibl", execute)
    code = '$args = [self:read]{path:"args.json"}; return [limbs:youtube]{**$args.data}'
    result = handle_request({"edition": 2, "code": code}, str(tmp_path))
    assert result.get("success") is False, result
    assert calls == ["read"], result  # 동적 인자도 재생 핸들러 진입 전에 거절한다.
    assert result["diagnostic"]["code"] == "UNKNOWN_ARGUMENT", result


def test_param_warning_and_node_routing_remain_distinct(monkeypatch, tmp_path):
    import ibl_engine

    issue = check_params("limbs", "youtube", {"op": "play", "query": "OST", "target": "삼성0"})
    assert issue and issue["unknown"] == ["target"]
    calls = []
    monkeypatch.setattr(ibl_engine, "execute_ibl",
                        lambda step, *a, **k: calls.append(step) or {"success": True})
    result = handle_request({"edition": 2, "code": 'return [limbs:youtube]{op:"stop"}@hub'}, str(tmp_path))
    assert result["success"], result
    assert calls[0]["target_node"] == "hub"
    assert "target" not in calls[0]["params"]
