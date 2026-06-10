# IBL 액션 전체 정합성 감사 — Handoff

> 작성: 2026-06-05 (다음 세션에서 실행). 작성자 세션이 측정만 하고 수정은 안 함.

## 왜

최근 액션을 대량 수정함 — music 은퇴, cctv 행정 op 통합, xlsx 읽기 흡수 + `engines:spreadsheet` 신설, 그 이전 라운드2 어휘 개혁(~100 액션 제거/개명). 개별 작업의 사후감사에서 **제거/개명이 여러 표면에 죽은 참조를 남기는 패턴**이 반복 확인됨(특히 action_removal §5=world_pulse 건강기록, 인접 죽은코드, 엔진 종단 검증을 빠뜨림). 전체를 한 번 훑어 정합성 복구.

## 정찰 스냅샷 (2026-06-05 측정)

현존 레지스트리: **109 node:action / 104 고유 액션명** (`data/ibl_nodes.yaml`).

| 표면 | 상태 |
|---|---|
| 라이브 해마 DB `data/ibl_usage.db` (2261행) | **죽은 참조 0 ✓ 이미 깨끗** (수정 불필요) |
| 학습 `ibl_distilled.json` (181) | 깨끗 ✓ |
| 학습 `ibl_training_balanced_20260516.json` (2084) | **죽은코드 32행** ← music 은퇴 누락분 |
| world_pulse `action_health` (고유 123) | **유령 32개** ← 라운드2 잔재 |
| world_pulse `self_checks` (고유 36) | 깨끗 (`ibl_consistency`는 `__static__` 정상, 삭제 금지) |

### A. 학습 balanced JSON 죽은코드 32행 — **전부 music/abc** (대체 없음 → 행 제거)
```
22  engines:music
 5  sense:abc_get
 5  sense:abc_search
```
원인: music 은퇴 때 `ibl_synthetic_opus_final_2479.json`만 확인하고 `ibl_training_balanced_20260516.json`을 안 봄. 이 액션들은 *은퇴*(대체 액션 없음)라 **해당 행 삭제**가 맞음. 라이브 DB는 이미 0이므로 재색인 불필요. 단 이 JSON은 다음 fine-tuning 입력이라 안 지우면 재학습 시 죽은 액션을 다시 학습함.

### B. world_pulse action_health 유령 32 — 라운드2 개혁 잔재 (행 삭제)
```
apt_rent, apt_trade, book_by_isbn, book_detail, books, call, chrome, clipboard,
collect_sites, collect_xtest, company_news, content, cookies, dialog_info, file,
find, gui, house_rent, house_trade, iframe, indicators, info, integrated,
lecture_plan, list_api, logs, mss, navigate, price_target, recent, search_scholar, tab
```
이들은 **현존 액션명이 아님**(어느 노드에도 없음) → 안전 삭제. action_removal §5. X-Ray 유령 제거 목적.
⚠️ **공유 액션명 트랩**: 삭제 전 반드시 valid_names(아래 스크립트)로 재확인. cctv/music처럼 *다른 노드에 살아있는* 이름은 보존해야 함(위 32는 측정 시점에 전부 죽은 이름이지만, 작업 시점에 레지스트리가 바뀌었을 수 있음).

## 작업 목록 (표면별, 우선순위)

1. **[빠른 처리] 학습 balanced JSON 32행 삭제** — music/abc 행. `migrate` 말고 단순 제거(은퇴라 대체 없음).
2. **[빠른 처리] world_pulse action_health 유령 32 삭제** — valid_names 재확인 후 `DELETE FROM action_health WHERE action IN (...)`. self_checks도 동일 점검(현재 0).
3. **미점검 표면 전수 sweep** (위 죽은 이름들 + 라운드2 개명 액션 전반으로):
   - `data/guides/*.md`, `data/guide_db.json`, `data/system_docs/*.md`(historical changelog 줄은 보존)
   - `backend/generate_missing_intents.py`, `backend/rebuild_usage_db.py` 시드
   - `backend/ibl_routing.py` `_ACTION_NAME_ALIASES` / param alias가 죽은 액션 가리키나
4. **Orphan 점검**: 각 패키지 `tool.json`에 정의됐지만 *어떤 IBL 액션도 `tool:`로 안 가리키는* 도구 / handler `_OP_DISPATCHERS` 고아 / `ibl-core/tool.json` enum 레거시.
5. **프론트(app 모드)**: `frontend/src` 계기(Instrument)들의 하드코딩 IBL 코드에 죽은 액션 없나.
6. **self_check_plan.json**: action_removal §6대로 자동 재생성. 깨끗이 하려면 `generate_test_plan(force=True)` 1회.

## 재발 사각 체크리스트 (개별 액션 제거/개명 시에도 매번)

①**인접 죽은코드** — 이름 바뀐 것뿐 아니라 도메인의 *이미 죽어 있던* 코드까지(예: cctv_sources).
②**world_pulse §5** — action_health + self_checks 유령 삭제.
③**공유 액션명 보존** — 삭제 전 다른 노드에 그 이름이 살아있나 확인(cctv·music·read 등 노드 공유).
④**엔진 종단 검증** — 핸들러 직접 테스트로 끝내지 말고 `POST /ibl/execute`(project_id 필요)로 파서→라우팅→핸들러 전체.
⑤**학습 JSON** — 라이브 DB뿐 아니라 `data/training/*.json` 활성 파일까지(다음 fine-tuning 입력). balanced + distilled 둘 다.

## 도구

### 정찰 스크립트 (드리프트 재측정 — 작업 시작/종료에 실행)
```python
import yaml, sqlite3, json, re
d=yaml.safe_load(open('data/ibl_nodes.yaml',encoding='utf-8'))
valid={(n,a) for n,nd in d['nodes'].items() for a in nd.get('actions',{})}
names={a for _,a in valid}
TOKEN=re.compile(r'\[(\w+):(\w+)\]')
# 해마 DB 죽은 참조
c=sqlite3.connect('data/ibl_usage.db')
dead={}
for rid,code in c.execute("SELECT id,ibl_code FROM ibl_examples"):
    for n,a in TOKEN.findall(code or ''):
        if (n,a) not in valid: dead[f"{n}:{a}"]=dead.get(f"{n}:{a}",0)+1
print("해마 죽은참조:", dead)
# world_pulse 유령
wp=sqlite3.connect('data/world_pulse.db')
for t in ('action_health','self_checks'):
    ph=[r[0] for r in wp.execute(f"SELECT DISTINCT action FROM {t}") if r[0] and r[0] not in names and not r[0].startswith('__')]
    print(f"{t} 유령({len(ph)}):", sorted(ph))
# 학습 JSON
for f in ['data/training/ibl_training_balanced_20260516.json','data/training/ibl_distilled.json']:
    n=sum(1 for e in json.load(open(f,encoding='utf-8')) for x,y in TOKEN.findall(e.get('ibl_code','')) if (x,y) not in valid)
    print(f, "죽은코드 토큰:", n)
```

### 정리 패턴
- **삼각 검증**: `python3 scripts/build_ibl_nodes.py --check`
- **해마 relabel+재임베딩**(필요 시): `IBLUsageDB()._load_model_sync()` 후 행별 `UPDATE ibl_examples`(FTS 트리거 자동) + vec는 **DELETE→INSERT**(vec0는 INSERT OR REPLACE 미신뢰, [[project_sqlite_vec_quirks]]). 끝에 ex/vec/fts 카운트 일치 확인.
- **world_pulse 삭제**: `DELETE FROM action_health/self_checks WHERE action IN (...)` — **valid_names로 거른 것만**.
- **반영**: 해마/world_pulse는 라이브 read(리로드 불필요). src/handler/tool.json 변경 시 `POST /packages/reload`.

## Definition of Done
- 정찰 스크립트가 모든 표면에서 **0 죽은참조 / 0 유령**(공유명·`__static__` 제외).
- `build_ibl_nodes.py --check` 통과.
- 샘플 액션 1~2개 `POST /ibl/execute` 종단 통과.
- (선택) 학습 JSON 수정했으면 다음 해마 재학습 일정에 반영.
