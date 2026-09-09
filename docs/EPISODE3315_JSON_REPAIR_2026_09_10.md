# 에피소드 #3315 — 과제 JSON 오류와 거짓 완료 수리

2026-09-10 08:21, 컨텐츠 에이전트의 디지털 노마드 글쓰기 요청이 18.86초 만에 중단됐다.
분류(THINK)와 기존 과제 선택 뒤 재검토 응답을 `json.loads`로 읽으며
`Expecting property name enclosed in double quotes: line 1 column 2 (char 1)`가 발생했다.
도구 실행과 최종 응답은 없었다. 원문 응답은 저장되지 않아 실제 잘못된 문자열은 확인할 수 없다.

`pursuit_bind.ask_json`은 코드펜스만 벗긴 뒤 바로 JSON을 해석했고 재시도가 없었다.
선택·재검토·요약 프롬프트는 따옴표 없는 유사 JSON을 출력 예시로 사용했다.
프로젝트 WebSocket은 예외 뒤에도 태스크를 무조건 completed로 닫았다.
실제 `task_3b9cb7fb`는 completed/result 빈 문자열, 과제 턴은 interrupted로 서로 달랐다.
과제 턴의 에피소드 연결도 존재하지 않는 `ep.id`를 읽어 빈 값이었다.

수리 내용:

- 출력 예시를 유효한 JSON으로 교체. 선택의 id 타입, 재검토의 action·criteria와 문자열 필드,
  요약의 허용 필드·타입·원장 상한을 적용 전에 검증한다.
- 형식·필드 오류에 한 번만 재요청. 실패를 기본 판단으로 바꾸지 않으며 두 번째 실패는
  원인을 연결한 오류로 반환한다. 실패 단계와 마스킹된 응답 미리보기로 다음 오류를 추적한다.
- WebSocket은 종료까지 도구 메타를 받아 실패/취소/완료로 구분한다. 시간 초과 후 워커가
  마무리하는 경로에도 동일한 판정을 적용한다. 실패·취소에는 성공 응답과 완료 이벤트를 보내지 않는다.
- 과제 턴은 `ep.episode_id`로 에피소드에 연결한다.

검증은 `backend/test_episode3315_repairs.py`에서 실제 과제 SQLite 원장과 WebSocket
핸들러를 사용한다. 모델·네트워크·사용자 데이터는 시험 대역으로 격리한다.
잘못된 JSON/필드/타입/상한, 정상 JSON·코드펜스, 재시도 소진, 진단 비밀 마스킹,
과제 보존·에피소드 연결, 예외·오류 이벤트·취소·빈 응답·정상 완료를 검사한다.
시간 초과 시 태스크가 열린 채 유지되고, 늦게 끝난 워커의 성공/실패로 종결되는 것도 검사한다.

실사용 기록도 복구했다. 코드 반영 중 재기동의 기존 `boot_common._cleanup_completed_tasks`가
거짓 completed 행을 정리했으므로, 에피소드의 요청·agent·task/run ID·시작/종료 시각을
근거로 `task_3b9cb7fb`를 failed로 복원했다. 도구 실행 없음은 원장의 빈 도구 목록으로 확인했다.
시작/종료 시각은 에피소드의 한국 시각을 tasks의 UTC 표기로 변환했다. 알 수 없는 WS 연결 ID는
복원하지 않았다. 과제 턴의 interrupted 상태·입력·응답은 보존하고 episode_id=3315 및 오류를
보완했으며 `pursuit_event:turn.repaired`에 근거를 남겼다. 수정 전 SQLite 온라인 백업은
`data/_backups/2026-09-10_episode3315_status/conversations.db`다. 원본 에피소드 로그는 그대로다.

검증 결과: 전체 백엔드 `3409 passed, 1 skipped`(123.22초), 이 수리의 회귀 30건 통과.
Android 몸 번들 재생성과 backend 층 검사도 통과했다. 실행 중인 정본 백엔드의 `/health`는
healthy로 확인했다. 전체 시험이 registry.yaml에 남긴 의미 없는 YAML 줄바꿈은 원복했다.
