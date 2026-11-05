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


def test_reentry_adopts_only_live_identity_and_restores_after_exception(tmp_path):
    runner = SimpleNamespace(project_path=tmp_path, config={"id": "owner"},
                             ai=SimpleNamespace(_provider=SimpleNamespace(agent_id="alias")))
    with tc.actor_context(agent_id="owner", task_id="execution"):
        token = turns.enter(runner)
        original = turns.current()
        try:
            def reenter():
                assert turns.current() is None
                with pytest.raises(RuntimeError, match="tool failed"):
                    with turns.adopt_session("alias", "execution") as binding:
                        assert binding is original and turns.current() is original
                        binding.followup_reason = "shared with original execution"
                        for agent, task in [(None, "execution"), ("owner", None),
                                            ("other", "execution"), ("owner", "other")]:
                            with turns.adopt_session(agent, task):
                                assert turns.current() is None
                            assert turns.current() is original
                        raise RuntimeError("tool failed")
                assert turns.current() is None
            with ThreadPoolExecutor(1) as pool:
                pool.submit(reenter).result()
            assert original.followup_reason == "shared with original execution"
            copied = contextvars.copy_context()
        finally:
            turns.leave(token)

        def expired():
            assert turns.current() is original  # copied context is not proof of liveness
            with turns.adopt_session("owner", "execution"):
                assert turns.current() is None
        copied.run(expired)


def test_reentry_does_not_borrow_another_principals_turn(tmp_path):
    import principal
    runner = SimpleNamespace(project_path=tmp_path, config={"id": "owner"}, ai=None)
    with tc.actor_context(agent_id="owner", task_id="execution"):
        token = turns.enter(runner)
        original = turns.current()
        try:
            with principal.narrow(principal.Principal(kind="member", id="other")):
                with turns.adopt_session("owner", "execution"):
                    assert turns.current() is None
                assert turns.current() is original
        finally:
            turns.leave(token)


if __name__ == "__main__":
    import pytest
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
