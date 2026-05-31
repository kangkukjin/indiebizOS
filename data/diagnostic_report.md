# IndieBiz OS 진단 리포트
생성: 2026-05-31T12:14

## 시스템 상태: warning
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 45.6GB 여유
- 최근 6시간 펄스: 7회 (마지막: 2026-05-31T12:14)

## 액션 건강
- 전체 199개: verified 134 | assumed 57 | failed 3
- 평균 성공률: 66.7%
- 만성 실패: self:run_pipeline, sense:kosis
- 성능 저하: engines:newspaper
- 속도 저하: others:channel_read, sense:crawl, sense:kr_investor
- 회복됨: engines:publish_list, engines:web_catalog, sense:house_rent, sense:kr_investor, sense:legal

### 최근 7일 실패 빈도 Top
- [others:channel_read]: 12회 (마지막: 2026-05-28T11:03)
- [sense:kosis]: 7회 (마지막: 2026-05-30T15:05)
- [sense:kr_investor]: 5회 (마지막: 2026-05-28T09:20)
- [others:ask_sync]: 4회 (마지막: 2026-05-26T07:27)
- [sense:legal]: 4회 (마지막: 2026-05-28T11:03)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 51회 → 45회
- 해마 점수: 0.754 → 0.727 stable
- EXECUTE 비율: 13% → 24%
- 평균 실행 라운드: 9.39 → 1.0 ✅ improving
- 평균 소요시간: 134.7s → 191.8s ⚠ declining
- 평가 달성률: 86% → 100%

## 추천 조치
1. [HIGH] 만성 실패 액션 2개: self:run_pipeline, sense:kosis
   → 해당 패키지 handler.py 점검 필요
2. [MEDIUM] 성능 저하 감지 1개: engines:newspaper
   → API 소스 또는 네트워크 상태 확인
3. [LOW] 응답 속도 저하 5개: others:channel_read, sense:crawl, sense:kr_investor
   → 외부 API 지연 또는 내부 병목 확인
