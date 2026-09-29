# 상상 훈련 80회차 결과보고서 (2026-09-29) — 이웃·게시판·발행

훈련 턴 · **무수정**(가이드 §4-3). 아래 갭 원장의 근거는 셋이다.
- [before.json](before.json)·[baseline.json](baseline.json)
- 셸로 읽은 코드(`backend/ibl/channel_engine.py`·`backend/services/indienet_publish.py`·`business`·`family-news`·`bulletin`·`community-portal`·`blog` 패키지·`backend/cognition/routing_system.py`)
- 읽기 전용 원장 대조(`business.db`·`~/.indiebiz/indienet/posts.db`·블로그 DB, `mode=ro`)

원 보고서는 훈련 당시 관측을 보존한다. 현재 수리 상태는 끝의 집행 완료 절을 따른다.

★**개인정보**:
- 메시지 미리보기·이웃 이름·연락처·게시판 글·방명록·포털 회원·공개 주소(슬러그는 입장 열쇠다)는 before.json에 모양(shape)만 남겼다. 이 보고서에도 싣지 않았다. 실은 것은 건수·칸 이름·불리언·날짜뿐이다.
- 훈련자 Nostr 공개키는 요청 문장에서 `<my_npub>`로 바꿨다.
- 저장 후 before.json·baseline.json을 원장 값(이웃 이름·메시지 앞머리·연락처·포털 열쇠·비번 해시)으로 대조했다. 0건이었다.

## 축 선정

- **축**: 행동 기준 미조합 메뉴의 소통·공개면 어휘다. 모두 describe로 op·인자·반환을 확인했다.
  - IndieNet: `others:feed`·`board`·`follow`·`nostr`·`publish`
  - 채널: `others:messages`·`channel_read`
  - 사람·위임: `others:neighbor`·`agents`·`delegate`·`ask`
  - 공개면: `others:bulletin`·`portal`·`showcase`·`family_news`
  - 자기 매체: `self:blog`·`webapp`, `sense:feed`
  - 18액션 중 15개는 교재 코퍼스에 조합이 있는데 행동에서는 한 번도 조합된 적이 없다("가르쳤으나 안 씀"). 나머지 3개(`follow`·`nostr`·`publish`)는 교재에도 조합이 없다.
- **도메인**: 사용자의 실제 생활 흐름에서 나올 법한 일로 골랐다.
  - 가족신문 이번 호 준비(판·가족 사진·방명록)
  - IndieNet 이웃 소식 읽기·"최근 5개"·이번 주 것만, 게시판에서 내 글에 달린 반응 모으기
  - 여러 채널 받은 메시지 중 안 읽은 것만
  - 블로그 최근 글·조회수·공개 RSS와 대조, 폴더 검색
  - 내 웹앱 생존 점검, 자유게시판 글 현황
  - 쇼케이스·포털 진열 준비(check), 에이전트 조사 위임(check)
  - 발행 전 미리보기·검수 → 발행 → 실패 폴백(check), 매주 이웃 소식 알림 트리거(check)
- **부작용 규칙**
  - 읽기만 실행했다: feed read·board list·follow list·nostr profile·messages inbox·neighbor list·blog posts/stats/search/latest·webapp status·bulletin status/detail·portal portals/status/display 목록·showcase status/basket_list·family_news status/uploads/comments/detail·agents·sense:feed.
  - 게시·발행·팔로우·위임·질문·발신·진열 변경·등록은 **전부 check만** 했다.
  - `others:delegate`·`others:ask`는 상대 LLM 턴을 만들어서 check만 했다. `ask`의 `dry_run`도 상대가 컴파일(LLM)하므로 실행하지 않았다.
  - `self:blog{op:"check_new"}`은 수집(블로그 DB·vault 쓰기)이라 실행하지 않았다.
- **축 선정 관문 질문**("기계로 열거 가능한가")
  - "순서·단위·뜻이 사용자 질문과 맞나"는 실제로 불러 봐야 드러난다. 그래서 훈련 축이다.
  - 발견 중 둘은 열거할 수 있으니 census로 넘긴다.
    - 읽기 결과의 자격증명 칸(B80-1): 행 투영 AST·관측 반환 키 대조
    - 선언 enum 밖 값이 다른 부작용 모드로 떨어지는 자리(delegate mode/scope, 재확인 B79-2)
- **닫힌 밭**: 값 표기 격자·경로 방언·날짜 표기·동시성·절단 표지는 다시 갈지 않았다. 방명록·게시판 200행 캡, 메신저 미리보기 40자는 절단 표지 밭이라 적지 않았다.
- **탐침**: `agent_id:"IT80_probe"`·`task_id:"IT80_task"`. 모든 요청이 `edition:2`·`project_id:"컨텐츠"`·`origin:"training"`이다. t25만 판본 1 대조라 `edition:1`이다.

## 지표 스냅샷 (훈련 전)

- 행동 미조합 140/168 · 파이프 길이 중앙값 3 · 문형 4(조회 26·축적 8·적용 6·조건 2) · 파트너 다양성 중앙값 2
- 79회차와 같다. 원본은 [metrics.json](metrics.json)이다.
- 지표는 몸의 현황이며, 훈련 실측은 증류에 담기지 않는다(§6).

## 과제 표

원문·판정식: [probe.py](probe.py) · 응답(개인 원문 마스킹): [before.json](before.json) · 기준선과 회차 후 diff: [baseline.json](baseline.json).

**25과제 중 기계 판정 16통과 · 9실패**다. 결함 4부류 · 마찰 3부류 · 어휘 후보 1이다.
- 구성: 실행 16 · check만 4(t18·t19·t20·t23) · 실행+check 혼합 4(t05·t06·t14·t17) · 판본 1 대조 1(t25)
- check 과제는 기계 판정이 기본 통과라서 분류는 아래 표가 정본이다.

탐색 중 훈련자 문장 잘못은 결함 판정에서 뺐다. 거절 안내가 모두 위치를 정확히 짚었다.
- `table:document{sections:…}`: UNKNOWN_ARGUMENT, 사용 가능 인자 목록이 함께 왔다
- 트리거 `do` 문자열 안에 큰따옴표를 중첩: SYNTAX
- RSS 봉투를 `.items` 없이 each로: TYPE
- 블로그 폴더 "AI"는 실제 폴더명이 아니었다. 고쳐서 다시 찍었다.

| # | 상상 의도 | 결과 | 분류 |
| --- | --- | --- | --- |
| T01 | 가족신문 이번 호 준비 — 판·초안·가족이 보낸 새 사진(다음 판 후보)·방명록 | 판 5(초안 0·발행 5)·가족 사진 7(후보 0)·방명록 4. 후보 판별은 `contains(meta,"다음 신문 후보")`뿐 | 깨끗(F77-1 재확인) |
| T02 | IndieNet 이웃 소식 — 기본 보드 글 "최근 5개" | 7행이 **오래된 것부터** → `take 5`와 최신 5개의 겹침 3/5 | 결함 B80-3 |
| T03 | 같은 피드를 세 갈래로(보드·팔로우·내 글) + "이번 주 것만" | 보드는 오름차순, 내 글(author)은 내림차순. 시간 칸은 연도 없는 `"MM/DD HH:MM"`, 원시 시각 칸 없음 | 결함 B80-3(F77-1 재확인) |
| T04 | 게시판에서 내 글에 달린 반응(답글·좋아요) 모으기 | 내 글 3. 행 칸은 author·author_full·content·id·is_mine·time뿐이고 답글 관계 칸 0. 캐시에는 e 태그(답글) 행 62개 | 불가 V80-1 |
| T05 | 오타 op 6종(feed `reed`·follow `lists`·board `remove`·nostr `relay`·messages `inbox_all`·bulletin `stat`) | 6/6 check `invalid`·`ARGUMENT_CONTRACT`. 핸들러의 "모르는 op = 읽기" 폴백에 닿지 않음 | 깨끗 |
| T06 | 선언 밖 인자 — feed `since`·`count`·`limit:0`, inbox `search`, 발행·게시의 `dry_run`·`preview` | `since`(3일 전) → 인자 없을 때와 같은 id. `count:3` → 7행. 발행 `dry_run:true`·게시 `preview:true` check `incomplete`·경고 0. inbox `search`는 UNKNOWN_ARGUMENT(핸들러는 읽음) | 재확인(F78-2 새 차원·B72-2) |
| T07 | 여러 채널 받은 메시지 중 안 읽은 것만 — inbox `unread>0` | 대화 10 중 2. **unread = 미답신 수 10/10 일치**, 원장에 읽음 칸 없음 | 결함 B80-2 |
| T08 | 채널 원시 수신함(nostr·email 최근 3건) — 프로젝트 에이전트로 | 둘 다 "에이전트 'IT80_probe'를 찾을 수 없습니다." — 신원 게이트 정직 | 깨끗 |
| T09 | 블로그 최근 글 5개 + 통계 + 조회수 | 행 칸 title·meta·summary·url(날짜·분류는 meta 문자열), 조회수 칸 없음, stats는 글 수 3칸 | 꼬임(F77-1 재확인) |
| T10 | 공개 RSS 최신 10편이 내 블로그 DB에 다 들어왔나 | url anti join **10/10 누락**(`"/N"` vs 절대 주소), 제목 anti join 3/10 누락 → DB가 09-21에서 멈춤. latest가 09-21 글을 "최근 글"로 | 결함 B80-4 · 마찰 F80-2 |
| T11 | RSS 가장자리 — limit 0·HTML 주소·없는 피드 | 0건 성공 · "RSS/Atom 피드 형식이 아닙니다." · HTTP 404 — 선언대로 정직 | 깨끗 |
| T12 | 내 웹앱 생존 점검 — 죽은 것만 | `not $r.alive` → "조건에는 Bool이 필요합니다"(어느 행인지 없음). alive null 3행(주소 미상). `== false`로 고치면 26곳 중 죽음 2 | 꼬임 F80-1 |
| T13 | 자유게시판 전체 — 게시판마다 detail로 글 수 | 게시판 2·글 1·2. detail의 `items`는 **게시판 행 자신**, 글은 `posts`. 글 시각·본문은 meta 한 문자열 | 꼬임 F80-3 |
| T14 | 쇼케이스·포털 진열 준비 — 읽기 실행, 담기·진열 변경 check | 폴더 3·바스켓 3·포털 2·진열 목록 20. 담기·진열 check `incomplete`·effects `unknown`. **포털 읽기 뒤 `portal_state.json` mtime 변경**(내용 동일) | check · 재확인(B78-2·B75-4) |
| T15 | 없는 포털을 지목한 읽기 | "오류: 'NoneType' object has no attribute 'get'", 상태 파일은 또 재기록 | 재확인(F72-2·B78-2) |
| T16 | 이웃 목록 — 레벨·즐겨찾기로 거르기 | 10행·23칸. **`portal_key` 4·`portal_pw`(pbkdf2) 4·`portal_login_id` 4가 가려지지 않은 값**. 실행 영수증 1파일에 열쇠 4 | 결함 B80-1 ★ |
| T17 | 조사 위임 — 명부 읽기 → 위임 문장 check | 에이전트 33·프로젝트 23. `agent`/`msg` 오타·message 없음·`mode:"sinc"`·ask `dry_run` 모두 `incomplete`·경고 0 | check · 재확인(F78-2·B79-2·B75-4) |
| T18 | 발행 전 문서 → 발행, 실패하면 파일로 / 게시 실패하면 알림 | 전부 `incomplete`. effects: publish ?? write → `["unknown","write_external"]`, 나머지 `["unknown"]` | check(B75-4) |
| T19 | 부작용 사전 판정 격자 — 같은 액션 읽기 op vs 쓰기 op 14쌍 + 옛 검수기 | check effects 14쌍 **전부 `unknown`**. `/ibl/validate`는 14쌍 모두 `has_side_effect` false/true로 정확 | check · 재확인(B75-4 가장 강한 증거) |
| T20 | 코퍼스 용례 — 축 18액션 386용례 판본 2 check | invalid 57(TYPE 54·ARGUMENT_CONTRACT 10·UNKNOWN_ARGUMENT 8·SYNTAX 6…). sense:feed 20·channel_read 6 | check(교재 드리프트 재확인) |
| T21 | 실패 봉투 세 모양 — `{error}`만 · `{success:false,message}` · 정상 | `{error}`만은 판본 2 실패·`??` 폴백·action_health success 0 모두 정상. `{success:false,message}`(가족신문·게시판 없는 대상)는 판본 2 실패·catch `TOOL`은 정상인데 **action_health success=1** | 재확인(B78-8) |
| T22 | 팔로우 × 이웃 × 메신저 — 승격 다리 건수 | 팔로우 0·이웃 10·inbox 10·nostr 이웃 7·indiebiz 동료 2 | 깨끗 |
| T23 | 매주 월 8시 지난 1주 이웃 소식 있으면 알림(trigger check) | 트리거 check `incomplete` + `LITERAL_DOLLAR`(do 안 프로그램을 문자열로 봄). 안쪽 단독 check `incomplete` | check(B75-4 재확인) |
| T24 | 블로그 폴더 안·밖 검색, 폴더 목록 | 안 5·밖 5·목록 5. 없는 폴더 단독 → 0 + "검색 결과가 없습니다". 목록 속 없는 폴더는 말없이 빠짐 | 깨끗(B79-2 재확인) |
| T25 | 판본 1(저장·스케줄 호환)에서 오타 op + feed `limit:3` | 판본 1도 3/3 거절. `limit:3` → 3행 | 깨끗 |

튼튼했던 것:
- 커뮤니티·메신저·게시판 op의 enum 검증: 판본 1·2 모두 오타 op를 거절했다. 핸들러의 조용한 읽기 폴백은 도달할 수 없다.
- 가족신문 판·가족 사진·방명록 집계
- RSS의 0건·HTML·404 정직
- 블로그 폴더 검색의 폴더 안/밖 두 번(가이드 실무 순서)
- 채널 수신함의 신원 게이트
- `{error}`만 있는 실패 봉투: 판본 2 실패·폴백·건강 원장이 모두 정상이었다.

실패는 두 자리에서 났다.
- **값의 이름·순서·신선도가 사용자 질문과 다른 뜻으로 오는 자리**다.
  - 사용자는 "안 읽은 메시지", "최근 5개", "블로그 최근 글", "죽은 웹앱"을 물었다.
  - 몸은 "답장 안 한 메시지", "가장 오래된 5개", "8일 전 사본의 최근 글", "주소를 아는 것 중 죽은 것"에 답했다.
- **읽기 결과에 자격증명이 딸려 오는 자리**(B80-1)다.

## 갭의 원장

### B80-1 ★ `others:neighbor`가 이웃 행에 **포털 로그인 열쇠·비번 해시를 가리지 않고** 싣는다 — 실행 영수증까지 남는다

- **요약**
  - `business/handler.py` `_nb_list`(548~550행)는 `bm.get_neighbors()` 결과를 그대로 items에 싣는다. `get_neighbors`는 `SELECT * FROM neighbors`(`backend/datastore/business_manager.py` 839행)다. `_nb_detail`의 `neighbor`도 `get_neighbor`(`SELECT *`, 932행)다. (보고서 저장 전 세 자리를 직접 읽어 확인했고, 원장에 열쇠·pbkdf2 해시가 든 행이 있음을 건수로만 대조했다.)
  - 이웃 행에는 포털 인증 칸이 붙어 있다: `portal_login_id`·`portal_pw`·`portal_key`·`portal_revoked`·`portal_joined_at`·`portal_last_used`·`warehouse_key`.
    - `portal_key`는 `secrets.token_urlsafe(18)`이다. `/h/<슬러그>/k/<키>`로 **비밀번호 없이 즉시 로그인**하는 열쇠이고, 포털 가이드가 "유출 시 revoke"라고 말하는 그 값이다.
    - `portal_pw`는 `pbkdf2$salt$hash`다.
  - `business_sync.py`는 이 칸들을 "맥 전용(동기화 제외)"로 이미 분류한다(`PORTAL_LOCAL_COLS`). 그런데 IBL 읽기 표면은 그 분류를 모른다.
  - describe의 관측 반환(fixture)이 `portal_pw`·`portal_key`·`warehouse_key`를 이 액션의 반환 칸으로 **광고한다**. 모델이 쓸 칸으로 배운다.
- **최소 재현**: `return [others:neighbor]{op:"list"}` → 행마다 `portal_key`·`portal_pw` 칸 확인(값은 싣지 말 것)
- **실측**(T16)
  - 살아 있는 이웃 10행 중 `portal_key` 4·`portal_pw` 4(모두 `pbkdf2$` 접두)·`portal_login_id` 4가 비어 있지 않다. 가림(`*`·REDACT) 0이다.
  - 실행 영수증 `data/ibl_runs/632d48f3…/1437703f0c2047a8809faf1240c4cb54.sqlite`(03:05, 이 회차 탐침)에 열쇠 4·해시 4가 들어 있다.
    - 다른 영수증 14,646개, `world_pulse.db`, `backend_runtime.log`, `data/*.json|db`에는 0이다.
    - 영수증 보존 정리 규칙은 찾지 못했다(`data/ibl_runs` 264MB). 주인 실행 기록은 재기동을 넘는다(교재).
- **영향**
  - 이웃 목록을 한 번 읽은 모든 에이전트 턴의 값·영수증·모델 문맥에 로그인 열쇠가 실린다.
  - 열쇠 하나면 그 이웃의 레벨로 포털 계기를 쓸 수 있다.
- **제안(수리성)**
  1. 이웃 읽기 표면(`_nb_list`·`_nb_detail`·같은 행을 싣는 모든 생산자)에 **허용 칸 투영**을 둔다. 인증 칸은 빼고 `portal_member:bool`·`portal_revoked`만 싣는다. 개인 링크는 지금처럼 `portal members`/`issue`만 준다(운영자 발급 목적이 선언된 자리).
  2. fixture를 다시 돌려 관측 반환에서 인증 칸을 지운다.
  3. **census**: `SELECT *` 행을 그대로 값으로 내보내는 생산자 전수. 관문: "값·영수증 직렬화 경계에 자격증명 칸 이름 목록(portal_pw·portal_key·*_key·*_token·password·nsec…) 금지". `mask_secrets`는 `token_urlsafe` 형태를 못 잡는다(실측 가림 0).
  4. 이미 남은 영수증 1파일의 처분은 판정 요청 참고.
  - 가드: 이웃 list/detail 행에 인증 칸 0, 관측 반환 키에 인증 칸 0.

### B80-2 메신저 inbox의 `unread`는 **미답신 수**다 — "안 읽은 것만"이 "답장 안 한 것만"으로 답한다

- **요약**
  - `get_inbox_summary`의 `_unread`는 `replied=0 AND is_from_user=0` 개수다(독스트링 "미답신 수신 수"). 이것이 행의 `unread`가 된다.
  - 메시지 원장(`messages`)에는 읽음 칸이 없다. 그래서 "읽었지만 답하지 않은 메시지"와 "밖(폰 메일 앱 등)에서 답한 메시지"도 영원히 unread다.
  - 선언이 둘로 갈린다. description은 "table:filter 로 **미독**·즐겨찾기만 선별", target_description은 "이웃별 최근 메시지·**미응답**"이다.
  - 비이웃 Nostr DM 행은 `"unread": 0` 고정이다(`_msg_inbox` 390행). 측정하지 않은 값을 0으로 낸다. 그래서 `unread > 0` 필터가 낯선 사람의 DM을 전부 떨어뜨린다.
- **최소 재현**: `$m=[others:messages]{op:"inbox"}; return $m.items >> [table:filter]{where:($r)=> $r.unread > 0}`
- **실측**(T07)
  - 대화 10, `unread>0` 2다. 이웃 행 10/10에서 `unread` = 원장의 미답신 수신 수였다.
  - 한 대화는 07-21~09-07 미답신 12건이 전부 "unread"다.
  - 이번 원장에는 비이웃 DM 행이 0이라 DM 고정값은 코드로만 확인했다.
  - 코퍼스 3690(`unread gt 0`)·3704(`unread eq true`, 정수 칸)가 이 칸으로 "안 읽은 것"을 가르친다.
- **제안(수리성)**
  1. 칸 이름을 뜻대로 나눈다. `unreplied`(지금 값)를 신설하고, `unread`는 읽음 기록이 생길 때까지 선언에서 "미답신"으로 명시하거나 null로 낸다.
  2. 비이웃 DM은 측정하지 않았음을 null로 낸다.
  3. 두 선언 문구를 한 뜻으로 맞추고, 코퍼스 두 건은 용례 재검토 대상에 올린다.
  - 가드: 읽음 기록 없는 원장에서 `unread` ≠ 미답신이 되도록 fixture를 두고, DM 행 unread는 null이어야 한다.
  - 칸 이름을 바꾸는 쪽이 기존 문장을 깨면 별칭을 유지한다(비파괴).

### B80-3 `others:feed` read의 행 순서가 **갈래마다 반대**다 — 보드의 "최근 5개"가 가장 오래된 5개다

- **요약**
  - `channel_engine._community_feed`는 보드 읽기(hashtag 또는 기본)에서 `posts.reverse()`를 한다. 채팅방 말풍선 관례대로 과거→최신이다. author·following 갈래는 원천 순서(최신순) 그대로다.
  - 선언(`target_description`)은 순서를 말하지 않는다. 화면 계기(thread 뷰)의 관례가 값 계약으로 새어 나왔다.
  - 행의 시간 칸 `time`은 `_fmt_unix`의 `"MM/DD HH:MM"`(연도 없음) 표시 문자열뿐이다. 원시 `created_at`은 핸들러가 버린다.
    - IndieNet 캐시는 2023-08~2026-08에 걸친다. `sort by time`도 "이번 주 것만"도 해마다 같은 날짜가 섞인다.
- **최소 재현**: `$f=[others:feed]{op:"read", limit:30}; return $f.items >> [table:take]{n:5}` → 캐시 `created_at`과 대조
- **실측**
  - T02: 보드 7행이 오름차순이다. `take 5`와 최신 5개의 겹침은 3/5다.
  - T03: 내 글(author) 3행은 내림차순이다. `time` 형식 `MM/DD HH:MM` 7/7, 연도 칸·원시 시각 칸 0이다.
- **제안(수리성)**
  1. 값 계약은 한 순서(최신순)로 둔다. 말풍선 순서는 계기 뷰가 뒤집는다(뷰 선언에 `order:"asc"`).
  2. 행에 `created_at`(ISO 또는 Unix 정수)을 싣고, `time`은 표시 칸으로 남긴다.
  3. 같은 표시 시각은 메신저 inbox·thread `time`(`_short_time`)에도 있다. 함께 고친다(F77-1 census 항목).
  - 가드: 세 갈래 모두 최신순, `created_at` 존재.

### B80-4 `self:blog`가 **로컬 사본의 "최근 글"**을 기준 시각 없이 준다 — 공개 블로그에는 더 새 글 3편이 있다

- **요약**
  - posts·search·latest는 모두 로컬 블로그 DB(수집 사본)를 읽는다. 사본은 `check_new`(RSS 수집 → DB·vault 쓰기)가 불릴 때만 자란다.
  - 신선하게 하는 유일한 길이 쓰기 op다. 그 op의 이름은 "확인(check)"이고 effects는 `unknown`이다.
  - 블로그 발행 스케줄(`[IBL] warehouse_publish_blog`)은 꺼져 있다(마지막 07-21).
  - latest는 "발행 파이프의 머리"로 선언돼 있다. 오래된 글이 "최근 글"로 발행 파이프에 들어갈 수 있다.
  - 봉투에는 사본의 기준 시각(`as_of`·`last_collected`)이 없다.
- **최소 재현**: `$r=[sense:feed]{url:"https://irepublic.tistory.com/rss", limit:5}` vs `[self:blog]{op:"latest"}`
- **실측**(T10·격리)
  - RSS 최신은 09-28 23:32·09-28 01:51·09-22 10:58·09-21 16:26 순이다.
  - DB 최신은 09-21 16:26(7891417)이고, latest가 이 글을 "최근 글: …"로 준다.
  - 제목 anti join으로 RSS 10편 중 3편이 DB에 없다.
- **제안(수리성)**
  1. posts·search·latest 봉투에 `as_of`(마지막 수집 시각)를 싣는다.
  2. latest는 사본이 N시간보다 낡았으면 `stale:true`와 "먼저 수집" 안내를 싣는다.
  3. 선언에 "로컬 사본에서 답함"을 적는다.
  4. `check_new`의 선언을 "수집(쓰기)"으로 고친다(부작용 판정은 B75-4 투영에서 따라온다).
  - 가드: 낡은 사본 fixture → `as_of`·`stale` 표지.

### F80-1 `self:webapp` status의 `alive`가 **삼치**(true/false/null)인데 선언은 둘뿐이다

- T12: 26곳 중 3곳이 `alive:null`이다. 주소 미상 외부 Worker·Vercel 사이트이고, `status_line` "주소 미상 — register 로 보충"이다.
- 선언은 "2xx/3xx·401/403이면 true, 404/410/5xx 등은 false"만 말한다. 교재식 `where:($r)=> not $r.alive`가 "조건에는 Bool이 필요합니다"로 실패한다. 오류가 어느 행·어떤 값인지 말하지 않는다(F72-2 재확인).
- 관측: 죽음 2다. 수동 등록 진단 페이지 1곳은 404였다. 몸 공개면 1곳은 연결 실패(http 0)였는데, 재측정에서는 살아 있었다(일시 장애).
- 제안(수리성): 선언에 `alive:null = 측정 불가(주소 미상)`를 적거나 `alive` 대신 `state:"alive|dead|unknown"`을 병기한다. 조건 오류 진단에 행 인덱스·값을 싣는다.

### F80-2 같은 블로그 글의 url이 **두 표기**다 — posts·search는 `"/N"`, latest·RSS는 절대 주소

- T10: `_posts_to_records`·`_results_to_records`는 `url:"/{post_id}"`를 싣는다. `_op_latest`와 `sense:feed`는 `https://irepublic.tistory.com/N`이다.
- 같은 액션 안에서도 op마다 다르다. 그래서 "RSS에는 있고 DB에는 없는 글"을 url로 거르면 10/10이 누락으로 나온다. 제목으로 거르면 3/10이다.
- 제안(수리성): 블로그 레코드는 절대 url(또는 `post_id` 칸 병기)로 통일한다. F76-1(통화 칸 규약) census의 식별자 칸 항목이다.

### F80-3 `others:bulletin` detail의 `items`가 **게시판 행 자신**이다 — 글은 `posts`

- T13: status의 `items`는 게시판 목록이다(주 컬렉션). detail은 `items:[게시판 행]`, 글은 `posts`에 싣는다.
  - "단일 통화 items = 주 컬렉션" 규약대로 detail을 파이프하면 게시판 한 행을 걸러 쓰게 된다.
  - 관측 반환은 op별로 갈리지 않아 `posts` 접근은 관측 밖이다.
- 글 행의 작성자 칸 `title`에 이미지 표시 `" 🖼"`가 붙는다(이름 오염). 시각·본문 80자는 `meta` 한 문자열이다(F77-1 재확인).
- 제안(수리성): detail의 `items`는 글 목록으로, 게시판은 `board`로 둔다(모더레이션 화면은 이미 `posts`·`board` 둘 다 읽음). 글 행에 `name`·`at`·`has_image`·`body` 칸을 싣고, 표시 문구는 표시 칸으로 뺀다.

### V80-1 (후보) 내 글에 달린 **답글·반응**을 모을 수 없다

- T04: `others:feed`는 kind 1 글을 태그·저자로만 가져온다. 행에서 `tags`를 버려 답글 관계(e 태그)를 볼 수 없다. 반응(kind 7)은 조회 대상이 아니다.
- IndieNet 캐시에는 e 태그 행 62개가 있다(이번 원장에서 내 글을 가리키는 답글은 0).
- "내 게시글에 누가 뭐라고 했나"는 공개층 소통에서 자연스러운 요구다. 지금 어휘로는 답글이 있어도 표현할 수 없다.
- **어휘 신설은 제안하지 않는다.** 기존 read의 선택 칸(`replies_to:"<event id>"`)이나 행의 `reply_to` 칸으로 가능한지는 현실 반복이 인준할 일이다.

## 재확인 (앞 회차 갭·수리의 증거 — 새 항목 아님)

- **B75-4**(check의 액션별 사전 판정 부재) — **가장 강한 증거**(T19)
  - 읽기·쓰기 op 14쌍의 판본 2 check effects가 **전부 `["unknown"]`**이다: feed read/post, board list/delete, follow list/add, nostr profile/reset_identity, neighbor list/delete, bulletin status/delete, family_news status/delete, portal portals/revoke, showcase status/basket_delete, blog posts/rebuild_index, webapp list/remove, messages inbox/channel_send, agents/publish, sense:feed/delegate.
  - 옛 검수기 `/ibl/validate`는 14쌍 모두 `has_side_effect` false/true로 **정확히 가른다**.
  - 원천 `others.yaml`에는 op별 `side_effect`(`feed.ops.side_effect.read:false` 등)가 이미 있다.
  - 즉 데이터는 있고 판본 2 `callable_contract.effects`로의 **투영만 빠졌다**. 교재가 가르치는 검사가 은퇴 예정 검수기보다 눈이 어둡다.
  - 트리거 `do` 안 프로그램은 `LITERAL_DOLLAR`로만 보인다(T23).
- **F78-2**(open_params 인자 계약 밖) — **새 차원: 되돌릴 수 없는 발신**
  - `[others:publish]{…, dry_run:true}`·`[others:feed]{op:"post", …, preview:true}`가 check `incomplete`·경고 0이다(T06). `_publish_article`·`_community_feed`는 이 인자를 읽지 않는다. 미리보기를 기대한 문장이 **실제 공개 발행·게시**가 된다.
    - 비교: `others:ask`는 `dry_run`을 선언하고 읽는다.
  - feed `since`는 무시된다. `fetch_board_posts`는 `since`를 받지만 핸들러가 넘기지 않아, 3일 전 기준에도 같은 7행이 나온다. `count:3`도 무시된다.
  - delegate `agent`/`msg` 오타·message 없음이 check 경고 0이다(T17).
  - 발신 액션(publish·feed·delegate·board·follow·nostr)을 닫힌 계약으로 만드는 것을 open_params census의 첫 순서로 적는다.
- **B79-2**(원천 인자 값 영역 침묵)
  - `others:delegate`의 `mode`·`scope`는 enum 선언이 없다(T17 `mode:"sinc"` check 경고 0).
    - 코드(`routing_system._delegate_unified`)상 모르는 mode는 **기본 async 위임**(fire-and-forget LLM 턴)으로 떨어진다. 모르는 scope는 same으로 떨어진다.
    - sync 응답을 기대한 파이프가 조용히 비동기 위임을 만든다.
  - 블로그 없는 category → "검색 결과가 없습니다"(없는 폴더라는 말 없음). 목록 속 없는 폴더는 말없이 빠진다(T24).
- **B72-2**(선언이 핸들러의 실제 인자를 모름): messages inbox `search`·`level`은 핸들러가 읽는다(`_msg_inbox`). 그런데 닫힌 선언(`open_params:false`)이 UNKNOWN_ARGUMENT로 거절하고, 선언은 "파라미터 없음"이라 한다(T06).
- **B72-5/B78-2**(읽기가 쓰기를 만든다)
  - `others:portal`의 모든 op는 `_get_portal` → `core.mutate_state`를 거친다. 읽기(status·portals·display 목록)도 `portal_state.json`을 다시 쓰고 write_ledger 사건을 남긴다(T14·T15 mtime 변경, 내용 해시 동일).
  - 포털이 0개면 읽기가 기본 포털(공개 주소)을 **만든다**(`ensure_default_portal`, 코드).
  - `display{key:X}`는 조절 인자가 없어도 빈 진열 항목을 쓴다(코드).
  - `self:blog latest`는 vault `.md`가 없으면 쓴다(코드).
- **F72-2**(진단 안내 부족): 없는 포털 → "오류: 'NoneType' object has no attribute 'get'"(T15). 조건 비-Bool 오류에 행·값이 없다(F80-1).
- **B78-8**(문자열 실패 봉투의 성공 기록): `items(..., success=False, message=…)`로 실패하는 가족신문 detail·게시판 detail이 판본 2에서는 실패인데 action_health success=1(shape error)이다(T21, 3행). `{error}`만 있는 channel_engine 봉투는 success 0으로 정확했다.
- **B79-3**(파싱·조회 실패 = 빈 성공) — 코드만, 재현 안 함
  - `indienet_publish.fetch_board_posts`는 `except Exception: return []`다. 핸들러는 그것을 "아직 글이 없습니다" success로 준다.
  - 릴레이가 전부 실패하면 캐시 행만 돌려준다. 신선도 표지가 없다.
  - 가족신문 comments는 방명록 JSON 파싱 실패를 빈 목록으로 삼킨다.
- **F77-1**(구조 칸이 표시 문자열에만)
  - 가족신문: 판 행의 발행일·사진 수·수집 구간, 가족 사진의 "다음 신문 후보"
  - 게시판 글 시각·본문
  - 블로그 날짜·분류
  - RSS 날짜(`meta`의 RFC 822 문자열)
  - 피드·메신저 `time`(B80-3)
- **F76-2**(관측 반환의 변이 축 부족): 게시판 detail의 `posts`, `delegate sync`의 `response`가 `UNOBSERVED_FIELD`다(op·mode별 관측 없음).
- **교재·코퍼스 드리프트**(F76-3·F78-3 계열): 축 18액션 386용례 중 판본 2 check **invalid 57**이다(T20).
  - TYPE 54: 봉투를 `.items` 없이 파이프, 옛 `where:{field,op,value}`
  - ARGUMENT_CONTRACT 10: `channel_read`에 channel_type·to 없음
  - UNKNOWN_ARGUMENT 8, SYNTAX 6: `[repeat: while …, max:5]`
  - 액션별 invalid: sense:feed 20·channel_read 6·blog 5·webapp 5
- **B73-1**(판본 2 파이프 자리): `table:document >> [others:publish]`가 이번에는 check `incomplete`(파이프 충돌·타입 오류 없음)다. 실행은 금지 축이라 수리 여부를 실측하지 못했다.

## 시드 후보 (실행 검증 통과만 — 자동 등록 안 함)

- T22(follow list × neighbor list × messages inbox → filter channel·is_neighbor·is_indiebiz_peer → 건수)
- T24(blog search 폴더 안 + 폴더 밖 + 폴더 목록 → 건수 대조) — 가이드 실무 순서

문장 안의 폴더명은 자리표로 바꿔 심을 것.

**빼는 것**:
- T01·T09·T13: F77-1·F80-3 문자열 우회
- T02·T03: B80-3
- T07: B80-2
- T10: B80-4·F80-2
- T12: F80-1
- T14·T15: 읽기 재기록
- T16: B80-1
- T17~T20·T23: check
- T21: 실패 격리
- 코퍼스 3690·3704(unread)와 invalid 57건은 용례 재검토 대상이다.

## 판정 요청 (언어 개정·파괴적 변경 2종만)

**1건 — 파괴적 변경(삭제)**: 이 회차 탐침(T16)이 만든 실행 영수증 `data/ibl_runs/632d48f3…/1437703f0c2047a8809faf1240c4cb54.sqlite`의 처분이다.
- 여기에 이웃 4명의 포털 즉시 로그인 열쇠와 비번 해시가 들어 있다.
- 같은 기계의 `business.db`가 이미 원본을 갖고 있으므로 노출 범위가 새로 넓어지지는 않았다.
- 다만 영수증은 보존 정리 없이 남고, 배포 묶음 필터(pitfall dist-bundle denylist)가 `data/ibl_runs`를 다루는지 확인하지 못했다.
- 권고는 삭제다(되살릴 필요가 없는 탐침 기록). 훈련 턴은 시스템 기록을 지우지 않으므로 사용자 결정으로 올린다.
- 열쇠 재발급(`portal issue`)은 회원의 기존 링크를 무효화하는 더 큰 파괴적 변경이다. 영수증이 기계를 떠난 증거가 없으면 필요하지 않다고 본다.

나머지(B80-1~4·F80-1~3)는 모두 수리성이다.
- B80-1(인증 칸 투영)은 표면에서 빼는 쪽이다. 개인 링크는 기존 `portal members`/`issue`가 선언대로 계속 준다.
- B80-2는 별칭을 유지하면 비파괴다.
- B80-3의 순서 통일은 화면 계기가 뷰에서 뒤집으면 표면이 바뀌지 않는다.
- V80-1은 어휘 후보일 뿐이다(현실 반복이 인준).

**다음 수리 턴의 첫 항목(밭 이관·census)**:
1. B80-1: `SELECT *` 행 투영 생산자 census + 값·영수증 직렬화 경계의 자격증명 칸 금지 관문 + 관측 반환 재생성
2. B75-4: 원천 `ops.side_effect`·옛 검수기 판정을 판본 2 `callable_contract.effects`로 투영(op 인자별)
3. F78-2 발신 우선: publish·feed·delegate·board·follow·nostr 닫힌 계약, `dry_run`·`preview` 같은 "미리보기" 인자는 선언 없으면 거절

## 72~80회차 공통 뿌리에 80회차가 더하는 것 (훈련자 관찰)

- 79회차의 "선언이 말하지 않는 기본값·표본·단위"가 이번에는 **칸의 이름·순서·기준 시각**으로 나타났다. 넷 모두 success이고, 그 해석을 말하는 칸이 없다. 뿌리 2(선언과 실제 동작의 대조 관문 부재)의 또 다른 모양이다.
  - `unread`라는 이름이 미답신을 담는다(B80-2).
  - 화면 관례(말풍선 오름차순)가 값 계약으로 샌다(B80-3).
  - 사본의 "최근"이 원천의 "최근"을 참칭한다(B80-4).
  - null이 선언 밖 제3의 값이다(F80-1).
- **부작용의 지식이 한 몸 안에서 셋으로 갈라져 있다**.
  - 원천 yaml의 `ops.side_effect`가 있다.
  - 옛 검수기 판정 `has_side_effect`는 정확하다.
  - 판본 2 check effects는 `unknown`이다.
  - 교재는 셋째를 가르친다. 부작용 사전 판정이 가장 필요한 축(발행·게시·위임)에서 가장 눈이 어둡고, open_params가 그 위에 "미리보기 인자 침묵"을 얹는다.
  - 판정의 정본이 한 벌이어야 한다는 71·75회차 교훈이 발신 축에서 되풀이됐다.
- **읽기 표면의 투영이 설계되지 않았다**(B80-1).
  - 동기화 층은 포털 인증 칸을 "맥 전용"으로 이미 분류했다(`PORTAL_LOCAL_COLS`). IBL 읽기 표면은 행을 통째로 내보낸다. 같은 몸 안에서 한 층이 아는 비밀 등급을 다른 층이 모른다.
  - 실행 영수증이 모든 값을 기한 없이 보존하므로, 투영 누락 한 번이 디스크 사본이 된다.
- **읽기가 쓰기를 부르는 부류가 네 번째 패키지에서 나왔다**(포털 `mutate_state`, 블로그 latest의 vault 쓰기). 78회차 B78-2가 요청한 census가 아직 미집행이라는 증거다.

## 위생

- **기준선**: 탐침 전 03:02:50에 떴다([baseline.json](baseline.json)).
  - action_health max id 244679, notify_log 6260, 알림함 2통
  - 파일 해시: 포털·쇼케이스·게시판·웹앱 수동 등록·IndieNet settings·identity
  - 트리: bulletin·family_news
  - business.db messages·neighbors·contacts 행 수·max id, IndieNet posts·dms 캐시 행 수
  - 위임 큐(tasks 3 DB), 시스템 AI 대화, 블로그 DB 글 수, 코퍼스, episode_log
- **회차 후 diff**(재측정 포함 최종)
  - action_health 새 행 60, **전부 `training`/agent**. B78-8 때문에 가족신문·게시판 실패 3행도 success=1로 적혔다. channel_read 4행은 success 0으로 정확했다.
  - notify_log 0 · 알림 추가 0
  - 게시·발행·팔로우·위임·발신 0: IndieNet posts 캐시 134 불변, 보드·팔로우 설정 불변, tasks 불변, 시스템 AI 대화 불변
  - business.db 불변 · bulletin·family_news 트리 불변 · 블로그 DB 4,036 불변 · 코퍼스 3,735 불변 · episode_log 불변
  - 바뀐 것은 `portal_state.json` **mtime 하나**(내용 해시 동일)다. 포털 읽기 op가 재기록한 것이다(재확인 B78-2).
- **호출**
  - 외부:
    - IndieNet 릴레이 조회 `others:feed` 10회(author 갈래는 동시 3조회)
    - 공개 RSS `sense:feed` 5회
    - `self:webapp` status 5회(각각 자기 공개면 약 23곳 HTTP)
  - 로컬 읽기: blog 12·family_news 5·bulletin 4·portal 3·showcase 2·nostr 2·neighbor 2·messages 2·follow 1·agents 1·table:join 2
  - channel_read 4회는 신원 게이트에서 거절돼 외부 접속이 없었다.
  - 검사: check 약 450회(코퍼스 386 포함), `/ibl/validate` 28회
  - 유료 AI 0 · 발신 0 · 해마 시딩 0
- **스크래치**
  - 파일 쓰기는 하지 않았다(`IT80*` 0).
  - 스크래치패드의 describe 사본 18개와 탐침 폴더의 `__pycache__`는 지웠다.
- **사용자 데이터 무손상**
  - 메시지 스레드 본문은 읽지 않았다(inbox 요약만).
  - before.json·baseline.json에 이웃 이름·메시지 앞머리·연락처·포털 열쇠·비번 해시가 0건임을 원장 값으로 대조했다. 공개키 3곳은 `<my_npub>`로 바꿨다.
  - 예외: 탐침이 만든 실행 영수증 1파일에 포털 열쇠·해시가 남았다(B80-1, 판정 요청).
- **나머지**: 라이브 코어 편집 0 · 커밋 0
- **백엔드**: 회차 내내 `state.json` phase `ACTIVE`(`last_result.outcome: restarted`), 재기동·FAILED 없음.

## 집행 완료

### 2026-09-29 잔여 수리 — 정본 main

후속 공통 수리와 현재 코드를 대조한 뒤, 남은 결함을 아래처럼 닫았다. 원 훈련 당시의
수치·실패 기록은 변경하지 않았다. 이 절은 실제 수정·검증 범위이며 후보 기능과 구별한다.

| 항목 | 현재 상태와 근본 원인 수리 |
| --- | --- |
| B80-1 | 기존 허용 필드 투영이 list/detail/save/merge에 적용됨을 확인. 실제 이웃 조회에서도 인증 칸 없음. 옛 탐침 영수증은 파일 잠금·온라인 백업 뒤 인증 필드 40개를 가리고 secure_delete+VACUUM, 재사용 불가·재개 차단 처리. 현재 원장의 열쇠/해시 바이트 잔존 0. 원본은 디렉터리 0700·파일 0600 백업에 보존했고 회원 열쇠를 회전하거나 회원 링크를 끊지 않음. [처리 영수증](receipt_remediation.json). |
| B80-2 | 기존 unreplied와 unread 호환 별칭(미답신), 비이웃 DM null 계약을 유지. 실제 읽음 기록이 없는 시스템에서 읽음 수를 발명하지 않음. 관련 교재의 nullable 미답신 필터·발송 주소 참조까지 교정. |
| B80-3 | 기존 최신순·created_at·tags 보존 확인. since를 보드/저자/팔로우의 실제 질의에 전달하고 limit:0은 0건. 원래 말풍선 순서는 선언형 뷰 reverse로 복원(실행 값의 순서를 화면에 종속시키지 않음). 메시지 thread에도 표시 시각과 별개인 created_at 보존. |
| B80-4 | collection 완료 트랜잭션만 as_of를 기록. posts/search/latest/stats가 source:local_snapshot·as_of·stale·freshness를 전달. 기존 사본은 확인할 수 없는 수집 시각을 null로 유지하며 24시간 초과/미상은 stale. 발행일·파일 mtime을 수집 시각으로 추정하지 않음. 수집 실패는 시각을 갱신하지 않으며 HTML 응답은 실패. |
| F80-1 | alive:null에 state:unknown을 병기하고 미완료 프로브 행도 버리지 않음. alive==false 필터를 교재에 명시. 공통 filter 콜백의 직접 nullable 반환도 Bool 검사를 행 문맥 안에서 수행하여 row_index를 보존. |
| F80-2 | 이미 고친 절대 URL·post_id·pub_date·category 확인. latest의 items에도 식별자·날짜·분류를 전달. |
| F80-3 | detail의 items를 글 목록으로 수정. board는 게시판, posts는 기존 화면 호환 별칭. title은 작성자 원값이고 이미지 표시는 display_title로 분리. at/name/body/has_image의 기존 구조 칸을 유지. |
| B75-4 / 발신 인자 / B79-2 위임 | 기존 op별 부작용 투영·닫힌 발신 계약 확인. delegate는 런타임에서만 거절하던 mode/scope enum과 조건별 필수 인자를 선언 계약으로 올려 check에도 적용. 실제 발신 없이 publish dry_run·feed preview·delegate 오타를 검사에서 거절하는지 검증. |
| B72-2 / B78-2 / F72-2 | inbox search/level 및 포털 읽기/없는 대상 진단은 기존 수리 확인. blog latest의 지연 파일 생성은 이번에 제거. vault 파일이 없으면 명시적 export 안내 오류를 주고, 일반 블로그 읽기 연결도 DB 생성·FTS 초기화를 하지 않음. RAG 본문/검색/상태 조회도 읽기 전용 연결을 쓰며, 검색 중 벡터 테이블을 만드는 경로를 제거. |
| B79-2 블로그 폴더 | category 목록을 구성하는 각 폴더가 존재하는지 확인. 일부 정상 폴더 뒤에 없는 폴더를 숨기지 않으며, 정상 폴더의 검색 0건과 구별. |
| B79-3 / B78-8 | 실패 봉투의 action_health 판정은 기존 회귀 확인. 맥의 피드 세 갈래는 릴레이 완료 응답 부재·파싱 오류를 정상 0건/오래된 캐시로 위장하지 않음. 방명록·가족 사진 JSON은 파일 부재만 빈 목록, 손상/형식 오류/권한 오류는 실패. |
| F77-1 / F76-2 | 이미 추가된 가족신문·RSS·게시판·블로그 구조 칸 확인. 실제 로컬 읽기 11개 op의 반환 열을 재관측하고 값 없이 저장. [관측 열](repair_observations.json). |
| 교재 드리프트 | 386건 검사에서 남은 invalid 54건을 의도별 재작성. 추가로 실행 전에는 검사를 통과하던 블로그 본문/산출물 값 참조 3건과 조회수·방문자를 글 수로 잘못 가르치는 의도 2건 교정. 총 59건, 훈련 JSON의 대응 54행 반영. 원문·관측 통계는 provenance와 온라인 백업에 보존, 벡터를 다시 생성하고 FTS 정합 확인. [검토](corpus_review.json) · [적용](corpus_application.json). |

근본 원인은 **표시 값과 실행 사실의 혼합**, **조회와 초기화/쓰기의 혼합**, **빈 결과와
관측 실패의 혼합**, **선언 변경 후 남은 실행기억**이었다. 코드·선언·뷰·용례를 각 소유
경계에서 함께 수정했다. 도메인 이름을 공통 파서에 추가하거나 새 어휘를 늘리지 않았다.

### 검증

- 새 결함·직접 소비자 회귀 101건 통과. 프런트엔드 `npx tsc -p tsconfig.app.json` 통과.
- 교재 59건 × 빈 목록/정상/첫 호출 실패 = 177개 격리 실행 검증. 실제 파서·실행기·순수 표 연산을 사용하고 외부 도구·발신·모델은 격리. 중첩 trigger 프로그램도 별도로 컴파일/실행. [검증](repair_verification.json).
- 위임 계약 추가 후 관련 70건, 원격·회원 화면과 새 회귀 41건 통과. 원격 말풍선 역순에서도 버튼이 원래 행을 가리키며 원본 순서가 바뀌지 않는지 실제 JS 실행으로 검사.
- 라이브 재기동 정상(ACTIVE), 읽기·검사 전용 8건 통과. 블로그 신선도·이웃 투영·게시판 items·0건 피드·없는 폴더·발신 인자/위임 오타를 확인. [라이브 검증](repair_live.json).
- 386건 재검사 invalid 0. 빌드 정합·회원 셸 파생·폰 번들·은퇴 문구 검사 통과.
- 최종 직접 소비자 검사 103건 통과. 기존 테스트 2개의 import 대역·읽기 전용 DB 연결 대역을 새 계약에 맞춰 수정한 뒤 재검증. Python 라이브러리·어휘 아카이브·분리 배포 시스템 검사 71건 통과.
- 최종 종합 회귀 `pytest backend/ -m "not system" --ff`: **7,687 passed, 1 skipped, 95 deselected, 515.32초**, 실패 0. 제외된 system 95개 중 이번 변경 관련 71개는 위 별도 묶음으로 통과. 재기동 장애 주입·지도 이름 전수 감사는 이번 변경 대상이 아니어서 재실행하지 않음.

### 범위와 보존한 한계

- V80-1의 kind 7 반응 수집은 원 보고서의 **새 기능 후보**다. tags 보존으로 기존 kind 1의 답글 관계는 읽을 수 있지만 반응 조회 기능을 신설했다고 주장하지 않는다.
- unread 호환 별칭은 여전히 미답신 수이며 실제 미열람 추적 기능은 아니다. 블로그 stats는 조회수·방문자 분석을 제공하지 않는다.
- as_of는 RSS 수집 완료 시각이며 원격 실시간 최신성이나 전체 과거 글 수집의 보증이 아니다. 기존 수집 시각을 임의로 채우거나 원격 글을 이번 수리의 일부로 수집하지 않았다.
- 외부 게시·발행·메시지 발송 및 유료 AI 호출 없이 검증했다. 프런트엔드는 소스와 타입 검사로 확인했으며 배포 앱 바이너리를 새로 패키징한 것은 아니다.
