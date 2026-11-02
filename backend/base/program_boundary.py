"""Program ownership and the small, explicit governance boundary.

Ordinary implementations are discovered from the existing source layout, not
registered in an allow list. A program's right to change is distinct from its
activation mechanism. Shared modules use stable call boundaries and explicit state contracts.
"""
from pathlib import PurePosixPath


# These are authority/validation/lifetime enforcement, not a list of features.
# Keep the reason alongside the boundary so additions remain reviewable.
CORE_MODULES = {
    'boot_paths': 'bootstrap', 'api': 'composition root', 'runtime_utils': 'code and data ownership',
    'principal': 'caller authority', 'approval_tokens': 'approval authority',
    'action_requires': 'operation authority', 'thread_context': 'caller binding',
    'execution_turn': 'execution authority', 'tool_context': 'path authority',
    'tool_loader': 'implementation loading', 'ibl_routing': 'call authority',
    'ibl_access': 'call authority', 'ibl_principal': 'call authority',
    'agent_pipeline': 'execution and grant issuance',
    'final_evaluator': 'completion criteria', 'supervisor_handoff': 'goal ownership',
    'consciousness': 'goal ownership', 'conscious_supervisor': 'goal ownership',
    'supervision_bus': 'supervision authority', 'supervision_hook': 'supervision authority',
    'supervision_watch': 'supervision authority', 'supervision_delivery': 'approved publication',
    'red_grant': 'repair authority', 'red_apply': 'publication authority',
    'red_watchdog': 'repair recovery', 'restart_red': 'publication authority',
    'repair_policy': 'repair acceptance', 'repair_readiness': 'repair acceptance',
    'repair_check_runner': 'test evidence', 'repair_test_results': 'test evidence',
    'repair_process': 'candidate isolation', 'coding_process': 'candidate isolation',
    'script_process': 'execution isolation', 'file_script': 'script authority',
    'script_workspace': 'execution isolation', 'shell_shadow_gate': 'execution isolation',
    'task_repair': 'repair scope', 'repair_continuation': 'repair lifetime',
    'component_continuation': 'repair lifetime', 'repair_root': 'repair lifetime',
    'task_cancellation': 'cancellation authority', 'task_tree_budget': 'execution budget',
    'control_base': 'control activation', 'restart_protocol': 'activation protocol',
    'restart_process': 'process ownership', 'restart_child': 'process ownership',
    'restart_controller': 'process ownership', 'restart_candidates': 'activation authority',
    'restart_helper': 'recovery authority', 'generation_store': 'code activation',
    'component_registry': 'component publication', 'component_runtime': 'component isolation',
    'program_boundary': 'program ownership', 'program_dependencies': 'validation scope',
    'program_modules': 'module activation', 'program_publication': 'module publication',
    'program_runtime': 'program activation', 'program_versions': 'program publication',
    'python_environment_lock': 'execution identity', 'execution_commit': 'publication evidence',
    'completion_contract': 'completion authority', 'completion_lease': 'completion authority',
    'install_approvals': 'installation authority', 'body_trust': 'body authority',
    'capability_change_checks': 'change validation', 'capability_changes': 'change planning',
    'function_store': 'definition publication', 'function_library': 'definition validation',
    'function_consumers': 'consumer validation', 'script_mutation': 'script publication',
    'vocabulary_policy': 'vocabulary authority', 'vocabulary_state': 'vocabulary publication',
    'value_semantics': 'language values', 'ibl_registry': 'vocabulary loading',
    'ibl_v2_parser': 'language grammar', 'ibl_v2_runtime': 'language execution',
    'ibl_v2_compile': 'language validation', 'ibl_edition': 'language edition',
    'vocabulary_import': 'vocabulary publication',
    'control_launcher': 'control activation', 'update_maintenance': 'process ownership',
    'member_profile': 'member authority', 'member_bridge': 'member authority',
    'member_files': 'member path authority', 'member_runtime': 'member isolation',
    'member_device_auth': 'device authority', 'member_enrollment': 'member identity',
    'portal_auth': 'portal authority', 'auth_manager': 'authentication authority',
}
ESSENTIALS_CORE = frozenset({
    'handler', 'red_zone_family', 'essentials_file_io', 'essentials_workspace',
    'essentials_component_repair', 'repair_tool_scope', 'repair_staging',
    'program_host_apply', 'repair_candidate', 'repair_gates', 'repair_outcomes', 'repair_surfaces', 'program_apply',
    'vocab_write_gate', 'body_ops', 'script_ops', 'script_runtime', 'script_session', 'program_derived',
})
CORE_PREFIXES = {
    'data/common_prompts/': 'agent instructions',
    'data/restart_control/': 'activation records',
    'data/system_ai_state/': 'task authority and receipts',
    'data/ibl_nodes_src/self.yaml': 'standard functional vocabulary',
    'data/ibl_nodes_src/others.yaml': 'standard functional vocabulary',
    'data/ibl_nodes_src/table.yaml': 'standard functional vocabulary',
    'data/ibl_nodes_src/meta.yaml': 'language metadata',
    'data/vocabulary_policy.yaml': 'vocabulary authority',
    'docs/generated_templates/': 'build templates',
    '.git/': 'source publication', '.github/': 'validation configuration',
}


def canonical(relative):
    if not isinstance(relative, str) or not relative or '\\' in relative:
        return None
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != relative:
        return None
    return path


def protected_reason(relative):
    path = canonical(relative)
    if path is None:
        return 'noncanonical path'
    if path.name.startswith('.env'):
        return 'credentials'
    if path.name in {'AGENTS.md', 'CLAUDE.md', 'conftest.py', 'pytest.ini',
                     'runtime_components.json', '.env', 'registry.yaml'}:
        return 'instructions, authority or owner-managed contract'
    for prefix, reason in CORE_PREFIXES.items():
        if relative == prefix.rstrip('/') or relative.startswith(prefix if prefix.endswith('/') else prefix + '/'):
            return reason
    if path.name.startswith('test_') or 'tests' in path.parts:
        return 'existing acceptance contract'
    if relative.startswith('backend/') and path.stem in CORE_MODULES:
        return CORE_MODULES[path.stem]
    if relative.startswith('data/packages/installed/tools/system_essentials/') and path.stem in ESSENTIALS_CORE:
        return 'file, execution or publication authority'
    if relative.startswith('scripts/') and (path.stem.startswith(('check_', 'build_', 'audit_', 'iblbuild_'))
                                           or path.stem in {'select_tests', 'red_safety_selftest'}):
        return 'build and acceptance infrastructure'
    return None


def describe(relative):
    """Return a discovered owner and the existing activation contract, or None."""
    path = canonical(relative)
    if path is None:
        return None
    reason = protected_reason(relative)
    if reason:
        return {'kind': 'core', 'owner': 'protected-core', 'reason': reason,
                'mutable': False, 'activation': 'external-development'}
    parts = path.parts
    if relative.startswith('data/scripts/'):
        return {'kind': 'script', 'owner': 'script:' + relative[13:],
                'mutable': True, 'activation': 'script-owner'}
    if relative.startswith('data/ibl_nodes_src/'):
        return {'kind': 'vocabulary', 'owner': 'vocabulary:' + path.stem,
                'mutable': True, 'activation': 'vocabulary-owner'}
    if len(parts) > 5 and parts[:4] == ('data', 'packages', 'installed', 'tools'):
        return {'kind': 'package', 'owner': 'package:' + parts[4],
                'root': '/'.join(parts[:5]), 'mutable': True, 'activation': 'package'}
    if parts[0] == 'backend':
        return {'kind': 'module', 'owner': 'module:' + path.stem,
                'mutable': True, 'activation': 'module-publication'}
    if parts[0] == 'frontend':
        return {'kind': 'surface', 'owner': 'surface:' + '/'.join(parts[1:3]),
                'mutable': True, 'activation': 'surface-owner'}
    if parts[0] == 'scripts':
        return {'kind': 'program', 'owner': 'program:' + relative,
                'mutable': True, 'activation': 'next-invocation'}
    return None


def eligible(relative):
    return bool((describe(relative) or {}).get('mutable'))


def plan(paths):
    owners, protected, unmanaged = {}, {}, []
    for path in sorted(set(paths)):
        item = describe(path)
        if not item:
            unmanaged.append(path)
        elif not item['mutable']:
            protected[path] = item['reason']
        else:
            owners.setdefault(item['owner'], {**item, 'files': []})['files'].append(path)
    return {'programs': list(owners.values()), 'protected': protected, 'unmanaged': unmanaged}


def managed(kind, target):
    """Definitions use their existing publication owners, never the code loader."""
    owners = {'idiom': 'function-store', 'script': 'script-registry', 'action': 'vocabulary'}
    if kind not in owners:
        raise ValueError('Unknown managed program kind')
    return {'kind': kind, 'owner': owners[kind], 'target': target,
            'activation': 'vocabulary-and-implementation' if kind == 'action' else 'owner-revision',
            'restart_required': None if kind == 'action' else False,
            'in_flight': 'bound-compiled-plan' if kind == 'idiom' else 'owner-execution-contract',
            'verification': 'owner-and-consumer-contracts'}
