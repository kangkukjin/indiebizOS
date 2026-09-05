r"""깨진 원장을 '없음'으로 눙치지 않는다 — 회귀 테스트 (2026-08-22)

ep1396 쓰기 경로 추적에서 파서의 침묵 절단을 고친 뒤, 같은 부류
("파일이 있는데 못 읽었다"를 "없다"로 만드는 자리)를 감사해 넷을 골랐다.
넷 다 보안 구멍은 아니다(빈 값은 권한을 좁히는 쪽 = fail-closed) —
진단 가능성 결함이다: 사용자와 AI 가 원인을 영영 못 본다.

    S1. workflow_engine.get_workflow    깨진 yaml → None(=없는 워크플로)
    S2. ibl_access.load_nodes_raw     깨진 어휘 → {} (낱말 151개가 전부 증발)
    S3. ibl_access._load_peer_agents    깨진 명부 → [] (동료가 사라져 위임 불가)
    S4. tool_loader.load_tool_schema    깨진 tool.json → None(=그런 도구 없음)
    S5. ibl_registry.load_nodes_installed  깨진 설치본 사전 → 안내 없는 생 예외 (2026-08-24 추가)

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
    import workflow_store as st         # 원장 경로의 정본(2026-09-05 분리) — 재수출 이름을 갈아끼우면 본체는 그대로다

    _orig = st._get_workflows_path      # ★전역을 갈아끼우면 반드시 되돌린다 —
    try:                                #   임시 폴더가 사라진 뒤 뒤 시험들이 그 자리를 본다
        _run_s1(wf, st, Path)
    finally:
        st._get_workflows_path = _orig


def _run_s1(wf, st, Path):
    with tempfile.TemporaryDirectory() as td:
        st._get_workflows_path = lambda: Path(td)          # noqa: E731
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

    _orig = ibl_access._get_nodes_path
    try:
        _run_s2(ibl_access)
    finally:
        ibl_access._get_nodes_path = _orig
        ibl_access._nodes_data_cache = None


def _run_s2(ibl_access):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ibl_nodes.yaml"
        p.write_text(BROKEN_YAML, encoding="utf-8")
        ibl_access._nodes_data_cache = None
        ibl_access._get_nodes_path = lambda: p             # noqa: E731
        try:
            ibl_access.load_nodes_raw()
        except RuntimeError as e:
            assert "어휘 원장" in str(e), str(e)
        else:
            raise AssertionError("깨진 어휘 파일이 조용히 {} 로 통과했다")
        finally:
            ibl_access._nodes_data_cache = None

        # 부재는 여전히 조용한 {}
        ibl_access._get_nodes_path = lambda: Path(td) / "없는파일.yaml"   # noqa: E731
        assert ibl_access.load_nodes_raw() == {}, "진짜 부재까지 시끄러워졌다"
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

    _o1, _o2 = tool_loader.get_tools_path, tool_loader.build_tool_package_map
    try:
        _run_s4(tool_loader)
    finally:
        tool_loader.get_tools_path = _o1
        tool_loader.build_tool_package_map = _o2


def _run_s4(tool_loader):
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


def test_s5_broken_installed_dictionary_raises():
    """S5(2026-08-24 추가): **설치본** 사전도 깨지면 시끄럽다.

    S2 는 원본 사전집(ibl_access.load_nodes_raw)만 덮었다. 같은 ibl_nodes.yaml 을 읽는
    두 번째 로더(ibl_registry.load_nodes_installed = 원본+api_registry 병합+몸-필터)는
    깨진 파일을 그대로 예외로 흘리되 재생성 안내가 없었다 — 실행 경로 전체가 이쪽을 쓴다.
    """
    import ibl_registry

    _orig_path, _orig_nodes = ibl_registry._nodes_path, ibl_registry._nodes
    try:
        _run_s5(ibl_registry)
    finally:
        ibl_registry._nodes_path, ibl_registry._nodes = _orig_path, _orig_nodes


def _run_s5(ibl_registry):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ibl_nodes.yaml"
        p.write_text(BROKEN_YAML, encoding="utf-8")
        ibl_registry._nodes, ibl_registry._nodes_path = None, p
        try:
            ibl_registry.load_nodes_installed()
        except RuntimeError as e:
            assert "어휘 원장" in str(e), str(e)
            assert "build_ibl_nodes" in str(e), "재생성 안내가 없다"
        else:
            raise AssertionError("깨진 설치본 사전이 조용히 {'nodes': {}} 로 통과했다")

        # 부재는 여전히 조용한 빈 사전
        ibl_registry._nodes = None
        ibl_registry._nodes_path = Path(td) / "없는파일.yaml"
        assert ibl_registry.load_nodes_installed() == {"nodes": {}}, "진짜 부재까지 시끄러워졌다"
        ibl_registry._nodes = None


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
