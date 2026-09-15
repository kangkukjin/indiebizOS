# IBL 사용 순위 31–40 구현 감사·수리

2026-09-15. 정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`에서 작업한다.

## 집계 기준

조사 시작 시점의 `data/ibl_usage.db` → `action_usage_daily` 전체 기록
(2026-08-05~2026-09-15)을 node/action별로 합산했다. origin은 모두 포함한다.
`data/ibl_nodes.yaml`의 현재 등록 어휘만 남겨 과거 은퇴 어휘·미등록 이름·`fn` 호출은 제외했다.
내림차순 정렬, 동률은 node/action 이름 순으로 배치했다. 기존 21–30위 보고서와 같은 기준이다.

이 계수는 `system_tools_ibl._collect_step_actions`가 **제출된 코드의 어휘 수요**를 센 값이다.
성공한 실행만 세는 값이 아니며, 실행하지 않은 조건·폴백 가지의 어휘나 내부 점검도 포함될 수 있다.
사용자의 수동 실행 횟수 또는 성공률로 해석하지 않는다.

| 순위 | 어휘 | 누적 계수 |
|---|---|---:|
| 31 | self:trigger | 407 |
| 32 | self:patch | 398 |
| 33 | self:ledger | 364 |
| 34 | sense:performance | 354 |
| 35 | self:forage | 351 |
| 36 | sense:search_youtube | 351 |
| 37 | others:portal | 339 |
| 38 | sense:weather | 323 |
| 39 | self:blog | 322 |
| 40 | self:webapp | 310 |

재조회 SQL(결과에 현재 등록 어휘 필터를 적용):

```sql
SELECT node, action, SUM(count) AS uses
FROM action_usage_daily
GROUP BY node, action
ORDER BY uses DESC, node, action;
```

## 발견한 결함과 수정

| 어휘 | 재현한 문제 → 수정 |
|---|---|
| self:trigger | 채널·파일·웹훅 config에 시간 규칙 강제 → 시간 검증은 schedule에만 적용. 실행기와 dry-run이 같은 타입별 해소기를 사용한다. 알 수 없는 타입은 저장하지 않는다. |
| self:trigger | schedule→channel 변경 뒤 이전 타이머 잔존 → 이전 타입으로 타이머 삭제 후 새 타입을 연동한다. 동기화 오류는 warning으로 반환한다. |
| self:trigger | 채널 발화가 프로젝트를 무시하고 실패도 성공 이력으로 기록 → 등록 프로젝트 해소, 공통 결과 판정·오류 사유와 행수 기록. 구문 실패도 실패 이력에 남긴다. 문서에 안내된 subject_contains는 제목에만 적용한다. |
| self:trigger | history limit:0이 전체 이력을 반환하고 문자열 숫자는 예외 → 0은 빈 목록, 문자열 정수 수용, 음수 거절. |
| self:patch | 같은 초의 동시 propose가 한 세션으로 충돌 → UUID로 제안 ID를 구분한다. |
| self:patch | 적용 후 파생물 검증 실패도 success/verified=true → 적용 여부와 검증 여부를 분리한다. 중복 수행도 실패 판정을 보존하고 재기동 후 검증 단계까지 전달해 제어자가 복구하게 한다. 삭제 실패를 제거 성공으로 삼키던 경로도 예외를 전파한다. |
| self:ledger | 동시 append/upsert/set이 갱신을 유실 → 공용 경로 잠금으로 읽기·수정·저장 전체를 직렬화한다. 파일 원자 교체만으로는 막지 못하던 경쟁을 막는다. |
| self:ledger | Python 비교가 true와 1을 합치고 대소문자·NFC/NFD를 다르게 식별 → IBL 공통 값 동등성 사용. 부분 upsert가 기존 행의 스키마 위반을 통과 → 병합된 최종 행도 enum/list 관문 검사. |
| sense:performance | KOPIS 오류 XML·점검 HTML이 공연 0건 성공으로 변환 → 정상 dbs 응답만 목록으로 인정한다. 빈 dbs는 정상 0건 유지. |
| self:forage | 잘못된 layer가 map 쓰기로 전환, 문자열 false가 실제 쓰기/일반화 표식을 켬 → layer 검증, 쓰기 옵션의 명시적 불리언 해석. |
| sense:search_youtube | 배치 검색의 일부/전부 실패·검색 상한 조정 누락 → success:false와 검색어별 errors/sections, 얻은 items는 partial:true로 보존. 잘못된 queries는 검색 전에 거절하고 성공 검색의 중복 제거는 유지. |
| others:portal | audit의 portal 무시 및 limit:0의 전체 반환 → 대상 포털로 좁힌 뒤 상한 적용. 빈 intro로 기존 소개를 지울 수 없던 문제도 수정. 삭제·상세 op의 낡은 설명은 정본 이름으로 갱신. |
| sense:weather | Open-Meteo 기본 km/h를 m/s로 표시 → wind_speed_unit=ms를 요청하고 반환에도 단위를 명시. lon:0이 누락되는 truthiness 오류 수정. |
| self:blog | 안내한 title 인자를 content 모드가 무시 → post_id→title→query 순으로 입력 해소. 알 수 없는 op가 글 목록으로 바뀌던 동작은 오류로 반환. |
| self:webapp | 동시 등록/삭제의 갱신 유실 → 공용 경로 잠금·고유 임시 파일 원자 저장. HTTP 404/410도 살아 있다고 판정 → 2xx/3xx와 인증 요구 401/403만 alive=true. |

풍속 단위 근거: [Open-Meteo 공식 API 문서](https://open-meteo.com/en/docs)의
wind_speed_unit 기본값은 kmh이고 ms를 지정할 수 있다.

## 검증

- 초기 회귀 45개를 수정 전 커밋 `3d21fe396b9522d7edfa6a13de7f177291cb72c8`의 소스로 실행했을 때 34개 실패, 초기 수정본에서는 45개 통과했다.
- 채널 발화·사전검수·제어자 전달까지 추가한 새 회귀와 트리거/언어/재기동 관련 검사: 105개 통과.
- 기존 유튜브 테스트가 성공 sections의 정확한 모양을 검사하는 것을 확인해 성공 행의 불필요한 success 키를 제거했다. 실패 행에만 실패 표식을 붙여 기존 성공 계약을 유지한다.
- 신규 회귀는 최종 55개다. 전체 `pytest backend/ -o addopts='' -q`: **4565 passed, 1 failed, 1 skipped**, 451.60초. 유일한 실패는 새 subject_contains 비교를 공통 함수로 위임하지 않았다는 값 판정 관문이었다.
- 이를 `common.value_semantics.text_match`로 교체한 뒤 신규 55개·값 판정 관문·트리거 기존 회귀를 함께 재실행: **82 passed**, 6.16초. 이 한 줄 수정 후 전체 스위트를 다시 실행하지는 않았다.
- 어휘 빌드 및 `--check`, Android 몸 번들 재생성, backend 층 검사, 은퇴 계약 검사를 통과했다.
- 실행 중 백엔드는 변경 감지 제어자가 자동 재기동했다. 최종 확인: phase=ACTIVE, /health=healthy, 실행 코드 지문=디스크 지문, 활성 턴 0개.
- 정본 main 구현 커밋: `6a2f6dd5545f3e3ac58de8136b846a4278f713e9`. 커밋 전 필수 검사 전부 통과(자기수정 안전장치 30개 포함).

## 회원 파일 경로 재감사

system_essentials의 실행 소스가 바뀌어 self:read/fill의 path_audited 지문을 다시 계산했다.
`member_files.py`, `member_bridge.py`, `member_documents.py`의 호출 경로를 확인했다.
회원 장치의 명시적 입력 → 턴 전용 작업대 → office 읽기/fill → 회원 장치 저장 영수증의
경로에서 ledger_ops·webapp_registry·repair_staging은 호출되지 않는다.
변경한 모듈이 회원 입력을 허브 파일로 바꾸거나 새 도구 실행을 열지 않는다.

## 범위와 한계

외부 검색/API 응답은 결정론 대역으로 오류·빈 결과·성공 계약을 검증했다.
날씨의 실제 단위 규약은 공식 문서로 확인했으며, 외부 서비스 전체를 실시간 종단 검증한 것은 아니다.
채널 검사는 실제 폴링·발신 없이 함수 경로를 실행했다. 원장·제안 검사는 임시 파일만 사용했다.

webhook/file 트리거의 실제 감시기는 기존 가이드에 명시된 미구현 범위이며 이번에 새 감시 서비스를 만들지 않았다.
실용 발화 경로는 schedule/channel이다. 파일 잠금은 이 잠금을 사용하는 도구끼리의 협력 규약이다.
webapp의 alive는 HTTP 상태 판정으로, 인증 뒤 기능이나 정상처럼 응답하는 오류 페이지까지 보증하지 않는다.
