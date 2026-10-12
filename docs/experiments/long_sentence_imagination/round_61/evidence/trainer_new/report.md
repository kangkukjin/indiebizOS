# 재고 대조

원본/고유/제외 및 상태별 건수: {"raw": 6, "unique": 6, "excluded": 0, "matched": 6, "different": 0, "unknown": 0}

| 품목 | 창고 | 기초 | 확인 순증감 | 실사 | 예상 | 차이 | 상태 |
|---|---|---:|---:|---:|---:|---:|---|
| A | 서울&#124;A | 10 | 1 | 11 | 11 | 0 | 일치 |
| a | 서울&#124;A | 20 | -2 | 18 | 18 | 0 | 일치 |
| 01 | 창고&lt;&amp;<br>둘 | 30 | 3 | 33 | 33 | 0 | 일치 |
| 1 | 창고&lt;&amp;<br>둘 | 40 | 4 | 44 | 44 | 0 | 일치 |
| é | 부산 | 50 | 5 | 55 | 55 | 0 | 일치 |
| NO-EVENT | 부산 | 60 | 0 | 60 | 60 | 0 | 일치 |

## 수량 미상 전표
[{"id": "EXTRA", "version": 1, "sku": "새품목", "warehouse": "부산", "kind": "반품", "qty": null, "sku_key": 6, "warehouse_key": 2}]

## 미등록 조합
[{"sku_key": 6, "warehouse_key": 2, "known": 0, "missing": 1, "events": 1, "sku": "새품목", "warehouse": "부산", "ids": ["EXTRA"]}]

## 누락 파일
[]

행별 근거 전표 ID는 result.json의 rows[].ids에 보존했습니다.
