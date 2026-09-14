# ep3796 — API 오류 전달과 분류 응답 검증

## 문제와 재현

2026-09-15 04:00:56의 DeepSeek 분류 호출이 681초 뒤
`RemoteProtocolError: incomplete chunked read`로 끝났는데, 에피소드에는
`[무의식] 분류: THINK`가 남았다. OpenAI SDK 공용 동기 경로가 스트림의
`error` 사건을 무시해 빈 문자열을 반환했고, 분류기는 `None`만 실패로 보아
`EXECUTE`가 포함되지 않은 빈 문자열을 `THINK`로 처리했다.

## 변경 계약

- OpenAI SDK 계열(OpenAI·DeepSeek)의 `process_message`는 스트림 오류를
  예외로 전달한다. 오류 전 텍스트가 있어도 성공 응답으로 반환하지 않는다.
  클라이언트 미준비와 빈/공백 응답도 예외이며, 호출별 `last_failure_kind`에
  `unavailable`·`provider_error`·`empty_response`를 남긴다.
- 기존 원샷 경계는 예외를 `None`으로 반환하고 실패 범주를 전달한다.
  GUI용 스트리밍 호출은 기존 `error` 사건 계약을 유지한다.
- 분류기는 공백·대소문자 정규화 뒤 허용된 단일 토큰만 채택한다.
  `SESSION_RESET`·`CONTEXT_UPDATE`·`EXECUTE`·`THINK`·`REPAIR`, 기존
  `RESET` 별칭을 지원한다. 빈 응답·잘린 토큰·오류 설명·혼합 출력은
  분류 실패를 로그에 남기고 기존 정책대로 `EXECUTE`를 반환한다.
- 시간 상한, 후처리 큐의 성공 판정·재시도, 보고서 프로그램은 이번 범위 밖이다.
  과거 에피소드 원장은 수정하지 않는다.

## 검증

`backend/test_episode3796_classification_failure.py`는 네트워크 없이 실제
SDK 프로바이더 → 원샷 → 분류기 경로에서 연결 중단을 재현한다. 빈 스트림과
`THINK`를 일부 받은 뒤의 오류가 모두 실패 기본 경로로 가는지 검증한다.
정상 분류 5종·RESET 별칭, 잘못된 출력, 정상 후속 호출의 실패 상태 초기화,
스트리밍 소비자의 오류 사건도 확인한다.

- 전체 `pytest backend/ -q`: 4,390건 통과, 신규 테스트의 `__main__` 진입점
  누락을 잡은 저장소 규약 검사 1건 실패. 런타임 기능 검사 실패는 없었다.
- 진입점 추가 후 관련 검사와 `test_single_runner.py`: **61 passed**.
- 신규 테스트 파일 직접 실행: **25 passed**. 진입점만 보완했으므로 전체
  기능 검사는 반복하지 않았다.
- backend 층 가드·의식 출력 스키마 검사 통과. Android 몸 번들 재생성 결과는
  기존 파생물과 같았다.
