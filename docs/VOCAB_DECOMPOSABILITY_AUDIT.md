# 어휘 분해가능성 전수 감사 (2026-08-15)

> **판정 기준이 바뀐 감사다.** 직전 감사들이 쓰던 자(사용계수·호출빈도·코퍼스 행수)를
> 은퇴 근거에서 **배제**하고, 오직 **구조적 분해 가능성**으로만 151 어휘를 훑었다.
> 이번 산출물은 **조사·설계 제안까지** — 어휘 삭제·backend 편집 없음(라이브 reload 자해 회피).
>
> 자매 문서: `VOCAB_COMPOSABILITY_HANDOFF.md`(집행 이력·기각 기록) ·
> `HIGHER_ORDER_SENTENCE_DESIGN.md`(문형 층·M3) · `VOCAB_DEDUP_HANDOFF.md`(압축 전사)

---

## 0. 자(尺)를 바꾼 이유 — 순환논증 기각과 그 새 증거

사용자 판정(그대로 옮김): **"나쁜 언어라서 스위치처럼 쓰이는 단어를 '스위치로 쓰이니
스위치로 고정하자'는 것은 순환논증이다."** 미사용은 어휘의 죄가 아니라 *조합이 안 되게
생긴 언어*의 증상일 수 있고, 그 상태를 빈도로 못 박으면 실패의 비준이 된다.
(이미 `c4330f2` 로 프레임째 기각 기록됨 — 이 감사는 그 판정의 집행이다.)

### 0-1. 이번에 새로 확인된 오염 — 빈도 지표의 **두 번째** 독립 오염원

사용자가 방금 고친 코드(미커밋, `git diff` 실측)에서 나온 사실이다:

| 수리 | 파일 | 무엇이 틀려 있었나 |
|---|---|---|
| **id 기반 도구 페어링** | `providers/anthropic.py`·`claude_code.py`·`cognition/agent_pipeline.py` | 옛 `[-1]` 페어링이 **병렬 호출에서 A의 결과를 B에 붙이고 B의 결과(실패 포함)를 유실**. 빈 껍데기가 된 A가 반성 게이트를 오발동(라이브 3회) |
| `had_tool_calls` 기본값 | `cognition/ai_agent.py` | 인자 미전달로 기본 `False` — **도구를 실제로 쓴 정상 응답도 "도구 안 씀"으로 판정** |
| 반성 턴 게이트 | `cognition/agent_pipeline.py` | `elif` → `if not _eval_ran`. 달성기준이 빈 THINK 턴이 평가·반성 **두 그물 사이로 낙하** |

첫 번째가 이 감사에 직접 걸린다. `eval_tool_calls`/`tool_calls_log` 는 **경험 증류 → 해마
코퍼스**로 흐르는 궤적이다. 병렬 호출이 잘못 페어링됐다는 것은 **어떤 액션이 어떤 액션과
함께 쓰였는지(=조합 파트너)의 기록이 병렬 구간에서 틀렸다**는 뜻이다.

이미 알려진 오염(자가점검 순찰이 `origin='agent'` 로 잡혀 08-15 이전 계수의 ~55%)에 더해
**독립적인 두 번째 오염원**이다. 두 오염의 성격이 다르다는 점이 중요하다 — 순찰 오염은
"안 쓴 걸 썼다고" 부풀리고, 페어링 버그는 **"함께 쓴 것을 안 썼다고" 깎는다.** 조합 지표는
후자에 정확히 취약하다.

> **결론**: 빈도 배제는 이제 원칙(순환논증)만이 아니라 **계측 신뢰성**으로도 받쳐진다.
> `vocab_composition_metrics.py` 의 네 지표는 **품질 개선의 전후 측정 도구로만** 쓰고,
> 은퇴 근거로 승격하지 않는다. 특히 파이프/파트너 다양성 수치는 이 수리 **이전 데이터**라
> 재수집 전까지 하한선으로만 읽어야 한다.

---

## 1. 실측 베이스라인 (문서 인용 아님 — 빌드/yaml 기준)

```
$ python3 scripts/build_ibl_nodes.py --check
[build_ibl_nodes] 노드 6개, 액션 151개, 패키지 fragment 53개(+123 액션)
[build_ibl_nodes] 검증 통과 ✓ … 전 가드 통과
[build_ibl_nodes] 압축 경고(비차단): 2건
```

| 노드 | 액션 | op분기 | app블록 | returns 분포 |
|---|---:|---:|---:|---|
| sense | 42 | 17 | 18 | items 31 · scalar 10 · effect 1 |
| self | 52 | 29 | 9 | items 25 · scalar 10 · effect 17 |
| limbs | 16 | 9 | 1 | effect 15 · scalar 1 |
| others | 18 | 12 | 6 | items 11 · effect 6 · scalar 1 |
| engines | 9 | 3 | 1 | effect 8 · scalar 1 |
| table | 14 | 0 | 0 | **transform 10** · effect 3 · scalar 1 |
| **계** | **151** | **70** | **35** | |

- `prompt_hidden`(스위치) = 2 (`engines:newspaper`·`engines:icon`)
- **app: 블록 보유 = 35** (§6에서 별도 식별)

---

## 2. 판정 기준 — 3분법 (빈도 아님)

각 어휘에 **하나의 질문**만 던졌다: *이 액션이 내부에서 하는 일이 곧 파이프 한 줄인가?*

| 등급 | 정의 | 처분 |
|---|---|---|
| **A. 원자** | 조합으로 표현 **불가**. 외부 API+인증 캡슐화 / 프로토콜 / 하드웨어 접촉 / 문법 자체 | 유지 — 빈도 무관 |
| **B. 축(軸)** | 이름이 **파라미터여야 할 것**. 같은 동사·같은 저장소·다른 명사 | 통합 — 명사를 데이터로 |
| **C. 문장** | 기존 어휘의 **호출 순서**뿐. 오케스트레이션·산술·URL 하드코딩 | 문장화(스크립트/워크플로/앱) |

B와 C는 **반증 가능해야 한다** — 후보마다 대체 IBL 문장을 적었다. 그 문장이 실제로
안 되면 그 후보는 기각이다.

---

## 3. 6노드 전수 스윕 (요약)

| 노드 | A. 원자 | B. 축(통합 후보) | C. 문장 |
|---|---:|---:|---:|
| sense | 33 | 6 | 3 |
| self | 30 | 20 | 2 |
| limbs | 12 | 4 | 0 |
| others | 8 | 10 | 0 |
| engines | 7 | 2 | 0 |
| table | 14 | 0 | 0 |
| **계** | **104** | **42** | **5** |

**table 14개는 전원 A** — 이것들이 조합자 자체다. 분해 대상이 아니라 분해의 도구다.

---

## 4. B군 — 통합 후보와 **대체 IBL 문장** (반증 가능)

### 4-1. 재생기 3형제 — 새 낱말 없이 −2 (가장 확실)

**실측(핸들러를 열었다)**: `tool_radio.py:517 radio_status()` / `:563 set_radio_volume()` 는
라디오 모듈 전역(`_player_process`·`_current_station`)만 만진다. 음악은 youtube 패키지의
별도 `_OP_DISPATCHERS["music_op"]`(queue/stop/skip/seek)로 완전히 다른 재생기다.

**즉 desc 두 개가 거짓말이다** — `limbs:player_status` desc "음악·라디오 재생 상태"(실제
라디오 전용), `limbs:volume` implementation "mpv IPC 소켓으로 볼륨 조절"(실제 `play_radio`
**재시작**). `limbs:explorer` 의 "Finder" 거짓말과 **같은 부류**이고, 그건 이미 은퇴 사유였다.

```ibl
# 현재 (3 낱말)
[limbs:player_status]
[limbs:volume]{volume: 40}
[limbs:radio_favorite]{op: "list"}

# 대체 — radio 의 op 축으로 흡수 (신규 낱말 0)
[limbs:radio]{op: "status"}
[limbs:radio]{op: "volume", volume: 40}
[limbs:radio]{op: "favorite", mode: "list"}
```
`limbs:radio` 는 이미 op 분기(play/stop)를 가진다. **−3 낱말, 신설 0.**
음악 상태는 이미 `[limbs:music]{op:"queue"}` 로 표현된다.

> 반증 조건: `volume`/`player_status` 가 음악 재생기도 제어한다면 기각. — **실측으로 부정됨.**

### 4-2. 세계-명사 CRUD 20종 — 최대 후보

**실측**: `business.db` 한 파일에 6개 테이블이 있고, 그것이 6개 액션 이름과 1:1이다.
`business/handler.py:1011 _OP_DISPATCHERS` 는 7개 액션 전부를 `fn(bm, tool_input)` —
**같은 매니저·같은 시그니처**로 던진다. 함수 본문 실측:

```
_doc_list 3줄 · _nb_list 3줄 · _ct_update 5줄 · _guide_update 5줄 · _doc_update 5줄
_ct_add 6줄 · _guide_list 6줄 · _biz_delete 7줄 …
```

CRUD op 는 **3~8줄 통과 함수**다. 실질 로직은 `_doc_publish`(36 — Nostr 발행)·
`_nb_merge`(28 — 신원 병합)·`_nb_save`(31 — 검증)뿐이다.

같은 모양이 노드를 건너 흩어져 있다. `sense:local_query`(FTS 읽기)와
`self:local_save`(쓰기)는 **하나의 원장이 두 노드로 찢어진 것**이다.

```ibl
# 현재 (명사마다 낱말)
[self:business]{op: "list"}
[self:business_item]{op: "save", business_id: 3, title: "..."}
[others:neighbor]{op: "list", level: 2}
[others:contact]{op: "add", neighbor_id: 7, type: "email", value: "..."}
[self:work_guideline]{op: "detail", level: 2}
[sense:local_query]{query: "카페"}
[self:local_save]{data: "...", type: "store"}

# 대체 — 명사를 자유 데이터 라벨로 (신설 1)
[self:ledger]{store: "business", op: "query"}
[self:ledger]{store: "business_item", op: "save", values: {business_id: 3, title: "..."}}
[self:ledger]{store: "neighbor", op: "query", where: "level == 2"}
[self:ledger]{store: "contact", op: "save", values: {neighbor_id: 7, type: "email", …}}
[self:ledger]{store: "work_guideline", op: "query", where: "level == 2"}
[self:ledger]{store: "local", op: "query", q: "카페"}
[self:ledger]{store: "local", op: "save", values: {...}}
```

**흡수 대상 CRUD op**: `self:business` · `business_item` · `business_document`(list/detail/update) ·
`work_guideline` · `others:neighbor`(list/detail/save/delete) · `others:contact` · `others:follow` ·
`self:local_save` + `sense:local_query` · `limbs:radio_favorite`(4-1과 택일).

**남는 진짜 능력**(원자로 존치, 별도 낱말 또는 도메인 op):
`business_document{regenerate}`(AI 재생성) · `{publish}`(Nostr 발행) ·
`neighbor{merge}`(신원 병합) · `business_item{add_image/remove_image}`(파일 복사).

> **헌법 정합 (§8 참조)**: 이 통합은 새 규칙이 아니라 **이미 선포된 조항의 소급 적용**이다.
> 반증 조건: 이 원장들이 서로 다른 트랜잭션·권한·동기화 계약을 가진다면 기각.
> — `business.db` 단일 파일·단일 매니저이므로 **적어도 business 6종은 부정됨.**
> `health`/`finance`/`memory`/`notebook` 은 별 DB·별 ingest 라 **이번 범위에서 제외**(§9).

### 4-3. 등기부 3형제 — 같은 list/register/remove

`self:webapp{list,status,register,remove}` · `self:script{list,register,run,remove}` ·
`engines:web_site{list,register,remove,update}` — 세 개가 **동일한 등기부 CRUD**다.

```ibl
# 대체 (4-2의 ledger 로 흡수 가능)
[self:ledger]{store: "webapp", op: "query"}
[self:ledger]{store: "site", op: "save", values: {...}}
```
**남는 능력**: `webapp{status}`(전 함대 병렬 HTTP 생존 실측 — 이건 감각이다) ·
`script{run}`(결정화 사다리의 가로대 — 절대 흡수 금지).

> ⚠ **주의**: `self:script` 는 "새 특수 어휘 만들까?"의 기본 답으로 설계된 **반-어휘-증식
> 장치**다. 등기부 부분만 접고 `run` 은 반드시 독립 유지. 이 후보는 이득이 작아 **후순위**.

### 4-4. 공개면 4종 — 39 op, 카탈로그 ~4,900자

**실측**: `others:portal`(12 op) · `showcase`(10) · `family_news`(10) · `bulletin`(7) 이
`SHOWCASE_ORIGIN_SECRET` 를 공유하고 전부 `backend/surface/` 에 살며 `portal_base.py` 를
공유 기반으로 쓴다. 서빙도 동일 3층(브라우저→Worker→터널→맥).

**결정적 증거**: 정기보고 공개면 `/r/` 은 **IBL 어휘가 0개**다(`backend/surface/api_report.py`,
CLAUDE.md "신규 IBL 어휘 없음"). 같은 3층 인프라 위의 다섯 번째 공개면이 **낱말 없이 산다.**
넷은 낱말을 갖고 하나는 안 갖는 이 비대칭이, 넷의 낱말이 필연이 아님을 보여준다.

```ibl
# 현재
[others:portal]{op: "members", portal: "BZVAB"}
[others:showcase]{op: "basket_list"}
[others:family_news]{op: "publish"}
[others:bulletin]{op: "create", title: "동네 게시판"}

# 대체 — 표면 종류를 축으로 (신설 1, −4)
[others:surface]{kind: "portal", op: "members", portal: "BZVAB"}
[others:surface]{kind: "showcase", op: "basket_list"}
[others:surface]{kind: "family_news", op: "publish"}
[others:surface]{kind: "bulletin", op: "create", title: "동네 게시판"}
```

> **반론(강함, 정직하게 적는다)**: 넷의 op 집합이 실제로는 겹치지 않는다 —
> portal 은 회원 CRM(members/promote/revoke/audit), family_news 는 조판(photos/publish),
> showcase 는 바스켓(basket_*), bulletin 은 글 모더레이션(post_delete). `kind` 마다 다른
> op 표를 갖는 통합은 **"선행 명사 스키마"에 가까워진다**(§8이 금지하는 방향).
> → **판정: kind 축으로 접는 것은 보류.** 대신 넷에 **공통으로 존재하는 것**만 뽑는 것이
> 정직한 1단계다 — 아래 §7-U3.

### 4-5. 상거래 3형제 — `sense:search{source}` 선례 적용

`search_shopping`(다나와) · `used`(당근/번개/중고나라/네이버) · `freelance`(크몽).
셋 다 이미 `source` 축을 가지며, 셋 다 "물건·서비스를 파는 목록"이다.

```ibl
# 대체 (신설 1, −3) — 2026-08-05 search 통합(5→1)과 동일한 수
[sense:market]{kind: "new", source: "danawa", q: "노트북"}
[sense:market]{kind: "used", source: "danggeun", q: "자전거"}
[sense:market]{kind: "service", source: "kmong", q: "번역"}
```
**선례가 있다**: `search_ddg/naver/gnews/hn/guardian` 5개가 `[sense:search]{source}` 하나로
접혔고(`dbf370d`) 그 통합은 성공으로 기록됐다. 같은 수를 상거래에 적용하는 것뿐이다.

> 반증 조건: 셋의 통화 필드가 정렬·필터 불가능할 만큼 다르면 기각.
> — 셋 다 `items{title, price, url, …}` 로 이미 `table:sort{by:"price"}` 가 도는 것이 실측.

### 4-6. 스케줄 6형제 — 이미 설계됨, 기준 일치 확인만

`schedule`/`trigger`/`workflow`/`goal`/`manage_events`/`switch` — `HIGHER_ORDER_SENTENCE_DESIGN.md`
§9 의 M3-1 로 이미 설계돼 있고 **판정 대기**다. 이번 기준으로 봐도 결론이 같다:
문장 자리(`do`)는 M1 로 이미 통일됐고, 남은 것은 **문장 원장(workflow) + 시간축(trigger)** 분리.
중복 판정하지 않는다. **다만 이번 감사가 더할 것 하나** — M3-1 의 판정 근거를
"계수가 얇다"로 미루지 말 것. 이 기준에서는 계수가 근거가 아니다.

---

## 5. A군 — 원자로 남길 것과 **왜 조합 불가인가**

| 군 | 예 | 조합 불가 사유 |
|---|---|---|
| **외부 API 캡슐** | legal · kosis · world_bank · company · stock · realty · paper · entity · researcher · book · performance · exhibit · stay · restaurant · commercial · contest · startup · weather · crypto · devdocs | 각각 **고유 인증·엔드포인트·응답 정규화**를 진다. 다른 어휘의 조합으로 그 API에 닿을 방법이 없다. `source`/`op` 축은 이미 도메인 *내부* 변종을 접었다 |
| **범용 획득** | `sense:crawl` · `sense:feed` · `sense:search` | 이미 통합의 *결과물*(feed←pew_research, search←5종) |
| **하드웨어 접촉** | browser · android · guestpc · screen · phone · here/see/listen | 프로토콜(CDP·ADB·헬퍼)·물리 센서. 소프트웨어 조합으로 대체 불가 |
| **파일 원자** | read · write · edit · list · grep · file_find · copy · move · delete | 이것들이 조합의 **재료**다 |
| **AI 호출 3축** | `self:ask`(원샷) · `others:delegate`(위임) · `others:ask`(이웃 몸) | 셋이 서로 다른 실행 주체·비용·동기성. 하나로 접으면 축이 사라진다 |
| **문법(table 14)** | filter · sort · take · select · dedup · groupby · join · union · merge · **each** · chart · spreadsheet · document · structure | **조합자 자체.** 분해 대상이 아니다 |
| **헌법 장치** | `self:propose_patch`(REPAIR) · `self:package` · `sense:self_check` · `self:script{run}` | 시스템이 자기를 고치는 통로. 빈도와 무관하게 가용해야 함 |

**특히 방어해야 할 것**: `self:script{run}` 과 `table:each`. 전자는 어휘 증식의 대안이고,
후자는 문형을 곱셈으로 바꾸는 유일한 고차 변환자다.

---

## 6. 앱 전용 어휘 — 별도 식별 (충족기준 ⑤)

**app: 블록 보유 35개** — 이 중 *앱 때문에 생긴/앱이 유일 소비자인* 것을 가른다.

**6-1. 앱이 유일 소비자에 가까운 것 (13)** — 계기 개편 없이는 은퇴 불가
`others:portal` · `showcase` · `family_news` · `bulletin` · `self:webapp` · `self:music` ·
`self:photo` · `self:health` · `self:finance` · `sense:cctv` · `limbs:cctv` · `self:cctv` ·
`limbs:launch`

**6-2. 앱은 얇은 뷰이고 능력이 독립인 것 (22)** — 앱과 무관하게 판정 가능
`sense:book` · `stock` · `realty` · `weather` · `restaurant` · `radio` · `performance` ·
`exhibit` · `stay` · `contest` · `startup` · `freelance` · `commercial` · `host` ·
`navigate_route` · `search_youtube` · `video` · `self:file_find` · `self:business` ·
`self:notebook` · `others:messages` · `others:feed`

**6-3. 프롬프트에서 이미 뺀 것 (2)** — `engines:icon`(앱 전용, `prompt_hidden`) ·
`engines:newspaper`(스위치화 완료)

> **원칙**: 앱 존재는 **사전 상주 근거가 아니다**(기존 합의). 그러나 앱 존재는
> **은퇴의 장애물**이다 — 6-1 은 낱말을 지우면 계기가 깨진다. 6-1 을 건드리려면
> 계기 개편이 선행돼야 하며, 이번 감사는 그 비용을 지불하라고 권하지 않는다.

---

## 7. 추가하면 복합어 N개를 지우는 보편 어휘 후보 (충족기준 ⑥)

> 원칙 4 재적용: **복합어 제거의 최선은 보편어 신설**이다(`pew_research`→`feed` 가 모범 —
> 사전 −1 +1 인데 차원은 늘었다).

| # | 신설 후보 | 지우는 것 | 순증감 | 신뢰도 |
|---|---|---|---:|---|
| **U1** | `[self:ledger]{store, op: query\|save\|delete, where, values}` | business·business_item·work_guideline·neighbor·contact·follow CRUD + local_save + local_query + 등기부 3형제 CRUD | **+1 / −9** | 높음 — 단일 DB·단일 매니저·3~8줄 통과함수 실측 |
| **U2** | (신설 없음) `[limbs:radio]{op: status\|volume\|favorite}` | player_status · volume · radio_favorite | **0 / −3** | **매우 높음** — desc 거짓말 2건 실측, 은퇴 선례 있음 |
| **U3** | `[others:surface]{op: list\|status}` (공통면만) | 없음(4종 유지) — 대신 "내 공개면 전부" 질의를 신설 | **+1 / 0** | 중 — 4-4 반론 수용한 축소판 |
| **U4** | `[sense:market]{kind: new\|used\|service, source}` | search_shopping · used · freelance | **+1 / −3** | 높음 — `search{source}` 선례 동형 |
| **U5** | (M3-1, 이미 설계) `workflow`=문장 원장 · `trigger`=시간축 | schedule · manage_events · switch 흡수 심사 | **0 / −1~3** | 판정 대기 |

**U3 부연** — 4-4 의 반론을 받아들인 결과다. 넷을 `kind` 로 접는 대신, 넷에 **공통으로
존재하는 것**(공개 주소를 가진 면이 지금 몇 개고 살아 있는가)만 보편어로 뽑는다.
`self:webapp{status}` 가 이미 하는 일과 겹치므로, 실은 **U1 이후 `webapp` 에 흡수**하는 것이
더 정직할 수 있다. 넷의 도메인 op 는 그대로 둔다.

**합계 전망**: U1+U2+U4 만 집행해도 **151 → 약 138** (신설 2, 은퇴 15).
카탈로그 상주 비용은 그보다 크게 준다(공개면을 건드리지 않아도 ~3,000자).

---

## 8. 헌법 정합 — 이 감사가 발견한 가장 중요한 것

`data/system_docs/ibl.md:85` **"명사의 자리"**(2026-08-06 부속 조항):

> 이 시스템이 하드코딩하는 명사는 **몸의 명사**뿐이다 — 6개 노드와 액션 어휘, 즉 *작용의 거처*.
> **세계의 명사** — 사람·장소·사물·관계 — 는 어떤 경우에도 코드·표준 쪽으로 넘어오지 않고,
> 오직 데이터에 **반증 가능한 퇴적물**로만 존재한다.
> (…) **명사에서는 몸이 표준이고 세계가 사전이다.**

**그런데 현재 어휘에는 세계의 명사가 낱말로 박혀 있다**: `business` · `business_item` ·
`business_document` · `work_guideline` · `neighbor` · `contact` · `follow` · `board` ·
`local`(save/query). 이것들은 작용의 거처가 아니라 **세계가 이런 곳이다라는 앎**이다.

조항은 2026-08-06에 선포됐고, 이 낱말들은 **2026-06-12에 이미 있었다**(CLAUDE.md 비즈니스
도메인 IBL화). 즉 **조항이 소급 적용된 적이 없다.** §4-2 의 U1 은 새 규칙의 발명이 아니라
**이미 선포된 조항의 미집행분 집행**이다.

조항이 함께 금지하는 "선행 명사 스키마"와도 충돌하지 않는다 — `store: "neighbor"` 의
`"neighbor"` 는 **Object Type 선언이 아니라 자유 문자열 라벨**이다. 조항의 표현대로
**"명사가 무료로 틀릴 수 있다"**. 반대로 §4-4 처럼 `kind` 마다 다른 op 표를 강제하는 통합은
조항이 금지하는 방향이라 **보류**로 판정했다.

---

## 9. 하지 않은 것 · 한계 (정직한 경계)

1. **삭제·코드 편집 0.** 어휘 정의 yaml 은 읽기만 했다. `backend_keeper_off` 표식이 이미 서 있고
   라이브 reload 자해를 피했다.
2. **개인 기억 원장은 U1 범위에서 제외했다** — `health`·`finance`·`memory`·`notebook`·`forage`·
   `blog` 는 각자 별 DB·별 색인·별 `ingest`(AI 구조화)를 가진다. 같은 "save/query" 모양이지만
   **저장소가 하나가 아니다**. business 6종처럼 단일 파일·단일 매니저라는 실측이 없어
   같은 등급으로 묶지 않았다. (`blog`→`notebook` 은 이미 사용자 기각.)
3. **`self:mkdir` 은 판정 보류.** §4 가 "write 가 부모 폴더를 자동 생성(실측)"이라 적었으나
   **이번 세션에서 그 경로를 직접 확인하지 못했다**(`file_ops.py` 의 write 본문 미확인).
   선행 실측 인용으로만 남기고 내 판정으로 승격하지 않는다.
4. **A군 104개를 개별 논증하지 않았다** — 군(群) 단위 사유로 묶었다. 개별 반증이 필요하면
   해당 군의 핸들러를 여는 것이 절차다(원칙 2).
5. **조합 지표 재수집이 선행돼야 한다.** §0-1 의 페어링 수리 이후 데이터로 다시 재야
   `vocab_composition_metrics.py` 의 파이프·파트너 수치가 의미를 갖는다. 현재 수치는
   **하한선**으로만 읽을 것.

---

## 10. 다음 세션 착수 순서 (제안)

1. **U2 (재생기 3형제)** — 신설 0·−3, desc 거짓말 실측 완료. 가장 싸고 확실.
2. **U4 (상거래 3형제)** — `search{source}` 선례 동형. 통화 필드 호환 실측 완료.
3. **U1 (세계-명사 CRUD)** — 헌법 집행. business 6종부터(단일 DB 실측). 앱 계기
   (`self:business` app 블록) 동반 개편 필요 — 비용 산정 먼저.
4. **조합 지표 재수집** — 페어링 수리 후 데이터로 §6 네 지표 재측정.
5. **U5 / M3-1** — 사용자 판정 대기 유지.

> 전부 **판정 대기**다. 이 문서는 조사·설계까지이며, 어느 항목도 집행하지 않았다.
