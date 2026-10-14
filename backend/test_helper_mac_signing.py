"""실제 키체인 없이 Mac 서명·자동 수리 승인 경계를 검사한다."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def signing(tmp_path):
    helper = tmp_path / 'helper'
    (helper / 'desktop_native').mkdir(parents=True)
    for rel in ('sign_mac.sh', 'build.sh', 'desktop_native/build_mac.sh'):
        shutil.copyfile(ROOT / 'helper' / rel, helper / rel)
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    log = tmp_path / 'commands'
    fake = bin_dir / 'fake'
    fake.write_text(f'#!{sys.executable}\n' + '''import os, sys
from pathlib import Path
name, args = Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ['FAKE_LOG'], 'a') as stream:
    stream.write(name + ' ' + ' '.join(args) + '\\n')
if name == 'security':
    if os.environ.get('FAKE_MISSING') != '1':
        print('1) ABC "IndieBiz Helper Signing"')
elif name == 'codesign':
    target = Path(args[-1])
    receipt = target.with_name(target.name + '.identity')
    if '-d' in args:
        print('designated => identifier "' + receipt.read_text() + '" and certificate leaf = H"abc"')
    elif os.environ.get('FAKE_FAIL') == '1':
        sys.exit(1)
    else:
        receipt.write_text(args[args.index('--identifier') + 1])
elif name in ('clang', 'go'):
    target = Path(args[args.index('-o') + 1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('fake binary')
''')
    fake.chmod(0o755)
    for name in ('codesign', 'security', 'clang', 'go', 'python3'):
        (bin_dir / name).symlink_to(fake)
    env = {**os.environ, 'PATH': str(bin_dir) + os.pathsep + os.defpath,
           'FAKE_LOG': str(log), 'PYTEST_CURRENT_TEST': '', 'INDIEBIZ_REPAIR_CHILD': '',
           'INDIEBIZ_MAC_SIGN_IDENTITY': 'IndieBiz Helper Signing',
           'INDIEBIZ_MAC_SIGN_KEYCHAIN': str(tmp_path / 'fake.keychain')}

    def run(script, *args, terminal=False, **changes):
        test_env = {**env, **changes}
        argv = ['/bin/bash', str(helper / script), *map(str, args)]
        if terminal:
            import pty
            master, slave = pty.openpty()
            try:
                return subprocess.run(argv, stdin=slave, capture_output=True, text=True,
                                      env=test_env, timeout=15)
            finally:
                os.close(master)
                os.close(slave)
        return subprocess.run(argv, input='', capture_output=True, text=True,
                              env=test_env, timeout=15)

    return run, log, helper


@pytest.mark.parametrize('script,args', [
    ('sign_mac.sh', ('--interactive', 'com.indiebiz.helper', 'file')),
    ('sign_mac.sh', ('--setup-identity',)),
    ('build.sh', ('--sign',)),
    ('desktop_native/build_mac.sh', ('--interactive',)),
])
def test_noninteractive_signing_stops_before_any_keychain_or_build_tool(signing, script, args):
    run, log, _ = signing
    result = run(script, *args)
    assert result.returncode == 77
    assert 'AUTHORIZATION_REQUIRED' in result.stderr
    assert not log.exists()


@pytest.mark.parametrize('changes', [{'INDIEBIZ_REPAIR_CHILD': '1'}, {'PYTEST_CURRENT_TEST': 'test'}])
def test_automatic_jobs_cannot_sign_even_with_a_terminal(signing, changes):
    run, log, _ = signing
    result = run('sign_mac.sh', '--interactive', 'com.indiebiz.helper', 'file',
                 terminal=True, **changes)
    assert result.returncode == 77 and not log.exists()


def test_implicit_signing_is_rejected_even_when_identity_environment_is_set(signing):
    run, log, _ = signing
    assert run('sign_mac.sh', 'com.indiebiz.helper', 'file').returncode == 64
    assert not log.exists()


def test_default_build_only_uses_adhoc_for_all_five_mac_outputs(signing):
    run, log, _ = signing
    result = run('build.sh')
    assert result.returncode == 0, result.stderr
    commands = log.read_text().splitlines()
    signs = [row for row in commands if row.startswith('codesign ')]
    assert len(signs) == 5
    assert all('--sign - --identifier' in row for row in signs)
    assert not any(row.startswith('security ') for row in commands)


def test_explicit_build_signs_workers_before_embedding_and_all_helpers(signing):
    run, log, _ = signing
    result = run('build.sh', '--sign', terminal=True)
    assert result.returncode == 0, result.stderr
    commands = log.read_text().splitlines()
    signs = [row for row in commands if row.startswith('codesign --force')]
    assert len(signs) == 5
    assert all('--sign IndieBiz Helper Signing ' in row for row in signs)
    first_go = next(i for i, row in enumerate(commands) if row.startswith('go '))
    assert all(commands.index(row) < first_go for row in signs[:2])
    assert all('com.indiebiz.screen' in row for row in signs[:2])
    assert all('com.indiebiz.helper' in row for row in signs[2:])


def test_sign_failure_stops_without_retry_and_preserves_existing_worker(signing):
    run, log, helper = signing
    old = helper / 'desktop_native/bin/mac-arm64'
    old.parent.mkdir()
    old.write_text('previous working binary')
    result = run('desktop_native/build_mac.sh', '--interactive', terminal=True, FAKE_FAIL='1')
    assert result.returncode != 0
    assert old.read_text() == 'previous working binary'
    assert len([row for row in log.read_text().splitlines() if row.startswith('codesign ')]) == 1
    assert list(old.parent.iterdir()) == [old]


def test_missing_identity_never_falls_back_to_adhoc(signing):
    run, log, _ = signing
    result = run('sign_mac.sh', '--interactive', 'com.indiebiz.helper', 'file',
                 terminal=True, FAKE_MISSING='1', INDIEBIZ_MAC_ALLOW_UNSIGNED='1')
    assert result.returncode == 77
    assert 'codesign ' not in log.read_text()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
