"""회상은 같은 코드를 한 번만 보여준다 (2026-09-18) — 바꿔 말하기 행이 Top-K 를 독점하지 않는다."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__)); import boot_paths  # noqa
from types import SimpleNamespace as R
import ibl_usage_rag as rag


def _rows(*codes):
    return [R(id=i, ibl_code=c, score=1 - i / 100) for i, c in enumerate(codes)]


def test_same_code_collapses_to_best_scored_row():
    out = rag._distinct_codes(_rows('[a:b]{op: "x"}', '[a:b]{op:"x"}', '[c:d]', '[a:b]{op: "x"}'))
    assert [r.id for r in out] == [0, 2]


def test_funnel_widens_until_distinct_codes_fill(monkeypatch):
    pool = _rows(*(['[a:b]'] * 9 + ['[c:d]', '[e:f]', '[g:h]']))

    class DB:
        def search_hybrid(self, top_k=5, **kw):
            return pool[:top_k]

    monkeypatch.setattr(rag, "_principal_allows_recall", lambda: True)
    monkeypatch.setattr(rag, "_own_only", lambda rs: rs)
    out = rag._search_active(DB(), query="q", top_k=3)
    assert [r.ibl_code for r in out] == ['[a:b]', '[c:d]', '[e:f]']


if __name__ == '__main__':
    import sys, pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
