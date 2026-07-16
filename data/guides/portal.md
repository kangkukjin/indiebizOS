# 개인 포털 (커뮤니티 홈) 가이드 — [others:portal]

"커뮤니티당 노드 하나" 전략의 홈. 공개 홈(`/h/<5자 코드>/`)으로 이웃을 모으고, 레벨에 따라
콘텐츠(가족신문·공개파일)와 계기(🎨 아이콘, 🎵 유튜브뮤직, 날씨 등)를 **설치 없이 브라우저로**
빌려 쓰게 한다. 이메일 보급 모델: 운영자 1명=노드, 구성원=브라우저.

## 개념

- **포털은 여러 개** — 대상별 공개 주소(가족용·친구용…, showcase 바스켓 패턴). 각 포털이
  자기 회원 명부·진열 다이얼(첫페이지 구성)을 독립으로 가진다. 새 포털=진열 전부 꺼진 채 시작.
- **가입/로그인 = 아이디+비밀번호(네이버식)**: 홈에서 이름·아이디·비번으로 가입 → **레벨 0
  자동 등록 + 즉시 로그인**(승인 대기열 없음 — 레벨 0은 공개층뿐이라 무위험, **승급이 곧 승인**).
  자동 로그인 체크(기본)=1년 쿠키, 해제=브라우저 세션. form autocomplete 시맨틱이라 브라우저
  비밀번호 관리자가 저장·자동완성.
- **개인 링크 = 운영자 발급 즉시 로그인 열쇠**: `/h/<슬러그>/k/<회원키>` 클릭 → 쿠키 → 홈.
  **비밀번호 분실 복구 경로**(재설정 메일 불필요 — 운영자가 issue 로 새 링크 전달).
  유출·이탈=`revoke`(그 사람의 링크·쿠키·아이디 로그인 전부 차단). 홈 주소는 완전 공개 가능.
- **레벨**: 0 손님 / 1 이웃 / 2 가족 (포털별).
- **다이얼**: 계기·콘텐츠마다 `{켬/끔, min_level}`(누가 보는가=계기별 진열 사다리).
- **일일 사용 한도는 포털 단위 설정**: 손님/회원/전체 계기 사용 캡(`guest_daily`·`member_daily`·`global_daily`)은
  코드가 아니라 `[others:portal]{op:"config", portal, guest_daily, member_daily, global_daily}` 또는 앱 **설정 탭**에서
  포털마다 정한다(그 포털 전 계기 공통). min_level 이 접근을 막으므로 캡을 공통으로 둬도 안전. 기본 손님 3/회원 50/전체 300.
  콘텐츠 타일(아웃링크)은 사용 게이트를 안 지나 캡 미적용. (계기의 카운트 캡은 포털 config 가 단일 소스 — display op 로 계기별 guest_daily 를 넣어도 계기엔 포털 값이 우선한다. 계기별로 다르게 두는 건 min_level/켬끔뿐.)
- **진열 가능 목록은 노드 축 유도**: self·others·limbs 가 낀 계기와 host(집 PC 상태)는 목록 자체에
  없음(다이얼 불가 — 공급망 게이트 철학). 예외는 portal_core.MANUAL_LISTABLE 에만(현재 ytmusic).
- **회원 실행 게이트**: 범용 /ibl/execute 직결 금지 — 계기 `app:` 블록 선언 템플릿의 인스턴스만
  실행(op·mode 등 리터럴 파라미터 강제, `$key`·`{field}` 자리만 값 허용) + 3중 일일 한도 + 감사로그.

## op 요약

대부분 op 는 `portal` 파라미터(슬러그/이름)로 대상 포털을 고른다 — 비우면 첫 포털.

| op | 용도 |
|---|---|
| status | 그 포털의 주소·회원 수·오늘 사용량 |
| portals / create / remove | 포털 목록 / 새 주소 만들기(title) / 삭제(회원 있으면 force) |
| members | 이웃 목록 + 개인 링크(key_link) |
| join | 이웃 직접 등록 (name 필수, 링크 전용 회원) → 개인 링크 반환 — 본인에게만 전달 |
| promote | 레벨 변경 (member_id + level 또는 +1, down:true 면 -1) |
| issue / revoke | 개인 링크 재발급 / 회수 |
| display | 다이얼 — key 없으면 목록. **노출 사다리**: level_down=한 칸 열기(꺼짐→가족만→이웃→손님) / level_up=한 칸 잠그기(끝은 꺼짐). toggle/min_level/guest_daily/member_daily 직접 지정도 가능 |
| audit | 사용 기록 (누가·언제·무엇을) |
| config | title(이름)·intro(소개글) |

## 예시

```
[others:portal]{op: "create", title: "친구들"}               → 친구용 주소 신설
[others:portal]{op: "display", portal: "친구들", key: "weather", level_down: true} → 그 포털에 날씨 진열
[others:portal]{op: "join", name: "아내"}                    → 링크 전용 회원 + 개인 링크
[others:portal]{op: "promote", member_id: "m1a2b3"}          → 레벨 +1
[others:portal]{op: "display", key: "icon", level_down: true} → 아이콘 한 칸 열기 (꺼짐이면 가족만으로 켬)
[others:portal]{op: "display", key: "icon", level_up: true}   → 아이콘 한 칸 잠그기 (레벨 2에서 또 올리면 꺼짐)
[others:portal]{op: "display", key: "weather", min_level: 0, guest_daily: 3}  → 손님 개방
[others:portal]{op: "audit"}                                 → 사용 기록
```

## 아키텍처 (3층 + 함정)

- 운영자 어휘 = community-portal 패키지 handler.py / 상태·게이트 = **portal_core.py 단일 소스**
  (`data/portal_state.json`, flock 직렬화) / 공개 서빙 = `backend/api_portal.py` / Worker `/h/`
  (public-files 와 공유, **무캐시 no-store** — 쿠키 개인화라 캐시 절대 금지).
- ★portal_core.py 수정 = 백엔드 재시작 필요(api_portal 이 sys.modules 캐시). handler 만이면 /packages/reload.
- 계기 페이지 = 원격 런처 셸 재사용(`window.__PORTAL` 주입, 포크 없음). 실행은 `/h/<슬러그>/tool/<계기>`.
- 크롤형 계기(직방·당근·여기어때)는 남용 시 집 IP 차단(팔의 평판) — 손님(레벨 0)에 열지 말 것.
- 아이콘: 브라우저는 클립보드 자동복사 불가 → "꾹 눌러 복사" 안내(포털 전용 note). ~93원/장 → 한도.
- 유튜브뮤직: googlevideo URL 이 맥 IP에 잠김 → 게이트가 stream_url 을 오디오 프록시
  `/h/<슬러그>/tune/<video_id>`(api_portal.tune, Range 통과·만료 재해소·회원 쿠키 필수)로
  바꿔쳐 **외부망에서도 재생**. 수제 tune URL(캐시 미스)은 사용량으로 카운트.
- 감사로그 = `data/portal_audit.jsonl` (거부 포함).
