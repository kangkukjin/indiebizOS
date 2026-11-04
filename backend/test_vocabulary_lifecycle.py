"""네 인수 원칙: 선택 권한·보존·호출 차단·회상 후보·복구."""
from types import SimpleNamespace

import pytest
import vocabulary_state as state
from test_vocabulary_state import box
from vocabulary_lifecycle import HUMAN_AUTHORITY, set_package_active


def test_sleep_wake_preserves_files_and_uses_one_reset(box, monkeypatch):
    import ibl_routing
    calls = []
    monkeypatch.setattr(ibl_routing, "invalidate_runtime_caches", lambda: calls.append(1) or [])
    before = {p: p.read_bytes() for p in box.rglob('*') if p.is_file()}
    assert not set_package_active("awake", False)["success"]
    assert state.is_active("awake")
    assert set_package_active("awake", False, authority=HUMAN_AUTHORITY)["success"]
    with pytest.raises(ValueError, match="잠들어"):
        state.require_tool_active("awake")
    assert set_package_active("awake", True, authority=HUMAN_AUTHORITY)["success"]
    state.require_tool_active("awake")
    assert len(calls) == 2
    assert all(p.read_bytes() == content for p, content in before.items())


def test_failed_reset_restores_selection(box, monkeypatch):
    import ibl_routing
    answers = iter([["failed"], []])
    monkeypatch.setattr(ibl_routing, "invalidate_runtime_caches", lambda: next(answers))
    with pytest.raises(RuntimeError, match="실패"):
        set_package_active("awake", False, authority=HUMAN_AUTHORITY)
    assert state.is_active("awake")


def test_required_cannot_sleep(box):
    with pytest.raises(ValueError, match="필수어휘"):
        set_package_active("base", False, authority=HUMAN_AUTHORITY)


def test_rag_refills_after_sleeping_top_results(monkeypatch):
    import ibl_usage_rag as rag
    # 코드는 줄마다 다르게 — 회상은 같은 코드를 한 번만 보인다(09-18 _distinct_codes). 이 시험이 지키는 것은 '잠든 상위를 건너 채우기'다.
    rows = [SimpleNamespace(id=i, ibl_code=(f"sleep-{i}" if i < 10 else f"awake-{i}")) for i in range(13)]
    class DB:
        def search_hybrid(self, top_k, **kwargs):
            return rows[:top_k]
    monkeypatch.setattr(rag, "_own_only", lambda rs: [r for r in rs if r.ibl_code.startswith("awake")])
    assert [r.id for r in rag._search_active(DB(), top_k=2)] == [10, 11]


def test_http_without_user_metadata_rejected(monkeypatch):
    import sys
    from starlette.requests import Request
    from api_vocabulary import human_authority
    monkeypatch.setitem(sys.modules, "api_launcher_web", SimpleNamespace(
        is_external_request=lambda req: False, verify_session=lambda req: False))
    request = Request({"type": "http", "headers": [], "method": "POST", "path": "/vocabulary/x/activation"})
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        human_authority(request)
    assert exc.value.status_code == 403


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


@pytest.mark.parametrize('profile', ['member', 'other'])
@pytest.mark.parametrize('selected', [None, True, False])
@pytest.mark.parametrize('owner_active', [True, False])
@pytest.mark.parametrize('requested', [True, False])
def test_profile_selection_preserves_explicit_choice(
        box, monkeypatch, profile, selected, owner_active, requested):
    import copy
    import ibl_routing
    before = copy.deepcopy(state.read_state())
    before['active']['awake'] = owner_active
    if selected is not None:
        before['profiles'] = {profile: {'active': {'awake': selected}}}
    state.write_state(before)
    original_bytes = state.state_path().read_bytes()
    resets = []
    monkeypatch.setattr(ibl_routing, 'invalidate_runtime_caches', lambda: resets.append(1) or [])
    if requested and not owner_active:
        with pytest.raises(ValueError, match='주인 선택'):
            set_package_active('awake', requested, authority=HUMAN_AUTHORITY, profile=profile)
        assert state.state_path().read_bytes() == original_bytes
        assert resets == []
        return
    result = set_package_active('awake', requested, authority=HUMAN_AUTHORITY, profile=profile)
    previous = (profile == 'member') if selected is None else selected
    changed = previous != requested
    assert result['changed'] is changed
    assert state.is_active('awake', profile=profile) is (owner_active and requested)
    assert len(resets) == int(changed)
    assert state.read_state()['revision'] == before['revision'] + int(changed)
    if changed:
        assert state.read_state()['profiles'][profile]['active']['awake'] is requested
    else:
        assert state.state_path().read_bytes() == original_bytes
    if not owner_active:
        # 주인이 나중에 켜도 회원이 기록한 거부는 남는다.
        after = copy.deepcopy(state.read_state())
        after['active']['awake'] = True
        state.write_state(after)
        assert state.is_active('awake', profile=profile) is requested


@pytest.mark.parametrize('profile', ['owner', 'member'])
@pytest.mark.parametrize('failure', ['list', 'exception', 'write_before', 'write_after',
                                     'restore_write', 'restore_cache', 'conflict'])
def test_selection_failure_and_retry(box, monkeypatch, profile, failure):
    import copy
    import ibl_routing
    import vocabulary_lifecycle as lifecycle
    before = copy.deepcopy(state.read_state())
    before['profiles'] = {'member': {'active': {'awake': True}}}
    state.write_state(before)
    resets, writes = [], []
    real_write = state.write_state

    def write(value):
        writes.append(copy.deepcopy(value))
        if failure == 'write_before' and len(writes) == 1:
            raise OSError('initial write')
        if failure == 'restore_write' and len(writes) == 2:
            raise OSError('restore write')
        real_write(value)
        if failure == 'write_after' and len(writes) == 1:
            raise OSError('after replace')

    def refresh():
        resets.append(1)
        if len(resets) == 1 and failure not in {'write_before', 'write_after'}:
            if failure == 'conflict':
                newer = copy.deepcopy(state.read_state())
                newer['revision'] += 1
                newer['external'] = 'preserve'
                real_write(newer)
            if failure == 'exception':
                raise RuntimeError('initial refresh')
            return ['initial refresh']
        if failure == 'restore_cache' and len(resets) == 2:
            raise RuntimeError('restore refresh')
        return []

    monkeypatch.setattr(lifecycle, 'write_state', write)
    monkeypatch.setattr(ibl_routing, 'invalidate_runtime_caches', refresh)
    with pytest.raises((OSError, RuntimeError)) as error:
        set_package_active('awake', False, authority=HUMAN_AUTHORITY, profile=profile)
    current = state.read_state()
    if failure == 'conflict':
        assert current['external'] == 'preserve'
        assert '판본 충돌' in str(error.value)
        assert len(writes) == 1
        return
    if failure == 'restore_write':
        assert '원장 복구 실패' in str(error.value)
        assert error.value.__cause__ is not None
        assert not state.is_active('awake', profile=profile)
        return
    assert state.is_active('awake', profile=profile)
    assert current['revision'] == before['revision'] + (0 if failure == 'write_before' else 2)
    if failure == 'write_before':
        assert resets == []
    if failure == 'restore_cache':
        assert '캐시 복구 실패' in str(error.value)
        assert error.value.__cause__ is not None
    monkeypatch.setattr(lifecycle, 'write_state', real_write)
    monkeypatch.setattr(ibl_routing, 'invalidate_runtime_caches', lambda: resets.append(1) or [])
    count = len(resets)
    result = set_package_active('awake', False, authority=HUMAN_AUTHORITY, profile=profile)
    assert result['changed'] is True
    assert not state.is_active('awake', profile=profile)
    assert len(resets) == count + 1


def test_concurrent_selection_updates_keep_both_choices(box, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import ibl_routing
    monkeypatch.setattr(ibl_routing, 'invalidate_runtime_caches', lambda: [])
    before = state.read_state()['revision']
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(set_package_active, 'awake', False,
                               authority=HUMAN_AUTHORITY, profile=p) for p in ['member', 'owner']]
        assert all(f.result()['changed'] for f in futures)
    after = state.read_state()
    assert after['revision'] == before + 2
    assert after['active']['awake'] is False
    assert after['profiles']['member']['active']['awake'] is False
