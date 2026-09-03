# 지도 — 장소 검색·저장·상세·길찾기

앱 모드 **지도** 앱(구 '길찾기·CCTV', 2026-09-03 개편 — 카카오맵 앱 모양)과 그 뒤의 어휘. 사용자가 "근처 카페 찾아줘", "저장한 장소 보여줘", "그 가게 전화번호", "여기까지 길찾기" 같은 말을 할 때 읽는다.

## 어휘 (능력) — 앱은 이 조합의 표현일 뿐

| 일 | 문장 골격 |
|---|---|
| 장소 검색(전 업종) | `[sense:place]{query: "<검색어>", lat: <위도>, lng: <경도>, limit: <n>}` — 좌표는 선택(주면 그 주변 편향), `radius`(m, 최대 20000)까지 주면 반경 안만 |
| 카테고리 주변 | `[sense:place]{category: "<카페·편의점·주차장·병원·약국·은행·마트·숙박·관광명소·지하철·주유소·음식점…>", lat, lng, radius: <m>, sort: "distance"}` — 좌표 필수 |
| 한 곳 상세 | `[sense:place]{op: "detail", name: "<이름>", id: "<검색 결과 id>", lat, lng}` → 카카오 기본 + 네이버 설명·링크 + 블로그 언급(`blog_count`·`reason`) 1행 |
| 맛집 추천(후기순) | `[sense:restaurant]{query: "<지역 음식>"}` — 음식점만, 블로그 근거 정렬. 업종 무관 검색은 place |
| 좌표 → 주소 | `[sense:reverse_geocode]{lat, lng}` |
| 내 위치 | `[sense:here]{}` (데스크탑=선언 위치, 폰=GPS) |
| 길찾기 | `[sense:navigate_route]{origin: "<장소명 또는 경도,위도>", destination: "<…>"}` |
| 경로 주변 CCTV | `[sense:cctv]{op: "nearby", lat, lng, radius_km: <km>}` |

검색 결과 항목: `id·name·category·cat·address·phone·url(place.map.kakao.com/<id>)·lat·lng·distance(m, 좌표 준 검색만)`. 사진·영업시간·리뷰·평점은 공개 API 가 주지 않는다 — 앱은 `url` 의 카카오 장소 페이지를 안(webview)에 띄워 보여주고, 대화에서는 `url` 을 그대로 건넨다.

## 저장한 장소 원장 (사용자 데이터)

앱의 ☆ 저장은 파일 원장 한 개에 쌓인다 — **`~workspace/projects/앱모드/outputs/map/places.json`** (통화 `{items:[…], count}`). 행 = 검색 항목 + `tag`(폴더, 기본 "기본") + `memo` + `saved_at`. 지도 클릭으로 저장한 임의 위치는 `id: "spot:<lat>,<lng>"`·`cat: "위치"`.

- 읽기: `[self:read]{path: "~workspace/projects/앱모드/outputs/map/places.json"}` → items. 거르기는 `>> [table:filter]{where: {tag: "<폴더>"}}` 등 표 어휘.
- 쓰기(AI 가 대신 저장): `$본 = [self:read]{path}` 로 읽어 `items` 에 행을 더해 `[self:write]{path, format: "json"}` 로 통째 다시 쓴다(부분 갱신 어휘 없음 — 원장 누적 관용구). 행에는 반드시 `id·name·lat·lng` 을 채운다(앱은 좌표 없는 행을 버린다).
- 이 원장은 개인 데이터다 — 내용(가게 이름·메모)을 문서·커밋 메시지에 옮기지 말 것.

## 앱 동작 요약 (표현 — `frontend/src/components/MapInstrument.tsx` + `map/`)

검색창(Enter/검색) → 번호 핀 + 결과 목록 · 카테고리 칩 = 현 화면 반경 주변 검색 · 지도를 움직이면 "이 지역에서 재검색" · 항목/핀 클릭 = 상세(정보 탭 / 카카오 상세 탭) · ☆ 저장 → 폴더·메모 · ⭐ 패널 = 저장 목록(폴더 칩) · 지도 빈 곳 클릭 = 주소 카드(출발/도착/주변 음식점/저장) · 🛣️ 길찾기 패널(출발·도착·우리집·CCTV) · 📍 내 위치. 우리집 주소는 브라우저 localStorage(`directions.instrument.home`).
