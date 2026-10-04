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
