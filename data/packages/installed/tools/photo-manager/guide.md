# Photo Manager 가이드

## 현재 사진 조회

`[self:photo]`는 OS 미디어 색인(맥 Spotlight·폰 MediaStore)을 조회합니다. PC 기본 범위는 `~/Pictures`이며 홈 전체의 개발용 이미지를 개인 사진으로 간주하지 않습니다. 다른 보관 폴더는 `path`로 지정합니다. 폰·USB는 기존 MediaStore 범위를 사용합니다.
먼저 스캔하거나 SQLite DB를 직접 조회할 필요가 없습니다.

```ibl
[self:photo]{start:"2021-04-01",end:"2021-04-30",has_gps:true,limit:100}
```

기간과 GPS 보유 조건을 함께 적용합니다. `start`·`end`는 현지 촬영일 기준으로
`YYYY-MM` 또는 `YYYY-MM-DD`를 받습니다. `taken_at`에는 시간대가 포함됩니다.
결과 `items`에는 `path`, `taken_at`, `month`, `lat`, `lng`, `camera`, `kind`,
`size`, `source`, `origin` 등이 담깁니다. 날짜·좌표가 미상이면 그 사실을 유지합니다.
`origin:unknown`은 생성 이미지라는 뜻이 아닙니다. 위도·경도 0도는 유효한 좌표입니다.

경로 생략 시 홈에서 시스템 outputs·data·프로젝트 outputs를 제외합니다.
특정 폴더의 산출물까지 보려면 `path`를 명시합니다. 단일 파일 상세는 `file`을 사용합니다.
`limit`로 제한된 결과를 전체 사진 수로 보고하지 말고 결과의 잘림·경고 표지를 확인합니다.

## 날짜·장소별 조합

조회 결과를 `$photos`로 받은 뒤 `$photos.items`를 표 변환자의 `items`에 전달합니다.
월별 집계는 `month`를 기준으로 그룹화할 수 있습니다.
`has_gps:true`는 위치 정보의 존재만 확인하므로 특정 도시나 반경 검색과 다릅니다.
좌표 범위는 콜백으로 걸러냅니다. 다음은 제주 일대 사각 범위의 예입니다.

```ibl
$photos = [self:photo]{start:"2021-04",end:"2021-04",has_gps:true,limit:100};
[table:filter]{items:$photos.items,where:($r)=>$r.lat >= 33.2 && $r.lat <= 33.6 && $r.lng >= 126.1 && $r.lng <= 126.9}
```

좌표의 주소 확인에는 `[sense:reverse_geocode]{lat:33.4,lon:126.5}`를 사용합니다.
GPS 없는 사진은 위치 필터에서 빠집니다. PC에서 USB 안드로이드 사진을 조회하는
`source:"usb"`는 GPS 필터를 지원하지 않습니다.

## 기존 스캔 자료

사진 관리 풍부창(REST)의 기존 스캔은 `data/packages/photo_scans/`의
`scans.json`과 `scan_{id}.db`에 남아 있습니다. 해당 화면의 스캔·타임라인 기능은
이 자료를 사용하며 현재 `[self:photo]`의 라이브 조회와 구분합니다.
기존 스캔의 날짜·GPS·촬영 기종이 없으면 미상이며, 현재 파일 상태나 전체 사진의
완전한 목록으로 간주하지 않습니다.
