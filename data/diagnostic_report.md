# IndieBiz OS 진단 리포트
생성: 2026-04-20T11:12

## 시스템 상태: warning
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 46.7GB 여유
- 최근 6시간 펄스: 2회 (마지막: 2026-04-20T11:12)

## 액션 건강
- 전체 311개: verified 56 | assumed 244 | failed 0
- 평균 성공률: 79.8%

### 최근 7일 실패 빈도 Top
- [limbs:os_open]: 3회 (마지막: 2026-04-19T15:46)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 48회 → 41회
- 해마 점수: 0.658 → 0.591 ⚠ declining
- EXECUTE 비율: 23% → 29%
- 평균 실행 라운드: 3.67 → 2.17 ✅ improving
- 평균 소요시간: 128.5s → 112.3s ✅ improving
- 평가 달성률: 90% → 52%

## 추천 조치
1. [MEDIUM] 해마 점수 하락 추세 — 용례 사전 보강 또는 재학습 검토
   → ibl_usage_db 용례 확인, 필요시 ibl_embedding_trainer.py 실행
2. [LOW] 미확인 액션 244개 (78%) — 절반 이상 미검증
   → 건강 체크 확대 또는 수동 테스트 실행
