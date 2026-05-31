# IndieBiz OS 진단 리포트
생성: 2026-05-31T23:46

## 시스템 상태: warning
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 42.3GB 여유
- 최근 6시간 펄스: 6회 (마지막: 2026-05-31T23:20)

## 액션 건강
- 전체 199개: verified 134 | assumed 58 | failed 3
- 평균 성공률: 67.4%
- 만성 실패: self:run_pipeline, sense:kosis
- 속도 저하: others:channel_read, sense:commercial, sense:kr_company
- 회복됨: engines:publish_list, engines:web_catalog, sense:house_rent, sense:kr_disclosure, sense:kr_investor

### 최근 7일 실패 빈도 Top
- [others:channel_read]: 12회 (마지막: 2026-05-28T11:03)
- [sense:kosis]: 8회 (마지막: 2026-05-31T22:20)
- [self:run_pipeline]: 5회 (마지막: 2026-05-31T22:21)
- [sense:kr_investor]: 5회 (마지막: 2026-05-28T09:20)
- [others:ask_sync]: 4회 (마지막: 2026-05-26T07:27)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 42회 → 43회
- 해마 점수: 0.738 → 0.732 stable
- EXECUTE 비율: 22% → 21%
- 평균 실행 라운드: 9.69 → 1.0 ✅ improving
- 평균 소요시간: 124.0s → 216.2s ⚠ declining
- 평가 달성률: 84% → 100%

## 추천 조치
1. [HIGH] 만성 실패 액션 2개: self:run_pipeline, sense:kosis
   → 해당 패키지 handler.py 점검 필요
2. [LOW] 응답 속도 저하 6개: others:channel_read, sense:commercial, sense:kr_company
   → 외부 API 지연 또는 내부 병목 확인
