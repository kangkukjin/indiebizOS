# IBL 사용 순위 41–50 구현 감사·수리

2026-09-15. 정본 `/Users/kangkukjin/Desktop/AI/indiebizOS`에서 작업했다.

## 집계 기준

조사 시작 시점의 `data/ibl_usage.db` → `action_usage_daily` 전체 기록
(2026-08-05~2026-09-15, 모든 origin)을 node/action별로 합산했다.
현재 `data/ibl_nodes.yaml`에 등록된 어휘만 남겼다. 은퇴·미등록 어휘와 fn 호출은 제외했다.
내림차순, 동률이면 node/action 이름 순이다. 앞선 31–40위 감사와 같은 기준이다.

| 순위 | 어휘 | 누적 계수 |
|---|---|---:|
| 41 | sense:cctv | 255 |
| 42 | sense:company | 249 |
| 43 | others:showcase | 248 |
| 44 | sense:feed | 243 |
| 45 | engines:image_read | 237 |
| 46 | self:workflow | 236 |
| 47 | sense:paper | 232 |
| 48 | sense:navigate_route | 223 |
| 49 | sense:sqlite | 221 |
| 50 | sense:radio | 215 |

이 값은 제출된 IBL 코드의 어휘 수요다. 성공 실행 횟수나 사용자의 수동 호출 횟수가 아니다.
실행하지 않은 조건·폴백 가지와 내부 점검도 포함될 수 있다. 이후 사용에 따라 수치는 달라진다.

```sql
SELECT node, action, SUM(count) AS uses
FROM action_usage_daily
GROUP BY node, action
ORDER BY uses DESC, node, action;
```

결과에 현재 등록 어휘 필터를 적용한 뒤 41–50번째 행을 취한다.

## 확인한 결함과 수정

| 어휘 | 문제 → 수정 |
|---|---|
| sense:cctv | IBL에서 정규화한 limit이 nearby/webcam 공급자의 count로 전달되지 않음 → 호출 경계에서 변환. nearby의 lon 입력도 lng로 해소. |
| sense:company | corp_code만 주면 미국 시장으로 분기 → 명시 시장이 없을 때 DART로 전달. 문서에 안내한 005930·005930.KS가 회사명 검색으로 빠져 실패 → 등록된 stock_code와 정확히 일치하는 기업을 해소. 복수 후보는 거절. |
| others:showcase | 깨진 JSON을 빈 상태로 간주해 다음 쓰기가 기존 폴더·바스켓 원장을 덮어씀 → 읽기·형식 오류를 명시하고 원본 보존. status의 path 필터도 추가·상세와 동일하게 정규화. |
| sense:feed | 정상 HTML 페이지를 빈 피드 성공으로 반환 → RSS/Atom 인식 여부 확인. limit:0이 기본 10으로 바뀌고 음수는 뒤쪽 항목을 잘라 반환 → 0 보존·음수/잘못된 숫자 실패 반환. |
| engines:image_read | critic이 passed:"false"를 참으로 표시하고 배열·잘못된 score/issues는 예외 또는 오판 → 판정 객체의 타입·점수 범위 검증. tier/rubric은 모델의 주장 대신 실제 호출 경로·기준표로 기록. |
| self:workflow | YAML 한 파일이 배열·스칼라이면 전체 목록 조회 중단 → 해당 행만 실행 불가로 표시. id 경로 이탈·외부 심볼릭 링크 접근 → 파일 이름과 링크 검증. 직접 덮어쓰기 도중 실패·동시 읽기에 반쪽 YAML 노출 → 고유 임시 파일 완성 후 원자 교체. |
| sense:paper | 알 수 없는 source가 OpenAlex로 묵시 전환 → 오류 반환. arXiv 오류 Atom 항목이 논문으로, HTML/깨진 피드·OpenAlex 오류 JSON이 검색 0건으로 반환 → 응답 형식·오류 항목 검증. |
| sense:navigate_route | 경로별 실패 코드가 있어도 일반 결과 봉투로 반환 → result_code=0과 summary를 가진 경로만 성공으로 채택. 전부 실패면 success:false, 일부 대안 실패는 failed_routes와 warning에 보존. |
| sense:sqlite | ?/#/% 경로를 URI 구문으로 오해 → 경로 URI 인코딩. SQL 문자열·열 이름에 update/drop 등이 있으면 조회도 거절 → SQLite authorizer로 실제 연산 판정. 설정 PRAGMA 거절, 조회 PRAGMA 허용. 공백·따옴표가 있는 표 이름 인용 처리. 중복 열 이름으로 앞 값이 덮이는 경우 AS 안내와 오류 반환. |
| sense:radio | 알 수 없는 op를 검색으로 전환 → 명시 거절. 비JSON·객체·스칼라 행 응답이 예외 또는 빈 성공으로 흐름 → 형식 오류 반환. |

길찾기 성공 코드의 근거: [Kakao Mobility 자동차 길찾기 공식 응답 계약](https://developers.kakaomobility.com/guide/navi-api/directions).
SQLite 연산 검증의 근거: [SQLite authorizer](https://www.sqlite.org/c3ref/set_authorizer.html),
[authorizer action codes](https://www.sqlite.org/c3ref/c_alter_table.html).

## 회원 경로 재감사

패키지 단위 지문이 바뀌는 system_essentials·web·radio의 회원 경로를 재확인했다.

- self:read/fill: member_files → member_documents의 회원 장치 입력 → 턴 전용 작업대 → 변환 → 장치 반환 경로를 확인했다. 수정한 sqlite_ops는 이 경로에서 호출되지 않는다.
- sense:search/crawl: 변경한 함수는 fetch_feed이며 검색·크롤링 분기 및 공통 수신 함수는 바꾸지 않았다. 호스트 파일 조회나 새로운 쓰기 경로를 추가하지 않는다.
- sense:radio 및 limbs:radio 회원 변환: 검색의 응답 검증만 변경했다. radio_member는 방송국 URL만 해소하고 exchange로 회원 기기에 재생을 요청한다. 변경한 검색·op 오류 경로가 호스트 재생을 열지 않는다.

이를 반영해 세 패키지의 기존 path_audited 지문을 갱신하고 빌드로 회원·폰 매니페스트를 재생성했다.

## 검증

- 수정 전 `3d47d3eb`의 해당 소스를 임시 테스트 프로세스에서 로드해 동일 회귀를 실행: **40 failed, 4 passed**. 실제 작업 트리는 되돌리지 않았다.
- 신규 회귀: `backend/test_ibl_rank41_50_repairs.py` **44개 통과**.
- 기존 비전·워크플로·SQLite·공개파일·31–40위 회귀: **94개 통과**.
- SQLite 전문검색(FTS) 내부 data_version 조회와 PRAGMA 테이블 함수도 실제 임시 DB로 검증했다. 신규 회귀 + 기존 SQLite 검사 **50개 통과**.
- 회원 파일·격리·완료 경로 검사 **31개 통과**.
- 어휘 빌드/`--check`, Android 몸 번들 재생성, backend 층·은퇴 계약 검사 통과.
- 값 의미론·판정 관문 **23개 통과**.
- 최종 적용 중 자동 제어자가 부팅 중 파생물 변경을 감지해 중단했다. 빌드 완료 후 공식 `backend/api.py restart --wait`로 재기동해 **phase=ACTIVE, health=healthy, 실행 코드 지문=디스크 지문**을 확인했다.
- 전체 `pytest backend/ -o addopts='' -q`: **4623 passed, 1 failed, 1 skipped**, 469.04초. 유일한 실패는 새 회귀 파일의 직접 실행용 `__main__` 누락을 감지한 단일 러너 관문이었다.
- `__main__`을 pytest로 위임하도록 추가했다. 추가 FTS 검사까지 포함한 최종 신규 44개와 단일 러너 관문을 함께 재실행: **48 passed**. 테스트 진입점 수정 후 전체 스위트를 다시 실행하지는 않았다.

## 범위와 한계

외부 API와 비전 모델은 결정론 대역으로 입력·응답 계약을 검사했다.
외부 서비스 전체의 실시간 종단 실행이나 실제 이미지 의미 판단을 보증하는 감사는 아니다.
파일 저장·삭제 검사는 임시 원장만 사용했고 실제 파일 공개·알림·재생은 수행하지 않았다.
워크플로 저장은 한 파일의 완성된 스냅샷을 교체하며, 여러 편집자의 버전 병합 기능을 추가하지 않았다.
