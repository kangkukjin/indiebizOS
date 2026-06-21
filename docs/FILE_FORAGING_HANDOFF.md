# 파일 포식(Information Foraging) 핸드오프 — v2 (2026-06-20 연구 세션 후)

*성격: **다음 세션 진입점/항해도.** 깊은 기록·논증·실증은 `FILE_FORAGING_RESEARCH.md`(§0~13). 이 문서는 "결정된 것 / 다음 할 일 / 재사용 자산 / 시작법"만.*

---

## 0. 30초 요약 (TL;DR)

- **문제**: 낯선·반구조 공간(대표=하드디스크)에서 *이미 있는* 정보 찾기 = **비용인지 포식**. 전략명제 "찾기 ≥ 쌓기".
- **이번 세션 핵심 전환**: **forager는 AI다 — 짓지 마라.** 우리는 *AI가 결여한 것 넷*만 더한다. 선행연구(포렌식·TAR·포식이론)는 *규율有지능無*, 현대 에이전트는 *지능有규율無* → 우리=옛 규율을 새 지능 위에.
- **중심 문제 = F2(개인 서치 경험 누적)**. 5턴 실증 통과(아래 §1).
- **다음 세션 1순위 = 설계 결정화**: *개인-forager 메모리 스키마*(2층 + defeasible + surface + provenance). §2 참조. **→ ✅ 완료(2026-06-20): `FORAGER_MEMORY_SCHEMA.md`** — 2 테이블 field 스키마(`forage_map`/`owner_model`)·거처(루프=인지층, `[?:seek]` 안 만듦, 기억=`[self:forage]` accessor=folder_note 부유화)·물질화(경험누적, 선스캔캐시X)·생명주기(해마증류 공간판, lazy 부패무효화)·안전판4 전부 결정. 다음=§5 "가장 얇은 첫 구현".
- **상태**: 연구 *닫음* + 설계 결정화 *닫음* + **얇은 첫 구현 step 1~5 완료(2026-06-20)**: 저장소(`backend/forage_memory.py` 2테이블)·IBL 액션(`[self:forage]{recall/note/forget}` scope:workspace, build --check 139액션·라이브 종단)·자동주입(`_search_forage_memory` 의도게이트)·**자동증류(`_distill_forage_memory` 3 훅, 경량LLM이 지도 델타만 추출+2단게이트)·surface 카운터패스**까지 ✅. **★루프 닫힘: 주입→포식(AI)→증류→surface 전부 실LLM 검증**(dead_branch+prune_reason·convention·owner 추출, §12 증류실증 일치 / §13 필터버블 near-miss 재현=라벨위반 surface표식). F2 핵심(교차세션 지속+부패)도 검증됨. **+정리 패스(consolidation) 완료(2026-06-20)**: `forage_consolidation.py`(기계=forage_memory merge/prune/meta+surface보호, 의미병합=경량LLM, run_maintenance_bundle item4 합류 24h카덴스). 실LLM 검증=근접중복 병합·다른폴더 보존·surface 보호·카덴스skip. **증류+정리 대칭 닫힘 → forager 루프 전체 완성**(주입→포식→증류→surface→정리). 다음=surface 매칭 정교화·해마시드, 큰 검증=F3 음성단언(§3).

---

## 1. 결정된 것 (재론 금지 — 실증·논증 완료, 출처=RESEARCH.md 절)

| 결론 | 근거 |
|---|---|
| **forager = AI.** AI는 이미 싼-것-먼저 포식·재구성·내용판단·정지를 NL로 함. 우리는 *결여한 것*만 더함(침식 테스트로 판정). | §0.5 |
| **연구의 진짜 범위 = "나라는 개인이 서치하는 *방식*"의 누적.** 웹="어떻게 뒤지나"가 공동체에 이미 누적(모델 베테랑) / 디스크=그게 없어 *내가 만들어야*. 개인 누적은 *웹도* 개선(교차-몸). | §0.6 |
| **AI가 더할 것 = 넷** ① 몸(싼 탐침: 해시·메타·EXIF·트리·카빙) ② 세션 넘는 지속 기억 ③ 사적 prior(일화기억·관습) ④ provenance+음성검증 행위. | §0.5, §6 |
| **실제 베이스라인 실패 5 = 추가 4와 1:1.** apparatus(정지공식·루프컨트롤러·다단티어)는 *실패 목록에 없음 → 짓지 마라.* | §11 |
| **스케일은 실패 아님.** 111k 파일을 ~6개 열어 해결(트리 하강+가지치기). LlamaIndex 규모실패는 *평탄* 검색 한정 → **계층 가지치기 컨트롤러 불요.** | §11 |
| **F2 실현가능·고ROI. 증류해야 할 것 = 지도+관습+죽은가지+정체** (*날 내용·로그 아님*). 관습은 *안 본 새 가지에도 일반화*됨. | §12 |
| **교차-몸 전이 검증.** 디스크 주인모델이 *검색불가 웹질의(흔한이름→유명인)*를 핀포인트로. **F2 저장소 = 2층**: (a)몸별 지도 (b)몸독립 주인모델. | §12.1 |
| **필터버블 위험 실증 + 경계.** 위험한 건 *의미적 과일반화 prior*(주인=신경과학자 → 개인에세이·투자·배우자출판 매몰). *구조적 prior*(폴더=동질 PDF)는 안전. **가장 개인적 내용일수록 지배 프레임을 안 따른다.** | §13 |
| **선행연구 정독 결론**: 학습분류기·seed set·특징공학·추정apparatus = 흡수(짓지마). knee/elusion = "공식 이식"이 아니라 **정지는 AI 판단 + 음성단언 *측정* 도구만 얇게.** | §4~5 |

---

## 2. 다음 세션 1순위 — 설계 결정화: *개인-forager 메모리 스키마*  ✅ 완료 → `FORAGER_MEMORY_SCHEMA.md`

> **2026-06-20 완료.** 아래 요건 A~F는 전부 `docs/FORAGER_MEMORY_SCHEMA.md`에서 field 수준 스키마+거처·물질화·생명주기 결정으로 못박힘. 핵심 결정: ①거처=루프는 인지층(`[?:seek]` 안 만듦), 기억은 `[self:forage]{recall/note/forget}` accessor(=기존 `folder_note` 부유화) ②물질화=경험누적(선스캔 캐시 금지, file_index 선스캔0 헌법) ③생명주기=해마 증류 패턴의 *공간판*+lazy 부패무효화(mtime 노출, AI 판단) ④2 테이블(`forage_map` 몸별 / `owner_model` 몸독립) ⑤기존 자산 위에 올라탐(folder_note·fs_query·해마/심층메모리 배관 재사용). **다음 = 그 문서 §5 "가장 얇은 첫 구현"(5단계).** 아래 요건은 이력으로 보존:

네 실험이 내용을 다 채웠으니, 이제 **F2 지속저장소의 최소 설계**를 그린다. 요건(전부 실증에서 도출):

**(A) 2층 구조** (§12.1)
- **(a) 몸별 지도** — 이 디스크의 폴더 정체·관습·죽은가지. 몸 전속.
- **(b) 몸독립 주인 모델** — 정체·분야·소속·내용신호·어휘/의도 매핑. 디스크·웹·코드 공유. (world_pulse.db 일화기억과 ⋈.)

**(B) 각 prior 항목이 지녀야 할 것** (§13 안전판)
- **provenance**: 왜·어느 포식에서 형성됐나.
- **confidence**.
- **종류 태그**: *구조적*(동질·싸게재검증=committal prune 허용) vs *의미적*(이질억압 위험=committal prune 금지).
- **defeasible + prune-reason**: "죽음"이 아니라 "~이유로 아마 죽음" → *새 질의 목표가 prune-reason과 안 겹치면 자동 재오픈*.

**(C) 반대힘 — surface 카운터-패스** (§13)
- 주인 모델을 *위반하는*(이질적) 내용을 일부러 들어올림. "이질성이 라벨을 깬다": 동질성 붕괴 시 의미 라벨 무효화·재조사. (필터버블 = 해자의 그림자, 누적엔 항상 반대힘 짝지을 것.)

**(D) 증류 정책** (§12)
- 저장 = 지도+관습+죽은가지+정체. *날 내용·로그 저장 금지.*
- 트리거: 해마 증류 패턴([[execution-memory-architecture]]) 재사용 검토(언제·무엇을 — surprise/저확신 시?).

**(E) 결정해야 할 열린 질문** (RESEARCH §7 중 스키마에 필요한 것)
- **거처**: IBL 동사(`[?:seek]`)인가, 코그니티브 층 행동인가, 둘 다인가?
- **물질화**: 라이브 추론 vs 파생 캐시(프로파일 트리)? 캐시면 **부패 무효화 규칙**(디스크 변경).
- **자율 vs 협업 비율** (augmentation: 사람이 prune 재오픈).

**(F) 과(過)설계 금지** (§0.5): 위 요건의 *가장 얇은* 첫 구현부터. 코드 하네스 = 탐침바인딩 + 지속저장소 + provenance헬퍼 *셋뿐*. 루프는 AI. 다단티어·정지공식 짓지 말 것.

---

## 3. 그다음 — 미검증(설계 후 엔지니어링 검증으로)

- **교차세션 지속 + 부패**: ✅ 구현·검증(별도프로세스 note→새프로세스 recall / locus변경→stale·부재→missing).
- **F3 음성-단언 측정 행위**: ✅ **완료(2026-06-20)** — `[self:residual]{sample|estimate}`. 모집단(file_index.candidate_paths)−seen=미관측 균일 무작위 표본 → AI가 판단 → Wilson 이항추정으로 "미관측 중 누락 점추정+95% CI". **판단(없음 vs 덜봄)은 AI 몫**(목표 recall 대비), 도구는 측정·중립 해석만(apparatus 아님). 라이브 검증(estimate 0/100 of 50→상한1.8 / sample 1631 PDF→균일표본·seen 제외). forage 출력계약 §3.3 "무엇을 못 찾았나" 메움. **남은(소)**: 인지층 프롬프트가 강한 음성단언 전 residual을 *능동 호출*하도록 넛지(지금은 어휘로 발견 가능, 능동 미배선).
- **고recall 망라**(§6.2 마지막 바늘 문제): "여권 스캔 *전부*" 류. **F3 residual이 측정 도구 제공** — "전부 찾았나"를 estimate로 정량화. 남은=인지층이 망라 의도 감지 시 residual+고지 의무화.
- **다른 몸 일반화**(코드/책/웹): probe 계약(probe/peek/cost) 인터페이스. **다음 큰 프런티어**(미착수). owner_model은 이미 몸독립이라 절반 됨 — probe 바인딩만 몸별.

---

## 4. 재사용 자산 (실험 인프라 — 다음 세션이 바로 씀)

- **테스트 디스크**: `/Volumes/Extreme SSD/비둘기/total` — 파일 **111,497개·깊이 15**, 강국진 학술 아카이브(2002~14). *알려진 구조 노트*(폴더 정체) = RESEARCH §12. ★주의: 디스크 주인 = 사용자 본인 학술 이력으로 보임(공개 논문).
- **실증 트레이스 3건**(대조군): Gmail(싼메타 충분·핀포인트) / 여행사진(싼메타 부재=EXIF null·내용층 강제·열린gather) / 한국강의(조인+군집+거짓냄새교정) = RESEARCH §2.
- **주인 모델**(교차-몸용): Kukjin Kang — 신경부호화·tuning curve·Fisher info·Chernoff distance·population coding, POSTECH(PhD)→NYU(Sompolinsky)→RIKEN BSI. 대표논문 Kang-Shapley-Sompolinsky, *J.Neurosci* 2004.
- **싼 탐침 도구 패턴**: 이름매치 `find`, `strings -e l`(UTF-16 옛 .ppt 한글), `textutil -convert txt`(.doc/.htm), `Read`(이미지/pdf 표본), `mdls`(EXIF — *외장볼륨선 null*=F1). 포맷 이질성을 probe 계약이 흡수해야.
- **구현 토대(완료)**: `backend/file_index.py`(보편 색인 어댑터, 선스캔0, `detect_body()` 맥=Spotlight/폰=MediaStore). `self:photo`(미디어 preset)·`self:fs_query`(보편 preset) 둘 다 위임. 파생조회=`>>groupby` 통화. A36 종단검증. 해마 stale op 58건 교체. 검증=`python3 scripts/build_ibl_nodes.py --check`.

### 정리 잔여 (낮은 위험, 이해층 설계와 함께)
- **A1. 물질화 은퇴(deferred, task#7)**: 데스크탑 풍부창(REST `api_photo`→`photo_db`)→file_index 이관 + `photo_db`/`scanner`/`storage_db` `_archive`. ★지금 하지 말 것 — 이해층이 풍부 UI 재편(redo 방지).
- **A2. 일반 `table`/`chart` view(task#6)**: groupby table 통화를 앱모드 타일로(두 렌더러 + photo 통계/타임라인 모드).
- **A3. 폰 `fs_query`**: 다음 폰 빌드 때 번들. 폰 MediaStore는 미디어-한정(일반파일=scoped-storage 제약).
- **A4. 소소**: 폰 has_gps=EXIF per-file(위치없는 사진 많으면 비용↑, 날짜로 좁히면 OK). mdfind 미색인 볼륨=walk 폴백.

---

## 5. 헌법 닻 (이 작업의 제약)

- **forager=AI, 더할 것만**(침식 테스트) — [[architecture_body_vs_absorbable]]
- **축적은 가중치 아닌 코퍼스/메모리에** — [[execution-memory-architecture]] (해마 증류를 *공간*에 적용)
- **augmentation**: 사람이 AI가 prune한 것 재오픈, surface가 AI가 숨길 것 노출 — [[project_augmentation_over_autonomy]]
- **벤더 미접근 층 = 개인 누적**(웹서치 기술은 commodity, 내 디스크 경험은 복리·나만의 것) — [[architecture_avoid_vendor_layer]]
- **하부/상부 이음매**: 몸별 탐침=하부, 포식정책=상부 — [[architecture_substrate_superstructure_seam]]

---

## 6. 포인터

- **깊은 기록**: `docs/FILE_FORAGING_RESEARCH.md` (§0 관통명제 / §0.5 forager=AI / §0.6 개인 forager / §1 문제정의 / §2 트레이스 / §3 아키텍처 / §4~5 선행연구 keep·absorb / §6 델타 / §7 열린질문 / §8 쇼핑리스트 / §9 후속 / §11 실패분류 / §12 누적실험 / §12.1 교차-몸 / §13 필터버블).
- **구현 토대**: `backend/file_index.py`, `data/packages/installed/tools/photo-manager/handler.py`, `.../pc-manager/handler.py`, `data/ibl_nodes_src/self.yaml`(photo/fs_query), `docs/FILESYSTEM_PHOTO_REDESIGN_PLAN.md`(Phase 1~5).
- **메모리**: [[project_personal_search_forager]](중심), [[project_filesystem_comprehension_direction]], [[project_file_index_unification]], [[reference_openhuman]].
- **검증**: `python3 scripts/build_ibl_nodes.py --check`. 폰 빌드: `cd phone-companion && ./gradlew :app:installDebug`.
