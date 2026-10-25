"""Current input abstraction preserves the existing reusable-function privacy check."""
import inspect
import boot_paths  # noqa: F401


def test_input_function_finalization_checks_private_names():
    from ibl_v2_experience import finalize_candidate
    assert '_phrase_private_reason(code)' in inspect.getsource(finalize_candidate)


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
