"""
해마 기반 실행기억 검증 스크립트

discover 제거 후 해마만으로 생성한 실행기억의 품질과 크기를 측정한다.

실행: cd backend && python3 test_discover_contribution.py
"""

import re
import sys
import os
import time

try:
    import pytest
except ImportError:  # pytest 없는 몸(폰) — 스크립트 실행 경로
    pytest = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401 — 층 디렉토리 등재 (물리 이동 2026-08-05)

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



def _hippocampus_unavailable():
    """해마 회상이 원리적으로 불가능한 환경이면 그 사유, 가능하면 None.

    ①교재 DB 파일이 없거나 비었다 ②시맨틱 인덱스를 못 연다 — 둘 다 '이 몸에 해마가
    아직 없다'는 뜻이지 회상 품질의 회귀가 아니다."""
    try:
        import ibl_usage_db
        # ★경로 정본 = 모듈 상수 DB_PATH. 종전의 getattr(db, "db_path", None) 은 존재하지
        #   않는 속성이라 항상 None 이었고, sqlite3.connect(str(None)) 이 cwd 에 `None`
        #   파일을 만들며(빈 DB) "테이블 부재"로 **라이브에서도** skip 시켰다 — 판별자가
        #   결함이면 skip 이 아니라 실패해야 한다.
        path = getattr(ibl_usage_db, "DB_PATH", None)
        assert path, "판별자 결함: ibl_usage_db.DB_PATH 가 없다 — skip 으로 덮지 말 것"
        if not os.path.exists(str(path)):
            return f"해마 DB 없음({path}) — 이 몸엔 교재가 아직 없다"
        import sqlite3
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)  # ro — 판별자가 파일을 만들면 안 된다
            n = con.execute("SELECT COUNT(*) FROM ibl_examples").fetchone()[0]
            con.close()
        except Exception:
            return "해마 DB 를 읽을 수 없다(테이블 부재) — 부재이지 회귀가 아니다"
        if n == 0:
            return "해마 교재 0건 — 회상할 것이 없다"
    except AssertionError:
        raise
    except Exception as e:  # noqa: BLE001
        return f"해마 모듈을 열 수 없다: {type(e).__name__}"
    return None

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
        memory, _, _ = build_execution_memory(cmd)
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

    return {"n": n, "empty_count": empty_count,
            "total_chars": total_chars, "total_actions": total_actions}


def _hippo_data_ready() -> bool:
    """해마 DB 존재 여부 — 없는 환경(CI·신선 설치)에선 스킵."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.exists(os.path.join(root, "data", "ibl_usage.db"))


try:
    import pytest

    @pytest.mark.local
    @pytest.mark.skipif(not _hippo_data_ready(), reason="해마 DB 없음 (data/ibl_usage.db)")
    def test_hippocampus_recall_quality():
        """해마 회상이 대다수 명령에 실행기억을 내놓는지 (측정 스크립트의 pytest 편입, 감사 ⑧)."""
        # ★환경 부재는 실패가 아니다(2026-08-24 #repair C7). 격리 사본·CI 에는 해마 DB 와
        #   임베딩 모델이 없어 회상이 30/30 으로 비고, 그 빨강을 회차마다 사람이 "환경 탓"
        #   이라고 설명해 왔다. 부재를 감지해 skip(사유) 로 말하게 한다 — 부재와 회귀는
        #   다른 사건이고, 그 구별은 시험이 스스로 해야 한다.
        _why = _hippocampus_unavailable()
        if _why:
            pytest.skip(_why)
        stats = run_test()
        # 30개 일상 명령 중 빈 회상이 다수면 해마 인덱스/모델 회귀
        assert stats["empty_count"] <= stats["n"] // 3, \
            f"빈 실행기억 {stats['empty_count']}/{stats['n']} — 해마 인덱스·임베딩 모델 확인"
        assert stats["total_actions"] > 0
except ImportError:  # pytest 없는 환경(폰 등)에서도 스크립트 직접 실행은 가능해야 함
    pass


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # 이 파일의 pytest 시험은 같은 `run_test()` 를 **같은 프로세스에서** 부르므로 위임해도
    # 재귀하지 않는다. 위임하면 해마 DB 가 없는 환경에서 조용히 성공하는 대신 pytest 가
    # `skipped` 라고 **말해 준다**(부재와 통과를 구별하는 것이 이 규약의 요점).
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:                          # pytest 없는 환경(폰 등)은 스크립트로
        raise SystemExit(0 if run_test() is not None else 1)
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
