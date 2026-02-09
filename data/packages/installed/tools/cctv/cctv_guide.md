# CCTV 실시간 영상 가이드

## 도구 선택 가이드

### 한국 교통 상황 확인
- `search_cctv` / `get_nearby_cctv` / `get_cctv_by_name` 사용
- 고속도로/국도 CCTV 실시간 영상 URL 제공
- 소스: ITS 국가교통정보센터

### 전세계 웹캠 검색
- `search_webcam` / `get_nearby_webcam` 사용
- 18개 카테고리: beach, mountain, city, airport, coast, forest, lake, landscape, meteo, port, river, traffic 등
- 소스: Windy Webcams (전세계 수십만 개)

### 한국 해변/해안 확인
- `search_coastal_cctv` 사용
- 해운대, 경포, 중문 등 주요 해수욕장 약 20개소

### 한국 국립공원 확인
- `search_park_cctv` 사용
- 17개 국립공원 (설악산, 한라산, 지리산 등)
- 산 정상 날씨/적설/단풍 상황 확인에 유용

### AI 화면 분석
- `capture_cctv` 사용
- CCTV URL에서 프레임 캡처 → 이미지 파일 저장
- 저장된 이미지를 읽어서 교통 상황, 날씨, 혼잡도 등 분석

### 소스 상태 확인
- `list_cctv_sources` 사용
- API 키 설정 여부, ffmpeg 설치 여부 확인

---

## AI 화면 분석 워크플로우

CCTV 화면을 AI가 직접 보고 판단하려면:

```
1. CCTV 검색 (search_cctv, search_webcam 등) → URL 획득
2. capture_cctv(url=URL) → 이미지 파일 경로 반환
3. 반환된 file_path의 이미지를 읽어서 상황 분석
```

### 분석 가능한 항목
- 교통: 정체 여부, 차량 밀도, 사고 유무
- 날씨: 맑음/흐림/비/눈, 안개, 시야 상태
- 해변: 파도 상태, 사람 수, 일출/일몰
- 산: 적설량, 단풍, 등산 가능 여부
- 도시: 혼잡도, 야경, 축제/이벤트

---

## 도구로 직접 안 되는 CCTV 찾기 (확장 전략)

내장 도구(ITS, Windy, 연안, 국립공원)로 원하는 CCTV를 못 찾을 때, **web 패키지 + browser-action 패키지를 조합**하면 지구 어디든 CCTV를 찾아 캡처할 수 있다.

### 전략 1: 웹 검색으로 CCTV 스트리밍 URL 찾기

```
1. ddgs_search(query="[장소명] 실시간 CCTV" 또는 "[place] live webcam")
2. 검색 결과에서 CCTV/웹캠 페이지 URL 확인
3. crawl_website(url=페이지URL) → 페이지 내 m3u8/영상 URL 추출
4. capture_cctv(url=찾은URL) → 캡처
```

### 전략 2: 브라우저로 CCTV 페이지 직접 접속

```
1. browser_navigate(url="CCTV 페이지 URL")
2. browser_snapshot() → 영상 플레이어 요소 확인
3. browser_screenshot() → 현재 화면 캡처 (이게 곧 CCTV 화면)
```

이 방법은 JavaScript 렌더링이 필요한 CCTV 사이트에도 작동한다.

### 전략 3: 알려진 글로벌 CCTV 사이트 활용

다음 사이트들에서 전세계 CCTV를 찾을 수 있다:

| 사이트 | 범위 | 특징 |
|--------|------|------|
| insecam.org | 전세계 공개 IP카메라 | 국가/도시별 분류 |
| earthcam.com | 전세계 주요 관광지 | 고화질 |
| skylinewebcams.com | 전세계 관광지/해변 | 실시간 HD |
| opentopia.com | 전세계 공개 웹캠 | 카테고리 분류 |
| webcamtaxi.com | 전세계 관광/도시 | 국가별 분류 |
| balticlivecam.com | 유럽 (발트해 중심) | 항구/해변 |
| explore.org/livecams | 전세계 자연/야생동물 | 환경/동물 관찰 |

#### 활용법
```
1. browser_navigate(url="https://www.skylinewebcams.com")
2. browser_snapshot() → 검색 또는 카테고리 탐색
3. 원하는 CCTV 페이지로 이동
4. browser_screenshot() → 화면 캡처 → AI 분석
```

### 전략 4: 한국 특화 CCTV 사이트

| 사이트 | 범위 |
|--------|------|
| its.go.kr/map/cctv | 전국 교통 CCTV (지도) |
| coast.mof.go.kr | 연안 침식 모니터링 |
| www.knps.or.kr (실시간영상) | 국립공원 |
| www.jeju.go.kr/tool/halla/cctv_01.html | 한라산 |
| www.weather.go.kr | 기상청 관측 카메라 |
| www.badatime.com/cctv | 전국 바다 CCTV 모음 |
| cctv.jejudoin.co.kr | 제주도 종합 CCTV |
| www.cctv-world.kr | 전국 해변 CCTV 모음 |

#### 활용법
```
1. browser_navigate(url="https://www.badatime.com/cctv")
2. browser_snapshot() → 해변 선택
3. browser_click(ref=해당해변) → 스트리밍 페이지
4. browser_screenshot() → 화면 캡처
```

### 전략 5: 특정 국가/도시 CCTV

어느 나라든 "[도시명] live camera" 또는 "[도시명] CCTV stream"으로 검색하면 대부분 찾을 수 있다.

```
1. ddgs_search(query="Times Square New York live webcam")
2. 결과에서 스트리밍 페이지 URL 확인
3. browser_navigate(url=결과URL)
4. browser_screenshot() → 캡처
```

또는 Windy 웹캠이 전세계를 커버하므로:
```
1. search_webcam(lat=40.758, lon=-73.9855, radius_km=5, category="city") → 타임스퀘어
2. 결과의 image_url로 capture_cctv() → 캡처
```

---

## 다른 패키지와의 관계

### web 패키지
- `ddgs_search`: CCTV 사이트/스트리밍 URL 검색
- `crawl_website`: CCTV 페이지에서 스트리밍 URL 추출

### browser-action 패키지
- JavaScript 렌더링이 필요한 CCTV 사이트 접속
- `browser_screenshot`: 가장 범용적인 CCTV 화면 캡처 방법
- 어떤 CCTV 사이트든 브라우저로 열고 스크린샷 가능

### location-services 패키지
- 위치 좌표 조회 → CCTV 근처 검색에 활용
- "서울역 근처 CCTV" → 서울역 좌표 조회 후 get_nearby_cctv

---

## capture_cctv 소스 타입 판별

| URL 패턴 | source_type | 캡처 방법 |
|-----------|-------------|-----------|
| `*.m3u8*` | hls | ffmpeg |
| `*.jpg`, `*.png`, `*.webp` | image | requests |
| `images-webcams.windy.com/*` | image | requests |
| 그 외 | auto | 이미지 시도 → HLS 시도 |

---

## 환경변수

| 변수 | 용도 | 필수 |
|------|------|------|
| ITS_API_KEY | ITS 교통 CCTV | search_cctv 등 사용시 |
| WINDY_API_KEY | Windy 전세계 웹캠 | search_webcam 등 사용시 |

ffmpeg가 설치되어 있어야 HLS 스트림 캡처가 가능하다. (brew install ffmpeg)
