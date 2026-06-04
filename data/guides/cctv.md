# CCTV 실시간 영상 가이드

## 빠른 사용법 — `[sense:cctv]` 단일 op 액션

CCTV 조회는 **`[sense:cctv]` 하나**로 통합되어 있다. `op`로 검색 방식만 고른다.

```
[sense:cctv]{query: "광화문"}                 # op 생략 시 기본 search
[sense:cctv]{op: "search", query: "경부고속도로"}
[sense:cctv]{op: "nearby", lat: 37.5665, lng: 126.9780}        # 좌표 근처
[sense:cctv]{op: "nearby", lat: 37.49, lng: 127.03, radius_km: 3, count: 5}
```

| op | 언제 | 필수 | 옵션 |
|----|------|------|------|
| `search` (기본) | 장소 **이름**으로 찾을 때 | `query` | `category`(웹캠), `limit` |
| `nearby` | **좌표**를 알 때 (지도 클릭 등) | `lat`, `lng` | `radius_km`(km, 기본 5), `count`(기본 5) |

> 이름만 알면 `search`, 좌표를 알면 `nearby`. 둘 다 같은 액션이라 출력 형식이 동일하다.

### 출력 계약 (중요)

- `cctvs[]`의 모든 항목은 **좌표 `{lat, lng}` (float)를 보장**한다 — 좌표 없는 항목은 출력에서 제외된다. 그래서 지도에 바로 찍을 수 있다.
- 각 항목과 `stream_tags`에 **`playable`(bool)** 이 실린다 — HLS(hls.js)로 채팅창/플레이어에서 바로 재생 가능한지. 프론트는 이 값을 신뢰한다(URL 재판별 불필요).
- `radius_km` 단위는 **km** (전 소스 통일).

**데이터 소스 (검색 순서)**: 카카오맵(전국 6,892대, 좌표 보강 완료·모두 HLS) → TOPIS(서울) → UTIC(전국 시내도로) → ITS(고속도로/국도) → Windy(해외 폴백). 카카오가 전국 시내도로+고속도로를 좌표·HLS로 커버하므로 지도 표시에 가장 적합하다.

### ⚠️ 검색 결과 처리 원칙

1. **`[sense:cctv]` 한 번이면 충분하다.** 같은 장소를 키워드만 바꿔 반복 검색하지 말 것.
2. 정확한 이름 매칭이 안 되더라도 **좌표가 근접하면 그 결과를 사용**한다.
3. 결과의 `stream_tags`를 응답에 포함하면 실시간 스트리밍이 표시된다.
4. 결과가 0건이면 "해당 장소의 CCTV를 찾지 못했습니다"라고 안내. 웹 검색/브라우저 우회 금지.
5. **금지**: 동일 요청에 3회 이상 반복, web_search로 CCTV URL 찾기, 브라우저로 외부 사이트 접속.

---

## 관련 액션

| 용도 | 액션 | 예시 |
|------|------|------|
| CCTV 검색(이름) | `[sense:cctv]{op:"search"}` | `[sense:cctv]{query: "광화문"}` |
| CCTV 검색(좌표) | `[sense:cctv]{op:"nearby"}` | `[sense:cctv]{op: "nearby", lat: 37.49, lng: 127.03}` |
| 해외 경치 웹캠(좌표) | `[sense:cctv]{op:"webcam"}` | `[sense:cctv]{op: "webcam", lat: 21.31, lng: -157.86, radius_km: 50}` |
| 영상 열기/캡처 | `[limbs:cctv]{op}` | `[limbs:cctv]{op: "open", name: "시청"}` / `{op: "capture", url: "..."}` |
| 데이터 통계 | `[self:cctv_stats]` | `[self:cctv_stats]` |
| UTIC 캐시 갱신 | `[self:cctv_refresh]` | `[self:cctv_refresh]` |

### CCTV 영상 열기 / 캡처 (조작 = limbs)

```
[sense:cctv]{query: "한라산"} >> [limbs:cctv]{op: "open"}     # 브라우저에서 재생
[limbs:cctv]{op: "capture", url: "http://cctv-url/stream.m3u8"}  # ffmpeg 프레임 PNG (AI 분석용)
```

> 조회(perceive)는 `[sense:cctv]`, 조작(act: 열기·캡처)은 `[limbs:cctv]` — 노드로 역할이 갈린다.

---

## AI 화면 분석 워크플로우

```
[sense:cctv]{query: "해운대"}
```
결과의 첫(또는 가장 가까운) 항목 URL을 `[limbs:cctv]{op: "capture", url: ...}`로 캡처 → 반환된 이미지 경로를 읽어 분석.
분석 가능: 교통 정체, 차량 밀도, 사고, 날씨(맑음/비/눈/안개), 파도, 혼잡도, 적설량.

---

## UTIC 실시간 API 구조

UTIC(도시교통정보센터)는 전국 시내 도로 CCTV 16,000+대를 실시간 API로 제공한다.
- 엔드포인트: `http://www.utic.go.kr/map/mapcctv.do` · 인증: UTIC_API_KEY + Referer 헤더
- 반환: cctvname, lat, lng, kind(1=시내, 7=고속도로), cctvurl(HLS), stream_id
- `[self:cctv_refresh]`로 수동 갱신 (보통 자동 캐시로 충분)

---

## 참고: 한국 해안/국립공원 CCTV 사이트 (사용자 직접 접속용)

| 사이트 | URL |
|--------|-----|
| 해양수산부 연안 | https://coast.mof.go.kr/coastScene/coastMediaService.do |
| 바다타임 | https://www.badatime.com/cctv |
| 국립공원공단 | https://www.knps.or.kr/common/cctv/cctv{번호}.html |
| 한라산 | https://www.jeju.go.kr/tool/halla/cctv_01.html |

**에이전트가 브라우저 자동화로 접속하지 말 것.** 사용자가 명시적으로 요청한 경우에만.

---

## 환경변수

| 변수 | 용도 | 필수 |
|------|------|------|
| KAKAO_REST_API_KEY | 카카오맵 CCTV(전국, 좌표·HLS) | 권장 |
| UTIC_API_KEY | UTIC 시내도로 CCTV | 권장 |
| ITS_API_KEY | ITS 고속도로/국도 CCTV | 권장 |
| WINDY_API_KEY | Windy 해외 웹캠([sense:cctv]{op:"webcam"}, search/nearby 폴백) | 선택 |

ffmpeg 필요: HLS 프레임 캡처 (brew install ffmpeg).

*최종 업데이트: 2026-06-03 — cctv_search/cctv_nearby → [sense:cctv]{op} 통합, 좌표 계약·playable·radius_km(km).*
