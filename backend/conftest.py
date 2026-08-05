"""pytest 부트스트랩 — 층 디렉토리를 sys.path 에 (2026-08-05 ⑦ 물리 이동).

pytest 는 testpaths=backend 의 테스트 파일 곁(backend 루트)만 sys.path 에 넣는다.
층 디렉토리로 이사한 평면 모듈들을 테스트가 그대로 import 하도록 boot_paths 를 건다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401
