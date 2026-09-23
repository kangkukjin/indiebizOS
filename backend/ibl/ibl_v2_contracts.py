"""Data-only compatibility contract construction for inspection and execution."""


def handler_contract(node, action, config, schema_keys=None):
    from ibl_param_vocab import allowed_param_keys
    keys = allowed_param_keys(node, action, config, schema_keys=schema_keys)
    return {"version": 1, "params": {k: "Unknown" for k in sorted(keys or ()) if not k.startswith("_")},
            "open_params": keys is None,
            "required": [], "result": "Record", "effects": ["unknown"],
            "compatibility": "legacy-envelope/1",
            "adapter": {"protocol": "legacy-envelope", "value_path": ""}}
