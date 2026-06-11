# IndieBiz OS 진단 리포트
생성: 2026-06-11T22:24

## 시스템 상태: warning
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 312.1GB 여유
- 최근 6시간 펄스: 6회 (마지막: 2026-06-11T22:24)

## 액션 건강
- 전체 111개: verified 88 | assumed 21 | failed 2
- 평균 성공률: 76.4%
- 만성 실패: sense:kosis
- 속도 저하: others:channel_read, others:channel_send, sense:crawl
- 회복됨: limbs:radio, sense:crypto, sense:realty, sense:stock, sense:weather

### 최근 7일 실패 빈도 Top
- [self:run_pipeline]: 13회 (마지막: 2026-06-09T15:13)
- [sense:kosis]: 12회 (마지막: 2026-06-11T15:14)
- [others:channel_read]: 4회 (마지막: 2026-06-05T11:23)
- [others:channel_send]: 4회 (마지막: 2026-06-05T11:36)
- [sense:crypto]: 3회 (마지막: 2026-06-11T16:42)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 15회 → 28회
- 해마 점수: 0.747 → 0.737 stable
- EXECUTE 비율: 40% → 21%
- 평균 실행 라운드: 1.0 → 1.0 stable
- 평균 소요시간: 136.2s → 101.7s ✅ improving
- 평가 달성률: 100% → 100%

## 추천 조치
1. [HIGH] 만성 실패 액션 1개: sense:kosis
   → 해당 패키지 handler.py 점검 필요
2. [LOW] 응답 속도 저하 3개: others:channel_read, others:channel_send, sense:crawl
   → 외부 API 지연 또는 내부 병목 확인
