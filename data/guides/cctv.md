# CCTV 실시간 영상 가이드

## 빠른 사용법

### "OO의 모습을 보여줘" → cctv_search 한 줄이면 된다

```
[sense:cctv_search]("광화문")
[sense:cctv_search]("해운대")
[sense:cctv_search]("경부고속도로")
```

cctv_search는 ITS 교통 CCTV → Windy 웹캠 순으로 폴백 검색하고, 첫 결과의 프레임을 자동 캡처까지 한다.
반환값의 `auto_capture.file_path`로 이미지를 분석할 수 있다.

### ⚠️ 검색 결과 처리 원칙 (중요)

1. **cctv_search 한 번이면 충분하다.** 같은 장소를 키워드만 바꿔 반복 검색하지 말 것.
2. **정확한 이름 매칭이 안 되더라도, 좌표가 근접하면 그 결과를 사용한다.** 예: "광화문" 검색 → "Seoul › North" (37.56, 126.98) 반환 → 광화문 근처이므로 이것을 사용.
3. **결과가 나왔으면 첫 번째(또는 가장 가까운) 결과의 캡처 이미지를 사용자에게 보여주고 설명한다.**
4. **검색 결과가 0건이면** "해당 장소의 CCTV를 찾지 못했습니다"라고 안내한다. 웹 검색이나 브라우저 자동화로 우회하지 말 것.
5. **절대 하지 말 것**: 동일 요청에 3회 이상 cctv_search 반복, web_search로 CCTV URL 찾기, 브라우저로 외부 사이트 접속 시도

### 전세계 웹캠 검색

```
[sense:webcam]("Times Square") {"category": "city"}
[sense:webcam]("Mont Blanc") {"category": "mountain"}
```

### 좌표 기반 근처 검색

```
[sense:nearby]("서울역") {"lat": 37.5547, "lng": 126.9706}
[sense:webcam_nearby]("하와이") {"lat": 21.3069, "lng": -157.8583, "radius_km": 50}
```

nearby는 lat/lng가 필수. 모르면 cctv_search를 쓰는 게 더 간편하다.

### CCTV 영상을 브라우저에서 열기

```
[sense:cctv_search]("한라산") >> [sense:cctv_open]("browse")
```

### 프레임 캡처 (AI 분석용)

```
[sense:cctv_capture]("http://cctv-url/stream.m3u8")
```

### 소스 상태 확인

```
[sense:cctv_sources]()
```

---

## 도구 선택 기준

| 상황 | 액션 | 예시 |
|------|------|------|
| 장소 이름으로 CCTV 찾기 | `cctv_search` | `[sense:cctv_search]("광화문")` |
| 전세계 웹캠 검색 | `webcam` | `[sense:webcam]("Paris") {"category": "city"}` |
| 좌표 근처 CCTV | `nearby` | `[sense:nearby]("강남") {"lat": 37.49, "lng": 127.03}` |
| 좌표 근처 웹캠 | `webcam_nearby` | `[sense:webcam_nearby]("...") {"lat": ..., "lng": ...}` |
| CCTV URL 열기 | `cctv_open` | `[sense:cctv_open]("CCTV이름 또는 URL")` |
| 프레임 캡처 | `cctv_capture` | `[sense:cctv_capture]("http://...")` |
| 소스 상태 | `cctv_sources` | `[sense:cctv_sources]()` |

**중요: 대부분의 경우 `cctv_search`가 가장 간단하고 확실한 선택이다.**
nearby는 좌표를 알아야 하므로, 모르면 cctv_search를 쓸 것.

---

## AI 화면 분석 워크플로우

CCTV 화면을 AI가 직접 보고 판단하려면:

```
[sense:cctv_search]("해운대")
```

반환된 결과에서:
- `auto_capture.file_path`: 자동 캡처된 이미지 경로
- 이 이미지를 읽어서 교통, 날씨, 혼잡도 등 분석

분석 가능 항목: 교통 정체, 차량 밀도, 사고, 날씨(맑음/비/눈/안개), 파도, 혼잡도, 적설량

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

| 변수 | 용도 |
|------|------|
| ITS_API_KEY | ITS 교통 CCTV (cctv_search, nearby) |
| WINDY_API_KEY | Windy 전세계 웹캠 (webcam, webcam_nearby) |

ffmpeg가 필요: HLS 스트림 캡처 (brew install ffmpeg)

---

*최종 업데이트: 2026-03-06*
