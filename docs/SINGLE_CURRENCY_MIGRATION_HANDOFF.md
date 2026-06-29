# 단일 통화(items) 이행 — 핸드오프

한 줄: **통화를 하나로 접는다 — `{"items":[ {…열린 필드…} ]}`. 구조적으로 강제되는 건 바깥 형태 하나뿐. 옛 형태(records/table/map_data/document/scalar)는 전부 이 하나의 view 로 흡수되며 삭제된다.**

---

## ▶▶ 다음 세션 RESUME HERE (2026-06-27 7차 종료 시점) ◀◀

### ★★★★단일 통화(items) 이행 **완료** — 모든 컬렉션 통화가 items 하나로. (남은 건 의도된 면제만)
**통화 선언 분포: `items 53` (유일한 컬렉션 통화) · scalar 23 · effect 57 · transform 9.** records EMIT=0·enum={items,transform,scalar,effect}·골든 5/5·§1B GREEN 50/Y2/R0·build 142.

### ★7차에서 한 것 (straggler·dead-code 청소) — 전부 라이브·검증
- **context7 devdocs**(returns:items인데 op:search가 `blocks` 방출=유일한 items-선언-blocks-방출 불일치) → `blocks`→`items`(문서 IR). 소비자 engines:document가 type/text 감지.
- **derive_items**(`backend/common/currency.py`) **records 분기 삭제**(records 생산자 0이라 dead). table(stock)·blocks(read/report) 분기는 returns:scalar/effect straggler 표시용 유지(docstring 명시).
- **read(returns:scalar)·report(returns:effect)·stock(returns:scalar)는 의도된 면제**: blocks/table 부가방출이지만 통화 선언이 scalar/effect라 단일통화 대상 아님(종착 액션의 부가 IR). derive_items가 렌더러서 items 파생.

### ▶▶ 남은 것 (전부 *의도된 설계·기능 무손상*, 추가 작업 불요) ◀◀
1. **map_data 봉투**(zigbang/commercial/cctv/navigate) — **의도적 면제**(§3): items가 이미 lat/lng 보유(markers 중복), center/zoom은 봉투 직독(items서 유도 불가). 지도 위젯이 봉투 읽음. *통화 아님, 그대로 유지가 정답*.
2. **scalar/effect 부가 IR**(stock table·read/report blocks) — 종착 액션의 부가 출력. derive_items가 흡수. 건드릴 필요 없음.
3. **classify_currency rec/blk 방어 읽기** — 무해(declared==items만 검사, straggler 방어). 남겨둠.
**→ 단일 통화 이행은 실질적으로 끝. 추가 작업은 새 생산자 작성 시 `items` 방출 규약만 지키면 됨(§4 생산자 계약).**

### ~~정리(2026-06-28)~~ — 통화 종착 명문화 + stale/dead-code 청소 (보존)
통화 구조가 narrow-waist 종착(도메인 이름 0)에 도달했다는 판정 후, 그 종착을 *읽을 수 있게* 만드는 청소:
- **stale docstring 수정**: `data-ops/handler.py` 모듈 docstring("두 통화: records→envelope {records}" → 단일 items)·`_get_records` docstring("records 폴백 ~18개" → items-only, 코드는 이미 그러함). 코드 동작 무변경.
- **dead-code 삭제(8)**: culture 5 헬퍼 + business `_to_records`+`_doc_records` + study `_search_books` 내부 죽은 records 루프. 전부 호출자 0.
- **생산자 계약 1쪽 신설**: `docs/IBL_CURRENCY_CONTRACT.md` — 낯선 사용자가 읽는 단일 규약(`items` 방출·평평한 필드·map_data=통화 아님·fail-fast·순수 추가형). map_data를 "통화 아닌 렌더링 사이드채널"로 명시(미완성 마이그레이션 오해 차단).
- **검증**: build --check 142 GREEN·바이트 일치 / py_compile 4파일 OK / `/packages/reload` 후 라이브 회귀(business_document·search_books·classic·book>>take) 전부 items 정상.
- **✅ 추가 청소(2026-06-29)**: data-ops `_emit_records` 호출 3곳(union/dedup/join, line 472/502/561)이 base envelope 로 `{"records": []}` 를 넘겨 **출력에 vestigial 빈 `records:[]` 키가 새던 것**을 `{}` 로 교체 — 마지막 records 출력 흔적 제거. 검증=AST OK·`/packages/reload`·라이브 3변환(filter 한식152/dedup 카테고리72/merge 두입력1206) 전부 출력 키에 `records` 없음 확인. (잔여 `records` 참조 1곳=line 617 은 *입력* 수용=정당 backward-compat.)
- **✅ records producer = 0 종합 확인(2026-06-29, 백엔드 정지 창)**: channel_engine `_community_feed`/`_community_board` 는 *이미* items 방출(stale ⏳ 노트였음 — `records` 단어조차 0). 전 코드베이스 records 출력 생산자 스캔 = **backend 0 · tools 0**(data-ops:617 의 `params["records"]` 는 *입력 수용*=정당 backward-compat, 출력 아님). **단일통화(items) 마이그레이션 기능적 완료.** 남은 records-aware 코드 2곳은 의도적·방어적: ⒜`classify_currency`(scripts/ibl_health_check.py)=records/table/blocks 관용을 *함께* 처리(table/blocks 와 묶임 → 그것들 은퇴까지 유지) ⒝data-ops:617 입력 수용. **둘 다 straggler 아님 — 제거 대상 없음.**
- **map_data enum 추가는 *하지 않음***(map_data는 returns 값이 아니라 생산자 봉투 필드 — 환각 교정).

### ~~6차에서 한 것~~ — table·document·currency 흡수, enum 축소 (보존). 전부 라이브·검증
- **table → items** (4 생산자): **world_bank**(`study/handler.py` `{table}`→`items=[{연도,지표}]`)·**grep_files**(`system_essentials` 3모드 `[{파일,줄번호,내용}]`)·**company**(`investment/handler.py` `_attach_company_table` `[{지표,값}]`)·**kosis**(`tool_kosis_api.py` `_to_table_currency`→행dict). **★소비자가 items→table 재구성**: `data-ops _get_table`·`visualization _extract_table_from_prev`·`system_essentials` spreadsheet(1029, generic 키=열) 셋 다 items(행dict)→table 브릿지 추가. 라이브 **golden `world_bank>>chart` PASS**·`world_bank>>spreadsheet` 파일생성·grep items 6·company items 11.
- **document → items** (crawl): `web/handler.py` `_text_to_blocks`→`items`(문서 IR [{type,text,level}]). **★소비자 `engines:document`(media_producer 1196)에 type/text 감지 추가**=문서IR items면 blocks로, 아니면 cards로. 라이브 crawl items=2(heading/paragraph)·`crawl>>document` 파일생성.
- **currency 선언 정리**: health·company·kosis `returns:currency`→items.
- **★★enum 축소**: `_RETURNS_ENUM = {items, transform, scalar, effect}` (records/table/currency/document **전부 제거**). `classify_currency`(ibl_health_check)도 declared!=items면 SKIP로 정리(rec/tbl/blk 방어 읽기는 straggler용 유지). **★이제 통화 선언 = items 하나뿐.**
- **검증**: §1A 정적 ✅ · §1B GREEN 50/YELLOW 2(양성)/RED 0 · 골든 5/5 · build 142 · 구조 건강 ✅.

### ▶▶ 남은 것 (전부 *저우선·기능 무손상* — 이행은 끝, 청소만) ◀◀
**선언 차원 단일통화 완료. 아래는 straggler/dead-code 청소(동작은 이미 단일통화):**
1. **blocks 부가방출 생산자** (declare items, emit `blocks`): context7(123)·report-viewer(117/149)·read_pdf/read_docx(`system_essentials` 679/898). 동작 OK(`engines:document`가 blocks 먼저 읽음 + derive_items가 blocks→items). 일관성 위해 blocks→items 가능(document 소비자가 type/text 감지하니 안전) — ★단 report-viewer는 app이라 렌더러 확인.
2. **stock table 부가방출**(returns:scalar): `investment/handler.py` `_attach_table`(날짜/종가) — invest 앱이 table 직독할 수 있어 보류. chart는 _get_table로 동작.
3. **죽은 분기 청소**(무해): `derive_items`(currency.py) records 분기(생산자 0)·table 분기(stock만)·blocks 분기(위 1)는 일부 live → straggler 정리 후 삭제. `classify_currency` rec/blk 읽기도 그때.
4. **map_data 봉투**(zigbang/commercial/cctv) — §3대로면 items lat/lng로 흡수 가능하나 center/zoom 기준점 유도 필요. 지도 위젯 계약 정리(별도·저우선).

### ~~5차에서 한 것~~ — **records 통화 완전 은퇴** (보존). 전부 라이브·검증
- **브릿지 핸들러 5개 마이그레이션** (returns는 이미 items였고 핸들러도 items 방출로): **photo-manager**(156/175-176/230/375 — native-drop 패턴=`_photo_record` 카드 shape를 items로 *덮어씀*, raw 버려도 무회귀=app 카드가 카드 shape 읽음) · **system_essentials** list_directory/glob_files(`{text,table,items}`) + spreadsheet 소비자 1028을 `items or records`로 보강 · **recent_chats**(`backend/drivers/sqlite_driver.py` `_memory_recent` records→items) · **channel_read**(`backend/channel_engine.py` gmail/nostr `messages`→items). 백엔드 코어도 `/packages/reload`로 반영됨(라이브 확인).
- **잔여 sub-module records 6개** (이전 grep이 handler.py만 봐서 놓친 tool_*.py): contest·startup(`_attach_records`+source=all)·health-record(3)·kosis(177+368)·dart·**naver(★과적 legacy items 함정**=`"items":raw + "records":card` 동시 방출 → legacy 제거+카드를 items로)·ddgs. 전부 records→items.
- **★records EMIT = 0** (전 핸들러·tool·backend 감사 통과). 라이브 items 확인: photo 50·contest 10·kosis 10·recent_chats(items키)·dart·startup 등.
- **★★records 통화 컷오버 완료**: ①`data-ops _get_records` records 폴백 **삭제**(items-only) ②`_emit_records` records dual-emit **삭제**(items-only) ③모든 records 소비자(system_essentials 1028·media_producer 1198)를 items-우선으로 ④골든 체커 3 파이프(naver/legal/kosis) `kind:records→items` ⑤**`_RETURNS_ENUM`에서 `records` 제거**(returns:records 선언 0). 골든 `items=3/items=5`로 통과.
- **검증**: §1B GREEN 50/YELLOW 2(양성: channel_read identity·business_item 무인자)/RED 0 · 골든 5/5(items 검증) · build 142 · 구조 건강 ✅.

### ▶▶ 다음에 할 일 (남은 통화 shape = table·document·currency 소수만) ◀◀
**records는 끝. 남은 건 *shape가 다른* 통화 3종 — 단순 rename 아닌 변환 필요:**
**1. table → items** (returns:table 2개 + currency 중 table 방출하는 것):
   - **world_bank**(`study/handler.py` ~1068 `{table:{columns,rows}}`) · **grep_files**(`system_essentials`, returns:table) · **company**(`investment/tool_dart.py`? 216/265 `obj["table"]`, returns:currency) · **kosis**(`tool_kosis_api.py` 272 `_to_table_currency`, 부가) — table을 items 행dict(`[{col:val}]`)로. ★소비자 `engines:chart`는 `data-ops _get_table` 별도경로 → chart도 items에서 수치칸 찾게 하거나 table 유지 판단. **골든 `world_bank>>chart` 깨지지 않게**.
**2. document → items** (returns:document 1개):
   - **crawl**(`web/handler.py` crawl_website, `{blocks}`) → blocks를 items(type+text+depth)로. 소비자 `engines:document`(5포맷) 확인.
**3. currency 선언 정리** — health/company/kosis가 `returns: currency`(generic). health=items 방출이니 returns:items로, company/kosis=table 부가 → 1번 후 정리.
**4. 죽은 records 분기 청소**(저우선·무해): `derive_items`(api_ibl) records 분기 + `classify_currency`(ibl_health_check 42/50) records 분기 — 이제 records 생산자 0이라 dead. table/blocks 분기는 1·2 전까지 유지.
**5. map_data 최종 검토**(저우선) — zigbang/commercial/cctv map_data 봉투.

### ~~4차에서 한 것~~ (records-관습 생산자 ~20개 → items + returns 전수 플립) — 전부 라이브·검증 (보존)
- **핸들러 records→items rename 20 액션** (records-관습 카드 shape는 그대로, 키만 records→items): study 4(paper/researcher/pew_research/search_guardian — 8 emit)·local-info 2(search_local/local_query)·context7(devdocs)·legal·memory·pc-manager(fs_query)·lecture_workspace(lecture)·android(phone)·web 3(search_ddg/search_news/search_naver)·blog·location-services(travel)·business_item(이미 items, returns만). **delete 계열**(native items 이미 존재 → 손실 records 줄 삭제): web-collector(collect)·shopping(search_shopping). 라이브 items 확인: legal 3·memory 5·shopping 10·lecture 2·phone 20·legal>>take 2·blog>>take 2(in-pipe).
- **returns 전수 플립 ✅** — `returns: records` **27개 전부 → items**(sense 17·self 9·others 1, bulk replace). **★이제 `returns: records` 선언 = 0** (남은 건 `returns: table` 2 + `returns: document` 1뿐).
- **검증**: §1B GREEN 50/YELLOW 2(둘 다 양성: channel_read=identity 없어 테스트불가·business_item=default op list 무인자라 빈 items)/RED 0 · 골든 5/5 · build 142 · 구조 건강 ✅.

### ▶▶ 다음에 할 일 (꼬리 — 점점 짧아짐) ◀◀
**1. 브릿지로 남은 records-emit 핸들러 ~5개 마이그레이션** (returns는 이미 items지만 핸들러가 아직 records 직접 emit → derive_items+폴백이 브릿지 중. 라이브 확인=photo는 records+items 공존, list items152):
   - **photo-manager**(`photo/handler.py` 156/175-176/230/375) — ★native-drop 패턴 주의: 175-176이 `res["records"]=[_photo_record(it) for ...]; res.pop("items")` (native items를 버리고 records로 포장). 이건 단순 rename 아님 — **native items 유지**(pop 제거)하되 app 카드가 records-관습(title/meta/image) 읽으면 `_photo_record` shape를 items로 내야. 230=native 있음→records 줄 삭제. 156/375=rename. 케어 필요.
   - **system_essentials**(`system_essentials/handler.py` 270/479 `{text, table, records}`) — list_directory/glob_files. records→items rename. ★단 grep_files=`returns: table`(아래 2번)이고, **라인 1028 `_po.get("records")` 는 spreadsheet *소비자* 읽기** → items도 읽게 추가(`_po.get("items") or _po.get("records")`).
   - **recent_chats**(router:driver, backend) · **channel_read**(`backend/channel_engine.py` `_channel_read` 563, channel_engine 코어) — 각 emit 찾아 records→items.
**2. table/document 3개 (shape 변환 필요 — records 단순 rename 아님)**:
   - **world_bank**(`study/handler.py` 1068 `{table:{columns,rows}}`) + **grep**(`system_essentials` grep_files, table) → table을 items 행dict로(`[{col:val}]`). 소비자=chart는 `_get_table` 별도경로라 chart도 items 읽게 하거나 table 유지 판단. **golden `world_bank>>chart` 깨지지 않게** 주의.
   - **crawl**(`web/handler.py` crawl_website, document=blocks) → document/blocks를 items(type+text)로. 소비자 확인.
   - 이 3개는 `returns: table`/`returns: document` 그대로 두고 핸들러+소비자 같이 옮긴 뒤 returns flip.
**3. records 폴백·dual-emit 최종 은퇴** — 1·2 끝나 records-emit 0 되면 `_get_records` records 폴백 줄 + `_emit_records` records dual-emit 줄 삭제.
**4. §8.4 enum 축소** — **records는 지금 당장 enum에서 제거 가능**(returns:records 선언 0 확인됨) — `build_ibl_nodes.py` `_RETURNS_ENUM`에서 records 빼기. table/document는 2 끝난 뒤. `classify_currency`(ibl_health_check) records/table/blocks 분기도 정리.
**5. map_data 최종 검토**(저우선) — zigbang/commercial/cctv map_data 봉투 정리.

### ~~3차에서 한 것~~ (cctv + 키스톤 items-우선 플립 + 잔여 정리) — 전부 라이브·검증 (보존)
- **cctv ✅** (`cctv/handler.py`·`windy_webcam.py`·`DirectionsInstrument.tsx`) — search/nearby `cctvs`+`records` → `items`(native: name/url/lat/lng/source/playable/distance_km). 빈결과·webcam op도 items. **★bespoke STATIC 렌더러**(`DirectionsInstrument.tsx` 길찾기+CCTV 지도)가 `r.cctvs` 직독 → `r.items`로 플립(이게 "map 얽힘"의 정체). app `markers: cctvs`/`from: cctvs`→items, returns records→items. tsc 0 err·라이브 search 10·nearby 5.
- **§8.3 키스톤 플립 ✅** — `data-ops/handler.py` `_get_records`를 **records-우선 → items-우선·records-폴백**으로 뒤집음. items 생산자(native 풍부 dict)가 in-pipe로 lat/lng·level 등 흘림(zigbang `>>take`에서 lat/lng/distance_m 보존 확인=items-우선의 구체 이득). **records 폴백 유지**=아직 items 안 내는 records-관습 생산자(~18개) in-pipe용(records는 손실 없는 dict 목록=in-pipe derive_items). 골든 5/5 PASS.
- **잔여 dual-emit·dead 헬퍼 정리 ✅** — zigbang `records`+`data` 제거(items+map_data만)·business_item op:list `records` 제거. dead 헬퍼 삭제: cctv `_cctvs_to_records`·real-estate `_realty_to_records`+`_commercial_to_records`·business `_nb_record`. (business `_to_records`+`_doc_records`는 **2026-06-28 삭제 완료** — 호출자 0 재확인 후.)

### ▶▶ 다음에 할 일 (남은 꼬리 — 거의 다 됨) ◀◀
**1. records-관습 생산자 ~18개 → items 키 rename (이게 남은 본체, 기계적·저위험)**
현재 in-pipe records-only로 남은 생산자들(렌더러 경계 derive_items + in-pipe records 폴백이 둘 다 records→items 투명 처리 → *소비자 관점은 이미 단일통화*, 생산자 키 라벨만 records). 이들은 `result["records"]={title,meta,summary,url,image}` 카드 통화를 냄 → **records가 이미 정확한 카드 shape라 순수 키 rename**(`records`→`items`) + `returns: records`→items + (app 있으면 `from:`은 Phase 3a서 이미 items). 목록(grep `'"records"'` 결과): blog(2)·android·contest·context7·health-record(3)·local-info(2)·location-services search_local(841)·lecture_workspace·pc-manager·legal·memory·shopping(250)·photo-manager(여러)·startup·study(2)·system_essentials(2)·web-collector(2)·web(2). 각각 5묶음과 동일 케어(핸들러+returns+app from: 확인, build·reload·라이브, §1B). **★이거 끝나면 records 생산자 0.**
**2. records 폴백·dual-emit 최종 은퇴** — 위 끝나면 `_get_records` records 폴백 줄 + `_emit_records` records dual-emit 줄 삭제(이제 읽히지 않음).
**3. §8.4 enum 축소** — `_RETURNS_ENUM`에서 records/table/document 제거(1 끝나야 가능=returns:records 0), `classify_currency` records/table/blocks 분기를 items 하나로.
**4. map_data 최종 검토** — zigbang/commercial/cctv가 쓰는 map_data 봉투는 §3 표대로면 items의 lat/lng로 흡수 가능하나 center/zoom 기준점은 유도 필요 → 지도 위젯 계약 정리(별도, 저우선).

### 지금까지 (전부 라이브·검증, §1B GREEN 50/YELLOW 2/RED 0·골든 5/5·build 142)
- **Phase 1 ✅** items() 생성자(`backend/common/currency.py`) + data-ops keystone.
- **Phase 2 ✅** `derive_items(result)`(`common/currency.py`)를 **렌더러 경계** `api_ibl.py` `/ibl/execute`(문자열 파싱 직후)에서 호출 → records/table/blocks를 items로 파생. **★위치가 핵심**: `_route_handler`(공용) 아니라 api_ibl(렌더러 전용) — 문자열 반환 생산자 커버 + 에이전트 토큰 중복 회피. map_data 제외(특수). 상세 §7.6.
- **Phase 3a ✅** records-관습 카드 12개 `from:→items`(photo·fs_query·travel·startup·contest+report thread). 상세 §7.7.
- **Phase 3b ✅** native 카드 생산자 **15개** `items=native(키 pop)+손실 records 은퇴`: work_guideline·report·launch·culture×4(performance/book/classic/exhibit)·restaurant·search_youtube·search_books·radio·radio_favorite·feed·board·business_document. 상세 §7.8.
- **Phase 3c ✅ (2026-06-27 2차)** 남은 통화 생산자 **5묶음 전부 native items화** (모두 라이브 검증):
  - **weather** (`location-services/handler.py`) — `forecast`+`table` 둘 다 폐기 → `items`=풍부 일별 dict(date/max_temp/min_temp/condition/precipitation_mm). app `kv_list from: forecast`→items, returns table→items. 라이브 7건.
  - **manage_events** (`backend/system_ai_tools.py` `_execute_manage_events`) — op:list `{events, records}`→`{items: events}`(native, calendar 뷰가 id/date 직독). app `calendar from: events`→items, returns records→items. ★코어 모듈인데 `/packages/reload`로 반영됨(확인).
  - **real-estate** (`real-estate/handler.py`) — 5 realty emit(realty_price+4 직접) + commercial 모두 `result["records"]=_X_to_records(data)` → `result["items"]=result.pop("data")`(native 한글필드 명칭/법정동/거래금액 + commercial lat/lng). 제자리 dong/name 필터는 data 작업변수로 유지 후 막판 pop. **map_data·summary 보존**. zigbang(이미 items+map_data) 무영향. app realty `from: data`×2 + commercial `from: data`·`markers: data`→items, returns records→items. 라이브 molit 90건·commercial 6385건·zigbang 6건.
  - **business** (`business/handler.py` `_biz_list`) — Phase 1 dual-emit(title-rename items + records + businesses) → `_ok(items(businesses))`(native name/id/level). app `card_list from: businesses`+`options_from: businesses`→items, returns records→items. 라이브 7건.
  - **messages+neighbor** (`business/handler.py`) — ★두 컬렉션 응답 처리법 확립: **주 컬렉션=items, 보조 컬렉션은 도메인명 유지**(business detail의 `business` 스칼라 선례). `_msg_inbox` conversations→items(records 폐기) / `_msg_thread` messages→items(주=스레드), `contacts` 보조 유지(정보탭 editable_list), 헤더 스칼라 보존 / `_nb_list` neighbors→items(records 폐기) / `_nb_detail` messages→items, neighbor·contacts 보조. app messages `from: conversations`/`from: messages`→items(`from: contacts` 그대로), returns messages·neighbor records→items. 라이브 inbox 8·thread 2+contacts 1·neighbor 7.

### ★Phase 3c에서 확립된 새 레시피 (두 컬렉션 응답)
한 응답이 컬렉션 둘을 가지면(thread=messages+contacts, neighbor detail=messages+contacts): **주 컬렉션만 `items`, 나머지는 도메인명 키로 공존**. 근거=§2 위배 아님(contacts는 items와 같은 *shape*, 새 형태 아님·동기화 상태 0). 렌더러가 `from: contacts`로 명시 참조. 단일통화=주 통화 하나 강제이지 응답 내 리스트 1개 강제 아님.

### ~~다음에 할 일 (cctv + 컷오버)~~ — ✅ 3차에서 완료(위 RESUME 참조)
cctv·키스톤 items-우선 플립·dead 헬퍼·zigbang/business_item records 정리 전부 끝. 남은 것은 위 RESUME의 "다음에 할 일"(records-관습 18개 rename + 폴백 은퇴 + enum 축소).

### ★확립된 레시피 (native-필드 생산자 = 대다수)
```
1. 생산자 핸들러: return {…, "<nativekey>": lst, "records": _X_to_records(lst)}
   →  return {…, "items": lst}            # nativekey pop, records 은퇴 (items=native 풍부 dict)
2. app 블록 src yaml: from: <nativekey>  →  from: items     # ★반드시 같이! 안 하면 카드 빈값
3. returns 선언: returns: records  →  returns: items        # effect/scalar면 그대로 둠
4. python3 scripts/build_ibl_nodes.py && --check 바이트 일치
5. 핸들러 편집=POST /ibl... 아니라 curl /packages/reload (코어 모듈도 반영됨/싱글턴만 예외)
6. 라이브: curl /ibl/execute → items 있고 옛키 제거·records 은퇴, 필드가 카드 참조와 일치 확인
```
**판별**: 카드 필드가 records-관습(title/meta/summary/url/image)이면 `from:→items`만(derive_items가 줌, 생산자 무변경). native 필드면 위 레시피(생산자도 items화). 판별=`grep 'image:\|title:\|sub:\|lines:' 해당 app블록`.

### ★함정 (실측)
- **app from: 동반 flip 필수**: 핸들러가 옛 키를 pop하면 app이 옛 키 읽어 카드 빈값. 핸들러+app+returns 3곳 세트.
- **reload 메커니즘**: 패키지 핸들러·channel_engine 코어 → `/packages/reload`로 반영(실측). **tool_radio.py는 싱글턴 → `touch backend/api.py` 필요**(reload 안 먹음, 메모리 `project_radio_korean_stream_urls`).
- **items 과적 키**(§7.5): items를 *비통화 raw*로 쓰던 생산자 있음 → derive_items는 records→items 단방향만(역방향 금지). photo는 `summary_table`로 개명 완료. 새 생산자 점검: `grep -rn '"items":' .../handler.py`.
- **체커가 안전망**: 핸들러만 바꾸고 app/returns 깜빡하면 `python3 scripts/ibl_health_check.py` §1B가 RED로 잡음. 매 producer 후 돌릴 것.
- **scalar/effect from: 키는 면제**(이행 대상 아님): host top/disks·stock/crypto data.prices·navigate map_data/key_guides·cctv cctvs·nostr relays·music queue 등 — kv_list/sparkline이 scalar 하위 직독. 그대로 둠.
- **dead code**: native 이행이 `_X_to_records`/`_to_records`/`_doc_records` 헬퍼를 죽임 → 컷오버서 일괄 삭제(§7.8 목록).

### 검증 한 방
```
python3 scripts/ibl_health_check.py 2>/dev/null | grep -E '정적:|§1B 통화:|골든파이프:|구조 건강|RED'
# 기대: 정적 ✅ · §1B RED 0 · 골든 5/5 · 구조 건강 ✅
```

---

## 0. 왜 (병의 이름)

통화가 *늘어난 게* 문제가 아니라, **예외마다 새 형태(shape)를 도입한 것**이 문제였다. 형태가 N개면 변환자 N², 체커 N개, "이건 어느 통화냐" 논쟁 N개. 형태를 하나로 접으면 그 곱셈이 통째로 사라진다. (배경 대화·근거: `architecture_single_currency_items` 메모, 검색 선례=IP 헤더+페이로드·PowerShell 객체·LSP 봉투+params 가 만장일치로 "최소 뼈대 + 열린 내용"으로 수렴.)

## 1. 강제 규칙 — 딱 하나

```
컬렉션은 {"items": [ … ]} 다.
```
비어도/1개여도 목록. 이게 **유일하게 구조적으로 강제되는 계약**. `title`조차 보장 아님 — 가장 흔한 *관습*일 뿐. 항목 내부는 열림(도메인 필드 자유).

## 2. "추가할까?"의 유일한 시험 (★거버넌스 — 재발 방지의 핵심)

> **동기화 지점을 없애는 구조만 더한다. 유지·동기화할 상태를 늘리는 구조는 절대 안 더한다.**

| 후보 | 판정 | 이유 |
|---|---|---|
| `items()` 생성자로 returns 파생 | 더한다 | 선언↔출력 동기화 지점 제거, 유지 상태 0 |
| view 봉투(center/zoom/route, map_data) | 안 더한다 | 새 형태 = 곱셈 부활 |
| 필수 필드 레지스트리 | 안 더한다 | 동기화할 상태 = 병의 재발 |
| title 자동채움 휴리스틱 | 안 더한다 | 추측 로직 = 유지비 + 침묵 실패 |

## 3. 옛 형태가 전부 접힌다 (예외 없음)

| 옛 형태 | 접는 법 |
|---|---|
| records | items (title은 흔한 관습) |
| table | 같은 칸 공유 items → 소비자가 열로 봄 |
| map(마커) | lat/lng 단 items → 지도가 핀으로 |
| map(경로) | 순서 있는 lat/lng items → 핀이냐 선이냐는 *소비자 동사*가 결정 |
| map(center/zoom) | 안 실음 — 마커 bounds에서 유도(유도 가능한 건 통화에 안 넣음) |
| document/blocks | type+text 단 items, 중첩은 depth 필드(Portable Text 식) |
| 단일값(시세) | items 길이 1 → `items[0].price` |
| 트리/그룹 | parent/group 필드 단 items |

## 4. 생산자 계약 — items()로 감싸기 하나

```python
from common.currency import items
return items([{ "title": ..., ...열린 필드 }, ...], success=True, message="...")
```
`items(rows, **wrapper)` = `{"items": list(rows), **wrapper}`. **title 추측 안 함**(§2). returns 선언은 "items()를 호출했나"에서 파생 → 선언↔출력 어긋날 자리 구조적으로 없음.

## 5. 소비자 계약 — 아는 필드만 읽고, 못 읽으면 *신호한다*

`take/filter/sort` = 어떤 items든. `chart` = 숫자 칸 찾음. `map` = lat/lng 찾음(핀/선은 동사). `document` = title+필드, type/text 있으면 산문.
**유일한 규율**: 소비자가 자기 뷰에 쓸 필드를 *하나도* 못 찾으면 조용한 빈 결과 말고 **보이는 신호**("숫자 칸 없음"/"좌표 없음"). 이게 필드명 드리프트의 유일한 완화책(레지스트리 대신). ★새 소비자 작성 체크리스트에 박을 것.

## 6. 전환 전략 — dual-emit (비파괴)

★이행의 무게중심은 *생산자가 아니라 소비자(렌더러)*다. 지금 `records`/`table`/`map_data`/`image_grid`를 직독하는 앱 렌더러(ActionDesktop·GenericInstrument)에 런처가 의존한다.

1. **dual-emit**: 생산자가 items와 옛 키를 *함께* 낸다(`{**old, **items(rows)}`).
2. 소비자/렌더러를 하나씩 items로 옮긴다.
3. 다 옮긴 뒤 옛 키 분기 삭제(완전 컷오버 — 임시방편 금지 원칙=은퇴까지 끝낼 것).

## 7. 현재 상태 — Phase 1 ✅ (2026-06-27)

- **생성자**: `backend/common/currency.py` `items()` 신설(핸들러가 `from common.currency import items`).
- **엔진 keystone**: `data-ops/handler.py` `_get_records`=**records 우선·items 폴백**(★아래 충돌 점검 참고) / `_emit_records`=items+records dual-emit. → `>>` 파이프가 단일 통화로 흐름(전환기엔 records 키가 운반, 컷오버 후 items로 플립).
- **대표 생산자 2 전환(dual-emit)**:
  - `self:business` op:list — items(개방필드 title/id/level/description, `level`이 "레벨 0" 문자열 아닌 진짜 필드) + records + businesses.
  - `sense:realty` source:zigbang — items에 `lat/lng/distance_m` 노출(records 5칸이 버린 필드) + records + map_data.
- **검증**: business 단독 items7/records7 공존 · `business >> take 2`(items2/records2) · zigbang items에 lat/lng 직독 · photo 파이프가 records(title) 흘림 · **골든파이프 5/5 PASS·build --check 142 통과·구조 건강 ✅**.

### 7.5 ★점검에서 잡은 충돌 — `items`는 과적 키 (메모리 경고가 옳았음)

`items`를 **raw 행으로 이미 쓰는 생산자**가 여럿이다(메모리 `architecture_records_currency`가 "items는 naver·shopping·kosis 과적이라 통화 키로 회피"라 적어둔 그 이유). 그래서 keystone을 **items-우선으로 두면 침묵 오독**이 난다 — 점검 실측:

| 생산자 | top-level `items` 정체 | records 있나 | items-우선이면 | 판정 |
|---|---|---|---|---|
| `self:photo` | 한국어키 summary(`타입/크기/촬영일`, **title 없음**) | ✅(개방필드 records) | summary가 records 가로챔→titleless 흐름 | **오작동** |
| shopping | 상품 dict(title/name) | ✗ | 새로 파이프 가능 | 무해(개선) |
| web news | 뉴스 dict(title) | ✗(이 함수) | 새로 파이프 가능 | 무해 |
| `self:business_item` | 아이템 dict(title) | ✅ | 둘 다 title→호환 | 무해 |
| kosis | `ITM_ID`는 `data` *안에 중첩* | ✅ | top-level 아님→안 닿음 | 안전 |

**해결 = `_get_records` records-우선·items-폴백**(적용·검증). records(현재 명확한 통화 키)를 먼저 읽어 과적 `items`와 충돌 회피. records 없는 생산자(shopping·web)만 items로 폴백→파이프 가능(보너스). 기존 파이프 동작 *완전 불변*(골든 5/5). 이 순서는 **전환기·최종상태 둘 다 안전**(records 있으면 그걸, 없으면 items).

## 7.6 ★Phase 2 ✅ — 옛 형태→items 파생을 *렌더러 경계 한 곳*에서 (2026-06-27)

§8.1의 "생산자 일괄 dual-emit"을 **80여 방출 사이트(23개 핸들러)를 건드리지 않고** 한 곳에서 달성했다. 옛 통화 형태(records/table/blocks)를 단일 통화 `items`로 파생하는 **`common/currency.py` `derive_items(result)`** 를 신설하고, 이를 **렌더러 경계** — `backend/api_ibl.py` `/ibl/execute`(문자열 파싱 직후) — 에서 호출한다.

```python
# api_ibl.py /ibl/execute 끝:  실행 → str이면 json.loads → derive_items
from common.currency import derive_items
return derive_items(result)
```

`derive_items`(common/currency.py): 이미 items(list)면 보존, 아니면 ① records → items ② table(columns+rows / table봉투) → 행 dict items ③ blocks → items. **map_data 제외**(봉투 구조가 생산자마다 달라 균일 파생 불가; 지도 위젯이 봉투 직독 — §3이 map을 특수 케이스로 인정). **역방향(items→records) 금지** — items는 비통화 raw로 쓰는 과적 키(§7.5).

**★왜 `_route_handler`(공용 choke point)가 아니라 렌더러 경계(api_ibl)인가** — 두 번 갈아엎고 얻은 결론:
1. **문자열 생산자 커버**: 많은 핸들러가 `json.dumps` *문자열*을 반환한다(pc-manager 35·system_essentials 22·world_bank 등 다수). `_route_handler`는 파싱 *전*이라 dict 결과만 잡고 문자열 생산자를 통째로 놓친다. api_ibl은 `json.loads` *후* 호출되므로 str·dict를 모두 커버.
2. **에이전트 토큰 중복 회피**: `_route_handler`는 에이전트의 내부 `execute_ibl`도 거친다 → 거기서 items를 더하면 records가 통째로 중복돼 tool-result 토큰이 2배(메모리 `project_agent_payload_size_budget` 위반). **모든 렌더러 표면(앱·수동·원격·폰)은 HTTP `/ibl/execute` 단일 경로로 들어오고**(GenericInstrument·ManualMode·api_launcher_web·폰 네이티브 모두), 에이전트는 안 거친다. items는 *렌더러 관심사*이므로 렌더러 경계에 둔다.

**왜 per-producer 편집이 아니라 한 곳인가 (§2 거버넌스)**: per-producer dual-emit은 22+곳에 *유지·동기화할 상태*를 심고 컷오버 때 다시 청소해야 한다. derive_items는 동기화 지점을 **N→0**(생산자는 옛 키만, items는 파생). 컷오버(생산자가 items 직접 방출·옛 키 제거) 후 derive_items는 무동작 → 제거.

**파이프**: 프론트가 `final_result`를 펴는데(GenericInstrument.tsx:126), data-ops `_emit_records`가 이미 거기에 items를 넣으므로(Phase 1) 커버됨. 단일 액션은 api_ibl top-level 파생으로 커버. (드문 가장자리=파이프 끝이 *문자열 producer*면 final_result에 items 없음 — 추후.)

**§7.5 선결도 처리**: `self:photo`의 비통화 top-level `items`(한국어 summary `타입/크기/촬영일`) → `summary_table` 개명(`photo-manager/handler.py:374`). 렌더러는 `from: records`만 읽어 무영향, data-ops는 records-우선이라 무영향.

**검증(in-process, 새 프로세스가 디스크 최신 로드)**: derive_items 단위 6종(table봉투·top-level columns/rows·blocks·map_data 제외·items 과적 보존·효과 무동작) · 렌더러 경계 재현: photo(핸들러가 str 반환·records 포함)→items L3, world_bank(str·table 포함)→items L49(★이전 실패 케이스 해결) · 에이전트 경로 photo items 미주입(토큰 중복 0) · build --check 142.

**★라이브 반영 필요**: `api_ibl.py`·`common/currency.py`=backend 코어 → **백엔드 재시작**. photo `handler.py` → `/packages/reload`(재시작이 둘 다 커버). 재시작 후 라이브 curl로 photo·world_bank items 확인할 것. (참고: `_route_handler`에 잠깐 뒀던 records-only shim은 위 1·2 이유로 *철회*하고 api_ibl로 이동함 — 코드에 흔적 없음.) **✅ 라이브 확인됨(재시작 후)**: photo items=3, world_bank items=49(table→행dict).

## 7.7 ★Phase 3(부분) ✅ — §8.2 소비자 flip: records/blocks 버티컬 (2026-06-27)

derive_items가 렌더러에 items를 보장하므로, app 블록의 `from:` 키를 `items`로 모으기 시작. **이번엔 *필드 동일* 부분집합만** — derive_items가 items=records/blocks *같은 리스트*를 주므로 위젯 필드가 그대로 풀린다(무위험·무관찰변화, 컷오버 선이행).

- **flip 완료(12)**: `from: records`(10: photo×3·fs_query×3·travel×2·startup·contest) + `from: blocks`(2: report latest·read의 thread) → `from: items`. src yaml 2파일 → build(142) → `/packages/reload`(★재시작 불필요 — `_derive_instruments`가 IBL_NODES_PATH 매 호출 새로 읽음, 노드캐시는 reload가 비움).
- **검증(라이브)**: instruments 매니페스트 photo 3모드 `from: items` · `/ibl/execute` photo items=5[title,meta,summary,url,path]·fs_query items=5·report items=19(blocks→items, blocks 보존, thread text) 전부 렌더 가능.

**★business·커스텀키는 *제외*(필드 드리프트 — §9가 경고한 비용 실측)**: `from: businesses`(self:business)는 flip 못 함 — Phase 1 dual-emit이 `items`에 records 관습 필드 `title`을 넣었는데(=name 개명), card_list는 `from: businesses`라 native `name`을 참조. items로 flip하면 items엔 `name`이 없어 카드 표시가 깨진다. records/blocks 버티컬이 안전했던 건 items가 native 리스트와 *동일 dict*(=카드가 records-관습 필드)였기 때문. (회귀 점검 ✅: travel/startup/contest/fs_query 카드 전부 `{title}/{meta}/{summary}/{image}/{url}` records-관습 → items=records 정확 일치, 무회귀.)

## 7.8 ★Phase 3b ✅ — native-필드 생산자 패턴: items=native + 손실적 records 은퇴 (2026-06-27)

커스텀키 생산자를 파보니 **records-관습 dual-emit이 단일통화와 *충돌***한다는 게 드러났다(전략 교정). 많은 생산자가 `{nativekey: [풍부 dict], records: _to_records(...)}` 둘 다 낸다. `_to_records`는 native의 풍부 필드(level/author/content/hashtag…)를 records 5칸(title/meta/summary/url/image)으로 *납작하게* 버린다. 그런데 그 생산자들의 **카드는 native 필드를 읽도록** 만들어져 있다(예: work_guideline 카드 `{level}`·feed 카드 `{author}/{content}`·board 카드 `{name}/{hashtag}`). derive_items는 records-우선이라 flip하면 *손실적 records*를 items로 줘서 카드가 깨진다.

→ **올바른 이행 = items=native(풍부) + 손실적 records 은퇴.** native 리스트 자체가 단일 통화(열린 필드)다. 카드는 native 필드를 그대로 읽고(무수정), `_to_records` 호출이 사라져 *코드가 준다*. records-관습은 단일통화가 되돌리려던 제약(열린 items > 5칸 records)이었음 — 이행이 *필드 풍부성을 회복*한다.

**두 패턴 분기(소비자 flip 시 카드 필드로 판별)**:
| 카드가 읽는 필드 | 이행 | 예 |
|---|---|---|
| records-관습(title/meta/summary/url/image) | `from:→items` (derive_items가 records→items, 생산자 무변경) | photo·fs_query·travel·startup·contest ✅ |
| native(level/author/name/hashtag…) | 생산자가 `items=native` 직접 방출 + 손실적 records 은퇴 + `from:→items` | work_guideline ✅ / feed·board·… ⏳ |

**이행 완료 native 생산자(검증)**:
- **work_guideline** ✅: `business/handler.py` `_guide_list` → `_ok({"items": bm.get_all_work_guidelines()})`(guidelines·records 키 제거, `_to_records` 은퇴). 라이브: items=5, `[id,level,title,content,updated_at]`(★records가 버리던 `level` 복원).
- **report**(self:report op:list) ✅: `report-viewer/handler.py` `reports`→`items`. 라이브: items=5, `[title,date,filename,path,sub]` native. (records 본디 없음=단순 rename.)
- **launch**(limbs:launch list) ✅: `web/handler.py` 두 list 반환 `sites`→`items`. 라이브: items=21, `[name,url]` native.
- **culture ×4**(sense:performance·book·classic·exhibit) ✅: `culture/handler.py`의 5개 records-부착 지점 `result["records"] = _X_to_records(result["data"/"results"])` → `result["items"] = result.pop("data"/"results")`(native 키 pop=중복 제거, _X_to_records 은퇴). app블록 from: 4개(★culture 것만 — search_books·commercial·realty·youtube의 from:data/results는 *안* 건드림, 그 생산자 미이행). 라이브: book items=10·classic 10·performance 20·exhibit 10, data/results·records 키 소멸. **★items==옛 native와 동일 dict라 카드 필드 무관 무회귀**(book 카드가 {bookname}이든 뭐든 동일 내용 직독).
- 모두 외부 reader 점검 클린, 카드 native 필드 무수정, `from:→items`, build142→reload 라이브.
- **★표준형=native 키 pop(개명)**: 중복 없이 단일 items만. (한때 culture를 keep-data로 뒀다가 에이전트 토큰 중복 회피 위해 pop으로 통일 — work_guideline/report/launch와 동일형.)

**커스텀키 생산자 맵(★returns로 분류 — 통화만 이행 대상, scalar/effect는 면제)**:
- ✅ **자족 native card_list/list_action(전부 완료, 15 producer)**: launch·report·culture×4(performance/book/classic/exhibit)·restaurant(combined+map_data 보존)·search_youtube·search_books·radio(★싱글턴=tool_radio.py 편집 후 `touch backend/api.py`)·radio_favorite·**feed·board**(channel_engine 공유 코어 — posts/boards→items, /packages/reload가 코어도 반영함을 실측)·**business_document**(documents→items, 내부 reader 우려는 stale였음=자족). 모두 native 카드라 items=native(records 동반 시 pop+은퇴), `from:→items`, 라이브 검증.
- ⏳ **남은 통화 생산자(각 복잡, 개별 작업)**: ①**real-estate** `data`(commercial·realty×2, records) — data를 dong/name으로 *제자리 필터* + `summary` 참조 + map_data 동봉이라 단순 pop 아님. ②**manage_events** `events`(records) — `api_scheduler.py`(backend 코어) 반환 + `calendar_html.py` 내부 events와 구분 필요. ③**business** `businesses`(records) — ★필드 드리프트(items엔 records관습 `title`, card는 native `name`)=card 필드 정합 동반. ④**messages** `conversations`/`messages`/`contacts`(records, 3키 클러스터) + **neighbor** `contacts`(records) — thread/editable_list, CRM 상호참조라 묶어서. ⑤**weather** `forecast`(table) — table 통화를 kv_list로 렌더, table→items 행dict 검토.
- ✅ **면제(scalar/effect — 통화 아님, 이행 대상 아님)**: host top/disks(scalar 자기상태)·stock/crypto data.prices(scalar 시계열)·navigate_route map_data/key_guides(scalar)·cctv cctvs(effect)·radio_favorite favorites(effect, 단 list는 items화함)·report types(effect)·nostr relays(effect)·music queue(effect). 이들 from: 키는 그대로 둔다(kv_list/sparkline이 scalar 하위구조 직독).
- **★cctv는 얽힘(막판)**: `cctvs`가 ①카드 ②지도 markers ③소스 집계 내부키(kakao/topis_res["cctvs"]) 삼중 + `_cctvs_to_records` → map_data 컷오버 때 함께.
- **★컷오버 청소 (대부분 완료 2026-06-28)**: ✅삭제됨 — culture `_performances_to_records`/`_books_to_items`/`_gutenberg_to_records`/`_korean_classics_to_records`/`_exhibits_to_records`(5) + business `_to_records`+`_doc_records`(2) + study `_search_books` 내부 죽은 records 루프(1). 전부 호출자 0 재확인·--check 142 GREEN·라이브 회귀 통과. ⏳잔존 — channel_engine feed/board의 records-building 루프(backend/*.py, uvicorn --reload 자해 위험으로 백엔드 정지 시점에 정리). (native 이행이 _X_to_records류를 죽인다 = 코드 감소의 실현.)

## 7.9 ★§8.4(부분) ✅ — returns enum에 `items` + 체커 items-우선 (2026-06-27)

native 이행 생산자가 records를 은퇴하자 §1B 체커가 "returns:records 선언인데 items만"으로 RED 5개를 띄움(선언 드리프트). 정직성·건강 위해 §8.4를 부분 착수:
- **enum 확장**: `build_ibl_nodes.py` `_RETURNS_ENUM`에 `items` 추가(records/table/document는 전환기 호환 유지, 컷오버서 축소).
- **체커 items-우선**: `ibl_health_check.py` `classify_currency`가 `items`(비어있지 않은 dict 리스트)를 *최우선* 통화로 GREEN(title 불요=열린 항목). declared 집합·생산자 집합에 items 합류. **★효과**: derive_items가 렌더러 경계(=체커 probe 경로 `/ibl/execute`)서 records/table/blocks도 items로 파생하므로, *모든 통화 생산자가 items로 GREEN* — 전환기를 우아하게 흡수(native·파생 무관). 예: 미이행 `search_books`도 `items[5] (선언 records)` GREEN.
- **이행 5액션 returns: records→items**: sense:performance/book/classic/exhibit·self:work_guideline. (report·launch는 `effect` 다중op라 RED 아니었고 그대로.)
- **검증**: build142·바이트 일치 ✓·**§1B GREEN 50/YELLOW 2/RED 0**(이전 RED 5)·골든 5/5·구조 건강 ✅.
- **남은 §8.4**(컷오버 단계): 모든 생산자 items화 후 records/table/document를 enum서 제거, 체커의 records/table/blocks 분기 삭제(items 하나로), `_get_records` items-우선 플립.

## 8. 남은 롤아웃 (다음 단계들)

1. ~~**생산자 일괄 dual-emit 전환**~~ ✅ **records·table·blocks 생산자 모두 §7.6 `derive_items`(렌더러 경계)로 완료** — 렌더러는 이제 옛 형태 무관하게 `items`를 받는다. **남은 형태=`map_data`**(특수: 봉투 구조가 markers vs origin/route로 달라 균일 파생 불가). map 위젯이 `from: map_data` 봉투를 직독하고, §3대로 center/zoom·핀/선은 *소비자 동사*다 → map은 컷오버 막판에 별도로 다룬다(지금은 그대로 동작).
2. **소비자 from: → items** (★무게중심, 진행중):
   - ✅ **records/blocks 버티컬(12)**=완료(§7.7) — items가 native와 동일 dict라 무위험.
   - ⏳ **커스텀키 생산자(per-producer)**: `from: data`(7)·`data.prices`(3)·`stations`(2)·`results`(2)·`contacts`(2)·`conversations`·`businesses`·`posts`·`disks`·`forecast`·`favorites`·`documents`·`cctvs`·`relays`·`boards`·`queue`·`sites`·`reports`·`top`·`combined`·`key_guides`·`guidelines`·`events`·`book.loan_stats.*` 등. **각 생산자별 절차**: ①생산자가 그 리스트를 records로도 내는지 확인(많은 location/메신저 생산자가 records 생산자 목록에 있음=derive_items가 items 줌) ②카드/위젯 필드 참조를 items 필드명과 정합(★`{name}`→`{title}` 같은 드리프트 주의 — §7.7 business 사례) ③`from:`→items, build→reload, 라이브 렌더 검증. 필드 정합 없으면 침묵 깨짐.
   - data-ops 변환자(`_get_table`/groupby/chart/document)는 이미 records-우선·items-폴백이라 동작 — 컷오버 때 items-우선으로 플립(§8.3·8.4).
   - map(`from: map_data`)·`from: '.'`(응답 자체 1행)은 특수 — 그대로 둠.
3. **옛 키 컷오버**: 모든 소비자 이전 후 records/table/map_data 분기 삭제 → 코드 총량 감소.
   - ★**선결 조건(§7.5)**: `_get_records`를 items-우선으로 플립하기 *전에*, **top-level `items`가 통화가 아닌 생산자를 먼저 개명**해야 한다. **photo는 ✅완료**(§7.6: `items`→`summary_table`). 남은 감사: `grep -rn '"items":' data/packages/installed/tools/*/handler.py` 로 나머지 top-level items 생산자 전수 확인 — 현재 후보=shopping(상품 items=통화성, 무해)·web news(통화성)·business/business_item(title 보유, 호환). 비통화는 photo뿐이었음(점검 완료). 플립 시 재확인.
4. **returns enum 축소**: records/table/currency/document → "items 생산자 / 효과 / transform". `ibl_health_check.classify_currency`의 records/table/blocks 분기 → "items 있나" 하나로. build_ibl_nodes `_RETURNS_ENUM` 정리.
5. **§5 신호 규율**을 소비자 작성 체크리스트(`new_action_checklist.md`)에 추가.

## 9. 정직한 단서 (고른 비용)

- **필드명 드리프트**(lat vs latitude)는 남는다 — 레지스트리 안 짓는다(§2). 완화=약속 필드 목록 한 장(문서, 강제 아님) + 소비자 not-found 신호(§5). 오타=기능 침묵-미적용이지 크래시 아님 + 신호로 보임.
- **깊은 중첩 문서**는 flat+depth로 표현력 한계(선택한 포기). **큰 동질 수치 표**는 dict 목록이 columnar보다 무거움(소비자가 내부 투영 → 비용 국소화).
- dict+관습뿐이라 "바깥 형태 하나만 생성자로 강제"가 현실적 최대치(PowerShell 안전은 밑의 타입시스템 덕분, 우리는 없음).
- **목록 아닌 출력**(파일 썼다·ok·예/아니오)=효과, 통화 아님. "모든 게 통화"라는 강박이 형태폭증의 뿌리였으니 안 되풀이.

---

## 10. 표현 평면 분리 — `message` O(1) 불변식 (2026-06-28)

### 10.1 발단 (왜 또 났나)

직방 다가구 주인세대 전세 조사 중 `[sense:realty]{...limit:70} >> [engines:filter]{where:"주인세대"}` 가 **결과 68,032자 → claude 바이너리 MCP 캡 초과 → 파일 스필**. 진단: filter는 items를 0건으로 정상 축소했으나, `_emit_records`(data-ops handler.py:80-89)가 `out = dict(envelope)` 로 **봉투를 통째 복사**해, realty가 같이 실은 거대한 `message`(70건을 한 건씩 풀어쓴 산문)가 그대로 따라감. **filter로 못 줄이는 죽은 무게 + 필터 후 stale(items는 0건인데 message는 "70건…"을 떠듦)**.

### 10.2 이게 단일통화 원칙의 사각이다 (붕괴 아님)

- 데이터 평면은 **안 무너졌다** — `items`는 여전히 유일 컬렉션 통화(`_get_records` items만, records EMIT=0). filter/sort/take 전부 items 위에서 돈다. 회귀 아님.
- 무너진 게 아니라 **원칙의 적용 범위가 표현 축까지 안 갔다.** 단일통화 §2 시험("형태 N개=곱셈=동기화 부채")은 *통화*에만 걸리고, `message`는 "그냥 표현용 문자열"로 분류돼 시험을 안 받았다. 그런데 **items를 한 건씩 렌더한 message는 사실상 items의 두 번째 형태** = 정확히 §2가 금하는 것. 사각에서 샜다.

### 10.3 규칙 (확장된 원칙)

> **봉투의 사람용 텍스트 필드(`message` 등)는 항목 수에 대해 O(1)이어야 한다 — 상태/요약/에러 한 줄("30건 찾음"·"결과 없음"·"위치 못 찾음")만 담는다. 항목을 한 건씩 풀어쓴 O(items) 렌더는 금지. 항목을 화면에 그리는 일은 선언형 렌더러(items→card_list/image_grid)의 몫이며, 생산자가 산문으로 재구현하지 않는다.**

핵심: **`message`를 죽이는 게 아니다.** message에는 정당한 O(1) 소비자가 있다 — 죽이면 그것들이 깨진다(아래 §10.4). 죽이는 건 message **안의 O(items) 덤프**뿐. 정당한 O(1) message는 통화의 복제가 아니라 바운드된 상태문이므로 남는다.

### 10.4 ★`message`를 죽이면 깨지는 곳 (소비자 — 보존 대상)

| 소비자 | 위치 | 의존 형태 | message 사라지면 |
|---|---|---|---|
| `empty_from: message` 선언형 빈상태 | `data/ibl_nodes.yaml` (performance·book·exhibit·restaurant 등 수십 액션) | items 비면 message를 "결과 없음"으로 표시 | 빈 결과인지 오류인지 구별 불가 (강의존) |
| 성공 토스트·실패 표시 | `frontend/.../GenericInstrument.tsx:628,778,805,807` | `data.message`(success=false 에러 / 완료 notice) | 액션 피드백 소실 (강의존) |
| 원격 HTML 에러 | `backend/api_launcher_web.py:1499,756` | `data.message` 폴백 | 폰/원격서 에러 안 보임 |

**파이프(`>>`)·프롬프트·메모리는 message 비의존** — 다음 액션은 items만 소비, 프롬프트 빌더는 items만 추출, 메모리는 봉투 전체 JSON 저장. 따라서 **O(1)로 줄이는 건 전부 안전, 통째 삭제는 위 3곳을 깬다.**

### 10.5 위반 목록 (6곳 확정 — items와 함께 O(items) 산문 방출)

| # | 파일:줄 | 함수 | 산문 | items 동반 | 상한 |
|---|---|---|---|---|---|
| 1 | `real-estate/tool_zigbang.py:314-328` | get_zigbang_listings | 건당 meta+URL | Yes | 없음(기본30) |
| 2 | `location-services/handler.py:854-862` | amadeus_travel_search | 건당 3-4줄 | Yes | 15 (그래도 선형) |
| 3 | `study/handler.py:34-56` | _search_arxiv | 논문당 6줄 | Yes | 없음(기본5) |
| 4 | `study/handler.py:197-221` | _nanet_author_find | 행당 1줄 | Yes | 30 |
| 5 | `study/handler.py:239-255` | _nanet_coauthor | 행당 1줄 | Yes | 30 |
| 6 | `health-record/handler.py:743-777` | format_search_results | 건당 1줄(message만, items 없음) | **No** | 없음 |

추가 점검 대상(애매 — `text`/`table` 키로 분리돼 덜 위반이나 같은 결): health-record `format_measurements`(672), `symptoms`(354), `medications`(370). slide_ai.py return부 미확인(검토 필요). **무해 확인**: blog_vault·youtube(O(1) 고정문)·browser_session·media_producer·system_essentials(message 미사용).

### 10.6 수정 레시피 (생산자 1곳당)

1. **items는 그대로 둔다**(대부분 이미 native dict 방출 — 상세는 items가 진실 소스).
2. **비어있지 않은 분기의 `message`를 O(1) 요약으로 교체**: `message = "\n".join(per-item lines)` → `message = f"{label} {n}건"`. 건당 줄·URL은 **삭제**(items에 이미 있음, 렌더러/에이전트가 items로 읽음).
3. **빈 분기(n==0)의 message는 유지**(이미 O(1) — "…매물이 없습니다". `empty_from`이 이걸 씀).
4. #6(health-record format_search_results)은 items가 아예 없음 → **items를 native dict로 추가 방출** + message는 O(1)로. (다른 결의 작업 = 미이행 생산자의 items화.)

예(zigbang #1):
```python
# before (314-316)
msg_lines = [f"직방 '{...}' 반경 {radius}m · {cat} {lease_label} — {len(rows)}건:"]
for r in rows: msg_lines.append(f"- {r['meta']}\n  {r['url']}")
# after — 첫 줄만(O(1)), 건당 루프 삭제
message = f"직방 '{matched or region}' 반경 {radius}m · {cat} {lease_label} — {len(rows)}건"
```

### 10.7 ★강제 장치 (재발 방지 — 변명 없게)

`--check`(정적)는 핸들러 런타임 산문을 못 본다 → **강제는 런타임 불변식으로**, `ibl_health_check.py`(하루 1회, AI 0, 이미 fixture로 `/ibl/execute` probe)에 합류:

> **불변식: `returns: items` 액션의 봉투에서 `items`를 뺀 나머지 직렬화 크기는 항목 수에 대해 O(1)이어야 한다.**
>
> 구현(둘 중 하나, 권장은 ⒜):
> ⒜ **고정 예산(단일 실행)**: fixture로 실행 → `non_items_bytes = len(json.dumps({k:v for k,v in env.items() if k!="items"}))` → `> 2048` 이면 FAIL(위반 필드명 출력). realty 덤프(~30KB)는 즉시 잡힘, 정당한 상태문(~수십 byte)은 통과.
> ⒝ **스케일 차등(2회 실행)**: limit=N·2N 두 번 → non_items_bytes가 항목수에 비례 증가하면 FAIL. ⒜보다 정밀하나 fixture가 다항목을 줘야 함.

+ `new_action_checklist.md`에 한 줄: *"목록을 내는 액션은 `message`에 항목을 풀어쓰지 마라(O(1) 요약만). 항목 표시는 렌더러가 items로 한다 — §10."* (§5 신호 규율 옆.)

이 두 가지(런타임 불변식 + 체크리스트)가 있어야 7번째 생산자가 같은 실수를 해도 self-check가 잡는다. 문서만으론 또 샌다.

### 10.8 작업 순서

1. **강제 장치 먼저**(§10.7 ⒜) — 불변식을 켜면 위반 6곳이 self-check RED로 *자동 열거*된다(목록을 코드가 유지, 사람이 안 함).
2. 위반 6곳 §10.6 레시피로 수정 → 핸들러 편집이라 `/packages/reload`(직방·study·location·health)로 라이브. radio류 싱글턴 함정 없음(이들은 매 호출 import).
3. `empty_from`·토스트 회귀 확인(§10.4 3곳) — message가 O(1)로 남아 있으니 통과해야 함. realty empty 분기·culture empty_from 라이브 1건씩 점검.
4. health-record #6은 items화(별도, 미이행 생산자 롤아웃 §8.2와 합류).
