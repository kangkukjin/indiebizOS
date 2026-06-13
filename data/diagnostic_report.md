# IndieBiz OS 진단 리포트
생성: 2026-06-13T14:58

## 시스템 상태: warning
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 307.8GB 여유
- 최근 6시간 펄스: 6회 (마지막: 2026-06-13T14:47)

## 액션 건강
- 전체 125개: verified 93 | assumed 27 | failed 5
- 평균 성공률: 77.2%
- 만성 실패: engines:chart, sense:kosis
- 성능 저하: self:time, sense:cctv, sense:legal
- 속도 저하: limbs:music
- 회복됨: limbs:music, others:messages, sense:crypto, sense:realty, sense:stock

### 최근 7일 실패 빈도 Top
- [sense:kosis]: 12회 (마지막: 2026-06-13T03:16)
- [self:run_pipeline]: 9회 (마지막: 2026-06-09T15:13)
- [engines:chart]: 3회 (마지막: 2026-06-13T03:16)
- [limbs:music]: 2회 (마지막: 2026-06-13T09:28)
- [sense:crypto]: 2회 (마지막: 2026-06-11T16:42)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 38회 → 2회
- 해마 점수: 0.734 → 0.711 데이터 부족
- EXECUTE 비율: 29% → 0%
- 평균 실행 라운드: 1.0 → 1.0 데이터 부족
- 평균 소요시간: 112.8s → 228.7s 데이터 부족
- 평가 달성률: 100% → 100%

## 추천 조치
1. [HIGH] 만성 실패 액션 2개: engines:chart, sense:kosis
   → 해당 패키지 handler.py 점검 필요
2. [MEDIUM] 성능 저하 감지 4개: self:time, sense:cctv, sense:legal
   → API 소스 또는 네트워크 상태 확인
3. [LOW] 응답 속도 저하 1개: limbs:music
   → 외부 API 지연 또는 내부 병목 확인
