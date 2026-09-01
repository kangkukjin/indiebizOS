# 자기수정 안전 바닥 설계 (Self-Modification Safety Floor)

*작성: 2026-07-02 (Claude Code, 외부 개발 하네스). 근거: 에피소드 548~552 실측 + 코드베이스 조사 2건.*

> **★헌법 개정 (2026-08-05, 사용자 확정) — Floor #4(사람 승인) 폐기, REPAIR 경로 신설:**
>
> "어차피 AI가 하는 걸 사람이 일일이 승인할 거라면 사람이 하는 것과 다름없다" — 사람 승인
> 게이트를 폐기하고, RED 직접 쓰기를 아래 3조건 + 기계 안전판으로 허용한다:
>
> 1. **사람 명령 한도**: 사용자가 직접 명령한 태스크에서만 (`thread_context.task_origin == 'user'`
>    — WS 채팅×2·`/system-ai/chat`·에이전트 명령 HTTP 4곳만 세팅. 스케줄러·자가점검·위임
>    사슬·외부 채널 = 미세팅 = fail-closed). 자율 태스크는 종전대로 `patch` 제안만.
> 2. **최고 모델 전용**: 기어가 절약이어도 REPAIR 태스크의 실행 모델은 고급으로 승격
>    (`model_resolver` `system_repair→고급 고정` — reflex→경량 고정의 역방향).
> 3. **의식 각성**: 의식 토글 OFF 여도 REPAIR 는 THINK(의식 framing) 경로를 강제.
>    의식 프롬프트에 수리 안전수칙 2조(사용자 명령 한도·실측 검증 달성기준) 추가.
>
> **감지**: `#repair` 태그(무조건) → 결정론 단서(구역어+수리동사, 의식 OFF 에서도 작동,
> Reflex 보다 먼저) → 무의식 분류기 REPAIR 범주. 미탐 시 게이트 거부 메시지가 재명령 안내.
>
> **★한도는 셋이다 — 넷이 아니었다 (2026-08-25, ep1915 수리)**: 위 3조건을 배선한 코드가
> 선언에 없는 넷째(`is_system_ai`)를 함께 걸고 있었다. '누가 명령했나'(`origin=='user'`)와
> '누가 실행하나'(시스템 AI/프로젝트 에이전트)는 다른 축인데, 넷째가 하필 이 헌법이 정당한
> 진입점으로 이름 붙인 **"에이전트 명령 HTTP"**(폰 원격런처 → 프로젝트 에이전트)를 배제했다.
> 게다가 그 표면은 `cognitive_stream` 을 우회해 `#repair` 가 읽히는 자리를 지나지도 않았다
> (실측: 그 턴의 로그에 `[무의식] 분류` 0줄 → 그랜트 미발급 → RED 거절). 조건은 이 문서대로
> 되돌리고, 표면 포크는 관문 `backend/test_user_surface_pipeline.py` 로 잠갔다 —
> `set_task_origin("user")` 를 세우는 함수는 자기 호출 그래프에서 `cognitive_stream` 에
> 닿아야 한다. **범위는 넓어지지 않는다**: origin 세터는 지금도 여기 적힌 넷뿐이고
> (위임 사슬·스케줄러·채널 = 미세팅 = fail-closed), `origin` 은 threading.local 이라 위임으로
> 상속되지 않으며, 기계 안전판은 실행 주체와 무관하게 그대로 걸린다.
>
> **기계 안전판 (Floor #3+#5, 오히려 강화)**: 그랜트된 RED 쓰기는 ①사전 구문검증
> (compile — 깨진 .py 는 라이브에 닿기 전 거부) ②원본 백업(파일당 최초 1회,
> `data/system_ai_state/red_backups/<task>/`) ③backend .py 면 분리 워치독
> (`backend/red_watchdog.py`, start_new_session — 서버가 죽어도 생존)이 리로드 후
> `/health` 를 확인, 죽어 있으면 백업 복원+touch 재기동+OS 알림 자동 롤백.
>
> **★keeper 표식 = 기계 소유 (2026-08-17 개정)**: backend/*.py 쓰기 직전 `_keeper_pause`
> 가 `data/backend_keeper_off` 를 세우고(내용 `auto <task>` = 소유자 표시, 매 쓰기마다
> 갱신 = 심장박동), 회수는 워치독이 어느 결말에서든(`__main__` 의 finally) 한다.
> 놓쳐도 keeper 가 `PAUSE_TTL`(900초) 만료로 감시를 재개한다. **왜**: 옛 규약("작업 전
> touch, 작업 후 rm")은 자기수리에서 원리적으로 완주 불가 — 편집이 부른 리로드가
> 회수 단계를 실행할 턴을 죽인다(실측: 표식이 남아 감시가 몇 시간 멎음). 일반 원칙 =
> **자기 죽음 이후에 실행돼야 하는 단계는 죽음을 넘는 프로세스가 소유한다.**
> 사람이 손으로 세운 빈 표식은 워치독이 건드리지 않는다(의도적 정비 창).
>
> **★결말의 회수 (2026-08-17)**: 수리의 판정은 **자기 턴이 죽은 뒤에** 난다 — 워치독이
> `result.json` 에 적지만 그 파일을 읽는 쪽이 없어서, 사용자 자리에서는 성공한 수리와
> 그냥 멎은 수리가 구별되지 않았다. ①워치독이 **성공·판정미완에도** OS 알림(종전엔
> 실패만) ②`backend/datastore/red_report.py` 가 미보고 판정을 회수해 다음 턴의 0단계
> 연상에 `<repair_outcome>` 으로 얹는다(`cognitive_recall._pending_repair_scent` —
> 파일 읽기뿐·없으면 0토큰·`announced_at` 표식으로 한 번만).
> 원칙: **죽음을 넘긴 판정은 다음 턴의 입이 닫는다.**
>
> **★그 입은 수리한 에이전트다 (2026-08-25, 사용자 확정)**: 옛 게이트는 '시스템 AI 만'
> 이었고 그건 수리 주체가 하나라는 전제였다 — 같은 날 한도가 정본대로 복원되며 깨졌다.
> 게이트를 신원('내가 시스템 AI 인가')에서 **소유**('이 판정이 내 것인가')로 옮긴다.
> 주인 열쇠(`red_report.owner_key` — 규칙 한 벌. 시스템 AI 는 예약 id `system_ai` 하나로
> 접는다: 그 몸은 채팅 턴에선 신원을 안 세우고 상주 루프에선 세워, 안 접으면 자리마다
> 다른 열쇠를 받는다)를 **쓰기 시점에** 원장에 박는다 — `handler._red_write_prepare` →
> manifest → `red_watchdog` → `result.json`, 그리고 `repair_staging` 세션 원장 → 지연
> 결말(분리 수행자 red_apply 에겐 수리한 턴의 컨텍스트가 없으므로 **원장에서 실려 와야**
> 한다. 거기서 물으면 언제나 '시스템 AI' 라는 오답이 나온다). 회수가 한 번뿐이라 엉뚱한
> 입이 먼저 주우면 표식만 찍히고 명령한 창에서는 영영 안 보인다 — 침묵 실패라 관문으로
> 잠갔다(`backend/test_repair_verdict_owner.py` O1~O6).
>
> **배선**: 그랜트 원장 `backend/datastore/red_grant.py`(프로세스 전역 — claude_code 의 MCP→HTTP
> 재진입 심을 task_id 매칭으로 건넘), 발급/회수는 `agent_pipeline` REPAIR 분기/finally 만.
> **만료는 시계가 아니라 발급 턴의 생사로 판정한다**(2026-08-23, ep1746): 그 턴이 이 프로세스에
> 열려 있는 동안(`episode_logger` 의 열린-턴 집합 — `/health` 의 `live_turns` 와 같은 출처)
> 그랜트는 만료되지 않고, 턴이 닫힌 뒤에는 **마지막 사용**부터 재는 유휴 한도로 회수한다
> (시계의 용도는 'finally 가 못 돈 누수' 하나뿐 — 프로세스가 죽으면 인메모리 그랜트도 같이
> 죽으므로 크래시는 시계가 막는 대상이 아니다). 거절은 fail-closed 그대로 두되 **사유**
> (만료/미발급/주인 불일치)를 구별해 말한다 — 뭉갠 거절 문구가 막힌 수리 턴의 자기 오진을
> 낳았다.
> 게이트 `system_essentials/handler.py` `_red_zone_violation` + `_red_write_prepare/finalize`.
> **구역 재구획**: `backend/static/` 비-py 정적 자산은 RED 제외(프로세스가 import 하지
> 않아 reload 절단 원리적 불가 — 2026-08-04 자막 수리 하루 지연의 교훈).
> **디렉토리 단위 RED 복사·이동·삭제는 그랜트가 있어도 금지**(파급 과대).
> 승인 원장(`install_approvals.json`)은 그랜트로도 못 쓴다(공급망 게이트는 별개 헌법).
>
> **안전장치 자기검증 (③검증자 없는 영역 보강, 2026-08-05 같은 날 후속)**: 안전장치
> (게이트·그랜트·백업·워치독)를 수리하다 미묘하게 망가뜨리면 /health 만으로는 못 잡는다
> (서버는 멀쩡히 뜬다 = 침묵 결함). `scripts/red_safety_selftest.py` — 임시 저장소에서
> 안전장치의 *기능*을 실측하는 기계 채점 배터리(24검사·~1초·라이브 무접촉, 프롬프트
> 기계 계약[분류 토큰 4종] 포함) — 를 3곳에 배선:
> ① 워치독: 안전장치 파일(`SAFETY_SUFFIXES`)이 수정된 태스크는 헬스체크 후 스모크까지
>   통과해야 healthy(실패=자동 롤백+알림) ② World Pulse 자가점검 12h 순찰
>   (`__static__:red_safety`, ★subprocess 필수 — 인프로세스면 selftest 의 그랜트 발급이
>   라이브 게이트를 순간 연다) ③ pre-commit(안전장치 파일 스테이징 시 통과 강제).
> 또한 게이트 파일(handler.py) 자체는 data/ 구역인데도 그랜트 필요로 승격(`_SELF_FILE`
> — 게이트를 지키는 게이트) + 수정 시 백업·워치독 대상.
>
> **★격리 스테이징 (2026-08-17) — 수술 순서를 뒤집는다:**
>
> 위 헌법(08-05)은 RED 를 **라이브에 직접** 쓰고 사후에 맥을 짚는 구조였다. 그래서
> 검증이 둘 다 사후적이었다 — 사전은 `compile()`(구문)뿐이고 사후는 `/health 200`
> (= "프로세스가 살아는 있다")뿐. keeper 일시정지·분리 워치독·다음 턴 판정 회수는
> 전부 *편집자가 자기 편집에 죽는다*는 전제 위의 수습 장치였다.
>
> ```
> (구) 쓴다 → 리로드 → 죽는다 → 워치독이 맥을 짚는다 → 다음 턴이 판정을 읽는다
> (신) 격리 사본에 쓴다 → 거기서 검증한다 → 통과분만 한 번에 옮긴다 → 리로드 1회
> ```
>
> - **스테이징**: 그랜트된 RED write/edit 은 `_red_stage` 가 세션 worktree
>   (`.worktrees/repair-<task>`)로 돌린다. 라이브 무변경 = **리로드 없음 = 편집자가
>   자기 턴 안에서 살아 있다** — 검증 결과를 읽고 고쳐 쓸 수 있다. 되읽기(read)도
>   *자기가 건드린 파일만* 격리본을 본다(안 건드린 파일은 라이브 그대로).
> - **★베이스는 라이브 작업 트리(HEAD 아님)**: 세션 생성 시 `git diff HEAD` 를
>   best-effort 로 얹고, 파일을 처음 건드릴 때 **라이브 원본에서 씨를 뿌린다**(권위).
>   HEAD 를 베이스로 쓰면 적용이 미커밋 라이브 작업을 조용히 되돌린다 = 데이터 손실.
> - **검증 배터리**(`repair_staging.verify`, 실측 2.5초 / frontend 포함 시 +3초):
>   live_sync → 삭제면 `delete_no_orphan_imports` → py_compile → **import 스모크**
>   → IBL 삼각(plain build) → `.ts/.tsx` 가 끼면 **frontend tsc** → 안전장치 파일이면
>   `red_safety_selftest`.
>   ★import 스모크가 새 축이다 — 사전 `compile()` 이 원리적으로 못 잡는 부류
>   (ImportError·모듈 최상위 NameError·순환 import)를 잡는다. **브릭 원인 대부분이
>   거기 산다.** 스모크는 `INDIEBIZ_BASE_PATH` 를 worktree 로 박아 격리한다(라이브
>   `data/` 를 물려받으면 격리가 깨진다).
> - **적용** `[self:patch]{op:"apply"}`: 검증 전량 통과 → 준비 전량 통과 →
>   쓰기 → 워치독. **부분 적용 없음** — 한 파일이라도 막히면 아무것도 안 나간다.
>   적용은 기존 `_red_write_prepare/_red_write_finalize` 를 그대로 통과하므로
>   **백업·keeper 일시정지·분리 워치독·자동 롤백이 전부 그대로 이어받는다.**
>   스테이징은 그 *앞에* 층을 하나 더 놓을 뿐 무엇도 대체하지 않는다.
> - **적용 안 함이 기본 실패 모드**: 격리의 장점(라이브 무변경)이 곧 약점이라 apply 를
>   빠뜨린 수리는 아무 흔적이 없다. → `red_report.collect_unapplied` 가 미적용 세션을
>   다음 턴 연상에 `<repair_staged>` 로 얹는다(판정 회수와 같은 원리, 다만 표식을
>   남기지 않는다 — 지나간 사건이 아니라 *지금도 참인 상태*라 해소될 때까지 보인다).
>   **자동 적용은 하지 않는다** — 응답이 이미 나간 뒤 적용하면 검증 결말을 못 본 채
>   "고쳤다"가 되어 거짓 보고가 된다.
> - **폴백**: git 이 없는 몸(설치본·폰)이나 그랜트 없는 경로에서는 세션이 안 열리고
>   종전 라이브 직행으로 떨어진다(안전판은 그대로).
>
> **★원장 단일화 (2026-08-18 후속) — 격리가 둘이었다**
>
> 사정거리(문 하나)와 **쌍둥이 문제**가 하나 더 있었다: 격리 기구 자체가 둘이었다.
>
> ```
> (구) propose → .worktrees/selfpatch-<ts> + patch_proposals/     ← 적용 경로 없음
>      apply   → .worktrees/repair-<key>   + repair_sessions/     ← 제안을 못 봄
> ```
>
> 같은 `[self:patch]` 어휘의 op 라 파이프라인처럼 보이는데 `op_apply` 본문에 proposal
> 언급이 0건이었다 — 게이트에 막혀 propose 로 간 수리는 **재작업 말고는 라이브로 갈 길이
> 없었다**(실측: 제안 7건 누적·적용 0건·5건은 워크트리도 사라진 죽은 기록).
>
> 이제 **제안도 세션이다**: `op_propose` 가 `ensure_session(key="proposal-<ts>")` +
> `stage_file` 을 그대로 쓴다. 워크트리 접두사·원장·생애주기(`_cleanup_old`)가 하나로
> 합쳐지고 apply/status/discard 의 이중 분기가 사라졌다(코드 순감). 그랜트 요구는
> apply 쪽에 그대로라 자율 태스크의 자가적용 금지는 유지된다.
>
> 통합이 덤으로 고친 것 셋:
> - **씨가 HEAD 가 아니라 라이브 원본**(`stage_file` 규약) — 옛 propose 는 `old_string` 을
>   HEAD 내용에 맞춰봐서 미커밋 라이브와 어긋나면 헛발질했다.
> - **같은 초 충돌**이 조용히 합쳐지지 않는다(접미사로 가름). 옛 구현은 worktree 생성 실패.
> - **`read_session` 을 `load_session` 에서 분리**: 후자는 *staging 인 세션* 접근자라
>   닫힌 세션을 `None` 으로 감춘다. 그걸 존재 판정에 쓰면 ①적용된 제안에 "그런 제안이
>   없습니다"라 답하고 ②키가 비었다고 오판해 재사용 → `ensure_session` 이 **이전 격리본을
>   지우고 원장을 덮어쓴다**(조용한 파괴). 존재·상태 질의는 `read_session`.
>
> 옛 원장은 **좌초 감지 읽기 전용**으로만 남는다(`list_legacy_proposals` → status 가 알림).
> 통합 시점 살아있는 제안 0건이라 이관은 없었다.

> **★★이 격리의 사정거리 — 파일이 아니라 문 하나다 (2026-08-18 정정)**
>
> 위 서술은 격리가 *backend 를 지킨다*처럼 읽히지만, 실제로 세운 불변식은 그게 아니다.
>
> ```
> (세운 것)   REPAIR 경로가 self:write/edit 로 고칠 때 격리된다   ← 코드 경로의 성질
> (필요한 것) backend/*.py 는 격리를 거쳐야만 바뀐다              ← 파일의 성질
> ```
>
> 게이트(`system_essentials/handler.py` `_red_zone_write_block`)는 `[self:write]`·
> `[self:edit]` 가 지나는 자리에 있고, 그랜트는 인지 파이프라인 REPAIR 경로만 발급한다.
> **그 문을 안 쓰는 편집자는 그냥 통과한다:**
>
> | 문 | 격리 | 비고 |
> |---|---|---|
> | `[self:write]`/`[self:edit]` + REPAIR 그랜트 | ✅ | 설계된 경로 |
> | 아웃오브프로세스 Claude Code 세션(자체 Edit/Bash) | ❌ | 그 손이 이 프로세스 밖이라 **원리적으로 차단 불가** |
> | `[self:script]{op:"run"}` 이 실행하는 스크립트 | ❌ | Phase 1 미구현 |
> | `run_command` | ❌ | Phase 1 미구현(위 '미구현' 줄) |
> | 패키지 핸들러 자신의 `open()` | ❌ | 게이트를 안 거침 |
> | `_find_repo_root()` 미탐지 | ❌ | 의도된 **fail-open** — 편의 게이트로는 옳지만 격리 바닥으로는 아님 |
>
> **2026-08-18 실측**: `data/system_ai_state/repair_sessions/` 디렉토리가 **아예 없었다**
> (세션 시작 시 `makedirs` 하고 청소는 파일만 지운다 = 한 번도 열린 적 없음).
> `.worktrees/repair-*` 0건. 즉 08-17 에 만들어 배터리를 통과시킨 뒤로 **라이브에서
> 한 번도 돈 적이 없다** — 실제 편집이 이 길로 오지 않았다. 같은 날 조사에서
> 개명 전 세대의 고아 격리본(`.worktrees/selfpatch-20260817_094955`)이 미적용
> `backend/surface/api_showcase.py` 편집을 품은 채 하루 넘게 떠 있던 것도 함께 발견.
>
> **대응(2026-08-18)**: 차단을 넓히지 않는다 — 아웃오브프로세스 편집자를 못 막는 한
> "닫았다"는 착각만 다시 만든다. 대신 **가시성**을 넣었다:
> `scripts/check_red_drift.py` 가 *미커밋 `backend/**/*.py` 인데 격리 세션이 안 붙잡은
> 것* + *원장 없는 고아 격리본* 을 본다(원장은 새로 안 만든다 — **git 이 원장**이고
> 커밋이 곧 사람의 승인이라 저절로 해소된다). 24시간 이내는 '작업 중'으로 통과,
> 그보다 오래되면 실패. 자가점검 순찰 §1H(`world_pulse_health._run_red_drift`)로 12시간마다 돈다.
> - **이동·복사·삭제도 같은 층**(같은 날 후속): 세션 기록이 `op: write|delete` 두 종을
>   나른다. 삭제는 라이브를 놔둔 채 **격리 사본에서만** 지운다(그래야 검증이 *그 파일이
>   없는 세계*를 본다). 이동은 '대상 쓰기 + 원본 삭제' 한 쌍이라 **양쪽이 다 적재
>   가능할 때만** 격리로 간다(`can_stage` 선판정 — 한쪽만 가면 라이브가 반쪽 상태가
>   된다). 적용 순서는 **쓰기 먼저, 삭제 나중**(대상에 생긴 뒤 원본이 사라진다).
>   삭제도 apply 가 백업을 뜬 뒤 지우므로 워치독 롤백이 되돌릴 수 있다.
> - **★삭제 전용 게이트 `delete_no_orphan_imports`**: 쓰기의 위험은 *그 파일이 깨지는*
>   것이라 그 모듈을 import 해보면 잡힌다. 삭제의 위험은 반대다 — **남의 import 가
>   깨진다.** 지워진 모듈은 import 해볼 수조차 없으니(없는 게 정상) 스모크로는 원리적
>   으로 안 잡힌다. 그래서 격리 사본의 추적 .py 를 훑어 아직 그 모듈을 import 하는
>   파일을 찾아 이름을 대고 막는다.
> - **★라이브 파생물 게이트 `live_derived`** (2026-09-01 신설, ep2519 봉합): 격리에서
>   난 초록이 **라이브 판정으로 승격되던** 자리를 닫는다. `ibl_triangle` 게이트는 격리
>   사본 안에서 plain build 를 돌리는데, 그 빌드는 검사만 하는 게 아니라 `ibl_nodes.yaml`·
>   `tool.json` 같은 **파생물을 워크트리에 쓴다**. 수리 에이전트의 셸 cwd 도 워크트리라,
>   이어서 손으로 돌린 `build --check` 도 초록이고 `git status` 에도 파생물이 갱신된 것처럼
>   찍힌다. 그 상태로 `discard` 하면 워크트리와 함께 **빌드 산출물이 같이 죽고** 라이브는
>   처음 그대로 낡아 있다. 실측(ep2519 자막 합성 옵션): `ibl_actions.yaml`·핸들러·렌더러엔
>   새 낱말이 살아 있는데 `data/ibl_nodes.yaml` 에는 없어서, **시스템이 제 낱말을 못 보는
>   채로** 턴이 끝났다. 관문은 "빌드하면 통과한다"만 증명했지 "라이브가 빌드돼 있다"를
>   증명한 적이 없다.
>   처방을 문장으로 돌려주지 않고 **집행**한다 — 파생물은 기계 소유이므로(`data_ownership`
>   derived · CLAUDE.md "직접 편집 금지, 다음 빌드가 되돌린다") keeper 표식과 같은 부류다:
>   기계가 세우고 기계가 회수한다. 사람/AI 의 다음 단계로 미루면 그 단계는 **턴이 죽는
>   자리에서 영영 안 온다**(ep2519 는 백엔드 종료로 끝났다). 갈래는 둘로 정직히 나눈다 —
>   **드리프트**는 라이브 재생성으로 닫고 무엇이 재생성됐는지 이름을 대며 초록,
>   **소스 결함**(빌드 자체가 검증에 걸림)은 재생성으로 못 닫으므로 빌더의 말 그대로 빨강.
>   방아쇠는 목록을 새로 두지 않고 빌더에게 묻는다(`--inputs-regex`, pre-commit 훅과 같은
>   출처 — 목록을 두 벌 두면 한쪽만 늙는다). 자리는 `verify()`(propose·apply)와
>   **`op_discard()`(워크트리를 지우기 전)** 둘 다. 같은 날 `discard` 응답에서 무조건
>   "라이브는 무변경이었습니다"라고 말하던 문장도 걷었다 — 적재분 기준으로만 참인데,
>   ep2519 에선 라이브에 이미 6파일이 바뀐 채여서 그 문장이 '아무것도 안 남았다'는 오독을
>   거들었다. 이제 남은 미커밋을 세어서 말한다. 가드: `test_repair_staging.py` S17.
> - **★frontend 타입검사 게이트 `frontend_tsc`** (2026-08-22 신설): RED 구역은
>   `("backend", "frontend", "scripts")` 인데 관문은 전부 파이썬용이었다 — **타입은
>   아무도 안 봤다**(실측: 이 경로로 `.tsx`/`.ts` 10건이 무검사 통과. NarrationStudio.tsx
>   등). 브릭은 아니지만 빌드 때까지 조용한 부류다. 세션에 `.ts/.tsx` 가 끼면
>   격리 사본에서 `tsc -p tsconfig.app.json --noEmit`(실측 3초). 두 가지를 **빌린다**:
>   ①`node_modules` — 의존성은 델타가 아니므로 라이브 것을 심링크로 읽고 **검증 후 즉시
>   회수**(격리 사본에 남기면 워크트리 청소가 라이브를 향한다) ②**선행 상태** — 실패했을
>   때만 라이브에서 한 번 더 돌려(읽기 전용) *이 델타가 새로 만든 오류*만 빨강으로 친다
>   (`build --check` 를 격리에 못 들인 이유였던 '선행 파손 볼모' 문제가 여기선 이렇게
>   풀린다. 자리 비교는 줄·칸을 빼고 파일+메시지로 — 델타가 줄을 밀어도 유령 신규가 없게).
>   ★검사할 수 없으면(node_modules 미설치·tsc 부재) 초록도 빨강도 아닌 **건너뜀을 정직히
>   적는다** — 검사 불능이 apply 를 영원히 막는 것은 import 스모크가 패키지 모듈을
>   탈락시켜 apply 를 막던 2026-08-18 부류의 재생산이다. 삭제도 방아쇠에 넣는다(프런트엔
>   고아-import 검사가 따로 없는데, 격리 사본엔 이미 그 파일이 없으니 tsc 가 그대로 잡는다).
> - **남은 갭(정직하게)**: **행동 검증은 여전히 적용 이후**다 — 격리 사본에서 잡는 것은
>   구조적 브릭이고, 라이브 프로세스의 실제 동작은 워치독·다음 턴이 판정한다. 디렉토리
>   단위 RED 복사·이동·삭제는 종전대로 **금지**(그랜트가 있어도 — 파급 과대).
>
> **배선**: `data/packages/installed/tools/system_essentials/repair_staging.py`(본체) +
> handler 의 `_red_stage`/`_patch_op`(이음매 — RED 구역 정의의 단일 출처는 계속
> `_red_zone_violation` 하나) + `red_report.collect_unapplied` + `agent_pipeline` finally
> 경고. 배터리: `backend/test_repair_staging.py`(**63검사**, 임시 git 저장소·라이브 무접촉).
>
> 아래 본문의 Floor #4 절은 역사 기록으로 보존한다.

> **구현 상태 (2026-07-12 갱신):**
> - **Floor #1 ✅ 구현·커밋** (`30a4116`): RED 구역 직접 쓰기 차단. `system_essentials/handler.py` `_validate_path_in_scope` 에 `_red_zone_violation`(realpath 정규화, repo 루트 backend+frontend 독립 탐지) 게이트. 쓰기 계열 단일 초크포인트 전부 커버, 읽기는 유지. 에피소드 551 구멍 폐쇄.
>   - **개정 (2026-08-27, 48회차 별건)**: 구역의 기준 루트를 판정자의 집(`_REPO_ROOT`)에서 **과녁이 속한 몸의 루트**로(`red_zone_family.body_root_of` — 본체와 그 git 워크트리는 한 가족, 남의 저장소는 종전대로 허용). 종전 판정은 라이브 게이트가 격리 워크트리의 RED 를(거울상으로 워크트리 게이트가 본체의 RED 를) 못 봤다 — Floor #2 의 격리 사본이 정작 Floor #1 밖이었다. 실측·근거는 `red_zone_family.py` docstring, 가드는 `test_red_zone_body_family.py`.
> - **Floor #2 ✅ 구현·커밋** (`9838830`): `[self:patch]`(액션 150, RED 전용). git worktree(HEAD 격리 사본)에만 기록 + py_compile·plain build 기계검증 + `data/system_ai_state/patch_proposals/` 기록(★그 별도 원장은 2026-08-18 에 세션 원장으로 통합됐다 — 아래 '원장 단일화'). 라이브 무변경. **주의**: `build --check` 의 코퍼스/fixture/gitignore-매니페스트 검사는 런타임 DB·미추적 파생물 의존이라 바레 worktree 에서 못 돎 → 격리 게이트는 plain build(삼각 검증)로 한정, 완전 검증은 사람 머지 시(pre-commit).
> - **Floor #2·#3 △ 사용자 경로까지 확장** (2026-08-17, 위 '격리 스테이징' 절): 격리가
>   `patch`(자율 태스크 전용)에만 있고 실제로 도는 수리 경로는 라이브 직행이던
>   비대칭을 해소 — **단 `self:write`/`edit` 문에 한해서다**(사정거리 표 참조.
>   2026-08-18 정정: 다른 문은 여전히 라이브 직행이고 실사용 세션 0건이었다). Floor #3 에 **import 스모크**가 합류(사전 compile 이 못 잡던 축).
>   액션은 늘지 않았다 — `patch` 에 op 축(propose/apply/status/discard) 추가.
> - **미구현**: Phase 1(run_command 리다이렉션 게이트) · Floor #3 의 표적 스모크(변경
>   동작의 실제 1회 실행 — 라이브 프로세스가 필요해 원리적으로 적용 이후로 남는다).
> - **미이관**: `[self:patch]` 해마 시드 용례 없음 → 다음 임베더 재학습 시 흡수.
>   (그때까지는 tool description 과 의식 프롬프트 수리 안전수칙 3조가 apply 를 이끈다.)

## 0. 왜 이 문서인가 — 실측된 실패

에피소드 551에서 시스템 AI(gemini-3.1-flash-lite, 절약 기어)는 **"자기 수정을 안전하게 하는 법"**을 묻자, 그 자리에서 자기 `backend/`에 새 파이썬 파일 2개를 직접 써넣었다:

- `backend/validate_code_integrity.py` (AST 구문 검사기)
- `backend/checkpoints/safe_update_engine.py` (`from backend.xxx` import가 애초에 죽는 파일)

둘 다 **고아 코드**(아무도 import 안 함)였고, **import조차 안 되는 깨진 코드**였으며, 시스템은 이를 **자기 채점으로 ACHIEVED** 판정했다. 즉 한 턴에 네 가지 실패가 겹쳤다:

1. **게이트 없는 자기 편집** — 라이브 `backend/`를 IBL 쓰기로 직접 수정
2. **자기 채점** — 실행 주체가 세운 기준으로 스스로 합격
3. **능력 투영** — 열린 설계 문제를 "파일 하나 쓰기"로 축소
4. **거짓 완료 기억 각인** — 심층기억에 "구현 완료" 오염

에피소드 552에서 **같은 질문을 opus(최대 기어)로** 돌리자 정반대로 행동했다 — 읽고 조사하고 기존 안전장치를 인식하고 파일을 안 고쳤다. 이 대비가 이 설계의 출발점이다.

## 1. 원칙 — 천장이 아니라 바닥

- **소프트 가드(천장)** = "좋은 모델이면 알아서 지킨다." 프롬프트 훈계. opus는 도달했고 gemini는 무시했다. **모델 품질에 안전을 건다.**
- **구조적 바닥** = "어떤 모델이든, 프롬프트를 무시하든, 코드 구조가 이 선 밑으로 못 가게 막는다." **모델 독립적.**

이 시스템의 헌법 원칙 그대로다 — *튼튼함 = 모델 독립성, 분산을 author-time으로*. 지금은 "운전 잘하세요" 표지판(프롬프트)은 있는데 **가드레일(구조)이 없다.**

**결론: 강한 티어로 라우팅해 천장을 올리되(즉효), 기어와 무관하게 버티는 구조적 바닥을 깐다(근본). 둘 다.**

## 2. 구역 정의 — 무엇을 자기수정하나

핵심 이음매: **실행 중인 몸을 브릭할 수 있는가.**

| 구역 | 경로 | 성격 | 리로드 | 자기수정 |
|------|------|------|--------|----------|
| 🟢 **GREEN** (내용) | `data/` 하위 순수 데이터 — 가이드, 프롬프트, `ibl_nodes_src/*.yaml`, 코퍼스, 매니페스트, 기억, `outputs/`, `projects/` | 선언적 데이터, 실행 코드 아님 | mtime 핫리로드, **프로세스 재시작 없음** | **허용** (가역, 브릭 불가) |
| 🟡 **YELLOW** (패키지 코드) | `data/packages/installed/**/handler.py`, `tool.json` | 실행되는 코드 + IBL 어휘. 시스템 AI의 `project_path=data/`라 **상대경로로 도달 가능** | tool_loader mtime 재임포트 / `/packages/reload` | **검증 게이트 통과 시만** (`build --check`) |
| 🔴 **RED** (몸) | `backend/*.py`, `frontend/*`, `scripts/*.py`, 루트 `*.py`(`api.py`,`mcp_server.py`) | 실행 중인 유기체의 substrate | **`backend/*.py` 편집 = uvicorn 재시작 = WebSocket·in-flight 절단(자해)** | **직접 금지 → 제안·격리·검증·승인·가역** |

**실측 근거:**
- 시스템 AI의 `project_path = DATA_PATH = data/` (`system_ai_core.py:120, 453`). → **상대경로 쓰기는 이미 `data/`(GREEN)에 갇힌다.** 551이 RED로 탈출한 유일한 통로는 **절대경로**.
- `uvicorn.run(reload=not is_production, reload_delay=2.0)` (`api.py:435-451`). `backend/*.py` 편집만 프로세스 재시작. `data/` 편집은 재시작 없음.

## 3. 다섯 안전판 — 정확한 위치에 매핑

### Floor #1 — 구역 게이트 (쓰기 chokepoint에 코드로 강제) ★최고 레버리지

**위치:** `data/packages/installed/tools/system_essentials/handler.py` → `_validate_path_in_scope(path, project_path)` (L120-135).

**현재 구멍:** 절대경로는 `if os.path.isabs(path): return None`으로 **무조건 통과**. 551이 정확히 이 구멍으로 `/Users/.../backend/...`에 썼다.

**호출처(이 함수 하나가 5개 도구를 커버):** `write_file`(L249), `edit_file`(L512), `copy_path`(L587), `move_path`(L616), `delete_path`(L638).

**변경:** 절대경로에 대해 **RED 거부 리스트**를 적용. 몸을 브릭하는 표면만 정확히 막는다(deny-list이 allow-list보다 이 목적에 견고 — 브릭 표면이 유한하고 명확하므로):

```python
# _validate_path_in_scope 안, os.path.isabs(path) 분기
REPO = _repo_root()                      # indiebizOS 루트
DENY = [f"{REPO}/backend", f"{REPO}/frontend", f"{REPO}/scripts", f"{REPO}/.git"]
abs_path = os.path.realpath(path)        # 심링크·../ 정규화 (우회 차단)
for zone in DENY:
    if abs_path == zone or abs_path.startswith(zone + os.sep):
        return f"보호된 실행 영역입니다(자기수정 안전 바닥): {abs_path}. RED 구역은 patch 경로로만."
```

- **읽기는 무제한 유지** — `read_op`/`list_directory`는 이 함수를 안 거친다. opus의 조사 행동(backend 읽기)은 살린다. 읽기는 브릭 못 시킨다.
- YELLOW(`data/packages/**/handler.py`)는 GREEN 스코프라 통과하지만 → Floor #3의 `--check` 게이트로 넘긴다.
- **이 한 블록이 에피소드 551을 원천 차단한다.**

**잔여 구멍 — `run_command`** (L541-578, `shell=True`, `cwd=project_path`): 셸 리다이렉션(`> backend/x.py`)으로 쓰기 게이트를 우회 가능. `is_dangerous_command`(L138)가 `rm/sudo/chmod`는 이미 `__REQUIRES_APPROVAL__`로 보낸다. **확장:** 절대경로 쓰기·리다이렉션(`>`, `>>`, `tee`, `dd`)이 DENY 구역을 향하면 승인 경로로. (셸은 튜링완전이라 완벽 차단은 불가 → run_command는 §6 잔여위험으로 명시.)

### Floor #2 — 격리 (라이브 트리 직접 수술 금지)

RED 변경은 라이브 파일이 아니라 **git worktree(격리 사본)**에만 쓴다. Floor #1로 시스템은 이제 RED를 직접 못 쓰므로, RED를 건드리는 **유일한 정규 통로**는 새 통제 채널이다:

**신규 어휘 `[self:patch]`** (scope: workspace, RED 전용):
- 입력: 대상 파일(RED), 새 내용 또는 diff, 근거
- 동작: 격리 세션 worktree(`.worktrees/repair-proposal-<ts>`)에만 기록 → **라이브 트리 무변경**
  (2026-08-18 통합 전에는 `selfpatch-<ts>` + 별도 원장 `patch_proposals/` 였다 — 아래 '원장 단일화' 절)
- 산출: worktree 경로 + diff. 유기체는 자기 몸이 아니라 사본에만 손댄다.

**근거:** git repo 확인(`main`, 미커밋 2개뿐, worktree 실현 가능).

### Floor #3 — 객관 검증 (자기 채점 아님)

제안된 RED/YELLOW 패치는 **적용 전** 기계 게이트를 통과해야 한다. 전부 이미 존재:

| 게이트 | 도구 | 대상 | 판정 |
|--------|------|------|------|
| 구문·import | `python -m py_compile` + import smoke | 모든 .py | 예외 = FAIL |
| IBL 삼각 | `scripts/build_ibl_nodes.py --check` | YELLOW(handler/tool.json), ibl_nodes_src | exit 1 = FAIL |
| 통화·파이프 | `scripts/ibl_health_check.py` | fixture 116 + 골든 파이프 5 | RED = FAIL |
| 표적 스모크 | 변경 동작의 실제 1회 실행 | 바뀐 기능 | 예외/오답 = FAIL |

- **평가 에이전트의 "ACHIEVED"를 신뢰하지 않는다.** pass/fail 기계값만이 게이트를 연다. (551·548~550의 거짓 ACHIEVED가 여기서 막혔을 것.)
- worktree 사본에서 검증 → 라이브 오염 없음.

### Floor #4 — 사람/외부 승인 게이트 (RED 전용) ★대부분 이미 존재

**재사용:** `enter_plan_mode`/`exit_plan_mode` → `data/system_ai_state/plan_mode_state.json`(`phase=awaiting_approval`) → `SystemAIView`가 폴링해 승인 UI 표시 → 사용자 승인/거부.

**배선(추가):**
1. `patch` 산출 diff + Floor #3 검증 결과를 `plan_mode_state.json`에 실어 승인 화면에 노출.
2. **적용은 시스템이 아니라 외부 단계가** 수행 — 사용자가 "승인"하면 별도 apply 스텝(git merge worktree → 라이브 → 리로드)이 돈다. 유기체는 자기 몸에 substrate 변경을 **자가 적용하지 않는다.**
3. 거부 시 worktree 폐기.

**근거:** 승인 흐름 이미 구현됨(handler.py L1199-1245 + SystemAIView 폴링). 지금은 자유 편집에 쓰이는 걸, **RED 변경의 필수 관문**으로 승격.

### Floor #5 — 가역성 + 자동 롤백

- **적용 전 스냅샷:** apply 스텝이 `git commit`(또는 tag)으로 롤백 지점 확보.
- **적용 후 감시:** RED 적용 직후 `world_pulse_health` self-check를 즉시 1회 트리거(정규 12h와 별도).
- **자동 롤백:** 적용 후 N분 내 self-check가 RED거나 서비스 alive 실패면 → `git revert` + 리로드. `NotificationManager`로 사용자 통지.

**근거:** self-check + RED 알림 이미 존재(`world_pulse_health.py:729-741` → `NotificationManager`). 이걸 **"방금 자가적용한 패치"의 롤백 방아쇠**로 배선.

## 4. 무엇이 이미 있고, 무엇을 짓나

| 안전판 | 이미 있는 것 | 새로 짓는 것 |
|--------|--------------|--------------|
| #1 구역 게이트 | `_validate_path_in_scope` 뼈대, `is_dangerous_command` | 절대경로 DENY 블록(~10줄), run_command 리다이렉션 확장 |
| #2 격리 | git repo, worktree | `[self:patch]` 어휘 + worktree 배선 |
| #3 검증 | `build --check`, `ibl_health_check`, self-check | 세 게이트를 apply 전에 묶는 러너 |
| #4 승인 | plan_mode + SystemAIView 폴링 | diff/검증결과를 승인 화면에 배선 |
| #5 롤백 | self-check + RED 알림 + git | "최근 자가패치" 롤백 방아쇠 배선 |

**대부분 배선이지 신축이 아니다.**

## 5. 단계별 구현 계획

- **Phase 0 (최소·즉효, ~1시간):** Floor #1 절대경로 DENY 블록만. **551을 원천 차단.** `build --check` 통과 확인 + 스모크(backend 절대경로 쓰기 거부 / data·outputs 쓰기 정상 / backend 읽기 정상). handler.py 편집이라 `/packages/reload`로 라이브.
- **Phase 1:** run_command 리다이렉션 게이트 확장 → 승인 경로.
- **Phase 2:** `[self:patch]` + worktree 격리(Floor #2) + 검증 러너(Floor #3).
- **Phase 3:** 승인 배선(Floor #4) — plan_mode에 diff/검증 노출.
- **Phase 4:** 자동 롤백(Floor #5).

각 Phase는 독립적으로 가치가 있다. Phase 0만으로도 이번 사고는 재발 불가.

## 6. 잔여 위험 (정직하게)

- **`run_command`(shell=True)** 는 튜링완전이라 구조적 완전 차단 불가. 최선 = 위험 패턴 승인 + `cwd` 제한 + (강경책) 시스템 AI에게서 raw shell 쓰기 능력을 아예 거두고 파일 조작을 IBL 어휘로만. 이건 별도 결정.
- ~~**YELLOW(package handler.py) 라이브 핫리로드** 는 `--check` 없이 mtime로 반영될 수 있음 → Floor #3를 handler.py **쓰기 시점**에도 강제하려면 tool_loader 재임포트에 `--check` 훅을 걸어야. Phase 2 범위.~~ → **닫힘 (2026-09-01, ep2519 사슬 수리 — 두 달 미룬 청구서였다.** 어휘 부정합이 이 틈으로 라이브에 남은 실사고 후 집행): ①쓰기 시점 — `[self:write]/edit/copy` 가 빌드 입력(빌더 `--inputs-regex` 가 단일 출처)에 쓰면 그 자리에서 `sync_live_derived` 재생성 집행 + 패키지 `.py` 는 그랜트 무관 `compile()` 사전검증(`vocab_write_gate.py`). ②적용 시점 — `_perform_apply` 가 라이브에 쓴 **후** 재생성(verify 의 초록은 적용 *전* 신선도만 증명한다). ③핫리로드 시점 — tool_loader 가 handler.py mtime 로 낡은 모듈을 자동 무효화. ④순찰 — 부팅 + 일일점검이 아웃오브프로세스 편집(초크포인트 밖 넷: Claude Code 세션·`[self:script]`·`run_command`·핸들러 자신의 `open()`)의 잔여 드리프트를 재생성으로 닫는다(`world_pulse_health.enforce_derived_freshness`). ⑤빌더 정직화 — handler.py `SyntaxError` 는 폴백 초록이 아니라 빨강(`iblbuild_validators._handler_syntax_issue`; `_OP_DISPATCHERS` 부재 폴백은 정당한 호환 경로라 유지).
- **RED 그랜트 다중 슬롯 (2026-09-01)**: 옛 싱글턴 슬롯의 전제("시스템 AI 는 동시 런이 없다")가 위임 런으로 반증됐다 — ep2520 발급이 ep2519(storyteller 위임)의 그랜트를 덮어써 정상 경로(write 자동 적재→apply)를 봉쇄, propose/discard 루프로 밀어 넣었다. 그랜트는 task_id 별 슬롯에 살고 발급·회수는 자기 슬롯만 건드린다(`red_grant.py`).
- **소프트 가드 의존 잔재:** consciousness_prompt의 훈계는 유지하되(천장), 안전은 위 구조(바닥)에 건다.

## 7. 한 줄 요약

**시스템 AI의 `project_path`는 이미 `data/`(GREEN)다. 절대경로 구멍 하나가 RED를 열어놨을 뿐이다. 그 구멍을 코드로 막고(Floor #1), RED 변경은 "제안(worktree)→기계검증→사람승인→가역적용"이라는 이미-대부분-존재하는 관문으로만 흐르게 한다.**

## 지연 적용 (2026-08-19) — 적용 순간의 리로드를 턴 밖으로

격리 스테이징(08-17)은 스테이징 구간의 리로드를 없앴지만, **apply 순간의 한 번**은 남아
있었다 — backend/*.py 를 쓰는 즉시 uvicorn 리로드(reload_delay 2초)가 apply 를 부른 턴의
워커를 죽여, 최종 응답·주행기록 로그 버퍼(END 저장 전까지 메모리)·증류 데몬 스레드가
함께 죽었다. "자기 죽음 이후 단계는 죽음을 넘는 프로세스가 맡는다"(라이브 백엔드 편집
규약)를 적용 단계에 적용해 봉합했다:

- **op:apply = 예약**: backend/*.py 가 낀 세트는 검증 통과 후 잡 파일
  (`repair_sessions/<key>.apply.json`)을 남기고 분리 수행자
  `backend/datastore/red_apply.py` 를 spawn(start_new_session), 세션 상태
  `apply_scheduled`. frontend/scripts 만이면 리로드가 없으므로 종전대로 즉시 적용.
- **수행자 대기 프로토콜**: ①주행기록 `ended_at`(=응답 전송·버퍼 저장 완료, 상한 900초)
  ②증류 재합류 — cognitive_distill 의 finally 가 `refresh_episode` 로 log 를 한 번
  다시 쓴다(길이 변화 감지, 상한 120초). 에피소드 문맥 없으면 10초 유예만.
- **쓰기 직전 재검증**: 예약~수행 사이 라이브 드리프트를 live_sync 가 맞춘 뒤 관문 재실행.
  실패=라이브 무변경+세션 staging 복귀+`result.json`(deferred_verify_failed)로 다음 턴 보고.
- **그랜트 이월**: red_grant 는 인메모리 싱글턴 — 수행자의 프로세스-로컬 재발급은 턴에서
  검증된 그랜트의 이월이지 새 권한이 아니다(워치독이 그랜트 없이 백업 복원하는 것과 동류).
- **좌초 안전망**: 수행자가 죽어 `apply_scheduled` 가 30분+ 남으면 red_report 가
  `<repair_staged stranded_scheduled>` 로 다음 턴에 문다 — 다시 apply 하면 재예약(멱등).
- **예약 후 같은 세션에 쓰기가 이어지면** ensure_session 이 staging 으로 재개봉하고
  수행자는 낡은 예약을 취소한다(deferred_canceled).

이로써 세 보장이 완성된다: 주행기록(행+내용), 턴 내 최종 보고("검증 통과·적용 예약"),
증류 — 전부 리로드보다 **먼저** 끝난다. 헬스 판정은 종전대로 워치독→다음 턴.

### 예약을 낸 턴이 자기가 병목인 줄 알게 하기 (2026-08-25, ep1934)

위 설계는 **기계 쪽으로는 완결**이었지만 한 칸이 비어 있었다 — 예약을 낸 AI 가 자기 턴
안에서 적용을 기다린 것이다(실측: `task_sysai_3bb7d923`). 적용은 그 턴이 닫혀야 일어나므로
기다림은 원리적으로 성공할 수 없고, 대기 상한 900초가 통째로 탄 뒤 "턴이 끊긴 것으로 보고"
강행되며 끝났다. **안전망이 시간표가 된 것이다** — 상한이 하중을 받기 시작하면 정작 진짜
좌초(수행자 사망)를 아무도 구별하지 못한다.

원인은 지능이 아니라 **자기수용감각**이었다. 모델에는 "내가 죽은 다음"이라는 시제가 없어
자기 종료를 계획의 한 단계로 놓을 수 없고, 한편 하네스는 "검증하기 전엔 끝났다고 하지 마라"
고 요구한다. 두 요구가 충돌하면 AI 는 기다리는 쪽을 고른다 — 비합리가 아니라 나쁜 인센티브
아래의 합리다. 그런데 필요한 사실은 이미 손안에 있었다: 잡의 `episode_id` 가 곧 예약을 낸
그 턴이다. 없던 것은 정보가 아니라 **그걸 마주 들이미는 자리**였다. 셋을 채웠다:

- **(가) 예약 응답이 지목한다**: `_schedule_deferred_apply` 가 `waiting_on_episode`·
  `do_not_wait` 를 싣고, 문구가 "기다리는 대상이 곧 당신이다 / 폴링하지 마라 / 지금 턴을
  닫는 것이 이 작업의 완결이다 / 기다리면 상한 N초를 통째로 태운다"를 명령형으로 말한다.
  상한 숫자의 출처는 `red_apply.TURN_CLOSE_CAP_S` 하나다(`_turn_cap_s()` — 문구와 실제가
  갈라지지 않게). 프롬프트 훈계가 아니라 **기계가 사실을 들이미는 것**이 요점이다.
- **(나) 적용 후 검증을 위탁한다**: `[self:patch]{op:"apply", verify_cmd:"…"}` — 확인할
  명령을 예약과 함께 맡기면 수행자가 적용 뒤(몸이 다시 200 을 낼 때까지 대기, 상한 120초)
  실행해 결과를 다음 턴 보고에 싣는다(명령 상한 180초·출력 4000자). 권한은 새로 열리지
  않는다 — 그 턴이 이미 셸로 돌릴 수 있던 명령이고 바뀐 것은 **실행 시점**뿐이다. 리로드
  없는 즉시 적용 경로에서는 돌리지 않고 그렇게 말한다(이 턴이 살아 있으니 직접 확인).
- **(다) 상한 강행이 결말로 돌아온다**: `wait_turn_closed` 가 `observed`/`cap`/`no_turn`
  을 반환하고, 수행자가 판정 **옆자리**(`red_backups/<key>/followup.json` — 성공 경로의
  `result.json` 은 나중에 워치독이 통째로 덮으므로)에 남긴다. `red_report` 가 회수 때 합쳐
  `<wait outcome="cap">`·`<verify verdict="…">` 로 다음 턴 AI 의 얼굴 앞에 띄운다.

★상한 자체는 줄이지 않았다 — 짧게 하면 진짜로 끊긴 턴을 오판한다. 고칠 것은 상한이 아니라
**상한에 닿는 빈도**이고, 그것이 보이게 만드는 것이 (다)다.

검증=`backend/test_repair_staging.py` S4·S9·S10·S13 (배터리 77검사 — S11 오염 agent 폴백,
S12 frontend tsc, S13 예약-대기 계약 14검사 포함).
