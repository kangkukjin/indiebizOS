"""Declared vocabulary adapters. Action names never drive language semantics.

Catalog contracts select an adapter protocol. Existing leaf routing still owns
permissions, actor context, file protection, receipts and package dispatch.
"""
from dataclasses import dataclass
from pathlib import Path
import copy
import json
from ibl_v2_ir import Fault, UNIT, digest
from ibl_v2_types import guard, declared
from ibl_v2_expr import boolean


@dataclass(frozen=True)
class Adapter:
    contract: dict
    run: object
    authorize: object = None
    dependency: object = None
    # args → bool: 이 호출의 영수증을 고친 프로그램이 재사용해도 되는가. 선언 effects 가 미상(legacy)인
    # 어휘는 부작용 해소 규칙(ibl_ops.op_side_effect — 안전 분류·dry-run·건강검진과 같은 한 벌)로 op 단위 판정.
    reusable: object = None
    stateful: object = None
    resource_identity: object = None
    model_identity: object = None
    invocation_dependency: object = None


@dataclass(frozen=True)
class Adapted:
    value: object
    evidence: dict


def validate_contract(contract):
    if not isinstance(contract, dict) or contract.get("version") != 1:
        raise ValueError("callable_contract.version은 1이어야 합니다.")
    if not isinstance(contract.get("params"), dict):
        raise ValueError("callable_contract.params가 필요합니다.")
    for spec in contract["params"].values():
        declared(spec)
    declared(contract["result"])
    effects = contract.get("effects")
    if not isinstance(effects, list) or not effects or not set(effects) <= {"pure", "read_external", "write_external", "model", "unknown"}:
        raise ValueError("올바른 effects가 필요합니다.")
    if "pure" in effects and len(effects) != 1:
        raise ValueError("pure는 다른 효과와 함께 선언할 수 없습니다.")
    reuse_model = contract.get('model_reuse')
    if reuse_model is not None:
        if effects != ['model'] or not isinstance(reuse_model, dict):
            raise ValueError('model_reuse는 입력값만 쓰는 model 단독 효과의 설정 선언입니다.')
        if not ((set(reuse_model) == {'role'} and isinstance(reuse_model['role'], str) and reuse_model['role'])
                or (set(reuse_model) == {'provider', 'model'}
                    and all(isinstance(v, str) and v for v in reuse_model.values()))):
            raise ValueError('model_reuse는 {role} 또는 {provider,model}입니다.')
    if 'per_run' in contract and type(contract['per_run']) is not bool:
        raise ValueError('per_run은 실행 시점 값의 재사용 여부를 나타내는 Bool입니다.')
    if contract.get("pipe_input") and contract["pipe_input"] not in contract["params"]:
        raise ValueError("pipe_input은 선언된 인자여야 합니다.")
    if not set(contract.get("required", contract["params"])) <= contract["params"].keys():
        raise ValueError("required는 params에 포함되어야 합니다.")
    for name in ('read_resources', 'write_resources'):
        resources = contract.get(name, {})
        if not isinstance(resources, dict) or any(v not in contract["params"] for v in resources.values()):
            raise ValueError(f"{name}는 자원 종류→선언 인자 이름입니다.")
    adapter = contract.get("adapter", {})
    envelopes = adapter.get("input_envelopes", [])
    if (not isinstance(envelopes, list)
            or any(not isinstance(key, str) or key not in contract["params"] for key in envelopes)):
        raise ValueError("input_envelopes는 선언된 입력 인자 이름 목록입니다.")
    if adapter.get("protocol") not in {"core-table/2", "legacy-envelope", "ibl-script/2", "document-value/1", "ibl-script-session/1"}:
        raise ValueError("지원하지 않는 어댑터 프로토콜입니다.")
    if adapter.get('protocol') == 'ibl-script-session/1' and (
            effects != ['unknown'] or adapter.get('stateful') is not True
            or adapter.get('local_code') is not True):
        raise ValueError('세션 스크립트는 unknown 효과·stateful·local_code를 명시해야 합니다.')
    from ibl_callable_contract import validate_extensions
    validate_extensions(contract)
    return contract


def table_operation(operation, runtime, args):
    from ibl_v2_runtime import Binding
    from common.value_semantics import sort_records, integer_value
    rows = args["items"]
    def at_row(fn, row, index, result_type=None):
        try:
            value = runtime.callback(fn, [Binding(row)]).value
            return guard(value, result_type, operation + " 콜백") if result_type else value
        except Fault as error:
            error.details.setdefault("row_index", index)
            error.details.setdefault("operation", operation)
            raise
    if operation == "filter":
        return [row for index, row in enumerate(rows) if at_row(args["where"], row, index, "Bool")]
    if operation == "select":
        columns = args["columns"]
        if isinstance(columns, list):
            for index, row in enumerate(rows):
                missing = [k for k in columns if not isinstance(row, dict) or k not in row]
                if missing:
                    raise Fault("MISSING_FIELD", f"select 입력 {index}번 행에 열이 없습니다: {missing}",
                                details={"row_index": index, "missing_fields": missing})
            return [{k: row[k] for k in columns} for row in rows]
        return [at_row(columns, row, index, "Record") for index, row in enumerate(rows)]
    if operation == "take":
        count = integer_value(args["n"])
        if count is None or count < 0:
            raise Fault("TAKE_COUNT", "take.n은 0 이상의 정수입니다.")
        return rows[:count]
    if operation == "sort":
        # The shared ordering primitive tolerates missing cells. The adapter
        # must distinguish those from an entirely absent ranking criterion;
        # otherwise sort -> take certifies the original order as a ranking.
        keys = [args["by"]] if isinstance(args["by"], str) else args["by"]
        if not isinstance(keys, list) or not keys or any(not isinstance(k, str) or not k for k in keys):
            raise Fault("ARGUMENT_CONTRACT", "sort.by는 필드 이름 또는 필드 이름 목록입니다(앞의 키가 먼저).")
        for key in keys:
            if rows and not any(key in row for row in rows):
                available = list(dict.fromkeys(k for row in rows[:20] for k in row))[:12]
                raise Fault("MISSING_FIELD", f"sort의 기준 필드가 입력 행에 없습니다: {key}. "
                            f"입력 필드 예: {available}")
        # 안정 정렬을 뒤 키부터 쌓는다 — 앞 키가 같은 행끼리 다음 키 순서가 남는다.
        for key in reversed(keys):
            rows = sort_records(rows, key, descending=args.get("descending", False))
        return rows
    if operation == "compute":
        return [{**row, **at_row(args["set"], row, index, "Record")}
                for index, row in enumerate(rows)]
    raise Fault("ADAPTER", f"지원하지 않는 표 어댑터: {operation}", kind="protocol")


def pointer(value, path):
    if not path:
        return value
    for key in path.removeprefix("/").split("/"):
        key = key.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or key not in value:
            raise Fault("ADAPTER_SHAPE", f"선언된 반환 경로가 없습니다: {path}")
        value = value[key]
    return value


def inner_diagnostics(raw, limit=5):
    """판본 2 안쪽 실행·저장(`[self:workflow]{op:"run"|"save"}` 등)의 진단을 경계 너머로 (71회차 B71-3).

    안쪽 봉투는 판본 2 자신의 형식(issues·diagnostic)인데 옛 도구 봉투의 허용 목록으로만 읽어
    코드·위치가 사라졌다. 크기 제한: 진단 5개·메시지 500자, 코드·안내·줄·칸만."""
    if raw.get("edition") != 2:
        return []
    items = [i for i in (raw.get("issues") or []) if isinstance(i, dict)]
    if isinstance(raw.get("diagnostic"), dict):
        items.append(raw["diagnostic"])
    out = []
    for item in items[:limit]:
        where = item.get("location") or item.get("source_span") or {}
        row = {key: str(item[key])[:500] for key in ("code", "message", "hint") if item.get(key)}
        row.update({key: where[key] for key in ("line", "column", "source") if where.get(key) is not None})
        out.append(row)
    return out



# 수량 인자로 풀 수 있는 절단 사유 — bounded_selection 의 reason 은 생산자가 쓴 인자 이름이다.
_COUNT_REASONS = {"limit", "count", "top_k", "max_results", "max_points", "max_length", "count_per_month"}


def _partial_message(raw, truncation):
    """불완전 원천의 거절이 고칠 방향을 말하게 한다(72회차 후속: 기본 상한 절단이 이제 여기로 온다).

    기본 상한으로 잘린 원천은 선택(selection)이 아니라 불완전(source)이다. 상한 인자를 명시하면
    그만큼의 선택으로 받는다 — 그 길을 말하지 않으면 모델은 같은 호출을 되풀이한다."""
    message = "도구의 원천 결과가 불완전합니다."
    cut = [t for t in (truncation or {}).get("truncations", []) if t.get("scope") != "selection"]
    if cut and cut[0].get("reason"):
        first = cut[0]
        message += f" 절단 사유 `{first['reason']}`" + (f"(상한 {first['limit']})" if first.get("limit") is not None else "") + "."
        if first["reason"] in _COUNT_REASONS:
            message += f" `{first['reason']}` 를 명시하면 그만큼의 선택으로 받고, 전부가 필요하면 값을 올리세요."
    # 안내문은 warning 이 먼저다. message 는 도구에 따라 본문 전문이다 — self:read 는 파일 내용을 싣는데
    # 그것을 '원천 안내'로 붙이면 사유 대신 자료 앞머리가 나간다(ep4213: 3.5MB JSON, 1MB 상한 안내가 가려졌다).
    note = None
    if isinstance(raw, dict):
        for key in ("warning", "message"):
            candidate = raw.get(key)
            if (isinstance(candidate, str) and candidate.strip() and len(candidate) <= 400
                    and not candidate.lstrip().startswith(("{", "["))):
                note = candidate.strip()
                break
    if note:
        message += f" 원천 안내: {note[:200]}"
    elif cut and not cut[0].get("reason"):
        message += " 원천이 절단 사유를 밝히지 않았습니다. 범위 인자(offset·limit 등)가 있으면 나눠 읽으세요 — 인자는 describe 로 확인합니다."
    return message

# 판본 1 도구의 평문 실패 규약(`return f"Error: …"`)은 legacy-envelope 프로토콜의 성질이다 — 도구별
# 선언으로 전개하면 선언을 잊은 도구의 파일 부재·권한 실패가 ADAPTER_SHAPE(봉투 파손)로 오분류된다
# (74회차 B74-5, 56회차 B56-3 과 같은 속). 선언된 text_error_prefixes 는 이 위에 더해진다.
_LEGACY_TEXT_ERROR_PREFIXES = ("Error:",)


def decode_envelope(raw, adapter, input_values=None):
    from ibl_honesty import completion_evidence, truncation_evidence, markers_of
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            prefix = adapter.get("text_success_prefix")
            error_prefixes = tuple(adapter.get("text_error_prefixes", [])) + (
                _LEGACY_TEXT_ERROR_PREFIXES if adapter.get("protocol") == "legacy-envelope" else ())
            from common.currency import is_plain_failure, plain_body
            if prefix and plain_body(raw).startswith(prefix):
                raw = {"success": True, "message": raw}
            elif error_prefixes and is_plain_failure(raw, error_prefixes):
                raise Fault("TOOL", raw) from exc
            else:
                raise Fault("ADAPTER_SHAPE", f"선언된 JSON 실행 봉투가 아닙니다: {raw[:1000]}") from exc
    if not isinstance(raw, dict):
        raise Fault("ADAPTER_SHAPE", "선언된 Record 실행 봉투가 아닙니다.")
    # Only this explicitly declared legacy envelope has error/status meaning.
    if raw.get("success") is False or raw.get("error"):
        kind = "permission" if raw.get("blocked") or raw.get("denied") or raw.get("permission_denied") or raw.get("error_type") == "permission" else "runtime"
        if raw.get("error_type") in {"capability", "result_unknown"}:
            kind = "protocol"
        # 원천의 요청 한도(429)는 '잠시 뒤 같은 원천'과 '원천을 바꿔라'를 가를 값이다 — 일반 TOOL 과
        # 같은 코드면 프로그램이 문자열로만 구별했다(상상훈련 77회차 F77-2). 생산자는 공통 봉투
        # common.api_client.rate_limited_failure 로 error_type·retry_after 를 싣는다.
        code = {"rate_limited": "RATE_LIMITED", "not_found": "NOT_FOUND"}.get(raw.get("error_type"), "TOOL")
        raise Fault(code, str(raw.get("error") or raw.get("message") or "도구 실행 실패"), kind=kind,
                    details={key: raw[key] for key in (
                        "error_type", "errno", "path", "base_path", "hint", "stage",
                        "usage", "supported_channels", "available_actions", "error_code", "recovery",
                        "input_contract", "failure_origin", "execution_ref", "def", "retry_after",
                        "http_status", "url", "resolved_url", "reason", "stages",
                        "expected_rows", "returned_rows", "missing_indices", "duplicate_indices",
                        "invalid_indices", "model_output_ref", "model_output_preview", "phase",
                        "missing_criteria", "decision", "checks", "changed_files",
                    ) if key in raw} | ({"inner_diagnostics": inner} if (inner := inner_diagnostics(raw)) else {}))
    if adapter.get("protocol") == "document-value/1":
        from ibl_document_value import document_value
        raw = {**raw, "value": document_value(raw)}
        if (raw.get("metadata") or {}).get("truncated"):
            raw["truncated"] = True
    fields = adapter.get("value_fields")
    value = ({k: pointer(raw, p) for k, p in fields.items()} if fields is not None
             else pointer(raw, adapter.get("value_path", "")))
    # Only declared envelope slots carry source status. A List is user rows,
    # never a list of envelopes; business error/truncated fields stay data.
    sources = []
    for key in adapter.get("input_envelopes", []):
        source = (input_values or {}).get(key)
        if isinstance(source, str):
            try:
                source = json.loads(source)
            except ValueError:
                continue
        if isinstance(source, dict):
            sources.append(source)
    boundaries = [raw, *sources]
    incomplete = completion_evidence(boundaries if sources else raw)
    # 도구가 봉투 최상위에서 스스로 "원천 불완전"(source_complete:false)을 말하면 그 말이 경계 증거다.
    # 74회차 후속: 접근 실패가 있던 스캔의 요약·76회차 시세 이력 실패가 이 표지를 싣고도 완전한 성공으로
    # 통과했다. 최상위 봉투만 읽는다 — 사용자 값 속 같은 이름의 필드는 데이터로 남는다.
    incomplete.extend({"at": "result" if boundary is raw else "input", "source_complete": False,
                       **({"errors": len(boundary["errors"])} if isinstance(boundary.get("errors"), list) else {})}
                      for boundary in boundaries if boundary.get("source_complete") is False)
    incomplete.extend({"at": "input", "error": source.get("error") or source.get("message")}
                      for source in sources if source.get("success") is False or source.get("error"))
    truncation = truncation_evidence(boundaries if sources else raw)
    markers = markers_of(raw)
    if incomplete or any(t.get("scope") != "selection" for t in truncation.get("truncations", [])) or any(b.get("rows_dropped") for b in boundaries):
        raise Fault("PARTIAL_SOURCE", _partial_message(raw, truncation), kind="partial", partial=value,
                    details={"completion": incomplete, "truncation": truncation, "markers": markers})
    from ibl_v2_ir import pack, unpack
    value = unpack(pack(value))
    evidence = {"markers": markers, "attachments": {k: raw[k] for k in adapter.get("attachments", []) if k in raw}}
    # Execution metadata declared by the adapter/runner, never business value fields.
    if isinstance(raw.get('operation_outcomes'), list):
        evidence['operation_outcomes'] = raw['operation_outcomes']
    if isinstance(raw.get('warning'), str) and raw['warning']:
        evidence['warning'] = raw['warning']
    return value, evidence


def observed_result(key, contract, params, result_type):
    """fixture·실사용 실측 반환 열(data/ibl_return_shapes.json)을 결과 타입에 *관측 필드*로 붙인다.

    선언이 아니라 흔적이다: Record 는 열린 채 두고, 관측 밖 이름을 읽으면 컴파일 *경고*(UNOBSERVED_FIELD)만 낸다.
    옛 검사기(ibl_typecheck)가 판본 1 에 하던 '관측 열 밖 참조' 경고를 판본 2 컴파일러가 이어받는 자리다.
    해소 규칙(node:action · #op · @param=값 · columns_from · fixture op)은 ibl_typecheck.catalog_entry 한 벌.
    상한에 잘린 관측(`more`)·미상은 기권한다. 외부 도구 봉투(legacy-envelope)에만 붙인다 — 표 변환자의
    열은 입력이 정한다. 관측은 계약 지문에 들어가지 않으므로 스윕 갱신이 재개 지문을 바꾸지 않는다."""
    if (contract.get("adapter") or {}).get("protocol") != "legacy-envelope" or ":" not in key:
        return result_type
    node, action = key.split(":", 1)
    try:
        from ibl_typecheck import catalog_entry
        entry = catalog_entry(node, action, dict(params), kinds=("items", "table", "scalar"))
    except Exception:
        return result_type
    if not entry or not entry.get("keys"):
        return result_type
    from ibl_v2_types import Type, UNKNOWN
    record = Type("Record", tuple((k, UNKNOWN) for k in entry["keys"]), open=True, observed=True)
    if entry.get("kind") == "scalar":
        # ⟨키⟩ = 봉투 최상위 필드 — `$r.키` 로 읽는 자리
        return record if result_type.kind == "Record" and not result_type.fields else result_type
    # ⟨열⟩ = 통화의 행 필드 — 봉투 Record 의 items 원소, 또는 List 원소. 선언이 행 모양을 이미 말하면(필드 있는 Record) 손대지 않는다.
    def blank_row(t):
        return t is None or t.kind == "Unknown" or (t.kind == "Record" and not t.fields)

    if result_type.kind == "Record" and not result_type.fields:
        return Type("Record", (("items", Type("List", item=record)),), open=True)
    if result_type.kind == "Record":
        fields = dict(result_type.fields)
        items = fields.get("items")
        if items is not None and items.kind == "List" and blank_row(items.item):
            fields["items"] = Type("List", item=record, positions=items.positions)
            return Type("Record", tuple(fields.items()), open=result_type.open)
        return result_type
    if result_type.kind == "List" and blank_row(result_type.item):
        return Type("List", item=record)
    return result_type


def load_registry(project_path=".", agent_id=None):
    from ibl_registry import load_nodes_installed
    from ibl_engine import execute_ibl
    from thread_context import get_allowed_nodes
    from ibl_access import check_node_access
    catalog = copy.deepcopy(load_nodes_installed())
    from tool_loader import build_tool_package_map, package_path
    package_map = build_tool_package_map()
    package_roots = {name: package_path(name) for name in set(package_map.values())}
    schemas = {}
    for root in package_roots.values():
        schema = json.loads((root / "tool.json").read_text())
        for tool in schema.get("tools", [schema]):
            schemas[tool.get("name")] = (tool.get("input_schema") or {}).get("properties", {})
    allowed = get_allowed_nodes()
    result, file_hashes = {}, {}
    from ibl_v2_contracts import handler_contract, declared_contract
    from ibl_run_journal import model_reuse_identity
    from ibl_v2_compat import plain_arguments
    for node, config in catalog.get("nodes", {}).items():
        for action, action_config in config.get("actions", {}).items():
            contract = declared_contract(action_config) or handler_contract(node, action, action_config, schemas.get(action_config.get("tool")))
            if not contract or (allowed is not None and not check_node_access(node, allowed)):
                continue
            contract = copy.deepcopy(validate_contract(contract))
            contract["analysis"] = {"ai_call": action_config.get("ai_call") is True,
                                    "ai_inspect_param": action_config.get("ai_inspect_param"),
                                    "schema_input_fields_param": action_config.get("schema_input_fields_param"),
                                    "schema_param": action_config.get("schema_param"),
                                    "flow": action_config.get("flow", {})}
            adapter = contract["adapter"]
            key = f"{node}:{action}"
            # Capture contract and implementation identities now. A changed
            # catalog/package is refused, never silently rebound mid-program.
            implementation = action_config.get("tool", "")
            package_paths = []
            if implementation:
                package = package_map.get(implementation)
                if package:
                    package_paths = sorted(p for p in package_roots[package].rglob("*.py") if "__pycache__" not in p.parts)
            for p in package_paths:
                if str(p) not in file_hashes:
                    file_hashes[str(p)] = digest(p.read_text())
            files = {str(p): file_hashes[str(p)] for p in package_paths}
            contract["implementation_fingerprint"] = digest(files)
            def run(runtime, args, *, node=node, action=action, c=contract,
                    ac=action_config, files=files, allowed=allowed):
                if allowed is not None and not check_node_access(node, allowed):
                    raise Fault("NODE_ACCESS", f"허용되지 않은 노드: {node}", kind="permission")
                current = load_nodes_installed().get("nodes", {}).get(node, {}).get("actions", {}).get(action)
                if current != ac or any(not Path(p).is_file() or digest(Path(p).read_text()) != h for p, h in files.items()):
                    raise Fault("DEFINITION_CHANGED", "컴파일 이후 어휘 구현이 바뀌었습니다. 새 계획으로 검사하세요.", kind="protocol")
                protocol = c["adapter"]["protocol"]
                if protocol == "core-table/2":
                    from member_profile import gate
                    if gate(node, action, ac):
                        raise Fault("MEMBER_ACCESS", "회원의 어휘 권한이 없습니다.", kind="permission")
                    return table_operation(c["adapter"]["operation"], runtime, args)
                if protocol == "ibl-script/2":
                    from ibl_file_script import is_file_call, invoke as invoke_file
                    if is_file_call(args):
                        return invoke_file(runtime, args, ac, node, action)
                    from ibl_script_session import registration, invoke
                    session_registration = registration(args)
                    if session_registration:
                        return invoke(runtime, args, session_registration, project_path, agent_id, ac, node, action)
                params = {**plain_arguments(args), **c["adapter"].get("fixed_params", {})}
                if protocol == "ibl-script/2":
                    params.setdefault("op", "run" if params.get("id") or params.get('path') else "list")
                    params["_ibl_edition"] = 2
                pipe_key = c["adapter"].get("legacy_pipe_input")
                if pipe_key and pipe_key in params:
                    previous = params[pipe_key]
                    params["_prev_result"] = {"items": previous} if isinstance(previous, list) else previous
                raw = execute_ibl({"_node": node, "action": action, "params": params}, project_path, agent_id=agent_id)
                boundary = c["adapter"]
                if protocol == "ibl-script/2" and params["op"] != "run":
                    boundary = {**boundary, "value_path": ""}
                value, evidence = decode_envelope(raw, boundary, params)
                return Adapted(value, evidence)
            def authorize(node=node, action=action, ac=action_config):
                from member_profile import visible
                current_allowed = get_allowed_nodes()
                if (current_allowed is not None and not check_node_access(node, current_allowed)) or not visible(node, action, ac):
                    raise Fault("RECEIPT_ACCESS", "현재 권한으로 이 호출의 영수증을 사용할 수 없습니다.", kind="permission")
            from ibl_dependencies import script_snapshot
            def reusable(args, ac=action_config):
                # 조이는 건 자동, 푸는 건 명시(ibl_ops 규칙 그대로): 부작용 없음 + 내부 모델 호출 없음 + 스크립트 아님.
                if ac.get("ai_call") is True or (ac.get("callable_contract") or {}).get("adapter", {}).get("protocol") == "ibl-script/2":
                    return False
                from ibl_ops import op_side_effect, resolve_op
                return not op_side_effect(ac, resolve_op(ac, args if isinstance(args, dict) else {}))
            dependency = script_snapshot if adapter['protocol'] == 'ibl-script/2' else None
            def resource_identity(realm, value, base=project_path):
                from runtime_utils import file_resource_identity
                # Offline definition checks have no turn directory. Keep a symbolic
                # identity; actual invocation always resolves an authorized scope.
                if realm == 'file' and (value == '~turn' or value.startswith(('~turn/', '~turn\\'))):
                    from script_workspace import current_scope
                    if current_scope() is None:
                        import posixpath
                        return posixpath.normpath(value.replace('\\', '/'))
                return file_resource_identity(value, base) if realm == 'file' else value
            from ibl_script_session import is_stateful
            from ibl_file_script import invocation_identity
            result[key] = Adapter(contract, run, authorize,
                                  dependency,
                                  None if contract["effects"] != ["unknown"] else reusable,
                                  is_stateful if adapter['protocol'] == 'ibl-script/2' else None,
                                  resource_identity,
                                  (lambda c=contract: model_reuse_identity(c['model_reuse']))
                                  if contract.get('model_reuse') else None,
                                  invocation_identity if adapter['protocol'] == 'ibl-script/2' else None)
    from ibl_v2_compat import function_adapters
    result.update(function_adapters(project_path, agent_id))
    return result
