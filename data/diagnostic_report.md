# IndieBiz OS 진단 리포트
생성: 2026-06-10T23:10

## 시스템 상태: warning
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 316.3GB 여유
- 최근 6시간 펄스: 6회 (마지막: 2026-06-10T23:10)

## 액션 건강
- 전체 111개: verified 87 | assumed 23 | failed 1
- 평균 성공률: 74.1%
- 만성 실패: sense:kosis
- 성능 저하: sense:realty
- 속도 저하: engines:slide, others:channel_read, others:channel_send
- 회복됨: engines:slide, limbs:radio, self:trigger, sense:crypto

### 최근 7일 실패 빈도 Top
- [self:run_pipeline]: 13회 (마지막: 2026-06-09T15:13)
- [sense:kosis]: 10회 (마지막: 2026-06-10T15:13)
- [sense:stock]: 6회 (마지막: 2026-06-09T15:13)
- [others:channel_read]: 4회 (마지막: 2026-06-05T11:23)
- [others:channel_send]: 4회 (마지막: 2026-06-05T11:36)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 17회 → 32회
- 해마 점수: 0.725 → 0.728 stable
- EXECUTE 비율: 12% → 31%
- 평균 실행 라운드: 1.0 → 1.0 stable
- 평균 소요시간: 249.9s → 88.5s ✅ improving
- 평가 달성률: 100% → 100%

## 추천 조치
1. [HIGH] 만성 실패 액션 1개: sense:kosis
   → 해당 패키지 handler.py 점검 필요
2. [MEDIUM] 성능 저하 감지 1개: sense:realty
   → API 소스 또는 네트워크 상태 확인
3. [LOW] 응답 속도 저하 4개: engines:slide, others:channel_read, others:channel_send
   → 외부 API 지연 또는 내부 병목 확인
