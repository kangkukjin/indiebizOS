"""핀 가시성 관문 — **효력 있는 핀은 예외 없이 계기판에 보인다.**

★사고(2026-09-04, ep2806): `overrides["system_ai_delegation"] = "고급"` 핀이 2026-08-09
(커밋 67b1a8c4)부터 걸려 있어 정기보고앱→시스템 AI 위임이 늘 Opus 로 갔는데, 조종실의
핀 패널이 **실재 에이전트만** 열거해서 그 핀이 화면에 없었다. 결과:
  - 기어 레버를 절약으로 내려도 정기 보고서만 고급으로 가는 이유가 표면에 없었다.
  - 핀 값은 gitignore 된 `data/model_gear.json` 에만 살아 git 이력도 없어, 사용자가
    자기가 설정한 기억조차 못 했다("나는 언제 그랬는지 기억이 안 나").

뿌리는 UI 한 줄 누락이 아니라 **키 공간의 비대칭**이다: `model_resolver.resolve()` 는
overrides dict 를 키로 그냥 조회해서 role 이름도, 코드가 지어낸 경로 이름
(`system_ai_delegation`)도 유효한 키인데, 열거하는 쪽은 '에이전트'만 알았다. 그래서
목록에 이름을 하나 더 하드코딩하는 것은 미룸이다 — 다음에 코드가 새 핀 키를 지어내면
같은 유령이 다시 난다. 관문은 그 불변식을 잡는다.
"""

import unicodedata

import boot_paths  # noqa: F401

import api_config
import model_resolver as M


def _nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


def _ids():
    return {_nfc(a["id"]) for a in api_config._list_pinnable_agents()}


def test_delegation_pin_key_is_listed():
    """위임 경로 핀 키는 핀이 안 걸려 있어도 목록에 있다(걸기 전에 보여야 고를 수 있다)."""
    assert "system_ai_delegation" in _ids()


def test_every_effective_pin_is_visible(monkeypatch):
    """불변식 — overrides 에 있는 키는 무엇이든 목록에 나타난다.

    코드가 앞으로 어떤 이름을 핀 키로 지어내도(role·경로·미래의 무엇) 계기판에서
    보이고 지울 수 있어야 한다. 이게 깨지면 유령 핀이 다시 생긴다.
    """
    fake = {
        "system_ai_delegation": "고급",
        "어떤_미래의_핀키": "중급",       # 코드가 나중에 지어낼 이름
        "없는프로젝트:agent_001": "경량",  # 사라진 프로젝트에 남은 핀도 지울 수 있어야 한다
    }
    monkeypatch.setattr(M, "get_overrides", lambda: dict(fake))
    ids = _ids()
    missing = [k for k in fake if _nfc(k) not in ids]
    assert not missing, f"효력 있는 핀이 목록에서 빠졌다(유령 핀): {missing}"


def test_no_duplicate_pin_keys(monkeypatch):
    """고아 흡수가 이미 열거된 키를 두 번 넣지 않는다(드롭다운 중복 방지)."""
    monkeypatch.setattr(M, "get_overrides",
                        lambda: {"system_ai": "고급", "forage": "경량",
                                 "system_ai_delegation": "고급"})
    rows = api_config._list_pinnable_agents()
    ids = [_nfc(a["id"]) for a in rows]
    assert len(ids) == len(set(ids)), "핀 키가 중복 열거됐다"


def test_sweep_failure_does_not_kill_the_list(monkeypatch):
    """흡수가 실패해도 기본 목록은 살아야 한다 — 패널이 통째로 비면 더 나쁘다."""
    def boom():
        raise RuntimeError("overrides 읽기 실패")

    monkeypatch.setattr(M, "get_overrides", boom)
    assert "system_ai" in _ids()


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
