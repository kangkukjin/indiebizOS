# IndieBiz OS 진단 리포트
생성: 2026-06-21T17:36

## 시스템 상태: healthy
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 284.1GB 여유
- 최근 6시간 펄스: 2회 (마지막: 2026-06-21T17:35)

## 액션 건강
- 전체 140개: verified 108 | assumed 30 | failed 1
- 평균 성공률: 83.6%
- 성능 저하: self:recent_chats
- 속도 저하: engines:groupby, engines:image_critic, engines:newspaper
- 회복됨: engines:chart, engines:groupby, engines:join, engines:merge, engines:sort

### 최근 7일 실패 빈도 Top
- [sense:stock]: 12회 (마지막: 2026-06-17T20:51)
- [sense:kosis]: 7회 (마지막: 2026-06-17T07:35)
- [engines:chart]: 5회 (마지막: 2026-06-17T19:14)
- [engines:groupby]: 5회 (마지막: 2026-06-17T16:41)
- [self:grep]: 4회 (마지막: 2026-06-18T11:32)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 7회 → 68회
- 해마 점수: 0.747 → 0.726 stable
- EXECUTE 비율: 0% → 16%
- 평균 실행 라운드: 1.0 → 1.0 stable
- 평균 소요시간: 140.2s → 195.7s ⚠ declining
- 평가 달성률: 100% → 100%

## 추천 조치
1. [MEDIUM] 성능 저하 감지 1개: self:recent_chats
   → API 소스 또는 네트워크 상태 확인
2. [LOW] 응답 속도 저하 12개: engines:groupby, engines:image_critic, engines:newspaper
   → 외부 API 지연 또는 내부 병목 확인
