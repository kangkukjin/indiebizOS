# IndieBiz OS 진단 리포트
생성: 2026-05-20T16:30

## 시스템 상태: healthy
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 48.8GB 여유
- 최근 6시간 펄스: 7회 (마지막: 2026-05-20T16:30)

## 액션 건강
- 전체 312개: verified 74 | assumed 230 | failed 0
- 평균 성공률: 87.9%
- 속도 저하: sense:navigate_route
- 회복됨: engines:slide

### 최근 7일 실패 빈도 Top
- [engines:slide]: 1회 (마지막: 2026-05-17T16:09)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 0회 → 52회
- 해마 점수: ? → 0.755 데이터 부족
- EXECUTE 비율: ? → 29%
- 평균 실행 라운드: ? → 4.9 데이터 부족
- 평균 소요시간: ? → 87.1s 데이터 부족
- 평가 달성률: ? → 75%

## 추천 조치
1. [LOW] 응답 속도 저하 1개: sense:navigate_route
   → 외부 API 지연 또는 내부 병목 확인
2. [LOW] 미확인 액션 230개 (73%) — 절반 이상 미검증
   → 건강 체크 확대 또는 수동 테스트 실행
