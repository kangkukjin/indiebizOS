# 앱 공통 기반 — 다음 세션 핸드오프 (2026-10-05 밤)

독자: 이 일을 이어받는 구현자. 전제·판정은 [설치 목록](APP_COMMON_FOUNDATION_GAPS_2026_10_05.md)과 [앱 전수 감사](APP_IBL_GAP_AUDIT_2026_10_05.md)가 정본이고, 이 문서는 **어디까지 왔고 다음에 무엇을 어떤 순서로 하는가**만 적는다.
사용자 결정(2026-10-05): 판정은 구현자의 추천대로 진행한다. **코딩·문서·스프레드시트 앱의 재구성은 이 목록이 끝난 뒤** 조금씩 한다([계획서](APP_COMPOSITION_ON_IBL_PLAN_2026_10_05.md) §6-4~5 — 여기서는 다루지 않는다).

## 0 지금 상태 (main, 전부 커밋)

| 커밋 | 내용 |
| --- | --- |
| `15dcd020` | 표면 바인딩 ① (앱 템플릿 치환 폐지, 원문+inputs+declared_inputs) + 같은 날 다른 세션의 위임 수리·작업 공간 기반 |
| `85e8053a` `86506f57` | 잠든 패키지 어휘는 가드 경고, 잠든 패키지의 앱은 홈에서 숨김(캐시 키에 어휘 활성 판본) |
| `57b1a569` | 판본 2에 `@별칭` 노드 지정 이월 → 지도·정기보고·신문도 edition 2, 계기 33개 전부 판본 2 |
| `06cd0445` | ① 완결: 구형 치환 코드(코어 `buildAction/rowAction`·포털 `action_allowed`·회원 해소기 치환·`edition: 1` 탈출구) 삭제, `edition: 2` 선언 필수 |
| `a4eb44d0` | ② 1차: 액션 `requires:` 관문, 사람 승인 토큰 + `/ibl/approve`, 표면 `$principal`, `[self:package]{op: activate\|deactivate}` |

검증 상태: `build_ibl_nodes.py --check` 27 가드 통과, `tsc`, 렌더 코어·층·크기·validate-parity 가드, 비시스템 전수 8,878 통과(`pytest -m "not system" -n auto --dist loadfile`). 라이브(맥) 확인: 전 계기 edition 2, 지도·정기보고·신문 읽기, 승인 왕복(거절→승인→재전송).

**설치 목록 기준 완료**: ① 전부. ② 1차+2차(§2-② 참조 — 셋은 판정으로 닫음). ③ 1차(§2-③). 나머지 ④~⑩ 미착수.

## 1 사용자 실기기 확인 대기 (다음 세션 첫 일)

제가 볼 수 없는 표면이다. 문제가 나면 그 화면·메시지만 받아 수리한다.
1. 데스크톱 앱 임의 계기(라디오 검색·실거래가)의 조회·드릴·행 버튼 — 빈 입력이 "인자 생략"으로 가는지.
2. 폰 표면: 정기보고 "최신"·"폰에 저장·공유", 신문 "폰에 저장·공유" — `limbs:phone` 은 맥에서 검사 불가. 공유는 `$d = [self:read]…; [limbs:phone]{op:"share", content: $d.text, …}` 로 바꿨고 `content` 인자 이름은 limbs:phone 설명에서 추정했다.
3. 폰/원격 지도 ☆ 저장·삭제 — `places.json` 봉투 `{items,count}` 보존은 임시 파일로만 확인.
4. 승인 대화상자: 수동 모드에서 `[self:package]{op: "deactivate", package_id: "record-ops"}` → 확인 창 → 승인 → 완료(이미 잠든 묶음이라 `changed: false`).

## 2 남은 일 — 순서대로

### 2-① ① 잔여 (소형)
- `scripts/migrate_app_templates_edition2.py` 는 1회성 — 블록이 전부 edition 2 라 더 할 일이 없다. 삭제 판정은 사용자(파괴적). 남기면 "파이프 축약 신고기"로만 의미.
- 해마에 시딩된 관용구 6개(`선택교정` 등, `data/idioms/workspace_seeds.json`)는 **워크플로 원장에 정의가 없어** 매니페스트 `[fn:…]` 로 부르면 실행이 거절된다. 빌드 가드가 경고로 드러낸다. 문서 앱 계기 선언 때 먼저 걸린다 → `[self:workflow]{op:"save"}` 로 정의를 원장에 올리는 것이 해법(코딩·문서·시트 재구성 때 함께).

### 2-② ② 권한 연결 잔여 — **2차 집행 완료(2026-10-05 밤), 셋은 판정으로 닫음**
완료: `requires` 선언·관문(`backend/base/action_requires.py`), 승인 토큰(`backend/base/approval_tokens.py`, `/ibl/approve`), 렌더러 2곳 승인 왕복, `$principal`, 첫 소비자 self:package. 회귀 `backend/test_action_requires_2026_10_05.py`.
2차(같은 날 밤):
1. ✅ 어휘 활성 HTTP `/vocabulary/{id}/activation` = 얇은 통로(`api_vocabulary.run_ibl_as_human` → `[self:package]{op, package_id, profile}` → 관문). `self:package` 에 `profile`(owner|member) 인자. `human_authority` 는 "사람 표면 증명"만 남는다. 회귀 `test_activation_route_is_thin_passage_over_requires_gate`.
2. ✅ 업무기록 확인 토큰 → 공통 승인 토큰(`record_commands.confirmation_challenge`: 주체·`self:record`·`request_hash`). 공간별 `confirmations` 표 은퇴(DDL·내보내기·복원 `DROP TABLE IF EXISTS`). record-ops `path_audited` 4 파일 재감사. 회귀 `test_managed_records_api::test_human_confirmation_is_bound_to_input`(그대로 통과). **record-ops 는 아직 잠들어 있다** — 라이브 확인은 깨운 뒤.
3. 판정 — 포털 자원 범위(`requires.paths`): 자원 인자 선언 자리가 ⑤ 와 같은 설계 → ⑤ 와 함께. 화이트리스트 그대로.
4. 판정 — 회원 승인 통로 `/m/approve`: 회원이 닿는 `human_confirm` 액션이 없어 소비자 없는 배관 → ⑩ 의 첫 회원 소비자와 함께(`/m/run` 봉투 `approval` → member_session → 관문 배선 + 회원 셸 왕복, 실기기 확인).
5. 판정 — `install_approvals` 는 접지 않음(동기 표면 승인 vs 자율 에이전트의 비동기 보류 — "누가 기다리는가"가 다름). ③ 뒤 재검토.
남은 것(⑩ 뒤): 바탕화면·가져오기·외부사용자·패키지 설치/삭제 HTTP 창의 IBL 전환.

### 2-③ ③ 작업 수명의 공통 관찰·제어 (다음 큰 일)
**1차 집행 완료(2026-10-05 밤)** — 접수증 통화 `task_receipts.receipt`, `[self:task]{status|wait|cancel}`, 어댑터 7종(delegation·script·guestpc·newspaper·lecture_video·notebook_source·sheet_op), 상태 어휘 한 벌. 명세 ibl.md '작업 접수증과 대기', 가이드 `data/guides/task_receipts.md`, 회귀 `test_task_receipts_2026_10_05.py`. **2차(남은 것)**: 사진·PC 스캔 접수증화(React 폴링 은퇴, 실기기) · `scope: system` 위임 작업 id · 표면 `await:` + mode 버튼 결과 렌더(렌더러 2곳 setInterval 은퇴) · `/m/run` 스트림 투영 · 용례가 옮겨가면 `self:script status(job_id)`·`guestpc result`·`deck video check` 은퇴 판정. 아래는 원 계획(참고).
설치 목록 §1-③ 그대로. 요점만:
- 수명 셋을 섞지 않는다: **목표**(`self:goal`) / **작업**(task·job) / **티켓**(HTTP 복구). 공통은 관찰·제어 계약, 기존 실행기는 어댑터 뒤.
- 접수증 통화 1종 = 위임 접수증 모양(`delegation_tasks.accepted`: `accepted·task_ref·run_id·state·status_url`)을 채택. 현재 제각각인 것: `[self:script]{background:true}`→`job_id`+`op:status`, guestpc `op:result`, `[engines:newspaper]`→즉시 반환+상태 JSON(`newspaper_publish_state.json`), 사진·PC 스캔(`api_photo.py:71` 스레드+진행 dict+2초 폴링), 시트 `apply` `state:queued`.
- **1순위는 IBL 안에서 접수증을 기다려 값으로 잇는 낱말** — 화면 진행률만 생기면 조합 공백은 그대로. 새 낱말보다 `self:goal status`·`self:script status`·위임 GET(`/system-ai/tasks/{id}?wait=`)을 하나로 접는 것이 먼저(이름은 판정 — 추천: 낱말 신설 대신 `[others:delegate]`·`[self:script]` 가 같은 `task_ref` 를 돌려주고 `[self:task]{op: wait|status|cancel}` 하나로 읽는다. op 신설도 어휘 증식으로 보고 판정 기록을 남길 것).
- 상태 어휘: `cancel_requested`≠`cancelled`, `timeout`(대기자 사정)≠`failed`, 재접속(`ticket` 회수)≠재실행.
- 표면 `await:` 선언 + mode 버튼이 성공 결과를 그리도록(지금 버려짐: `GenericInstrument.fireButton`·`launcher_app_appmode.fireButton`). 런타임의 `ticket`·`/ibl/recover`·`completion_channel` 은 있으나 표면 미배선(`manifest.ts runIBL`·`launcher_app_common.ibl` 은 code·edition·inputs·declared·approval 만 보냄).
- 완료 조건: 신문·사진·PC·노트북·강의 비디오·매니저 command 가 같은 접수증, 한 관용구가 둘을 기다려 합치는 시험, 표면 폴링 코드 삭제.

### 2-④ ④ 구독·주기
뷰 이벤트 `tick:{every}`·`push:{channel}`. 두 렌더러 `setInterval` 0. 웹소켓 라우터(`api_websocket.py`)·`channel_poller` 상주. ③의 진행 수신과 같은 배관으로. 첫 소비자 유튜브뮤직 override(`YtMusicInstrument` 4초 폴링)·메신저 thread.

### 2-⑤ ⑤ 미디어·파일 핸들 · 2-⑥ ⑥ 표면 지시
핸들 통화 `{$blob: handle, mime, …}` + 접근 규칙, 제공자는 종류별 유지(라우터 은퇴 아님). `BACKEND_MEDIA_ROUTES`(`app_render_core.js`) 화이트리스트 삭제가 완료 신호. `surface:{play|stop|open|download|share|stream}` 봉투 필드로 매직 필드 7종(`play_in_client`·`stop_in_client`·`download_in_client`·`pc_only`·`stream:true`·`[MAP:]`·`[STREAM:]`) 정식화 — 렌더러 3곳의 덕타이핑을 코어 한 곳으로.

### 2-⑦ ⑦ 선택·순서·페이지·표면 상태 · 2-⑧ ⑧ 뷰 낱말
`select`(다중)·`reorder` 이벤트, `page:`(next_cursor 소비 — `self:record query` 에 cursor 있음), `state:`. 뷰 낱말은 승격 4기준 충족분만: `tree`(escape 6개: 폴더 창·공유창고·PC 탐색·NAS·빈노트 폴더·강의 재료), `grid`·`chart`, map `map_click`·`layers`, `video`(HLS 정식화), 다화자 `thread`+입력창. 낱말 하나당 지정 escape 를 **같은 커밋에서 삭제**. ①의 `$event`·`$state` 이름 공간이 그릇.

### 2-⑨ ⑨ 위임 범위 지정 (소형 아님)
`[others:delegate]{…, role, allowed, context}` — `allowed` 는 부모 권한 좁히기만·하위 위임 상속, `context` 는 ①의 inputs. 제한 변환은 `table:ai` 유지(모든 AI 호출을 전체 파이프라인에 올리지 않음). 첫 소비자 검색브라우저 `/forage/chat`(`force_role="forage"`, `allowed_set=sense+self+table`, 사냥판 스냅샷).

### 2-⑩ ⑩ 몸의 명사 생애주기 어휘 (② 뒤)
에이전트·프로젝트·폴더·휴지통(매니저·폴더 창), 채팅방(멀티채팅), 스위치 CRUD, 즐겨찾기 add/remove 노출, calendar update/toggle, 창고 feed·like·poll·레벨, 채널 설정, 미디어 probe·transcode·자막. **op 신설도 어휘 증식**(사용자 질책 09-14) — 각각 판정 기록과 가이드·checklist·용례 시딩 의무.

### 2-§2 수리 (판정 불요, 기반 완료를 기다리지 않음 — 단 React 화면은 실기기 확인이 붙는다)
감사 §2-1 목록. 서버만 보고 할 수 있는 것은 없고 전부 React 화면이다: 신문 `issue()`→`[engines:newspaper]{wait:true}`, 강의 REST 18개→`self:lecture/slide/material/deck`, 창고 이웃 3종→`[others:neighbor]`, 매니저 agents/command→`others:agents/delegate`, PC list/analyze→`self:list/storage`, 사진 save/open→`self:copy/limbs:os_open`, 스위치→`self:switch`, 주행기록·트레이스 창→`self:body trajectory`. 죽은 코드 삭제(`api-business.ts` 31메서드, `api_gmail.py`, `gen_newspaper.py`×2, scheduler tasks 래퍼, 원격 `CUSTOM_RENDERERS`)는 파괴적 → 사용자 판정.

## 3 이 코드베이스에서 배운 함정 (다음 세션이 다시 밟지 않게)
- **백엔드 편집은 모아서**: 연속 편집이 재기동 도중 닿으면 제어자 `FAILED`(artifact_changed_before_start), 자동 재시도 없음. 복구 `nohup .venv/bin/python3 backend/api.py start &`. 판정은 `/health` 가 아니라 `data/restart_control/state.json`.
- **계약을 바꾼 액션**(description·ops·target_description)은 `--check` 가 용례 재검토를 요구 → `scripts/iblbuild_example_review.py --show X` 읽고 `--ack X`. description 은 200자 한도.
- **`path_audited.dependencies`**(record-ops 등)에 든 backend 파일(`common/expression_parser.py` 등)을 고치면 지문 불일치 → 재감사 뒤 해시·`at` 갱신(사유 주석).
- 커밋 전 파생물: `build_ibl_nodes.py`(ibl_nodes.yaml·문서 마커 구간), `build_member_shell.py`(helper/member_app.html — 렌더 코어·회원 브리지 바뀌면), `build_body_bundle.py android`(backend 모듈 추가 시). 새 backend 모듈은 `scripts/check_backend_layers.py` LAYERS 등재, base 층은 ibl 층 import 금지.
- 1500줄 한도(`iblbuild_validators.py` 1508 → `iblbuild_requires.py` 분리), 가이드 36KB 예산(`new_action_checklist.md` 는 36KB 턱밑 — 더하면 압축).
- 템플릿 변환기는 여러 줄 YAML 스칼라(`note: '…` 다음 줄 `'`)에서 블록을 조기 종료했다 — 가드(`"$key"`·`{필드}` 잔여 거절)가 잡았다. 수동 변환 뒤 `--check` 를 믿을 것.
- `zsh` 에서 `grep --include` 글롭·`sed -n "$L,+N"` 가 자주 깨진다 — python 으로 읽기.
- 판본 2 `[self:read]` 는 Document{text,blocks,data}: blocks 뷰 `from: blocks`, JSON 원장 `.data.items`. `table:sort`는 List, `table:dedup`는 Record{items} — write 로 이을 땐 `.items`. `table:filter` 의 where 는 람다.

## 4 참고
- 설계·판정: [설치 목록](APP_COMMON_FOUNDATION_GAPS_2026_10_05.md) · [전수 감사](APP_IBL_GAP_AUDIT_2026_10_05.md) · [세 앱 계획](APP_COMPOSITION_ON_IBL_PLAN_2026_10_05.md) · [렌더러 플랜 최상단 2항](REMOTE_APP_GENERIC_RENDERER_PLAN.md)
- 명세: `data/system_docs/ibl.md` '앱 표면 노출 → 표면 바인딩', '조합 연산자 → 노드 지정', '도구 경계 → 요구 권한 requires'
- 회귀: `backend/test_app_template_inputs_2026_10_05.py`(①), `backend/test_action_requires_2026_10_05.py`(②), `backend/test_app_view_engine.py`
- 변경 이력: `data/system_docs/changelog.log` 2026-10-05 항목 5건
