"""수리 후보의 번들 파생물이 검사·봉인 전에 만들어지고 함께 검증되는가."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
from test_repair_workspace_completion import setup  # noqa: F401


def builder(wt, *, broken=False):
    (wt / "scripts").mkdir(exist_ok=True)
    (wt / "backend").mkdir(exist_ok=True)
    (wt / "backend/new_module.py").write_text("VALUE = 1\n")
    script = wt / "scripts/build_body_bundle.py"
    script.write_text("""import json, sys
from pathlib import Path
dest = Path('data/bodies/android.engine.json')
if '--check' in sys.argv:
    raise SystemExit(0 if dest.exists() and json.loads(dest.read_text()) == {'modules': ['new_module']} else 1)
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps({'modules': ['new_module']}))
""" if not broken else "raise SystemExit(7)\n")


@pytest.mark.parametrize("broken", [False, True])
def test_op_apply_generates_bundle_before_verification_and_preserves_live(setup, monkeypatch, broken):
    root, wt, st, sess = setup
    builder(wt, broken=broken)
    calls = []
    def prepare(repo, session, verify, candidate):
        calls.append(1)
        assert json.loads((wt / 'data/bodies/android.engine.json').read_text()) == {'modules': ['new_module']}
        assert 'data/bodies/android.engine.json' in {r['rel'] for r in session['files'].values()}
        return {"success": False, "error": "stop after candidate inspection"}
    monkeypatch.setattr("supervision_bus.current", lambda: SimpleNamespace(
        repair_granted=True, prepare_repair=prepare))
    result = st.op_apply({"_repo_root": str(root), "_grant_key": sess["key"]})
    assert not result["success"]
    assert len(calls) == (0 if broken else 1)
    assert not (root / 'data/bodies/android.engine.json').exists()
    if broken:
        assert result['checks'][0]['gate'] == 'body_bundle' and not result['checks'][0]['passed']


def test_bundle_check_is_read_only_and_detects_missing_generated_file(setup):
    root, wt, st, sess = setup
    builder(wt)
    rels = ['backend/new_module.py']
    check = lambda: st._gates.body_bundle(str(wt), rels, st._sandbox_check)
    assert not check()['passed']
    assert not (wt / 'data/bodies/android.engine.json').exists()
    assert st._gates.body_bundle(str(wt), rels, st._sandbox_check, regenerate=True)['passed']
    assert check()['passed']
    (wt / 'data/bodies/android.engine.json').write_text('{}')
    assert not check()['passed']


def test_reservation_identity_is_saved_before_waiter_starts(setup, monkeypatch):
    from restart_protocol import read_json
    from restart_red import request_id
    root, wt, st, sess = setup
    monkeypatch.delenv('INDIEBIZ_REPAIR_NO_SPAWN', raising=False)
    observed = []
    def spawn(args, **kwargs):
        job = read_json(args[-1])
        current = st.read_session(str(root), sess['key'])
        assert current['status'] == 'apply_scheduled'
        assert current['scheduled_at'] == job['scheduled_at']
        assert job['restart_request_id'] == request_id(job)
        observed.append(job)
        return SimpleNamespace(pid=123)
    monkeypatch.setattr(st.subprocess, 'Popen', spawn)
    assert st._schedule_deferred_apply(str(root), sess, [])['scheduled']
    assert len(observed) == 1


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
