r"""깨진 원장을 '없음'으로 눙치지 않는다 — 회귀 테스트 (2026-08-22)

ep1396 쓰기 경로 추적에서 파서의 침묵 절단을 고친 뒤, 같은 부류
("파일이 있는데 못 읽었다"를 "없다"로 만드는 자리)를 감사해 넷을 골랐다.
넷 다 보안 구멍은 아니다(빈 값은 권한을 좁히는 쪽 = fail-closed) —
진단 가능성 결함이다: 사용자와 AI 가 원인을 영영 못 본다.

    S1. workflow_engine.get_workflow    깨진 yaml → None(=없는 워크플로)
    S2. ibl_access._load_nodes_data     깨진 어휘 → {} (낱말 151개가 전부 증발)
    S3. ibl_access._load_peer_agents    깨진 명부 → [] (동료가 사라져 위임 불가)
    S4. tool_loader.load_tool_schema    깨진 tool.json → None(=그런 도구 없음)

각 시험은 **진짜 없는 경우와 구별되는가**를 함께 확인한다 — 부재는 여전히
조용한 None/[] 여야 한다(그건 정상이니까).

실행: python3 backend/test_corrupt_not_absent.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401 — 층 디렉토리 등재

BROKEN_YAML = "steps: [\n  - unclosed: 'quote\n"   # yaml 파서가 확실히 죽는 모양
BROKEN_JSON = '{"tools": [ {"name": '


def test_s1_broken_workflow_is_not_missing():
    """S1: 깨진 워크플로 파일은 '없음'이 아니라 problem 을 달고 온다."""
    import workflow_engine as wf

    with tempfile.TemporaryDirectory() as td:
        wf._get_workflows_path = lambda: Path(td)          # noqa: E731
        (Path(td) / "broken.yaml").write_text(BROKEN_YAML, encoding="utf-8")

        got = wf.get_workflow("broken")
        assert got is not None, "깨진 파일이 None(=없음)으로 눙쳐졌다"
        assert got.get("problem"), "problem 이 없다: %r" % got
        assert got.get("runnable") is False, "runnable 표식이 없다: %r" % got

        # 부재는 여전히 조용한 None 이어야 한다
        assert wf.get_workflow("정말없는것") is None, "진짜 부재까지 시끄러워졌다"

        # 실행 경로가 problem 을 삼키지 않고 표면화하는가
        res = wf.run_workflow("broken") if hasattr(wf, "run_workflow") else None
        if isinstance(res, dict):
            assert res.get("success") is False
            assert "읽을 수 없" in str(res.get("error", "")), res


def test_s2_broken_vocabulary_raises():
    """S2: 깨진 어휘 원장은 {} 가 아니라 오류 — 몸이 조용히 사라지면 안 된다."""
    import ibl_access

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ibl_nodes.yaml"
        p.write_text(BROKEN_YAML, encoding="utf-8")
        ibl_access._nodes_data_cache = None
        ibl_access._get_nodes_path = lambda: p             # noqa: E731
        try:
            ibl_access._load_nodes_data()
        except RuntimeError as e:
            assert "어휘 원장" in str(e), str(e)
        else:
            raise AssertionError("깨진 어휘 파일이 조용히 {} 로 통과했다")
        finally:
            ibl_access._nodes_data_cache = None

        # 부재는 여전히 조용한 {}
        ibl_access._get_nodes_path = lambda: Path(td) / "없는파일.yaml"   # noqa: E731
        assert ibl_access._load_nodes_data() == {}, "진짜 부재까지 시끄러워졌다"
        ibl_access._nodes_data_cache = None


def test_s3_broken_peer_roster_raises():
    """S3: 깨진 동료 명부는 [] 가 아니라 오류."""
    import ibl_access

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "agents.yaml").write_text(BROKEN_YAML, encoding="utf-8")
        try:
            ibl_access._load_peer_agents(td, "나")
        except RuntimeError as e:
            assert "동료 명부" in str(e), str(e)
        else:
            raise AssertionError("깨진 명부가 조용히 [] 로 통과했다")

    with tempfile.TemporaryDirectory() as td2:   # agents.yaml 자체가 없는 프로젝트
        assert ibl_access._load_peer_agents(td2, "나") == [], "진짜 부재까지 시끄러워졌다"


def test_s4_broken_tool_json_raises():
    """S4: 깨진 tool.json 은 None(=그런 도구 없음)이 아니라 오류."""
    import tool_loader

    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "가짜패키지"
        pkg.mkdir()
        (pkg / "tool.json").write_text(BROKEN_JSON, encoding="utf-8")
        tool_loader.get_tools_path = lambda: Path(td)                       # noqa: E731
        tool_loader.build_tool_package_map = lambda: {"가짜도구": "가짜패키지"}  # noqa: E731
        try:
            tool_loader.load_tool_schema("가짜도구")
        except RuntimeError as e:
            assert "도구 정의" in str(e), str(e)
        else:
            raise AssertionError("깨진 tool.json 이 조용히 None 으로 통과했다")

        # 파일은 멀쩡한데 이름이 없다 = 진짜 없음(조용한 None)
        (pkg / "tool.json").write_text('{"tools": [{"name": "다른도구"}]}', encoding="utf-8")
        assert tool_loader.load_tool_schema("가짜도구") is None, "진짜 부재까지 시끄러워졌다"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for fn in fns:
        try:
            fn()
            print("  ✓ %s" % fn.__name__)
        except Exception as e:
            fails += 1
            print("  ✗ %s — %s" % (fn.__name__, e))
    print("\n%d/%d 통과" % (len(fns) - fails, len(fns)))
    sys.exit(1 if fails else 0)
