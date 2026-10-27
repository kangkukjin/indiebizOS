# 101회차 사후 코드·기존 기록 감사 — 중앙 보관과 평가 모델

이 감사는 훈련 산출물 평가에 없던 **코드와 기존 기록을 추가로 읽은 사후 확인**이다. 원본 AI 답변·입력 사본·정답표·비용 기록은 바꾸지 않았다. 훈련·모델 호출·라이브 API·장치 시험을 실행하지 않았고, 제품 설정·데이터 삭제도 하지 않았다. 테스트 파일은 기존 검사의 계약을 읽었을 뿐 새로 실행하거나 통과했다고 보고하지 않는다.

## 확인 결과

1. **중앙 통계에는 요청 메시지 본문이 영속 저장된다.** `data/member_activity.sqlite3`의 `tasks.request`에 `MemberSession.turn`이 받은 `message` 문자열을 그대로 넣는다. 본문을 줄이거나 가리는 처리는 이 경로에 없다. v2 결과 RAM의 30분과 다른 저장소다.
2. **통계 원장에는 코드상 TTL·날짜별 정리·PC 해제 연동 삭제가 없다.** 30일은 일별 사용량 합산 범위이고, 상세 작업 목록은 날짜 제한 없이 50개씩 조회한다. PC 해제는 자격 폐기·세션 종료이며 작업 원장 삭제가 아니다. 따라서 유한 보존 기한을 약속할 수 없고, 별도 삭제 없이는 남는 구현이다.
3. **별도 API 평가 모델은 연구 대화의 필수 진입 조건이 아니다.** 그 조건을 만들었던 CLI→평가 모델 치환·API 강제 검사가 2026-10-10 커밋에서 제거됐다. 공통 평가가 실제 실행될 때는 준비된 평가 제공자가 필요하지만 CLI도 가능하다. API 방식 제공자를 실제 사용하는 경우에 그 제공자의 인증·모델 준비가 필요하다.

## A. 저장·조회·보존·삭제 경로

| 범위 | 코드에서 확인한 내용 | 근거 |
| --- | --- | --- |
| 요청 메시지 | `client_agent.run`이 `resolved.message`(없으면 앱 실행 표제)를 `MemberSessionManager.turn`으로 전달하고, 입력·한도 검사 후 `member_activity.begin`이 문자열을 `tasks.request`에 그대로 INSERT | [client_agent.py](../../../../../backend/services/client_agent.py) 47~95행; [member_session.py](../../../../../backend/cognition/member_session.py) 195~239행; [member_activity.py](../../../../../backend/datastore/member_activity.py) 9~36행 |
| 저장 내용의 경계 | 회원/기기/작업 식별자·표시명·요청 메시지·시각·상태·토큰·사용 모델, 도구 이름/시각/상태를 저장. 관리자 원장 스키마에는 assistant 답변·파일 바이트·도구 입력/출력 전문 칸이 없음 | member_activity.py 16~28행, 39~72행; [member_runner.py](../../../../../backend/cognition/member_runner.py) 86~108행 |
| 메시지와 전체 입력의 구별 | `begin`은 workflow 변환·첨부 문자열을 모델 입력에 덧붙이는 단계보다 앞에 있음. 따라서 저장되는 것은 받은 message이며, 요청 envelope·첨부·모델 입력 전체를 보존한다는 뜻은 아님 | member_session.py 239행, 283~289행 |
| 일별 사용량 | `data/member_usage.json`에는 주체/날짜별 턴·토큰이 누적됨. 통계 API의 최근 30일 필터는 이 합산에만 적용됨 | member_session.py 148~170행, 386~395행; [api_member_pcs.py](../../../../../backend/surface/api_member_pcs.py) 254~278행 |
| 상세 통계 | `recent`는 회원·기기로 제한하지만 날짜 WHERE 없이 시작 시각 내림차순·LIMIT/OFFSET 조회. API는 51건을 읽어 50건과 다음 offset 제공 | member_activity.py 54~72행; api_member_pcs.py 273~278행 |
| 조회 권한 | `/member-pcs`는 주인 인증 의존성을 사용. statistics는 해당 member_id/device_id로 조회. `/activity`는 member_id 기준. 자격 폐기된 등록도 `_require`에서 revoked로 배제하지 않아 주인 조회 자체가 자동 폐쇄되는 것은 아님 | api_member_pcs.py 12행, 46~50행, 162~167행, 254~278행 |
| 보존·삭제 | member_activity에는 생성·추가·갱신·조회만 있고 DELETE/TTL 없음. 저장소 파일명·모듈 소비자 전체 검색에서도 별도 삭제 작업을 찾지 못함. DELETE `/member-pcs/{device}`는 키 폐기와 세션 close만 호출. close/cleanup은 RAM 이력·임시 폴더를 정리하며 통계 DB를 지우지 않음 | api_member_pcs.py 38~43행, 138~143행; [limb_keys.py](../../../../../backend/base/limb_keys.py) 304~338행; member_session.py 96~114행 |
| v2 접수/결과 | `member_requests.sqlite3`는 기기·요청·작업·지문·epoch·상태·갱신 시각만 저장. 완료 결과/이벤트는 LIVE RAM. 완료 후 1,800초를 넘긴 항목은 submit/status 때 sweep으로 제거되고, 프로세스 재시작에도 소실. 이 정리는 통계 DB의 request에 영향을 주지 않음 | [member_desktop_requests.py](../../../../../backend/services/member_desktop_requests.py) 20~39행, 48~69행, 74~102행, 115~135행 |

RAM의 30분은 주기 타이머로 보장하는 물리 삭제 시각이 아니다. 완료 후 경과 시간을 submit/status 시 검사하며, 장기 실행 중인 행에는 같은 완료 TTL을 적용하지 않는다. 접수 메타데이터에도 이 파일에서 삭제 기한이나 PC 폐기 연동 DELETE가 없다. 따라서 기존 D1 L238의 현재 등록 수명 보관이라는 표현 역시 코드상의 삭제 실행 보장으로 읽을 수 없다.

중앙 통계에서 요청 메시지와 실행 메타데이터는 회수할 수 있지만, 이 스키마만으로 전체 대화·assistant 결과·작업 파일을 복원할 수 없다. 로컬 정본 백업은 여전히 필요하다. 이는 감사한 저장소의 범위이며 OS 백업·관리자의 수동 파일 삭제·외부 정리 작업이나 다른 로그 전체까지 없다고 증명한 것은 아니다. **보존 정책과 삭제 기능 마련은 별도 운영/개발 결정으로 남는다.** 이번에는 삭제를 실행하지 않았다.

### 기존 저장 기록의 읽기 전용 확인

- 확인 시각: `2026-10-28T06:39:20.632512+09:00`. `sqlite3` URI `mode=ro`와 `PRAGMA query_only=ON` 사용. 앱의 DB helper는 스키마 생성·commit을 하므로 호출하지 않았다.
- 실제 중앙 DB: 작업 3건, request 비NULL 3건, actions 3건. 요청 길이 11~118자. 본문·이름·식별자는 출력하거나 복사하지 않았다.
- 기록 시각: `2026-10-16T14:54:28.425735+09:00`~`2026-10-16T15:22:42.538382+09:00`. 30일 초과 기록은 0건이므로 실제 30일 초과 보존을 관측했다고 주장하지 않는다. 저장 사실은 관측, TTL/해제 삭제 부재는 코드 분석 결과다.
- 기존 [회원 완료 검사](../../../../../backend/test_member_completion_2026_09_14.py) 114~120행도 request 원문을 통계 DB에서 확인하고, 그 DB를 다른 중앙 파일의 원문 부재 검사에서 명시적으로 제외한다. [통계 검사](../../../../../backend/test_member_model_settings.py) 98~129행은 일별 30일 합산·50건 페이지·회원/기기 격리를 검증하는 계약이다. 이 테스트들을 이번에 실행하지 않았다.

## B. 평가 모델이 필요한 조건

| 상황 | 코드에서 확인한 조건 |
| --- | --- |
| 연구 대화 시작/실행 모델 선택 | `ResearchRunner._resolve_execution_config`는 일반 실행 해소를 그대로 사용. 연구 전용 평가 모델 선행 검사나 CLI→API 치환 없음. 주 실행 모델은 선택한 실행 기어/핀의 제공자·모델·인증이 필요 |
| 일반 턴의 공통 목표 평가 | 의식 출력이 있고 force_role/질문 확인 빠른 응답이 아닌 경로에서 결과가 있을 때 평가 경로 진입. 감독 경로는 enabled와 비어 있지 않은 criteria 계약을 확인. 비감독 대체 경로는 criteria와 `goal_eval.enabled`도 확인. 취소·기준 없음·특정 자기수리 완료 경로 등은 별도 조기 반환 가능 |
| 텍스트 평가 | `system_ai_call(role="evaluate")` → 평가 역할의 기어/핀 제공자. 얻지 못하면 system 원샷 제공자, 이어 의식 제공자로 대체 시도. API 제공자만을 허용하는 분기 없음 |
| 이미지 평가 | 평가 역할의 이미지 지원 제공자 → 비전 슬롯 순으로 확인. 이미지 지원이 명시적으로 True이고 준비된 제공자여야 하며 둘 다 없으면 오류. 텍스트 전용 제공자로 이미지를 평가하지 않음 |
| API 인증이 필요한 경우 | 실제 선택된 제공자가 API 키를 필요로 하는 유형인 경우. 공통 `provider_needs_api_key`는 Claude Code·Codex 계열 CLI와 Ollama를 키 불요 유형으로 분류. 키 불요는 바이너리·로그인·서버 가용성까지 보장한다는 뜻은 아님 |
| 평가 제공자 부재/실패 | 가능한 제공자를 얻지 못하거나 응답이 없으면 평가 미완료/UNKNOWN·재시도 가능 상태. API 평가 모델을 반드시 새로 설정해야 한다는 단일 시작 오류로 환원하지 않음 |

근거: [research_runner.py](../../../../../backend/cognition/research_runner.py) 13~18행·80~94행,
[agent_pipeline.py](../../../../../backend/cognition/agent_pipeline.py) 750~755행·794~835행,
[conscious_supervisor.py](../../../../../backend/cognition/conscious_supervisor.py) 281~317행·889~910행,
[cognitive_eval.py](../../../../../backend/cognition/cognitive_eval.py) 437~446행·522~557행,
[consciousness_agent.py](../../../../../backend/cognition/consciousness_agent.py) 822~835행·992~1036행,
[model_resolver.py](../../../../../backend/base/model_resolver.py) 42~61행·358~417행·580~637행·693~703행.

### 과거 API 필수 조건의 이력과 보존된 평가 실행

`96a9a6d4f5ea004fd9f938c5bfb9a163ece65572`(2026-10-10)의 실제 diff는 ResearchRunner에서 CLI이면 `resolve('evaluate')`로 치환하던 코드와, 치환 후에도 CLI이면 API 모델 설정을 요구하며 거절하던 코드를 제거했다. 가이드 R2 L36~39는 이 커밋에서 바뀌었지만 L40은 그보다 앞선 `a4c79b128`의 문장으로 남았다. 따라서 **R2 L40을 연구 대화의 현행 일괄 선행 조건으로 적용하는 것은 낡은 지침의 잔존**이다. 일반 평가가 선택한 API 제공자의 설정 필요성과는 별개다.

기존 [연구 실행 검사](../../../../../backend/test_research_runner.py) 39~57행은 Codex·Claude Code·Anthropic 경로가 실행 설정을 유지하고 별도 auxiliary resolve가 호출되지 않아야 한다고 정의한다. 이번에는 실행하지 않았다.

101회차 원시 usage에도 API 전용이 아니라 CLI 평가가 실제 사용된 기록이 있다. 이 기록은 같은 공통 인지 평가 경로의 관측이며, 연구 프로젝트의 새 실행 검증으로 바꾸어 부르지 않는다.

| 턴 | 보존 usage 역할/모델/제공자 | calls | input | output |
| --- | --- | ---: | ---: | ---: |
| [A1](../harness/collect_A1.json) | `oneshot:evaluate\|opus\|ClaudeCode` | 1 | 55,067 | 941 |
| [A2](../harness/collect_A2.json) | `oneshot:evaluate\|opus\|ClaudeCode` | 1 | 37,283 | 1,189 |
| [B1](../harness/collect_B1.json) | `oneshot:evaluate\|opus\|ClaudeCode` | 1 | 52,383 | 1,246 |
| [B2](../harness/collect_B2.json) | `oneshot:evaluate\|opus\|ClaudeCode` | 1 | 33,209 | 975 |

총 4회의 평가가 `ClaudeCode/opus`로 계측돼 있다. 현재 로그인 유효성·API 자격·실제 제공자 응답 가능 여부는 새 호출 없이 확인하지 않았고, 이 과거 기록으로 지금의 준비 상태를 보장하지 않는다. 연구의 배경 요약 등 다른 역할 호출은 평가 모델 필요성과 구분한다.

## 판본과 범위

코드 조사 기준 HEAD는 `51a0c1a6c89fa2a290964a9137692e5bfc11ea20`이다. 아래 파일은 읽은 바이트가 해당 HEAD와 일치했고, 최초 훈련 HEAD `950d976c`와도 모두 동일한지 개별 비교했다. 다른 세션의 미커밋 IBL 편집은 이 감사 근거에 포함하지 않았다.

| 코드 | SHA-256 | 훈련 HEAD와 동일 |
| --- | --- | --- |
| [backend/datastore/member_activity.py](../../../../../backend/datastore/member_activity.py) | `19d54c196a53ee27d3b52c5e1ebc60123ab21c5bdb54d897b690447d00f130ff` | 예 |
| [backend/cognition/member_session.py](../../../../../backend/cognition/member_session.py) | `ca6d8660b5cf7f6a8f1c04e45fbffa5d3f10f0d7ed4d71c481bf0f58912404d6` | 예 |
| [backend/cognition/member_runner.py](../../../../../backend/cognition/member_runner.py) | `001b70a6ea8cbef50f361a0a6809cee0e34dd05c0824adbf20f67f6bbc998755` | 예 |
| [backend/surface/api_member_pcs.py](../../../../../backend/surface/api_member_pcs.py) | `e989a0957ace080d9f60da1388e5878557a9bccc1f8425bdd0c029c454a85528` | 예 |
| [backend/services/member_desktop_requests.py](../../../../../backend/services/member_desktop_requests.py) | `2885da76d4351372f2ccaf77d42a001e3c7eb47774cd243c45bb13738476b210` | 예 |
| [backend/services/client_agent.py](../../../../../backend/services/client_agent.py) | `347c186e7b9801be6ce6420dc6f15e3c1f66c016ac05ebbd4ac01e1cff743df1` | 예 |
| [backend/base/limb_keys.py](../../../../../backend/base/limb_keys.py) | `b2bbd569eae1eba56babb66c50ab5475bf4282a0ef65e7668c6a97f6b1845d36` | 예 |
| [backend/cognition/research_runner.py](../../../../../backend/cognition/research_runner.py) | `3f3e23d06396389b794c836c0d175cd5c59d01779d89f4962a6bfbd2e3d15961` | 예 |
| [backend/base/model_resolver.py](../../../../../backend/base/model_resolver.py) | `5e63483d4b8469c6615669d8ed0f21e47121787223a4ca806bf55e5ace96bb73` | 예 |
| [backend/cognition/consciousness_agent.py](../../../../../backend/cognition/consciousness_agent.py) | `7f6ed25d1da7f36e18045559b94efe0782852c264eb6f193271f7a453c423c39` | 예 |
| [backend/cognition/cognitive_eval.py](../../../../../backend/cognition/cognitive_eval.py) | `b1cf151256cd33ef0b1d034e05e7a04231d347751ec98a70607809f4e686a665` | 예 |
| [backend/cognition/agent_pipeline.py](../../../../../backend/cognition/agent_pipeline.py) | `0716978f85e7bdb7b4464730dfb3cadaf3d8a4f1c5f1f845fa3ef49ae807014d` | 예 |
| [backend/cognition/conscious_supervisor.py](../../../../../backend/cognition/conscious_supervisor.py) | `b9acc8c7ef4be84a8d91037d355343d4d8b594aac81595df734227496d00f729` | 예 |
| [backend/cognition/final_evaluator.py](../../../../../backend/cognition/final_evaluator.py) | `1ea1357f2cfab75a7c17a6135aa060176a942eeff4ec3d26fae92766f1694b60` | 예 |

원본 입력 7편과 수집 4개·AI 산출물 7개는 기존 감사 지문으로 다시 확인한다. 이번 확인은 읽기·정적 경로 추적·기존 DB 집계이며 새 테스트·훈련·실모델 실행 성과가 아니다.
