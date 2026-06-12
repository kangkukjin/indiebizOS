# IndieBiz OS 진단 리포트
생성: 2026-06-12T21:37

## 시스템 상태: warning
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 309.3GB 여유
- 최근 6시간 펄스: 6회 (마지막: 2026-06-12T21:37)

## 액션 건강
- 전체 122개: verified 93 | assumed 26 | failed 3
- 평균 성공률: 77.4%
- 만성 실패: engines:chart, sense:kosis
- 속도 저하: sense:crawl
- 회복됨: others:messages, sense:crypto, sense:realty, sense:stock, sense:weather

### 최근 7일 실패 빈도 Top
- [sense:kosis]: 12회 (마지막: 2026-06-12T15:15)
- [self:run_pipeline]: 10회 (마지막: 2026-06-09T15:13)
- [engines:chart]: 2회 (마지막: 2026-06-12T15:15)
- [sense:crypto]: 2회 (마지막: 2026-06-11T16:42)
- [limbs:phone]: 1회 (마지막: 2026-06-12T00:25)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 28회 → 15회
- 해마 점수: 0.742 → 0.711 stable
- EXECUTE 비율: 39% → 7%
- 평균 실행 라운드: 1.0 → 1.0 stable
- 평균 소요시간: 134.0s → 76.0s ✅ improving
- 평가 달성률: 100% → 100%

## 추천 조치
1. [HIGH] 만성 실패 액션 2개: engines:chart, sense:kosis
   → 해당 패키지 handler.py 점검 필요
2. [LOW] 응답 속도 저하 1개: sense:crawl
   → 외부 API 지연 또는 내부 병목 확인
