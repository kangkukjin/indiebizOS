# 어휘 분해가능성 감사 — 2라운드 (2026-08-15, 149 액션 시점)

> 1라운드(`VOCAB_DECOMPOSABILITY_AUDIT.md`, 151 시점) 이후 변화분을 반영한 **재판정**이다.
> 판정 기준에서 사용빈도·사용계수·코퍼스 4지표를 **결론의 근거로 쓰지 않는다** — 인용하더라도
> '어디가 아픈지 가리키는 표지'로만. 어휘 정의(`data/ibl_nodes_src/*.yaml`)·backend 파일은
> **한 줄도 수정하지 않았다**(작업 트리 clean 확인). 산출은 이 보고서뿐이다.

---

## 1. 실측 확정과 문서 불일치

```
$ python3 scripts/build_ibl_nodes.py --check
[build_ibl_nodes] 노드 6개, 액션 149개, 패키지 fragment 53개(+121 액션)
… 전 가드 통과 ✓ (바이트·tool.json·fixture·enum·포크·OS·launcher·교재·뷰 일치)
```

| 노드 | 액션 | op분기 | app블록 | prompt_hidden |
|---|---:|---:|---:|---:|
| sense | 42 | 17 | 18 | 0 |
| self | 52 | 29 | 9 | 0 |
| limbs | 14 | 9 | 1 | 0 |
| others | 18 | 12 | 6 | 0 |
| engines | 9 | 3 | 1 | 2 |
| table | 14 | 0 | 0 | 0 |
| **계** | **149** | **70** | **35** | **2** |

**문서 표기 불일치 (실측 기준)**

| 출처 | 표기 | 판정 |
|---|---|---|
| 빌드 실측 | **149** (42·52·14·18·9·14) | 정본 |
| `CLAUDE.md` | 149 | 총계 일치 ✓ |
| `data/system_docs/system_structure.md` | **150** (43·49·18·18·9·13) | **총계 −1 오차이나 노드별로는 6개 중 4개가 틀림** — sense +1, self −3, limbs +4, table −1 이 서로 상쇄돼 총계만 근접해 보인다 |

총계가 비슷해 보여 넘어가기 쉬우나, `system_structure.md` 의 노드 분포는 **limbs 18(실제 14)**
처럼 크게 어긋난다. 이 파일은 의식·실행·평가 에이전트에 **항상 주입**되므로, 시스템이 자기
몸의 크기를 틀리게 아는 상태다. (1라운드가 지적한 "자기상도 임시적 명사"의 재발.)

---

## 2. 1라운드 이후 변화분 — 그리고 그것이 가르친 것

| 커밋 | 변화 | 액션 |
|---|---|---:|
| `dc38fb0` | `[table:each]` 신설 + 문장 자리 `do` 통일 | 150→151 |
| `6f86a89` | 병렬 도구 호출 페어링 id 기반 + 증류 success 게이트 복구 | — |
| `10dd650` | 1라운드 보고서 커밋 | — |
| `f2b39a3` | **라디오 재생 제어 흡수** — `player_status`·`volume` 은퇴 | 151→**149** |
| `8e5874b` | 조합성 4지표 기준선 고정 | — |

1라운드의 U2 제안이 집행됐다. **다만 제안대로가 아니라 한 항목이 잘려 나갔고, 그 잘림이
이번 라운드의 핵심 판정 도구가 됐다.**

- 제안: `player_status` · `volume` · `radio_favorite` 셋을 `[limbs:radio]{op}` 로 흡수 (−3)
- 집행: 앞의 둘만 흡수 (−2). `radio_favorite` 는 **접지 않음**
- 사용자 사유: *"즐겨찾기=원장 CRUD 라 재생 제어와 `op` 축의 의미가 다르다 —
  **한 축이 두 개념을 나르면 안 된다**"*

결과 실측: `limbs:radio` ops = `play·stop·status·volume` (재생 제어 한 개념) /
`limbs:radio_favorite` ops = `list·add·remove` (원장 한 개념). 축이 깨끗하게 갈렸다.

> **이 판정에서 도출되는 규칙 — 이번 라운드의 주 렌즈**:
> **op 축은 개념의 단위이지 액션의 수납장이 아니다.** 한 액션의 op 목록이 두 개 이상의
> 개념(조회 / 원장 CRUD / 작업 / 화면)을 나르고 있으면, 그 액션은 이미 복합어다 —
> 이름이 하나라서 안 보일 뿐이다. 이 렌즈는 사용빈도와 무관한 **순수 구조 판정**이다.

---

## 3. 새 판정 — 축 혼재 (Axis Conflation)

1라운드는 *이름이 여럿인데 개념이 하나*인 것(명사 복합어)을 찾았다. 이번엔 반대 방향 —
*이름이 하나인데 개념이 여럿*인 것을 찾는다. 둘 다 같은 병의 양면이다.

### 3-1. 축 혼재 목록 (op 목록 실측 + 핸들러 디스패처 대조)

| 액션 | op수 | 섞인 개념 | 심각도 |
|---|---:|---|---|
| **`self:music`** | 14 | ①조회 `library·track·folders` ②플레이리스트 원장 `playlist_*` 6개 ③소스 원장 `sources·add_source·remove_source` ④작업 `scan·stop` | **최악 — 4개념/1축** |
| **`others:portal`** | 12 | ①포털 원장 `portals·create·remove` ②회원 CRM `members·join·promote·issue·revoke` ③진열 다이얼 `display` ④감사 `audit` ⑤설정 `config` | 4~5개념 |
| **`others:showcase`** | 10 | ①폴더 원장 `add·remove·detail` ②바스켓 원장 `basket_*` 5개 | **원장 2개/1축** |
| **`others:family_news`** | 10 | ①발행 `create·publish` ②초안 편집 `photos·remove_photo` ③수신함 `comments·uploads` | 3개념 |
| `self:trigger` | 9 | CRUD + 상태 토글 `enable·disable` + 이력 `history` | 3개념 |
| `self:notebook` | 8 | 노트북 원장 + 소스 원장 `add·sources·remove` + 질의 `ask·search` | 3개념 |
| `limbs:music` | 8 | 재생 제어 + 파일 획득 `download` + 스트림 해소 `relay` | 3개념 |
| **`sense:video`** | 7 | ①동영상 데이터 `info·transcript·languages·summarize` ②**yttv 앱 화면** `feed·watch·history` | 2개념(§6 참조) |
| `others:bulletin` | 7 | 게시판 원장 + 글 모더레이션 `post_delete` + 포털 연결 `portals` | 3개념 |
| `self:blog` | 7 | 조회 `posts·latest` + 검색 + 색인 관리 `rebuild_index` + vault 운영 | 3개념 |
| `others:neighbor` | 6 | CRUD + `favorite` + `merge` | 3개념 |
| `self:business_document` | 5 | CRUD + `regenerate`(AI) + `publish`(Nostr) | 3개념 |
| `self:finance` | 5 | CRUD + `ingest`(AI 구조화) + `sync`(폰 수거) | 3개념 |

### 3-2. 왜 이것이 "조합을 못 보게" 만드는가

축이 섞이면 **op 이름이 그 액션 안에서만 뜻을 가진다.** `self:music{op:"sources"}` 의
`sources` 와 `self:notebook{op:"sources"}` 의 `sources` 는 철자가 같지만 전이되지 않는다 —
전자는 스캔 대상 폴더 목록, 후자는 노트북에 넣은 문서 목록이다. AI 입장에서 이것은
**액션마다 따로 외워야 하는 관용구**이고, 관용구는 조합되지 않는다. 이것이 복합어가
"스위치처럼" 쓰이는 구조적 이유다 — 빈도가 원인이 아니라 결과다.

---

## 4. 대체 IBL 문장 — 실제로 써 본 것과 못 써 본 것

### 4-1. 라이브 실행으로 검증한 것 ✅

**(a) 전 변환자는 리터럴 `items` 로 씨앗을 받는다 — 문서에 없던 사실**

```ibl
[table:take]{n: 2, items: [{"title":"가","price":300},{"title":"나","price":100},{"title":"다","price":200}]}
→ {"items":[{가,300},{나,100}],"count":2,"success":true}          ✅ 실행 성공

[table:filter]{where: {field:"price", op:"lt", value:250}, items: [{가,300},{나,100}]}
→ {"items":[{"title":"나","price":100}],"count":1,"success":true}  ✅ 실행 성공
```

즉 **파이프의 첫 칸에 데이터를 직접 놓을 수 있다.** 이것은 어느 문서에도 안 적혀 있고
어느 desc 도 초대하지 않는다. 사실상 숨은 기능이다.

**(b) 그런데 `table:each` 만 이 씨앗을 거부한다 — 대칭 결함**

```ibl
[table:each]{items: [{"city":"서울"},{"city":"부산"}], do: "[sense:weather]{city:'$it.city'}"}
→ success:false  "each: 입력에서 items 통화를 찾지 못했습니다. 받은 봉투: str"   ❌ 실행 실패
```

**(c) 우회는 된다 — 그러나 이름이 거짓말을 한다**

```ibl
[table:take]{n: 2, items: [{"city":"서울"},{"city":"부산"}]}
  >> [table:each]{do: "[sense:weather]{city: '$it.city'}", limit: 2}
→ ok_count:2  서울 24.8℃ / 부산 25.7℃ 실제 회수                    ✅ 실행 성공 (11.5초)
```

리터럴 생성자가 **`[table:take]`("상위 n개만") 라는 이름 아래 숨어 있다.** AI 가 "목록을
만들어라"를 표현하려 할 때 `take` 를 떠올릴 이유가 없다. **능력은 있는데 이름이 없다** —
이것이 사용자가 말한 "나쁜 언어"의 정확한 형태다(단어가 많아서가 아니라, 있는 능력에
부를 이름이 없어서 조합이 안 보인다).

### 4-2. 축 분리 제안 — 문장은 썼으나 미실행(대상 어휘 부재)

**`self:music` 4개념 분해** — 원장 축을 빼내면 조회 축이 깨끗해진다.

```ibl
# 현재 (한 축에 4개념)
[self:music]{op: "playlist_add", name: "드라이브", path: "..."}
[self:music]{op: "add_source", folder: "/Volumes/MUSIC"}
[self:music]{op: "scan"}

# 제안 — 원장은 원장 어휘로, 조회는 조회로, 작업은 작업으로
[self:ledger]{store: "playlist", op: "save", values: {name: "드라이브", path: "..."}}
[self:ledger]{store: "music_source", op: "save", values: {folder: "/Volumes/MUSIC"}}
[self:music]{op: "scan"}                       # 작업만 남는다
[self:music]{op: "library", q: "김광석"}         # 조회만 남는다
```

**`sense:video` 2개념 분해** — 앱 화면 op 를 데이터 능력에서 뗀다.

```ibl
# 현재 — 데이터 능력과 yttv 앱 화면이 한 축에
[sense:video]{op: "transcript", video_id: "..."}   # 데이터 능력
[sense:video]{op: "feed"}                          # 앱 화면 (계기 3탭 전용)

# 제안 — 앱 화면 3 op 는 prompt_hidden 축으로 분리하거나 계기 선언으로 내림
[sense:video]{op: "transcript", video_id: "..."}   # 사전에 남는 것
# feed·watch·history → 계기(app: 블록)가 직접 쥐고 사전에서는 퇴거
```

**공개면 원장 CRUD** — 1라운드 U1 의 연장. 원장 op 만 걷어내고 도메인 능력은 남긴다.

```ibl
# 현재
[others:showcase]{op: "basket_save", basket_id: "...", title: "가족"}
[others:neighbor]{op: "save", name: "김씨", level: 2}
[limbs:radio_favorite]{op: "add", station_id: "kbs_coolfm"}

# 제안 — 명사를 자유 데이터 라벨로 (헌법 "명사의 자리" 소급 적용)
[self:ledger]{store: "showcase_basket", op: "save", values: {id: "...", title: "가족"}}
[self:ledger]{store: "neighbor", op: "save", values: {name: "김씨", level: 2}}
[self:ledger]{store: "radio_favorite", op: "save", values: {station_id: "kbs_coolfm"}}
```

`radio_favorite` 가 여기 들어오는 것이 중요하다 — 사용자가 재생 축에서 **잘라낸** 바로 그
이유(원장 CRUD)가, 그것이 **원장 어휘에 속한다**는 뜻이기 때문이다. 1라운드 U2 의 잘림은
제안의 실패가 아니라 **행선지가 U1 이었다**는 정정이다.

### 4-3. 대체 불가 — 원자로 남길 것

| 군 | 조합 불가 사유 |
|---|---|
| 외부 API 캡슐 (legal·kosis·world_bank·company·stock·realty·paper·entity·researcher·book·performance·exhibit·stay·restaurant·commercial·weather·crypto·devdocs·contest·startup) | 고유 인증·엔드포인트·응답 정규화. 다른 어휘 조합으로 그 API 에 닿을 경로가 없다 |
| 범용 획득 (crawl·feed·search) | 이미 통합의 *결과물*(feed←pew_research, search←5종) |
| 하드웨어 접촉 (browser·android·guestpc·screen·phone·here·see·listen) | 프로토콜(CDP·ADB·헬퍼)·물리 센서 |
| 파일 원자 (read·write·edit·list·grep·file_find·copy·move·delete) | 조합의 **재료** |
| AI 호출 3축 (`self:ask`·`others:delegate`·`others:ask`) | 실행 주체·비용·동기성이 서로 다름. 접으면 축이 사라진다 |
| table 14 | **조합자 자체** — 분해 대상이 아니라 분해의 도구 |
| 헌법 장치 (`propose_patch`·`package`·`self_check`·`script{run}`) | 시스템이 자기를 고치는 통로 |

---

## 5. 더해야 할 보편 원시 어휘 (충족기준 4)

> 원칙: **복합어 제거의 최선은 보편어 신설**(`pew_research`→`feed` 가 모범 — 사전 −1 +1 인데
> 차원은 늘었다). 아래는 순증 1 이하로 여러 복합어를 지우거나, 없어서 못 하던 것을 여는 것만.

### P1. `table:each` 의 `items` 씨앗 — **신설 0, 대칭 수리** (최우선)

§4-1 실측: 전 변환자가 리터럴 씨앗을 받는데 `each` 만 거부한다. `each` 는 **문형을 곱셈으로
바꾸는 유일한 고차 변환자**인데, 정작 씨앗을 못 받아 항상 앞에 생산자가 필요하다.
한 줄 대칭 수리로 "AI 가 스스로 만든 목록에 문장을 적용"이 열린다.

```ibl
[table:each]{items: [{url:"a"},{url:"b"},{url:"c"}], do: "[sense:crawl]{url:'$it.url'}"}
  >> [table:document]{title: "세 곳 브리핑"}
```
비용 최소·효과 최대. **1순위 권고.**

### P2. `[table:of]{items}` — 리터럴 생성자에 **이름을 준다** (신설 1)

능력은 이미 있다(§4-1). 없는 것은 **이름**이다. `take` 라는 이름 아래 숨은 기능을 AI 가
발견할 경로가 없다. P1 을 하면 `each` 한정으로는 해결되지만, `filter`·`sort`·`groupby`
앞에 데이터를 놓는 일반형은 여전히 이름이 없다.

> 반론(적어 둔다): 순수 별칭이라 어휘만 늘고 능력은 안 는다는 반박이 가능하다.
> 그러나 이 언어의 병목은 능력이 아니라 **명명**이라는 것이 §4-1 의 실측이다.
> P1 만 먼저 하고 P2 는 관찰 후 판정해도 된다.

### P3. `[self:ledger]{store, op: query|save|delete, where, values}` (신설 1, 다수 흡수)

1라운드 U1 의 계승. 이번 라운드가 더하는 근거는 두 가지다 —
①`radio_favorite` 의 잘림이 "원장은 원장끼리"라는 사용자 판정을 명시적으로 만들었고,
②§3 축 혼재 목록의 **13개 중 9개가 원장 CRUD 를 다른 개념과 섞고 있다**.
ledger 가 생기면 그 9개의 축이 자동으로 깨끗해진다(어휘를 지우지 않고도 축이 정리된다).

### P4. `table:derive` — 행 단위 필드 계산 (신설 1)

§4 실측에서 드러난 빈칸: `select` 는 투영, `groupby` 는 집계, `each` 는 IBL 실행.
**행마다 값을 계산해 새 필드를 만드는 것**만 없다(예: 가격을 만원 단위로, 제목+채널 결합).
지금은 `each` 로 IBL 문장을 돌려야 하는데 이는 limit 20·외부 호출 위험을 동반한다 —
순수 산술에 고차 실행기를 쓰는 셈이다.

```ibl
[sense:used]{q:"자전거"} >> [table:derive]{field: "만원", expr: "price / 10000"}
  >> [table:sort]{by: "만원"}
```

### P5. 재생 상태 보고 — 라디오 흡수가 남긴 갭 (판정 필요)

`f2b39a3` 이 남긴 기록: *"로컬 음악 재생 상태는 표면 `<audio>` 가 쥐어 보고할 액션이 없다."*
`limbs:radio{op:status}` 는 서버가 mpv 를 쥐어서 가능하지만, `self:music` 은 표면이 재생을
쥐므로 서버가 모른다. **이것은 어휘 부재가 아니라 아키텍처 비대칭**이라 새 낱말로 못 푼다.
적어만 두고 신설을 권하지 않는다.

---

## 6. 앱·계기 전용 어휘 — 별도 식별 (충족기준 5)

**`prompt_hidden: true` = 2** — 이미 사전에서 퇴거한 것
- `engines:icon` (🎨 아이콘 계기 전용, 폰-직결)
- `engines:newspaper` (신문 계기 발행 버튼 전용)

**app: 블록 보유 = 35.** 그중 성격을 셋으로 가른다.

| 구분 | 수 | 예 | 판정 |
|---|---:|---|---|
| **앱이 유일 소비자** (계기 없으면 존재 이유가 흐릿) | 13 | `others:portal`·`showcase`·`family_news`·`bulletin` · `self:webapp`·`music`·`photo`·`health`·`finance` · `sense:cctv`·`limbs:cctv`·`self:cctv` · `limbs:launch` | 낱말을 지우면 계기가 깨진다 — **계기 개편 선행 필요**. 이번 라운드도 집행 권고하지 않음 |
| **앱은 얇은 뷰, 능력은 독립** | 22 | `sense:book`·`stock`·`realty`·`weather`·`restaurant`·`radio`·`performance`·`exhibit`·`stay`·`contest`·`startup`·`freelance`·`commercial`·`host`·`navigate_route`·`search_youtube`·`video`·`self:file_find`·`business`·`notebook`·`others:messages`·`feed` | 앱과 무관하게 판정 가능 |
| **한 액션 안에 앱 전용 op 가 섞인 것** | — | **`sense:video{feed·watch·history}`** = yttv 계기 3탭 전용 | §3 축 혼재의 특수형. 데이터 능력(`info`·`transcript`)과 분리 대상 |

> 마지막 줄이 이번 라운드의 새 식별이다. 지금까지 앱 전용 어휘는 **액션 단위**로만 셌는데,
> 실제로는 **op 단위로 스며든 것**이 있다. `prompt_hidden` 은 액션 전체에만 걸리므로
> `sense:video` 는 앱 op 를 데리고 사전에 상주한다.

---

## 7. 계수·지표를 쓰지 않았음 (충족기준 6)

이 보고서의 어떤 판정도 사용빈도·사용계수·코퍼스 4지표(파이프 길이·미조합 수·문형 수·
파트너 다양성)를 **근거로 삼지 않았다.** 판정 근거는 전부 다음 넷이다 —
①핸들러 디스패처 실측 ②op 목록의 개념 수 ③라이브 실행 결과 ④헌법 조항("명사의 자리").

지표를 언급한 곳은 §5-P4(빈칸 지목)뿐이며 그것도 "어디를 볼지"의 표지였다.

> 덧붙임 — 1라운드가 지적한 계수 오염(자가점검 순찰 ~55% + 병렬 페어링 유실)은
> `6f86a89` 로 후자가 수리됐다. 그러나 **수리는 앞으로의 데이터만 고친다** — 축적된
> 코퍼스는 여전히 오염된 구간을 품고 있다. 재수집 전까지 4지표는 하한선으로만 읽어야 한다.
> 이는 계수를 근거로 쓰지 말아야 할 이유를 하나 더한다.

---

## 8. 하지 않은 것 · 한계

1. **어휘 정의·backend 무수정.** `git status` clean 확인, 이 보고서 파일만 추가.
2. **축 혼재 13건 중 핸들러를 직접 연 것은 4건**(`self:music`·`sense:video`·`business` 7종·
   `radio`). 나머지 9건은 op 목록과 desc 로 판정했다 — 개별 반증이 필요하면 핸들러를
   여는 것이 절차다(원칙 2).
3. **개인 기억 원장(`health`·`finance`·`memory`·`notebook`·`forage`·`blog`)은 P3 범위에서
   제외.** 각자 별 DB·별 색인·별 `ingest`(AI 구조화)를 가져, `business.db` 처럼 단일 파일·
   단일 매니저라는 실측이 없다. 축 혼재 목록에는 올렸으나 흡수 대상으로 올리지 않았다.
4. **P4 `table:derive` 의 `expr` 문법을 설계하지 않았다.** 안전한 식 평가(샌드박스)가
   선행 과제이며, 그 설계 없이 착수하면 `_execute_condition` 계열의 침묵 실패를 재생산한다.
5. **`self:mkdir` 은 2라운드에서도 판정 보류** — `write` 의 부모 폴더 자동 생성 경로를
   이번에도 직접 확인하지 못했다. 선행 실측 인용으로만 남긴다.

---

## 9. 착수 순서 제안 (전부 판정 대기)

1. **P1 — `each` 의 `items` 씨앗 대칭 수리.** 신설 0, 위험 최소, 문형 즉시 확장.
2. **`system_structure.md` 노드 분포 정정.** 시스템이 자기 몸 크기를 틀리게 알고 있다.
3. **`sense:video` 앱 op 분리.** 축 혼재 중 가장 경계가 뚜렷하다.
4. **P3 `self:ledger`.** 헌법 집행 + 축 혼재 9건 동시 정리. 계기 개편 비용 산정 선행.
5. **P2·P4** — P1 이후 관찰하고 판정.

> 이 문서는 조사·설계까지다. 어느 항목도 집행하지 않았다.
