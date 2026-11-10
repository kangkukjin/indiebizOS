"""Program ownership and the small, explicit governance boundary.

Ordinary implementations are discovered from the existing source layout, not
registered in an allow list. A program's right to change is distinct from its
activation mechanism. Shared modules use stable call boundaries and explicit state contracts.
"""
from pathlib import PurePosixPath


# These roots require staged code publication, not permission to alter core.
LIVE_CODE_ROOTS = ('backend', 'frontend', 'scripts')

# File-owned content uses normal file/ledger operations even in a repair turn.
# Program sources, managed stores and protected contracts are resolved first.
FILE_CONTENT_ROOTS = ('docs', 'data/guides', 'data/system_docs', 'outputs', 'data/outputs',
                      '공유창고')


def repair_requested(request_type, framing=None):
    """A repair route supplies a workspace; it never authorizes protected core.

    A model's false 'needs_repair' used to revoke an already requested repair
    merely because scripts needed no core edit. Actual deltas, not this hint,
    determine publication and completion receipts.
    """
    return request_type == 'REPAIR' or bool((framing or {}).get('needs_repair'))


def guidance():
    """Shared contract supplied to planning and execution; path decisions stay here."""
    return (
        '수리 경계 정본: backend/base/program_boundary.py의 describe/change. route와 completion이 실행·완료 경로다. '
        '대상이 불명확하면 [self:patch]{op:"status",path:"정본 상대 경로"}로 현재 소유권을 조회한다. '
        '자기 변경 금지는 요청 신원·권한, 격리, 적용 권한과 완료 계약·영수증, 기본 지침의 최소 경계다. '
        '보호 코어는 수리 그랜트가 있어도 내부에서 변경할 수 없다. '
        '코어라는 이름이나 backend 위치만으로 수리를 금지하지 않는다. '
        '수리 가능한 실행 기반은 검사 후 기존 외부 제어자의 세대 교체·복구로 반영한다. '
        '일반 프로그램(backend 모듈·frontend·scripts·도구 패키지·data/scripts·개인 사전)은 '
        '공통 소유권 판정에 따라 사본 수정→관련 검사→self:patch apply→활성 확인·각인으로 수리한다. '
        'needs_repair는 이 프로그램 사본 작업의 필요 여부이며 코어 변경 여부가 아니다. '
        'REPAIR로 시작한 사용자 요청은 needs_repair:false여도 이 경로를 유지한다. '
        '관용구 등 관리 정의만 개정하면 소유 API의 검증·판본 저장·새 호출로 완료한다. '
        'route=file인 문서·업무 원장은 정본 경로의 일반 파일·원장 도구로 편집하고 운영 조회로 확인한다. '
        '수리 턴이나 재개 중에도 이 파일들을 코드 사본으로 옮기거나 patch apply를 요구하지 않는다. '
        '파일 소유 프로젝트의 명령도 run_command cwd로 그 정본에서 실행한다. 긴 실행은 mode=session과 기존 task 관측·제어를 쓴다. '
        '코드와 함께 배치할 산출물은 명시적인 현재 사본 경로로 작성하고 artifact_paths로 적용한다. '
        '그랜트만으로 코드 적용·재기동·커밋을 요구하지 않으며 실제 후보 변경이 있을 때만 요구한다. '
        '빌더가 읽을 새 후보 파일의 Git 추적 정보는 수리 서비스가 준비한다. 사본 셸에서 git add를 수행하지 않는다. '
        '작업 목표·검사 기준은 유지하고 보호 코어 변경이 필요하면 그 경계와 미완료를 보고한다.'
    )


# A publication transaction never changes its own authority or evidence store.
# Other host implementation is repairable, but switches at a generation boundary.
# These two maps are the single policy: consumers must use the predicates below.
CORE_MODULES = {
    'principal': 'caller authority',
    'approval_tokens': 'approval authority',
    'action_requires': 'operation authority',
    'thread_context': 'caller binding',
    'execution_turn': 'execution authority',
    'tool_context': 'path authority',
    'ibl_access': 'call authority',
    'ibl_principal': 'call authority',
    'agent_pipeline': 'execution and grant issuance',
    'red_grant': 'repair authority',
    'red_apply': 'publication authority',
    'restart_red': 'publication authority',
    'repair_readiness': 'repair acceptance',
    'repair_process': 'candidate isolation',
    'repair_process_bridge': 'candidate isolation',
    'coding_process': 'candidate isolation',
    'script_process': 'execution isolation',
    'script_workspace': 'execution isolation',
    'shell_shadow_gate': 'execution isolation',
    'task_repair': 'repair scope',
    'task_cancellation': 'cancellation authority',
    'generation_store': 'code activation',
    'program_boundary': 'program ownership',
    'program_publication': 'module publication',
    'program_versions': 'program publication',
    'execution_commit': 'publication evidence',
    'completion_contract': 'completion authority',
    'completion_lease': 'completion authority',
    'install_approvals': 'installation authority',
    'body_trust': 'body authority',
    'script_mutation': 'script publication',
    'member_device_auth': 'device authority',
    'member_enrollment': 'member identity',
    'portal_auth': 'portal authority',
    'auth_manager': 'authentication authority',
}

RESTART_MODULES = {
    'boot_paths': 'bootstrap',
    'api': 'composition root',
    'runtime_utils': 'code and data ownership',
    'tool_loader': 'implementation loading',
    'ibl_routing': 'call authority',
    'cognitive_consciousness': 'repair routing',
    'consciousness_agent': 'goal framing',
    'prompt_builder': 'agent instructions',
    'prompt_composition': 'agent instructions',
    'reframe': 'goal revision',
    'framing_inheritance': 'goal and authority inheritance',
    'final_evaluator': 'completion criteria',
    'supervisor_handoff': 'goal ownership',
    'consciousness': 'goal ownership',
    'conscious_supervisor': 'goal ownership',
    'supervision_bus': 'supervision authority',
    'supervision_hook': 'supervision authority',
    'supervision_watch': 'supervision authority',
    'supervision_delivery': 'approved publication',
    'red_watchdog': 'repair recovery',
    'repair_policy': 'repair acceptance',
    'repair_check_runner': 'test evidence',
    'repair_test_results': 'test evidence',
    'file_script': 'script authority',
    'repair_continuation': 'repair lifetime',
    'component_continuation': 'repair lifetime',
    'repair_root': 'repair lifetime',
    'task_tree_budget': 'execution budget',
    'control_base': 'control activation',
    'restart_protocol': 'activation protocol',
    'restart_process': 'process ownership',
    'restart_child': 'process ownership',
    'restart_controller': 'process ownership',
    'restart_candidates': 'activation authority',
    'restart_helper': 'recovery authority',
    'component_registry': 'component publication',
    'component_runtime': 'component isolation',
    'program_dependencies': 'validation scope',
    'program_modules': 'module activation',
    'program_runtime': 'program activation',
    'python_environment_lock': 'execution identity',
    'capability_change_checks': 'change validation',
    'capability_changes': 'change planning',
    'function_store': 'definition publication',
    'function_library': 'definition validation',
    'function_consumers': 'consumer validation',
    'vocabulary_policy': 'vocabulary authority',
    'vocabulary_state': 'vocabulary publication',
    'value_semantics': 'language values',
    'ibl_registry': 'vocabulary loading',
    'ibl_v2_parser': 'language grammar',
    'ibl_v2_runtime': 'language execution',
    'ibl_v2_compile': 'language validation',
    'ibl_edition': 'language edition',
    'vocabulary_import': 'vocabulary publication',
    'control_launcher': 'control activation',
    'update_maintenance': 'process ownership',
    'member_profile': 'member authority',
    'member_bridge': 'member authority',
    'member_files': 'member path authority',
    'member_runtime': 'member isolation',
    'repair_resume': 'repair workspace continuity',
}

ESSENTIALS_CORE = frozenset({
    'handler', 'red_zone_family', 'repair_tool_scope', 'repair_staging',
    'repair_candidate', 'program_host_apply', 'program_apply', 'vocab_write_gate',
    'body_ops', 'script_ops',
})
RESTART_ESSENTIALS = frozenset({
    'essentials_workspace', 'essentials_component_repair', 'repair_gates',
    'repair_outcomes', 'repair_surfaces', 'script_runtime', 'script_session', 'program_derived',
})

# Workspace state is not candidate source. Reading and writing use the same
# list instead of maintaining a second private-path boundary in staging.
WORKSPACE_PRIVATE = {  # reason, owner diagnostic reads allowed
    '.git': ('source publication', False),
    '.worktrees': ('other candidate ownership', False),
    'data/system_ai_state': ('task authority and receipts', True),
    'data/restart_control': ('activation records', True),
    'data/_backups': ('recovery records', False),
    'data/spill': ('execution evidence', False),
    'data/script_runs': ('execution receipts', False),
    'data/backend_keeper_off': ('process control', False),
}
CORE_PREFIXES = {
    **{path + '/': policy[0] for path, policy in WORKSPACE_PRIVATE.items()},
    'data/common_prompts/': 'agent instructions',
    'data/ibl_nodes_src/self.yaml': 'standard functional vocabulary',
    'data/ibl_nodes_src/others.yaml': 'standard functional vocabulary',
    'data/ibl_nodes_src/table.yaml': 'standard functional vocabulary',
    'data/ibl_nodes_src/meta.yaml': 'language metadata',
    'data/vocabulary_policy.yaml': 'vocabulary authority',
    'docs/generated_templates/': 'build templates',
    '.github/': 'validation configuration',
}


def canonical(relative):
    if not isinstance(relative, str) or not relative or '\\' in relative:
        return None
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != relative:
        return None
    return path


PROTECTED_FILENAMES = frozenset({'AGENTS.md', 'CLAUDE.md', 'conftest.py', 'pytest.ini',
                                'runtime_components.json', '.env', 'registry.yaml'})


def protected_reason(relative):
    path = canonical(relative)
    if path is None:
        return 'noncanonical path'
    if path.name.startswith('.env'):
        return 'credentials'
    if path.name in PROTECTED_FILENAMES:
        return 'instructions, authority or owner-managed contract'
    for prefix, reason in CORE_PREFIXES.items():
        if relative == prefix.rstrip('/') or relative.startswith(prefix if prefix.endswith('/') else prefix + '/'):
            return reason
    if relative.startswith('backend/') and path.stem in CORE_MODULES:
        return CORE_MODULES[path.stem]
    if relative.startswith('data/packages/installed/tools/system_essentials/') and path.stem in ESSENTIALS_CORE:
        return 'file, execution or publication authority'
    if relative.startswith('scripts/') and (path.stem.startswith(('check_', 'build_', 'audit_', 'iblbuild_'))
                                           or path.stem in {'select_tests', 'red_safety_selftest'}):
        return 'build and acceptance infrastructure'
    return None


def readable_runtime_state(relative):
    """Owner repair may diagnose live control/receipt state without editing it."""
    return bool(canonical(relative)) and any(relative == p or relative.startswith(p + '/')
        for p, (_, readable) in WORKSPACE_PRIVATE.items() if readable)


def requires_restart(relative):
    """Repairable host implementation keeps its process lifetime; not a denial."""
    path = canonical(relative)
    if path is None:
        return False
    return ((relative.startswith('backend/') and path.stem in RESTART_MODULES)
            or (relative.startswith('data/packages/installed/tools/system_essentials/')
                and path.stem in RESTART_ESSENTIALS))


def host_bound(relative):
    """Immutable and restartable host code must not enter the hot import loader."""
    return bool(protected_reason(relative) or requires_restart(relative))


def generation_candidate(session):
    """Choose publication from actual files, including sessions made by older code."""
    return any(requires_restart(item.get('rel', path))
               for path, item in session.get('files', {}).items())


def _describe(relative):
    """Return a discovered owner and the existing activation contract, or None."""
    path = canonical(relative)
    if path is None or not path.parts:
        return None
    reason = protected_reason(relative)
    if reason:
        if relative in MANAGED_RESOURCES:
            return {'kind': 'managed', 'owner': MANAGED_RESOURCES[relative],
                    'reason': reason, 'mutable': False, 'activation': 'owner-revision'}
        return {'kind': 'core', 'owner': 'protected-core', 'reason': reason,
                'mutable': False, 'activation': 'external-development'}
    parts = path.parts
    if (parts[0] in LIVE_CODE_ROOTS or relative.startswith('data/packages/')) and (
            path.name.startswith('test_') or 'tests' in parts):
        return {'kind': 'test', 'owner': 'test:' + relative, 'mutable': True,
                'activation': 'acceptance-source'}
    if requires_restart(relative):
        return {'kind': 'host', 'owner': 'host:' + relative, 'mutable': True,
                'activation': 'generation-restart',
                'reason': 'process lifetime; repair through the existing restart controller'}
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
    if any(relative == root or relative.startswith(root + '/') for root in FILE_CONTENT_ROOTS):
        return {'kind': 'document', 'owner': 'file:' + relative,
                'mutable': True, 'activation': 'file-write'}
    return None


def _contract(item):
    """One routing/completion decision for queries, file tools and publication."""
    if item is None:
        return None
    if item['kind'] == 'document':
        route, completion = 'file', 'readback'
    elif item['mutable']:
        route, completion = 'workspace', 'publication-receipt'
    elif item['kind'] == 'managed':
        route, completion = 'owner', 'owner-receipt'
    else:
        route, completion = 'deny', 'external-development'
    return {**item, 'route': route, 'completion': completion}


def describe(relative):
    return _contract(_describe(relative))


def eligible(relative):
    return (describe(relative) or {}).get('route') == 'workspace'


def artifact_path(relative):
    """Explicit candidate outputs may be delivered with code, never as code."""
    return (bool(canonical(relative)) and relative.startswith('outputs/')
            and (describe(relative) or {}).get('route') == 'file')


def may_have_derived_content(relative):
    """Only the builder's exact output receipt can authorize these candidates."""
    return bool(canonical(relative)) and (relative.startswith(('data/', 'README')) or relative.endswith('.md'))


def direct_write_reason(relative):
    """Non-granted file writes keep the same governance and gate-package boundary."""
    return protected_reason(relative) or (
        'program workspace required' if relative.startswith(
            'data/packages/installed/tools/system_essentials/') else None)


def source_artifact(relative):
    """Non-live-code sources covered by existing repair staging adapters."""
    if relative.startswith('data/ibl_nodes_src/'):
        return relative.endswith(('.yaml', '.yml'))
    return relative.startswith('data/packages/installed/') and (
        relative.endswith(('.py', '.js', '.ts', '.tsx', '.jsx', '.css', '.html'))
        or PurePosixPath(relative).name in {'ibl_actions.yaml', 'tool.json', 'package.json'})


def path_status(raw, repo):
    """Read-only ownership query for self:patch status; never create a workspace."""
    from pathlib import Path
    from runtime_utils import expand_body_path
    try:
        path = Path(expand_body_path(raw))
        root = Path(repo).resolve()
        relative = path.resolve().relative_to(root).as_posix() if path.is_absolute() else raw
        if not canonical(relative) or not (root / relative).resolve().is_relative_to(root):
            raise ValueError('정본 내부의 정규 경로가 필요합니다')
        relative = (root / relative).resolve().relative_to(root).as_posix()
        item = describe(relative) or {'kind': 'unmanaged', 'mutable': False, 'activation': None,
                                     'route': 'unmanaged', 'completion': None}
        return {'success': True, 'items': [{'path': relative, **item,
                'decision': 'static-ownership', 'source': 'backend/base/program_boundary.py'}],
                'message': '정적 소유권 조회입니다. 새 검사·관리 원장·파생물의 실제 변경은 '
                           '기준 판본과 공식 소유자 영수증으로 change가 판정합니다.'}
    except (ValueError, TypeError, OSError) as exc:
        return {'success': False, 'error': str(exc)}


def plan(paths):
    owners, protected, unmanaged = {}, {}, []
    for path in sorted(set(paths)):
        item = describe(path)
        if not item:
            unmanaged.append(path)
        elif item['route'] == 'file':
            unmanaged.append(path)  # content is edited through its file owner
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


# The owner may publish this resource; ordinary file writes may never grant it.
MANAGED_RESOURCES = {'data/scripts/registry.yaml': 'script-registry'}


def change(relative, before, after, *, managed=None, derived=None):
    """One decision for an actual delta, shared by collection and publication.

    Tests follow their program workspace. Owner outputs require exact host receipts.
    """
    if not canonical(relative):
        return describe(relative)
    receipt = (managed or {}).get(relative) or {}
    owner = MANAGED_RESOURCES.get(relative)
    if owner and receipt.get('owner') == owner and receipt.get('fingerprint') == after:
        return _contract({'kind': 'managed', 'owner': owner, 'mutable': True,
                          'activation': 'owner-revision'})
    if relative in (derived or {}) and derived[relative] == after:
        return _contract({'kind': 'derived', 'owner': 'host-builder', 'mutable': True,
                          'activation': 'derived-publication'})
    return describe(relative)


def candidate_plan(session, current):
    """Project trusted baseline/owner receipts into the existing program plan."""
    baseline = session['baseline']
    changes = sorted(p for p in set(baseline) | set(current) if baseline.get(p) != current.get(p))
    result = {'programs': [], 'protected': {}, 'unmanaged': []}
    owners = {}
    for relative in changes:
        if relative in session.get('artifact_paths', []):
            continue
        item = change(relative, baseline.get(relative), current.get(relative),
                      managed=session.get('managed_files'), derived=session.get('derived_files'))
        if not item or item['route'] == 'file':
            result['unmanaged'].append(relative)
        elif not item['mutable']:
            result['protected'][relative] = item['reason']
        else:
            entry = owners.setdefault(item['owner'], {**item, 'files': []})
            entry['files'].append(relative)
    result['programs'] = list(owners.values())
    return result
