# World Pulse — 오늘의 세계와 나 (자동 주입)
수집 시각: 2026-06-02T22:22

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
- 프로젝트 24개, 에이전트 33개 활성
- 오늘 예정: 없음
- 저장소 여유: 333.0GB

## 시스템 건강
- scheduler: 정상
- channel_poller: 정상
- system_ai_runner: 정상
- ⚠ 비정상 액션 (3개): engines:tts, self:run_pipeline, sense:kosis

## 자가점검 패턴 분석
- 만성 실패: self:run_pipeline, sense:kosis
- 성공률 하락: engines:tts (100% → 0%)
- 응답 느려짐: limbs:player_status (0ms → 0ms)
- 응답 느려짐: others:channel_read (2ms → 711ms)
- 응답 느려짐: sense:book (261ms → 616ms)
- 응답 느려짐: sense:commercial (116ms → 1497ms)
- 응답 느려짐: sense:gutenberg_books (10731ms → 28176ms)
- 응답 느려짐: sense:kr_company (112ms → 254ms)
- 응답 느려짐: sense:legal (3ms → 409ms)
- 응답 느려짐: sense:search_books (392ms → 980ms)
- 복구됨: engines:publish_list, engines:web_catalog, sense:book, sense:commercial, sense:kr_investor, sense:legal, sense:realty, sense:search_arxiv

## Digital Proprioception
- 메모리: 146.7MB
- CPU: 98.1%
- 스레드: 14개
- 태스크: 실행 0개 / 대기 0개

## 경제
- 코스피: 8801.49 (+0.1%) [2026-06-02]
- 코스닥: 1026.03 (-2.3%) [2026-06-02]
- S&P500: 7599.96 (+0.3%) [2026-06-01]
- 나스닥: 27086.81 (+0.4%) [2026-06-01]
- 원/달러: 1517.47 (+0.7%) [2026-06-02]
- 금: 4546.0 (+1.6%) [2026-06-02]
- 유가: 91.61 (-0.6%) [2026-06-02]
