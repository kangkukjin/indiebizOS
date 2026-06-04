# IndieBiz OS 진단 리포트
생성: 2026-06-04T12:06

## 시스템 상태: healthy
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 321.4GB 여유
- 최근 6시간 펄스: 4회 (마지막: 2026-06-04T12:06)

## 액션 건강
- 전체 144개: verified 88 | assumed 50 | failed 6
- 평균 성공률: 82.7%
- 만성 실패: self:run_pipeline, sense:collect_sites, sense:crypto, sense:kosis
- 성능 저하: engines:tts, sense:paper
- 속도 저하: engines:newspaper, self:manage_events, self:storage
- 회복됨: engines:slide_shadcn, limbs:music, self:trigger, sense:book, sense:cctv

### 최근 7일 실패 빈도 Top
- [sense:kosis]: 16회 (마지막: 2026-06-03T14:17)
- [sense:realty]: 16회 (마지막: 2026-06-02T15:45)
- [self:run_pipeline]: 13회 (마지막: 2026-06-03T14:17)
- [sense:crypto]: 7회 (마지막: 2026-06-04T04:53)
- [sense:stock]: 7회 (마지막: 2026-06-04T04:30)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 63회 → 15회
- 해마 점수: 0.725 → 0.749 stable
- EXECUTE 비율: 25% → 33%
- 평균 실행 라운드: 5.24 → 1.0 ✅ improving
- 평균 소요시간: 163.7s → 209.7s ⚠ declining
- 평가 달성률: 93% → 100%

## 추천 조치
1. [HIGH] 만성 실패 액션 4개: self:run_pipeline, sense:collect_sites, sense:crypto, sense:kosis
   → 해당 패키지 handler.py 점검 필요
2. [MEDIUM] 성능 저하 감지 2개: engines:tts, sense:paper
   → API 소스 또는 네트워크 상태 확인
3. [LOW] 응답 속도 저하 6개: engines:newspaper, self:manage_events, self:storage
   → 외부 API 지연 또는 내부 병목 확인
