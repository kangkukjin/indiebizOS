"""화면 판본의 원자성·무재기동 반영·소스/배포 분리 계약."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path

import pytest
import surface_assets as assets

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_surfaces', ROOT / 'scripts/build_surfaces.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture
def surface_store(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'view.html').write_text('<p>first</p>')
    store = tmp_path / 'releases'
    monkeypatch.setattr(assets, '_SOURCE', source)
    monkeypatch.setattr(assets, '_STORE', store)
    monkeypatch.setattr(assets, 'STATIC_INPUTS', ())
    monkeypatch.setattr(assets, '_cache', {})
    monkeypatch.setattr(builder, 'render_all', lambda: {'test': assets.read_asset('view.html')})
    return source, store


def test_source_save_does_not_deploy_and_build_does_not_activate(surface_store):
    source, store = surface_store
    assert assets.read_asset('view.html') == '<p>first</p>'
    (source / 'view.html').write_text('<p>second</p>')
    version = builder.build(store)
    assert (store / version / 'test.html').read_text() == '<p>second</p>'
    assert assets.read_asset('view.html') == '<p>first</p>'
    assert not (store / 'active.json').exists()
    builder.build(store, activate=True)
    assert assets.read_asset('view.html') == '<p>second</p>'


def test_one_response_pins_assets_and_old_release_survives(surface_store):
    source, store = surface_store
    old = builder.build(store, activate=True)
    with assets.asset_snapshot():
        assert assets.read_asset('view.html') == '<p>first</p>'
        (source / 'view.html').write_text('<p>second</p>')
        new = builder.build(store, activate=True)
        assert assets.read_asset('view.html') == '<p>first</p>'
    assert assets.read_asset('view.html') == '<p>second</p>'
    assert (store / old / 'test.html').read_text() == '<p>first</p>'
    assert json.loads((store / 'active.json').read_text()) == {'version': new, 'previous': old}


def test_incomplete_candidate_cannot_replace_active(surface_store, monkeypatch):
    source, store = surface_store
    old = builder.build(store, activate=True)
    (source / 'view.html').write_text('second')
    monkeypatch.setattr(builder, 'render_all', lambda: (_ for _ in ()).throw(ValueError('syntax error')))
    with pytest.raises(ValueError, match='syntax error'):
        builder.build(store, activate=True)
    assert json.loads((store / 'active.json').read_text())['version'] == old


def test_parallel_source_edit_rejects_activation(surface_store, monkeypatch):
    source, store = surface_store
    old = builder.build(store, activate=True)
    def changing_render():
        value = assets.read_asset('view.html')
        (source / 'view.html').write_text('concurrent edit')
        return {'test': value}
    monkeypatch.setattr(builder, 'render_all', changing_render)
    with pytest.raises(RuntimeError, match='변경'):
        builder.build(store, activate=True)
    assert json.loads((store / 'active.json').read_text())['version'] == old


def test_tampered_asset_rejected_before_serving(surface_store):
    _, store = surface_store
    version = builder.build(store, activate=True)
    (store / version / 'assets/view.html').write_text('tampered')
    with pytest.raises(ValueError, match='지문'):
        assets.read_asset('view.html')


def test_composition_change_gets_new_immutable_version(surface_store, monkeypatch):
    _, store = surface_store
    old = builder.build(store)
    monkeypatch.setattr(builder, 'render_all', lambda: {'test': '<section>new composition</section>'})
    new = builder.build(store)
    assert old != new
    assert (store / old / 'test.html').read_text() == '<p>first</p>'


def test_template_does_not_interpret_inserted_text(surface_store):
    source, _ = surface_store
    (source / 'view.html').write_text('<p>@@text@@</p>')
    assert assets.render_template('view.html', text='@@injected@@') == '<p>@@injected@@</p>'
    with pytest.raises(ValueError, match='missing'):
        assets.render_template('view.html')


def test_failed_new_asset_uses_previous_complete_release(surface_store):
    source, store = surface_store
    old = builder.build(store, activate=True)
    (source / 'view.html').write_text('candidate')
    new = builder.build(store, activate=True)
    (store / new / 'assets/view.html').write_text('broken')
    assert assets.read_asset('view.html') == '<p>first</p>'
    assert assets.read_artifact('test.html') == b'<p>first</p>'
    assert (store / old).is_dir()


def test_expected_version_blocks_concurrent_activation(surface_store):
    source, store = surface_store
    old = builder.build(store, activate=True)
    (source / 'view.html').write_text('changed after verification')
    with pytest.raises(ValueError, match='라이브 입력'):
        builder.build(store, activate=True, expected=old)
    assert json.loads((store / 'active.json').read_text())['version'] == old


def test_ui_repair_classification_does_not_restart_backend(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT / 'data/packages/installed/tools/system_essentials'))
    from repair_surfaces import touched
    assert touched(['frontend/surfaces/member/display.js'])
    assert touched(['frontend/src/components/chat/ChatDisplayView.tsx'])
    assert touched(['backend/static/app_render_core.js'])
    assert touched(['frontend/i18n/remote.json'])
    assert touched(['frontend/i18n/runtime.mjs'])
    assert touched(['frontend/package-lock.json'])
    assert not touched(['frontend/notes.md', 'data/notes.md'])


def test_owner_shared_behavior_changes_display_not_execution_host(tmp_path):
    import shutil
    import subprocess
    target = tmp_path / 'frontend'
    for path in assets.source_files():
        if path.is_relative_to(ROOT / 'frontend'):
            destination = target / path.relative_to(ROOT / 'frontend')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    (target / 'node_modules').symlink_to(ROOT / 'frontend/node_modules', target_is_directory=True)
    def host():
        return subprocess.check_output(['node', '--input-type=module', '-e',
            'import {ownerHost} from "./scripts/owner-display.mjs";console.log(ownerHost())'],
            cwd=target, text=True).strip()
    before = host()
    rules = target / 'surfaces/shared/conversation.js'
    rules.write_text(rules.read_text().replace('pageSize:50', 'pageSize:25'))
    assert host() == before
    preload = target / 'electron/preload.js'
    preload.write_text(preload.read_text() + '\n// changed native execution contract\n')
    assert host() != before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
