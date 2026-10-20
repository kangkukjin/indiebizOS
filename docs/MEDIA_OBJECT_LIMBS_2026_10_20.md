# 라디오·CCTV를 조작 대상 중심으로 통합

## 분류와 호출

`limbs`는 사용하는 도구·기기를 가리킨다. 같은 대상을 탐색·관찰·조작하는 동작을
하나의 어휘의 op로 모은다. `sense`는 알아내려는 정보·지각 능력을 중심으로 구성한다.
읽기/쓰기·반환·실행 위치는 노드가 아니라 개별 op의 계약이다.

- `limbs:radio`: search, stations, play, stop, status, volume,
  favorite_list, favorite_add, favorite_remove.
- `limbs:cctv`: search, nearby, open, capture, stats, refresh.
- radio의 한국 채널 목록은 stations(country 생략 또는 KR). 다른 국가는 search로 찾는다.
- CCTV의 공개 웹캠 조회는 nearby의 source:windy. 기본 source:auto와 동작은 같고 공급처만 다르다.
- 기존 limbs 호출의 기본 의미를 보존한다: radio=play, cctv=open.
  옮겨오는 검색·관리 호출에는 search/stats를 명시한다.

패키지 어휘 6개를 2개로 합쳤다. API 등록부가 별도로 노출하던 ITS CCTV·Windy webcam의
노드 바인딩도 해제한다. 내부 공급자 함수·API 연결·저장소는 유지한다.
Windy 독립 어휘의 라이브 용례는 0건이며, 카탈로그 재로딩 뒤 옛 이름의 부재를 확인한다.
앱 버튼·지도 검색·가이드·시드와 빌드 파생물을 함께 이관한다.

## 회원 경계

`ops.lands_on`은 액션의 기본 목적지를 op별로 덮는다(hub/body/false).
빌드는 대상 op의 실존·읽기/쓰기·감사 지문을 검증한다. 매니페스트는 선언을 보존하고,
실행기는 권한 관문과 기기 라우팅에서 같은 해소값을 사용한다. 어휘 이름 특례는 없다.

라디오 search/stations는 허브에서 읽으며 연결된 재생 기기를 요구하지 않는다.
play/stop/status/volume은 기존 회원 기기의 미디어 경로를 따른다.
즐겨찾기는 기존 주인 저장소라 회원 비공개(false)이며 requires에도 주인 전용을 명시한다.
CCTV의 회원 공개 범위는 확대하지 않는다.

## 이관과 검증

`scripts/migrate_media_limbs.py --apply --reindex`는 실행 용례·훈련 JSON·저장 프로그램을
이관한다. SQLite는 backup API, 파일은 원문 사본으로 `data/_backups/2026-10-20_media_limbs/`에
보존한다. 이전 기본 op를 보충하며 문자열 페이로드와 과거 사건 로그는 바꾸지 않는다.
동적 즐겨찾기 op는 추측하지 않고 수동 검토를 요구한다. 재실행은 멱등이다.

이 PC에서 실행 용례 119행·훈련 JSON 2개를 이관했다. 변경 용례만 재색인한다.
radio 54건·CCTV 117건의 현행 용례를 검토하고 계약 검토 원장을 갱신했다.
과거 사건 보고서의 이름은 당시 기록으로 보존한다.

회귀의 거처: `backend/test_cctv.py`, `test_tool_radio.py`, `test_member_profile.py`,
`test_migrate_media_limbs.py`. 공급처·결과 상한·0 좌표·캡처 작업공간·즐겨찾기 저장·회원의
허브/기기/비공개 분기·감사 지문·이관의 기본값과 백업을 검사한다.
외부 스트림의 실제 재생 품질과 기기별 실물 인수는 이 변경의 자동 회귀가 증명하지 않는다.
