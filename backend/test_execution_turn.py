"""과제 없이 실행 신원·세션·MCP 재진입을 보존한다."""
import contextvars
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest
import boot_paths  # noqa: F401
import execution_turn as turns
import thread_context as tc


def test_registration_has_no_semantic_storage_and_rejects_expired_context(tmp_path):
    runner = SimpleNamespace(project_path=tmp_path, config={"id": "owner"},
                             ai=SimpleNamespace(_provider=SimpleNamespace(agent_id="alias")))
    with tc.actor_context(agent_id="owner", task_id="execution"):
        token = turns.enter(runner)
        copied = contextvars.copy_context()
        try:
            with ThreadPoolExecutor(1) as pool:
                binding = pool.submit(turns.resolve_session, "alias", "execution").result()
            assert binding.runner is runner
            assert not list(tmp_path.iterdir())
            for agent, task in [("other", "execution"), ("owner", None), ("owner", "wrong")]:
                with pytest.raises(ValueError):
                    turns.resolve_session(agent, task)
            with pytest.raises(ValueError, match="이미 실행"):
                turns.enter(runner)
        finally:
            turns.leave(token)
        assert turns.current() is None
        with pytest.raises(ValueError):
            copied.run(turns.resolve_session, "owner", "execution")


def test_nested_distinct_executions_restore_outer_context(tmp_path):
    runner = SimpleNamespace(project_path=tmp_path, config={"id": "owner"}, ai=None)
    with tc.actor_context(agent_id="owner", task_id="outer"):
        outer = turns.enter(runner)
        try:
            with tc.actor_context(agent_id="owner", task_id="inner"):
                inner = turns.enter(runner)
                try:
                    assert turns.resolve_session("owner", "outer").task == "outer"
                    assert turns.current().task == "inner"
                finally:
                    turns.leave(inner)
            assert turns.current().task == "outer"
        finally:
            turns.leave(outer)


if __name__ == "__main__":
    import pytest
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
