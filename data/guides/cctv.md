# CCTV 실시간 영상 가이드

## 빠른 사용법

### "OO의 모습을 보여줘" → cctv_search 한 줄이면 된다

```
[sense:cctv_search]{query: "광화문"}
[sense:cctv_search]{query: "해운대"}
[sense:cctv_search]{query: "경부고속도로"}
```

cctv_search는 UTIC 시내도로 → ITS 고속도로/국도 → Windy 웹캠 순으로 통합 검색하고, 첫 결과의 프레임을 자동 캡처까지 한다.
반환값의 `auto_capture.file_path`로 이미지를 분석할 수 있다.

**데이터 소스 (검색 순서)**:
1. **UTIC 도시교통정보센터** — 전국 시내 도로 CCTV 16,000+대 (실시간 API)
2. **ITS 국가교통정보센터** — 고속도로/국도 CCTV
3. **Windy Webcams** — 전세계 웹캠 (한국 결과 없을 때 폴백)

### ⚠️ 검색 결과 처리 원칙 (중요)

1. **cctv_search 한 번이면 충분하다.** 같은 장소를 키워드만 바꿔 반복 검색하지 말 것.
2. **정확한 이름 매칭이 안 되더라도, 좌표가 근접하면 그 결과를 사용한다.** 예: "광화문" 검색 → "Seoul › North" (37.56, 126.98) 반환 → 광화문 근처이므로 이것을 사용.
3. **결과가 나왔으면 첫 번째(또는 가장 가까운) 결과의 캡처 이미지를 사용자에게 보여주고 설명한다.**
4. **검색 결과가 0건이면** "해당 장소의 CCTV를 찾지 못했습니다"라고 안내한다. 웹 검색이나 브라우저 자동화로 우회하지 말 것.
5. **절대 하지 말 것**: 동일 요청에 3회 이상 cctv_search 반복, web_search로 CCTV URL 찾기, 브라우저로 외부 사이트 접속 시도

### 전세계 웹캠 검색

```
[sense:webcam]{query: "Times Square", category: "city"}
[sense:webcam]{query: "Mont Blanc", category: "mountain"}
```

### 좌표 기반 근처 검색

```
[sense:cctv_nearby]{lat: 37.5547, lng: 126.9706}
[sense:webcam_nearby]{lat: 21.3069, lng: -157.8583, radius_km: 50}
```

cctv_nearby는 lat/lng가 필수. 모르면 cctv_search를 쓰는 게 더 간편하다.

### CCTV 영상을 브라우저에서 열기

```
[sense:cctv_search]{query: "한라산"} >> [sense:cctv_open]
```

### 프레임 캡처 (AI 분석용)

```
[sense:cctv_capture]{url: "http://cctv-url/stream.m3u8"}
```

### 소스 상태 확인 및 데이터 관리

```
[sense:cctv_sources]          # 소스 목록 + API 연결 상태
[sense:cctv_stats]            # 센터별 통계 (CCTV 수, 데이터 소스)
[sense:cctv_refresh]          # UTIC API에서 최신 목록 강제 갱신
```

---

## 도구 선택 기준

| 상황 | 액션 | 예시 |
|------|------|------|
| 장소 이름으로 CCTV 찾기 | `cctv_search` | `[sense:cctv_search]{query: "광화문"}` |
| 전세계 웹캠 검색 | `webcam` | `[sense:webcam]{query: "Paris", category: "city"}` |
| 좌표 근처 CCTV | `cctv_nearby` | `[sense:cctv_nearby]{lat: 37.49, lng: 127.03}` |
| 좌표 근처 웹캠 | `webcam_nearby` | `[sense:webcam_nearby]{lat: 21.31, lng: -157.86, radius_km: 50}` |
| CCTV URL 열기 | `cctv_open` | `[sense:cctv_open]{name: "CCTV이름"}` |
| 프레임 캡처 | `cctv_capture` | `[sense:cctv_capture]{url: "http://..."}` |
| 소스 상태 | `cctv_sources` | `[sense:cctv_sources]` |
| CCTV 데이터 통계 | `cctv_stats` | `[sense:cctv_stats]` |
| UTIC 데이터 갱신 | `cctv_refresh` | `[sense:cctv_refresh]` |

**중요: 대부분의 경우 `cctv_search`가 가장 간단하고 확실한 선택이다.**
cctv_nearby는 좌표를 알아야 하므로, 모르면 cctv_search를 쓸 것.

---

## AI 화면 분석 워크플로우

CCTV 화면을 AI가 직접 보고 판단하려면:

```
[sense:cctv_search]{query: "해운대"}
```

반환된 결과에서:
- `auto_capture.file_path`: 자동 캡처된 이미지 경로
- 이 이미지를 읽어서 교통, 날씨, 혼잡도 등 분석

분석 가능 항목: 교통 정체, 차량 밀도, 사고, 날씨(맑음/비/눈/안개), 파도, 혼잡도, 적설량

---

## UTIC 실시간 API 구조

UTIC(도시교통정보센터)는 전국 시내 도로 CCTV 16,000+대를 실시간 API로 제공한다.

- **API 엔드포인트**: `http://www.utic.go.kr/map/mapcctv.do`
- **인증**: UTIC_API_KEY + Referer 헤더 필수
- **데이터 갱신**: API 우선, 실패 시 로컬 캐시 폴백 (메모리 캐시 TTL 10분)
- **반환 필드**: cctvname, lat, lng, kind(1=시내, 7=고속도로), cctvurl(HLS 스트림), stream_id

`cctv_refresh` 액션으로 수동 갱신 가능. 일반적으로는 자동 캐시 관리로 충분하다.

---

## 참고: 한국 해안/국립공원 CCTV 사이트

아래 사이트들은 사용자가 직접 접속하는 참고용. **에이전트가 브라우저 자동화로 접속을 시도하지 말 것.**

| 사이트 | URL |
|--------|-----|
| 해양수산부 연안 | https://coast.mof.go.kr/coastScene/coastMediaService.do |
| 바다타임 | https://www.badatime.com/cctv |
| 국립공원공단 | https://www.knps.or.kr/common/cctv/cctv{번호}.html |
| 한라산 | https://www.jeju.go.kr/tool/halla/cctv_01.html |

사용자가 명시적으로 "이 사이트에서 CCTV를 찾아줘"라고 요청한 경우에만 브라우저 접근 가능.

---

## 환경변수

| 변수 | 용도 | 필수 |
|------|------|------|
| UTIC_API_KEY | UTIC 시내 도로 CCTV 16,000+대 (cctv_search 1순위) | 권장 |
| ITS_API_KEY | ITS 고속도로/국도 CCTV (cctv_search 2순위) | 권장 |
| WINDY_API_KEY | Windy 전세계 웹캠 (webcam, webcam_nearby, 폴백) | 선택 |

ffmpeg가 필요: HLS 스트림 캡처 (brew install ffmpeg)

---

*최종 업데이트: 2026-03-09*
