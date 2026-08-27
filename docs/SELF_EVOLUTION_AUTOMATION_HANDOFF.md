# 자기진화 자동화 핸드오프 — 몸 각인 낱말 + 상상훈련 마라톤

> 2026-08-27 설계. 사용자 위임: "상상훈련 4배+수리+커밋을 4회 반복하는 명령이 작동하게 하라.
> git 낱말은 **스크립트 등록이 아니라 어휘만들기**로. 그리고 그 어휘는 **이 컴퓨터·이 사용자 전용이면 안 된다** —
> indiebizOS 는 남이 클론해 자기 PC에 설치하는 하네스다. 내 GitHub 저장소 하드코딩 금지, 내 PC 전용 금지."
>
> 상태: **구현 완료 (2026-08-27 같은 날).** Part A = body_ops.py op_commit + handler 디스패치 +
> ibl_actions.yaml + 관문 test_body_commit.py C1~C8 + 가이드 body.md + 해마 시드 5건.
> Part B = PENDING_VERDICTS.md + scripts/imagination_marathon.sh. 구현 중 설계에서 달라진 것:
> ① 부작용 op 에는 fixture 금지(빌드 검증기 — 건강검진이 실행해 버림) → 용례는 가이드로.
> ② C5 계약 정정: "공유 인덱스 파일 무변"이 아니라 **남의 스테이징 생존 + 각인 경로는 커밋 후
>   공유 인덱스 동기화**(`git reset -q HEAD -- paths` — `git commit -- paths` 원 의미 재현.
>   안 하면 각인 경로가 남들에게 유령 스테이징으로 보인다).
> ③ 실행기에 `-c core.quotepath=false` — 한글 파일명 8진수 인용 깨짐 수리(시험이 적발).
> ④ 라이브 반영 실측: system_essentials 형제 모듈은 `/packages/reload` 만으로 살아난다
>   (_SIBLING_MODS 캐시가 handler 재실행에 리셋) — 백엔드 재기동 불요.

---

## Part A — `[self:body]` op:commit (각인)

### A-0. 자리 판정: 새 액션이 아니라 기존 낱말의 굴절이다

실측: 몸 원장 낱말은 **이미 있다** — `[self:body]`(system_essentials, `body_ops.py`).
op 6개(changes/log/file/writes/trajectory/diff) 전부 읽기 전용이고, 머리말이 스스로
"원장은 git 이 쓰고, 이 어휘는 회상 통로"라고 선언한다.

- **명명 헌법 2조(변형은 op)**: commit 은 같은 개념(몸의 변화 원장)의 **쓰기 굴절**이다.
  `[self:commit]` 신조어는 3조(한 단어=한 개념) 위반 — 원장 개념이 두 이름에 흩어진다.
- **액션 4기준(접근 캡슐화)**: 커밋은 "git 호출"이 아니라 **절차 지식의 캡슐**이다 —
  공유 인덱스 불가침(동시 세션 함정) + 관문(pre-commit) 보존 + pathspec 강제.
  기존 어휘 조합으로 표현하면 길고 취약한 raw 코드로 떨어진다 → 주조 가치 충족.
- 계약 개정: 머리말 "전 op 읽기 전용" → **"회상 6 + 각인 1(commit)"**.
  각인이 유일한 쓰기다. reset/checkout/rebase/amend = 개서(파괴)라 낱말이 아니고,
  push = 전파라 낱말이 아니다(아래 A-3 ②).

### A-1. 낱말 계약

```
[self:body]{op: "commit", message: "...", paths: ["backend/x.py", "docs/y.md"]}
```

| 자리 | 규칙 |
|---|---|
| `message` | **필수.** 호출자가 준 그대로 커밋된다 — 자동 서명·Co-Authored-By·접두어 주입 금지. |
| `paths` | **필수, 1개 이상.** 생략·빈 배열 = 거절 봉투. "전부 커밋"이라는 굴절은 없다(공유 인덱스 함정의 어휘化 차단). 저장소 밖 경로 = 거절(기존 `_scope_of` 재사용). |
| 통화 | 성공 = `{items:[{commit, message, files:[...], author, gates:"passed|none"}]}` 1행. 실패(관문 거부 포함) = 정직한 봉투에 **관문의 stderr 원문 요지** 동봉 — 침묵 실패 금지. |

거절 봉투가 필요한 경우: ①paths 누락 ②저장소 아님(폰 몸 — 기존 `_guard_root`)
③해당 paths 에 변화 없음(empty commit 금지) ④git 저자 미설정(A-3 ③) ⑤관문 실패.

### A-2. YAML 개정안 (선언 골자)

```yaml
body:
  returns: items
  side_effect: true     # 각인 op 보유 — 통화(returns)와 안전은 다른 축 (others:board 선례)
  ops:
    side_effect:
      changes: false
      log: false
      file: false
      writes: false
      trajectory: false
      diff: false
    fixture:
      commit: '[self:body]{op: "commit", message: "수리 요지", paths: ["backend/x.py"]}'
    values:
      commit: 각인 — 지정한 경로만 원장에 기록 (paths·message 필수, 관문 통과 필요)
```

`side_effect: false` 를 `true` 로 뒤집되 읽기 op 6개를 명시적으로 `false` 표기 —
검수 비용 계층(0층 prescreen)과 dry-run 이 읽기 op 에서 계속 초록불을 켤 수 있게.

### A-3. 이식성 계명 — 사용자 제약의 기계화

위임 제약("이 컴퓨터·이 사용자 전용 금지")을 산문이 아니라 **거절 규칙과 관문**으로 만든다.

1. **저장소 = 코드 위치의 `.git` 조상** (기존 `_repo_root` 재사용). 절대경로 하드코딩 0.
   어느 PC 에 클론해도 그 클론이 몸이다.
2. **원격 무지**: commit 은 remote 를 조회조차 하지 않는다. push 낱말이 없으므로
   **GitHub URL 이 존재할 자리 자체가 없다.** (push 는 전파 = 세계로 나가는 행위 —
   현 사용자 습관도 push 는 수동. 필요가 실증되면 별도 판정으로 재론.)
3. **저자 = 그 클론의 git config** (`user.name`/`user.email`). 미설정이면 정직한 봉투
   "git config user.name/email 설정 필요" — 특정인 폴백·환경변수 주입 금지.
4. **메시지 불변**: 호출자가 준 message 그대로. 몸이 서명을 덧붙이지 않는다.
5. **관문 = 그 클론의 소유물**: 그 저장소에 설치된 pre-commit 을 그대로 실행한다.
   없으면 그냥 커밋된다 — 관문은 저장소의 것이지 낱말의 것이 아니다.
6. **OS 중립**: `_find_git` 은 `shutil.which` 가 정본, 고정 경로 후보는 폴백일 뿐(기존 코드 유지).
   `data/packages/` = Windows 이식성 위험지대 관문 대상 — 경로 조립은 `os.path` 만.
7. **폰 몸 정직**: `.git` 없는 몸(Chaquopy)은 기존 `_guard_root` 봉투로 거절.

### A-4. 구현 설계 — 임시 인덱스 + 관문 보존

핵심 제약 둘이 메커니즘을 결정한다:
**(a) 공유 인덱스 불가침** — 동시 Claude Code 세션이 같은 `.git/index` 를 쓴다(운영 함정 원장).
**(b) 관문 보존** — pre-commit 이 반드시 돌아야 한다(관문이 커밋 시점의 안전판이므로
plumbing `commit-tree` 경로는 **금지** — 훅을 우회한다).

```
tmp_index = tempfile (저장소 밖, scratch)
env GIT_INDEX_FILE=tmp_index 로:
  git read-tree HEAD            # 임시 인덱스를 HEAD 로 초기화
  git add -A -- <paths>          # 지정 경로만 반영 (신규·수정·삭제 동일 취급)
  git diff --cached --quiet && → "변화 없음" 봉투 (empty commit 금지)
  git commit -m <message>        # porcelain — pre-commit 훅이 같은 env 를 상속해
                                 #   임시 인덱스 기준으로 정확히 검사한다
```

- **동시성**: `.git/ibl_body_commit.lock` flock — 몸 안 호출자끼리 직렬화.
  외부 세션(Claude Code)과의 레이스는 커밋 직후 `HEAD^ == 시작 시점 HEAD` 검증,
  어긋나면(사이에 남의 커밋 착륙) 1회 재시도 — 재시도도 어긋나면 정직한 봉투.
- **timeout**: subprocess timeout **명시 300s + 사유 주석**("pre-commit 관문 체인이 수십 초" —
  동시성 관문 `check_concurrency` 규약). 기본 20s 인 기존 `_git` 헬퍼와 별도 경로.
- **REPAIR 그랜트와의 관계**: commit 은 실행 코드를 바꾸지 않는다 — 이미 바뀐 작업트리를
  기록할 뿐이다. RED 쓰기 게이트는 쓰기 시점(`[self:edit]`/patch)에 이미 작동했으므로
  commit 에 이중 게이트를 달지 않는다. 단 커밋은 되돌릴 수 있고(revert) 개서(amend)는 낱말이 없다.

### A-5. 관문(시험) 목록

- `test_body_commit.py` (신설, `__main__`=pytest 위임 — test_single_runner 규약):
  C1 paths 없음=거절 · C2 저장소 밖 경로=거절 · C3 변화 없음=거절 · C4 저자 미설정=안내 봉투 ·
  C5 임시 인덱스 사용 실증(공유 인덱스 mtime 불변) · C6 pre-commit 실패 시 커밋 부재+stderr 동봉 ·
  C7 커밋 성공 통화 1행 · C8 **소스 어디에도 원격 URL·절대 홈경로 리터럴 없음**(AST/grep — 계명 1·2 의 기계화).
- 기존 상시 관문 통과: `build_ibl_nodes.py --check`(삼각+마커) · `check_value_judgment` ·
  `check_concurrency`(timeout 명시) · `check_silent_clamp`(paths 는 자르지 않는다 — 필수라 해당 없음) ·
  Windows 이식성 관문.

### A-6. 파생 의무 (vocab_change_docs 체크리스트)

빌드 재생성(`build_ibl_nodes.py`) → `/packages/reload`(handler 라이브, `body_ops.py` 는 백엔드 재기동) →
가이드 `body.md` 각인 절 추가 → `new_action_checklist.md` 경유 확인 → 문서 7표면 마커 →
해마 시드(조합 용례 위주): `[self:body]{op:"changes"} >> [self:body]{op:"commit", ...}` ·
수리 후 각인 시나리오 · 거절 봉투 시나리오. 시딩은 `add_examples_batch` 단일 경로.

---

## Part B — 상상훈련 마라톤 (4회 반복 프로토콜)

### B-0. 정직한 전제: Part A 는 마라톤의 전제가 아니다

마라톤의 실행자는 Claude Code 세션이고, 세션은 git 을 직접 쓴다. Part A 의 존재 이유는
**몸 안의 자기수리 경로(REPAIR)가 자기 손으로 결말을 각인할 수 있게** 하는 것 —
마라톤과 독립된 가치다. 둘을 묶은 것은 위임이 하나였기 때문일 뿐이다.

### B-1. 구조

- **실행자**: Claude Code 세션, **회차당 1세션** (46회차 실측 — 한 회차가 세션 하나를 소진).
- **라운드 프롬프트** (표준문, 각 세션에 동일 투입):
  > 상상훈련 1회차를 수행하라. 축 선정은 개정 가이드(`77857dc7` — 축 선정 관문 질문·닫힌 밭
  > 재검침 금지·표현력 갭 복귀)를 따르라. 보통때의 4배 규모. 수리성 결함은 근본 수리하고
  > 관문을 세운 뒤 **pathspec 으로** 커밋하라. 언어 개정·파괴적 변경 2종은 집행 금지 —
  > `outputs/imagination_training/PENDING_VERDICTS.md` 에 적립만 하라. 신규 발견 0 이면
  > 억지로 만들지 말고 "마른 라운드"로 보고하라.
- **판정 큐**: `PENDING_VERDICTS.md` — 라운드는 append 만, 비우는 것은 사용자.
  root-fix-not-verdict 원칙의 마라톤판: 루프는 판정 지점에서 멈추지 않되 월권하지도 않는다.
- **종료 조건**: 마른 라운드 2연속 = 조기 종료(loop-until-dry). 판정 큐 적립이 임계
  (제안: 5건) 초과 = 중단 후 사용자 호출 — 판정 없이 계속 돌면 보류 더미가 된다.

### B-2. 구동 3안과 권장

| 안 | 형태 | 평가 |
|---|---|---|
| ① 수동 4회 | 사용자가 세션 4개에 라운드 프롬프트 투입 | 가장 단순, 판정 개입 자연. 지금도 가능. |
| ② 반자동 래퍼 | `scripts/imagination_marathon.sh` — headless `claude -p` 4연속, 라운드 사이 종료 조건 검사 | **권장.** "명령 한 번 = 4라운드"라는 위임 원형에 부합. |
| ③ 주기 스케줄 | launchd/cron 상시 | 수확 체감 국면(밭 지도 종결)에서 과잉 — 보류. |

②의 래퍼는 몸 실행에 불요한 **개발 도구**다(빌드 스크립트와 같은 신분, `scripts/` 소속).
Claude Code 부재 환경에서는 그냥 안 도는 것으로 충분 — 하네스 기능이 아니므로 이식성 계명 비적용.
루프 사이 상태 판독은 전부 파일(git log 증분 / PENDING_VERDICTS 행수)로 — 세션 간 컨텍스트 전달 없음.

### B-3. 기대치 관리 (설계자 소견)

밭 지도 종결(46회차) 이후의 훈련은 census 가능한 축이 아니라 표현력 갭·마찰이 직업이다 —
회차당 수확은 판단 품질에 좌우되고, 마라톤의 한계 효용은 체감한다. 자동화의 지속 가능한
절반은 이미 관문 4종으로 몸에 들어가 있다("종 수리로는 속이 안 죽는다 — 관문이 속을 닫는다").
마라톤은 발견의 자동화, 관문은 재발 차단의 자동화 — 이 설계는 전자를 후자에 계속
공급하는 컨베이어로 이해하는 것이 정확하다.

---

## 구현 순서 제안

1. Part A: `body_ops.py` op_commit + YAML 개정 + 관문 C1~C8 + 파생 의무 일주 (반나절 규모)
2. Part B: PENDING_VERDICTS.md 초기화 + 라운드 프롬프트 정본화 + ② 래퍼 (한 시간 규모)
3. 판정 대기 없음 — 본 설계는 전부 사전 추가(내용어)·개발 도구 범위. 유일한 보류 =
   push 낱말(A-3 ②, 필요 실증 시 재론).
