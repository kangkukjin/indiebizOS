"""프로바이더 토큰 원장 관문 (2026-09-06) — 부류 수리는 손이 아니라 관문이 닫는다.

★사고: 09-06 원장 감사에서 프로바이더마다 다른 모양의 사각지대가 나왔다 — claude_code 는
캐시를 안 넘기고, codex 는 출력을 스레드 누적 그대로, gemini·ollama 는 벤더 usage 를 안 읽고
글자수÷4 로 추정(입력 0), gemini_http 는 기록 자체가 없었다. 셋을 손으로 고친 뒤 사용자:
"거론하지 않은 다른 프로바이더들은 어떻게 해?" — 그래서 규약을 base.normalize_usage 한 곳에
두고, 이 관문이 (1) 초크포인트 우회 (2) 추정치 (3) 미기록 프로바이더 (4) 벤더별 정규화 값을 잠근다.
새 프로바이더는 record_usage 를 부르지 않으면 여기서 빨갛게 된다 — 손 목록 없음.

실행: .venv/bin/python -m pytest backend/test_provider_usage_ledger_gate.py -q
"""
import ast
import re
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401

PROV = Path(__file__).resolve().parent / "providers"
MODULES = sorted(p for p in PROV.glob("*.py") if p.name not in ("__init__.py", "base.py"))


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _calls(tree: ast.AST, attr: str):
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == attr]


# ── (1) 초크포인트 우회 금지 ──

def test_no_direct_record_request_outside_base():
    bad = [f"{p.name}:{c.lineno}" for p in MODULES for c in _calls(_tree(p), "record_request")]
    assert not bad, "record_request 직접 호출(규약이 흩어진다 — record_usage 로):\n  " + "\n  ".join(bad)


# ── (2) 추정치 금지 ──

def test_no_char_count_token_estimates():
    pat = re.compile(r"estimated_(?:output|input)_tokens|토큰 수를 직접 제공하지 않으므로 추정")
    bad = [f"{p.name}:{i}" for p in MODULES
           for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if pat.search(line)]
    assert not bad, "글자수 추정 토큰(미측정은 None 이지 추정이 아니다):\n  " + "\n  ".join(bad)


# ── (3) 구체 프로바이더는 반드시 초크포인트를 부른다 (손 목록 없이: 상속 그래프로 판정) ──

def _provider_classes():
    """{모듈: [(클래스명, [베이스명])]} — providers 패키지 안의 클래스 전부."""
    out = {}
    for p in MODULES:
        cls = [(n.name, [b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in n.bases])
               for n in ast.walk(_tree(p)) if isinstance(n, ast.ClassDef)]
        out[p] = cls
    return out


def test_every_concrete_provider_records_usage():
    classes = _provider_classes()
    all_bases = {b for cl in classes.values() for _, bases in cl for b in bases}
    bad = []
    for p, cl in classes.items():
        src = p.read_text(encoding="utf-8")
        for name, bases in cl:
            if not any(b.endswith("Provider") for b in bases):
                continue                      # 프로바이더 계보가 아닌 보조 클래스(세션 저장소 등)
            defines_stream = re.search(r"def process_message_stream\(|def _translate_stream_event\(", src)
            if not defines_stream:
                continue                      # 부모의 스트림을 그대로 쓰는 얇은 상속(DeepSeek·OpenRouter)
            if name in all_bases and "record_usage(" not in src:
                continue                      # 가족 베이스(cli_provider) — 어댑터 자식이 기록한다
            if "record_usage(" not in src:
                bad.append(f"{p.name}:{name}")
    assert not bad, "벤더 usage 를 원장에 안 적는 프로바이더(미측정이 아니라 침묵):\n  " + "\n  ".join(bad)
    # 가족 베이스의 자식은 각자 기록해야 한다 — 베이스가 면제된 만큼 자식이 잠긴다
    for p, cl in classes.items():
        src = p.read_text(encoding="utf-8")
        for name, bases in cl:
            if "CliSubprocessProvider" in bases:
                assert "record_usage(" in src, f"{p.name}:{name} — CLI 어댑터가 usage 를 안 적는다"


# ── (4) 벤더별 정규화 값 — 실제 페이로드 모양 그대로 ──

def _norm(u):
    from providers.base import normalize_usage
    return normalize_usage(u)


def test_anthropic_sdk_shape_adds_cache_to_input():
    u = SimpleNamespace(input_tokens=118, output_tokens=54_112,
                        cache_read_input_tokens=17_253_163, cache_creation_input_tokens=342_784)
    assert _norm(u) == {"input": 118 + 17_253_163 + 342_784, "output": 54_112,
                        "cache_read": 17_253_163, "cache_create": 342_784}


def test_claude_code_result_dict_shape():
    u = {"input_tokens": 4, "output_tokens": 3635, "cache_read_input_tokens": 370_376,
         "cache_creation_input_tokens": 342_347}
    n = _norm(u)
    assert n["input"] == 4 + 370_376 + 342_347 and n["cache_read"] == 370_376


def test_codex_exec_shape_input_already_includes_cached():
    u = {"input_tokens": 19_554, "output_tokens": 5, "cached_input_tokens": 11_008, "cache_write_input_tokens": 0}
    assert _norm(u) == {"input": 19_554, "output": 5, "cache_read": 11_008, "cache_create": 0}


def test_openai_sdk_shape_with_details():
    u = SimpleNamespace(prompt_tokens=63_226, completion_tokens=329,
                        prompt_tokens_details=SimpleNamespace(cached_tokens=62_720))
    assert _norm(u) == {"input": 63_226, "output": 329, "cache_read": 62_720, "cache_create": 0}


def test_deepseek_dict_shape_top_level_hit():
    u = {"prompt_tokens": 51_193, "completion_tokens": 71, "prompt_cache_hit_tokens": 128}
    assert _norm(u)["cache_read"] == 128 and _norm(u)["input"] == 51_193


def test_gemini_sdk_shape_thoughts_count_as_output():
    u = SimpleNamespace(prompt_token_count=12_000, candidates_token_count=800, thoughts_token_count=1_500,
                        cached_content_token_count=9_000, total_token_count=14_300)
    assert _norm(u) == {"input": 12_000, "output": 2_300, "cache_read": 9_000, "cache_create": 0}


def test_gemini_rest_camel_shape():
    u = {"promptTokenCount": 3_000, "candidatesTokenCount": 120, "cachedContentTokenCount": 0}
    assert _norm(u) == {"input": 3_000, "output": 120, "cache_read": 0, "cache_create": 0}


def test_ollama_native_shape():
    assert _norm({"prompt_eval_count": 2_048, "eval_count": 96}) == {
        "input": 2_048, "output": 96, "cache_read": 0, "cache_create": 0}


def test_unrecognized_or_missing_is_none_not_zero():
    assert _norm(None) is None and _norm({"total_tokens": 11_653}) is None


def test_cache_read_never_exceeds_input():
    assert _norm({"prompt_tokens": 100, "completion_tokens": 1, "prompt_cache_hit_tokens": 500})["cache_read"] == 100


# ── (5) 초크포인트 → 턴 원장 ──

def test_record_usage_feeds_turn_ledger_and_none_stays_unmeasured():
    from providers.base import (ProviderMetrics, begin_turn_token_ledger, read_turn_tokens,
                                read_turn_cache_read_tokens)
    begin_turn_token_ledger()
    m = ProviderMetrics()
    assert m.record_usage(10.0, None, label="") is None
    assert read_turn_tokens() is None                      # 미측정 = None (0 오보 금지)
    m.record_usage(10.0, {"prompt_tokens": 1_000, "completion_tokens": 20, "prompt_cache_hit_tokens": 900})
    m.record_usage(10.0, {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 90})
    assert read_turn_tokens() == 1_000 + 20 + 100 + 5
    assert read_turn_cache_read_tokens() == 990
    assert m.total_requests == 3


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
