"""Code workspace adapter additions. Authorization stays above the LSP client."""
from pathlib import Path

from code_analysis_scope import check
from lsp_transport import LspError


class AnalysisWorkspace:
    @property
    def analysis(self):
        from code_analysis import manager
        return manager(self.store)

    def project(self, resource):
        row = self.store.get('code_view', resource) if resource.startswith('codeview_') else self.projects_api.project(resource)
        self.analysis.validate(row)
        if row.get('mode') == 'repair':
            from repair_context import active
            from thread_context import get_repair_workspace
            candidate = get_repair_workspace(create=False)
            if not active() or not candidate or Path(candidate).resolve() != Path(row['path']).resolve():
                raise PermissionError('현재 수리 후보가 아닌 작업 공간입니다')
        return row

    def open(self, path, goal=None, mode=None):
        check(path)
        from thread_context import get_repair_workspace
        from repair_context import active
        candidate = get_repair_workspace(create=False)
        if candidate and active() and Path(path).resolve() == Path(candidate).resolve():
            from code_analysis_changes import identity
            row = {'id': self.projects_api.resource_id(Path(candidate).resolve()), 'path': str(Path(candidate).resolve()),
                   'name': Path(candidate).name, 'mode': 'repair', 'root_identity': identity(candidate)}
            return self.store.save('project', row)
        if mode == 'inspect':
            return self.analysis.inspect(path)
        if mode not in (None, 'edit'):
            raise ValueError('code.mode는 inspect/edit입니다')
        check(path, write=True)
        return self.projects_api.open(path, goal)

    def analyze(self, row, selector, *, propose=False):
        try:
            return self.analysis.query(row, selector, propose=propose)
        except LspError as exc:
            status = 'unsupported' if exc.code in ('UNSUPPORTED', 'LANGUAGE_UNSUPPORTED', 'COMMAND_UNSUPPORTED') else 'unavailable' if exc.code == 'SERVER_UNAVAILABLE' else 'failed'
            return {'success': False, 'items': [], 'error': str(exc), 'error_code': exc.code,
                    'analysis': {'status': status, 'code': exc.code}}

    def read(self, row, selector):
        selector = selector or {}
        if selector.get('analysis'):
            return self.analyze(row, selector)
        if row.get('mode') != 'inspect':
            return self.projects_api.read(row, selector)
        if selector.get('path'):
            return self.projects_api.read(row, selector)
        items = []
        import os
        for root, dirs, files in os.walk(row['path']):
            dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '.venv', '__pycache__', '_backups') and not (Path(root) / d).is_symlink()]
            items.extend({'path': (Path(root) / name).relative_to(row['path']).as_posix()} for name in files)
        return {'items': items, 'mode': 'inspect'}

    def propose(self, row, selector, replacement):
        if (selector or {}).get('analysis'):
            return self.analyze(row, selector, propose=True)
        return self.projects_api.propose(row, selector or {}, replacement)

    def apply(self, row, proposal, client=None):
        p = self.store.get('workspace_proposal', proposal)
        if p.get('view'):
            return self.analysis.apply_draft(row, proposal, client)
        return self.projects_api.apply(row, proposal)

    @staticmethod
    def writable(row):
        check(row['path'], write=True)
        if row.get('mode') == 'inspect':
            raise PermissionError('inspect 뷰는 원본을 변경하지 않습니다')

    def recover(self, row):
        self.writable(row)
        from code_analysis_changes import recover
        return recover(self.store, row)

    def close(self, row):
        self.analysis.close_view(row['id'])
        return {'closed': True}
