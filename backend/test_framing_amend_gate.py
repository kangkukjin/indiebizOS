"""영속 과제의 재검토: amend 길이/사슬 상한과 턴 기준 분리를 고정한다."""
import boot_paths  # noqa: F401
from types import SimpleNamespace
import pytest
import pursuit_bind as pb
from pursuit_ledger import PursuitLedger


@pytest.fixture
def drive(tmp_path):
    tokens = []
    def run(action='amend', amended='새 범위를 반영해 충분히 길게 다시 작성한 규정 전문입니다', chain=0):
        ledger = PursuitLedger(tmp_path / 'test.db', 'agent')
        row = ledger.create('과제', '전체 목표', f'origin{len(tokens)}', framing='이전 규정',
                            framing_meta={'_amend_count': chain})
        calls = []
        def full(*a, **kw):
            calls.append(True)
            return {'task_framing': '의식이 새로 쓴 규정', 'achievement_criteria': '새 턴 기준'}
        runner = SimpleNamespace(_run_consciousness=full)
        b = pb.Binding(runner, ledger, 'agent', f'turn{len(tokens)}', '계속해', [])
        tokens.append(pb._current.set(b)); b.bind(row)
        b.review = {'action': action, 'amended_framing': amended, 'criteria': '이번 턴 기준'}
        out = pb.run_consciousness(runner, '계속해', [], '')
        return out, ledger.get(row['id']), calls
    yield run
    for token in reversed(tokens):
        pb._current.reset(token)


def test_amend_updates_framing_and_preserves_goal(drive):
    out, row, calls = drive()
    assert row['framing'] == out['task_framing'] and out['_amend_count'] == 1
    assert row['goal_criteria'] == '전체 목표' and out['achievement_criteria'] == '이번 턴 기준'
    assert not calls


def test_short_amend_reawakens_instead_of_using_stale_map(drive):
    out, _, calls = drive(amended='짧다')
    assert calls and out['task_framing'] == '의식이 새로 쓴 규정'


def test_amend_chain_cap_reawakens(drive):
    _, row, calls = drive(chain=2)
    assert calls and not row['framing_meta'].get('_amend_count')


def test_keep_reuses_with_new_turn_criteria(drive):
    out, row, calls = drive(action='keep')
    assert not calls and row['framing'] == '이전 규정'
    assert out['achievement_criteria'] == '이번 턴 기준'


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
