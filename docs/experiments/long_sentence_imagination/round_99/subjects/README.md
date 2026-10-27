시험 프로그램 6편. 각 프로그램은 inputs 로 `본문`(sleeper.py 원문) 을 받아 `~turn/sleeper.py` 에 쓴 뒤 `[self:script]{path}` 로 돈다.
S1·S3·S6 은 inputs `병렬`(1 또는 3) 을 받는다. S4 는 inputs `파일`(읽을 파일 경로) 을 받고 두 번 실행한다(두 번째는 reuse:{run_id:첫 run_id}).

(2026-10-27 수리 턴 정정) S1·S3·S6 의 `parallel:$병렬` 은 **입력으로 받을 수 없다** — each 옵션은 컴파일 리터럴(STATIC_OPTION, ibl.md). 실제 실행은 요청 조립기(`build_request.py`)가 1 또는 3 리터럴로 치환한 사본이며, 독립 AI 도 같은 치환 사본으로 실행했다(L99-4 ④). 원문은 그대로 둔다.
