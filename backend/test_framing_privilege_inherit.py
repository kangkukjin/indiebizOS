"""framing 재사용이 수리 권한(needs_repair)을 상속하지 않는다 — 회귀 시험

사건(2026-08-22, 상상훈련 22회차): "상상훈련을 다시 한번 해줘" 에 직전 `#repair` 턴의
framing 이 fits=true 로 재사용됐다. 재사용은 `dict(prev)` 통짜 복사라 `needs_repair` 까지
따라왔고, 파이프라인은 그걸 보고 **RED 자기수정 그랜트**(고급 모델 고정 + 라이브 코어
쓰기)를 발급했다. 보고만 해야 할 훈련 턴이 `workflow_contract.py` 를 고쳐 지연 적용까지 갔다.

구멍의 이름: **의식이 본 적 없는 턴에 권한이 발급된다.** 헌법 3조건의 '의식 각성'은
풀 의식 경로에서만 참인데, 재사용 경로가 같은 승격을 물려받았다.
대조군 — 같은 지시라도 의식이 깬 21회차는 보고만 하고 끝났다.

실행: cd indiebizOS && .venv/bin/python -m pytest backend/test_framing_privilege_inherit.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401 — 층 디렉토리 등재

import cognitive_consciousness as CC
from cognitive_consciousness import CognitiveConsciousnessMixin


_REPAIR_FRAMING = {
    "task_framing": "수리 원장 ①·② 항목의 전제가 현재 라이브 코드에서 참인지 실측하고 "
                    "유효한 것만 수리해야 한다.",
    "achievement_criteria": "유효한 항목만 수정하고 [self:patch]{op:\"apply\"} 로 통과시킬 것.",
    "needs_repair": True,
}

_PLAIN_FRAMING = {
    "task_framing": "21회차 원장의 갭 항목을 목록화해 상태를 정리한다.",
    "achievement_criteria": "항목마다 상태를 밝힐 것.",
}


class _Runner(CognitiveConsciousnessMixin):
    """게이트·의식만 대역으로 갈아끼운 최소 러너."""

    def __init__(self, gate_result=None, fresh=None):
        self.gate_calls = 0
        self.consciousness_calls = 0
        self._gate_result = gate_result
        self._fresh = fresh or {"task_framing": "새 지도", "achievement_criteria": "새 기준"}
        self.logs = []

    def _log(self, msg):
        self.logs.append(msg)

    def _consciousness_fit_gate(self, user_message, prev_framing):
        self.gate_calls += 1
        return self._gate_result

    def _run_consciousness(self, user_message, history, execution_memory=""):
        self.consciousness_calls += 1
        return dict(self._fresh)


def _seed(framing):
    CC._FRAMING_CACHE.clear()
    CC.framing_cache_set("default", dict(framing))


def test_수리_framing은_재사용되지_않는다():
    """★본체: needs_repair 가 걸린 지도는 게이트에 묻지도 않고 의식을 깨운다."""
    _seed(_REPAIR_FRAMING)
    runner = _Runner(gate_result={"fits": True, "amended_framing": "", "criteria": "아무거나"})

    out = runner._run_consciousness_or_reuse("상상훈련을 다시 한번 해줘.", history=[{"role": "user", "content": "이전"}])

    assert runner.consciousness_calls == 1, "의식이 깨지 않았다 — 권한이 캐시로 상속된다"
    assert runner.gate_calls == 0, \
        "수리 권한이 걸린 지도는 게이트 판정 대상이 아니다 (경량 모델에 권한 판정을 맡기지 않는다)"
    assert not out.get("needs_repair"), "새 의식이 선언하지 않은 수리 권한이 남았다"
    assert out["task_framing"] == "새 지도"
    assert any("needs_repair" in m for m in runner.logs), "재사용 거부가 원장에 안 남았다"


def test_평범한_framing은_그대로_재사용된다():
    """무회귀 — 권한 없는 지도의 재사용(Opus 스킵)은 그대로 살아 있어야 한다."""
    _seed(_PLAIN_FRAMING)
    runner = _Runner(gate_result={"fits": True, "amended_framing": "", "criteria": "이번 턴 기준"})

    out = runner._run_consciousness_or_reuse("그 다음 항목도 정리해줘", history=[{"role": "user", "content": "이전"}])

    assert runner.consciousness_calls == 0, "재사용이 죽었다 — 의식 스킵의 이득이 사라진다"
    assert runner.gate_calls == 1
    assert out["task_framing"] == _PLAIN_FRAMING["task_framing"]
    assert out["achievement_criteria"] == "이번 턴 기준"


def test_수리_framing이라도_새_의식이_선언하면_권한은_산다():
    """차단하는 것은 *상속*이지 수리 자체가 아니다 — 이번 턴 의식이 선언하면 그대로."""
    _seed(_REPAIR_FRAMING)
    runner = _Runner(
        gate_result={"fits": True, "amended_framing": "", "criteria": "x"},
        fresh={"task_framing": "이번에도 수리다", "achievement_criteria": "고칠 것",
               "needs_repair": True},
    )

    out = runner._run_consciousness_or_reuse("마저 고쳐줘 #repair", history=[{"role": "user", "content": "이전"}])

    assert runner.consciousness_calls == 1
    assert out.get("needs_repair") is True, "이번 턴 의식의 선언까지 막으면 안 된다"


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
