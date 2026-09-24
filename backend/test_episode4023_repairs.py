"""배포 스트림 경계·린트 실패·재개 대화 가이드 갱신의 회귀."""
import boot_paths  # noqa: F401
import asyncio
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / 'data/packages/installed/tools'


def load(relative):
    spec = importlib.util.spec_from_file_location('ep4023_' + Path(relative).stem, PACKAGES / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('stdout,stderr,expected', [
    ('https://project-123.vercel.app', 'Vercel CLI 50.1.1', 'https://project-123.vercel.app'),
    ('\x1b[32mhttps://project-123.vercel.app\x1b[0m\n', '', 'https://project-123.vercel.app'),
    ('https://actual.vercel.app\n', 'Aliased: https://alias.vercel.app', 'https://actual.vercel.app'),
    ('', 'Inspect: https://vercel.com/team/project\nProduction: https://actual.vercel.app [3s]',
     'https://actual.vercel.app'),
    ('https://wrong.vercel.app.evil.invalid', '', None),
    ('', 'completed without URL', None),
])
def test_deployment_stream_boundaries(stdout, stderr, expected):
    module = load('web-builder/tools/deploy_vercel.py')
    assert module._deployment_url(stdout, stderr) == expected


def test_deploy_result_does_not_redeploy_or_invent_url(tmp_path, monkeypatch):
    module = load('web-builder/tools/deploy_vercel.py')
    monkeypatch.setattr(module, 'check_vercel_cli', lambda: True)
    monkeypatch.setattr(module, 'check_vercel_auth', lambda *_: True)
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return {'success': True, 'stdout': '', 'stderr': 'done'}
    monkeypatch.setattr(module, 'run_command', run)
    result = module.run(str(tmp_path))
    assert result['success'] and result['url'] is None and result['warning']
    assert len(calls) == 1


@pytest.mark.parametrize('lint_ok,build_ok', [(False, True), (True, True), (True, False), (False, False)])
def test_lint_and_build_have_independent_receipts(tmp_path, monkeypatch, lint_ok, build_ok):
    module = load('web-builder/tools/build_site.py')
    (tmp_path / 'package.json').write_text(json.dumps({'scripts': {'build': 'build', 'lint': 'eslint'}}))
    def run(cmd, **kwargs):
        ok = lint_ok if cmd[-1] == 'lint' else build_ok
        return {'success': ok, 'stdout': '', 'stderr': '' if ok else 'missing eslint.config.mjs'}
    monkeypatch.setattr(module, 'run_command', run)
    result = module.run(str(tmp_path))
    assert result['success'] is (lint_ok and build_ok)
    assert result['build_success'] is build_ok
    assert result['lint']['success'] is lint_ok
    if not lint_ok:
        assert 'eslint.config.mjs' in result['lint']['stderr']


def test_old_ref_failure_returns_snapshot_recovery(monkeypatch):
    monkeypatch.syspath_prepend(str(PACKAGES / 'browser-action'))
    module = load('browser-action/browser_interact.py')
    monkeypatch.setattr(module, 'check_stale_ref', lambda *a: None)
    monkeypatch.setattr(module, 'find_locator', AsyncMock(return_value=None))
    session = SimpleNamespace(get_ref=lambda ref: {'role': 'button', 'name': 'closed menu'})
    locator, error = asyncio.run(module._resolve_locator(session, object(), {'ref': 'e55'}))
    assert locator is None and error['success'] is False
    assert error['error_code'] == 'REF_NOT_RESOLVED'
    assert error['recovery']['op'] == 'snapshot'


def test_followup_guide_map_and_reader_share_changed_revision(tmp_path, monkeypatch):
    import guide_registry as registry
    import associative_recall as recall
    import hippo_tree
    import ibl_routing
    import prompt_builder
    monkeypatch.setattr(registry, 'GUIDES_DIR', tmp_path)
    guide = tmp_path / 'fixture.md'
    guide.write_text('old procedure')
    stamp = guide.stat()
    monkeypatch.setattr(hippo_tree, 'sync_all', lambda: None)
    monkeypatch.setattr(hippo_tree, 'guide_map_text', lambda: '- 테스트: fixture.md')
    monkeypatch.setattr(ibl_routing, '_search_guide',
                        lambda *a: {'file': 'fixture.md', 'content': guide.read_text()})
    first = ibl_routing.search_guide('fixture.md', {})
    guide.write_text('new procedure')
    os.utime(guide, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    second = ibl_routing.search_guide('fixture.md', {})
    xml = recall._guide_map(recall.RecallRequest(None, '이어서', [], 'pipeline'), None).text
    assert first['catalog_revision'] != second['catalog_revision']
    assert second['catalog_revision'] in xml and first['catalog_revision'] not in xml
    assert '지문이 없거나 다르면' in xml and 'read_guide' in xml
    cmd = prompt_builder.compile_user_command('이어서', {'guide_files': ['fixture.md']})
    assert 'catalog_revision' in cmd and 'read_guide' in cmd
    guide.unlink()
    assert registry.catalog_revision() != second['catalog_revision']


def test_injected_guide_does_not_reuse_mtime_cached_text(tmp_path, monkeypatch):
    import prompt_builder as pb
    import guide_registry as registry
    folder = tmp_path / 'data/guides'
    folder.mkdir(parents=True)
    monkeypatch.setattr(pb, 'get_base_path', lambda: tmp_path)
    monkeypatch.setattr(registry, 'GUIDES_DIR', folder)
    monkeypatch.setattr(registry, 'freshness_note', lambda *a: '')
    monkeypatch.setattr(registry, 'record_use', lambda *a: None)
    monkeypatch.setattr(registry, 'mark_injected', lambda *a: None)
    guide = folder / 'fixture.md'
    guide.write_text('old procedure')
    stamp = guide.stat()
    builder = pb.PromptBuilder(tmp_path)
    first = builder._guide_block('fixture.md')
    guide.write_text('new procedure')
    os.utime(guide, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    second = builder._guide_block('fixture.md')
    assert 'old procedure' in first and 'old procedure' not in second
    assert 'new procedure' in second and registry.catalog_revision() in second


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
