"""하드캡 요약 체크포인트 + 스케줄러 따라잡기 회귀 테스트 (2026-08-14)

두 결함의 재현 케이스를 남긴다 (dsh 조사 실측 대조에서 발굴):
  A. 히스토리 하드캡(시스템AI 7·사용자 5·위임 4턴) 밖으로 밀려난 턴이 읽히지도
     않고 소실 — "버리기만 하고 요약을 안 남긴다" → history_checkpoint 가
     경량 AI 요약 체크포인트를 유지하고 히스토리 머리에 주입.
  B. 스케줄러 daily/weekly/monthly/yearly 가 정확한 분 일치일 때만 발화 —
     그 분에 백엔드가 죽어 있으면(창 닫힘=백엔드 종료 생명주기) 그날 몫이
     조용히 결번 → 따라잡기(latest-only): 시각 경과 + 오늘 미실행이면 1회 발화.

실행: python3 backend/test_history_checkpoint.py
"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


def test_checkpoint_engine():
    import history_checkpoint as hc
    import conversation_db as cdb_mod
    # 결정론: 자동 트리거만 잠그고(스케줄=no-op) 주입 훅은 실물 유지
    cdb_mod.register_checkpoint_hooks(lambda *a, **k: None, hc._apply_pair)

    calls = []

    def fake_llm(prompt, system_prompt):
        calls.append(prompt)
        return ("## 핵심 사실과 결정\n- 테스트 요약 v%d\n## 미해결 과제\n(없음)\n"
                "## 다음 단계\n(없음)\n## 주의할 맥락\n(없음)" % len(calls))
    hc._call_llm = fake_llm

    from conversation_db import ConversationDB
    db = os.path.join(tempfile.mkdtemp(), 'conversations.db')
    cdb = ConversationDB(db)
    uid = cdb.get_or_create_agent('user', 'user')
    aid = cdb.get_or_create_agent('비서', 'ai_agent')
    key, fetch, keep = hc._pair_key(aid, uid), hc._fetch_pair(aid, uid), hc.KEEP_RECENT_PAIR

    def put(i):
        cdb.save_message(uid if i % 2 == 0 else aid, aid if i % 2 == 0 else uid, f'메시지{i}')

    # 1) 캡 이하 → noop, LLM 미호출
    for i in range(4):
        put(i)
    assert hc._update(db, key, keep, fetch) == 'noop' and not calls

    # 2) 캡 초과 → updated, 밀려난 행(0~4)만 요약 입력에
    for i in range(4, 10):
        put(i)
    assert hc._update(db, key, keep, fetch) == 'updated'
    assert '메시지0' in calls[0] and '메시지4' in calls[0]
    assert '메시지5' not in calls[0] and '메시지9' not in calls[0]

    # 3) covered_until 영속 + 무변경 재호출 noop
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT content, covered_until_id, last_error FROM history_checkpoints").fetchone()
    assert row[0].startswith('## 핵심') and row[1] > 0 and row[2] is None
    assert hc._update(db, key, keep, fetch) == 'noop' and len(calls) == 1

    # 4) 재귀 병합 — 기존 체크포인트가 입력에 동봉, 새 밀림(5~8)만
    for i in range(10, 14):
        put(i)
    assert hc._update(db, key, keep, fetch) == 'updated'
    assert '테스트 요약 v1' in calls[1] and '메시지5' in calls[1] and '메시지0' not in calls[1]

    # 5) 실패도 기록 — 옛 체크포인트 보존 + last_error
    hc._call_llm = lambda p, s: None
    for i in range(14, 18):
        put(i)
    assert hc._update(db, key, keep, fetch) == 'error:summary'
    row = conn.execute("SELECT content, last_error FROM history_checkpoints").fetchone()
    assert '테스트 요약 v2' in row[0] and row[1]

    # 6) 형식 비적합(섹션 헤더 없음) → 거부
    hc._call_llm = lambda p, s: '섹션 없는 응답'
    assert hc._update(db, key, keep, fetch) == 'error:summary'

    # 7) get_history_for_ai 머리 주입 + 역할 교대 유지 (연속 user 금지 — 프로바이더 호환)
    hist = cdb.get_history_for_ai(aid, uid)
    assert '[이전 대화 체크포인트' in hist[0]['content'] and '테스트 요약 v2' in hist[0]['content']
    roles = [h['role'] for h in hist]
    assert all(roles[i] != roles[i + 1] for i in range(len(roles) - 1))

    # 8) inject_head 분기: assistant 첫 항목=별도 삽입, 빈 히스토리=무변화
    head = {'role': 'user', 'content': 'CKPT'}
    out = hc.inject_head([{'role': 'assistant', 'content': 'a'}], head)
    assert out[0]['content'] == 'CKPT' and out[1]['content'] == 'a'
    assert hc.inject_head([], head) == []

    # 9) 선판정 게이트(SQL-only): 갱신 직후 False, 새 턴 2행이면 True
    hc._call_llm = fake_llm
    assert hc._update(db, key, keep, fetch) == 'updated'
    assert hc._precheck_needs_llm(db, key, keep, fetch) is False
    put(18); put(19)
    assert hc._precheck_needs_llm(db, key, keep, fetch) is True
    conn.close()
    print('OK checkpoint engine (9)')


def test_scheduler_catchup():
    from calendar_manager import CalendarManagerBase as CM
    cm = CM.__new__(CM)  # __init__ 우회 — 판정 로직만

    def chk(task, now_str, expect):
        assert cm._should_run_task(task, datetime.fromisoformat(now_str)) == expect, (task, now_str)

    # daily: 결번 따라잡기 / 오늘 실행됨 / 시각 전 / 정확한 분(회귀) / 무패딩
    chk({'repeat': 'daily', 'time': '04:00', 'action': 'x', 'last_run': '2026-08-13T04:00:05'},
        '2026-08-14T09:13:00', True)
    chk({'repeat': 'daily', 'time': '04:00', 'action': 'x', 'last_run': '2026-08-14T09:13:05'},
        '2026-08-14T10:00:00', False)
    chk({'repeat': 'daily', 'time': '04:00', 'action': 'x', 'last_run': '2026-08-12T04:00:05'},
        '2026-08-14T03:59:00', False)
    chk({'repeat': 'daily', 'time': '04:00', 'action': 'x', 'last_run': '2026-08-13T04:00:05'},
        '2026-08-14T04:00:30', True)
    chk({'repeat': 'daily', 'time': '4:00', 'action': 'x', 'last_run': '2026-08-13T04:00:05'},
        '2026-08-14T09:00:00', True)
    # weekly / none(일회성) / interval 첫 발화 / 빈 시간
    chk({'repeat': 'weekly', 'time': '04:00', 'weekdays': [0], 'action': 'x'},
        '2026-08-14T09:00:00', False)
    chk({'repeat': 'weekly', 'time': '04:00', 'weekdays': [4], 'action': 'x',
         'last_run': '2026-08-07T04:00:05'}, '2026-08-14T09:00:00', True)
    chk({'repeat': 'none', 'time': '08:00', 'date': '2026-08-14', 'action': 'x'},
        '2026-08-14T11:00:00', True)
    chk({'repeat': 'none', 'time': '08:00', 'date': '2026-08-14', 'action': 'x',
         'last_run': '2026-08-14T11:00:01'}, '2026-08-14T12:00:00', False)
    chk({'repeat': 'none', 'time': '08:00', 'date': '2026-08-13', 'action': 'x'},
        '2026-08-14T11:00:00', False)
    chk({'repeat': 'interval', 'time': '05:00', 'interval_hours': 6, 'action': 'x'},
        '2026-08-14T09:00:00', True)
    chk({'repeat': 'interval', 'time': '05:00', 'interval_hours': 6, 'action': 'x',
         'last_run': '2026-08-14T08:00:00'}, '2026-08-14T09:00:00', False)
    chk({'repeat': 'daily', 'time': '', 'action': 'x'}, '2026-08-14T09:00:00', False)
    print('OK scheduler catch-up (13)')


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
