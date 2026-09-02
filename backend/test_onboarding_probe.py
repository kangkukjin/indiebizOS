r"""실응답 검증 — 실패가 원인별로 다른 문장으로 돌아온다 (2026-09-02, 첫 성공 온보딩 ① C)

"API 키가 설정되지 않았습니다" 하나로 뭉개지면 사용자는 키가 틀린 건지 모델명이 틀린 건지
CLI 로그인이 안 된 건지 영영 모른다. 가짜 프로바이더로 실패 4종을 재현해 kind 가 갈리는지 본다.

    T1. 키 필요 프로바이더에 키 없음 → no_key (프로바이더를 만들기도 전에)
    T2. 401 예외 → auth · 404 예외 → model · "Not logged in" → cli_login · 연결 거부(local) → local_down
    T3. init_client False → kind 별 기본 범주(cli_missing / local_down)
    T4. 성공 → ok, reply, latency_ms
    T5. 빈 응답 → empty (성공으로 눙치지 않는다)
    T6. 무키 프로바이더(claude_code)는 키 없이 프로바이더 생성까지 간다

실행: python3 -m pytest backend/test_onboarding_probe.py
"""
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

import ai_candidates as ac


class Fake:
    def __init__(self, *, init_ok=True, raise_text=None, reply="준비됨"):
        self._init_ok = init_ok
        self._raise = raise_text
        self._reply = reply

    def init_client(self):
        return self._init_ok

    def process_message(self, message, history, execute_tool=None, **_):
        if self._raise:
            raise RuntimeError(self._raise)
        return self._reply


def _mk(fake):
    return lambda provider, key, model: fake


def test_t1_missing_key_before_provider(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = ac.probe("anthropic", "claude-x", "", make_provider=_mk(Fake()))
    assert out["ok"] is False and out["kind"] == "no_key"
    assert "ANTHROPIC_API_KEY" in out["message"]


def test_t2_failure_kinds_are_distinct():
    out = ac.probe("anthropic", "m", "sk-x", make_provider=_mk(Fake(raise_text="401 Unauthorized: invalid x-api-key")))
    assert out["kind"] == "auth"
    out = ac.probe("anthropic", "m", "sk-x", make_provider=_mk(Fake(raise_text="404 model not found")))
    assert out["kind"] == "model"
    out = ac.probe("claude_code", "sonnet", "", make_provider=_mk(Fake(raise_text="Not logged in. Please run /login")))
    assert out["kind"] == "cli_login"
    out = ac.probe("ollama", "llama3", "", make_provider=_mk(Fake(raise_text="Connection refused localhost:11434")))
    assert out["kind"] == "local_down"
    kinds = {"auth", "model", "cli_login", "local_down"}
    assert len({ac._KIND_MESSAGES[k] for k in kinds}) == 4   # 문장도 서로 다르다


def test_t3_init_client_false_defaults_by_kind():
    assert ac.probe("claude_code", "sonnet", "", make_provider=_mk(Fake(init_ok=False)))["kind"] == "cli_missing"
    assert ac.probe("ollama", "llama3", "", make_provider=_mk(Fake(init_ok=False)))["kind"] == "local_down"


def test_t4_success_carries_reply_and_latency():
    out = ac.probe("codex", "gpt-x", "", make_provider=_mk(Fake(reply="준비됨")))
    assert out["ok"] is True and out["reply"] == "준비됨" and isinstance(out["latency_ms"], int)


def test_t5_empty_reply_is_not_success():
    out = ac.probe("codex", "gpt-x", "", make_provider=_mk(Fake(reply="")))
    assert out["ok"] is False and out["kind"] == "empty"


def test_t6_no_key_provider_reaches_provider_without_key():
    out = ac.probe("claude_code", "sonnet", "", make_provider=_mk(Fake(reply="ok")))
    assert out["ok"] is True


if __name__ == "__main__":
    # 직접 실행도 pytest 로 위임 — 두 번째 러너는 드리프트한다(test_single_runner R2)
    import pytest as _pytest
    sys.exit(_pytest.main([__file__]))
