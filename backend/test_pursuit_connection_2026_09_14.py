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


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_current_model_connection_preserves_goal_and_unrelated_turns(tmp_path, monkeypatch, case):
    from pursuit_ledger import PursuitLedger
    ledger = PursuitLedger(tmp_path / "pursuits.db", "agent")
    mapping = {}
    for i, candidate in enumerate(case["rows"]):
        mapping[candidate["id"]] = ledger.create(candidate["title"], candidate["goal_criteria"], f"seed{i}")
    b = pb.Binding(SimpleNamespace(), ledger, "agent", "turn", case["message"], case["history"])
    b.aliases = {"agent"}
    monkeypatch.setattr(pb, "ask_json", lambda *a, **k: pytest.fail("별도 연결 모델 금지"))
    token = pb._current.set(b)
    try:
        assert pb.prepare() and b.row is None
        # 의미 판정 자체를 시험 대역이 증명하지는 않는다. 선택을 받은 뒤 원장 경계를 검증한다.
        if case["selected"]:
            row = mapping[case["selected"]]
            result = json.loads(execute_pursuit({"op": "bind", "id": row["id"],
                                               "why": case["message"]}, "agent"))
            assert result["success"] and result["result"]["goal_criteria"] == row["goal_criteria"]
            note = json.loads(execute_pursuit({"op": "note", "progress": "현재 후속 질문 확인"}, "agent"))
            assert note["success"] and ledger.get(row["id"])["goal_criteria"] == row["goal_criteria"]
        else:
            assert pb.finish("현재 질문의 답변") is None
            assert all(not ledger.turns(row["id"]) for row in mapping.values())
    finally:
        pb._current.reset(token)


def test_catalog_excerpts_are_explicit_and_full_goal_is_available(tmp_path):
    from pursuit_ledger import PursuitLedger
    goal = "전체 완료 조건. " * 120 + "중요한 마지막 대상"
    ledger = PursuitLedger(tmp_path / "pursuits.db", "agent")
    row = ledger.create("긴 목표", goal, "seed")
    text = pb.render_index([row], 1)
    assert "목표 발췌" in text and "bind/read" in text
    assert ledger.get(row["id"])["goal_criteria"] == goal


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
