# IBL 설명서 (IndieBiz Logic)

> 현재 상태 기준: **142 액션 / 5 노드** · op 분기 57 · 앱 계기 26 · 통화 변환자 9 · 연산자 3 (2026-06-26 실측)
> 유지보수·건강점검은 [IBL_MAINTENANCE_MANUAL.md](IBL_MAINTENANCE_MANUAL.md) 참조.

---

## 1. IBL이란 무엇인가

IBL은 indiebizOS의 **신경계** — 모든 정보 소스(웹·파일·기기·사람·외부 API)를 **단일 어휘**로 접근하는 *정보 흐름 추상화 언어*다.

도구가 100개든 1000개든 제각각 이름이면 AI가 일관되게 못 쓴다. IBL은 그 폭증을 **언어로** 푼다 — 적은 수의 직교적 명사·동사로, 안 본 조합도 추론해 쓰게 한다. AI는 도구 목록을 외우는 게 아니라 **문법을 안다**.

핵심 성질 세 가지:
- **조합성**: 액션 출력이 표준 통화(records/table)라 `>>`로 다음 액션에 흐른다. 명사 N개 × 동사 M개 → N×M개 행동.
- **추상화**: 같은 어휘가 HTTP·SQLite·ADB·파일·CDP 등 프로토콜 차이를 가린다(드라이버 계층).
- **다표면**: 같은 어휘 하나가 자율주행·수동·앱 세 표면에서 동시에 쓰인다(아래 §7).

---

## 2. 문법

### 기본형
```
[node:action]{params}
```
- 모든 값은 `{key: val}` named parameter. `(target)` 옛 문법은 폐지(에러).
- 예: `[self:time]` · `[sense:stock]{op: "quote", ticker: "005930"}` · `[sense:weather]{city: "수원"}`

### op 분기 (한 액션 안의 변형)
빈번한 변형은 새 액션이 아니라 `op` 파라미터로 가지친다(현재 **57개** 액션이 op 보유).
```
[sense:realty]{op: "query", source: "molit", region: "강남구"}   # 실거래가
[sense:realty]{op: "query", source: "zigbang", region: "평택 죽백동"}  # 현재 매물
```

### 연산자 — 다중 스텝
| 연산자 | 이름 | 의미 | 예 |
|---|---|---|---|
| `>>` | Sequential | 앞 결과를 뒤로 자동 전달 | `[sense:search_gnews]{query:"경제"} >> [table:take]{n:3}` |
| `&` | Parallel | 병렬 실행, 결과 결합 | `[sense:weather]{city:"서울"} & [sense:stock]{op:"quote",ticker:"AAPL"}` |
| `??` | Fallback | 실패 시 대안 | `[sense:stock]{op:"quote",ticker:"AAPL"} ?? [sense:stock]{op:"info",ticker:"AAPL"}` |

※ `$prev`·`$result` 같은 변수 참조 문법은 없다 — `>>`가 이전 결과를 알아서 넘긴다.

---

## 3. 5개 노드 (어휘의 갈래)

인간 인지를 본뜬 다섯 갈래. 오직 이 노드만 존재한다.

| 노드 | 은유 | 무엇 | 액션 수 |
|---|---|---|---|
| **sense** | 감각 | 외부 정보 수집·질의 (주가·날씨·뉴스·학술·부동산·법률·미디어·세계상태) | 44 |
| **self** | 내부 | 개인 정보·시스템 관리 (파일·메모리·건강·사진·일정·워크플로우·설정) | 44 |
| **limbs** | 수족 | 작업 도구·기기 제어 (브라우저·데스크톱·음악/라디오/유튜브 재생·CCTV·폰) | 17 |
| **others** | 타자 | 외부 에이전트·사람과의 소통 (위임·메시징·이메일/Nostr·연락처·커뮤니티) | 11 |
| **engines** | 작업장 | 콘텐츠 생성·변환 (신문·슬라이드·영상·차트·문서·웹사이트 + 통화 변환자) | 26 |

대표 액션 맛보기:
- sense: `stock` `weather` `search_naver` `search_gnews` `paper` `legal` `realty` `kosis` `world_bank` `restaurant` `travel` `radio` `cctv`
- self: `read` `write` `grep` `file_find` `memory` `health` `photo` `manage_events` `workflow` `forage` `notify_user`
- limbs: `browser` `screen` `android` `phone` `music` `radio` `os_open` `show_map`
- others: `messages` `channel_send` `neighbor` `delegate` `feed` `auto_response`
- engines: `slide` `document` `chart` `spreadsheet` `newspaper` `tts` `image_gemini` `web`

---

## 4. 통화 (Currency) — 조합의 핵심

IBL의 정체성은 "**표준 통화가 `>>`로 흐른다**"이다. 두 통화:

- **`records`** = `[{title, meta, summary, url, image?}]` — 목록형(검색 결과·매물·논문·뉴스…). filter/take/document/newspaper로 흐름.
- **`table`** = `{columns, rows}` — 수치/시계열(통계·재무·세계지표…). chart/spreadsheet/groupby로 흐름.

액션은 성격에 맞는 통화를 낸다(목록→records, 수치→table). 통화를 말하지 않는 것: 단건 시세(스칼라)·작동기(limbs)·복합 스냅샷 등.

### 통화 변환자 9종 (engines, transform 그룹)
통화→통화로 변환하는 "동사". 파이프의 깊이를 만든다.

| 변환자 | 하는 일 |
|---|---|
| `filter` | 조건에 맞는 것만 (부분집합) |
| `sort` | 기준 필드로 정렬 |
| `take` | 상위 n개 (음수면 뒤에서) |
| `select` | 지정 열/필드만 (투영) |
| `dedup` | 중복 제거 |
| `groupby` | 키로 그룹지어 집계 (count/sum/avg/min/max) |
| `join` | 두 입력을 공통 키로 inner join |
| `union` | 두 표/목록 행 결합 |
| `merge` | 두 records 합치기 |

예: `[sense:search_naver]{query:"AI"} >> [table:filter]{where:"title != "} >> [table:take]{n:3}`

---

## 5. 구조적 특징

### 라우터 — 액션이 어떻게 실행되나
| 라우터 | 수 | 무엇 |
|---|---|---|
| `handler` | 118 | 패키지 핸들러 함수 직접 호출 (대다수) |
| `system` | 14 | 시스템 내장 동작 |
| `channel_engine` | 5 | 메시징/채널 추상화 |
| `driver` | 2 | 프로토콜 드라이버 (HTTP/WS/ADB/CDP/SQLite/File) |
| `workflow_engine` | 2 | 워크플로우 오케스트레이션 |
| `trigger_engine` | 1 | 트리거 등록 |

### runs_on — 어디서 도나 (몸 인식)
| 값 | 수 | 의미 |
|---|---|---|
| `anywhere` | 107 | 이식 가능 (맥·폰 어디서나) |
| `mac_only` | 31 | 집 PC 하드웨어·무거운 의존 → 폰에선 맥에 단건 위임 |
| `phone_only` | 4 | 폰 하드웨어 전용 (위치/마이크/카메라/알림) |

폰에서 못 도는 액션은 거부되지 않고 **분산 IBL**로 신뢰 노드(맥)에 위임된다. 혼합 파이프도 leaf별로 쪼개져 일부는 폰·일부는 맥에서 돌고 결과가 한 봉투로 결합된다.

### postprocess
액션 결과를 후처리하는 선택 필드. 현재 사용 0 — 압축은 통화를 파괴하므로 폐지됨. 메커니즘은 통화-안전형(지정 텍스트 필드만 압축, records/table 보존)으로만 남아 있다.

---

## 6. 앱 표면 노출 (app 계기)

액션 정의에 `app:` 블록을 달면 그 액션이 **앱 모드 GUI 계기**로 자동 등장한다(현재 **26개**). 코드가 아니라 *선언*이다 — `app:` 하나가 데스크탑·원격·폰 표면에 동시에 렌더된다. 렌더 어휘: metric·kv·kv_list·card_list·image_grid·map·thread·compose·form·editable_list 등.

예: 날씨·맛집·투자·도서·부동산·CCTV·길찾기·여행·시스템상태·메신저·사진 등이 아이콘 GUI로.

---

## 7. 세 표면 (같은 어휘, 세 가지 사용법)

IBL 위에 런처 3표면이 트릴레마({속도·표현력·주권} 중 둘)를 이룬다:

1. **자율주행** — 의도 → AI 다단계 인지(분류→의식→실행→평가). 표현력·주권, 느림.
2. **수동** — 경량모델이 자연어→IBL 번역 → dry-run 검수 → 실행. 컴파일러 프론트엔드.
3. **앱** — 아이콘 GUI로 직접 조작(`app:` 계기). 0토큰, 빠름·주권, 표현력 낮음.

빈도가 작업을 자율주행 → 수동 → 앱으로 **결정화**한다.

---

## 8. 빌드·학습 인프라

- **단일 진실 소스**: `data/ibl_nodes_src/*.yaml`(6파일) → `build_ibl_nodes.py` → 단일 `data/ibl_nodes.yaml`. 런타임은 단일 파일만 읽음.
- **삼각 검증**: `build_ibl_nodes.py --check` 가 src ↔ tool.json ↔ handler `_OP_DISPATCHERS` 를 AST로 정확 비교 + op enum + 코퍼스 param + app 블록 + runs_on/폰 매니페스트 + 변환자 계약. pre-commit + self-check에 합류.
- **해마(실행기억)**: fine-tuned 임베딩(768차원)으로 "사용자 자연어 → 과거 IBL 용례" 시맨틱 연상. 성공 실행을 자동 증류해 코퍼스 축적(파이썬이 인터넷서 공짜로 얻는 설명-코드 쌍을, IBL은 자력 조달).
- **프롬프트 비용**: 액션의 `description` + `ops.values`만 프롬프트에 실림(target/impl/keywords는 UI 전용).

---

## 9. 설계 원칙 (헌법)

- **명명 헌법**: ①빈도-길이 반비례(자주 쓰는 건 짧게) ②변형은 op로 ③한 단어=한 개념 + land-grab 금지.
- **어휘 vs 가이드**: 작업들이 *한 통화를 공유*하면 어휘(op 분기), *제각각*이면 가이드 파일(예: Cloudflare). → [IBL_MAINTENANCE_MANUAL.md] 및 설계철학 문서.
- **IBL 우선**: 새 기능은 IBL 패턴으로 추상화. 전문 데이터 액션이 있으면 파일 직접 탐색보다 우선.
- **실행까지**: 계획만 하지 말고 `execute_ibl`로 실행 완료. IBL 코드는 텍스트 응답에 넣지 말고 도구로만 실행.

---

## 10. 한눈 요약

| 항목 | 현재 |
|---|---|
| 노드 | 5 (sense 44 · self 44 · limbs 17 · others 11 · engines 26) |
| 총 액션 | 142 |
| op 분기 액션 | 57 |
| 앱 계기 | 26 |
| 통화 변환자 | 9 |
| 연산자 | 3 (`>>` `&` `??`) |
| 통화 | records · table |
| 실행 환경 | anywhere 107 · mac_only 31 · phone_only 4 |
| 표면 | 자율주행 · 수동 · 앱 |
| 구조 건강(2026-06-26) | ✅ (정적·통화·문법 GREEN — `scripts/ibl_health_check.py`) |
