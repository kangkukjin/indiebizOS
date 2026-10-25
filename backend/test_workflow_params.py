"""[self:workflow]{op:"run", params} 침묵 유실 수리 회귀 테스트 (2026-08-17 B8)

desc("run — … + params 옵션(문장 안 $변수에 주입)")가 선언만 하고 구현이 없어,
호출자 params 가 조용히 무시되고 워크플로우가 고정값으로 돌아 거짓 정상을 냈다.

    W1. 저장본 run + params → 문장 안 미할당 $변수에 실제 주입
    W2. 통짜 참조("$n")는 원시 타입 보존, 문자열 임베드는 str/JSON
    W3. 대응 $변수 없는 params 키 → 정직 경고(params_warning)
    W4. 예약 이름($it/$items/each as) → 주입 금지 + 경고, each 의 $it 는 보존
    W5. 즉석 실행(do/steps·pipeline) + params — 저장본과 동일 지원
    W6. 문장 안 할당($x = …)이 호출자 params 보다 항상 이긴다(파스 후 주입)
    W7. params 비객체(JSON 아님) → 침묵 무시 대신 정직 거절 / JSON 문자열은 관용 수용
    W8. 저장본 인자 누락 → 정직 거절 (2026-08-22 승격 — 아래 참조)

2026-08-22 시그니처·재귀 가드 (M-sig / M-rec):
    W8 은 원래 "params 없으면 리터럴 $변수 보존"을 무회귀로 못박고 있었다. 그 동작이
    바로 결함이었다 — 인자 없이 부른 저장본이 "$city 맛집" 을 그대로 검색어로 삼고도
    success 로 완주했다(스코프 문제가 아니라 시그니처 부재의 증상). 저장본에는 save 라는
    "선언하는 순간"이 있으므로 정직 거절로 승격한다. 무인자 워크플로우의 무회귀는 유지.

    W9.  params_default — 기본값이 인자를 채우고, 호출자 params 가 기본값을 이긴다
    W10. 자기 순환 워크플로우 → 정직 거절 (실경로: 가짜 엔진 없이 engine 왕복)
    W11. 상호 순환 A→B→A → 정직 거절
    W12. 워크플로우 중첩 깊이 상한(MAX_WORKFLOW_DEPTH)
    W13. 즉석 실행의 미채움 자유 변수 → 경고(거절 아님 — 선언하는 순간이 없다)
    W14. save 가 시그니처를 계산·저장·보고하고 list 가 노출
    W15. 스케줄러 run_workflow 액션이 action_params.params 를 엔진에 통과 (2026-08-22)
    W16. 몸통이 스스로 할당한 변수는 시그니처가 아니다 — 시그니처 = 사용 − 할당 (B22-1)

실행: python3 backend/test_workflow_params.py
"""
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401 — 층 디렉토리 등재
import workflow_contract

import ibl_engine  # noqa: E402
import workflow_engine  # noqa: E402
from workflow_engine import execute_workflow_action  # noqa: E402


class _FakeEngine:
    """ibl_engine.execute_ibl 을 가로채 tool_input 을 기록하고 성공 응답."""

    def __init__(self):
        self.calls = []
        self._orig = None

    def __enter__(self):
        self._orig = ibl_engine.execute_ibl

        def _fake(tool_input, project_path, agent_id=None, **kw):
            self.calls.append(tool_input)
            return {"success": True, "echo": tool_input.get("params", {})}

        ibl_engine.execute_ibl = _fake
        return self

    def __exit__(self, *a):
        ibl_engine.execute_ibl = self._orig


def _save_tmp_workflow(wf_id, data):
    data = dict(data)
    data["id"] = wf_id
    workflow_engine.save_workflow(data)
    return wf_id


def _cleanup(wf_id):
    workflow_engine.delete_workflow(wf_id)


















# === 2026-08-22 시그니처 (M-sig) ===







# === 2026-08-22 재귀·순환 가드 (M-rec) ===
# 여기부터는 _FakeEngine 을 쓰지 않는다 — 스택이 step → execute_ibl → params → 다음
# workflow run 으로 이어지는지가 검증 대상이라, 실제 엔진 왕복이 아니면 의미가 없다.







# === 스케줄 표면 — 저장된 인자를 실행 시점까지 나르는가 (2026-08-22) ===
# 시그니처 도입 뒤, 스케줄러의 run_workflow 액션이 workflow_id 만 읽고 params 를 버려
# "인자를 요구하는 워크플로우는 스케줄에 걸면 실행 시점에 반드시 실패" 하는 구멍이 있었다.


class _FakeScheduler:
    """CalendarActionsMixin._action_run_workflow 만 떼어 쓰는 최소 숙주(_log 만 요구)."""

    def __init__(self):
        import calendar_actions
        self.logs = []
        self._run = calendar_actions.CalendarActionsMixin._action_run_workflow

    def _log(self, msg):
        self.logs.append(str(msg))

    def run(self, action_params):
        return self._run(self, {"title": "_t_sched", "action_params": action_params})


def test_w15_scheduler_passes_params():
    from workflow_engine import execute_workflow_action
    saved = execute_workflow_action('workflow', {'op':'save',
        'code':'#!ibl edition=2\n[def:예약도시]($city){return $city + " 맛집"}'}, '.')
    assert saved['success'], saved
    sched = _FakeScheduler()
    missing = sched.run({'workflow_id':'예약도시'})
    assert not missing['success'] and 'city' in str(missing)
    for params,city in [({'city':'청주'},'청주'), ('{"city":"부산"}','부산')]:
        out = sched.run({'workflow_id':'예약도시','params':params})
        assert out['success'] and out['value'] == city + ' 맛집', out
    invalid = sched.run({'workflow_id':'예약도시','params':'청주'})
    assert not invalid['success']




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
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
