# 39회차 최소 재현 (HTTP /ibl/execute, origin:"training", project_id:"수동모드")

- `crlf_read.ibl` — CRLF 파일을 `self:read`(text) 로 읽으면 CR 이 사라지고(28자→24자) 그 본문을 `self:write` 하면 LF 파일이 된다. 입력(`inputs`)으로 준 CRLF 문자열은 보존된다. → L39-1
- `nfd_replace.ibl` — NFD 한글 입력에 일치하지 않는 `replace`/`split`+`join`/슬라이스를 적용하면 반환이 NFC 로 바뀐다(17 코드포인트→9). `self:read`→`self:write` 원시 왕복은 바이트 불변. → L39-2
- `contains_ws.ibl` — `contains("abc","\r")`·`"\n"`·`"\t"`·`" "`·`""`·`" "` 전부 true. → L39-3
- 4배 규모(144파일·4,616줄) 전체 프로그램은 `budget.steps` 최대 100만에서 BUDGET 실패(`evidence/trainer_big_main_v1.json`·`_v2.json`). 줄당 약 580 단계(v1)·410 단계(v2). → L39-4
