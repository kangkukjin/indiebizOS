"""Data-only compatibility contract construction for inspection and execution."""


def handler_contract(node, action, config, schema_keys=None):
    from ibl_param_vocab import allowed_param_keys
    keys = allowed_param_keys(node, action, config, schema_keys=schema_keys)
    contract = {"version": 1, "params": {k: "Unknown" for k in sorted(keys or ()) if not k.startswith("_")},
            "open_params": keys is None,
            "required": [], "result": "Record", "effects": ["unknown"],
            "compatibility": "legacy-envelope/1",
            "adapter": {"protocol": "legacy-envelope", "value_path": ""}}

    # pipe_in is the existing producer/consumer declaration, not a second list
    # of action names. Preserve the legacy input envelope instead of unwrapping.
    if config.get("pipe_in"):
        contract["params"].setdefault("items", "Unknown")
        contract["pipe_input"] = "items"
        contract["adapter"].update(legacy_pipe_input="items", input_envelopes=["items"])
    if config.get("pipe_text"):
        receiver = config["pipe_text"]
        contract["params"][receiver] = "Text"
        contract["pipe_input"] = receiver
    # 스키마의 유한 값 영역을 정적 검사에도 전달한다. 별도의 도구별 목록은 두지 않는다.
    if isinstance(schema_keys, dict):
        enums = {key: list(spec["enum"]) for key, spec in schema_keys.items()
                 if key in contract["params"] and isinstance(spec, dict) and spec.get("enum")}
        if enums:
            contract["enums"] = enums
    ops = config.get("ops") or {}
    if ops.get("values"):
        contract["params"].setdefault("op", "Unknown")
        contract.setdefault("enums", {})["op"] = list(ops["values"])
    if config.get("value_validator"):
        contract["value_validator"] = config["value_validator"]
    if config.get("code_params"):
        contract["code_params"] = config["code_params"]
    from ibl_ops import op_side_effect, resolve_op
    def effects(op):
        effect = "write_external" if op_side_effect(config, op) else "read_external"
        return [effect, "model"] if config.get("ai_call") is True else [effect]
    if ops.get("values"):
        contract["defaults"] = {"op": ops["default"]} if ops.get("default") else {}
        contract["variants"] = [{"when": {"op": op}, "effects": effects(op)}
                                for op in ops["values"]]
    elif "side_effect" in config or config.get("returns") in {"items", "scalar", "effect"}:
        contract["effects"] = effects(resolve_op(config))
    return contract
