import boot_paths  # noqa: F401
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
import time

import pytest

from execution_capacity import Capacity, fanout, scope
from test_ibl_v2_core import adapter, run


@pytest.mark.parametrize('limit', [1, 2, 8])
def test_nested_work_finishes_with_bounded_active_calls(limit):
    capacity, lock = Capacity(limit), Lock()
    active = peak = 0

    def leaf(rt, args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(.003)
        with lock:
            active -= 1
        return args['n']

    with scope(capacity=capacity, limit=limit):
        result = run('''[table:each]{items:[1,2,3],parallel:2} {
            [table:each]{items:[1,2,3,4],parallel:4} {
                [test:read]{n:$it}
            }
        }''', registry={'test:read': adapter(leaf, {'n': 'Number'}, 'Number')})
    assert result['success'], result
    assert result['value'] == [[1, 2, 3, 4]] * 3
    assert 1 <= peak <= limit
    assert capacity.active == 0
    if limit > 2:
        assert peak > 2  # the old nested-serial implementation cannot do this


def test_parent_error_drains_started_descendants_without_holding_slot():
    capacity = Capacity(2)
    started, proceed = Event(), Event()

    def child(i):
        if i == 0:
            started.set()
            proceed.wait(2)
            fanout(2, 2, lambda j: j, lambda j, f: f.result() >= 0)
        else:
            assert started.wait(2)
            proceed.set()
        return i

    def accept(i, f):
        if i == 1:
            raise ValueError('parent consumer failed')
        return True

    with ThreadPoolExecutor(1) as outer:
        def execute():
            with scope(capacity=capacity, limit=2):
                with pytest.raises(ValueError):
                    fanout(2, 2, child, accept)
        outer.submit(execute).result(timeout=3)
    assert capacity.active == 0


def test_concurrent_roots_share_body_limit():
    capacity = Capacity(2)
    def execute(_):
        with scope(capacity=capacity):
            fanout(20, 8, lambda i: time.sleep(.001), lambda i, f: f.result() is None)
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(execute, range(3)))
    assert capacity.peak == 2
    assert capacity.active == 0


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
