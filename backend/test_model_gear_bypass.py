"""모델 기어 우회 관문 — 티어 설정 파일을 패키지가 직접 읽지 못하게 한다.

★사고(2026-08-31, ep2482): 슬라이드 저작이 `저작 실패: 시스템 AI API 키가 없습니다
(설정 → 시스템 AI)` 로 죽었다. 원인은 키가 아니라 **통로**다 — `slide_image.py` 가
모델 기어 리졸버를 거치지 않고 고급 티어 파일(`data/system_ai_config.json`)의 `apiKey`
칸을 직접 검사했고, 그 칸은 기어가 키 불요 프로바이더(claude_code·codex)일 때 원래
비어 있다. 같은 자리에서 그 값을 **Gemini 키로도** 썼다(티어 키 ≠ 이미지 키).

같은 부류가 이미 두 번 고쳐졌다: slide_ai(2026-08-04)·youtube(2026-08-30). 두 번 다
'그 파일 하나'만 고쳤고 형제 파일이 남아 세 번째 사고가 났다 — 사람이 고른 grep 범위는
반드시 샌다(pitfall_hand_picked_sweep_leaks). 그래서 이번엔 목록이 아니라 관문을 둔다.

규칙: **패키지는 티어 설정 파일의 이름을 몰라야 한다.** 모델은 `model_resolver.resolve()`
로 해소하고, "키가 있나"는 `provider_needs_api_key()` 로 판정한다. 벤더 키(GEMINI 등)는
`.env`/환경변수가 정본이지 티어 파일이 아니다.
"""

import pathlib
import re

import boot_paths  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parent.parent
import pytest  # noqa: E402
pytestmark = pytest.mark.skipif(not (ROOT / "data" / "model_gear.json").exists(),
                                reason="data/model_gear.json(런타임 설정, gitignore) 없음 — 설정이 있는 몸에서만 도는 시험")
PKG_ROOT = ROOT / "data" / "packages"

# 티어 설정 파일 이름들 — model_gear.json 의 `tiers` 가 정본이므로 거기서 읽는다
# (여기 손으로 적으면 티어가 늘 때 관문이 낡는다).
def _tier_config_names() -> set:
    import json
    gear = json.loads((ROOT / "data" / "model_gear.json").read_text(encoding="utf-8"))
    names = set((gear.get("tiers") or {}).values())
    # 모달리티 슬롯도 같은 모양의 설정 파일이다 — 패키지가 직접 열 자리는 아니다.
    for v in (gear.get("modality") or {}).values():
        if isinstance(v, str) and v.endswith(".json"):
            names.add(v)
    return {n for n in names if n}


def _pkg_sources():
    for path in PKG_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue


def test_packages_do_not_read_tier_configs():
    """패키지가 티어 설정 파일을 직접 열지 않는다 — 모델 해소는 model_resolver 를 지난다."""
    names = _tier_config_names()
    stems = {n[:-5] for n in names}          # "system_ai_config.json" → "system_ai_config"
    offenders = []
    for path, text in _pkg_sources():
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(s in line for s in stems):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}")

    assert not offenders, (
        f"티어 설정 파일을 직접 읽는 패키지: {offenders}\n"
        f"티어 파일({sorted(names)})은 model_resolver 의 소유다. 패키지는 "
        f"`resolve('content_text')` 로 모델을 받고 `provider_needs_api_key()` 로 키를 "
        f"판정하십시오. 벤더 키(GEMINI_API_KEY 등)는 .env/환경변수가 정본입니다."
    )


def test_packages_do_not_hand_copy_no_key_sets():
    """'키 불요 프로바이더' 집합을 패키지가 손으로 적지 않는다.

    backend 안쪽은 test_cli_provider_gates.test_no_hand_copied_no_key_sets 가 지킨다 —
    그 관문의 스윕 범위가 backend/ 에서 끊겨 패키지 쪽 손복사본 두 벌
    (slide_ai·slide_native)이 그 밖에 살아 있었다. 같은 규칙, 나머지 반쪽.
    """
    pattern = re.compile(
        r"[{(\[][^{}()\[\]]*[\"']claude[_-]?code[\"'][^{}()\[\]]*[\"']ollama[\"'][^{}()\[\]]*[)}\]]"
    )
    offenders = []
    for path, text in _pkg_sources():
        for m in pattern.finditer(text):
            offenders.append(f"{path.relative_to(ROOT)}:{text.count(chr(10), 0, m.start()) + 1}")

    assert not offenders, (
        f"키 불요 프로바이더 집합의 손복사본: {offenders} — "
        f"model_resolver.provider_needs_api_key() 호출로 바꾸십시오."
    )


if __name__ == "__main__":
    import sys

    import pytest

    raise SystemExit(pytest.main([__file__, "-v"] + sys.argv[1:]))
