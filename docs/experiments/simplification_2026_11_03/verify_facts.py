"""Design evidence only: read repository/history; mutate synthetic files in /tmp.

Run from repository root with .venv/bin/python3 -B <this file>.
No backend bootstrap, service, model, or real project data is loaded.
"""
import ast
from collections import Counter
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True)


def definitions(relative):
    path = ROOT / relative
    namespace = {'__name__': 'design_evidence', '__file__': str(path)}
    exec(compile(path.read_text(), str(path), 'exec'), namespace)
    return namespace


def without_layers(source):
    tree = ast.parse(source)
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'LAYERS'
                for target in node.targets))]
    return ast.dump(tree, include_attributes=False)


def main():
    guard = definitions('scripts/check_backend_layers.py')
    paths = guard['module_paths'](str(ROOT / 'backend'))
    folder_layers = {v: k for k, v in guard['LAYER_DIR_OF'].items()}
    physical = {name: folder_layers[Path(path).parent.as_posix()]
                for name, path in paths.items()
                if Path(path).parent.as_posix() in folder_layers}
    mismatch = {name: [layer, guard['layer_of'](name)]
                for name, layer in physical.items()
                if layer != guard['layer_of'](name)}
    path = 'scripts/check_backend_layers.py'
    history = Counter()
    for commit in git('log', '--since=2026-08-03', '--until=2026-11-04',
                      '--format=%H', '--', path).splitlines():
        before = (git('show', f'{commit}^:{path}')
                  if git('ls-tree', f'{commit}^', '--', path).strip() else '')
        after = git('show', f'{commit}:{path}')
        history['LAYERS_only_AST' if without_layers(before) == without_layers(after)
                else 'other_logic'] += 1
    result = {'head': git('rev-parse', 'HEAD').strip(),
              'layer_modules': len(physical), 'layer_mismatches': mismatch,
              'layer_history': dict(history)}
    registry = definitions('backend/datastore/node_registry.py')
    lifecycle = definitions('backend/cognition/agent_lifecycle.py')
    registry['_get_tool_node_map'] = lambda: {}
    with tempfile.TemporaryDirectory(prefix='simplification-facts-') as tmp:
        base = Path(tmp)
        project = base / 'projects' / 'P'
        project.mkdir(parents=True)
        registry['_get_base_path'] = lambda: base
        lifecycle['_project_path'] = lambda _: project
        source = {'agents': [{'id': 'a', 'name': 'first',
                              'allowed_nodes': ['sense']}], 'common': {}}
        lifecycle['_save'](project, source)
        first = registry['_load_agent_nodes']()[0]
        lifecycle['update_agent']('P', 'a', name='second')
        stale = registry['_load_agent_nodes']()[0]
        registry['invalidate_agent_cache']()
        refreshed = registry['_load_agent_nodes']()[0]
        result['agent_cache'] = {'before': first['agent_name'],
                                 'after_update': stale['agent_name'],
                                 'after_invalidate': refreshed['agent_name'],
                                 'capabilities': refreshed['capabilities']}
        (project / 'agent_second_role.txt').write_text('original role')
        (project / 'agent_taken_role.txt').write_text('existing destination')
        lifecycle['update_agent']('P', 'a', name='taken')
        result['rename_collision'] = {
            'source_exists': (project / 'agent_second_role.txt').exists(),
            'destination': (project / 'agent_taken_role.txt').read_text(),
            'saved_name': lifecycle['_load'](project)['agents'][0]['name']}
        fake_backend = base / 'backend'
        for folder in ('base', 'surface'):
            (fake_backend / folder).mkdir(parents=True)
            (fake_backend / folder / 'duplicate.py').write_text('')
        result['duplicate_collection'] = {
            'input_files': 2,
            'returned_entries': len(guard['module_paths'](str(fake_backend)))}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
