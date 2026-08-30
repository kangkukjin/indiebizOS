"""test_secret_masking.py — 디스크에 영속되는 로그의 자격증명 마스킹 관문.

★왜 이 파일이 있나 (2026-08-30, ep2426 실측):
에피소드 로그에 Vercel 개인 토큰 값이 60자 그대로 박제됐다. 경위는 `key=value` 도
벤더 접두도 아니었다 — `echo "token set: ${VERCEL_TOKEN:+yes}${VERCEL_TOKEN:-no}"`.
`:-` 는 변수가 **있을 때 값을 내놓는다.** 이 관문은 "그 문장"이 아니라 그 **부류**를
지킨다: 자격증명 낱말 근처의 고엔트로피 덩어리는 문장 모양과 무관하게 가려져야 한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "base"))

from logging_utils import mask_secrets  # noqa: E402


def _assert_masked(text, secret, label):
    out = mask_secrets(text)
    assert secret not in out, f"[{label}] 값이 새어나감: {out!r}"
    return out


def test_shell_default_idiom_leak():
    """ep2426 실측 회귀: `${VAR:+yes}${VAR:-no}` 가 값을 뱉은 자리."""
    secret = "vcp_" + "a9F3k2Lq7X" * 5 + "b1C4"          # 접두 있는 60자
    _assert_masked(f'token set: yes{secret} --- /path/.env', secret, "shell :- 관용구")


def test_prefixless_credential_near_name():
    """벤더 접두가 없어도 이름 옆의 고엔트로피 덩어리는 가려져야 한다.

    (접두 목록만으로 막으면 다음 벤더에서 또 샌다 = 손으로 고른 스윕.)"""
    secret = "7Kq2Xa9Lf3Nd8Rb1Ty6Zv4Mw0Ph5Jc"           # 접두 없는 30자
    _assert_masked(f'token set: yes{secret}', secret, "접두 없는 토큰")
    _assert_masked(f'API_KEY -> {secret}', secret, "화살표 표기")
    _assert_masked(f'"secret": [{secret}]', secret, "괄호 표기")


def test_vendor_prefixes():
    for secret in (
        "vcp_" + "x7Q2m9Lk4Rt8" * 3,
        "npm_" + "aB3xY7zQ1w" * 4,
        "hf_" + "kQ9x2Lm7Vt4Bz1Nc8Rd5Wy3Ah6Ge0Jf",
        "glpat-" + "x9Km2Qw7Lz4Rt8Bn",
        "sk_live_" + "9xQm2Lk7Rt4Bz8Nc1Vd5",
    ):
        _assert_masked(f"배포 명령: --token={secret} 실행", secret, secret[:6])


def test_existing_rules_still_hold():
    for secret in (
        "AIza" + "B3xY7zQ1wK9m2Lt4Rn8Vc5Ha6Jd0Gf7Psxy",   # 접두 뒤 35자
        "sk-" + "aB3xY7zQ1wK9m2Lt4Rn8",
        "ghp_" + "aB3xY7zQ1wK9m2Lt4Rn8Vc5Ha6Jd0",
    ):
        _assert_masked(f"key: {secret}", secret, secret[:4])
    out = mask_secrets('{"apiKey": "s3cretValue123456"}')
    assert "s3cretValue123456" not in out, out


def test_no_false_positive_on_ordinary_text():
    """평범한 경로·문장·해시는 살아 있어야 한다 — 로그가 읽을 수 없게 되면 안 된다."""
    for keep in (
        "/Users/kangkukjin/Desktop/AI/indiebizOS/backend/base/logging_utils.py",
        "에피소드 2426 의 주행기록을 확인했습니다",
        "commit 9f5a8b4c478144149a6161a6320f11b1 을 되돌림",   # 이름 낱말이 근처에 없음
    ):
        assert mask_secrets(keep) == keep, f"오탐: {keep!r} -> {mask_secrets(keep)!r}"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
