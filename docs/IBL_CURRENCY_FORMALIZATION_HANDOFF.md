# IBL 통화 형식화 — 핸드오프 (2026-06-26)

다음 세션이 콜드로 이어갈 수 있게. 한 줄 요약: **`returns:` 키스톤(통화 역할 선언+강제) 완성·작동. 전수 점검이 진짜 갭 7개를 노출 — 그게 P1 백로그.**

---

## ✅ P1 완료 (2026-06-26 후속 세션)

§3 백로그 9개 전부 처리 + manage_events/company까지 → **RED 0 / GREEN 49 / YELLOW 2 / 구조 건강 ✅**(백엔드 재시작 반영 완료). 처리 내역:

- **records 비파괴 부착**(radio/zigbang 선례 그대로): `self:business`·`self:business_document`·`self:work_guideline`·`self:business_item`(business/handler.py `_to_records`/`_doc_records` 헬퍼) · `self:lecture`(lecture_workspace `_lecture_list`) · `sense:local_query`(local-info handler 디스패치 중앙 부착) · `sense:phone`(android `notifications` op) · `sense:researcher`(study `_nanet_author_find`·`_nanet_coauthor` → guardian 패턴 `{message, records}` dict 반환) · `self:manage_events`(backend/system_ai_tools.py `_execute_manage_events` list — **백엔드 코어라 재시작 후 라이브**).
- **`sense:video` 오분류 정정**: 4 op(info/transcript/languages/summarize) 전부 단일 영상 텍스트/메타 읽기 → `returns: records`→`scalar`(면제). records 생산자는 별개 `search_youtube`(그대로 유지). src 편집→build→--check 통과(142 유지).
- **`sense:company` 가장자리 폐쇄(P2 #2 선취)**: `currency` 선언인데 probe가 닿던 op(profile/financials)은 scalar라 YELLOW였음 → records 생산 op `disclosures`(DART 공시 20건, title=report_name)에 records 비파괴 부착(investment/tool_dart.py) + probe를 disclosures로 교체 → GREEN.
- **probe 정직화 2건**(점검 스크립트만, backend 무관): `self:manage_events` probe `op:list`→`action:list`(핸들러는 `action` 키 사용 — 빈 action으로 list에 못 닿던 false-YELLOW 제거) · `sense:company` probe op financials→disclosures.
- **라이브 검증**: `python scripts/ibl_health_check.py` **GREEN 49/YELLOW 2/RED 0**, `[self:business]{op:list}` records[7]·`[self:manage_events]{action:list}` records[22]·`[sense:company]{op:disclosures}` records[20] 종단 확인.
- **남은 YELLOW 2 = 통화 부착 불가능한 정직 advisory**: `self:business_item`(records 부착됨·probe 기본 business_id에 아이템 없음=데이터 의존) · `others:channel_read`(gmail agent identity 필요=환경). probe를 라이브 데이터/자격증명에 묶지 않는 한 GREEN 불가 — 그게 정직.

**잔여 행동**: **P2**(아래 §4) — engines 노드 분리·나머지 통화 가장자리(단일 시세 scalar·cctv lat/lng geo)·`self:list`/`self:file_find` table 정정.

---

## 0. 맥락 (왜 이 일을 했나)

IBL의 척추는 **통화**(records/table가 `>>`로 흐름)인데, 그동안 *형식화·강제가 없었다*. `world_pulse_health._evaluate_result`는 `error` 키만 봐서 통화 누수·미생산을 못 잡았다. 그래서 "올바른 어휘 = 자기 역할(생성/변환/행동)의 통화 계약을 지킴"을 **선언(`returns:`)으로 박고, `--check`(정적)와 `ibl_health_check.py`(런타임)가 강제**하게 만들었다.

배경 문서: `docs/IBL_MAINTENANCE_MANUAL.md`(점검 절차), `data/guides/new_action_checklist.md` 0.5단계(생성 게이트), `docs/IBL_GUIDE.md`(IBL 개관).

---

## 1. 완료된 것 (DONE)

1. **`returns:` 필드를 142개 액션 전부에 기입.** enum: `records | table | currency | transform | scalar | effect`.
   - `records`/`table`=단일 통화 생산자 · `currency`=op/입력 따라 records-or-table(다중, kosis/company/health) · `transform`=closure(변환자 9) · `scalar`=읽기 단일값(면제) · `effect`=행동/렌더(면제).
   - 분포: records 47 · table 2 · currency 3 · transform 9 · scalar 23 · effect 58.
2. **`--check` 강제** — `scripts/build_ibl_nodes.py` `_check_action`에 returns 검증 추가: 필수·enum·`group:transform ⇔ returns:transform`. `_RETURNS_ENUM` 도 거기. 커밋/self-check 게이트.
3. **`ibl_health_check.py` 를 선언-기준 단언으로 전환** — `RETURNS` 맵 적재 → `classify_currency(d, declared)`. 생성(records/table/currency)=통화 유효성 단언, 종착(scalar/effect)=SKIP(면제 → heuristic 거짓 RED 제거), transform=§1C 파이프로. 생산자 52개 **52/52 전수 probe**(미검증 0, 커버리지 명시).
4. **문서 동기화** — 생성 체크리스트 0.5단계(`returns:` 필수+템플릿), 유지보수 매뉴얼(키스톤 ✅+이력).
5. **분류 판단 2건**:
   - 다중-op 3개(kosis/company/health) → `currency`(per-op는 param-분기·query_type 하위파라미터라 안 맞아 폐기, currency가 정직·단순).
   - 4개 → `scalar` 재분류(도메인 통화 아닌 *내성/텍스트*): `self:grep`(텍스트 매치) `self:agents`·`others:agents`(에이전트 내성) `self:discover`(액션 검색).

**적용 스크립트(재현용)**: `scratchpad/classify_returns.py`(probe 기반 제안), `scratchpad/apply_returns.py`(src 기입, 미분류 기본=effect 안전디폴트). ※scratchpad는 세션 임시 — 로직은 이 문서가 정본.

---

## 2. 현재 건강 상태 (`python scripts/ibl_health_check.py`)

```
§1A 정적         ✅
§1B 통화         GREEN 40 / YELLOW 5 / RED 7   (생산자 52개 52/52 probe)
§1C 골든파이프   5/5 PASS
▶ 구조 건강: 주의 ⚠️  ← RED 7개가 백로그(아래 P1)
```
RED는 *형식화가 성공해서* 드러난 진짜 미순응이다(시스템이 정직하게 TODO를 보여주는 것). 정적·문법·소비자측은 모두 정상.

---

## 3. P1 백로그 — 노출된 통화 갭 7개(+YELLOW 2)

**전부 같은 부류**: `returns: records`로 선언했으나 핸들러가 *명명된 리스트만* 내고 `records`를 안 부착. **고치는 법 = radio/collect/kosis 선례 그대로 — 기존 리스트를 `records[{title,meta,summary,url}]`로 비파괴 부착**(원본 리스트 키는 유지, 앱은 원본·파이프는 records).

| 액션 | 패키지 | 현재 리스트 키 | title 후보 | 비고 |
|---|---|---|---|---|
| `self:business` | business | `businesses` | 사업명 | op:list |
| `self:business_document` | business | `documents` | 문서 제목/레벨 | |
| `self:work_guideline` | business | `guidelines` | 지침 제목/레벨 | |
| `self:business_item` | business | `items` | 아이템명 | (YELLOW — list op 빈결과) |
| `self:lecture` | lecture_workspace | `lectures` | 강의명 | |
| `sense:local_query` | local-info | `stores` | 가게명 | |
| `sense:phone` | android | `notifications` | 앱/발신자 | ★`phone_op` 싱글턴 가능 → reload 안 먹으면 `touch backend/api.py` |
| `sense:researcher` | study | (문자열만) | 연구자명 | guardian처럼 `{message, records}` 로 — 소속·생년·lodID를 meta에 |
| `self:manage_events` | (api_system_ai 의존) | (op:list 확인 필요) | 이벤트 제목 | YELLOW — op:list가 events 리스트 내는지 확인 후 records |

**절차**: 각 핸들러 편집 → `POST /packages/reload`(business/study/local-info 등) 또는 싱글턴이면 `touch backend/api.py` → `python scripts/ibl_health_check.py` 재실행 → 해당 줄 GREEN 확인. 9개 다 닫으면 **52/52 GREEN → 구조 건강 ✅**.

> business 4개는 한 패키지(`data/packages/installed/tools/business/handler.py`)라 함께 처리하면 효율적. researcher는 study `_search_guardian` 옆 패턴 참고.

---

## 4. P2 백로그 — 설계 개선 (평가에서 도출, 통화 형식화와 별개)

1. **`engines` 노드 과적재 분리**: 변환자(filter/sort… *언어 코어*) vs 생성기(slide/document/tts/image… *응용*)가 한 노드(26개)에 섞임. 고도가 다름 → 가르거나 명확히 표시.
2. ~~**통화 가장자리 정리**: records/table 둘로 안 떨어지는 것 — 단일 시세(scalar)·지도 마커(cctv lat/lng)·문서IR(crawl blocks)~~ ✅ **완료(2026-06-27)**. **결정 = 2층 통화 모델**(아래). 가장자리 3종이 *비대칭*임을 근거로 각각 처리:
   - **① 단일 시세 → scalar 유지**: stock·crypto·navigate_route·here·reverse_geocode 등 단일값. 메모리 `architecture_records_currency` 명시("의도적 스킵, 명사곱/필드쌓임 원칙상 통화 부적합"). 변경 없음.
   - **② 지도 마커 → 흡수(geo 통화 안 만듦)**: 장소 목록(restaurant·realty·cctv·commercial·travel)은 **이미 records + map_data 동시 발행**(전부 GREEN). 판단 축 = *소비자*: map_data는 지도 **렌더링**(앱 계기)만 소비할 뿐 **파이프 변환자가 없다** → 명사곱 0 → 통화 아님. records가 조합 통화, **map_data는 렌더링 봉투**(list/file_find의 records+table과 동형). 단일 지오(route/here)=scalar+봉투. **새 `geo` 타입 안 만듦.**
   - **③ 문서IR blocks → 통화로 인정(`document` 신설)**: 대칭 반대 — blocks는 다(多)생산자(crawl·read[docx/pdf]·pdf) → **풍부한 1소비자 `engines:document`(5포맷)** = 진짜 파이프 변환자 → 명사곱 성립. `returns` enum에 **`document`** 추가(build_ibl_nodes `_RETURNS_ENUM`), `ibl_health_check.classify_currency`가 `{blocks}`(type 키 블록 리스트) 인정, **`sense:crawl` effect→document** 재분류. 실측 근거=crawl→blocks[heading,paragraph] 산출 확인. crawl은 네트워크 의존이라 미검증(생산자 53·probe 52·미검증 1=crawl, 투명 집계). **GREEN 50/YELLOW 2/RED 0·142 액션 불변.**
   - **★잔여 후속**: `self:read`는 다중-모달 생산자(txt→scalar·xlsx→**table**[보편통화!]·docx/pdf→blocks)인데 `scalar`로 선언돼 **보편 통화(table)를 숨김**(grep·list 부류와 동급). `currency`로 승격이 정직하나, 구조화 파일 probe 전략(고정 xlsx/docx 부재) 필요 → 별도. *(company:disclosures records 부착 = P1에서 선취)*
3. ~~**선언 mismatch 미세정리**: `self:list`·`self:file_find`는 `records` 선언인데 `table` 산출~~ ✅ **완료(2026-06-26)**. 정정 방향 선택 = **records 부착(선언을 참으로)** > table 강등. 근거: 파일=명사(엔티티)→records가 보편통화(document·messages 어디든 흐름), table은 dataops용으로 비파괴 유지. system_essentials/handler.py `list_directory`·`glob_files`에 records[{title:파일명+/, meta:크기·수정일, url:절대경로}] 부착(table 동시 유지). health: `records[24]`·`records[5]`로 표시(전엔 "table N행 선언 records"). 종단 `file_find>>take 3`→records 3·table 5 동시 흐름. **★형제 이슈 `self:grep` ✅완료(2026-06-27)**: 역방향 불일치(`scalar` 선언인데 3 op모드 전부 `{text,table}` 산출)를 `returns: table`로 승격(src). +probe RED이 노출한 **잠재 param 버그 동시 수정**: grep 핸들러가 `root_path` 키만 읽어 src가 광고하는 `path`를 조용히 무시(`project_ibl_param_name_mismatch` 부류) → glob_files와 동일 규칙(`path > root_path > project_path` + 절대경로 처리)으로 통일. probe도 `path:"."`로 교정. health `table 4행` GREEN, GREEN 50/YELLOW 2/RED 0 유지.
4. **per-op returns**(보류): `currency`가 다중-op를 덮으므로 당장 불필요. 정밀 강제가 필요하면 op별 맵 도입(단 param-분기 액션엔 부적합 — §1 판단 참고).

---

## 5. 핵심 파일 · 명령

**파일**
- src(returns 필드): `data/ibl_nodes_src/{sense,self,limbs,others,engines}.yaml` → 빌드 → `data/ibl_nodes.yaml`
- 정적 검증: `scripts/build_ibl_nodes.py` (`_check_action`의 returns 블록, `_RETURNS_ENUM`)
- 런타임 점검: `scripts/ibl_health_check.py` (`RETURNS` 적재, `classify_currency`, `PRODUCERS` probe 목록)
- 생성 게이트: `data/guides/new_action_checklist.md` 0.5단계
- 절차/이력: `docs/IBL_MAINTENANCE_MANUAL.md`

**명령**
```bash
# 어휘 수정 후
python scripts/build_ibl_nodes.py && python scripts/build_ibl_nodes.py --check
# 핸들러 수정 후 반영
curl -s -X POST http://localhost:8765/packages/reload    # 싱글턴(tool_radio/phone_op 등)은 touch backend/api.py
# 건강 점검 (어휘 변경·새 액션 때마다)
python scripts/ibl_health_check.py
```

---

## 6. 함정 (Gotchas)

- **백엔드 코어는 안 건드림**: 이번 작업은 build 스크립트(빌드타임)+standalone 점검 스크립트+src yaml만. 러닝 백엔드(`ibl_engine.py`/`world_pulse_health.py`) 자기편집=자기-reload 자해 → 별도·동의 후. (P1 핸들러 수정은 패키지 reload라 안전.)
- **op/param-분기 액션의 returns는 action-level 근사**: 다중 통화면 `currency`. health=query_type 하위파라미터라 op-맵 부적합.
- **싱글턴 핸들러**(tool_radio·phone_op 등): `/packages/reload` 무시 → `touch backend/api.py`.
- **`_evaluate_result`(self-check)는 여전히 error 키만 봄** — 통화 검증은 `ibl_health_check.py`가 담당. 둘을 합치려면(자가점검에 통화 단언 이식) world_pulse_health 편집 필요(백엔드 코어, 별도 세션). 매뉴얼 §5 배치 로드맵 참고.
- **JSON 문자열 반환**: 핸들러가 `format_json`(문자열)으로 줘도 엔진이 파이프 때 파싱하므로 records가 흐름. 단 probe/분류 시 `json.loads`로 풀 것.

---

## 7. 한 줄 다음 행동

> `python scripts/ibl_health_check.py` 돌려 RED 7개 확인 → §3 표대로 핸들러에 records 부착(business 4개 먼저) → 재점검 GREEN → 52/52 달성. 그다음 P2.
