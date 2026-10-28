"""Explicit, no-execution recertification in the existing immutable catalog."""
import function_store as store
from function_library import definitions
from ibl_v2_ir import Fault


def revalidate(*, apply=False):
    """Certify eligible dependency closures; keep unsupported records unchanged.

    Discovery/check remain read-only. Publication rechecks under the catalog CAS
    lock; old revisions and pinned executions remain readable.
    """
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    from ibl_v2_semantic_store import certify
    from ibl_v2_ir import digest
    view = store.snapshot()
    with store.using(view):
        registry = load_registry()
        library = definitions(view)
        # An unchanged outer interface is invalid if a transitive primitive
        # contract changed. Rebuild the eligible closure from leaves each time.
        library.interfaces.clear()
        pending = {fid: row for fid, row in view['records'].items()
                   if row.get('state') == 'active' and not row.get('problem')}
        statuses, changes = {}, []
        while pending:
            progress = False
            for fid, row in list(pending.items()):
                try:
                    result = certify(row, library, registry)
                except (Fault, ValueError) as exc:
                    statuses[row['name']] = {'status': 'invalid', 'reason': str(exc)}
                    del pending[fid]
                    progress = True
                    continue
                if 'semantic_interface' not in result:
                    statuses[row['name']] = {'status': 'source-required', 'reason': result['semantic_limit']}
                    continue
                try:
                    checked = compile_program(row['source'], registry, definitions=library)
                    if checked.issues:
                        raise ValueError(checked.issues[0]['message'])
                except (Fault, ValueError) as exc:
                    statuses[row['name']] = {'status': 'invalid', 'reason': str(exc)}
                    del pending[fid]
                    progress = True
                    continue
                record = store.revision(fid, row['revision'])
                record.pop('revision')
                record.pop('semantic_interface', None)
                record.pop('semantic_limit', None)
                certified = {**record, **result}
                revision = store.digest(certified)
                library.interfaces[row['name']] = result['semantic_interface']
                library.references[row['name']] = store.reference({**certified, 'revision': revision})
                status = 'current' if revision == row['revision'] else 'ready'
                statuses[row['name']] = {'status': status, 'previous': store.reference(row),
                                         'interface_hash': digest(result['semantic_interface'])}
                if status == 'ready':
                    changes.append({'record': record, 'expected_revision': row['revision']})
                del pending[fid]
                progress = True
            if not progress:
                break
    published = None
    if apply and changes:
        # Publication validates every candidate again in the exact write view.
        published = store.publish(changes, expected_generation=view['generation'])
        for ref in published['functions']:
            statuses[ref['name']].update(status='certified', function_ref=ref)
    return {'executed': False, 'applied': bool(published), 'generation': view['generation'],
            'publication': published, 'functions': statuses}
