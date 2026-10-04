"""pytest 부트스트랩 — 층 디렉토리를 sys.path 에 (2026-08-05 ⑦ 물리 이동).

pytest 는 testpaths=backend 의 테스트 파일 곁(backend 루트)만 sys.path 에 넣는다.
층 디렉토리로 이사한 평면 모듈들을 테스트가 그대로 import 하도록 boot_paths 를 건다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def isolated_episode_store(tmp_path, monkeypatch):
    """모든 회귀의 기본 주행·코퍼스 저장소를 격리한다. 개별 DB 대역은 계속 허용한다."""
    import sqlite3
    import episode_logger

    # 테스트 대상 폴더의 파일 목록·산출물 수에 DB가 섞이지 않도록 형제 저장소에 둔다.
    path = tmp_path.parent / "_episode_stores" / (tmp_path.name + ".db")
    path.parent.mkdir(exist_ok=True)

    def connect():
        conn = sqlite3.connect(str(path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(episode_logger, "_get_db", connect)
    episode_logger._ensure_episode_tables()
    return path


def _tracked_modified(root):
    import subprocess
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return {line[3:].strip() for line in out.splitlines() if line.strip()}


def pytest_sessionstart(session):
    """추적 파일을 바꾸는 시험 관문(2026-10-04): 세션 전 git 상태를 기억한다. xdist 워커는 제외."""
    if hasattr(session.config, "workerinput"):
        return
    session.config._live_store_before = _tracked_modified(Path(__file__).resolve().parents[1])


def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput"):
        return
    before = getattr(session.config, "_live_store_before", None)
    if before is None:
        return
    after = _tracked_modified(Path(__file__).resolve().parents[1])
    if after is None:
        return
    new = sorted(after - before)
    if new:
        rep = session.config.pluginmanager.get_plugin("terminalreporter")
        msg = ("[live-store] 이 세션이 추적 파일을 바꿨다 — 시험이 실 저장소를 쓰거나, 라이브 몸이 그 사이 썼다. "
               "docs/REGRESSION_TESTING.md '시험의 실 저장소 쓰기': " + ", ".join(new))
        if rep is not None:
            rep.write_line(msg, red=True)
        else:
            print(msg)
        if exitstatus == 0:
            session.exitstatus = 1


@pytest.fixture(autouse=True)
def clean_turn_state():
    """턴 상태 위생(2026-10-04): 앞 시험이 스레드-로컬에 남긴 목표 평가 결과가 뒤 시험의 과제 결속을
    바꿨다(test_pursuit_connection — 단독 통과·전수 실패, 워커 배정이 바뀌자 드러남). 시험마다 비운다."""
    import thread_context
    thread_context.clear_goal_eval_outcome()
    yield
    thread_context.clear_goal_eval_outcome()


@pytest.fixture(autouse=True)
def isolated_runtime_stores(tmp_path, monkeypatch):
    """라이브 몸의 런타임 저장소를 시험마다 tmp_path 로(2026-10-04 쓰기 스윕 결과).
    실 data/ 에 1회 회귀가 남기던 것: ibl_runs 수십 디렉터리(총 957MB·7,160개), completion_wait 18,
    script_runs 65 + scripts.json, workflows 25, recall_index 5. 각 저장소의 루트 시임 하나를 바꾼다.
    새 런타임 저장소를 만들면 루트 함수를 두고 여기에 한 줄 더한다 — 스윕(INDIEBIZ_TEST_WRITE_SWEEP)이 샌 것을 찾는다."""
    import ibl_run_journal
    import workflow_store
    import script_workspace
    import repair_continuation
    import runtime_utils
    real_root = Path(__file__).resolve().parents[1]

    def follow(*sub):
        # 시험이 get_base_path 를 돌렸으면 그 아래 data/… (그 시험의 기대와 일치), 실 저장소를 가리키면 tmp.
        base = Path(runtime_utils.get_base_path()).resolve()
        return (base / "data").joinpath(*sub) if base != real_root else tmp_path.joinpath(*sub)
    monkeypatch.setattr(ibl_run_journal, "runs_root", lambda: follow("ibl_runs"))
    monkeypatch.setattr(repair_continuation, "state_root", lambda: follow("system_ai_state"))
    monkeypatch.setattr(workflow_store, "_get_workflows_path", lambda: _mk(follow("workflows")))
    from thread_context import get_repair_workspace

    def storage_root():
        # 원본과 같은 우선순위(수리 작업공간 > base) — 실 저장소를 가리킬 때만 tmp.
        ws = get_repair_workspace()
        return Path(ws) / "data" / "script_runs" / "transient" if ws else follow("script_runs", "transient")
    monkeypatch.setattr(script_workspace, "storage_root", storage_root)
    # 환경변수 시임은 시험 단위로 새 디렉터리(시험끼리 섞이지 않게) — 시험이 끝나면 monkeypatch 가
    # 세션(워커) 단위 값으로 되돌리므로, 늦게 쓰는 작업자 스레드도 실 저장소가 아니라 그리로 간다.
    monkeypatch.setenv("INDIEBIZ_RUNTIME_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("INDIEBIZ_RECALL_INDEX_DIR", str(tmp_path / "recall_index"))
    yield


def _mk(p):
    p.mkdir(parents=True, exist_ok=True)
    return p


def pytest_configure(config):
    """워커(프로세스) 단위 런타임 상태 루트(2026-10-04). 환경변수 시임은 시험 단위가 아니라 세션 단위다:
    ① 자식 프로세스(MCP 대기자·스크립트 러너)가 상속해야 하고 ② 시험이 띄운 작업자 스레드(회상 색인 동기화
    등)가 시험이 끝난 뒤에 써도 실 저장소가 아니라 여기로 와야 한다. 덮는 저장소: completion_wait·
    script 실행 원장·ibl_runs·write_ledger·system_ai_state(각 모듈의 루트 함수가 읽는다)·회상 색인."""
    import tempfile
    if os.environ.get("INDIEBIZ_RUNTIME_STATE_DIR_TEST_OWNED"):
        return
    root = tempfile.mkdtemp(prefix="indiebiz-test-state-")
    os.environ["INDIEBIZ_RUNTIME_STATE_DIR"] = root
    os.environ["INDIEBIZ_RECALL_INDEX_DIR"] = os.path.join(root, "recall_index")
    os.environ["INDIEBIZ_RUNTIME_STATE_DIR_TEST_OWNED"] = root


def pytest_unconfigure(config):
    import shutil
    root = os.environ.pop("INDIEBIZ_RUNTIME_STATE_DIR_TEST_OWNED", None)
    if root and os.environ.get("INDIEBIZ_RUNTIME_STATE_DIR") == root:
        os.environ.pop("INDIEBIZ_RUNTIME_STATE_DIR", None)
        os.environ.pop("INDIEBIZ_RECALL_INDEX_DIR", None)
        shutil.rmtree(root, ignore_errors=True)


# ── 상설 쓰기 스윕: INDIEBIZ_TEST_WRITE_SWEEP=<로그파일> 이면 저장소 트리로 향하는 쓰기를 nodeid 와 기록
_SWEEP_LOG = os.environ.get("INDIEBIZ_TEST_WRITE_SWEEP")
if _SWEEP_LOG:
    import builtins as _builtins
    import io as _io
    _SWEEP_ROOT = Path(__file__).resolve().parents[1]
    _SWEEP_SKIP = (".venv", "__pycache__", ".pytest_cache", "node_modules", ".git", ".hypothesis")
    _sweep_current = {"id": "<no test>"}

    def _sweep_hit(kind, p):
        try:
            rp = Path(p).resolve()
            rel = rp.relative_to(_SWEEP_ROOT)
        except (OSError, ValueError, TypeError):
            return
        if any(part in _SWEEP_SKIP for part in rel.parts):
            return
        with open(_SWEEP_LOG, "a", opener=lambda f, fl: os.open(f, fl)) as f:
            f.write(f"{_sweep_current['id']}\t{kind}\t{rel}\n")

    _orig_open, _orig_replace, _orig_rename = _builtins.open, os.replace, os.rename

    def _sweep_open(file, mode="r", *a, **k):
        if isinstance(file, (str, os.PathLike)) and any(c in str(mode) for c in "wax+"):
            _sweep_hit("open", file)
        return _orig_open(file, mode, *a, **k)

    def _sweep_replace(src, dst, *a, **k):
        _sweep_hit("replace", dst)
        return _orig_replace(src, dst, *a, **k)

    def _sweep_rename(src, dst, *a, **k):
        _sweep_hit("rename", dst)
        return _orig_rename(src, dst, *a, **k)

    _builtins.open = _sweep_open
    _io.open = _sweep_open
    os.replace = _sweep_replace
    os.rename = _sweep_rename

    @pytest.fixture(autouse=True)
    def _sweep_track(request):
        _sweep_current["id"] = request.node.nodeid
        yield
        _sweep_current["id"] = "<between tests>"


@pytest.fixture(autouse=True)
def isolated_spill_root(tmp_path, monkeypatch):
    """스필(data/spill) 을 시험마다 tmp_path 로. 2026-10-04 실측: 기본 회귀 1회가 실 data/spill 에
    1,659 경로·46MB 를 남겼고(총 112K 파일·9.8GB 의 최근분 대부분이 시험 산물), 티켓·감독 증거가
    라이브 몸의 것과 섞였다. 시임은 common.spill._root 하나 — 직접 경로를 짓는 코드가 다시
    생기면 이 격리가 새므로, 새 스필 소비자는 spill_dir() 을 쓴다.
    ContextVar(_spill_root) 가 아니라 모듈 함수를 바꾸는 이유: 티켓 마무리 같은 작업자 스레드는
    ContextVar 를 물려받지 않아(T10 실측) 실 스필에 쓰고 시험은 tmp 를 읽는 반쪽 격리가 된다."""
    from common import spill
    import runtime_utils
    real_root = Path(__file__).resolve().parents[1]
    fallback = str(tmp_path / "spill")

    def _test_root():
        if spill._spill_root.get() is not None:          # 회원 몸의 사설 스필(member_runtime) 은 그대로
            return spill._spill_root.get()
        base = Path(runtime_utils.get_base_path()).resolve()   # 호출 시점 조회 — 시험의 monkeypatch 를 본다
        if base != real_root:                             # 시험이 base_path 를 돌렸으면 그 아래 data/spill
            return str(base / "data" / "spill")
        return fallback                                   # 실 저장소를 가리키면 tmp 로
    monkeypatch.setattr(spill, "_root", _test_root)
    yield


@pytest.fixture
def isolated_distill_training(tmp_path, monkeypatch):
    """증류의 임시 파일→replace 저장도 운영 학습 자료 밖에서 검증한다."""
    from pathlib import Path
    import ibl_usage_rag as rag
    import ibl_idiom

    root = tmp_path / 'distill_workspace'
    prompt = Path(rag.__file__).resolve().parents[2] / 'data/common_prompts/reflection_prompt.md'
    target = root / 'data/common_prompts/reflection_prompt.md'
    target.parent.mkdir(parents=True)
    target.write_bytes(prompt.read_bytes())
    training = root / 'data/training/ibl_distilled.json'
    training.parent.mkdir(parents=True)
    monkeypatch.setattr(rag, '__file__', str(root / 'backend/cognition/ibl_usage_rag.py'))
    monkeypatch.setattr(ibl_idiom, '__file__', str(root / 'backend/cognition/ibl_idiom.py'))
    return training
