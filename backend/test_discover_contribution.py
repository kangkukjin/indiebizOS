"""
해마 기반 실행기억 검증 스크립트

discover 제거 후 해마만으로 생성한 실행기억의 품질과 크기를 측정한다.

실행: cd backend && python3 test_discover_contribution.py
"""

import re
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibl_usage_rag import IBLUsageRAG, build_execution_memory


TEST_COMMANDS = [
    "삼성전자 주가 알려줘",
    "오늘 날씨 어때",
    "재즈 음악 틀어줘",
    "메모 저장해줘",
    "블로그에서 투자 관련 글 찾아줘",
    "삼전 요즘 어때",
    "고속도로 밀리나?",
    "아까 그거 이메일로 보내줘",
    "김 사장님 연락처 알려줘",
    "이거 잊지 마",
    "지난달 블로그 글 중에서 투자 관련 내용을 정리해서 이메일로 보내줘",
    "내일 오후 2시에 회의 일정 잡아줘",
    "유튜브에서 파이썬 강의 찾아서 저장해줘",
    "부동산 실거래가 조회해줘",
    "뉴스 검색해서 요약해줘",
    "스케줄러 상태 확인해줘",
    "NAS에서 음악 목록 보여줘",
    "사진 정리해줘",
    "할일 목록 보여줘",
    "CCTV 상태 확인",
    "환율 정보 알려줘",
    "근처 맛집 추천해줘",
    "택배 조회해줘",
    "번역해줘 이 문장",
    "파이썬 코드 실행해줘",
    "라디오 틀어줘",
    "법률 검색해줘 임대차 관련",
    "건강 기록 보여줘",
    "쇼핑 가격 비교해줘",
    "웹사이트 만들어줘",
]


def extract_actions(xml_str: str) -> set:
    """XML에서 [node:action] 패턴 추출"""
    if not xml_str:
        return set()
    return set(re.findall(r'\[([a-z_-]+):([a-z_-]+)\]', xml_str))


def run_test():
    rag = IBLUsageRAG()

    print("=" * 80)
    print("해마 기반 실행기억 검증 (discover 제거 후)")
    print("=" * 80)
    print()

    total_chars = 0
    total_actions = 0
    empty_count = 0
    times = []

    for i, cmd in enumerate(TEST_COMMANDS, 1):
        rag._cache = {}
        rag._cache_times = {}

        t0 = time.time()
        memory = build_execution_memory(cmd)
        elapsed = (time.time() - t0) * 1000

        mem_len = len(memory)
        actions = extract_actions(memory)
        total_chars += mem_len
        total_actions += len(actions)
        times.append(elapsed)

        if not memory:
            empty_count += 1

        action_str = ", ".join(f"[{n}:{a}]" for n, a in sorted(actions)) if actions else "(없음)"
        print(f"[{i:2d}] \"{cmd}\"")
        print(f"     {mem_len:,}자 | {len(actions)}액션 | {elapsed:.0f}ms | {action_str}")
        print()

    n = len(TEST_COMMANDS)
    print("=" * 80)
    print("종합 통계")
    print("=" * 80)
    print()
    print(f"  테스트 명령 수:        {n}")
    print(f"  빈 결과:               {empty_count}/{n}")
    print(f"  총 실행기억 크기:      {total_chars:,}자")
    print(f"  평균 크기:             {total_chars/n:,.0f}자/명령")
    print(f"  총 액션 수:            {total_actions}")
    print(f"  평균 액션 수:          {total_actions/n:.1f}/명령")
    print(f"  평균 응답 시간:        {sum(times)/n:.0f}ms")
    print(f"  최대 응답 시간:        {max(times):.0f}ms")
    print()

    # 이전 결과와 비교 (하드코딩)
    prev_total = 39666  # discover 포함 시 총 크기
    prev_avg = 1322     # discover 포함 시 평균
    print("── discover 포함 시 대비 ──")
    print(f"  이전 평균 크기:        {prev_avg:,}자/명령")
    print(f"  현재 평균 크기:        {total_chars/n:,.0f}자/명령")
    print(f"  절감:                  {prev_avg - total_chars/n:,.0f}자/명령 ({(1 - total_chars/n/prev_avg)*100:.1f}%)")
    print()


if __name__ == "__main__":
    run_test()
