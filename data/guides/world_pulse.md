# World Pulse — 오늘의 세계와 나 (자동 주입)
수집 시각: 2026-06-11T08:29

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
- 최근 대화: ping (시스템 AI)
- 오늘 예정: 없음
- 저장소 여유: 312.1GB

## 시스템 건강
- scheduler: 정상
- channel_poller: 정상
- system_ai_runner: 정상
- ⚠ 비정상 액션 (2개): engines:chart, sense:kosis

## 자가점검 패턴 분석
- 만성 실패: sense:kosis
- 응답 느려짐: others:channel_read (2ms → 391ms)
- 응답 느려짐: others:channel_send (1ms → 1263ms)
- 응답 느려짐: sense:crawl (582ms → 3338ms)
- 복구됨: limbs:radio, sense:crypto, sense:realty, sense:stock, sense:weather

## Digital Proprioception
- 메모리: 611.0MB
- CPU: 0.2%
- 스레드: 14개
- 태스크: 실행 0개 / 대기 0개
