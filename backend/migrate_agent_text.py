"""프로젝트 역할·메모의 일회성 ID 저장 이전. 기본 동작은 읽기 전용 검사다.

운영 쓰기를 멈춘 유지보수 구간에서만 --apply --maintenance-confirmed를 사용한다.
구 파일은 삭제하지 않는다. --rollback도 최신 텍스트를 보존하고 선언을 마지막에 바꾼다.
"""
import boot_paths  # noqa: F401
import hashlib
import json
import os
import tempfile
from pathlib import Path

from project_manager import (AgentTextConflict, agent_settings, agent_text_path,
                             save_agent_settings, resolve_text_agent)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def inspect_project(project_path):
    pp = Path(project_path)
    source = (pp / 'agents.yaml').read_bytes()
    data = agent_settings(pp)
    agents = data.get('agents') or []
    ids, names, owned, entries = set(), set(), set(), []
    if data.get('agent_text_storage') not in (None, 'id-v1'):
        raise AgentTextConflict('알 수 없는 저장 형식')
    for agent in agents:
        identity, name = agent.get('id'), agent.get('name', agent.get('id'))
        if identity in ids or name in names:
            raise AgentTextConflict('중복 ID 또는 표시 이름')
        ids.add(identity); names.add(name)
        for kind in ('role', 'note'):
            legacy = agent_text_path(pp, agent, kind, data={}, require_exists=False)
            target = agent_text_path(pp, agent, kind, data={'agent_text_storage': 'id-v1'}, require_exists=False)
            owned.add(legacy.name)
            current = target if data.get('agent_text_storage') == 'id-v1' else legacy
            if data.get('agent_text_storage') == 'id-v1' and not current.is_file():
                raise AgentTextConflict('ID 저장 파일 누락')
            content = current.read_bytes() if current.exists() else b''
            entries.append({'id': identity, 'kind': kind, 'legacy': legacy.name,
                            'target': str(target.relative_to(pp)), 'sha256': digest(content),
                            'legacy_present': legacy.exists()})
    orphan = [p.name for pattern in ('agent_*_role.txt', 'agent_*_note.txt')
              for p in pp.glob(pattern) if p.name not in owned]
    if orphan and data.get('agent_text_storage') != 'id-v1':
        raise AgentTextConflict('소유가 불명확한 역할·메모 파일이 있습니다.')
    return {'format': data.get('agent_text_storage'), 'source_sha256': digest(source), 'entries': entries}


def migrate(project_path, backup_path, *, maintenance=False):
    if not maintenance:
        raise ValueError('프로젝트와 외부 확장의 쓰기가 멈춘 유지보수 구간이 필요합니다.')
    pp, backup = Path(project_path), Path(backup_path)
    plan = inspect_project(pp)
    if plan['format'] == 'id-v1':
        return {'status': 'already_migrated', 'files': len(plan['entries'])}
    # 기존 백업이 있으면 정확히 같은 이전의 재개만 허용한다.
    manifest = backup / 'manifest.json'
    if not manifest.exists() and any((pp / entry['target']).exists() for entry in plan['entries']):
        raise AgentTextConflict('이 이전이 소유하지 않은 ID 목적지가 있습니다.')
    if manifest.exists():
        if json.loads(manifest.read_text()) != plan:
            raise AgentTextConflict('백업과 현재 입력 판본이 다릅니다.')
    else:
        backup.mkdir(parents=True, exist_ok=False)
        (backup / 'agents.yaml').write_bytes((pp / 'agents.yaml').read_bytes())
        for entry in plan['entries']:
            if entry['legacy_present']:
                (backup / entry['legacy']).write_bytes((pp / entry['legacy']).read_bytes())
        # 백업 완성 뒤에만 재개 가능한 manifest를 만든다.
        manifest.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    for entry in plan['entries']:
        source = pp / entry['legacy']
        content = source.read_bytes() if source.exists() else b''
        if digest(content) != entry['sha256']:
            raise AgentTextConflict('이전 중 원본 텍스트가 변경되었습니다.')
        target = pp / entry['target']
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.agent-text-', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)  # 배타적 게시: 미완성 본문은 목적지가 되지 않는다.
            except FileExistsError:
                if target.is_symlink() or target.read_bytes() != content:
                    raise AgentTextConflict('기존 ID 목적지가 이전 원본과 다릅니다.')
        finally:
            Path(temporary).unlink(missing_ok=True)
        if target.read_bytes() != content:
            raise AgentTextConflict('복사 검증 실패')
    # 설정·원문·목적지 모두 마지막에 재대조한다. 외부 쓰기 제어를 대체하지 않는다.
    if inspect_project(pp) != plan:
        raise AgentTextConflict('이전 중 프로젝트 입력 판본이 변경되었습니다.')
    data = agent_settings(pp)
    data['agent_text_storage'] = 'id-v1'
    save_agent_settings(pp, data)
    return {'status': 'migrated', 'files': len(plan['entries'])}


def rollback(project_path, backup_path, *, maintenance=False):
    if not maintenance:
        raise ValueError('유지보수 구간이 필요합니다.')
    pp, backup = Path(project_path), Path(backup_path)
    original = json.loads((backup / 'manifest.json').read_text())
    current = inspect_project(pp)
    if current['format'] != 'id-v1':
        raise AgentTextConflict('ID 저장 형식에서만 되돌릴 수 있습니다.')
    data = agent_settings(pp)
    originals = {(row['id'], row['kind']): row for row in original['entries']}
    writes = []
    for entry in current['entries']:
        previous = originals.get((entry['id'], entry['kind']))
        if previous is None:
            raise AgentTextConflict('이전 후 신원이 변경되어 무손실 역매핑을 확인해야 합니다.')
        target = pp / entry['legacy']
        content = (pp / entry['target']).read_bytes()
        if target.exists() and target.read_bytes() != content:
            # 이 이전이 보존해 둔 옛 파일만 교체 가능하다.
            if target.name != previous['legacy'] or digest(target.read_bytes()) != previous['sha256']:
                raise AgentTextConflict('되돌릴 이름의 파일이 다른 내용을 소유합니다.')
        writes.append((target, content))
    # ID 원본은 계속 남는다. 중단 후 id-v1 선언으로 최신 본문을 읽고 재시도한다.
    for target, content in writes:
        target.write_bytes(content)
    for target, content in writes:
        if target.read_bytes() != content:
            raise AgentTextConflict('역매핑 검증 실패')
    if any(digest((pp / entry['target']).read_bytes()) != entry['sha256'] for entry in current['entries']):
        raise AgentTextConflict('되돌리는 중 ID 원본 변경')
    if digest((pp / 'agents.yaml').read_bytes()) != current['source_sha256']:
        raise AgentTextConflict('되돌리는 중 설정 변경')
    data.pop('agent_text_storage', None)
    save_agent_settings(pp, data)
    return {'status': 'rolled_back', 'files': len(writes)}


if __name__ == '__main__':
    import argparse
    from runtime_utils import get_base_path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--maintenance-confirmed', action='store_true')
    parser.add_argument('--backup-name')
    args = parser.parse_args()
    from agent_lifecycle import _project_path
    pp = _project_path(args.project)
    if args.apply or args.rollback:
        if not args.backup_name or Path(args.backup_name).name != args.backup_name or args.backup_name in ('.', '..'):
            parser.error('--backup-name YYYY-MM-DD_이름이 필요합니다.')
        from datetime import date
        try:
            date.fromisoformat(args.backup_name[:10])
            if args.backup_name[10:11] != '_' or len(args.backup_name) < 12:
                raise ValueError('name')
        except ValueError:
            parser.error('백업 이름은 YYYY-MM-DD_이름이어야 합니다.')
        backup = get_base_path() / 'data/_backups' / args.backup_name
        result = (rollback if args.rollback else migrate)(pp, backup, maintenance=args.maintenance_confirmed)
    else:
        plan = inspect_project(pp)
        result = {'format': plan['format'], 'files': len(plan['entries']), 'source_sha256': plan['source_sha256']}
    print(json.dumps(result, ensure_ascii=False))
