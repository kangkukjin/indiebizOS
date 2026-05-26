# IndieBiz OS 진단 리포트
생성: 2026-05-26T10:28

## 시스템 상태: healthy
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 44.9GB 여유
- 최근 6시간 펄스: 5회 (마지막: 2026-05-26T10:28)

## 액션 건강
- 전체 331개: verified 105 | assumed 224 | failed 2
- 평균 성공률: 89.1%
- 만성 실패: limbs:launch, others:channel_read, others:channel_search
- 속도 저하: self:list, sense:kr_investor, sense:search_pubmed
- 회복됨: self:list, self:read, sense:house_rent, sense:kr_investor, sense:weather

### 최근 7일 실패 빈도 Top
- [others:channel_search]: 5회 (마지막: 2026-05-26T07:27)
- [self:lecture_open]: 5회 (마지막: 2026-05-24T08:11)
- [others:ask_sync]: 4회 (마지막: 2026-05-26T07:27)
- [others:channel_read]: 4회 (마지막: 2026-05-26T07:27)
- [sense:kr_investor]: 4회 (마지막: 2026-05-26T09:08)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 48회 → 60회
- 해마 점수: 0.748 → 0.73 stable
- EXECUTE 비율: 30% → 20%
- 평균 실행 라운드: 3.92 → 6.88 ⚠ declining
- 평균 소요시간: 80.1s → 164.2s ⚠ declining
- 평가 달성률: 85% → 94%

## 추천 조치
1. [HIGH] 만성 실패 액션 3개: limbs:launch, others:channel_read, others:channel_search
   → 해당 패키지 handler.py 점검 필요
2. [LOW] 응답 속도 저하 3개: self:list, sense:kr_investor, sense:search_pubmed
   → 외부 API 지연 또는 내부 병목 확인
3. [MEDIUM] 실행 라운드 증가 추세 — 에이전트 효율 저하
   → 프롬프트 또는 도구 설명 점검
4. [LOW] 미확인 액션 224개 (67%) — 절반 이상 미검증
   → 건강 체크 확대 또는 수동 테스트 실행
