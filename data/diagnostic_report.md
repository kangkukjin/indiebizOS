# IndieBiz OS 진단 리포트
생성: 2026-06-15T15:18

## 시스템 상태: warning
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 306.0GB 여유
- 최근 6시간 펄스: 6회 (마지막: 2026-06-15T15:18)

## 액션 건강
- 전체 133개: verified 103 | assumed 26 | failed 3
- 평균 성공률: 77.6%
- 만성 실패: sense:kosis
- 성능 저하: self:recent_chats, sense:navigate_route, sense:search_books
- 속도 저하: engines:newspaper, limbs:music, self:read
- 회복됨: engines:chart, limbs:music, others:messages, others:neighbor, self:health

### 최근 7일 실패 빈도 Top
- [sense:kosis]: 14회 (마지막: 2026-06-15T11:22)
- [engines:chart]: 4회 (마지막: 2026-06-15T12:44)
- [sense:world_bank]: 4회 (마지막: 2026-06-15T09:35)
- [self:run_pipeline]: 3회 (마지막: 2026-06-09T15:13)
- [sense:host]: 3회 (마지막: 2026-06-15T09:19)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 34회 → 7회
- 해마 점수: 0.725 → 0.747 stable
- EXECUTE 비율: 29% → 0%
- 평균 실행 라운드: 1.0 → 1.0 stable
- 평균 소요시간: 97.2s → 140.2s ⚠ declining
- 평가 달성률: 100% → 100%

## 추천 조치
1. [HIGH] 만성 실패 액션 1개: sense:kosis
   → 해당 패키지 handler.py 점검 필요
2. [MEDIUM] 성능 저하 감지 3개: self:recent_chats, sense:navigate_route, sense:search_books
   → API 소스 또는 네트워크 상태 확인
3. [LOW] 응답 속도 저하 4개: engines:newspaper, limbs:music, self:read
   → 외부 API 지연 또는 내부 병목 확인
