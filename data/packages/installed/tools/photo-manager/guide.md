# Photo Manager 가이드

## 스캔 DB 구조

스캔 데이터는 `data/packages/photo_scans/` 폴더에 저장됩니다.
- `scans.json` — 스캔 목록 (id, name, root_path, photo_count 등)
- `scan_{id}.db` — 각 스캔별 SQLite DB

### media_files 테이블 주요 컬럼

| 컬럼 | 타입 | 설명 |
|------|------|------|
| path | TEXT | 파일 절대경로 |
| filename | TEXT | 파일명 |
| taken_date | TEXT | 촬영일 (ISO8601, 예: 2021-04-15T14:30:00) |
| gps_lat | REAL | 위도 (예: 37.5665) |
| gps_lon | REAL | 경도 (예: 126.9780) |
| media_type | TEXT | "photo" 또는 "video" |
| camera_model | TEXT | 카메라 모델명 |
| size | INTEGER | 파일 크기 (바이트) |

## 워크플로우

### 1. 특정 기간/장소 사진 조회

도구만으로는 기간+위치 조건 검색이 불가능합니다. **반드시 Python으로 DB를 직접 쿼리하세요.**

**순서:**
1. `list_scans`로 스캔 목록 및 DB 경로 확인
2. Python으로 해당 DB에 SQL 쿼리

```python
import sqlite3
conn = sqlite3.connect("DB경로")  # list_scans 결과의 DB 경로
cur = conn.cursor()

# 2021년 4월 GPS 있는 사진
cur.execute("""
    SELECT filename, taken_date, gps_lat, gps_lon, path
    FROM media_files
    WHERE taken_date LIKE '2021-04%'
      AND gps_lat IS NOT NULL AND gps_lon IS NOT NULL
      AND gps_lat != 0 AND gps_lon != 0
    ORDER BY taken_date
""")
rows = cur.fetchall()
```

3. GPS 좌표를 지역명으로 변환 — `[source:reverse_geocode]` 사용:
```
[source:reverse_geocode] {lat: 35.32, lon: 129.27}
→ {"address": "경상남도 울산광역시 울주군 ...", "region_1depth": "울산광역시", ...}
```

Python에서 클러스터링 후 좌표별 장소 확인:
```python
from collections import defaultdict
clusters = defaultdict(list)
for row in rows:
    key = (round(row[2], 1), round(row[3], 1))
    clusters[key].append(row)

# 주요 위치별 사진 수 → reverse_geocode로 도시명 확인
for (lat, lon), photos in sorted(clusters.items(), key=lambda x: -len(x[1])):
    print(f"위치 ({lat}, {lon}): {len(photos)}장")
```

### 2. 월별 촬영 현황 (타임라인)

`get_timeline` 도구를 사용하거나 Python으로 직접 조회:

```python
cur.execute("""
    SELECT substr(taken_date, 1, 7) as month,
           COUNT(*) as cnt,
           SUM(CASE WHEN gps_lat IS NOT NULL THEN 1 ELSE 0 END) as gps_cnt
    FROM media_files
    WHERE media_type = 'photo'
    GROUP BY month ORDER BY month
""")
```

### 3. 특정 지역 사진 검색

대한민국 주요 도시 좌표 범위:
- 서울: lat 37.4~37.7, lon 126.8~127.2
- 부산: lat 35.0~35.3, lon 128.9~129.2
- 제주: lat 33.2~33.6, lon 126.1~126.9

```python
cur.execute("""
    SELECT filename, taken_date, gps_lat, gps_lon
    FROM media_files
    WHERE gps_lat BETWEEN 33.2 AND 33.6
      AND gps_lon BETWEEN 126.1 AND 126.9
    ORDER BY taken_date
""")
# → 제주도에서 찍은 사진
```

## 주의사항

- `get_gallery`, `get_stats`, `get_timeline`은 경로 없이 호출하면 가장 큰 스캔을 자동 선택합니다.
- GPS 좌표 → 도시명 변환은 `[source:reverse_geocode] {lat: 위도, lon: 경도}` 사용 (카카오 API).
- GPS 정보가 없는 사진도 많습니다. GPS 검색 시 결과가 적을 수 있습니다.
- 여러 스캔 DB가 있을 수 있습니다. 필요하면 모든 DB를 순회하세요.
