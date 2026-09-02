r"""AI 후보 탐지 — 이 기계가 이미 가진 것을 세 원천에서 찾는다 (2026-09-02, 첫 성공 온보딩 ① B)

    T1. 환경변수에 카탈로그의 키가 차 있으면 그 프로바이더가 후보(source=env:VAR)
    T2. CLI 실행 파일이 있으면 후보 — 로그인 흔적 파일이 있으면 login=yes, 없으면 unknown(맥 키체인)
    T3. 로컬 서버 /api/tags 가 응답하면 모델마다 후보, 서버가 죽어 있으면 후보 0 이고 예외 아님
    T4. 원천이 전부 비면 빈 목록 (오류 아님)
    T5. model_resolver.env_var_for_provider 가 카탈로그를 정본으로 쓴다(코드 표는 바닥)
    T6. 카탈로그가 깨지면 '없음'이 아니라 예외(corrupt ≠ absent)

실행: python3 -m pytest backend/test_onboarding_candidates.py
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

import ai_candidates as ac


def _no_which(_cmd):
    return None


def _no_fetch(_url, _t):
    raise ConnectionRefusedError("refused")


def _none_exist(_p):
    return False


def _no_glob(_pattern):
    return []


BASE = dict(which=_no_which, fetch_json=_no_fetch, exists=_none_exist, glob_fn=_no_glob)


def test_t1_env_key_makes_candidate():
    items = ac.detect_candidates(env={"GEMINI_API_KEY": "abc"}, **BASE)
    assert [i["provider"] for i in items] == ["google"]
    assert items[0]["source"] == "env:GEMINI_API_KEY" and items[0]["needs_key"] is False


def test_t2_cli_present_with_and_without_login_marker():
    which = lambda cmd: "fake-bin/claude" if cmd == "claude" else None   # noqa: E731
    items = ac.detect_candidates(env={}, which=which, fetch_json=_no_fetch, exists=_none_exist, glob_fn=_no_glob)
    assert [i["provider"] for i in items] == ["claude_code"]
    assert items[0]["login"] == "unknown" and items[0]["source"].startswith("cli:")
    items = ac.detect_candidates(env={}, which=which, fetch_json=_no_fetch,
                                 exists=lambda p: p.endswith(".credentials.json"), glob_fn=_no_glob)
    assert items[0]["login"] == "yes"


def test_t3_local_server_models_and_down():
    fetch = lambda url, t: {"models": [{"name": "llama3:8b"}, {"name": "qwen3:4b"}]}   # noqa: E731
    items = ac.detect_candidates(env={}, which=_no_which, fetch_json=fetch, exists=_none_exist, glob_fn=_no_glob)
    assert [(i["provider"], i["model"]) for i in items] == [("ollama", "llama3:8b"), ("ollama", "qwen3:4b")]
    items = ac.detect_candidates(env={}, **BASE)
    assert items == []


def test_t4_nothing_found_is_empty_not_error():
    assert ac.detect_candidates(env={}, **BASE) == []


def test_t5_resolver_env_map_comes_from_catalog():
    from model_resolver import env_var_for_provider
    assert env_var_for_provider("gemini") == "GEMINI_API_KEY"
    assert env_var_for_provider("google") == "GEMINI_API_KEY"
    assert env_var_for_provider("claude_code") == ""      # 무키 프로바이더
    assert ac.catalog_env_map()["deepseek"] == "DEEPSEEK_API_KEY"


def test_t6_corrupt_catalog_raises(tmp_path, monkeypatch):
    bad = tmp_path / "ai_provider_catalog.yaml"
    bad.write_text("providers: {not: a list}\n", encoding="utf-8")
    monkeypatch.setattr(ac, "catalog_path", lambda: bad)
    ac._catalog_cache.update(mtime=None, data=None)
    with pytest.raises(ValueError):
        ac.load_catalog()
    ac._catalog_cache.update(mtime=None, data=None)


if __name__ == "__main__":
    # 직접 실행도 pytest 로 위임 — 두 번째 러너는 드리프트한다(test_single_runner R2)
    import pytest as _pytest
    sys.exit(_pytest.main([__file__]))
