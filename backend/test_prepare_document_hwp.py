"""Build-time RHWP portability; all generated assets stay in temporary roots."""
import importlib.util
import io
import json
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

SPEC = importlib.util.spec_from_file_location(
    'prepare_document_hwp', Path(__file__).resolve().parents[1] / 'scripts/prepare_document_hwp.py')
hwp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hwp)


@pytest.mark.parametrize('platform, executable', [('nt', 'npm.cmd'), ('posix', 'npm')])
def test_install_dependencies_resolves_executable(platform, executable, monkeypatch, tmp_path):
    monkeypatch.setattr(hwp, 'os', SimpleNamespace(name=platform))
    resolved = str(tmp_path / 'Node with spaces' / executable)
    monkeypatch.setattr(hwp.shutil, 'which', lambda name: resolved if name == executable else None)
    calls = []
    monkeypatch.setattr(hwp.subprocess, 'run', lambda *args, **kwargs: calls.append((args, kwargs)))
    hwp.install_dependencies(tmp_path)
    assert calls == [(([resolved, 'ci', '--ignore-scripts'],), {'cwd': tmp_path, 'check': True})]
    monkeypatch.setattr(hwp.shutil, 'which', lambda name: None)
    with pytest.raises(FileNotFoundError, match='npm is required'):
        hwp.install_dependencies(tmp_path)


def test_windows_manifest_uses_portable_nested_keys():
    class Asset(PureWindowsPath):
        def is_file(self):
            return True

        def open(self, mode):
            return io.BytesIO(b'license')

    class Directory(PureWindowsPath):
        def rglob(self, pattern):
            return [Asset(self / 'licenses' / 'notice.txt')]

    assert list(hwp.asset_hashes(Directory('C:/build/rhwp'))) == ['licenses/notice.txt']


def test_install_and_self_check_with_nested_assets(tmp_path, monkeypatch):
    source, host, root, dest = (tmp_path / name for name in ('source', 'host', 'repo', 'rhwp'))
    contents = {
        source / 'rhwp-studio/src/main.ts': 'IndieBiz: refuse a reported lossy serialization',
        source / 'rhwp-studio/dist/index.html': '<html>한글</html>',
        source / 'rhwp-studio/dist/assets/app.js': 'export const ready = true;',
        source / 'pkg/rhwp.js': 'export {};',
        source / 'LICENSE': 'MIT', source / 'THIRD_PARTY_LICENSES.md': 'Notices',
        host / 'host.html': '<html>한글</html>', host / 'host.js': 'export {};',
        host / 'licenses/notice.txt': '한글 고지',
    }
    for name in ('index.js', 'transport.js', 'document-agent-contract.js'):
        contents[root / 'frontend/node_modules/@rhwp/editor' / name] = 'export {};'
    for file, text in contents.items():
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding='utf-8')
    for name, value in [('ROOT', root), ('HOST', host), ('DEST', dest)]:
        monkeypatch.setattr(hwp, name, value)
    hwp.install(source)  # Calls the real manifest self-check.
    manifest = json.loads((dest / 'indiebiz-build.json').read_text(encoding='utf-8'))
    assert 'licenses/notice.txt' in manifest['files']
    assert 'assets/app.js' in manifest['files']
    (dest / 'licenses/notice.txt').write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='RHWP asset changed'):
        hwp.check()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
