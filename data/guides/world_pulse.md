# World Pulse — 오늘의 세계와 나 (자동 주입)
수집 시각: 2026-05-31T23:20

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
- 오늘 예정: 없음
- 저장소 여유: 42.3GB

## 시스템 건강
- scheduler: 정상
- channel_poller: 정상
- system_ai_runner: 정상
- ⚠ 비정상 액션 (3개): self:call, self:run_pipeline, sense:kosis

## 자가점검 패턴 분석
- 만성 실패: self:run_pipeline, sense:kosis
- 응답 느려짐: others:channel_read (0ms → 306ms)
- 응답 느려짐: sense:commercial (46ms → 199ms)
- 응답 느려짐: sense:kr_company (112ms → 254ms)
- 응답 느려짐: sense:kr_investor (108ms → 525ms)
- 응답 느려짐: sense:search_pubmed (1689ms → 3968ms)
- 응답 느려짐: sense:weather (1482ms → 4792ms)
- 복구됨: engines:publish_list, engines:web_catalog, sense:house_rent, sense:kr_disclosure, sense:kr_investor, sense:legal, sense:search_naver, sense:weather

## Digital Proprioception
- 메모리: 140.6MB
- CPU: 91.5%
- 스레드: 11개
- 태스크: 실행 0개 / 대기 0개

## 경제
- 코스피: 8476.15 (+3.5%) [2026-05-29]
- 코스닥: 1074.8 (-2.7%) [2026-05-29]
- S&P500: 7580.06 (+0.2%) [2026-05-29]
- 나스닥: 26972.62 (+0.2%) [2026-05-29]
- 원/달러: 1507.13 (+0.3%) [2026-05-29]
- 금: 4593.0 (+2.1%) [2026-05-29]
- 유가: 87.36 (-1.7%) [2026-05-29]
