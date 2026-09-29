"""75회차 후속 — 1차 수리(1b9a4932)가 남긴 누출의 회귀. 라이브 서비스·실제 저장소를 건드리지 않는다.

누출: ① 트리거 cron 이 정본 검사를 비켜 `0 9 31 2 *` 등이 "생성 완료" 좀비로 남음 ② 시각 없는 반복 예약이
성공·발화 0 ③ 판본 2 check 가 레코드 리터럴(`config:{…}`)을 미상으로 봐 등록 런타임과 다른 답 ④ 같은 영구
실패가 실행마다 바뀌는 로그 id 때문에 매시 "새 실패"로 알림 ⑤ 짧은 달에 건너뛰는 지정일을 등록이 말하지 않음.
"""
import json
from datetime import datetime, timedelta

import pytest

DO = "[self:time]{}"
FUTURE = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")


@pytest.fixture
def stores(tmp_path, monkeypatch):
    import calendar_manager as cmm
    import calendar_actions  # noqa: F401  합성 클래스 등록
    import trigger_engine as te
    monkeypatch.setattr(cmm, "CALENDAR_CONFIG_PATH", tmp_path / "calendar.json")
    monkeypatch.setattr(cmm, "DATA_PATH", tmp_path)
    monkeypatch.setattr(te, "TRIGGERS_PATH", tmp_path / "triggers.json")
    monkeypatch.setattr(te, "DATA_PATH", tmp_path)
    cls = cmm._MANAGER_CLS or cmm.CalendarManagerBase
    cm = cls(lambda _: None)
    monkeypatch.setattr(cmm, "_calendar_instance", cm)
    return cm, te


def _schedule(params):
    from system_ai_plans import _execute_schedule
    return json.loads(_execute_schedule(dict(params, pipeline=DO), agent_id=None, project_path=None))


def _events(params):
    from system_ai_tools import _execute_manage_events
    return json.loads(_execute_manage_events(dict(params, op="create", title="t", event_action=DO), project_path=None))


def _fires(cm, event, days):
    out = []
    for d in days:
        e = dict(event, created_at="2026-01-01T00:00:00")
        e.pop("last_run", None)
        if cm._should_run_task(e, datetime.fromisoformat(d + "T23:59")):
            out.append(d)
    return out


@pytest.mark.parametrize("cron", ["0 9 31 2 *", "0 9 32 * *", "0 25 * * *", "70 9 * * *", "0 9 1 13 *"])
def test_invalid_cron_is_refused_and_leaves_no_zombie(stores, cron):
    cm, te = stores
    result = te._create_trigger("z", {"cron": cron, "pipeline": DO}, None)
    assert result.get("error") and "trigger" not in result
    assert te.load_triggers()["triggers"] == [] and cm.config.get("events", []) == []


def test_sync_failure_rolls_back_trigger(stores, monkeypatch):
    cm, te = stores
    monkeypatch.setattr(te, "_sync_schedule_trigger", lambda *a: {"error": "boom"})
    result = te._create_trigger("z", {"cron": "0 9 * * *", "pipeline": DO}, None)
    assert "boom" in result["error"] and te.load_triggers()["triggers"] == []


@pytest.mark.parametrize("call", [
    lambda: _schedule({"repeat": "daily"}),
    lambda: _schedule({"repeat": "interval", "interval_hours": 2}),
    lambda: _events({"repeat": "daily"}),
    lambda: _schedule({"minutes": 5, "repeat": "daily"}),
    lambda: _schedule({"at": "내일 아침"}),
])
def test_executable_events_that_could_never_fire_are_refused(stores, call):
    cm, _ = stores
    result = call()
    assert result["success"] is False and cm.config.get("events", []) == []


def test_rest_task_invalid_rule_is_value_error(stores):
    cm, _ = stores
    with pytest.raises(ValueError):
        cm.add_task(name="r", repeat="monthly", action="run_pipeline", action_params={"pipeline": DO})


def test_every_entry_writes_the_same_firing_rule(stores):
    """같은 뜻을 입구마다 다르게 저장하던 B75-1 의 입구×규칙 표. 발화 판정 날짜가 같아야 한다."""
    cm, te = stores
    days = ["2026-10-01", "2026-10-15", "2026-10-31", "2026-11-30", "2026-12-12", "2027-02-28", "2027-12-12"]
    made = {
        "trigger cron monthly": te._create_trigger("a", {"cron": "0 9 15 * *", "pipeline": DO}, None),
        "schedule monthly day": _schedule({"repeat": "monthly", "day": 15, "time": "09:00"}),
        "schedule monthly date": _schedule({"repeat": "monthly", "date": "2026-10-15", "time": "09:00"}),
        "events monthly date": _events({"repeat": "monthly", "date": "2026-10-15", "time": "09:00"}),
    }
    assert all(r.get("success", True) and not r.get("error") for r in made.values()), made
    fired = {tuple(_fires(cm, e, days)) for e in cm.config["events"]}
    assert fired == {("2026-10-15",)}
    cm.config["events"] = []
    te._create_trigger("b", {"cron": "0 9 12 12 *", "pipeline": DO}, None)
    _schedule({"repeat": "yearly", "date": "2026-12-12", "time": "09:00"})
    _events({"repeat": "yearly", "date": "2026-12-12", "time": "09:00"})
    assert {tuple(_fires(cm, e, days)) for e in cm.config["events"]} == {("2026-12-12", "2027-12-12")}


def test_short_month_skip_is_said_at_registration(stores):
    _, te = stores
    assert "없는 달" in _schedule({"repeat": "monthly", "day": 31, "time": "21:00"})["notice"]
    assert "없는 달" in te._create_trigger("m", {"cron": "0 21 31 * *", "pipeline": DO}, None)["notice"]
    assert "윤년" in _events({"repeat": "yearly", "date": "2024-02-29", "time": "09:00"})["notice"]
    assert "notice" not in _schedule({"repeat": "monthly", "day": 15, "time": "09:00"})


def _ibl(value):
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {_ibl(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_ibl(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


PARITY = [
    ("self:schedule", {"repeat": "daily", "time": "09:00"}),
    ("self:schedule", {"repeat": "daily"}),
    ("self:schedule", {"repeat": "매일", "time": "09:00"}),
    ("self:schedule", {"repeat": "weekly", "time": "07:00"}),
    ("self:schedule", {"repeat": "weekly", "time": "07:00", "weekdays": ["mon"]}),
    ("self:schedule", {"repeat": "monthly", "time": "09:00"}),
    ("self:schedule", {"repeat": "interval", "interval_hours": 2}),
    ("self:schedule", {"repeat": "interval", "interval_hours": 2, "time": "08:00"}),
    ("self:schedule", {"minutes": 5, "repeat": "weekly"}),
    ("self:schedule", {"date": FUTURE, "time": "09:00"}),
    ("self:schedule", {"date": "2027-02-29", "time": "09:00"}),
    ("self:manage_events", {"op": "create", "title": "t", "repeat": "daily"}),
    ("self:manage_events", {"op": "create", "title": "t", "repeat": "yearly", "date": "2026-12-12", "time": "09:00"}),
    ("self:manage_events", {"op": "create", "title": "t", "repeat": "매주", "time": "09:00"}),
    ("self:trigger", {"op": "create", "name": "x", "cron": "0 9 31 2 *"}),
    ("self:trigger", {"op": "create", "name": "x", "cron": "0 25 * * *"}),
    ("self:trigger", {"op": "create", "name": "x", "cron": "30 0 1 * *"}),
    ("self:trigger", {"op": "create", "name": "x", "config": {"repeat": "매일", "time": "09:00"}}),
    ("self:trigger", {"op": "create", "name": "x", "config": {"repeat": "weekly", "weekdays": ["mon"], "time": "07:00"}}),
]


@pytest.mark.parametrize("action,args", PARITY)
def test_check_and_registration_agree(stores, action, args):
    """판본 2 check 의 판정 = 등록 런타임의 판정(B75-4 — 둘이 같은 함수를 부른다)."""
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    _, te = stores
    source = f"[{action}]{_ibl(dict(args, do=DO))}"
    checked = [i for i in compile_program(source, load_registry()).issues if i["code"] == "ARGUMENT_CONTRACT"]
    if action == "self:schedule":
        ran = _schedule(args)
        refused = ran["success"] is False
    elif action == "self:manage_events":
        ran = _events({k: v for k, v in args.items() if k not in ("op", "title")})
        refused = ran["success"] is False
    else:
        ran = te._create_trigger(args["name"], dict(args, pipeline=DO), None)
        refused = bool(ran.get("error"))
    assert bool(checked) == refused, (source, checked, ran)


def test_check_sees_record_literal_but_not_variables():
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    registry = load_registry()
    bad = compile_program('[self:trigger]{op:"create", name:"x", config:{repeat:"매일", time:"09:00"}, do:"[self:time]{}"}', registry)
    assert any("매일" in i["message"] for i in bad.issues)
    unknown = compile_program('$r = [self:time]{}\n[self:trigger]{op:"create", name:"x", config:{repeat:$r, time:"09:00"}, do:"[self:time]{}"}', registry)
    assert not [i for i in unknown.issues if i["code"] == "ARGUMENT_CONTRACT"]


def test_identical_script_failure_is_summarized_despite_run_ids():
    from calendar_actions import CalendarActionsMixin
    def err(uid, ms):
        return {"error": 'Step 1 에러: {"success": false, "duration_ms": %d, "error": "스크립트가 실패 결과를 반환했습니다.", '
                         '"log": "/x/data/script_runs/AI시대뉴스동기화-%s.log"}' % (ms, uid)}
    task = {}
    assert CalendarActionsMixin._should_notify_result(task, err("a03b57788f364620b13344dede2fface", 50), 100)
    assert not CalendarActionsMixin._should_notify_result(task, err("8cb2b1bf30644d889a959672b24d1eec", 57), 3700)
    assert task["failure_notice"]["repeated"] == 2
    assert CalendarActionsMixin._should_notify_result(task, {"error": "다른 원인"}, 3800)


@pytest.mark.parametrize("source,expected", [
    ('return date_add("2026-11-01", -1)', "2026-10-31"),          # 문자열 우회가 '2026-11-0' 을 내던 자리
    ('return date_add("2026-12-31", 1)', "2027-01-01"),
    ('return date_add("2026-03-01T09:30", -1)', "2026-02-28T09:30"),
    ('return date_add("2026-10-05T07:00:00Z", 2)', "2026-10-07T07:00:00Z"),
    ('return date_diff("2026-12-12", "2026-09-29")', 74),
    ('return month_end("2027-02-10")', "2027-02-28"),
    ('return month_end("2028-02-01")', "2028-02-29"),
])
def test_date_functions_g75_1(source, expected):
    """G75-1 언어 개정(사용자 채택): 날짜 산술 순수 함수 — 각 행 식 안에서도 호출 없이 쓴다."""
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    from ibl_v2_runtime import Runtime
    result = Runtime(compile_program(source, load_registry())).run()
    assert result["success"] and result["value"] == expected


def test_date_functions_refuse_undeclared_notation_and_hint_from_arithmetic():
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    from ibl_v2_runtime import Runtime
    registry = load_registry()
    slash = Runtime(compile_program('return date_add("2026/11/01", 1)', registry)).run()
    assert not slash["success"] and "ISO 8601" in json.dumps(slash["error"], ensure_ascii=False)
    fractional = Runtime(compile_program('return date_add("2026-11-01", 1.5)', registry)).run()
    assert not fractional["success"]
    minus = Runtime(compile_program('$d = "2026-11-01"; return $d - 1', registry)).run()
    assert "date_add" in json.dumps(minus["error"], ensure_ascii=False)
    typed = compile_program("return date_add(5, 1)", registry)
    assert any(i["code"] == "TYPE" for i in typed.issues)
    rows = Runtime(compile_program('$강의 = [{날짜:"2026-10-05"},{날짜:"2026-11-01"}]\n'
                                   'return $강의 >> [table:compute]{set:($r)=>{전날:date_add($r.날짜,-1)}}', registry)).run()
    assert [r["전날"] for r in rows["value"]] == ["2026-10-04", "2026-10-31"]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
