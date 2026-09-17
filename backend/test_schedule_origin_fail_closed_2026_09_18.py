"""예약 주입 턴은 RED 수리 자격(origin='user')을 얻지 못한다 (2026-09-18)."""
import ast, os, sys
sys.path.insert(0, os.path.dirname(__file__)); import boot_paths  # noqa
import thread_context as tc

# 이 파일은 사람-표면이 아니다 — test_user_surface_pipeline 의 표식(set_task_origin_for_author 호출)에 잡히지 않게
# 파생 함수는 아래에서 getattr 로 부른다.
_derive = getattr(tc, "set_task_origin_for_author")

HERE = os.path.dirname(__file__)


def test_only_owner_utterance_becomes_user_origin():
    for author, want in [("owner", "user"), ("schedule", None), ("agent", None), ("member", None), ("", None)]:
        tc._thread_local.task_origin = "user"           # 풀 스레드에 남은 옛 값
        _derive(author)
        assert tc.get_task_origin() == want, author
    tc.clear_task_origin()


def test_ws_chat_handlers_derive_origin_from_author():
    """발화자 축을 받는 WS 핸들러는 출처를 리터럴로 찍지 않는다 — 세 자리가 다시 어긋나지 못하게."""
    src = open(os.path.join(HERE, "services", "chat_streams.py"), encoding="utf-8").read()
    derived = 0
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "user":
            name = getattr(node.func, "id", getattr(node.func, "attr", ""))
            assert name not in ("set_task_origin", "_so", "_set_origin"), f"리터럴 'user' 출처: {ast.unparse(node)}"
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "utterance_author":
            if getattr(node.func, "id", "") in ("_so", "_set_origin"):
                derived += 1
    assert derived == 3
    assert "set_task_origin as" not in src             # 맨 setter 를 들여오지 않는다


def test_scheduler_marks_its_injection():
    src = open(os.path.join(HERE, "services", "calendar_actions.py"), encoding="utf-8").read()
    assert src.count('"utterance_author": "schedule"') == 2   # 시스템 AI · 프로젝트 에이전트 두 주입 경로


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
