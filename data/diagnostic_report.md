# IndieBiz OS 진단 리포트
생성: 2026-06-17T08:44

## 시스템 상태: healthy
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 299.6GB 여유
- 최근 6시간 펄스: 6회 (마지막: 2026-06-17T08:44)

## 액션 건강
- 전체 137개: verified 112 | assumed 22 | failed 2
- 평균 성공률: 81.0%
- 성능 저하: self:recent_chats, sense:company, sense:navigate_route
- 속도 저하: engines:newspaper, limbs:music, self:run_pipeline
- 회복됨: engines:chart, engines:join, engines:merge, engines:sort, limbs:music

### 최근 7일 실패 빈도 Top
- [sense:kosis]: 15회 (마지막: 2026-06-17T07:35)
- [sense:stock]: 11회 (마지막: 2026-06-16T23:35)
- [engines:chart]: 4회 (마지막: 2026-06-15T12:44)
- [self:run_pipeline]: 4회 (마지막: 2026-06-17T07:29)
- [sense:world_bank]: 4회 (마지막: 2026-06-15T09:35)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 32회 → 36회
- 해마 점수: 0.728 → 0.721 stable
- EXECUTE 비율: 31% → 22%
- 평균 실행 라운드: 1.0 → 1.0 stable
- 평균 소요시간: 88.5s → 185.6s ⚠ declining
- 평가 달성률: 100% → 100%

## 추천 조치
1. [MEDIUM] 성능 저하 감지 4개: self:recent_chats, sense:company, sense:navigate_route
   → API 소스 또는 네트워크 상태 확인
2. [LOW] 응답 속도 저하 4개: engines:newspaper, limbs:music, self:run_pipeline
   → 외부 API 지연 또는 내부 병목 확인
