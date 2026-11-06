"""Declarative managed language servers and project settings; never import project code."""
import ast
import json
import os
import shutil
from pathlib import Path

import yaml
from lsp_positions import digest
from lsp_transport import LspError

TOOLCHAIN = Path(__file__).resolve().parents[2] / 'data/code_analysis'


def registry():
    return yaml.safe_load((TOOLCHAIN / 'servers.yaml').read_text())


def inventory():
    result = []
    for name, spec in registry()['servers'].items():
        manifest = TOOLCHAIN / 'node_modules' / spec.get('package', '') / 'package.json'
        installed = json.loads(manifest.read_text()) if manifest.is_file() else {}
        result.append({'server': name, 'languages': spec['extensions'], 'version': installed.get('version') or spec.get('version'),
                       'installed': (not spec.get('package') or bool(installed)) and bool(shutil.which(spec['command'][0])),
                       'command': spec['command'], 'driver': spec.get('driver', 'standard')})
    return result


def select(path=None, server=None):
    specs = registry()['servers']
    if server:
        if server not in specs:
            raise LspError('SERVER_UNREGISTERED', '등록되지 않은 언어 서버: ' + server)
        return server, specs[server]
    for name, spec in specs.items():
        if Path(path or '').suffix in spec['extensions']:
            return name, spec
    raise LspError('LANGUAGE_UNSUPPORTED', '파일에 대응하는 언어 서버가 없습니다. capabilities를 확인하세요')


def environment(root, spec):
    root = Path(root)
    settings, initialization, sources = {}, {}, []
    if spec.get('driver') == 'pyright':
        analysis = {'diagnosticMode': 'openFilesOnly', 'autoSearchPaths': True}
        # Derive the actual flat layer imports from the project's declaration, without executing it.
        boot = root / 'backend/boot_paths.py'
        if boot.is_file():
            tree = ast.parse(boot.read_text())
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'LAYER_DIRS' for t in node.targets):
                    layers = ast.literal_eval(node.value)
                    if isinstance(layers, list) and all(isinstance(v, str) and '/' not in v for v in layers):
                        analysis['extraPaths'] = [str(root / 'backend')] + [str(root / 'backend' / v) for v in layers]
                        sources.append('backend/boot_paths.py:LAYER_DIRS')
        python = next((p for p in (root / '.venv/bin/python', root / '.venv/Scripts/python.exe') if p.is_file()), None)
        settings['python'] = {'analysis': analysis, **({'pythonPath': str(python)} if python else {})}
        settings['pyright'] = {'disableOrganizeImports': False}
    elif spec.get('driver') == 'typescript':
        # The project config and local compiler remain authoritative. Explicitly declare the selected compiler.
        compiler = root / 'node_modules/typescript/lib/tsserver.js'
        if not compiler.is_file():
            compiler = TOOLCHAIN / 'node_modules/typescript/lib/tsserver.js'
        initialization = {'tsserver': {'path': str(compiler)}, 'preferences': {'includeCompletionsForModuleExports': True}}
        sources.append(str(compiler))
    config_files = [root / p for p in spec.get('markers', [])] + [root / 'backend/boot_paths.py', TOOLCHAIN / 'servers.yaml', TOOLCHAIN / 'package-lock.json']
    config_files += list(root.glob('tsconfig*.json')) + [root / 'package-lock.json', root / '.venv/pyvenv.cfg', root / 'node_modules/typescript/package.json']
    evidence = {str(p): digest(p.read_bytes()) for p in config_files if p.is_file()}
    settings.update(spec.get('settings', {}))
    initialization.update(spec.get('initialization_options', {}))
    return settings, initialization, {'sources': sources, 'files': evidence, 'fingerprint': digest(json.dumps(evidence, sort_keys=True).encode())}


def launch(spec, runtime):
    command = [v.replace('{toolchain}', str(TOOLCHAIN)) for v in spec['command']]
    executable = shutil.which(command[0])
    if not executable or any('{toolchain}' in v for v in command):
        raise LspError('SERVER_UNAVAILABLE', '언어 서버 실행 환경이 없습니다. 코드 분석 설정에서 설치하세요')
    command[0] = executable
    if spec.get('package') and not (TOOLCHAIN / 'node_modules' / spec['package']).is_dir():
        raise LspError('SERVER_UNAVAILABLE', '관리된 언어 서버를 먼저 설치하세요')
    # No model credentials or user shell startup. Server caches belong to its runtime.
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'SystemRoot', 'WINDIR', 'LANG', 'LC_ALL', 'PATHEXT')}
    env.update(HOME=str(runtime), USERPROFILE=str(runtime), TMPDIR=str(runtime), TEMP=str(runtime), TMP=str(runtime),
               XDG_CACHE_HOME=str(runtime / 'cache'), PYTHONDONTWRITEBYTECODE='1')
    return command, env


def command_edit(session, command):
    """Known TypeScript read/effect contracts. Never execute an arbitrary server command."""
    if session.spec.get('driver') != 'typescript':
        raise LspError('COMMAND_UNSUPPORTED', '이 서버 명령의 효과 계약이 없습니다')
    name, args = command.get('command'), command.get('arguments', [])
    if name == '_typescript.applyWorkspaceEdit' and len(args) == 1:
        return args[0]

    def convert(changes):
        documents = []
        for change in changes:
            path = Path(change['fileName']).resolve()
            if not path.is_relative_to(session.root):
                raise PermissionError('서버 명령이 작업 공간 밖을 편집하려 합니다')
            uri = path.as_uri()
            if change.get('isNewFile'):
                documents.append({'kind': 'create', 'uri': uri})
            edits = []
            for edit in change.get('textChanges', []):
                edits.append({'range': {key: {'line': edit[key]['line'] - 1, 'character': edit[key]['offset'] - 1}
                                        for key in ('start', 'end')}, 'newText': edit['newText']})
            documents.append({'textDocument': {'uri': uri, 'version': None}, 'edits': edits})
        return {'documentChanges': documents}

    if name == '_typescript.applyCodeAction' and args:
        action = args[0]
        if action.get('commands'):
            raise LspError('COMMAND_UNSUPPORTED', '패키지 설치 등 추가 효과가 필요한 코드 액션입니다')
        return convert(action.get('changes', []))
    if name == '_typescript.applyRefactoring' and args:
        source = Path(args[0]['file']).resolve()
        if not source.is_relative_to(session.root):
            raise PermissionError('사본 밖의 리팩터링 요청')
        # Ask tsserver for edits only. The adapter's applyRefactoring also creates files, so do not invoke it.
        result = session.client.request('workspace/executeCommand', {'command': 'typescript.tsserverRequest',
            'arguments': ['getEditsForRefactor', args[0], {'expectsResult': True}]})
        body = (result or {}).get('body') or {}
        if body.get('notApplicableReason'):
            raise LspError('ACTION_DISABLED', body['notApplicableReason'])
        return convert(body.get('edits', []))
    raise LspError('COMMAND_UNSUPPORTED', '편집으로 환원할 수 없는 서버 명령: ' + str(name))


def project_root(root, path, spec):
    root = Path(root).resolve()
    if not path:
        return root
    from coding_git import safe_path
    current = safe_path(root, path).parent
    while current.is_relative_to(root):
        if any((current / marker).is_file() for marker in spec.get('markers', [])):
            return current
        if current == root:
            break
        current = current.parent
    return root
