# Codex 의식의 가이드 접근 복구

## 문제와 원인

2026-09-14 에피소드 3777(Codex `gpt-6-astra:high`)의 의식은
`supervision {op:"evidence", id:"tool:read_guide"}`를 요청했지만
`MCP tool call requires approval, but approval policy is never`로 거절됐다.
중간 감독의 근거 조회도 같은 오류였다. 실행자 입력에는 가이드 전문이 있었다.
따라서 이번 사건은 의식의 조회 경로 차단과 실행자의 절차 이행 문제를 구분해야 한다.

`providers/codex.py`는 의식의 네이티브 파일 수정을 제한하려고 `--sandbox read-only`와
`approval_policy="never"`를 사용한다. 그러나 MCP `supervision`은 조회뿐 아니라
`execute`와 `patch`도 제공하므로 도구 전체를 읽기 전용이라고 선언할 수 없다.
별도 허용 설정이 없으면 Codex는 읽기 인자의 호출도 승인 대상으로 분류하고,
비대화 정책은 승인을 요청하지 않고 거절한다.

## 수정 계약

Codex 의식의 MCP 브리지를 조립할 때만 다음 두 설정을 전달한다.

- `mcp_servers.indiebizos.enabled_tools=["supervision"]`
- `mcp_servers.indiebizos.tools.supervision.approval_mode="approve"`

이 설정은 해당 자식 호출의 `-c` 인자이며 사용자 전역 설정을 쓰지 않는다.
HTTP·stdio 및 세션 재개에 동일하게 적용한다. 실행자와 도구 없는 원샷에는
적용하지 않는다. 네이티브 `read-only` 샌드박스와 `approval_policy="never"`는 유지한다.
다른 MCP 도구의 승인 정책은 바꾸지 않는다.

실제 동작의 허용은 기존 `api_supervision.dispatch` → `Supervisor.tool`이 소유한다.
활성 턴·의식 신원·호출 예산·작업 소유권·실행자 정지 상태·패치 가능 단계를 계속 검사한다.
`supervision`에 사실과 다른 `readOnlyHint`를 붙이거나 전체 샌드박스를 해제하지 않는다.

설정 근거: [공식 MCP 설정](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## 검증

- 프로바이더 회귀: 의식의 HTTP·stdio·재개 호출만 작업대 허용을 갖고,
  실행자·도구 없는 호출에는 새 허용 설정이 없음을 검사한다.
- 실제 Codex CLI `0.153.4`, `gpt-6-astra:high`, `--strict-config`로 전후 대조했다.
  같은 프롬프트와 같은 격리된 stdio 작업대에서 도구 스키마 조회 후 가이드 읽기만 요청했다.
  작업대는 실제 `mcp_server.supervision`, `api_supervision.dispatch`, `Supervisor.tool`,
  `ibl_routing.search_guide`를 연결하며 검사 상태만 임시 디렉터리에 보관했다.
- 수정 전: `approval_mode`를 빼면 동일 승인 오류, 가이드 호출 영수증 없음.
- 수정 후: 스키마 조회·가이드 읽기 성공, 실제 가이드 본문 17,286자 수신.
  모델이 NEW의 중복 제거 계수와 0건 미발행 조건을 정확히 반환했다.
- 관련 프로바이더·감독 회귀, 전체 `.venv/bin/python3 -m pytest backend/ -q`,
  Android 번들 정합성 검사를 통과했다(전체 회귀 종료 코드 0).
- 기존 재기동 제어자로 백엔드에 반영했다. 중단된 작업 없이 `restarted`로 완료됐으며,
  ACTIVE 세대의 코드 지문이 수정한 작업 트리와 일치함을 확인했다.

이번 변경은 가이드 접근 경로만 복구한다. 중간 감독 JSON 파싱의 서두 처리,
실행자의 `table:ai`/`table:brief` 생략, 최종 보고서 품질은 별도 검증 대상이다.
보고서를 다시 발행하거나 원장을 수정하지 않았다.
