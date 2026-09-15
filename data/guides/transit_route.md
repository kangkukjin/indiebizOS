# 대중교통 길찾기 — [sense:navigate_route]{mode:"transit"}

버스·지하철을 이용할 때 `mode:"transit"`을 명시한다. 생략하면 기존 자동차 경로다.

```ibl
[sense:navigate_route]{mode:"transit", origin:"서울역", destination:"강남역"}
[sense:navigate_route]{mode:"transit", origin:"126.9726,37.5547", destination:"127.0276,37.4979"} >> [table:sort]{by:"duration_min"}
```

- 공급자: ODsay. `ODSAY_API_KEY`를 런처 설정 → API 키 → 포털·지도에 등록해야 한다. 장소명 좌표 변환에는
  기존 카카오 API 설정도 필요하다. 좌표는 **경도,위도** 순서다.
- 현재 지원은 도시내 경로다. `waypoints`·`avoid`·`priority`는 자동차 전용이라
  transit에 함께 쓰면 오류를 반환한다.
- 도시내 성공 `items`: `duration_min`(분), `walking_distance_m`(m), `fare_krw`(원),
  `transfer_count`, `path_type`, `segments`(도보·버스·지하철 구간), `complete:true`.
  `segments`와 `provider_info`는 공급자 근거를 보존한다.
- 조회 기준 시각 `observed_at`과 공급자를 함께 반환한다. 실시간 도착·혼잡도·막차 보장·
  예약 기능은 아니다(`live_arrival:false`). 요금·시간은 공급자의 경로 예상치다.

## 실패와 부분 결과

키 없음, 좌표 오류, 경로 없음, 공급자 오류를 구별한다. 오류를 자동차 경로로 바꾸지 않는다.
일부 도시내 경로만 형식이 잘못됐으면 `partial:true`, `rejected`와 유효한 items를 반환한다.
도시간 결과는 터미널까지/이후의 연결 구간이 빠져 있으므로 `success:false`,
`error_type:incomplete_route`, `partial:true`, 각 행 `complete:false`로 반환한다.
이 결과를 출발지부터 목적지까지 완결된 안내로 제시하지 않는다.

자동차·장소 검색은 [map.md](map.md)를 함께 본다.

지도 앱: 길찾기 → 대중교통 → 출발·도착 입력 → 길찾기. 경로별 시간·요금·환승·도보를 비교하고 상세 구간을 펼친다. 선택 경로의 정류장이 지도에 표시된다. 원격/폰 선언형 지도에도 대중교통 요약 탭이 있다.
