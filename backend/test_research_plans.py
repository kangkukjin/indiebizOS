"""대화별 계획의 영속 연결·경합·프로젝트 이동/복제 계약."""
import boot_paths  # noqa: F401
from pathlib import Path

import pytest

from research_store import ResearchStore, ResearchConflict
from research_plans import ResearchPlans
from research_lifecycle import copy_project


def saved(root, name='first', previous=None):
    path = root / name / 'research_plan.md'
    path.parent.mkdir(parents=True)
    path.write_text('# 지속 연구\n교사의 역할과 학생 자율성을 함께 살핀다.')
    return {'path': str(path), 'previous_path': previous, 'body': path.read_text(),
            'saved_at': '2000-01-01', 'author': 'consciousness', 'sha256': 'test'}


def test_topic_plan_survives_new_store_rename_and_copy(tmp_path):
    project = tmp_path / 'original'
    project.mkdir()
    store = ResearchStore(project, 'p')
    tid = store.create_thread('교육')['id']
    other = store.create_thread('경제')['id']
    run, _ = store.begin_run(tid, '역할을 연구', 'first')
    root = project / 'outputs/research_plans'
    plans = ResearchPlans(store, root)
    first = plans.bind(tid, run, saved(root), 0)
    second = plans.bind(tid, run, saved(root, 'second', first['path']), 1)
    assert plans.current(other) is None
    store.write_response(tid, run, '완료', 'completed')
    store.update_thread(tid, title='교육의 변화')
    assert ResearchPlans(ResearchStore(project), root).current(tid) == {k: v for k, v in second.items() if k != 'body'}
    moved = tmp_path / 'renamed'
    project.rename(moved)
    reopened = ResearchPlans(ResearchStore(moved), moved / 'outputs/research_plans').current(tid)
    assert Path(reopened['path']).read_text().startswith('# 지속 연구')
    assert Path(reopened['previous_path']).exists()
    duplicate = tmp_path / 'copy'
    copy_project(moved, duplicate, 'new-project')
    copied = ResearchPlans(ResearchStore(duplicate), duplicate / 'outputs/research_plans').current(tid)
    assert copied['project_uid'] == 'new-project'
    assert Path(copied['path']).is_relative_to(duplicate)
    Path(copied['path']).write_text('복제본에서만 변경')
    assert Path(reopened['path']).read_text() != '복제본에서만 변경'


def test_stale_revision_run_and_foreign_path_cannot_replace_plan(tmp_path):
    store = ResearchStore(tmp_path, 'p')
    tid = store.create_thread('교육')['id']
    run, _ = store.begin_run(tid, '연구', 'first')
    root = tmp_path / 'outputs/research_plans'
    plans = ResearchPlans(store, root)
    receipt = plans.bind(tid, run, saved(root), 0)
    with pytest.raises(ResearchConflict, match='최신 판본'):
        plans.bind(tid, run, saved(root, 'stale'), 0)
    with pytest.raises(ResearchConflict, match='종료되었거나'):
        plans.bind(tid, 'other-run', receipt, 1)
    with pytest.raises(ValueError, match='저장소 안'):
        plans.bind(tid, run, {'path': str(tmp_path / 'foreign.md')}, 1)
    store.write_response(tid, run, '중단', 'cancelled')
    with pytest.raises(ResearchConflict):
        plans.bind(tid, run, receipt, 1)
    assert plans.current(tid) == {k: v for k, v in receipt.items() if k != 'body'}


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
