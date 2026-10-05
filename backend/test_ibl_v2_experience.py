"""Reference-backed learning survives input-evidence identity revisions."""
import boot_paths  # noqa: F401
import copy

import pytest

from test_ibl_general_capabilities import boundary  # noqa: F401
from test_episode4182_repairs import reference_call


@pytest.mark.parametrize('nested', [False, True])
@pytest.mark.parametrize('legacy', [False, True])
def test_learning_accepts_matching_historical_and_certified_notes(boundary, tmp_path, nested, legacy):
    from ibl_v2_experience import closed_call
    from model_result_view import resolve_input_refs

    original, _ = reference_call(boundary, tmp_path, nested=nested)
    if legacy:
        _, notes = resolve_input_refs(original['input']['inputs'], store=boundary,
                                      legacy_fingerprints=True)
        original['result']['inputs_resolved'] = notes
    before = copy.deepcopy(original)
    assert closed_call(original), original.get('reuse_excluded')
    assert original == before


def test_learning_cannot_relabel_a_certified_fingerprint_as_historical(boundary, tmp_path):
    from ibl_v2_experience import closed_call

    original, _ = reference_call(boundary, tmp_path)
    original['result']['inputs_resolved'][0]['evidence'].pop('fingerprint_scheme')
    assert closed_call(original) is None
    assert original['reuse_excluded']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
