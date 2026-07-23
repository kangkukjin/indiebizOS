# USB 손발(게스트 PC 헬퍼) 가이드 — [self:limb] 발급 · [limbs:guestpc] 조작

낯선 PC 에 **USB 를 꽂아** 그 PC 에서 셸·파일 작업을 시키는 얇은 손발(헬퍼) 시스템.
두뇌·신원은 전부 내 몸(허브)에 남고, USB 엔 **허브 비밀번호가 아니라 limb key 하나**만 실린다.
"USB 에 AI 를 담는" 게 아니라 **USB 를 내 몸의 착탈식 손발로 만드는** 것.

## 구조 (폰↔PC 직접 연결 아님 — 둘 다 허브를 거친다)

```
내 폰/런처 ──(터널)──> 내 허브(두뇌·신원) <──(그 PC 인터넷, 아웃바운드)── 게스트 PC 의 헬퍼(손발)
```

헬퍼는 그 PC 에서 허브로 **아웃바운드** 접속(그 PC 방화벽·공유기 무설정). 허브가 셸 명령을
큐에 넣으면 헬퍼가 `/limb/poll` 롱폴로 당겨가 실행하고 `/limb/result` 로 회신한다. 폰이
LTE(CGNAT) 뒤에서 명령을 당겨가는 구조(phone_jobs)를 그대로 쓴다.

## 1) 발급 — USB 만들기

```
[self:limb]{op: "issue", alias: "사무실PC", ttl_days: 14, os: "win"}
```

- 새 limb key 를 만들고 `outputs/limb_issue/<alias>/` 에 **USB 페이로드**를 쓴다:
  `indiebiz-helper.json`(내 몸 주소 + 키 + 이름) + `사용법.txt`.
- `os`(win/mac/linux)를 주고 `helper/dist/` 에 빌드된 실행파일이 있으면 함께 동봉한다.
- 이 폴더 전체를 USB 에 복사한다.
- `ttl_days` 유효기간이 지나면 키가 자동 소멸(잊고 폐기 안 해도 안전). `0`=무기한.
- ★주소는 **직접 서빙 호스트(direct_hosts)** 로 박힌다 — Worker CDN 은 `/limb/` 를 프록시하지
  않으므로. 공개 주소(터널/얼굴)가 아직 없으면 `warning` 이 뜬다(먼저 터널 발급 필요).

## 2) 실행 — 그 PC 에서 헬퍼 띄우기

USB 를 그 PC 에 꽂고 헬퍼 실행파일을 더블클릭한다(`indiebiz-helper.json` 이 같은 폴더에
있어야 함). 헬퍼가 내 허브에 붙으면 **자동으로 연결(승인)** 되어 바로 쓸 수 있다.

## 3) 이름으로 명령 — 오배송 방어

```
[limbs:guestpc]{op: "shell", cmd: "python --version", limb: "사무실PC"}   # 이름으로 대상 지정
[limbs:guestpc]{op: "shell", cmd: "dir", cwd: "C:/Users", limb: "사무실PC"}
[limbs:guestpc]{op: "list", path: "C:/Downloads", limb: "사무실PC"}
[limbs:guestpc]{op: "read", path: "C:/note.txt", limb: "사무실PC"}
[limbs:guestpc]{op: "write", path: "C:/out.txt", content: "…", limb: "사무실PC"}
[limbs:guestpc]{op: "info", limb: "사무실PC"}
```

**승인은 자동이다** — 붙는 즉시 명령을 받는다. 대신 안전의 무게중심이 *승인 게이트*에서
*이름 명시*로 옮겨갔다: 명령할 때 `limb: "이름"` 으로 어느 PC 인지 지정한다(발급 시 지은
alias). 손발이 **둘 이상이면 이름은 필수** — 이름 없이 부르면 실행하지 않고 붙어 있는
목록을 보여준다. 이 강제가 곧 방어다: 유출된 키로 낯선 PC 가 하나 더 붙으면 손발이 둘이
되어 이름을 요구받고, 그때 "어? 손발이 둘이네?" 하고 알아챈다. 결과에는 어느 손발에서
돌았는지(`limb_name`)가 늘 찍혀 사후에도 확인된다.

- 손발이 하나뿐이면 `limb` 생략 가능(그 하나로 감).
- 다른 PC 에서 같은 키가 붙으면 자동승인하되 **위치 변경 알림**이 뜬다(내가 안 옮겼으면 유출 신호 → revoke).
- 특정 손발을 잠시 막고 싶으면 `[self:limb]{op:approve, target:"이름", approved:false}`(수동 잠금).
- 셸은 그 PC 의 기본 셸(win=`cmd /c`, mac·linux=`sh -c`). `timeout`(초, 기본 120).
- **눈 없음**: 화면 캡처·GUI 클릭은 1단계 미지원. CLI 없는 GUI 전용 앱은 다루지 못한다
  (셸/파일로 되는 작업이 PC 일의 대부분). 화면 조작은 후속 op 로 얹을 예정.

## 4) 해제 — 볼일 끝

```
[limbs:guestpc]{op: "detach", limb: "사무실PC"}   # 그 PC 헬퍼 종료
[limbs:guestpc]{op: "detach"}                     # 하나뿐이면 생략
```

휴대 USB 로 PC 를 옮겨 다니는 사용의 '볼일 끝' 동작 — 그 PC 의 헬퍼가 종료되고 그 PC 엔
아무것도 남지 않는다. 자동승인 체제라 그 PC 에서 헬퍼를 **다시 실행하면 또 자동으로 붙는다**
— detach 는 '지금 이 세션 끝'이지 영구 차단이 아니다. 그 PC 주인 입장의 해제는 더 단순하다:
창 닫기(설치·상주 없음). 영구 차단(유출·이탈)은 아래 revoke.

## 5) 폐기 — 뒷정리

```
[self:limb]{op: "revoke", target: "사무실PC"}     # 이 키만 폐기(USB 분실 시)
```

USB 를 잃어버려도 이 키 하나만 폐기하면 끝 — 허브 로그인·구독·데이터 API 키는 USB 에
실리지 않으므로 유출될 게 없다.

## 원칙 · 경계

- **augmentation-over-autonomy**: 남의 PC 에 셸을 내주는 고권한 도구다. 내 PC 아닌 곳에
  쓸 땐 그 PC 주인의 명시적 동의가 전제("남의 의도 자동실행 금지"의 거울상).
- 손발은 신뢰 원장(`grant_body`)의 레벨4 이웃으로 **자동 등록되지 않는다** — 인가는 오직
  limb key(붙으면 자동승인). 셸 실행 몸에 이웃 자격을 함부로 주지 않기 위함.
- 자동승인의 오배송 방어는 *이름 명시*가 진다(손발 둘 이상이면 필수). 유출 방어선은
  revoke(키 폐기)와 host 변경 알림. 편의(마찰 없는 로밍)와 안전(이름·폐기)의 트레이드오프.
- 허브가 켜져 있고 터널이 살아 있어야 한다(본체 의존). 대신 USB 는 수 MB 로 얇다.
- 서명 없는 실행파일은 SmartScreen·백신 경고가 뜰 수 있다(회사 PC 는 차단 가능).

## 헬퍼 빌드 (배포자용)

`helper/` 에 Go 단일 파일 소스. `helper/build.sh` 로 win/mac/linux 크로스컴파일 →
`helper/dist/`. 발급([self:limb]{op:issue})이 대상 OS 실행파일을 USB 페이로드에 동봉한다.
```
cd helper && ./build.sh      # Go 설치 필요
```
```

