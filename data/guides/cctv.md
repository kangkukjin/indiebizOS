# CCTV·공개 웹캠 조작

CCTV는 하나의 조작 대상이다. 탐색·관찰·열기·캡처·소스 관리를 모두 `[limbs:cctv]`의 op로 표현한다.
읽기와 쓰기의 구분은 노드가 아니라 각 op의 반환·부작용 계약이 맡는다.

```ibl
[limbs:cctv]{op:"search", query:"광화문"}
[limbs:cctv]{op:"nearby", lat:37.5665, lng:126.978, radius_km:3, limit:5}
[limbs:cctv]{op:"nearby", source:"windy", lat:48.8566, lng:2.3522, radius_km:50}
[limbs:cctv]{op:"open", name:"시청"}
[limbs:cctv]{op:"capture", url:"https://example.com/live.m3u8", save_path:"outputs/cctv.png"}
[limbs:cctv]{op:"stats"}
[limbs:cctv]{op:"refresh"}
```

| op | 용도 | 인자 |
|---|---|---|
| search | 이름으로 카메라 찾기 | query, 선택 lat/lng·category·limit |
| nearby | 좌표 주변 카메라 찾기 | lat/lng 필수, source·radius_km·limit 선택 |
| open | 브라우저에서 영상 열기 | name 또는 url |
| capture | 영상 프레임을 이미지로 저장 | name 또는 url, 선택 save_path |
| stats | 소스별 현황 조회 | 없음 |
| refresh | UTIC 캐시 갱신 | 없음 |

`op`는 명시해서 사용한다. 기존 재생 호출의 의미를 보존하기 위해 생략 시에는 `open`이다.
`source`는 `nearby`에만 쓰며 `auto`(기본 통합검색) 또는 `windy`(Windy 공개 웹캠 직접 조회)다.
Windy 웹캠은 내 PC의 카메라가 아니라 세계 각지의 공개 경치 카메라다.
검색 반경은 km이며 생략 시 auto=5, windy=50이다. nearby의 결과 상한은 기본 5다.

검색은 카카오·TOPIS·UTIC·ITS·Windy 공급자를 사용한다. 지역과 결과에 따라 폴백하며,
`source:"windy"`는 교통 카메라 공급자를 건너뛴다.

조회 결과는 `items`로 조합할 수 있다. 좌표·URL·`playable` 등 실제 반환 필드를 확인해
지도나 플레이어에 전달한다. `stream_tags`가 있으면 채팅창에서 스트리밍을 표시할 수 있다.
검색 결과의 확인된 URL을 `capture`에 넣고 반환된 이미지 경로를 읽어 화면을 분석한다.
조회 자체와 영상 내용의 해석은 별개다. 0건이면 다른 지역의 영상을 해당 장소로 주장하지 않는다.

`search`·`nearby`·`stats`는 읽기, `open`·`capture`·`refresh`는 부작용 동작이다.
`capture`의 상대 경로는 호출한 작업공간 기준이며 프레임 추출에 ffmpeg가 필요하다.

| 환경변수 | 용도 |
|---|---|
| KAKAO_REST_API_KEY | 카카오맵 연동 |
| UTIC_API_KEY | UTIC 교통 카메라·캐시 갱신 |
| ITS_API_KEY | 고속도로·국도 CCTV |
| WINDY_API_KEY | Windy 공개 웹캠 |
