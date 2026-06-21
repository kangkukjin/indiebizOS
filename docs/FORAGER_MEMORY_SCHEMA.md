# 개인-forager 메모리 스키마 — 설계 결정화 (v1, 2026-06-20)

*성격: **연구→설계 이행의 산출물.** 연구 종합·논증·실증은 `FILE_FORAGING_RESEARCH.md`(§0~13), 항해도는 `FILE_FORAGING_HANDOFF.md`. 이 문서는 그 핸드오프 §2(A~F)를 **field 수준의 결정된 스키마 + 거처·물질화·생명주기 결정**으로 못박는다. 아직 코드 아님 — "가장 얇은 첫 구현"의 청사진.*

> 한 줄: **forager는 AI다. 우리가 짓는 건 그 AI가 결여한 *지속 기억*뿐** — 2층(몸별 지도 + 몸독립 주인모델), 각 항목은 폐기가능(defeasible)·출처구속(provenance)·종류태그(구조/의미). 누적엔 반대힘(surface)을 짝짓는다.

---

## 0. 이미 있는 것 (재발명 금지) — 스키마는 *확장*이지 신축이 아니다

설계 전에 코드를 읽어 확인한, 이 스키마가 **올라탈 기존 자산**:

| 자산 | 현 상태 | 이 스키마에서의 역할 |
|---|---|---|
| **`[self:folder_note]{op:set/get}`** (self.yaml:585, pc-manager) | 폴더 의미 주석 set/get. **그러나** ① root_path(스캔 볼륨)에 묶임 — 은퇴 예정 storage_db(HANDOFF task#7) ② 평탄(provenance·confidence·종류태그·defeasible 전부 없음) ③ 수동(사람이 set) | **몸별 지도(1층)의 원시 종자.** 이 액션을 *부유화*(필드 추가)하고 저장소를 storage_db→forager 저장소로 이관. |
| **싼 탐침 IBL** `self:fs_query`·`self:grep`·`self:find`·`self:read`·`self:storage` | 전부 존재. file_index.py 보편 색인 위. F1(몸 갭) 대부분 해소 | **probe 계약** — forager가 이미 쓰는 손. 새 동사 불요. |
| **해마**(`ibl_usage.db`) + **심층메모리**(per-agent `memory.db`) | 증류(입력)+정리(위생)+lazy freshness(`last_seen` 노출, 손튜닝 감쇠 안 함) 패턴 완성 | **생명주기의 청사진.** forager 기억은 이 두 기억의 *공간판*. 패턴 그대로 상속(§4). |
| **일화기억**(`world_pulse.db:episode_log/summary`) + **사용자 프로파일**(`my_profile.txt`, 심층메모리) | 존재 | **주인모델(2층)의 join 원천**(§1.4 개인 prior). |

**결정 0**: 새 메모리 종(種)을 *0부터* 짓지 않는다. `folder_note`를 부유화하고, 해마/심층메모리의 증류·정리·lazy-freshness 배관을 *공간*에 재사용한다. 이는 헌법 [[architecture_body_vs_absorbable]](스캐폴드 얇게)·[[execution-memory-architecture]](해마 패턴을 공간에 적용)의 직접 집행.

---

## 1. 두 저장소 — 2층 (HANDOFF §2A / RESEARCH §12.1)

실증이 강제한 분리: **디스크 실험**(§12)이 (a)를, **교차-몸 실험**(§12.1)이 (b)를 채웠다. 둘은 *수명·범위·무효화 규칙이 다르다* → 한 테이블에 섞지 않는다.

### (a) 몸별 지도 — `forage_map`  *(이 디스크/볼륨 전속)*

이 몸 위에서만 의미를 갖는 것: 폴더 정체·주인 관습·죽은 가지·기질 가용성.

```
forage_map(
  id            INTEGER PK,
  body          TEXT,    -- 몸 신원: "mac" | "phone" | "disk:<volume_uuid>". detect_body()+볼륨UUID.
  locus         TEXT,    -- 이 항목이 말하는 곳. 폴더면 절대경로, 기질이면 "__substrate__".
  kind          TEXT,    -- 항목 종류: 'identity'(이 폴더=X) | 'convention'(명명·정리 관습)
                         --           | 'dead_branch'(여기 그것 없음) | 'substrate'(EXIF null 등 기질 가용성)
  claim         TEXT,    -- 자연어 단언. "journal*·안젤루치 = 출판논문(죽은가지)" / "발표=장소+날짜 명명"
  prior_class   TEXT,    -- ★구조적(structural) | 의미적(semantic). committal prune 권한을 가른다(§3).
  confidence    REAL,    -- 0~1.
  provenance    TEXT,    -- JSON: {forage_id, query, observed:["본 경로/내용 증거"], formed_at}. 왜 이 믿음이 생겼나.
  prune_reason  TEXT,    -- defeasible: "발표자료라 일본 자료 없음" — 죽음이 아니라 *이유로 아마 죽음*.
  generalizes   INTEGER, -- 0/1. convention 이 *안 본 새 가지에도* 적용되나(§12 "journal=논문" 일반화 실증).
  last_seen     TEXT,    -- 마지막 확인(재방문/형성)일. lazy freshness(감쇠 안 함, AI가 판단).
  locus_mtime   REAL,    -- 형성 시점 locus 의 mtime. 부패 무효화용(§4.3).
  surface_flag  INTEGER  -- 0/1. surface 카운터-패스가 "이 라벨을 의심하라" 표식한 항목(§3).
)
```

### (b) 몸독립 주인모델 — `owner_model`  *(모든 몸 공유)*

나라는 개인의 정체·분야·소속·내용신호·어휘↔의도 매핑. **디스크·웹·코드·책을 가로지른다**(§12.1 교차-몸 핀포인트 실증). world_pulse 일화기억과 ⋈.

```
owner_model(
  id            INTEGER PK,
  facet         TEXT,    -- 'identity'(이름·로마자 표기) | 'domain'(분야·전문어) | 'affiliation'(소속·이력)
                         -- | 'signal'(내용 지문: "FIPopCod·chernoff=Fisher/population coding")
                         -- | 'lexicon'(어휘↔의도: "작년 그 시점→mtime join") | 'habit'(정리 습관)
  value         TEXT,    -- 자연어. "Kukjin Kang=강국진, POSTECH→NYU(Sompolinsky)→RIKEN BSI"
  prior_class   TEXT,    -- structural|semantic. (대부분 semantic — 그래서 위험. §3)
  confidence    REAL,
  provenance    TEXT,    -- JSON: {sources:["disk:forage_id" | "web:url" | "profile"], formed_at, reinforced_by:[...]}.
                         --        ★복리 루프(§12.1④): 웹 결과가 디스크 신호를 역확증하면 reinforced_by 에 누적.
  last_seen     TEXT,
  surface_flag  INTEGER
)
```

**두 층의 핵심 차이**: `forage_map`은 *몸이 바뀌면 무의미*(이 디스크의 폴더). `owner_model`은 *몸을 가로질러 레버리지*(흔한 이름→유명인 중의성을 디스크 신호로 해소 → 웹에서 본인 논문 핀포인트). HANDOFF §2A·RESEARCH §12.1 결론을 1:1로 물질화.

---

## 2. 거처 (HANDOFF §2E 결정 ①) — **루프=인지층 / 기억=얇은 IBL accessor**

> 열린 질문: IBL 동사 `[?:seek]`인가, 인지층 행동인가, 둘 다인가?

**결정**: forager *루프*는 **인지층 행동**(AI 에이전트 자체). **`[?:seek]` 동사는 짓지 않는다.**

근거 (RESEARCH §0.5/§11): "루프는 AI 에이전트 자체 — 정지 apparatus·루프 컨트롤러는 실패 목록에 없다." seek를 동사로 만들면 *forager를 짓는* 것 = 침식 테스트 실패(모델이 좋아지면 풀림). forager의 손(probe)은 *이미* IBL 동사(`fs_query`/`grep`/`read`)다. 추가할 건 동사가 아니라 **기억**이다.

**그러나 기억은 거처가 필요하다** — 읽기/쓰기 인터페이스. 두 경로:

1. **자동 경로(주)** — 해마와 동형. forage *시작* 시 관련 `forage_map`+`owner_model` 항목을 인지 파이프라인이 `<forage_memory>` XML로 주입(해마 `<execution_memory>` 짝). forage *후* surprise/저확신 시 자동 증류(§4). **사람도 에이전트도 명시 호출 안 함.**
2. **수동 경로(보조, augmentation)** — 기존 `folder_note`를 부유화한 **얇은 IBL accessor** `[self:forage]{op:recall|note|forget}`:
   - `recall` — locus/주제로 기억 조회(사람이 "이 디스크에 대해 뭘 아나" 점검).
   - `note` — 사람이 직접 지도에 단언 추가(구조적 prior 수동 주입).
   - `forget` — 사람이 잘못된/낡은 prior 폐기(augmentation: 사람이 prune 재오픈·정정).

   이건 *forager 루프가 아니라 기억 CRUD*다 — 동사가 정당(folder_note가 이미 그 자리). `[?:seek]`(루프 동사)와 `[self:forage]`(기억 accessor)의 구분이 핵심: **우리는 후자만 만든다.**

**정합**: probe(`fs_query`)·기억accessor(`forage`)는 IBL, 정책·루프는 인지층 — 헌법 [[architecture_substrate_superstructure_seam]](탐침=하부, 포식정책=상부)·[[architecture_three_tier_cognition]](의식=루프, 어휘=손)에 정확히 안착.

---

## 3. 안전판 — 반대힘 (RESEARCH §13, HANDOFF §2B·2C)

누적의 그림자가 필터버블. 실증된 near-miss: "주인=신경과학자" prior가 `RIKEN PC etc/내글`(개인 에세이·**주식·투자**)·`희정 글`(타인 출판)을 *통째로 prune*할 뻔. **가장 개인적인 내용일수록 지배 프레임을 안 따른다** → 개인 비서엔 치명적. 스키마가 강제하는 4 안전판:

| 안전판 | 스키마 집행 |
|---|---|
| **① defeasible prior** | `prune_reason` 필수. "죽음"을 저장하지 않고 "~이유로 아마 죽음"을 저장 → **새 질의 목표가 prune_reason과 안 겹치면 자동 재오픈**(루프가 prune_reason을 읽고 판단). |
| **② prior_class 게이팅** | `prior_class='semantic'` 항목은 **committal prune 권한 없음**(가지를 *건너뛰되 삭제표시 안 함*). `structural`(동질·싸게 재검증, 예: 폴더=전부 PDF)만 committal 허용. RESEARCH §13 표. |
| **③ surface 카운터-패스** | `surface_flag`. forage 중 주인모델을 *위반*(이질)하는 내용을 만나면 그 라벨에 의심 표식 → 다음 recall이 "이 라벨 흔들림" 경고와 함께 회상. **이질성이 라벨을 깬다**(동질성 붕괴→의미 라벨 무효화·재조사). |
| **④ provenance+confidence** | 모든 항목 필수. 저확신 semantic prior는 ②에 의해 자동으로 committal 권한 박탈. |

**설계 원칙**: 빠른 가지치기 prior(해자)와 surface(반대힘)를 *항상 짝*짓는다 — [[project_augmentation_over_autonomy]]. AI가 숨길 것을 surface가 노출, AI가 prune한 것을 사람이(forget/note) 재오픈.

---

## 4. 생명주기 (HANDOFF §2D·2E 결정 ②, RESEARCH §7.4) — 해마 패턴의 공간판

### 4.1 물질화 (HANDOFF §2E 결정 ②) — **경험 누적, 선스캔 캐시 아님**

> 열린 질문: 라이브 추론 vs 파생 캐시(프로파일 트리)?

**결정**: **포식 경험에서 누적**(해마 증류 동형). 디스크 전체를 선(先)프로파일하는 *파생 캐시 트리를 짓지 않는다.*

근거: ① file_index 재설계의 헌법이 "선스캔0"([[project_file_index_unification]]) — 전체 프로파일 캐시는 이미 은퇴한 물질화의 부활. ② §12 실증: 증류물(지도+관습+죽은가지+정체)은 *싸고 작고 레버리지 큼* — 한 번의 forage가 ~6항목을 남기지 111k 파일을 색인하지 않는다. ③ 캐시는 부패 무효화 부담(디스크는 변한다). **누적은 forage가 실제로 밟은 곳만** 기록 → "지도≠전지"(§12 한계①, 새 내용은 여전히 탐침).

### 4.2 증류 트리거 (무엇을·언제) — 해마 `score<0.7` 짝

해마가 "유사 선례 없음(저점수)+성공"에서 증류하듯, forager는 **surprise/저확신에서** 증류:

- **형성**: forage가 끝날 때, *지도에 없던 것을 발견*했거나(새 폴더 정체·관습) *prior를 교정*했으면(거짓 냄새가 내용으로 뒤집힘, §2 한국강의 트레이스) 그것만 증류. **날 내용·로그는 저장 안 함**(§12 전이표: 내용=낮음).
- **강화**: 기존 항목을 재확인하면 `last_seen`·`confidence` 갱신, `provenance.reinforced_by`에 누적(복리).
- **정리 패스**: 해마/심층메모리 정리(self-check 합류, 24h 카덴스)와 동형 — 근접중복 병합·LRU·검증실패(거듭 틀린 prior) 가지치기. `surface_flag` 켜진 의미 prior는 보호(섣불리 정리 금지).

### 4.3 부패 무효화 (HANDOFF §3 미검증 핵심) — lazy, hard-decay 아님

심층메모리 ⑤("손튜닝 감쇠 곡선 대신 last_seen 노출, AI가 판단")의 공간판:

- **lazy**: recall 시 `locus_mtime` vs 현재 `os.stat(locus).st_mtime` 비교. 어긋나면 *삭제하지 않고* "이 지도는 형성 후 디스크가 변함(stale 가능)" 플래그를 회상에 부착 → AI가 재탐침 판단.
- **부재**: locus 경로가 사라졌으면 `dead_branch`로 강등(삭제 아님 — 이동일 수 있음).
- **이유**: hard-decay 곡선은 침식 대상(AI가 freshness 판단 가능) + 부패 규칙 자체가 apparatus화 위험. **측정값(mtime)을 노출하고 판단은 AI.**

> ★이 절(교차세션 지속+부패)이 F2의 *유일한 미검증 핵심 기제*(HANDOFF §3) — 단일 세션 프록시만 했음. **구현 후 실검증 1순위**: 노트를 디스크에 쓰고 *새 세션*이 읽기 + 디스크 변경 시 stale 플래그.

---

## 5. 가장 얇은 첫 구현 (HANDOFF §2F — 과설계 금지)

코드 하네스 = **탐침 바인딩 + 지속저장소 + provenance 헬퍼 셋뿐**(§11). 루프는 AI. 구현 상태(2026-06-20):

1. **✅ 저장소**: `backend/forage_memory.py` + `data/forage_memory.db`(2 테이블 §1, 실사용 시 자동 생성). note/recall/forget + provenance 병합(복리 reinforced_by) + lazy 부패 체크(`_stale_of`) + `recall_xml`. *맥 자아 전용*(폰=미디어한정, A3 후속). 무임베딩(엔트리 적음 → 키워드/locus 부분일치). 단위검증 통과.
2. **✅ `[self:forage]{op:recall|note|forget}`**: src `self.yaml`(scope:workspace) + pc-manager `tool.json`·`handler.py`(`_forage_op` 디스패처, `_OP_DISPATCHERS` 등록). build `--check` 삼각 통과(139 액션). **`folder_note`는 그대로 둠** — 그 storage_db 이관은 task#7 물질화 은퇴와 함께(deferred 경계 존중). 라이브 `/ibl/execute` 종단 검증(note map/owner·recall query필터·forget·freshness=missing).
3. **✅ 자동 주입**: `agent_cognitive._search_forage_memory` → `_build_execution_memory`에 `<forage_memory>` 합류(해마 `<execution_memory>` 옆). `_FORAGE_CUES` 의도 게이트(비forage 비용0) + 맥 자아 한정. **★백엔드 재시작 후 라이브**(core 모듈이라 packages/reload로는 불충분). 게이트·교차세션 회상은 유닛 검증 완료.
4. **✅ 자동 증류**: `agent_cognitive._distill_forage_memory` — forage 대화 종료 훅(`_distill_deep_memory` 옆 3 호출점: agent_communication·api_websocket×2). 경량 LLM이 *일반화 가능한 공간 지식 델타만* 추출(기존 지도를 "이미 아는 것"으로 넘김 → surprise/교정만). 날 내용·특정 파일 금지. dedup=저장소 UNIQUE upsert(재note=강화, 2차 판정 LLM 불요). **2단 게이트**: forage 단서(user) + 디스크 흔적(response에 경로/폴더/확장자 — 맛집·영상 검색은 LLM 호출 전 스킵). 실LLM 검증: dead_branch(+prune_reason)·convention·substrate·owner.domain/habit 추출, "여행 사진 못찾음" 날 결과는 미저장 — §12 증류실증과 일치.
5. **✅ surface 카운터-패스**: `_distill_forage_memory`가 증류 프롬프트에 "기존 라벨 *위반* 이질 내용→surface" 지시 + `mark_surface()`로 매칭 항목 표식. 실LLM 검증: §13 near-miss 재현("RIKEN PC etc"=연구라벨인데 개인 투자·타인 출판 발견→surface 표식).

**✅ 교차세션 지속 검증(F2 핵심, §6)**: 별도 프로세스(세션 A=note)→완전히 새 프로세스(세션 B=recall_xml)가 디스크에서 읽음 — 확인. **부패**: locus 변경→`stale`, 부재→`missing` 노출(삭제 안 함) 확인.

**짓지 말 것 재확인**(§11): 정지 공식(knee)·elusion apparatus·다단 모델 티어·세션내 믿음 부기 — 전부 실패 목록 밖. AI 판단 + 얇은 측정만.

### 5.1 정리 패스 ✅ (2026-06-20 완료) — 증류+정리 대칭 닫힘
관찰된 *의미적 근접중복 누적*(UNIQUE는 정확-locus만 dedup) 해소. `memory_consolidation.py` 동형:
- **기계 단계**(`forage_memory.py`, 무LLM): `forage_meta`(카덴스)·`list_bodies`·`merge_candidates`(surface 제외)·`merge_entries`(provenance 합집합·surface 이중거부)·`prune_cap`(LRU, surface 보호).
- **의미 병합**(`forage_consolidation.py`, 경량 LLM): `_merge_map_llm`(몸별 지도)·`_merge_owner_llm`(주인모델). 같은 공간지식만 병합, 애매하면 보존(과병합=손실).
- **합류**: `world_pulse_health.run_maintenance_bundle` item 4(해마 정리 다음). 24h 카덴스 게이트, 빈/소량 db는 LLM 호출 없이 스킵.
- **실LLM 검증**: convention 근접중복 병합·dead_branch(다른 폴더)는 보존·owner domain 중복 병합·**surface 항목 보호**·카덴스 재호출 skip·빈 db 무LLM 모두 확인.

### 5.2 소소 마감 (2026-06-20 완료)
- **✅ surface 매칭 정교화**: 증류 시 위반된 폴더(map locus)·*주인모델*(owner, semantic 하나) 둘 다 독립 표식. 실LLM 검증(RIKEN 위반→map#·owner# 동시 표식).
- **✅ CLAUDE.md changelog/카운트(139)** 갱신.
- **△ 해마 용례 시드(staged)**: manual op 발견용 4건 추가했으나 forage 어휘("포식"·"냄새지도")가 기존 액션(memory·show_map·storage)과 충돌해 *현재는 연상 안 됨* — [[execution-memory-architecture]]의 임베더 정렬 이음매(미사전학습 어휘). `source='manual_seed'`(정리 보호)라 **다음 임베더 재학습 시 흡수될 학습 데이터로 staged**, 무해. 자동주입이 주경로라 실용 영향 적음.

### 5.3 남은 일 (다음 세션 — 큰 것)
- **백엔드 재시작 반영**: 인지층(주입·증류·정리)은 core 모듈이라 *다음 재시작 후* 라이브.
- **F3 음성-단언 측정**(버린 더미 표본)·**고recall 망라**·**다른 몸(코드/책/웹) probe 계약** — HANDOFF §3. 큰 연구 프런티어.

---

## 6. 검증 계획 (구현 후)

- **단위**: `build_ibl_nodes.py --check`(forage 액션 삼각 정합) + 2 테이블 CRUD.
- **F2 핵심**(미검증 기제, §4.3): 세션A에서 `total` 디스크 포식→증류, **새 세션B**가 `<forage_memory>` 주입받아 1탐침 직행(§12 실증의 *진짜* 교차세션판). 디스크 변경→stale 플래그.
- **안전판**(§3): 의미 prior가 친 가지를 surface가 들어올리나(§13 near-miss 재현: `내글/투자` 가 "연구기" 라벨을 깨나).
- **교차-몸**(§12.1): `owner_model`만 들고 웹 질의("강국진")가 핀포인트 되나.
- **재사용 자산**: 테스트 디스크 `/Volumes/Extreme SSD/비둘기/total`(111,497파일), 주인모델 시드(HANDOFF §4).

---

## 7. 닻 (헌법)

- forager=AI, 더할 것만 — [[architecture_body_vs_absorbable]]
- 축적은 코퍼스/메모리에, 해마 증류를 *공간*에 — [[execution-memory-architecture]]
- 빠른 prune엔 항상 surface 짝 — [[project_augmentation_over_autonomy]]
- 벤더 미접근 층(사적 누적) — [[architecture_avoid_vendor_layer]]
- 탐침=하부/정책=상부 — [[architecture_substrate_superstructure_seam]]
- 루프=의식, 어휘=손 — [[architecture_three_tier_cognition]]

## 8. 포인터

- 연구: `FILE_FORAGING_RESEARCH.md`(§12 증류실증 / §12.1 교차-몸 / §13 필터버블 / §7 열린질문). 항해도: `FILE_FORAGING_HANDOFF.md`(§2 요건).
- 기존 코드: `data/ibl_nodes_src/self.yaml`(folder_note:585, fs_query:559), `backend/file_index.py`, `backend/agent_cognitive.py`(주입점), `backend/ibl_usage_rag.py`(증류 패턴), `backend/memory_consolidation.py`(정리 패턴), `data/system_docs/memory_architecture.md`(6종 지도).
- 메모리: [[project_personal_search_forager]], [[project_filesystem_comprehension_direction]], [[project_file_index_unification]].
</content>
</invoke>
