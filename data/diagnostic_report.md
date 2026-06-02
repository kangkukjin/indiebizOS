# IndieBiz OS 진단 리포트
생성: 2026-06-02T23:08

## 시스템 상태: warning
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 333.0GB 여유
- 최근 6시간 펄스: 6회 (마지막: 2026-06-02T22:21)

## 액션 건강
- 전체 199개: verified 128 | assumed 64 | failed 3
- 평균 성공률: 73.5%
- 만성 실패: self:run_pipeline, sense:kosis
- 성능 저하: engines:tts
- 속도 저하: limbs:player_status, others:channel_read, sense:book
- 회복됨: engines:publish_list, engines:web_catalog, sense:book, sense:commercial, sense:kr_investor

### 최근 7일 실패 빈도 Top
- [sense:realty]: 16회 (마지막: 2026-06-02T15:45)
- [sense:kosis]: 14회 (마지막: 2026-06-02T18:42)
- [self:run_pipeline]: 9회 (마지막: 2026-06-02T18:42)
- [others:channel_read]: 4회 (마지막: 2026-05-28T11:03)
- [sense:legal]: 4회 (마지막: 2026-05-28T11:03)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 64회 → 16회
- 해마 점수: 0.736 → 0.725 stable
- EXECUTE 비율: 26% → 12%
- 평균 실행 라운드: 6.51 → 1.0 ✅ improving
- 평균 소요시간: 157.5s → 249.3s ⚠ declining
- 평가 달성률: 94% → 100%

## 추천 조치
1. [HIGH] 만성 실패 액션 2개: self:run_pipeline, sense:kosis
   → 해당 패키지 handler.py 점검 필요
2. [MEDIUM] 성능 저하 감지 1개: engines:tts
   → API 소스 또는 네트워크 상태 확인
3. [LOW] 응답 속도 저하 8개: limbs:player_status, others:channel_read, sense:book
   → 외부 API 지연 또는 내부 병목 확인
