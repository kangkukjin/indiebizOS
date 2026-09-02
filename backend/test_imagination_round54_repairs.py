"""54회차 상상훈련 수리 회귀 — 축: **시간 왕복**(defer→fire: 지금 쓴 문장이 나중에 실행될 때 뜻을 보존하는가).

격자 = 미루는 어휘 4종(trigger · schedule · manage_events · workflow 호출) × 보존 차원 6종
(프로젝트 문맥 · $변수/중첩 인용 · 결과 통화의 행선지 · 실패의 정직성 · 시각/cron 표현력 ·
등록↔캘린더↔이력 되읽기). 등록 시점만 실측하던 과거 회차와 달리 스케줄러 틱·타이머 스레드·
run_now 의 **발화 시점**까지 실측했다.

재현하는 결함(전부 2026-09-02 실측, 보고서 `outputs/imagination_training/2026-09-02_54회차.md`):

  B54-1 **트리거가 발화할 때 등록 프로젝트를 모른다** — 레거시 경로가 project_path "." 고정이라
     패키지 도구 전부 "활성 프로젝트 경로를 확보할 수 없어". 등록 시 project_id 저장 + 캘린더
     owner_project_id + 발화가 그 경로에서 실행.
  B54-2 **[self:schedule] 이 표면 호출에서 시스템 AI 스케줄로 귀속** — /ibl/execute 의 기본
     agent_id "system_ai" 가 구체 프로젝트 경로보다 먼저 이겼다. 발화가 시스템 AI 창을 열어
     LLM 턴을 태웠다. 정체성은 프로젝트 경로가 먼저.
  B54-3 **지연 스케줄 결과 전달 함수 `_deliver_result_to_chat` 이 존재하지 않았다** — 성공은
     AttributeError 로 삼켜지고 실패는 호출조차 없었다. 알림으로 성공·실패 모두 전달.
  B54-4 **같은 분에 due 인 작업 중 하나만 돈다** — `_save_config` 의 임시 파일명이 하나
     (`<path>.json.tmp`) + 잠금 없음 → 동시 발화 스레드가 os.replace 에서 FileNotFoundError 로
     "작업 시작" 로그 앞에서 죽었다(라이브 7/4·재시험 4/1·격리 4/1). safe_save_json 도 같은 구조,
     add_history 는 잠금 없는 load-modify-save 라 이력 행이 유실됐다.
  B54-5 **manage_events{do: IBL} 가 실행 이벤트가 되지 않았다** — 문장이 액션 *이름*으로 저장돼
     발화 때 "알 수 없는 작업" 로그뿐, run_now 는 "즉시 실행 시작" 성공을 말했다.
  B54-6 트리거 레코드 `run_count`·`last_run` 죽은 필드.  B54-7 간격형 cron 의 분 필드 침묵 소실.
  B54-8 트리거 `config` 직접 지정이 검증 없이 저장(가이드의 `weekdays:["mon"]`·`repeat:"once"` 가
     영원히 안 도는 트리거로 성공 등록).
  F54-1 cron 요일 범위 `1-5`(평일) 미지원 + 검수가 cron 을 안 봄.  F54-2 등록 즉시 따라잡기 발화.
  F54-3 manage_events `date:"YYYY-MM-DD HH:MM"` 원문 저장 → 침묵 미발화.  F54-4 이력이 통화가 아님.
"""
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import boot_paths  # noqa: E402,F401


# ───────────────────────── 캘린더 매니저 (격리 인스턴스) ─────────────────────────

@pytest.fixture
def cm(tmp_path, monkeypatch):
    import calendar_manager as cmmod
    monkeypatch.setattr(cmmod, "CALENDAR_CONFIG_PATH", tmp_path / "calendar_events.json")
    monkeypatch.setattr(cmmod, "DATA_PATH", tmp_path)
    inst = cmmod.CalendarManagerBase(log_callback=lambda m: None)
    return inst


def _due_event(i: int, now: datetime, created: datetime = None, repeat="daily", action="fake"):
    t = now - timedelta(minutes=1)
    e = {"id": f"e{i}", "title": f"t{i}", "type": "schedule", "repeat": repeat,
         "time": f"{t.hour:02d}:{t.minute:02d}", "action": action, "enabled": True}
    if created is not None:
        e["created_at"] = created.isoformat()
    return e


def test_B54_4_concurrent_save_config_has_no_race(cm):
    """8 스레드가 동시에 _save_config — 수리 전엔 공유 임시 파일명 때문에 FileNotFoundError."""
    errors = []

    def _save():
        try:
            cm._save_config()
        except Exception as e:  # pragma: no cover - 수리 전 재현 경로
            errors.append(repr(e))

    ths = [threading.Thread(target=_save) for _ in range(8)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert errors == [], errors
    import calendar_manager as cmmod
    assert json.load(open(cmmod.CALENDAR_CONFIG_PATH)) == cm.config
    assert not [p for p in os.listdir(cmmod.CALENDAR_CONFIG_PATH.parent) if p.endswith(".tmp")]


def test_B54_4_all_due_tasks_in_same_minute_run(cm):
    """같은 분 due 4건 → 4건 전부 실행(수리 전 격리 실측: 1건)."""
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    cm.config["events"] = [_due_event(i, now, created=yesterday) for i in range(4)]
    ran = []
    cm.actions = {"fake": lambda task: (ran.append(task["title"]), time.sleep(0.2))}
    cm.running = True
    th = threading.Thread(target=cm._run_loop, daemon=True)
    th.start()
    time.sleep(1.5)
    cm.running = False
    assert sorted(ran) == ["t0", "t1", "t2", "t3"], ran
    assert all(e.get("last_run") for e in cm.config["events"])


def test_B54_4_safe_save_json_concurrent(tmp_path):
    from safe_store import safe_save_json, safe_load_json
    p = tmp_path / "x.json"
    errors = []

    def _save(i):
        try:
            safe_save_json(p, {"n": i, "rows": list(range(50))})
        except Exception as e:  # pragma: no cover
            errors.append(repr(e))

    ths = [threading.Thread(target=_save, args=(i,)) for i in range(8)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert errors == [], errors
    d = safe_load_json(p, None)
    assert isinstance(d, dict) and len(d["rows"]) == 50
    assert not [q for q in os.listdir(tmp_path) if q.endswith(".tmp")]


def test_F54_2_fresh_registration_is_not_due_today(cm):
    """반복형: 오늘 예정 시각 뒤에 등록했으면 오늘 몫이 아니다. 어제 등록(결번)은 따라잡는다.
    1회성(repeat none, 명시 date)은 현행 유지."""
    now = datetime.now().replace(hour=15, minute=30)
    slot = now.replace(hour=9, minute=0)
    fresh = {"id": "a", "title": "a", "repeat": "daily", "time": "09:00", "action": "fake",
             "enabled": True, "created_at": (slot + timedelta(hours=3)).isoformat()}
    old = dict(fresh, id="b", created_at=(now - timedelta(days=1)).isoformat())
    before_slot = dict(fresh, id="c", created_at=(slot - timedelta(minutes=5)).isoformat())
    assert cm._should_run_task(fresh, now) is False
    assert cm._should_run_task(old, now) is True
    assert cm._should_run_task(before_slot, now) is True
    once = {"id": "d", "title": "d", "repeat": "none", "date": now.strftime("%Y-%m-%d"), "time": "09:00",
            "action": "fake", "enabled": True, "created_at": now.isoformat()}
    assert cm._should_run_task(once, now) is True
    weekly = dict(fresh, id="e", repeat="weekly", weekdays=[now.weekday()])
    assert cm._should_run_task(weekly, now) is False
    assert cm._should_run_task(dict(weekly, created_at=old["created_at"]), now) is True


def test_B54_5_run_now_refuses_unknown_action(cm):
    cm.actions = {"run_pipeline": lambda t: None}
    cm.config["events"] = [
        {"id": "x", "title": "x", "repeat": "none", "date": "2030-01-01", "time": "09:00",
         "action": "[sense:stock]{op: 'quote'} >> [self:write]{path: 'a'}", "enabled": True},
        {"id": "y", "title": "y", "repeat": "none", "date": "2030-01-01", "enabled": True},
    ]
    why = cm.explain_run_now("x")
    assert why and "알 수 없는 작업" in why and "run_pipeline" in why
    assert cm.run_task_now("x") is False
    assert "실행 이벤트가 아닙니다" in cm.explain_run_now("y")
    assert "찾을 수 없습니다" in cm.explain_run_now("zzz")


# ───────────────────────── 트리거 엔진 (격리 파일) ─────────────────────────

@pytest.fixture
def te(tmp_path, monkeypatch):
    import trigger_engine as mod
    monkeypatch.setattr(mod, "TRIGGERS_PATH", tmp_path / "event_triggers.json")
    monkeypatch.setattr(mod, "DATA_PATH", tmp_path)
    synced = []
    monkeypatch.setattr(mod, "_sync_schedule_trigger", lambda trigger, action="add": synced.append((action, dict(trigger))) or True)
    mod._synced_for_test = synced
    return mod


def test_F54_1_cron_weekday_ranges_and_lists(te):
    assert te._cron_to_config("0 9 * * 1-5") == {"repeat": "weekly", "weekdays": [0, 1, 2, 3, 4], "time": "09:00"}
    assert te._cron_to_config("30 18 * * 1,3,5")["weekdays"] == [0, 2, 4]
    assert te._cron_to_config("0 9 * * mon-fri")["weekdays"] == [0, 1, 2, 3, 4]
    assert te._cron_to_config("0 10 * * 6,0")["weekdays"] == [5, 6]      # 토·일 (cron 0=일)
    assert te._cron_to_config("0 9 * * */2")["weekdays"] == [1, 3, 5, 6]  # cron 0,2,4,6=일·화·목·토 → calendar(0=월) 화·목·토·일
    assert "error" in te._cron_to_config("0 9 * * 8")
    assert "error" in te._cron_to_config("0 9 * * x-y")


def test_B54_7_interval_cron_minute_is_not_silently_dropped(te):
    assert te._cron_to_config("0 */2 * * *") == {"repeat": "interval", "interval_hours": 2}
    r = te._cron_to_config("30 */2 * * *")
    assert "error" in r and "분 0" in r["error"] and "self:schedule" in r["error"]
    assert te._cron_to_config("0 * * * *") == {"repeat": "interval", "interval_hours": 1}
    assert "error" in te._cron_to_config("15 * * * *")


def test_B54_8_direct_config_is_normalized_and_validated(te):
    n = te.normalize_schedule_config
    assert n({"repeat": "weekly", "weekdays": ["mon", "wed"], "time": "9:00"})["config"] == \
        {"repeat": "weekly", "weekdays": [0, 2], "time": "09:00"}
    assert n({"repeat": "once", "date": "2030-01-01", "time": "14:00"})["config"]["repeat"] == "none"
    assert "error" in n({"repeat": "weekly", "time": "09:00"})           # weekdays 없음
    assert "error" in n({"repeat": "interval"})                          # interval_hours 없음
    assert "error" in n({"repeat": "hourly"})
    assert "error" in n({"repeat": "daily", "time": "25:00"})
    assert "error" in n({"repeat": "once"})                              # date 없음
    assert "error" in n("daily")
    r = te._create_trigger("w", {"pipeline": "[sense:host]{op: 'status'}",
                                 "config": {"repeat": "weekly", "weekdays": ["fri"], "time": "18:00"}})
    assert r["trigger"]["config"]["weekdays"] == [4]
    bad = te._create_trigger("w2", {"pipeline": "[sense:host]{op: 'status'}", "config": {"repeat": "once"}})
    assert "error" in bad


def test_B54_1_create_stores_project_and_hands_owner_to_calendar(te):
    assert te.project_id_of_path("/x/projects/투자") == "투자"
    assert te.project_id_of_path("/x/data") == ""
    assert te.project_id_of_path(".") == "" and te.project_id_of_path(None) == ""
    r = te._create_trigger("p", {"pipeline": "[sense:host]{op: 'status'}", "cron": "0 9 * * *"},
                           project_path="/x/projects/투자")
    assert r["trigger"]["project_id"] == "투자"
    assert te._synced_for_test[-1][1].get("project_id") == "투자"
    r2 = te._create_trigger("s", {"pipeline": "[sense:host]{op: 'status'}", "cron": "0 9 * * *"},
                            project_path="/x/data")
    assert "project_id" not in r2["trigger"]
    r3 = te.execute_trigger("trigger", {"op": "create", "name": "q", "pipeline": "[sense:host]{op: 'status'}",
                                        "cron": "0 9 * * *"}, project_path="/x/projects/컨텐츠")
    assert r3["trigger"]["project_id"] == "컨텐츠"


def test_B54_6_F54_4_history_carries_currency_fields_and_updates_record(te):
    r = te._create_trigger("h", {"pipeline": "[sense:host]{op: 'status'}", "cron": "0 9 * * *"})
    tid = r["trigger"]["id"]
    te.add_history(tid, "[IBL] h", False, "{'error': 'boom'}", 12, error="boom", count=0, shape="items")
    te.add_history(tid, "[IBL] h", True, "{...}", 5, count=3, shape="items")
    hist = te._trigger_history(tid, {})["items"]
    assert hist[0]["success"] is True and hist[0]["count"] == 3
    assert hist[1]["error"] == "boom" and hist[1]["count"] == 0 and hist[1]["shape"] == "items"
    rec = te._get_trigger(tid)["trigger"]
    assert rec["run_count"] == 2 and rec["last_run"] and rec["last_success"] is True


def test_B54_4_concurrent_add_history_loses_no_rows(te):
    r = te._create_trigger("c", {"pipeline": "[sense:host]{op: 'status'}", "cron": "0 9 * * *"})
    tid = r["trigger"]["id"]
    ths = [threading.Thread(target=te.add_history, args=(tid, "c", True, str(i), i)) for i in range(8)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert te._trigger_history(tid, {"limit": 50})["count"] == 8
    assert te._get_trigger(tid)["trigger"]["run_count"] == 8


# ───────────────────────── 발화 경로 (calendar_actions) ─────────────────────────

class _FakeNM:
    def __init__(self):
        self.calls = []

    def success(self, title, message, source="system"):
        self.calls.append(("success", title, message))
        return {"id": "n1"}

    def warning(self, title, message, source="system"):
        self.calls.append(("warning", title, message))
        return {"id": "n2"}


@pytest.fixture
def actions_cm(tmp_path, monkeypatch):
    import calendar_manager as cmmod
    monkeypatch.setattr(cmmod, "CALENDAR_CONFIG_PATH", tmp_path / "calendar_events.json")
    monkeypatch.setattr(cmmod, "DATA_PATH", tmp_path)
    import calendar_actions
    nm = _FakeNM()
    import types
    fake_mod = types.SimpleNamespace(get_notification_manager=lambda: nm)
    monkeypatch.setitem(sys.modules, "notification_manager", fake_mod)
    inst = calendar_actions.CalendarManager(log_callback=lambda m: None)
    inst._nm_for_test = nm
    return inst


def test_B54_3_deliver_result_to_chat_exists_and_reports_both_outcomes(actions_cm):
    cm = actions_cm
    task = {"title": "5초 뒤 시세", "owner_project_id": "투자", "owner_agent_id": ""}
    ok = cm._deliver_result_to_chat(task, "", "[sense:stock]{}", {"success": True, "final_result": {"items": [1, 2]}})
    assert ok["delivered"] is True
    bad = cm._deliver_result_to_chat(task, "", "[sense:stock]{}", {"success": False, "error": "ZZZZ 종목 없음"})
    assert bad["delivered"] is True
    kinds = [c[0] for c in cm._nm_for_test.calls]
    assert kinds == ["success", "warning"]
    assert "2행" in cm._nm_for_test.calls[0][2] and "ZZZZ" in cm._nm_for_test.calls[1][2]
    assert "투자" in cm._nm_for_test.calls[0][1]


def test_B54_1_owner_run_path_resolves_project_and_keeps_dot_for_system(actions_cm):
    cm = actions_cm
    assert cm._owner_run_path("") == "." and cm._owner_run_path("__system_ai__") == "."
    assert cm._owner_run_path("없는프로젝트_zz") == "."


def test_B54_1_legacy_fire_runs_in_owner_project(actions_cm, monkeypatch, tmp_path):
    """소유 에이전트 없는 스케줄(트리거·표면 등록)의 발화는 소유 프로젝트 경로에서 execute_pipeline."""
    import types
    seen = {}
    proj = tmp_path / "projects" / "투자"
    proj.mkdir(parents=True)

    class _PM:
        def get_project_path(self, pid):
            return proj if pid == "투자" else tmp_path / "projects" / pid

    monkeypatch.setitem(sys.modules, "project_manager", types.SimpleNamespace(ProjectManager=_PM))
    monkeypatch.setitem(sys.modules, "ibl_parser", types.SimpleNamespace(
        parse=lambda code: [{"_node": "sense", "action": "host", "params": {}}],
        IBLSyntaxError=ValueError))

    def _exec(steps, project_path=".", context=None, agent_id=None):
        seen["project_path"] = project_path
        return {"success": True, "final_result": {"items": [1]}}

    monkeypatch.setitem(sys.modules, "workflow_engine", types.SimpleNamespace(execute_pipeline=_exec))
    hist = []
    monkeypatch.setitem(sys.modules, "trigger_engine", types.SimpleNamespace(
        add_history=lambda **kw: hist.append(kw)))
    task = {"id": "e1", "title": "[IBL] x", "action": "run_pipeline",
            "action_params": {"pipeline": "[sense:host]{op: 'status'}", "trigger_id": "trg_1"},
            "owner_project_id": "투자"}
    r = actions_cm._action_run_pipeline(task)
    assert r["success"] is True
    assert seen["project_path"] == str(proj)
    assert hist and hist[0]["count"] == 1 and hist[0]["shape"] == "items"
    seen.clear()
    actions_cm._action_run_pipeline(dict(task, owner_project_id=None))
    assert seen["project_path"] == "."   # 소유자 없는 옛 트리거는 종전 경로


# ───────────────────────── 등록 어휘 (schedule · manage_events) ─────────────────────────

class _FakeCM:
    def __init__(self):
        self.added = []
        self.actions = {"run_pipeline": lambda t: None, "send_notification": lambda t: None}
        self.config = {"events": []}

    def add_event(self, **kw):
        self.added.append(kw)
        ev = dict(kw, id=f"evt_{len(self.added)}")
        self.config["events"].append(ev)
        return ev

    def update_event(self, event_id, **kw):
        return True

    def explain_run_now(self, task_id):
        for e in self.config["events"]:
            if e["id"] == task_id:
                return None if e.get("action") in self.actions else f"알 수 없는 작업 '{e.get('action')}'"
        return "없음"

    def run_task_now(self, task_id):
        return self.explain_run_now(task_id) is None


@pytest.fixture
def fake_cm(monkeypatch):
    import calendar_manager as cmmod
    fake = _FakeCM()
    monkeypatch.setattr(cmmod, "get_calendar_manager", lambda log_callback=None: fake)
    return fake


def test_B54_2_schedule_owner_is_project_path_first(fake_cm):
    from system_ai_plans import _execute_schedule
    r = json.loads(_execute_schedule({"pipeline": "[sense:host]{op: 'status'}", "repeat": "daily", "time": "09:00"},
                                     agent_id="system_ai", project_path="/x/projects/투자"))
    assert r["success"] is True
    ev = fake_cm.added[-1]
    assert ev["owner_project_id"] == "투자" and ev["owner_agent_id"] == ""
    r2 = json.loads(_execute_schedule({"pipeline": "[sense:host]{op: 'status'}", "repeat": "daily", "time": "09:00"},
                                      agent_id="system_ai", project_path="/x/data"))
    assert r2["success"] is True and fake_cm.added[-1]["owner_project_id"] == "__system_ai__"
    r3 = json.loads(_execute_schedule({"pipeline": "[sense:host]{op: 'status'}", "repeat": "daily", "time": "09:00"},
                                      agent_id="agent_7", project_path="/x/projects/투자"))
    assert fake_cm.added[-1]["owner_agent_id"] == "agent_7" and r3["success"] is True


def test_F54_2_schedule_at_in_the_past_is_refused(fake_cm):
    from system_ai_plans import _execute_schedule
    r = json.loads(_execute_schedule({"pipeline": "[sense:host]{op: 'status'}", "at": "00:00"},
                                     agent_id="system_ai", project_path="/x/projects/투자"))
    assert r["success"] is False and "이미 지났습니다" in r["error"]
    past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    r2 = json.loads(_execute_schedule({"pipeline": "[sense:host]{op: 'status'}", "date": past, "time": "09:00"},
                                      agent_id="system_ai", project_path="/x/projects/투자"))
    assert r2["success"] is False
    future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    r3 = json.loads(_execute_schedule({"pipeline": "[sense:host]{op: 'status'}", "date": future, "time": "09:00"},
                                      agent_id="system_ai", project_path="/x/projects/투자"))
    assert r3["success"] is True and fake_cm.added[-1]["event_date"] == future


def test_B54_5_manage_events_do_becomes_run_pipeline(fake_cm):
    from system_ai_tools import _execute_manage_events
    code = "[sense:stock]{op: 'quote', ticker: '005930'} >> [self:write]{path: 'a.json', format: 'json'}"
    r = json.loads(_execute_manage_events({"op": "create", "title": "t", "date": "2030-01-01 14:00",
                                           "event_action": code}, project_path="/x/projects/투자"))
    assert r["success"] is True, r
    ev = fake_cm.added[-1]
    assert ev["action"] == "run_pipeline" and ev["action_params"]["pipeline"] == code
    assert ev["event_date"] == "2030-01-01" and ev["event_time"] == "14:00"     # F54-3
    assert ev["owner_project_id"] == "투자"
    bad = json.loads(_execute_manage_events({"op": "create", "title": "t", "date": "2030-01-01",
                                             "event_action": "launch_rockets"}))
    assert bad["success"] is False and "알 수 없는 실행 액션" in bad["error"]
    fake_cm.config["events"].append({"id": "old", "action": "[sense:x]{}", "title": "old"})
    rn = json.loads(_execute_manage_events({"op": "run_now", "event_id": "old"}))
    assert rn["success"] is False and "알 수 없는 작업" in rn["error"]


def test_F54_3_split_date_time():
    from system_ai_tools import _split_date_time
    assert _split_date_time("2026-09-03 14:00", None) == ("2026-09-03", "14:00")
    assert _split_date_time("2026-09-03T14:00:00", None) == ("2026-09-03", "14:00")
    assert _split_date_time("2026-09-03", "09:00:00") == ("2026-09-03", "09:00")
    assert _split_date_time("2026-09-03", "09:00") == ("2026-09-03", "09:00")
    assert _split_date_time(None, None) == (None, None)


# ───────────────────────── 검수↔실행 정합 (cron 값) ─────────────────────────

def test_F54_1_validate_sees_cron_like_the_engine():
    from api_ibl import validate_code
    ok = validate_code('[self:trigger]{op: "create", name: "x", cron: "0 9 * * 1-5", do: "[sense:host]{op: \'status\'}"}')
    assert ok["valid"] is True, ok
    bad = validate_code('[self:trigger]{op: "create", name: "x", cron: "30 */2 * * *", do: "[sense:host]{op: \'status\'}"}')
    assert bad["valid"] is False
    assert any("cron/config" in (st.get("error") or "") for st in bad["steps"])
    bad2 = validate_code('[self:trigger]{op: "create", name: "x", config: {repeat: "once"}, do: "[sense:host]{op: \'status\'}"}')
    assert bad2["valid"] is False
    lst = validate_code('[self:trigger]{op: "list"}')
    assert lst["valid"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
