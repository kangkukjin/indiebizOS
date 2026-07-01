# 사진·동영상 관리 가이드

`[self:photo]` 단일 액션으로 로컬 사진/동영상 라이브러리를 스캔·조회·검색·분석한다. **op 8종**이 핵심 분기.

전제: **사용 전 한 번은 `op:"scan"`이 필요하다.** 모든 조회는 스캔 인덱스(SQLite) 위에서 동작.

기술 깊이(직접 SQL 쿼리, DB 스키마)는 패키지 [`photo-manager/guide.md`](../packages/installed/tools/photo-manager/guide.md) 참조. 이 가이드는 **IBL 액션 사용 워크플로우**에 집중.

---

## 8 op 사양

| op | 필수 | 옵션 | 결과 |
|---|---|---|---|
| `scan` | `path` (폴더 절대경로) | — | 폴더 재귀 스캔 + EXIF/메타 추출 + SQLite 인덱싱 |
| `list_scans` | (없음) | — | 지금까지 스캔한 폴더 목록 + 통계 요약 |
| `gallery` | `path` | `page`, `limit`, `media_type`(photo\|video), `sort_by`(taken_date\|mtime\|size\|filename), `start_date`, `end_date` | 페이지네이션 + 필터 갤러리 |
| `search` | `query` | `media_type`, `start_date`, `end_date`, `limit`, `path` | 파일명·카메라 모델 키워드 검색 |
| `detail` | `media_id` | `path` (정확한 스캔 지정 시) | 단일 미디어 전체 메타(EXIF/GPS/해상도/MD5) |
| `stats` | `path` | — | 사진/동영상 수·용량·카메라 분포 |
| `timeline` | `path` | `year` (특정 연도만) | 월별 촬영 통계 (활동 패턴) |
| `duplicates` | `path` | — | MD5 해시 기반 중복 탐지 |

### `path` 자동 해석

`scan`을 제외한 op는 `path`를 생략하면 **가장 많이 스캔된 폴더가 자동 선택**된다. 한 스캔만 있는 경우 그걸 자동 사용.

`path`를 줬는데 그게 스캔된 적이 없으면 디렉토리 존재 여부만 검증하고 자동 선택으로 fallback.

### `media_id`

`gallery`/`search`/`duplicates` 결과의 각 항목에 들어 있는 `id` 필드. 정수.

---

## 표준 워크플로우

### 1) 첫 사용 — 인덱싱부터
```
[self:photo]{op:"scan", path:"/Users/k/Pictures"}
→ 스캔 완료. 사진·동영상 수, 총 용량, 오류 건수 반환
[self:photo]{op:"list_scans"}                    # 무엇이 스캔됐는지 확인
```

### 2) 갤러리 보기
```
[self:photo]{op:"gallery", path:"/Users/k/Pictures", limit:30}
[self:photo]{op:"gallery", path:"/Users/k/Pictures", media_type:"video"}
[self:photo]{op:"gallery", path:"/Users/k/Pictures",
             start_date:"2024-01-01", end_date:"2024-12-31"}
```

### 3) 키워드/메타 검색
```
[self:photo]{op:"search", query:"sunset"}
[self:photo]{op:"search", query:"iPhone 14"}              # 카메라 모델
[self:photo]{op:"search", query:"", media_type:"video",
             start_date:"2025-03-01", end_date:"2025-03-31"}
→ 검색 결과의 id로 detail 호출
[self:photo]{op:"detail", media_id:42}
```

### 4) 활동 패턴 보기
```
[self:photo]{op:"timeline", path:"/Users/k/Pictures"}
→ 월별 사진/동영상 건수 (활동 시기 시각화)
[self:photo]{op:"timeline", path:"/Users/k/Pictures", year:2024}
```

### 5) 통계 + 차트로 연결
```
[self:photo]{op:"stats", path:"/Users/k/Pictures"}
[self:photo]{op:"timeline", path:"/Users/k/Pictures"}
  >> [table:chart_bar]{x:"month", y:"count"}
```

### 6) 정리 — 중복 찾기
```
[self:photo]{op:"duplicates", path:"/Users/k/Pictures"}
→ MD5 같은 파일 그룹 목록. 용량 절감 정리용
```

### 7) 깊은 쿼리 — Python 직접 사용
IBL 도구로 부족할 때 (예: GPS 좌표 범위로 장소별 필터, 사진→비디오 대비 비율 등):
```
[self:photo]{op:"list_scans"}
→ 결과에서 DB 경로 확보
[engines:python]{code:"
  import sqlite3
  conn = sqlite3.connect('<DB 경로>')
  rows = conn.execute('SELECT path FROM media_files WHERE gps_lat BETWEEN ? AND ?', (...)).fetchall()
  ..."}
```
스키마는 패키지 `guide.md` 참조.

---

## 자연어 의도 매핑

| 사용자 말 | op |
|---|---|
| "사진 정리해야 해 / 폴더 스캔" | `scan` |
| "사진 통계 보여줘 / 카메라별로" | `stats` |
| "월별로 어떻게 찍었어 / 활동 패턴" | `timeline` |
| "사진 좀 보여줘 / 갤러리" | `gallery` |
| "비디오만 보고 싶어" | `gallery` + `media_type:"video"` |
| "이 키워드 사진 찾아줘 / iPhone으로 찍은 거" | `search` |
| "이 사진 상세 정보 / EXIF" | `detail` |
| "중복 파일 찾아 / 용량 줄이기" | `duplicates` |
| "어떤 폴더 스캔했어" | `list_scans` |

---

## 자주 하는 실수

- **scan 없이 다른 op 호출**: "스캔 데이터 없음" 에러. 첫 단계 필수.
- **path 형식**: 절대경로 권장. `~/Pictures` 같은 홈 디렉토리 표기는 자동 expanduser되지만, 상대 경로(`./Pictures`)는 위험.
- **start_date/end_date 형식**: `YYYY-MM-DD` 또는 ISO8601. `2024/01/01` 안 됨.
- **search 결과의 path**: 검색 결과 항목은 *파일 경로* 포함. `[limbs:os_open]`이나 `[self:copy]` 등으로 바로 엮어 쓸 수 있음.
- **media_id 자릿수**: 검색/갤러리 결과의 `id` 그대로. URL 디코딩 같은 처리 필요 없음.
- **외장 드라이브 스캔 후 분리**: 스캔 DB는 남아 있지만 실제 파일 경로 접근은 외장 드라이브 마운트 시에만. detail/gallery는 DB만 봐서 OK.
- **여러 스캔 폴더 혼동**: `list_scans`로 어떤 스캔이 있는지 확인 후 path 지정.

## 관련

- [`photo-manager/guide.md`](../packages/installed/tools/photo-manager/guide.md) — DB 스키마 + 직접 SQL 쿼리 예제
- `[table:chart_bar]`, `[table:chart_line]` — 통계/타임라인 시각화
- `[limbs:show_map]` — GPS 좌표 사진을 지도에 점으로 표시 (gallery 결과의 gps_lat/gps_lon 활용)
- `[engines:python]` — 깊은 쿼리/정리 자동화
