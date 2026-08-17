# 가이드 정리 백업 (2026-08-17)

`data/guides/` 79 → **74**. 삭제 5건 + 참조 수리 3곳.

## 삭제한 파일과 근거

| 파일 | 크기 | 근거 |
|------|------|------|
| `local_info.md` | 4,147자 | local-info 패키지가 2026-08-15 **디렉토리째 삭제**됨. 그런데 이 가이드는 `guide_db` 에 **등록된 채**(=검색으로 뽑혀 프롬프트에 주입) 남아 있었다 — 없는 도구의 사용법을 가르치는 상태. 후계=`[sense:search]{source:"naver", type:"cafe"}` |
| `html_video.md` | 10,479자 | `engines:html_video` 2026-08-05 은퇴(영상 정본=`[self:deck]{op:"video"}`). guide_db 미등록·인바운드 참조 0인데 본문은 **살아있는 가이드처럼** 파이프라인을 설명 = 죽은 경로 교습물 |
| `_deprecated_work_plan.md` | 5,754자 | 파일명이 스스로 deprecated 선언. `self:create_plan`·`self:execute_plan`·`self:file_write`·`sense:kr_stock_price`·`sense:search_gnews` 전부 은퇴어. 참조 0. 정본=`work_plan_writing.md` |
| `lecture_slides_with_illustrations.md` | 379자 | 2026-06-23 `slides.md` 통합 리다이렉트 스텁 |
| `lecture_slide_principles.md` | 266자 | 위와 같은 스텁 |

★스텁 2건을 지운 이유: **guide_db 미등록 = 검색으로 못 찾는다.** 리다이렉트는 "찾아온 사람을 보내주는" 장치인데
찾아올 경로가 없으므로 기능이 0이었다. (반대로 `remotion.md` 는 **남겼다** — 패키지가 `not_installed/` 에
살아 있어 "되살리려면 무엇을 해야 하는가"라는 생애주기-대칭 정보를 나른다.)

## 함께 수리한 참조 3곳 (지우면 끊기는 것들)

- `data/guide_db.json` — `local_info` 항목 제거 (70 → 69)
- `data/ibl_nodes_src/sense.yaml` — `[sense:startup]` 의 `guides:` 목록에서 `local_info.md` 제거 → 재빌드
- `data/guides/startup.md` — 본문 링크를 후계 어휘 안내로 교체
- `lecture_workspace/slide_ai.py` — 주석의 `lecture_slide_principles` 이름을 정본 `slides.md` 로

## 되살리는 법

이 폴더의 `.md` 를 `data/guides/` 로 복사하고, 등록이 필요하면 `guide_db.json` 에 항목을 되돌린다
(`guide_db.json.before`·`sense.yaml.before` 가 삭제 직전 상태). 단 **어휘가 죽은 가이드는 되살려도
죽은 경로를 가르친다** — 되살리기 전에 후계 어휘로 본문을 고칠 것.

---

## 2차 삭제 — 미설치 패키지용 가이드 (같은 날, 사용자 판정 "미설치용이면 지워")

가이드 74 → **69**, guide_db 69 → **66**. (`guide_db.json.before2` = 2차 삭제 직전 상태)

| 파일 | 크기 | 근거 |
|------|------|------|
| `house_designer.md` | 29,087자 | `house-designer` 패키지가 `not_installed/`. **guide_db 에 등록돼 있어** 의식 에이전트가 뽑을 수 있었다 — 돌지 않는 도구의 29KB 사용법이 프롬프트에 실릴 수 있는 상태 |
| `book_publishing.md` | 15,000자 | `publishing` 패키지가 `not_installed/`. 역시 guide_db 등록 |
| `book_typesetting.md` | 14,146자 | 위와 같은 패키지(조판 단계). 두 파일이 서로만 참조해 함께 나감 |
| `remotion.md` | 505자 | `remotion-video` 가 `not_installed/`. 1차에서 "묘비라 남긴다"고 판단했으나, **미설치 패키지 가이드는 남기지 않는다**는 규칙으로 통일 |
| `lecture_workspace.md` | 204자 | `slides.md` 리다이렉트 스텁. ★1차의 다른 스텁들과 달리 **해로웠다** — `data/ibl_nodes_src/self.yaml` 의 어휘가 이걸 가리켜서, 그 액션을 쓸 때마다 "slides.md 를 읽어라"라는 204바이트가 진짜 가이드 대신 주입됐다. self.yaml 을 `slides.md` 로 직결 후 삭제 |

**약 59KB 가 검색 풀에서 빠졌다.**

### 남긴 것과 근거 (이름이 비슷해 오해하기 쉬운 것들)

- `book.md` — `publishing` 이 아니라 **`[sense:book]`**(culture 패키지, 설치됨) 도서 검색 가이드
- `agent_publishing.md` — 이름만 publishing. 실제 내용은 **wrangler/Cloudflare Workers 배포**(cloudflare·web-builder 설치됨)
- `music_player.md` — `music-composer`(미설치)가 아니라 **music-player**(설치됨)

### 규칙 (다음에 패키지를 내릴 때)

**패키지를 `not_installed/` 로 내리면 그 가이드도 함께 내린다** — 파일 삭제 + `guide_db` 항목 제거.
설치/제거 생애주기는 대칭이어야 하고, 안 그러면 *돌지 않는 능력의 사용법*이 검색 풀에 남아
프롬프트 비용을 쓰고 사용자에게 없는 기능을 약속한다.

## 3차 삭제 — `phone_notifications.md` (사용자 판정)

가이드 69 → **68**. guide_db 는 66 불변(애초에 미등록).

| 파일 | 크기 | 근거 |
|------|------|------|
| `phone_notifications.md` | 1,930자 | **닿을 수 없었다** — guide_db 미등록·코드/yaml 참조 0. 게다가 알림 조회 절은 `[sense:phone]{op:"notifications"}` 의 desc 가 이미 덮는데, 이 가이드는 `run_command`+curl 을 가르쳐 **IBL 우선 원칙과 반대 방향**이었다 |

★**함께 사라진 정보(알고 지웠다)**: 폰 **걸음수**(`GET /phone/steps`)와 **위치**(`GET /phone/locations`)
엔드포인트는 이 파일에만 문서화돼 있었다. 위치는 `[sense:here]` 가 덮지만 **걸음수는 대응 어휘가 없다.**
수요가 생기면 두 갈래 — ①`[sense:phone]` 에 `op:"steps"` 추가(어휘 자격이 있는지부터 심사) ②`[self:script]`
등록 스크립트. 원문은 이 폴더에 보존돼 있으니 그때 꺼내 볼 것.
(관련 구현: `backend/services/phone_notifications.py` · `backend/surface/api_phone.py`)

## 4차 삭제 — `agent_publishing.md` (사용자 판정)

가이드 68 → **67**, guide_db 66 → **65**.

| 파일 | 크기 | 근거 |
|------|------|------|
| `agent_publishing.md` | 19,107자 | 에이전트를 Cloudflare Workers 웹앱으로 배포하는 절차서. 인바운드 참조 0 |

★참고: 이 파일은 3차 때 "이름만 publishing 이고 내용은 설치된 cloudflare/web-builder 배포라 남긴다"고
판단했던 것이다. 사용자 판정으로 뒤집혔다 — **웹앱 배포의 정본은 `webapp.md`**(등기부 `[self:webapp]` +
결정 트리 4부류 + 몸 공개면 레시피)이고, 이 파일은 그 위에 얹힌 19KB 중복 절차서였다.

---

## ★측정 함정 (이 정리 중 실측, 남겨 둘 것)

가이드 필요성을 판단하려고 카탈로그의 `(dormant: 키 없음)` 표시를 세었더니 **44개 액션이 dormant** 로
나왔다 — `sense:search`·`sense:realty` 처럼 매일 도는 어휘까지 포함해서. 원인은 시스템이 아니라 **측정**:
`_dormant_reason()` 은 `os.environ` 을 보는데, 독립 스크립트로 `ibl_access.build_environment()` 를 부르면
`.env` 가 로드되지 않아 모든 키가 없는 것처럼 보인다(백엔드는 부팅 때 dotenv 로 채운다).

`load_dotenv('.env')` 후 다시 재니 **dormant 0개**.

**교훈**: 프롬프트에 실리는 내용을 스크립트로 재현할 때는 **백엔드의 부팅 순서를 흉내내야 한다.**
안 그러면 "이 능력은 죽어 있다"는 잘못된 결론이 나오고, 그 결론으로 문서를 지우게 된다.
