"""Internal coding copies, one integration candidate and conditional application.

Snapshots deliberately have independent Git metadata: dirty/untracked bytes are
the baseline and a worker cannot use a shared worktree gitdir to alter the source.
The existing coding object store owns manifests and recovery receipts.
"""
import os
from pathlib import Path
import stat
import subprocess
import time
import uuid

from coding_store import CodingStore, fingerprint
from coding_git import safe_path


def _controller():
    import principal
    from conversation_sessions import current
    if not principal.is_owner() or not current():
        raise PermissionError('코드 협업은 소유자의 대화 세션에서 시작합니다')
    return current().session_id


class Collaboration:
    def __init__(self, store=None):
        self.store = store or CodingStore()

    def _snapshot(self, folder, include=()):
        folder = Path(folder)
        if (folder / '.git').exists():
            proc = subprocess.run(['git', '-C', str(folder), 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                                  capture_output=True, check=True)
            names = set(os.fsdecode(n) for n in proc.stdout.split(b'\0') if n)
        else:
            names = {str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file() or p.is_symlink()}
        # Newly added ignored files are not in the source Git index. The apply
        # receipt still owns their bytes and must observe them during recovery.
        names.update(include)
        result, total = {}, 0
        for name in sorted(names):
            p = safe_path(folder, name, allow_link=True)
            if not p.exists() and not p.is_symlink():
                continue
            st = p.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise ValueError('협업 변경은 일반 파일만 지원합니다(링크·서브모듈·하드 링크는 명시적으로 거절): ' + name)
            data = p.read_bytes()
            total += len(data)
            if len(result) >= 10000 or total > 100 * 1024 * 1024:
                raise ValueError('협업 스냅샷 한도(10000파일/100MiB)를 넘었습니다. 범위를 나누세요')
            digest = fingerprint(data)
            blob = self.store.root / 'collaboration_blobs' / digest
            blob.parent.mkdir(parents=True, exist_ok=True)
            try:
                with blob.open('xb') as stream:
                    stream.write(data)
            except FileExistsError:
                if fingerprint(blob.read_bytes()) != digest:
                    raise ValueError('스냅샷 객체가 손상되었습니다')
            result[name] = {'sha': digest, 'mode': stat.S_IMODE(st.st_mode)}
        return result

    def _write(self, folder, name, entry):
        p = safe_path(folder, name)
        if entry is None:
            p.unlink(missing_ok=True)
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        blob = self.store.root / 'collaboration_blobs' / entry['sha']
        data = blob.read_bytes()
        if fingerprint(data) != entry['sha']:
            raise ValueError('검증 바이트가 손상되었습니다')
        temp = p.parent / ('.collaboration-' + uuid.uuid4().hex)
        try:
            with temp.open('xb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temp.chmod(entry['mode'])
            os.replace(temp, p)
        finally:
            temp.unlink(missing_ok=True)

    def _materialize(self, folder, entries):
        folder.mkdir(parents=True, exist_ok=False)
        for name, entry in entries.items():
            self._write(folder, name, entry)
        subprocess.run(['git', 'init', '-q', str(folder)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(folder), 'add', '--force', '--all', '--', '.'], check=True, capture_output=True)

    def prepare(self, project, request_id, workers, controller):
        from coding_projects import CodingProjects
        source = Path(project['path']).resolve()
        CodingProjects(self.store)._refuse_self(source)
        if not request_id or type(workers) is not int or not 2 <= workers <= 8:
            raise ValueError('request_id와 workers(2~8)가 필요합니다')
        ident = 'collaboration_' + fingerprint([project['id'], controller, request_id])[:32]
        with self.store.lock(ident):
            try:
                existing = self.store.get('collaboration', ident)
            except ValueError:
                existing = None
            if existing:
                if existing['workers'] != workers:
                    raise ValueError('같은 request_id에 다른 작업자 수를 지정했습니다')
                return existing
            baseline = self._snapshot(source)
            folder = self.store.root / 'collaborations' / ident
            folder.mkdir(parents=True, exist_ok=True)
            row = {'id': ident, 'controller': controller, 'project': project['id'], 'source': str(source),
                   'baseline': baseline, 'workers': workers, 'copies': [], 'state': 'preparing',
                   'excluded': 'Git ignored 파일과 .git 메타데이터', 'applied': []}
            self.store.save('collaboration', row)
            for i in range(workers):
                copy = folder / ('worker-' + str(i))
                self._materialize(copy, baseline)
                row['copies'].append(str(copy))
            # An editor changing the source during copying invalidates admission.
            if self._snapshot(source) != baseline:
                row['state'] = 'source_changed'
                self.store.save('collaboration', row)
                raise ValueError('사본 준비 중 원본이 바뀌었습니다. 새 요청으로 준비하세요')
            row.update(state='ready', workspaces=[{'collaboration': ident, 'worker': i} for i in range(workers)])
            return self.store.save('collaboration', row)

    def merge(self, row):
        baseline, combined, owners, conflicts = row['baseline'], dict(row['baseline']), {}, []
        for index, copy in enumerate(row['copies']):
            current = self._snapshot(copy)
            for name in baseline.keys() | current.keys():
                if baseline.get(name) == current.get(name):
                    continue
                if name in owners and combined.get(name) != current.get(name):
                    conflicts.append({'path': name, 'workers': [owners[name], index]})
                    continue
                owners[name] = index
                if name in current:
                    combined[name] = current[name]
                else:
                    combined.pop(name, None)
        for name in combined:
            if any(str(parent) in combined for parent in Path(name).parents if str(parent) != '.'):
                conflicts.append({'path': name, 'reason': '파일/디렉터리 충돌'})
        if conflicts:
            row.update(state='conflict', conflicts=conflicts)
            row.pop('validation', None)
            return self.store.save('collaboration', row)
        candidate = self.store.root / 'collaborations' / row['id'] / ('candidate-' + uuid.uuid4().hex)
        self._materialize(candidate, combined)
        row.update(state='merged', candidate=str(candidate), merged=combined, conflicts=[],
                   candidate_hash=fingerprint(combined), changed=sorted(owners))
        row.pop('validation', None)
        return self.store.save('collaboration', row)

    def validate(self, row, checks):
        if row['state'] not in {'merged', 'validated'} or not checks:
            raise ValueError('먼저 충돌 없는 후보를 만들고 checks에 검사 명령 배열을 지정하세요')
        if not isinstance(checks, list) or any(not isinstance(c, list) or not c or any(not isinstance(v, str) for v in c) for c in checks):
            raise ValueError('checks는 argv 배열들의 목록입니다')
        from coding_process import CodingProcesses
        from task_cancellation import requested
        from thread_context import get_current_task_id, get_current_project_id
        proc_owner = CodingProcesses(row['candidate'], Path(row['candidate']).parent / 'validation-runtime')
        reports = []
        try:
            for command in checks:
                proc = proc_owner.spawn(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                # communicate drains pipes; no subprocess can block on a full pipe.
                started = time.monotonic()
                while True:
                    try:
                        output, _ = proc.communicate(timeout=.2)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() - started > 240 or requested(get_current_project_id() or 'system', get_current_task_id()):
                            proc_owner.terminate(proc)
                            raise ValueError('통합 검사 시간 초과 또는 취소')
                reports.append({'argv': command, 'exit_code': proc.returncode,
                                'output': output.decode(errors='replace')[-16000:]})
                if proc.returncode:
                    break
        finally:
            proc_owner.close()
        current = self._snapshot(row['candidate'])
        passed = current == row['merged'] and len(reports) == len(checks) and all(r['exit_code'] == 0 for r in reports)
        row.update(state='validated' if passed else 'validation_failed',
                   validation={'candidate_hash': fingerprint(current), 'passed': passed, 'reports': reports})
        return self.store.save('collaboration', row)

    def apply(self, row):
        if row['state'] == 'applied':
            return row
        if (row['state'] != 'validated' or not row.get('validation', {}).get('passed')
                or row['validation'].get('candidate_hash') != row['candidate_hash']):
            raise ValueError('같은 후보 바이트의 통합 검사 통과가 필요합니다')
        if self._snapshot(row['candidate']) != row['merged']:
            raise ValueError('검사 뒤 후보가 바뀌었습니다. 다시 통합·검사하세요')
        if self._snapshot(row['source'], row['merged']) != row['baseline']:
            raise ValueError('준비 이후 원본이 바뀌었습니다. 덮어쓰지 않고 새 기준에서 통합해야 합니다')
        row.update(state='applying', applied=[])
        self.store.save('collaboration', row)
        try:
            for name in row['changed']:
                before = self._snapshot(row['source'], row['changed'])
                expected = dict(row['baseline'])
                for done in row['applied']:
                    if done in row['merged']:
                        expected[done] = row['merged'][done]
                    else:
                        expected.pop(done, None)
                if before != expected:
                    raise ValueError('적용 중 외부 변경을 발견했습니다')
                target = safe_path(row['source'], name)
                if name not in expected and (target.exists() or target.is_symlink()):
                    raise ValueError('스냅샷에서 제외된 기존 경로는 덮어쓰지 않습니다: ' + name)
                row['inflight'] = name
                self.store.save('collaboration', row)
                self._write(row['source'], name, row['merged'].get(name))
                row['applied'].append(name)
                row.pop('inflight', None)
                self.store.save('collaboration', row)
            if self._snapshot(row['source'], row['merged']) != row['merged']:
                raise ValueError('반영 후 원본 지문이 다릅니다')
            row['state'] = 'applied'
        except BaseException as exc:
            row.update(state='partial', error=str(exc))
            self.store.save('collaboration', row)
            raise
        return self.store.save('collaboration', row)

    def recover(self, row):
        if row['state'] not in {'partial', 'applying'}:
            return row
        unresolved = []
        for name in reversed(list(dict.fromkeys(row['applied'] + ([row['inflight']] if row.get('inflight') else [])))):
            current = self._snapshot(row['source'], row['changed']).get(name)
            if current == row['baseline'].get(name):
                continue
            if current != row['merged'].get(name):
                unresolved.append(name)
                continue
            self._write(row['source'], name, row['baseline'].get(name))
        row.update(state='partial' if unresolved else 'recovered', unresolved=unresolved)
        return self.store.save('collaboration', row)

    def run(self, project, phase, *, request_id=None, workers=2, collaboration=None, checks=None):
        controller = _controller()
        if phase == 'prepare':
            return self.prepare(project, request_id, workers, controller)
        row = self.store.get('collaboration', collaboration)
        if row['controller'] != controller or row['project'] != project['id']:
            raise PermissionError('이 대화·프로젝트의 협업이 아닙니다')
        if phase in {'merge', 'validate', 'apply'}:
            import conversation_sessions as sessions
            with sessions.connection(sessions.current().db_path) as conn:
                cols = {r[1] for r in conn.execute('PRAGMA table_info(tasks)')}
                if 'worker_payload' in cols and conn.execute("SELECT 1 FROM tasks WHERE json_extract(worker_payload,'$.workspace.collaboration')=? AND status NOT IN ('completed','failed','cancelled')", (collaboration,)).fetchone():
                    raise ValueError('아직 이 사본에서 실행 중인 자식이 있습니다. task_ref로 종료를 확인하세요')
        with self.store.lock('collaboration-source:' + row['source']):
            row = self.store.get('collaboration', collaboration)
            if phase == 'merge':
                return self.merge(row)
            if phase == 'validate':
                return self.validate(row, checks)
            if phase == 'apply':
                return self.apply(row)
            if phase == 'recover':
                return self.recover(row)
            if phase == 'status':
                return row
            raise ValueError('phase는 prepare/merge/validate/apply/recover/status입니다')


def resolve_workspace(ref, controller):
    row = CodingStore().get('collaboration', ref.get('collaboration'))
    if row['controller'] != controller or row['state'] not in {'ready', 'merged', 'conflict', 'validation_failed', 'validated'}:
        raise PermissionError('사용할 수 없는 작업 사본입니다')
    index = ref.get('worker')
    if type(index) is not int or not 0 <= index < row['workers']:
        raise ValueError('잘못된 작업 사본 참조입니다')
    return row['copies'][index]
