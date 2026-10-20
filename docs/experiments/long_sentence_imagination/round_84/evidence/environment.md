# 84회차 실행 환경

- 정본 main, 시작 HEAD `0267ba8a`(미커밋 변경 17줄: 83회차 스테이지 파일·다른 세션의 web/finance/shopping 패키지 수정). 본 회차는 그 변경을 수정·취소하지 않았다.
- 10:23:52 다른 작업의 재기동이 `artifact_changed_before_start`로 FAILED → 10:37:41 `api.py start`(explicit_start_retry)로 복구 → 10:38:27 런처 앱이 shutdown 요청(런처 재실행) → 10:39 새 세대 ACTIVE.
- 10:54:43 `deferred(artifact_changed_after_check)` → 10:55:18 `recovery_unavailable(boot_artifact_changed)` FAILED → 10:56:39 복구 → 10:59:45 deferred → 11:00:13 `artifact_changed_before_start` FAILED → 11:01:03 복구. 원인은 별도 세션의 `data/packages/installed/tools/web/*`·`backend/test_web_search.py` 연속 편집(3분 간격 파일 변경 관측). 전체 이력 [restart_history.json](restart_history.json).
- 영향: ① 프로젝트 에이전트의 start 상태는 재기동 뒤 사라져 매번 `POST .../agents/{id}/start` 뒤 접수(400 "에이전트가 실행 중이 아닙니다"). ② 재기동 전에 **완료된** 작업(ep5059, 10:59:33 종료)의 `status_url`이 재기동 뒤 404("작업을 찾을 수 없습니다") — 접수증이 비영속. 답변·종료 시각은 `episode_log`/`trajectory_event`에서 회수했다(harness/recover.py, 재실행 없음). 대화 히스토리는 유지되어 T3이 T2 파일을 이어 수정했다.
- 훈련자 실행은 모두 재기동 사이에 완료됐고 중단된 실행은 없다. 독립 AI 실행 중 끊긴 작업도 없다(모두 terminal 또는 에피소드 종료 확인).
- HTTP 접수 경로는 training origin 의 에이전트별 rehearsal 히스토리를 사용한다(83회차와 동일). 원생 모델 세션의 동일성은 관측 범위 밖.
- 훈련자는 83회차 하네스에서 `/ibl/execute` 본문 키·agents command API 를 이미 보았으므로 접수 자체는 공개 교재 단독 실험으로 세지 않는다. IBL 본문은 교재 2권·문법 조각·describe 6개 계약으로 작성했고 내부 소스는 열지 않았다(재기동 제어자 소스는 복구 판단용으로 읽음 — 훈련 작성과 무관).
