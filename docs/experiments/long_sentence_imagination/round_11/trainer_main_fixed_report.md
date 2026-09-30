# 검침 정산

입력 3074행, 날짜별 2968건, 동일값 중복 100행.
전체 구간 2872개. 상태별: [{"status": "ok", "count": 2812}, {"status": "gap", "count": 8}, {"status": "conflict", "count": 12}, {"status": "unreadable", "count": 10}, {"status": "unpriced", "count": 30}].
확인된 사용량 36806, 확인된 요금 108800. 요율 미확인 30구간은 요금 null이며 총 청구액을 확정하지 않습니다.
충돌 날짜 6건, 판독불가 날짜 5건. 원본 source_id는 anomalies.json, 날짜별 구간은 intervals.json, 모든 계량기별 집계는 summary.json에 있습니다.
