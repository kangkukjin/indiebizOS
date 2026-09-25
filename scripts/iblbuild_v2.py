"""Builder seam for the edition 2 contract validator (runtime owns semantics)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401
from ibl_v2_adapters import validate_contract


def validate_v2_contracts(data):
    issues = []
    for name, node in (data.get("nodes") or {}).items():
        if not isinstance(node, dict):
            continue
        for action, entry in (node.get("actions") or {}).items():
            if not isinstance(entry, dict):
                continue
            # Multi-source consumers already declare their input topology. An
            # opaque JSON fallback cannot carry that topology into current IBL.
            flow = entry.get('flow') or {}
            if (flow.get('accepts') in {'items', 'prose', 'prose|items', 'items|prose'}
                    and entry.get('func') != 'table_each'):
                contract = entry.get('callable_contract') or {}
                receiver = contract.get('pipe_input')
                if not receiver or receiver not in contract.get('params', {}):
                    issues.append(f'{name}:{action}: 단항 flow에 callable_contract.pipe_input과 입력 인자 선언이 필요합니다')
                adapter = contract.get('adapter', {})
                if (adapter.get('protocol') == 'legacy-envelope'
                        and receiver not in adapter.get('input_envelopes', [])):
                    issues.append(f'{name}:{action}: 단항 봉투 입력의 근거를 adapter.input_envelopes에 연결하세요')
            if flow.get('accepts') in {'pair', 'same-kind'}:
                qualified = f'{name}:{action}'
                contract = entry.get('callable_contract') or {}
                bundle = flow.get('input_bundle_param')
                if not bundle or contract.get('pipe_input') != bundle:
                    issues.append(f'{qualified}: 결합 flow의 input_bundle_param을 callable_contract.pipe_input으로 연결하세요')
                params = entry.get('params') or {}
                for key in [bundle, *(flow.get('input_params') or [])]:
                    if not key:
                        continue
                    declared = params.get(key)
                    kinds = declared if isinstance(declared, list) else [declared]
                    if 'array' not in kinds or (key != bundle and 'object' not in kinds):
                        issues.append(f'{qualified}: 결합 입력 {key}에 컨테이너 타입(array/object)을 선언하세요')
                    if key not in contract.get('params', {}):
                        issues.append(f'{qualified}: 결합 입력 {key}가 callable_contract.params에 없습니다')
            if isinstance(entry, dict) and "callable_contract" in entry:
                try:
                    validate_contract(entry["callable_contract"])
                except (ValueError, KeyError, TypeError) as exc:
                    issues.append(f"{name}:{action} callable_contract: {exc}")
    return issues


def check_v2_corpus(code, entry, issues, origin, session=None):
    from ibl_edition import source_edition
    try:
        if source_edition(code, entry.get("edition")) != 2:
            return False
        from ibl_v2_learning import check_source
        kwargs = {}
        if session is not None:
            if not session:
                try:
                    from ibl_v2_adapters import load_registry
                    from ibl_v2_store import definitions
                    session.update(registry=load_registry(), library=definitions())
                except Exception as exc:
                    session['error'] = exc
            if 'error' in session:
                raise session['error']
            kwargs = session
        why = check_source(code, bool(entry.get("alias")) or entry.get("category") == "phrase", **kwargs)
        if why:
            issues.append(f"{origin}: 판본 2 용례 검사 — {why}")
    except Exception as exc:
        issues.append(f"{origin}: 판본 2 검사 불가 — {exc}")
    return True
