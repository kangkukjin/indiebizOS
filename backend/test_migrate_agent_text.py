"""안정 ID 저장의 이전·중단·복구와 실제 소비자 계약."""
import boot_paths  # noqa: F401
import yaml
import pytest
from pathlib import Path
from types import SimpleNamespace
import project_manager as pm
import migrate_agent_text as migration
import agent_lifecycle as life


@pytest.fixture
def project(tmp_path, monkeypatch):
    pp = tmp_path / 'projects/p'
    pp.mkdir(parents=True)
    pm.save_agent_settings(pp, {'agents': [{'id': 'stable-a', 'name': 'old', 'active': True}]})
    (pp / 'agent_old_role.txt').write_text('역할\n')
    (pp / 'agent_old_note.txt').write_text('메모\n')
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    return pp, tmp_path / 'data/_backups/2026-11-03_text'


def test_migrate_rename_read_write_and_latest_rollback(project):
    pp, backup = project
    assert migration.migrate(pp, backup, maintenance=True)['status'] == 'migrated'
    original_role = pp / 'agent_roles/stable-a/role.txt'
    inode = original_role.stat().st_ino
    assert life.read_text('p', 'stable-a', 'role') == '역할\n'
    life.update_agent('p', 'stable-a', name='new')
    assert original_role.stat().st_ino == inode
    assert not (pp / 'agent_new_role.txt').exists()
    life.write_text('p', 'stable-a', 'role', '편집한 최신 역할')
    assert migration.rollback(pp, backup, maintenance=True)['status'] == 'rolled_back'
    assert life.read_text('p', 'stable-a', 'role') == '편집한 최신 역할'
    assert (pp / 'agent_new_role.txt').read_text() == '편집한 최신 역할'
    assert original_role.read_text() == '편집한 최신 역할'
    assert (backup / 'agent_old_role.txt').read_text() == '역할\n'


def test_migration_resume_after_setting_commit_failure(project, monkeypatch):
    pp, backup = project
    save = migration.save_agent_settings
    monkeypatch.setattr(migration, 'save_agent_settings', lambda *a: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):
        migration.migrate(pp, backup, maintenance=True)
    assert pm.agent_settings(pp).get('agent_text_storage') is None
    assert life.read_text('p', 'stable-a', 'role') == '역할\n'
    monkeypatch.setattr(migration, 'save_agent_settings', save)
    assert migration.migrate(pp, backup, maintenance=True)['status'] == 'migrated'
    assert migration.migrate(pp, backup, maintenance=True)['status'] == 'already_migrated'


@pytest.mark.parametrize('problem', ['duplicate_id', 'duplicate_name', 'orphan', 'path', 'target', 'symlink'])
def test_migration_conflicts_never_change_setting_or_originals(project, problem):
    pp, backup = project
    data = pm.agent_settings(pp)
    if problem == 'duplicate_id':
        data['agents'].append({'id': 'stable-a', 'name': 'other'})
    if problem == 'duplicate_name':
        data['agents'].append({'id': 'other', 'name': 'old'})
    if problem == 'path':
        data['agents'][0]['id'] = '../escape'
    pm.save_agent_settings(pp, data)
    if problem == 'orphan':
        (pp / 'agent_unknown_note.txt').write_text('orphan')
    if problem == 'target':
        path = pp / 'agent_roles/stable-a/role.txt'
        path.parent.mkdir(parents=True)
        path.write_text('unowned')
    if problem == 'symlink':
        (pp / 'agent_roles').symlink_to(pp.parent, target_is_directory=True)
    before = (pp / 'agents.yaml').read_bytes()
    with pytest.raises(pm.AgentTextConflict):
        migration.migrate(pp, backup, maintenance=True)
    assert (pp / 'agents.yaml').read_bytes() == before
    assert (pp / 'agent_old_role.txt').read_text() == '역할\n'


def test_id_missing_never_falls_back_and_create_delete_uses_id(project):
    pp, backup = project
    migration.migrate(pp, backup, maintenance=True)
    role = pp / 'agent_roles/stable-a/role.txt'
    role.unlink()
    with pytest.raises(pm.AgentTextConflict):
        life.read_text('p', 'stable-a', 'role')
    with pytest.raises(pm.AgentTextConflict):
        life.write_text('p', 'stable-a', 'role', 'new')
    created = life.create_agent('p', 'second', role='second role')
    assert (pp / f"agent_roles/{created['id']}/role.txt").read_text() == 'second role'
    assert life.read_text('p', created['id'], 'note') == ''
    life.delete_agent('p', created['id'])
    assert not (pp / f"agent_roles/{created['id']}/role.txt").exists()


def test_research_template_identity_and_temporary_member_role(project):
    pp, backup = project
    migration.migrate(pp, backup, maintenance=True)
    cfg = {'id': 'research:runtime', 'name': 'topic changed', '_selected_agent': 'stable-a'}
    assert pm.configured_agent_text_path(pp, cfg, 'role').read_text() == '역할\n'
    from agent_cognitive import AgentCognitiveMixin
    runner = SimpleNamespace(project_path=pp, config=cfg)
    assert AgentCognitiveMixin._load_role(runner) == '역할\n'
    temporary = pp.parent / 'member_role.txt'
    temporary.write_text('temporary')
    runner.config = {'name': 'member', '_temporary_role_path': str(temporary)}
    assert AgentCognitiveMixin._load_role(runner) == 'temporary'


def test_id_template_copy_preserves_tree_without_root_duplicates(project):
    pp, backup = project
    migration.migrate(pp, backup, maintenance=True)
    base = pp.parents[1]
    manager = pm.ProjectManager(base)
    template = base / 'templates/id-template'
    template.mkdir()
    import shutil
    shutil.copytree(pp / 'agent_roles', template / 'agent_roles')
    shutil.copyfile(pp / 'agents.yaml', template / 'agents.yaml.template')
    dest = base / 'projects/copied'
    dest.mkdir()
    manager._copy_template_to_project(dest, 'id-template')
    assert pm.agent_settings(dest)['agent_text_storage'] == 'id-v1'
    assert (dest / 'agent_roles/stable-a/role.txt').read_text() == '역할\n'
    assert not list(dest.glob('agent_*_role.txt'))


def test_requires_maintenance_and_refuses_rollback_collision(project):
    pp, backup = project
    with pytest.raises(ValueError):
        migration.migrate(pp, backup)
    assert not backup.exists()
    migration.migrate(pp, backup, maintenance=True)
    life.update_agent('p', 'stable-a', name='new')
    (pp / 'agent_new_role.txt').write_text('other owner')
    with pytest.raises(pm.AgentTextConflict):
        migration.rollback(pp, backup, maintenance=True)
    assert pm.agent_settings(pp)['agent_text_storage'] == 'id-v1'


def test_legacy_extension_reads_and_writes_id_store_and_rejects_rename(project, monkeypatch):
    pp, backup = project
    migration.migrate(pp, backup, maintenance=True)
    import importlib.util
    source = Path(__file__).resolve().parents[1] / 'data/packages/installed/extensions/conversation/my_conversations.py'
    spec = importlib.util.spec_from_file_location('conversation_extension_for_test', source)
    extension = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extension)
    monkeypatch.chdir(pp)
    assert extension.MyConversations.load_agent_role('old') == '역할\n'
    saved = extension.MyConversations.save_agent_note('old', '새 메모')
    assert saved == str(pp / 'agent_roles/stable-a/note.txt')
    assert life.read_text('p', 'stable-a', 'note') == '새 메모'
    result = extension.MyConversations.rename_agent('old', 'new', str(pp))
    assert result['success'] is False
    assert pm.agent_settings(pp)['agents'][0]['name'] == 'old'
    assert (pp / 'agent_old_note.txt').read_text() == '메모\n'


def test_migration_resumes_after_exclusive_publish_interruption(project, monkeypatch):
    pp, backup = project
    original = migration.os.link
    calls = []
    def interrupted(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError('interrupted before second publication')
        return original(source, target)
    monkeypatch.setattr(migration.os, 'link', interrupted)
    with pytest.raises(OSError):
        migration.migrate(pp, backup, maintenance=True)
    assert pm.agent_settings(pp).get('agent_text_storage') is None
    assert (pp / 'agent_old_role.txt').read_text() == '역할\n'
    monkeypatch.setattr(migration.os, 'link', original)
    assert migration.migrate(pp, backup, maintenance=True)['status'] == 'migrated'


def test_rollback_resume_keeps_id_source_authoritative(project, monkeypatch):
    pp, backup = project
    migration.migrate(pp, backup, maintenance=True)
    life.write_text('p', 'stable-a', 'role', 'latest')
    original = migration.save_agent_settings
    monkeypatch.setattr(migration, 'save_agent_settings', lambda *a: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):
        migration.rollback(pp, backup, maintenance=True)
    assert life.read_text('p', 'stable-a', 'role') == 'latest'
    monkeypatch.setattr(migration, 'save_agent_settings', original)
    assert migration.rollback(pp, backup, maintenance=True)['status'] == 'rolled_back'
    assert life.read_text('p', 'stable-a', 'role') == 'latest'


def test_export_import_preserves_id_role_and_note(project, monkeypatch, tmp_path):
    import asyncio
    import io
    import api_config
    from starlette.datastructures import UploadFile
    pp, backup = project
    migration.migrate(pp, backup, maintenance=True)
    life.update_agent('p', 'stable-a', name='new')
    life.write_text('p', 'stable-a', 'note', 'latest note')
    monkeypatch.setattr(api_config, '_get_base_path', lambda: pp.parents[1])
    monkeypatch.setattr(api_config, 'ENV_PATH', tmp_path / 'absent.env')
    monkeypatch.setattr(api_config, 'DATA_PATH', tmp_path / 'empty-data')
    response = api_config.export_config()
    async def collect():
        return b''.join([chunk async for chunk in response.body_iterator])
    content = asyncio.run(collect())
    restored = tmp_path / 'restored'
    restored.mkdir()
    monkeypatch.setattr(api_config, '_get_base_path', lambda: restored)
    result = api_config.import_config(UploadFile(file=io.BytesIO(content), filename='config.zip'))
    assert result['status'] == 'success'
    data = pm.agent_settings(restored / 'projects/p')
    assert data['agent_text_storage'] == 'id-v1'
    assert data['agents'][0]['id'] == 'stable-a' and data['agents'][0]['name'] == 'new'
    assert pm.agent_text_path(restored / 'projects/p', data['agents'][0], 'role', data=data).read_text() == '역할\n'
    assert pm.agent_text_path(restored / 'projects/p', data['agents'][0], 'note', data=data).read_text() == 'latest note'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
