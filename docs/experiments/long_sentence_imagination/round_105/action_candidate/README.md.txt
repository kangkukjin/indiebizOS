# 시험 점검 자료 공급자 (ls105-inspection)

105회차 시험 범위 전용 패키지다. 실제 운영 사전에는 추가하지 않는다.

`[sense:ls105_inspection]`은 몸의 `inputs/inspection_source.json`(JSON 행 목록)을 읽어 `items`로 반환하는 source다.
반환 행은 원래의 `asset_id`, `checked`, `source_revision`을 보존한다.

```ibl
#!ibl edition=2
[sense:ls105_inspection]{}                    # 전체 행 (M1, M2)
[sense:ls105_inspection]{query:"M1"}          # asset_id = M1 인 행 하나
[sense:ls105_inspection]{query:"X"}           # 일치 없음 → 빈 items (성공)
[sense:ls105_inspection]{} >> [table:filter]{where:($r) => $r.checked}   # 점검 완료 행만
```

실패 구분: 파일 부재 `SOURCE_MISSING`, JSON 파싱 실패·행 목록이 아님 `SOURCE_PARSE_ERROR` (`success:false`).

검사 예제: `test_ls105_inspection.py` (핸들러를 직접 불러 전체·한 건·0건·부재·파싱 실패를 대조).
