"""Data-only compatibility contract construction for inspection and execution."""
import copy


def _op_effects(config, op):
    from ibl_ops import op_side_effect
    effect = "write_external" if op_side_effect(config, op) else "read_external"
    return [effect, "model"] if config.get("ai_call") is True else [effect]


def project_ops(contract, config):
    """`ops` 선언(허용 op·기본 op·op별 효과)을 계약에 투영한다 — 유도 계약과 손으로 쓴 계약의 한 벌.

    손으로 쓴 `callable_contract` 는 이 투영을 받지 못해 `[sense:realty]{op:"registry"}` 가 check 를
    통과하고 핸들러 폴백으로 실거래 825행 성공이 됐다(상상훈련 76회차 T19·B75-4 재확인).
    선언 계약이 스스로 적은 op 허용값·기본값·효과는 덮지 않는다(어긋남은 빌드 관문이 신고)."""
    ops = (config or {}).get("ops") or {}
    values = list(ops.get("values") or ())
    if not values or "op" not in (contract or {}).get("params", {}):
        return contract
    out = copy.deepcopy(contract)
    out.setdefault("enums", {}).setdefault("op", values)
    if ops.get("default"):
        out.setdefault("defaults", {}).setdefault("op", ops["default"])
    op_variant_effects = any("effects" in v and "op" in v.get("when", {}) for v in out.get("variants", []))
    if (out.get("effects") == ["unknown"] and not op_variant_effects
            and (out.get("adapter") or {}).get("protocol") == "legacy-envelope"):
        out["variants"] = list(out.get("variants", [])) + [
            {"when": {"op": op}, "effects": _op_effects(config, op)} for op in values]
    return out


def project_param_support(contract, config):
    """`param_support` 선언(축 값마다 받는 선택 인자·허용 값)을 조건부 계약으로 투영한다.

    원천마다 읽는 인자가 달라 `[sense:paper]{source:"arxiv", sort_by:"recent", year_from:2026}` 가
    경고 없이 관련도순 옛 논문을 돌려줬다(상상훈련 77회차 B77-1, B76-3 가족). 핸들러 검사만으로는
    check 가 침묵하므로, 같은 표를 계약 변이의 `forbidden`·`enums` 로 올려 정적 검사와 실행이 한 판정을 쓴다.
    축 값 자체도 선언 값(+별칭)만 받는다 — 모르는 원천을 기본 원천인 척 삼키지 않는다."""
    support = (config or {}).get("param_support")
    if not isinstance(support, dict):
        return contract
    axis = support.get("axis")
    table = support.get("values") or {}
    selectors = list(support.get("params") or ())
    params = (contract or {}).get("params", {})
    if not axis or axis not in params or not table:
        return contract
    out = copy.deepcopy(contract)
    aliases = support.get("aliases") or {}
    out.setdefault("enums", {})[axis] = sorted(set(table) | set(aliases))
    if support.get("default"):
        out.setdefault("defaults", {}).setdefault(axis, support["default"])
    variants = list(out.get("variants", []))
    for value in sorted(set(table) | set(aliases)):
        accepted = table.get(aliases.get(value, value)) or {}
        variant = {"when": {axis: value},
                   "forbidden": sorted(k for k in selectors if k not in accepted and k in params)}
        choices = {k: list(v) for k, v in accepted.items() if isinstance(v, list) and k in params}
        if choices:
            variant["enums"] = choices
        variants.append(variant)
    out["variants"] = variants
    return out


def alias_projection(contract, config):
    """액션 `aliases`(판본 1 정규화 표)를 판본 2 계약 별칭(별칭→정본)으로 옮긴 표와 문제 목록.

    한 별칭 무리({정본} ∪ 별칭들) 가운데 계약 params 에 **하나만** 있으면 그것이 판본 2 정본이고
    나머지가 그 별칭이다(판본 2 가 이름을 바꾼 경우 — self:grep root_path→path — 도 같은 규칙).
    무리 전체가 params 밖이면 판본 1 전용 인자라 옮기지 않고, 둘 이상 있으면 계약이 두 이름을 이미
    따로 받는 것이라 옮기지 않는다. 계약이 손으로 적은 별칭이 투영과 겹치면 두 벌 표, 다르면 모순이다.
    (79회차 B79-8: 판본 1 은 desc, 판본 2 는 descending 만 알아 같은 문장이 판본마다 달랐다.)"""
    params = set(((contract or {}).get("params") or {}))
    written = dict(((contract or {}).get("aliases") or {}))
    projected, problems = {}, []
    for canonical, alts in (((config or {}).get("aliases") or {}).items()):
        group = [str(canonical)] + [str(a) for a in (alts or [])]
        inside = [name for name in group if name in params]
        if len(inside) != 1:
            continue
        target = inside[0]
        for name in group:
            if name == target:
                continue
            if name in written:
                problems.append(f"계약 별칭 {name}→{written[name]} 은 액션 aliases 와 두 벌입니다"
                                + ("" if written[name] == target else f"(투영은 {name}→{target})")
                                + " — 액션 aliases 한 곳에만 적으세요")
                continue
            projected[name] = target
    return projected, problems


def project_aliases(contract, config):
    """액션 aliases 를 계약 별칭으로 투영한다(손으로 쓴 별칭은 덮지 않는다 — 어긋남은 빌드 관문)."""
    projected, _ = alias_projection(contract, config)
    if not projected:
        return contract
    out = copy.deepcopy(contract)
    out.setdefault("aliases", {})
    for alias, target in projected.items():
        out["aliases"].setdefault(alias, target)
    return out


def declared_contract(config):
    """손으로 쓴 계약에 선언 투영을 입힌다 — 레지스트리가 쓰는 한 입구."""
    contract = (config or {}).get("callable_contract")
    if not contract:
        return None
    return project_param_support(project_aliases(project_ops(contract, config), config), config)


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
    if config.get("value_validator"):
        contract["value_validator"] = config["value_validator"]
    if config.get("code_params"):
        contract["code_params"] = config["code_params"]
    if ops.get("values"):
        contract = project_ops(contract, config)
    elif "side_effect" in config or config.get("returns") in {"items", "scalar", "effect"}:
        from ibl_ops import resolve_op
        contract["effects"] = _op_effects(config, resolve_op(config))
    return project_param_support(contract, config)
