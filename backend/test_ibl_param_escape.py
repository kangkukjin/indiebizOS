r"""IBL 파라미터 문자열 이스케이프·침묵 절단 회귀 테스트 (2026-08-22)

ep1396(유튜브 AI 팁 보고서) 쓰기 경로 추적에서 나온 두 결함:

    E1. 느슨한 폴백이 `\n` 을 글자 `n` 으로 뭉갬       → 표준 이스케이프 해석
    E2. 값 안의 날 따옴표에서 content 가 조용히 절단  → IBLSyntaxError 정직 거절
    E3. 모르는 이스케이프(`\d` 등)가 글자로 뭉개짐     → 백슬래시째 보존
    E4. 조건 참조식이 파라미터 손실을 params={} 로 눙침 → None(유효하지 않은 참조)

배경: data/guides/youtube_ai_tips_report.md 2026-08-20 실측 ① — 이 결함 때문에
보고서 쓰기가 IBL 어휘를 떠나 Bash 히어독으로 이탈해 있었다.

실행: python3 backend/test_ibl_param_escape.py
"""
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401 — 층 디렉토리 등재


# 느슨한 폴백을 반드시 타도록: JSON5 가 해석 못하는 모양(따옴표 없는 한글 키)
BS = chr(92)














def test_e4_condition_ref_does_not_swallow():
    """E4: 조건 참조식이 파라미터 손실을 params={} 로 눙치지 않는다."""
    from ibl_exec_sense import _parse_source_ref
    got = _parse_source_ref('sense:stock{ticker: "N"VDA"}.price')
    assert got is None or got[2].get("ticker"), (
        "파라미터를 잃은 채 유효한 참조인 척했다: %r" % (got,)
    )






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
