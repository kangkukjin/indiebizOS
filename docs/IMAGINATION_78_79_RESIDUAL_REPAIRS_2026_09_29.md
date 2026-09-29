# 상상훈련 78·79회차 잔여 수리 (2026-09-29)

`747d5103`(77~81 공통 경계 수리)이 닫지 못한 78·79회차 항목을 라이브 재탐침으로 다시 골라 고쳤다. 원 보고서의 훈련 당시 관측은 덮어쓰지 않고, 각 보고서 끝 "집행 완료" 절에 이번 수리를 적었다.

## 재탐침 — 이미 닫힌 것과 샌 것

`747d5103` 이후 라이브(옛 코드)에서 각 보고서의 최소 재현을 다시 돌렸다.

- **닫혀 있던 것**: B78-1(recent_chats 판본 2 성공) · B78-2(새 agent 기억 DB·오타 건강 주체 생성 없음) · B78-3(두 낱말 AND) · B78-7(궤적 source=training) · B78-8(JSON 문자열 실패 → success=0) · B79-1(주말 공연 9건) · B79-2(미지 지역 거절) · B79-5(네이버 전국 행 제거) · B79-6(1박가 필터) · B79-7(전시 lat/lng) · B79-8(판본 1 descending)
- **샌 것**: B78-4·5·6, F78-1·2·3·4·5, 기억 대화 미리보기 무표지(B72-3), B79-3(당근은 정직 실패로만 바뀌고 검색 자체가 안 됨), B79-4, B79-5 블로그 지역어, show_map 좌표 별칭, B79-2 거절 문구의 dict 덤프, F79-1·2·3, 날씨 `days`·반경 침묵 클램프, 판본 1 경고 생성기 모순, 교재 드리프트

## 뿌리와 수리

공통 뿌리는 보고서가 짚은 그대로다. **같은 사실을 층마다 따로 번역했고, 선언과 동작을 대조하는 관문이 없었다.** 이번 수리는 사실마다 번역기를 한 벌로 모으고, 형제 자리를 사람이 고르지 않도록 관문을 먼저 세웠다.

| 항목 | 뿌리 | 수리 |
|---|---|---|
| F78-1·B78-4 | "그 장소가 있나"를 root_missing(경로 문서)·reconcile(경로 노드)·노트북 삭제(모름)가 따로 판정 | `forage_memory.place_exists(body, locus)` 한 벌(경로=디스크·미장착 None, notebook=노트북 저장소, book/웹=None). recall 이 `locus_exists`·`own_count`·`doc_is_ancestor` 를 싣고 root_missing·freshness·reconcile 이 같은 확인기를 쓴다. notebook delete 가 그 몸 기억을 기존 `_gone` 1주 유예로 접는다(유예가 옮긴 파일의 옛 mtime 으로 사실상 0이던 구멍도 수리). 수리 전 고아는 접지 않고 표식·`held` 만 |
| B78-5 | 책·노트북 몸을 입구는 정규화 면제, 회상은 locus 문자열 비교 | `own_space_label/body/address` 한 벌을 입구(locus 관문·canonical_body·note)와 회상(locus 해석·장소 id·문서 덮기)이 공유. own-space locus 는 `<몸>`·`<몸>/<하위>` 만. 옛 괄호·주제 이름 행도 데이터 개명 없이 정규형으로 찾아진다. 증류 프롬프트의 형태 자리표를 예시형으로 |
| F78-3 forage | 판본 1 판정 문구·은퇴 인자 잔존 | 선언을 "Record, `$f.map >> [table:…]`" 로, 계약에서 `layer`·`table` 제거 + `retired_contracts.yaml` 등록 |
| F78-2 | 인자 선언이 비면 계약이 **기본값으로 열림**(`open_params: keys is None`) | 관문 `scripts/iblbuild_open_params.py`(레지스트리와 같은 계약 함수로 열린 계약 전수, 사유 없는 개방 = build 실패). 20개 중 18개를 핸들러가 실제 읽는 키로 닫고 2개(`table:each`·`self:workflow`)만 사유를 달아 연다. `unknown_param_hint` 선언 → recent_chats 의 days/query/since 는 "[table:filter] 로" 안내와 함께 거절 |
| F78-3 health | 핸들러가 튜플 루프로 읽는 평탄 키를 구현-읽기 관문이 못 봄 | `iblbuild_action_reads.py` 가 리터럴 튜플 루프도 본다 → 평탄 키 13개 선언. 측정 조회 선언을 table 통화로 정정하고 0건도 같은 모양 |
| B72-3 | 대화 가지 미리보기에 행 표지 없음 | `preview_truncated`·`content_chars`·`preview_offset`(장기기억 가지와 같은 이름) + 봉투 selection scope |
| F78-4 | 도달 가능 셈이 활성 원장을 모름 | `ibl_registry.self_can_run`(describe 와 같은 정본)으로 셈 — 139 → 126 |
| F78-5 | ledger 원자 쓰기가 몸의 쓰기 원장 밖 | 공통 훅 `write_ledger.log_write(gate="self_ledger")` |
| 부수(78 작업 중 발견) | 평문 실패 판정이 파이프 판정기·통화 분류기·판본 2 어댑터·감독 검토에 따로 적힘. 엔진이 인자 경고를 평문 머리에 붙이면 접두 판정이 성공으로 샘. 분류기는 평문 실패를 text 성공으로 기록 | `common.currency` 의 `decorate_param_warning`·`plain_body`·`is_plain_failure` 한 벌을 네 소비자가 공유 |
| B78-6 | 정보나루가 요청 값을 `<request>` 에 이스케이프 없이 되실음(실측) | 모든 엔드포인트의 경계 `call_library_api` 에서 에코만 이스케이프 → 빗나가면 에코 구간 제외 재파싱 → 그래도 깨지면 `error_type:"source_parse"`. 형제 원천 결함(고전종합DB 가 `keyword` 대신 `query=` 를 보내 모든 질의에 같은 문서) 동시 수리 + 되실린 검색어 불일치는 `source_changed` |
| B79-8 잔여 | 판본 1 `aliases` 와 판본 2 손 별칭이 두 벌, 경고 생성기의 제안 어휘 ⊄ 허용 키 | `alias_projection` 으로 액션 aliases 를 판본 2 계약에 투영(손 별칭 표 2개 제거). sort 는 `descending` 정본 + `desc` 별칭(두 판본 공통). 관문(`iblbuild_v2`): 별칭 두 벌·모순·`vocab_outside_allowed` |
| F79-3 | Number 를 파이썬 `type is int` 로 인덱스 판정 | 인덱스·슬라이스·round 자릿수가 `integer_value`(67회차 take 와 같은 판정). INDEX 진단이 "정수 아님"/"범위 밖"을 가르고 `index_type` 을 싣는다. 교재에 산술 연산자 표 |
| B79-3 | 당근이 Remix 앱으로 이사 — 목록은 로더 JSON 에 있음(실측) | 로더 JSON 파서. 구조 미발견·응답 동네 불일치 = `source_changed`, 0건은 간격을 두고 최대 3회 재질의 후 `empty_notes`(아래 "당근 간헐 빈 목록"). region 없는 호출은 IP 추정 동네로 조용히 스코프되므로 거절. 관문 `scripts/iblbuild_source_honesty.py`(구조 미발견 0건 성공·원천 함수의 except 빈 반환) → 다나와·TOPIS 형제 수리. source enum 액션은 원천마다 실행 예시(shape_variants) 필수, 변이 0행 경보는 주간 정직성 스윕 |
| B79-4 | 원천에 지역 인자가 없는데 한 쪽만 훑음 | 40행×최대 5쪽, `scanned`·`unlocated`·`total_estimate`, 상한이면 `scan_limit` source 절단 |
| B79-5 잔여 | 블로그 지역어 = 질의 첫 낱말 | 행 주소의 시·군·구(없으면 검색 좌표 역지오코딩) |
| B79-7 잔여 | show_map 이 `lat/lng` 만 좌표로 읽음 | 좌표 별칭 먼저, 지오코딩은 좌표 없을 때만. 패키지 경계 넘는 좌표 계약은 주간 정직성 스윕 불변식 F |
| B79-2 잔여 | 코드표 거절이 dict 덤프 | `_resolve_code` 한 함수: 이름 목록·`allowed`·`hint`(시·군은 시도로 검색 후 거르라) |
| F79-1 | 원천 간 비교 키 부재 | 공연·전시 행에 `title_key`·`place_key`(+공연 `place`) — 순회 공연이 접히지 않게 장소 키 동반 |
| F79-2 | 0건이 길을 말하지 않음 | 한글 질의·0건에 선언과 같은 문장의 `hint`(시험이 대조) |
| 침묵 클램프 | 관문 어휘가 요청량(limit 류)뿐 | `check_silent_clamp.py` 에 기간·반경 어휘와 모듈 상수 상한 → 형제 8곳. 날씨는 원천 상한 16일까지 받고 넘으면 `clamped`·`requested`·`applied` |
| 잠재(79) | 자동차 길찾기 압축이 `routes[0]` 만 | `alternatives` 요약·`warning`, 지도 선은 첫 경로만(전엔 모든 경로 꼭짓점을 한 선으로 이음) |

## 교재

- 계약이 바뀐 액션의 용례 재검토 원장(`data/ibl_example_review.json`)은 각 묶음이 라이브 코퍼스를 읽기 전용으로 대조해 갱신했다.
- `[table:sort]{desc:…}` 47행은 이제 두 판본에서 유효해(별칭) 고치지 않았다.
- 틀린 것을 가르치는 용례는 개별 재검토 후 판본 2 문장으로 교정했다(아래 "집행" 절의 영수증). 판본 1 문장이 판본 2 에서 봉투 `.items` 등 구조 차이로만 실패하는 행(약 42)은 판본 1 에서 유효하므로 이번 범위 밖이다.

## 당근 간헐 빈 목록 (배포 후 실측)

배포 직후 당근이 첫 호출에서 282건을 준 뒤 연속 0건을 주었다. 원인을 가르려고 같은 로더 요청을 대조했다.
- 같은 요청·같은 UA 연속 10회 중 1회만 282건, 나머지 0건(광고 목록도 0, 전부 CloudFront Miss).
- UA 판본(Chrome/120~140), 검색 페이지 선방문 쿠키 세션, TLS 위장(curl_cffi) 어느 것도 규칙적으로 가르지 못했다(위장 세션에서 연속 적중이 한 번 있었지만 재현되지 않음).
- 결론: 원인은 원천 쪽이고 몸이 고칠 수 없다. 처음 가설("서버가 느릴 때")은 근거가 없어 문구를 "같은 요청에 간헐적으로 빈 목록"으로 바로잡았다. 몸의 몫은 정직이다 — 0건이면 간격을 두고 최대 3회 더 묻고, 그래도 0건이면 `empty_notes` 로 "매물 없음으로 단정할 수 없다"를 싣는다.

## 검증

- 통합 워크트리 전체 백엔드 시험: 7,697 통과·41 실패. 41건은 수리 전 기준 워크트리에서도 똑같이 실패(워크트리에 DB·playwright·mcp_server 부재). 라이브 트리에서 그 10개 파일을 다시 돌려 232건 전부 통과.
- 신규 회귀: `test_imagination_round78_79_{forage,memory,books,place,plain_failure}.py`.
- `build_ibl_nodes.py --check` 전 관문 통과(새 관문: 열린 인자 계약·원천 정직·별칭 투영, 확장: 침묵 클램프·구현-읽기).
- 배포: fast-forward 한 번. 재기동 제어자가 쓰기 도중을 한 번 감지해 `check_failed` 후 재요청으로 새 세대 ACTIVE(백엔드 다운 없음).
- 라이브 재현(새 코드): recent_chats `days/query` → UNKNOWN_ARGUMENT+안내 · 오타 폴더 `locus_exists:false, own_count:0` · `book:<…>` locus map_count 0→1 · 정보나루 `R&D 전략` 22건·`<하네스>` 8건 · health 평탄형 check 통과 · 공연 `청주` 거절 문구(이름 목록+hint) · 번개장터 `청주` `scanned 200·unlocated 129·scan_limit` · 판본 2 `sort{desc}` valid · 공모전 hint · 날씨 `days:10` 10일·`days:20` 16일+clamped · 대화 미리보기 `preview_truncated`·`content_chars` · 공연 `title_key`·`place_key` · show_map gpsX/gpsY 좌표 그대로.

## 교재 교정 영수증

- [개별 검토](experiments/imagination_round78_79_residual_2026_09_29/corpus_review.json) 14행(2799·2800 은퇴 인자, 3701·3906·4094 당근 region, 3825·3878 title_key+place_key dedup, 4755·4756 Kaggle≠공모전, 294·1257·1349·1373·1566 delegate workflow 의 `do` 는 문장). 판본 2 컴파일러 정적 판정 invalid 0 확인 후 적용.
- [적용 영수증](experiments/imagination_round78_79_residual_2026_09_29/corpus_application.json): DB 14행, 훈련 JSON 사본 11행. 옛 문장·통계는 provenance 에 보존하고 새 본문에 과거 실적을 승계하지 않았다. 벡터 14·FTS 무결성 확인. 백업 `data/_backups/2026-09-29_imagination78_79_residual_202020/`.

## 판정 대기 (파괴적 변경 — 78회차 판정 요청 1)

- 지운 노트북 몸 2개의 기억과 문서 처분, 같은 책 두 몸(`book:하네스`·`book:하네스: …`)의 병합, 괄호 몸 개명, 읽기가 만든 빈 기억 DB 3개. 이번 수리는 이들을 **지우거나 합치지 않고** 회상에서 정직하게 표시만 한다(`locus_exists:false`·`root_missing:true`·freshness missing). 접기는 `[self:forage]{op:"reconcile", locus:"notebook:<이름>"}` 로 지명할 때만 일어난다.

## 한계

- 당근 0건이 진짜 없음인지 원천 지연인지는 원천에서 가를 수 없어 `empty_notes` 로만 말한다.
- 구조 미발견 관문은 하한이다(함수 경계 밖의 빈 결과 조립, `.get("name","")` 류는 대상 밖). 클램프 관문은 `if days > 7: days = 7` 형태를 못 본다.
- 쓰기 어휘 전반의 쓰기 원장 기록 누락은 부류 관문을 세우지 않았다(오탐 없는 판정 재료 부족) — ledger 한 곳만 닫았다.
- delegate 를 닫힌 계약으로 만든 것은 80회차의 "발신 어휘 먼저 닫기"를 따른 판단이다.
