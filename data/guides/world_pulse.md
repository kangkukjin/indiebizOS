# World Pulse — 오늘의 세계와 나 (자동 주입)
수집 시각: 2026-05-26T21:59

> 이 정보는 대화 시작 시 시스템 프롬프트에 자동 포함됩니다.
> 사용자가 '요즘 세상은 어때', '오늘 경제 상황' 등을 물으면
> 아래 데이터를 바로 활용하여 답하세요.
> [sense:world_refresh]나 read_guide 호출은 불필요합니다.

## 사용자
- 이름: 강국진
- 직업: 물리학자, 작가
- 관심사: AI OS 개발, 정치, 물리학, 철학
- 메모: 시스템에는 사용자가 작성해온 블로그 데이터를 볼 수 있는 기능이 있다. 
사용자는 한국인 남성으로 1969년생이다. 
- 위치: Cheongju

## 시스템 상태
- 프로젝트 22개, 에이전트 31개 활성
- 최근 대화: sense:kr_investor가 작동 안하는 걸 다시 (시스템 AI)
- 오늘 예정: 없음
- 저장소 여유: 46.1GB

## 시스템 건강
- scheduler: 정상
- channel_poller: 정상
- system_ai_runner: 정상
- ⚠ 비정상 액션 (4개): engines:chart, engines:lecture_plan, others:channel_read, others:channel_search

## 자가점검 패턴 분석
- 만성 실패: limbs:launch, others:channel_read, others:channel_search
- 응답 느려짐: self:lecture_open (5ms → 844ms)
- 응답 느려짐: self:list (1ms → 2ms)
- 응답 느려짐: sense:kr_investor (21ms → 570ms)
- 응답 느려짐: sense:search_pubmed (1689ms → 3968ms)
- 복구됨: self:list, self:read, sense:house_rent, sense:kr_investor, sense:weather

## Digital Proprioception
- 메모리: 375.1MB
- CPU: 21.1%
- 스레드: 20개
- 태스크: 실행 0개 / 대기 0개

## 경제
- 코스피: 8047.51 (+2.5%) [2026-05-26]
- 코스닥: 1172.52 (+1.0%) [2026-05-26]
- S&P500: 7473.47 (+0.4%) [2026-05-22]
- 나스닥: 26343.97 (+0.2%) [2026-05-22]
- 원/달러: 1504.25 (-0.6%) [2026-05-26]
- 금: 4519.2 (-0.0%) [2026-05-26]
- 유가: 92.64 (-4.1%) [2026-05-26]
