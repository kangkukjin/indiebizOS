# World Pulse — 오늘의 세계와 나 (자동 주입)
수집 시각: 2026-06-04T03:29

> 이 정보는 대화 시작 시 시스템 프롬프트에 자동 포함됩니다.
> 사용자가 '요즘 세상은 어때', '오늘 경제 상황' 등을 물으면
> 아래 데이터를 바로 활용하여 답하세요.
> [sense:world]{op: "refresh"}나 read_guide 호출은 불필요합니다.

## 사용자
- 이름: 강국진
- 직업: 물리학자, 작가
- 관심사: AI OS 개발, 정치, 물리학, 철학
- 메모: 시스템에는 사용자가 작성해온 블로그 데이터를 볼 수 있는 기능이 있다. 
사용자는 한국인 남성으로 1969년생이다. 
- 위치: Cheongju

## 시스템 상태
- 프로젝트 24개, 에이전트 33개 활성
- 최근 대화: 멈췄다. (시스템 AI) / 지금도 라디오 소리가 나오고 있어. (시스템 AI)
- 오늘 예정: 없음
- 저장소 여유: 321.4GB

## 시스템 건강
- scheduler: 정상
- channel_poller: 정상
- system_ai_runner: 정상
- ⚠ 비정상 액션 (6개): engines:tts, self:run_pipeline, sense:collect_sites, sense:crypto, sense:kosis, sense:paper

## 자가점검 패턴 분석
- 만성 실패: self:run_pipeline, sense:collect_sites, sense:crypto, sense:kosis
- 성공률 하락: engines:tts (100% → 0%)
- 성공률 하락: sense:paper (100% → 50%)
- 응답 느려짐: engines:newspaper (872ms → 6194ms)
- 응답 느려짐: self:manage_events (1ms → 2ms)
- 응답 느려짐: self:storage (3ms → 6ms)
- 응답 느려짐: sense:commercial (123ms → 1917ms)
- 응답 느려짐: sense:search_books (392ms → 980ms)
- 응답 느려짐: sense:search_naver (124ms → 333ms)
- 복구됨: engines:slide_shadcn, limbs:music, self:trigger, sense:book, sense:cctv, sense:commercial, sense:realty, sense:stock

## Digital Proprioception
- 메모리: 461.5MB
- CPU: 90.0%
- 스레드: 21개
- 태스크: 실행 0개 / 대기 0개
