"""pytest 부트스트랩 — 층 디렉토리를 sys.path 에 (2026-08-05 ⑦ 물리 이동).

pytest 는 testpaths=backend 의 테스트 파일 곁(backend 루트)만 sys.path 에 넣는다.
층 디렉토리로 이사한 평면 모듈들을 테스트가 그대로 import 하도록 boot_paths 를 건다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

import pytest


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
