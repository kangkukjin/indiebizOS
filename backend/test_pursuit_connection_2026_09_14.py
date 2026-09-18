"""3793 회귀: 전체 목표와 하위 작업의 구별. CASES는 실제 모델 대조에도 사용한다."""
import boot_paths  # noqa: F401
from types import SimpleNamespace
import json
import pytest

import pursuit_bind as pb
from pursuit_tools import execute_pursuit


TRIP_ID = "pursuit_" + "1" * 32
REPORT_ID = "pursuit_" + "2" * 32
OTHER_ID = "pursuit_" + "3" * 32
TRIP = {
    "id": TRIP_ID, "title": "9/16~17 속초 가족여행", "status": "active",
    "goal_criteria": "9/16~17 속초 가족여행의 실행 가능한 일정을 완성한다. "
                     "체스터톤스 호텔에 1박하며 어머니와 함께 이동한다. 숙박·식사·동선의 조건을 확인한다.",
    "next": "9/17 아침 식당을 고르면 오전 동선을 정리한다.",
    "progress": "호텔 근처 조기 개점 식당을 조사했다.",
    "framing": "목요일 아침 일찍 문 여는 식당을 찾는다.",
}
REPORT = {
    "id": REPORT_ID, "title": "월별 보고서", "status": "active",
    "goal_criteria": "서울 월별 매출 자료를 모아 한국어 보고서와 PDF를 완성한다.",
    "next": "매출 자료의 중복 행을 제거한다.", "framing": "매출 원본 정리",
}
HOTEL_HISTORY = [
    {"role": "user", "content": "우리가 가는 호텔방은 요리도 할 수 있는 방인가?"},
    {"role": "assistant", "content": "체스터톤스 예약 객실은 취사 금지입니다."},
    {"role": "user", "content": "아침을 나가서 먹는다면 일찍 문 여는 곳이 호텔 근처에 있나?"},
    {"role": "assistant", "content": "9/17 목요일 아침 식당 후보를 정리했습니다."},
]
CASES = [
    {"name": "3793_checkin_after_breakfast", "rows": [TRIP, REPORT], "history": HOTEL_HISTORY,
     "message": "우리가 묵는 호텔에 온라인 체크인할 수 있다는데 어떻게 하는지 설명해줘.",
     "selected": TRIP_ID, "review_id": TRIP_ID, "action": "keep"},
    {"name": "unlisted_preparation", "rows": [TRIP], "history": HOTEL_HISTORY,
     "message": "어머니가 걷기 힘드시면 그 호텔에 휠체어를 빌릴 수 있는지도 알아봐줘.",
     "selected": TRIP_ID, "review_id": TRIP_ID, "action": "keep"},
    {"name": "same_goal_next_stage", "rows": [REPORT, TRIP],
     "history": [{"role": "assistant", "content": "서울 매출 자료의 중복을 정리했습니다."}],
     "message": "그 보고서를 PDF로 내보낼 때 글자가 깨지지 않게 하려면?",
     "selected": REPORT_ID, "review_id": REPORT_ID, "action": "keep"},
    {"name": "added_deliverable", "rows": [REPORT], "history": [],
     "message": "서울 월별 매출 보고서에 영문 번역본도 산출물로 추가해줘.",
     "selected": REPORT_ID, "review_id": REPORT_ID, "action": "amend"},
    {"name": "same_goal_correction", "rows": [REPORT], "history": [],
     "message": "그 월별 보고서 대상은 서울이 아니라 부산이야. 잘못 말했어.",
     "selected": REPORT_ID, "review_id": REPORT_ID, "action": "rewrite"},
    {"name": "other_trip_same_domain", "rows": [TRIP], "history": HOTEL_HISTORY,
     "message": "이번 속초 여행 말고, 다음 달 혼자 가는 제주 출장 호텔을 새로 추천해줘.",
     "selected": None, "review_id": TRIP_ID, "action": "detach"},
    {"name": "3762_unrelated_followup", "rows": [REPORT],
     "history": [{"role": "user", "content": "제주 방문 증가와 당시 정책은?"},
                 {"role": "assistant", "content": "관광과 투자를 나누어 제주 정책을 조사했습니다."}],
     "message": "그런데 부정적인 여론에도 제주 방문이 계속되는 이유는?",
     "selected": None, "review_id": REPORT_ID, "action": "detach"},
    {"name": "ambiguous_hotel", "rows": [TRIP, {
        "id": OTHER_ID, "title": "10월 제주 출장", "status": "active",
        "goal_criteria": "10월 제주 출장의 항공·호텔과 업무 일정을 준비한다.",
        "next": "호텔 예약 확인"}], "history": [],
     "message": "그 호텔 온라인 체크인은 어떻게 하지?",
     "selected": None, "review_id": TRIP_ID, "action": "detach"},
]


def test_goal_based_connection_can_record_new_subtopic(tmp_path, monkeypatch):
    """모델 의미 판정은 별도 실측. 여기서는 입력 경계와 연결 후 원장 쓰기를 검증한다."""
    from pursuit_ledger import PursuitLedger
    ledger = PursuitLedger(tmp_path / "pursuits.db", "agent")
    row = ledger.create(TRIP["title"], TRIP["goal_criteria"], "origin",
                        framing=TRIP["framing"], next=TRIP["next"],
                        framing_meta={"imagined_ibl": "OLD_EXECUTION_PLAN"},
                        artifacts=["LARGE_OLD_TOOL_RESULT"])
    other = ledger.create("10월 제주 출장", "10월 제주 출장의 항공·호텔을 준비한다.", "other")
    b = pb.Binding(SimpleNamespace(), ledger, "agent", "checkin_turn",
                   CASES[0]["message"], HOTEL_HISTORY)
    b.aliases = {"agent"}
    prompts = []

    def judgment(prompt, *, kind):
        prompts.append((kind, prompt))
        payload = json.loads(prompt.split("판단 자료:\n", 1)[1].split("\n판단 자료 끝", 1)[0])
        if kind == "selection":
            candidate = next(r for r in payload["candidates"] if r["id"] == row["id"])
            assert candidate["goal_criteria"] == row["goal_criteria"]
            return {"id": row["id"]}
        assert payload["pursuit"]["identity"]["goal_criteria"] == row["goal_criteria"]
        assert payload["pursuit"]["recent_work"]["next"] == row["next"]
        assert "OLD_EXECUTION_PLAN" not in prompt and "LARGE_OLD_TOOL_RESULT" not in prompt
        assert payload["recent_dialogue"] == HOTEL_HISTORY
        assert payload["other_candidates"][0]["goal_criteria"] == other["goal_criteria"]
        return {"action": "keep", "criteria": "", "evidence": "같은 숙박의 이용 준비"}

    monkeypatch.setattr(pb, "ask_json", judgment)
    token = pb._current.set(b)
    try:
        memory, needs_review = pb.prepare()
        assert b.row["id"] == row["id"] and not needs_review
        assert [kind for kind, _ in prompts] == ["selection", "review"]
        result = json.loads(execute_pursuit({"op": "note", "id": row["id"],
                                           "progress": "온라인 체크인 방법 확인"}, "agent"))
        assert result["success"]
        updated = ledger.get(row["id"])
        assert updated["goal_criteria"] == row["goal_criteria"]
        assert updated["progress"] == "온라인 체크인 방법 확인"
        assert row["id"] in memory
    finally:
        pb._current.reset(token)


def test_connection_prompt_never_silently_shortens_goal():
    goal = "전체 완료 조건. " * 120 + "중요한 마지막 대상"
    candidate = {**REPORT, "goal_criteria": goal}
    for selected in (None, candidate):
        prompt = pb.connection_prompt("이어줘", [], [candidate], selected=selected)
        assert goal in prompt


def test_selection_evidence_reaches_judgment_record(monkeypatch):
    evidence = "최근 대화의 숙박 대상과 같은 호텔의 이용 준비"
    monkeypatch.setattr("consciousness_agent.oneshot_ai_call", lambda *a, **k:
                        json.dumps({"evidence": evidence, "id": TRIP_ID}, ensure_ascii=False))
    events = []
    monkeypatch.setattr("episode_logger.record_trajectory_event", lambda kind, data: events.append((kind, data)))
    result = pb.ask_json("선택", kind="selection")
    assert result["id"] == TRIP_ID
    assert events[0][1]["decision"]["evidence"] == evidence


@pytest.mark.parametrize("answer", [{"id": TRIP_ID, "evidence": []},
                                    {"id": TRIP_ID, "action": "keep"}])
def test_selection_rejects_wrong_evidence_type_and_review_fields(answer):
    with pytest.raises(ValueError):
        pb._validate_answer(answer, "selection")


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
