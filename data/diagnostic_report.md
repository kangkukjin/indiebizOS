# IndieBiz OS 진단 리포트
생성: 2026-05-28T11:15

## 시스템 상태: healthy
- 서비스: scheduler ✅ | channel_poller ✅ | system_ai_runner ✅
- 디스크: 45.7GB 여유
- 최근 6시간 펄스: 4회 (마지막: 2026-05-28T11:15)

## 액션 건강
- 전체 195개: verified 115 | assumed 80 | failed 0
- 평균 성공률: 89.8%
- 만성 실패: limbs:launch
- 성능 저하: engines:newspaper
- 속도 저하: others:channel_read, self:lecture_open, self:list
- 회복됨: self:list, self:read, sense:house_rent, sense:kr_investor, sense:search_naver

### 최근 7일 실패 빈도 Top
- [others:channel_read]: 12회 (마지막: 2026-05-28T11:03)
- [self:lecture_open]: 6회 (마지막: 2026-05-26T13:57)
- [sense:kr_investor]: 5회 (마지막: 2026-05-28T09:20)
- [others:ask_sync]: 4회 (마지막: 2026-05-26T07:27)
- [sense:legal]: 4회 (마지막: 2026-05-28T11:03)

## 인지 품질 (최근 7일 vs 이전 7일)
- 에피소드: 54회 → 63회
- 해마 점수: 0.752 → 0.725 stable
- EXECUTE 비율: 29% → 25%
- 평균 실행 라운드: 5.15 → 5.24 stable
- 평균 소요시간: 88.2s → 163.7s ⚠ declining
- 평가 달성률: 86% → 93%

## 추천 조치
1. [HIGH] 만성 실패 액션 1개: limbs:launch
   → 해당 패키지 handler.py 점검 필요
2. [MEDIUM] 성능 저하 감지 1개: engines:newspaper
   → API 소스 또는 네트워크 상태 확인
3. [LOW] 응답 속도 저하 7개: others:channel_read, self:lecture_open, self:list
   → 외부 API 지연 또는 내부 병목 확인
