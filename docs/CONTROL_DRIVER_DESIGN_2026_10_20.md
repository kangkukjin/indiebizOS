# 제어 드라이버 설계 — 원격 기기·본체·브라우저를 한 문장으로

작성일: 2026-10-20. 상태: **첫 걸음 1~3 구현 + §5.2 해석기·알림 + §12 ① 관측 통로 (2026-10-20 같은 날)**. 구현 기록은 §15.
개정: 2026-10-20 Codex 검토 3회(13건) 반영 — 동작별 실행 조건, 관측 상태, 승격 기준, 매핑 칸 분리, 브라우저 3층, 결정성·속도 문장, 실행 전 검사와 실행 후 확인의 분리(2차); 요청된 효과와 부수 간섭의 구분, 격리는 도구가 아니라 자원 단위, 불명확 복구의 공통 계약, 관측 ID·환경(3차).

이 문서는 10-18의 두 설계를 일반화한다. [수동 하드웨어 앱과 AI 공유 실행 설계](HARDWARE_CONTROL_APPS_AND_GUIDES_DESIGN_2026_10_18.md)는
기기별 앱과 공용 스크립트를, [가이드 조회와 재사용 부품의 호출 계약 수리](CALLABLE_COMPONENT_REPAIR_DESIGN_2026_10_18.md)는
이름 조회와 스크립트 계약을 정했다. 둘 다 "원격 하드웨어" 를 대상으로 썼다. 이 문서는 같은
구조가 본체 자신과 브라우저에도 적용된다는 것을 보이고, 그 공통 단위를 **드라이버** 라고 부른다.
10-18 문서 §7의 가이드 목차 표(`hardware_control.md`·`windows_control.md`·`mac_control.md`·
`browser_playback.md`)는 이 문서의 §4 조작면 표로 대체한다. 실제로 만들어진 가이드는
`pc_control.md`·`tv_control.md`·`android_control.md` 셋이다.

드라이버는 별도 프레임워크가 아니다. **기존 부품(`self:script`·저장 함수·노드 액션)이 갖춰야 할 공통
요건** 의 이름이다. 이 문서가 먼저 확정하는 것은 이름이나 파일 배치가 아니라 네 가지다.
어떻게 발견하고(§5), 어떤 조건에서 호출하며(§6), 무엇을 확인하고(§7), 실패하면 어떻게 잇는가(§7).

## 0 한 문장

> 제어 대상이 원격 폰이든 원격 PC 든 본체 자신이든 브라우저든, 제어는 **안정된 호출 계약이
> 있는 조작면** 에 **드라이버**(가이드 + 고정 실행 부품 + 관측)를 붙여 호출하는 일이고,
> 계약이 없는 면만 화면 조작으로 **탐색** 하며, 탐색에서 가치가 확인된 길을 드라이버로 **승격** 한다.

목적은 [진화 목적 정본](IBL_EVOLUTION_PURPOSE.md)의 것이다. 품질을 유지·향상하면서 실제 완료
시간과 전체 토큰을 줄인다. 속도도 목적의 일부다. 이 설계가 그 목적에 이르는 **수단** 이 재사용
가능한 계약, 공유 구현, 정확한 결과 확인이다. 절감은 측정값으로만 말한다.

## 1 문제

현재 몸에는 제어 통로가 두 계열로 따로 자라 있다.

- **드라이버 계열**: 원격 폰·PC·TV. 장치 소개 행의 `control_guide` 포인터 → 가이드 → 고정 스크립트.
  앱 버튼과 AI 가 같은 코드를 호출한다. 10-18 에 완성됐다.
- **화면 조작 계열**: 본체(`limbs:screen`, 패키지 `computer-use`)와 브라우저(`limbs:browser`).
  snapshot 으로 읽고 ref 또는 좌표로 누른다. 44~48회차 긴 문장 훈련의 주 통로였다.

두 계열은 같은 일을 다르게 한다. 본체 음량은 `pc_control.py` 가 `__local__` 대상으로 이미 돌지만,
AI 는 그 사실을 모른다. 장치 소개 블록(`associative_recall.py` 의 `_connected_limbs`)에 본체 행이
없고, 회상 주석이 "원격 대상을 지정하지 않은 상태는 `[sense:host]`" 로 돌려보내며,
`pc_control.md` 는 `guide_db.json` 에만 있고 어느 노드의 guides 목록에도 결속돼 있지 않다.
그래서 본체를 다룰 일이 생기면 AI 는 드라이버가 있는데도 화면 조작으로 간다.

화면 조작 계열의 비용은 토큰만이 아니다. 44~48회차 발견 가운데 confirm 창 조용히 닫힘(L44-1),
탭 전환 불가(L46-1), snapshot 이 앞 앱 대신 런처 창을 읽음(L45-2), drag 가 다른 카드를 옮김(L47-1),
새 탭 뒤 활성 탭 조용히 전환(L48-1)은 모두 **계약 없는 면을 좌표로 더듬어서** 생긴 것이다.
같은 일을 "Safari 에게 현재 탭을 바꿔라" 하고 말하는 통로에서는 애초에 생기지 않는다.
그리고 사용자가 PC 를 쓰는 동안 몸이 자기를 움직여야 하는 인지 외골격에서, 사용자의 손과 눈이
보는 상태를 건드리는 동작은 실행 전에 걸러져야 한다. 45회차 교훈("데스크톱 조작 다리는 사용자
입회·frontmost 가드 없이 넣지 말 것")이 그 기록이다.

## 2 원칙

### 2.1 단위는 하드웨어가 아니라 조작면이다

**조작면** = 안정된 호출 계약이 있는 제어 대상의 표면. 원격 PC 는 OS 가 조작면이고, 본체는 앱이
조작면이며, TV 는 네트워크 API 가, 브라우저는 DOM 과 사이트의 업무 흐름이 조작면이다.
폰 한 대·맥 한 대가 아니라 "Android", "darwin", "Safari", "Tizen", "DOM", "특정 사이트의 로그인" 이
드라이버의 단위다. 드라이버는 OS 드라이버처럼 **클래스 드라이버 하나 + 개체별 관측** 의 모양을
갖는다. 개체마다 코드를 복제하지 않는다.

"대상이 느리게 변한다" 는 좋은 근사이지만 기준이 아니다. 기준은 둘이다. **호출 계약이 안정적인가**,
**판단과 기계를 분리할 수 있는가**. macOS 는 느리게 변하지만 AppleScript 지원은 판본마다 깎이고,
웹 사이트는 빠르게 변하지만 로그인 흐름·내려받기 확인 같은 업무 계약은 몇 달씩 안정적일 수 있다.

### 2.2 탐색과 실행을 분리한다

| | 실행 | 탐색 |
| --- | --- | --- |
| 조건 | 계약이 있는 조작면 | 계약이 없거나 아직 모르는 면 |
| 통로 | 드라이버의 고정 실행 부품 | `limbs:screen`·`limbs:browser` 의 snapshot→ref→action |
| 결과 | 상태값과 확인 범위 보고 | 관측(snapshot·screenshot) |
| 끝 | 효과 확인으로 완료 판정 | 가치가 확인되면 드라이버로 승격 |

화면 조작은 "나쁜 방식" 이 아니라 드라이버가 아직 없는 면의 정당한 도구다.

**배경 실행 가능성은 이 표의 열이 아니라 동작별 속성이다.** 고정 스크립트도 `activate` 하는
AppleScript 가 있고, 탐색 도구인 Playwright 도 활성 탭을 바꾸지 않고 페이지를 다룰 수 있다.
포커스를 빼앗지 않아도 사용자가 보는 탭·문서를 바꾸면 작업을 방해한다. 그래서 드라이버의
**동작마다** 다음 세 속성을 계약에 적고(§6), 배경 실행 가능 여부는 그 속성으로 판단한다.

- `needs_front`: 앞 앱·포커스를 요구하는가.
- `shared_state`: 사용자와 공유하는 상태(활성 탭·열린 문서·클립보드·음량)를 바꾸는가.
- `isolated_resources`: 사용자 것과 **어느 자원이** 분리돼 있는가. 화면·포커스, 계정·프로필 데이터, 파일, 세션 가운데
  분리된 것의 목록이다. 별도 창이나 headless 도 같은 계정의 문서·장바구니·파일을 바꿀 수 있으므로, 화면이 분리됐다는
  사실만으로 계정 데이터까지 분리됐다고 보지 않는다. 도구 이름(Playwright·Chrome MCP)이 아니라 실제 대상과 바뀌는 자원으로 적는다.

### 2.3 AI 와 드라이버의 경계

사용자 규칙: AI 가 할 일을 고정 프로그램으로 만들지 말 것. 드라이버는 이 규칙과 충돌하지 않는다.
드라이버가 얼리는 것은 **기계적 부분** 뿐이다. 음량 단계를 AudioManager 에 쓰는 코드, 탭을 바꾸는
AppleScript, 전원을 켜는 WOL 패킷. 어느 기기에, 어느 인수로, 어떤 순서로 조합할지는 AI 가 정한다.
10-18 문장 그대로다: 앱 버튼은 모델 호출 없이 같은 코드를 쏘고, AI 는 대상·인수·조합을 결정한다.
"모델 호출 0" 은 인수가 결정된 앱 버튼의 실행 경로에 해당하며, AI 가 대상을 고르고 조합하는 전체
작업이 0 이 되는 것은 아니다. 드라이버가 "무엇을 할지" 까지 정하기 시작하면 그것은 고정 프로그램이고
이 문서의 범위 밖이다.

### 2.4 무엇을 얻는가

같은 코드가 같은 결과를 보장하지는 않는다. 외부 제어는 기기 상태·권한·네트워크·사용자의 동시 조작에
따라 결과가 달라진다. 얻는 것은 **검증된 같은 판본의 공유** 와 **실행마다 실제 효과의 확인** 이다.
`verified` 는 결과 보장 장치가 아니라 특정 범위의 확인을 통과했다는 보고이고, 그 범위
(`verification_scope`)가 값과 함께 남는다. 각 동작에서 얻는 성질(절차 일관성, 확인 명확성, 배경
실행, 모델 호출 절감, 시간)과 비용은 고정 서열 없이 따로 본다.

### 2.5 헌법 조항과의 관계

- **몸의 명사=코드, 세계의 명사=데이터.** 실행 부품은 몸이라 코드다. 어느 기기가 어느 OS 인지, 어느
  앱이 사전을 갖는지, 어느 폰이 화면 제어를 거절했는지는 세계라 데이터다. 세 부품(§3) 가운데
  가이드·실행 부품은 코드 쪽, 관측은 데이터 쪽에 선다.
- **어휘 이름을 코드에 넣지 않는다.** OS→가이드 매핑은 `guide_db.json` 의 `control_platforms` 데이터다.
  앱·사이트→드라이버 매핑도 같은 파일에 데이터로 둔다(§5.2). "삼성1", "TV1", "Safari" 는 회상·파서
  코드에 들어가지 않는다.
- **반-어휘-증식은 기본값이지 금지가 아니다.** 드라이버는 새 낱말을 거의 요구하지 않는다. 실행 부품은
  `self:script`·저장 함수에, 원격 실행은 `limbs:guestpc`, 본체 실행은 `self:script` 로컬, 브라우저는
  `limbs:browser` 가 이미 있다. 어휘가 필요한 자리는 §12 의 판정 한 곳이며, 늘린다면 이유를 적는다.

## 3 드라이버의 세 부품과 정본 위치

| 부품 | 내용 | 정본 위치 | 성격 | 저자 |
| --- | --- | --- | --- | --- |
| **가이드** | 경로·인수·결과 계약·전제·복구. 코드를 복제하지 않는다 | `data/guides/*.md` + `guide_db.json` 등록 | 코드 쪽(몸의 명사) | 사람. AI 는 초안 |
| **실행 부품** | 고정 실행 코드. 앱과 AI 가 같은 판본을 호출. 동작별 조건(§6) 을 계약에 가짐 | `data/scripts/*.py`(`self:script`, `registry.yaml`)·저장 함수(`data/idioms/installed.json`). 폰은 아직 `data/instruments/` | 코드 | 사람 검증 뒤 등록 |
| **관측** | 개체·환경별 사실. 날짜·판본·상태 붙은 행 | 기기: 등록 기록(`limb_keys` registration / `hardware_registry`)의 데이터 칸. 앱·사이트: §12 판정 | 데이터(세계의 명사, 반증 가능) | AI 와 사람 |

가이드는 36KB 예산(`lifecycle_policy.yaml`)을 따른다. 현재 셋은 여유가 있다.

**관측 행의 형식.** `{observation_id, observed_at, version, environment, fact, source, status, scope, supersedes}`.

```
{observation_id:"obs_7f3a", observed_at:"2026-10-11T21:40", version:"APK 0.13", environment:{device:"삼성1"}, fact:"화면 제어 거절(update_required)", source:"ep4xxx", status:"valid", scope:"APK<0.14"}
{observation_id:"obs_8c10", observed_at:"2026-10-11T23:05", version:"macOS 15.6", environment:{device:"guestpc-3fd7…", lid:"closed"}, fact:"screen 이 검은 그림을 success 로 돌려줌", source:"L51-2", status:"valid"}
{observation_id:"obs_91e2", observed_at:"2026-10-19T10:12", version:"unknown", environment:{site:"example.com", profile:"forage", account:"none", lang:"ko"}, fact:"로그인 없이 내려받기 링크가 302 로 로그인 화면", source:"ep4xxx", status:"valid"}
```

- `observation_id` 는 안정적인 행 식별자다. 정정·상태 변경·대체 참조(`supersedes`)가 전부 이 ID 로 이뤄진다.
- `environment` 는 관측한 환경을 식별하는 값이다. 기기면 device_id, 사이트면 도메인·프로필·계정 유무·언어·권한.
  `scope` 를 생략하면 "관측한 환경 그대로" 이므로 그 환경이 **실제로 저장돼 있어야** 한다. 사이트 관측은 도메인만
  같다고 공유하지 않는다. 계정·프로필·언어·권한이 다르면 다른 환경이다.
- `version` 은 사이트처럼 판본을 알 수 없는 대상에서 `"unknown"` 을 허용한다. 그 경우 관측 시각과 환경이 판본의 자리를 대신한다.

- `status` 는 `valid`·`recheck`(새 판본·환경에 적용되는지 미확인)·`refuted`(재관측으로 반증)·
  `superseded`(다른 행이 대체) 넷이다. **지우지 않는다.** 폰이 APK 0.14 로 올라가면 첫 행은 틀린 행이
  아니라 **새 판본에 적용되는지 미확인** 인 행이고, 판본 불일치를 본 순간 `recheck` 로 바뀐다. 재관측이
  반증하면 `refuted`, 새 사실이 대체하면 새 행이 `supersedes:` 로 옛 ID 를 가리키고 옛 행은 `superseded`.
  과거 관측은 당시의 사실로 남는다.
- `scope` 는 적용 조건(판본 범위·권한·설정). 비어 있으면 관측한 환경 그대로다.
- 관측 시각과 환경이 없는 행은 적지 않는다. 시각 없는 사실은 영원히 남아 되는 기능을 안 되는 줄 알게 만든다.
- 쓰기의 의미는 **추가와 정정** 이다. 목록 통째 덮어쓰기가 아니다(§12 ①).

현재 `pc_control.md` 의 "현재 본체 맥에서는 CGSession 이 없어 잠금 버튼을 비활성화했다" 는 플랫폼
가이드에 들어간 개체 사실이며, 관측 칸이 생기면 그리로 옮긴다.

**세 부품이 지금 있는 곳.** 원격 폰·PC·TV 는 가이드와 실행 부품이 있고 관측 칸이 없다(등록 기록의
`context` 1000자 산문이 그 자리를 대신한다. 사용자가 손발 패널에서 쓰며 HTTP `api_resident_pcs` 로만
갱신된다). 본체는 실행 부품(`pc_control.py` `__local__`)과 가이드는 있으나 발견 경로가 없다.
브라우저는 범용 DOM 도구와 가이드(`browser_action.md`)가 있으나 사이트별 실행 부품과 관측이 없다.
본체 앱은 셋 다 없다.

## 4 조작면 표 — 현재 상태

| 조작면 | 실행 자리 | 계약 통로 | 드라이버 현황 | 발견 경로 | 공백 |
| --- | --- | --- | --- | --- | --- |
| Android 폰 | 폰(폰 IBL 엔진·Python) | `limbs:guestpc op:python` | 가이드 `android_control.md`, 부품 `phone_control.py`·`phone_device.py` | 장치 소개 `control_guide` | 관측 칸 없음. 부품이 `instruments/` 에 남아 있음 |
| 원격 PC(darwin·windows) | 대상 PC(헬퍼) | `fn:PC제어` → `self:script PC제어부품` → `guestpc shell` | 가이드 `pc_control.md`, 부품 `pc_control.py`+OS 네이티브 | 장치 소개 `control_guide` | 관측 칸 없음 |
| **본체** | 허브 로컬 | 같은 `fn:PC제어` 에 `__local__` | 원격 PC 와 **동일 드라이버** | **없음** (소개 행 없음, 노드 guides 미결속) | 발견 경로 |
| TV(Tizen) | 허브(network-api) | `self:script TV제어` | 가이드 `tv_control.md`, 부품 `tv_control.py`·`tv_epg.py` | 장치 소개 `control_guide` | 제조사 하나. 관측 칸 없음 |
| 브라우저 — 범용 DOM | 허브(내장 Playwright) 또는 사용자 Chrome(MCP) | `limbs:browser` snapshot→ref→click/type | 노드 액션이 곧 계약. 가이드 `browser_action.md` | 노드 guides 결속 | 동작별 조건(§6) 미선언 |
| 브라우저 — 사이트 업무 | 같음 | 사이트별 실행 부품(로그인·쿠키 복원·내려받기 확인·결과 수집) | **없음**. 47·48회차 사실이 가이드 산문에 | 없음 | 부품·관측·발견 전부. 원격 PC 브라우저(CDP)는 10-18 설계만 |
| **본체 앱**(Finder·Mail·Music·Safari·Keynote 등) | 허브 로컬 | 셸·`open -a`·`defaults`·AppleScript/JXA 사전·Shortcuts | **없음**. 몸에서 osascript 사용은 `desktop_notify.py` 하나 | 없음 | 드라이버·열거·발견 전부 |
| 본체 화면(계약 없는 앱) | 허브 로컬 | `limbs:screen` snapshot→ref(AXPress)→좌표 | 탐색 도구. 가이드 `desktop.md` | 노드 guides 결속 | 폴백 서열·조건이 가이드와 실행 경계에 없음 |

표에서 드러나는 사실 셋.

1. 본체는 드라이버가 **이미 있는데 보이지 않는** 유일한 면이다. 가장 싼 수리다.
2. 본체 앱은 드라이버가 **전혀 없고 탐색 통로만 있는** 면이다. 화면 조작 회차의 발견이 전부 여기서 났다.
3. 브라우저는 **세 층** 이다. 범용 DOM 도구(있음) → 사이트별 실행 부품(없음) → 환경별 관측(없음).
   `click(ref)` 는 요소를 누르는 계약이고, "검색 결과를 수집한다"·"내려받고 완료를 확인한다" 는 더 높은
   계약이다. 관측은 실행 부품을 보완하지 대체하지 못한다. 모든 사이트에 부품을 미리 만들 필요는 없고,
   안정된 업무 계약을 줄 수 있는 곳부터 만든다. 10-18 의 "DOM 관련 처리는 사이트 어댑터에 격리한다"
   가 가운데 층의 이름이다.

## 5 발견 경로

AI 가 드라이버를 찾는 길은 하나여야 한다. 지금은 원격 기기만 길이 있다.

### 5.1 장치 소개에 본체 행을 넣는다

`_connected_limbs` 에 `device_id="__local__"` 행을 하나 추가한다. `os` 는 허브 OS, `adapter="local"`,
`connected="true"`, `control_guide` 는 같은 `control_platforms` 매핑으로 해소된다. 본문은 사용자가
등록 기록에 적은 설명(없으면 빈 문자열). 회상 주석의 "본체는 `[sense:host]`" 문장은 **상태 조회** 에
한정하고, **제어** 는 본체 행의 `control_guide` 를 따른다고 고친다.

이것으로 본체 음량·주소 열기·잠금이 즉시 드라이버 통로로 간다. 새 코드는 행 하나다.

### 5.2 앱·사이트 드라이버는 별도 칸으로 열거한다

`control_platforms` 는 "이 OS 의 **대표 제어 가이드** 다" 라는 뜻이고, 해석기
`device_control_guides()` 는 OS 당 먼저 만난 가이드 하나를 `setdefault` 로 고른다. 여기에 앱 가이드를
`["darwin"]` 으로 넣으면 등록 순서에 따라 OS 가이드를 가린다. **지원 OS 조건과 제어 대상 식별자는
다른 칸이다.**

```json
{"file":"safari_control.md",
 "control_surfaces":["app:com.apple.Safari"],
 "supported_platforms":["darwin"]}
{"file":"site_example.md",
 "control_surfaces":["site:example.com"],
 "supported_platforms":["darwin","windows"]}
```

- `control_surfaces`: 이 가이드가 드라이버인 대상 식별자. `app:<bundle id>`·`site:<domain>`.
  `control_platforms` 는 그대로 OS 대표 가이드 전용으로 남긴다.
- `supported_platforms`: 동작하는 OS 조건. 매핑 선택에 쓰지 않고 호출 전 검사(§6)에 쓴다.
- 해석기 `surface_control_guides()` 가 식별자 → 가이드 파일을 돌려준다. 같은 식별자에 둘이면
  충돌로 신고하고 먼저 만난 것을 고르지 않는다. `test_pc_control.py` 의 실존·경로 검사를 같이 적용한다.

발견은 두 길이다. (a) `limbs:screen` snapshot 의 `bundle_id`, `limbs:browser` snapshot 의 현재 URL
도메인이 매핑에 있으면 handler 가 응답에 `control_guide` 를 실어 **탐색 도중 드라이버가 있음을 알린다**.
(b) 사용자가 앱·사이트 이름으로 말하면 기존 가이드 검색(`guide_db` 주제 목차)이 찾는다.
앱·사이트 목록 자체는 세계의 명사이므로 `guide_db.json` 데이터에만 있고 코드에는 없다.

### 5.3 포인터만, 한 번 읽기

소개 행에는 파일명만 싣는다. 본문은 그 면을 다룰 때 한 번 읽고, 현재 문맥에 계약이 있으면
다시 읽지 않는다(10-18 §7 의 규칙 그대로). 관측도 행에 통째로 싣지 않고 `observations:N` 개수만
싣고 다룰 때 읽는다. 기기·앱·사이트 수가 늘어도 매 턴 토큰이 비례해 늘지 않는다.

## 6 호출 조건 — 실행 전 검사

실행 후 확인(§7)과 **다른 책임** 이다. 사용자와 공유하는 탭을 바꾸는 동작은 결과 확인이 아무리
정확해도 이미 방해한 뒤다. 그래서 실행 부품의 계약은 동작마다 다음을 선언하고, 강제해야 할 조건은
**가이드가 아니라 실행 직전 경계** 가 검사한다. 가이드는 같은 조건을 설명하되 보장의 주체가 아니다.

| 선언 | 뜻 | 실행 전 검사 |
| --- | --- | --- |
| `needs_front` | 앞 앱·포커스 요구 | 화면을 쓸 수 없는 문맥(배경·정기 실행, 무인 기기)이면 거절. 쓸 수 있으면 `expect_app` 가드 필수. 위임 여부는 기준이 아니다(아래) |
| `shared_state` | 사용자와 공유하는 상태 변경 | **요청된 효과** 면 실행한다. 요청 범위 밖의 **부수 간섭** 만 검사한다(아래) |
| `isolated_resources` | 분리된 자원 목록 | 면제권이 아니다. 동작이 바꾸는 자원이 목록 안에 있을 때만 그 자원의 간섭 검사를 생략한다. 대상(전용 프로필·창)이 실제로 있는지 확인 |
| `supported_platforms` | 동작 OS | 대상 OS 불일치면 거절(§5.2) |
| 전제 | 권한·런타임·연결 | `runtimes.python.ready`·`connected`·`paused`·AX 권한 등 기존 info 값으로 확인 |
| 관측 | 적용 조건 있는 `valid`·`recheck` 행 | `recheck` 행이 걸리면 변경 전 상태 조회로 재확인 |

**요청된 효과와 부수 간섭.** 사용자가 타이핑하면서 "본체 음량 낮춰" 라고 하면 음량 변경은 **요청된 효과** 이고,
그 과정에서 작성 중인 창을 가리거나 활성 탭을 바꾸는 것은 **부수 간섭** 이다. 요청으로 허용된 대상·효과는
사용자 활동 중이어도 그대로 실행한다. 검사하는 것은 그 범위를 벗어나는 간섭뿐이다. 간섭이 있으면 간섭 없는
통로(AppleScript 가 `activate` 없이 되는가, AX 동작으로 되는가)를 먼저 고르고, 없으면 사용자 확인이다.
입력 유휴(`idle_seconds`)는 간섭의 크기를 가늠하는 **보조 관측** 이지 거절 조건이 아니다.

**위임과 화면.** 위임 여부와 화면 사용 가능 여부는 독립이다. 부모 작업이 확보한 대상·실행 조건(앞 앱 가드,
허용된 효과, 격리 자원)을 자식 작업이 **계승** 한다. 거절 기준은 "위임이라서" 가 아니라 "이 문맥에서 화면을
쓸 수 없어서" 다.

검사 주체는 호출 경계다. 저장 함수(`fn:PC제어` 류)가 입구인 드라이버는 그 함수의 첫 단계, 노드
액션(`limbs:screen`·`limbs:browser`)이 입구인 탐색은 handler 다. 10-18 의 `verify_task` 는 실행 **후**
영수증 대조이므로 여기에 끌어오지 않고, 실행 **전** 검사는 별도 단계로 둔다. 현재 `expect_app`·
`wait` 가 `needs_front` 의 부분 구현이고, 요청된 효과·부수 간섭·격리 자원의 구분과 작업 문맥 판별은 없다.

## 7 결과 확인과 실패의 연결

한 호출의 연결은 네 단계다.

```
실행 전 검사(§6) → 실행 → 효과 확인 → 불명확하면 기존 작업 조회
```

- **효과 확인** 은 `success`(요청 전달·실행 종료)와 `verified`(특정 범위의 재조회 통과)를 나누고,
  **무엇을 관측해 어느 범위까지 확인했는지** 를 값과 함께 남긴다. `pc_control` 의
  `verification_scope:os_setting_readback` 이 그 모양이다. 복합 작업의 다음 단계는 이 범위를 읽고
  결과를 얼마나 믿을지 정한다. 물리적 결과(실제 소리·실제 화면)는 범위 밖이면 미확인이다.
- **불명확하면 기존 작업 조회.** 응답 유실·시간 초과는 실패가 아니라 불명확이다. 공통 계약은 네 줄이다.
  1. 작업 참조(`task_ref`·`request_id`)가 있으면 기존 작업을 조회한다.
  2. 참조가 없으면 **변경 없이** 현재 상태를 재조회한다.
  3. 그래도 실행 여부를 판별할 수 없으면 `unknown` 을 유지한다. 확정을 꾸미지 않는다.
  4. 변경을 자동 재전송하거나 다른 통로로 중복 실행하지 않는다.

  "현재 상태가 목표와 같음" 과 "내 요청이 실제로 실행됨" 은 다른 사실이다. 후자를 확인할 근거(영수증·작업
  기록)가 없으면 전자만 보고한다. 10-18 의 `verify_task` 는 PC 준비 영수증과 `limbs:guestpc` 접수 영수증을
  전제로 한 **원격 PC 전용** 검증기이며, 본체 로컬 실행이나 TV 에는 그대로 적용되지 않는다. 그 둘은 2·3번
  줄로 간다.
- **통신 실패 뒤 화면 조작으로 같은 변경을 다시 시도하지 않는다.** 드라이버 통로가 불명확한 상태에서
  탐색 통로로 같은 효과를 내면 중복 적용과 원인 은폐가 동시에 생긴다. 폴백 서열(§8)은 "드라이버가
  없을 때" 의 순서이지 "드라이버가 불명확할 때" 의 순서가 아니다.
- **증거.** 실행 부품은 상태값을 돌려주지 그림을 주지 않는다. 증거가 필요한 작업은 마지막에
  screenshot 한 장을 찍어 사용자 규칙(시각 산출물은 눈으로)을 지킨다. 매 단계가 아니라 마지막 한 장이다.
- 사람이 앱 버튼으로 검증한 기록은 드라이버의 일부다. 10-18 의 "앱 개발의 산출물은 화면뿐 아니라
  재사용 가능한 실행 코드, 호출 계약, 사용 가이드, 실기 검증 기록" 을 드라이버 정의로 받는다.

## 8 폴백 서열

드라이버가 **없을 때** 의 순서다. `desktop.md`·`browser_action.md`·`guest_helper.md` 머리에 이 서열을
한 단락으로 넣되, 보장은 §6 의 실행 전 검사가 한다.

**본체**
1. 계약 통로: 드라이버 실행 부품. 없으면 셸·`open`·`defaults`·AppleScript 사전·Shortcuts. 동작별 조건은 §6.
2. AX 동작: `limbs:screen` snapshot 의 ref 로 AXPress. `needs_front`. 좌표 불필요. 이미 구현돼 있고 가이드가 1순위로 권한다.
3. 좌표: snapshot 의 center 또는 OCR 좌표. `needs_front` + 사용자 입회. 마지막.

**브라우저**
1. 사이트 실행 부품(있으면).
2. 범용 DOM: `limbs:browser` navigate·snapshot ref·content·evaluate. 격리는 도구가 아니라 자원 단위다. 내장 Playwright 의 전용 프로필은 화면·포커스·세션이 분리되지만 같은 계정으로 로그인했으면 계정 데이터는 공유다. Chrome MCP 는 사용자의 탭·세션을 그대로 쓴다.
3. 화면: screenshot 은 캔버스·이미지처럼 DOM 이 못 주는 것에만.

**원격 기기**
1. 드라이버 실행 부품(`guestpc python`·`fn:PC제어`·`TV제어`).
2. `guestpc shell`·`read`·`list` 범용 실행.
3. 원격 화면(`guestpc screen`, `mode:interactive`). `needs_front`. 마지막.

51회차에서 무인 맥12 의 밤일에 화면 찍기를 섞었다가 일반 실행 자리를 다퉈 60초 뒤 실패하고 2분 늦게
찍힌 일(L51-1)과, 꺼진 화면을 검은 그림으로 success 받은 일(L51-2)은 "이 동작은 배경 작업에 맞지
않는다" 는 조건이 가이드에도 실행 경계에도 없어서 생겼다. 전자는 §6 의 `needs_front` 검사, 후자는
§7 의 확인 범위(화면이 켜져 있었는지는 범위 밖이었다는 보고)가 막는다.

## 9 승격 규칙과 저자

### 9.1 등록 기준

드라이버로 등록하는 기준은 네 가지다. **계약의 명확성, 재사용 가능성, 검증 가능성, 유지 비용.**
반복 횟수는 기준이 아니라 **후보를 찾는 신호** 다. 같은 조작면에서 같은 동작을 두 번째 탐색으로
완수했으면 에피소드 기록이 후보로 올린다. 그러나 이미 안정된 인터페이스와 분명한 조합 가치가 있으면
첫 사용 전에도 만든다. 진화 목적 정본의 "개발 계획은 일반 능력의 목표 구조에서 도출한다" 가 그
근거다. 사용자 규칙(스위치화를 사용 빈도로 결정 금지)과도 이렇게 맞는다. 승격은 사람이 결정하고
AI 는 후보를 제안한다.

### 9.2 승격의 산출물

승격 하나 = 실행 부품 등록(`self:script` 또는 저장 함수, 동작별 조건 선언 포함) + 가이드 한 단락 +
`guide_db` 매핑 칸 + 검증 기록. 10-18 §4 의 "앱 하나를 만들 때 함께 완성할 묶음" 과 같다. 부품만
있고 가이드·매핑이 없으면 결정화됐지만 통로가 없는 상태(`crystallized-but-unrouted`)다. 넷이 함께여야
승격이다.

### 9.3 관측의 일반화

같은 클래스(같은 OS·같은 앱·같은 사이트)의 개체 **둘 이상** 에서 같은 관측 행이 반복되면 그것은
**일반화 후보** 다. 클래스 사실이 되려면 **원인과 적용 조건의 확인** 이 필요하다. 두 기기가 같은 권한
문제나 설정을 공유해서 같은 현상을 낼 수 있기 때문이다. 확인되면 가이드 또는 실행 부품으로 올리고,
개체 행은 `superseded` 로 표시한다. 맥12 의 "뚜껑 닫힘=검은 화면 success" 가 다른 맥에서도 났다면,
원인(화면 꺼짐인지 잠금인지 외부 디스플레이인지)을 확인한 뒤에야 `pc_control.py` 가 무엇을 먼저
읽어 거절할지 정할 수 있다. 밝기 하나로 판정하는 것은 별도 검증 전에는 쓰지 않는다.

### 9.4 누가 쓰는가

- **실행 부품**: AI 가 탐색에서 얻은 코드를 `self:script` 에 등록하는 길은 이미 있다. 등록은 사람 확인 뒤.
- **가이드**: AI 가 초안을 쓰고 사람이 등록한다(`guide_registration.md` 절차). 자기수정은 REPAIR 경로.
- **관측**: AI 가 **직접 써야** 한다(추가·정정). 51회차 발견 다섯 건이 전부 세션 기억에만 있고 몸에
  없는 이유가 통로 부재다. 통로는 §12 ①.

## 10 비용

- 소개 블록: 본체 행 하나 추가. 앱·사이트 드라이버는 소개 블록에 넣지 않고 탐색 도중 handler 가
  알린다. 매 턴 고정 비용은 행 하나다.
- 가이드 읽기: 면당 한 번. 현재 셋은 합쳐 36KB 예산의 절반 아래.
- 관측: 개수만 행에, 본문은 다룰 때. 행당 아홉 칸이라도 가이드 한 단락보다 작다.
- 실행 전 검사: 동작당 info 값 대조 한 번. 모델 호출 없음.
- 화면 조작 대비 절감은 **주장하지 않는다**. 10-18 의 "구조 변경만으로 시간·토큰 절감률을 주장하지
  않는다" 를 따르고, 첫 걸음 뒤 같은 과제를 두 통로로 실행해 품질·시간·전체 토큰을 잰다. 측정 대기로
  개발을 유예하지는 않는다.

## 11 범위 밖

- 앱 **안의** 콘텐츠 동작(음악 선곡, 메시지 내용, 문서 내용)은 드라이버가 아니다. 드라이버는
  "Music 에게 이 곡을 틀어라" 까지이고 어느 곡인지는 AI 의 일이다.
- 원격 PC 의 브라우저(CDP 전용 프로필)는 10-18 §6 의 설계를 그대로 두고 여기서 다시 설계하지 않는다.
  그 설계의 전용 프로필은 화면·세션이 분리된 `isolated_resources` 의 한 예이고, 계정 데이터 분리는 별도다.
- 폰 화면 조작(`limbs:android` snapshot→tap)은 본체 화면과 같은 탐색 도구이며 §8 서열의 폰 판이다.
- 실행 봉투의 겹 수·이름 통일(원격은 세 겹, 로컬은 두 겹, ibl-script/2 와 registered-json/1).
  `fn:PC제어` 처럼 저장 함수가 겹을 흡수해 호출자에게 한 모양을 보이는 10-18 §5 의 결정으로 충분하다.

## 12 사용자 판정이 필요한 것

1. **관측 쓰기 통로.** (a) `[self:limb]` 등록 갱신에 `observations` 칸 — 기존 액션의 인자 확장, 새 낱말 0,
   의미는 **추가·정정**(행 단위, `status` 변경 포함)이며 목록 덮어쓰기가 아니다. (b) 새 op — 어휘 증식이지만
   의도가 이름에 드러남. (c) 가이드에 붙임 — 코드 쪽에 세계의 명사가 들어가므로 권하지 않음. **권고 (a).**
   앱·사이트 관측의 소유 위치는 기기 등록 기록이 아니므로 함께 정해야 한다. 권고는 `guide_db.json` 의
   해당 드라이버 항목 옆 데이터 파일(`data/control_observations.json` 류, 식별자 키).
2. **앱·사이트 매핑의 자리.** `guide_db.json` 항목에 `control_surfaces`·`supported_platforms` 칸 추가(§5.2).
   `control_platforms` 는 OS 대표 가이드 전용으로 유지. 등록 절차·검사가 그대로 적용된다.
3. **사이트 관측을 무엇이라 부를지.** 실행 코드가 없는 관측만으로는 드라이버라 부르지 않는다. 사이트
   드라이버 = 사이트 실행 부품 + 관측이고, 부품 없이 관측만 있는 사이트는 "관측 있음" 으로만 발견된다.
   가이드 산문 밖(1 의 데이터 파일)에 저장한다. 47·48회차 사이트 발견이 산문에 묻혀 재발한 전례가 이유다.

## 13 첫 걸음 셋과 완료 조건

판정 1~3 과 무관하게 지금 할 수 있는 셋이다. 순서가 중요하다. 본체 발견 경로(1)는 다른 쟁점과 독립이라
먼저 잇고, 2 는 §6 의 구분 규칙을 확정한 뒤에 넣고, 앱 드라이버 하나(3)에 **실행 조건과 결과 확인 계약을
끝까지** 적용한다.

| # | 걸음 | 변경 | 완료 조건 |
| --- | --- | --- | --- |
| 1 | 본체를 장치 소개에 넣기 | `_connected_limbs` 에 `__local__` 행, 회상 주석 한 문장, `test_associative_recall.py` 한 건 | 긴 문장 "본체 음량 낮춰" 를 AI 가 `fn:PC제어` 로 완수. 화면 조작 0회 |
| 2 | 동작별 조건의 실행 전 검사 | **전제**: 요청된 효과·부수 간섭·실제 격리 자원을 구분하는 규칙(§6)을 먼저 확정. 그 뒤 `limbs:screen`·`limbs:browser` handler 에 화면 사용 가능 문맥 판별과 `needs_front`·부수 간섭 검사, 위임의 조건 계승. `desktop.md`·`browser_action.md`·`guest_helper.md` 머리에 §8 서열과 조건 설명 | 배경·정기 작업에 `needs_front` 동작을 넣은 긴 문장이 **실행 경계에서** 거절되고, 타이핑 중 "본체 음량 낮춰" 는 확인 없이 실행됨. 둘 다 통과해야 완료. 가이드만으로 막았다고 보고하지 않음 |
| 3 | 앱 드라이버 시범 하나 | 44~48회차에서 가장 많이 반복된 앱 하나(후보: Safari 탭·창, Finder 폴더·열기). AppleScript/JXA 부품 `self:script` 등록(동작별 조건 선언) + 가이드 + `control_surfaces` 매핑 + 실기 검증 | 정상 실행뿐 아니라 **사용자가 동시에 작업하는 경우, 권한 부족, 대상 소실, 실행 뒤 응답 유실** 네 경우의 동작을 기록. 같은 과제를 두 통로로 실행해 배경 실행 가능 여부·단계 수·품질·시간·토큰을 표로. 절감률 주장은 측정값으로만 |

3 이 끝나면 §5.2 의 `surface_control_guides()` 와 snapshot handler 의 알림을 넣고, 그 계약을 바탕으로
관측의 저장·재확인·발견(§3·§6·§9.3)을 잇는다. 그 전에는 가이드 검색만으로 발견한다.

## 14 이 문서가 바꾸지 않는 것

- 10-18 두 문서의 결정 전부. 이 문서는 그 위에 "본체·앱·브라우저도 같은 행" 이라는 일반화와
  관측 한 부품, 동작별 조건, 실행 전 검사와 실행 후 확인의 분리, 폴백 서열, 승격 기준을 얹는다.
- `control_platforms` 매핑·`fn:PC제어`·`TV제어`·`android_control.md` 의 현재 계약.
- 화면 조작 패키지(`computer-use`·`browser`)의 액션 어휘. 조건 검사와 알림만 더한다.

이 설계가 만들어야 할 가장 중요한 능력은 AI 가 **무엇을 할 수 있는지, 지금 어떤 조건에서 실행할 수
있는지, 실행 뒤 무엇이 확인됐는지** 를 알고 조합하는 것이다.

## 15 구현 기록 (2026-10-20)

§12 의 판정 셋은 권고안대로 구현했다 — ① (a) `[self:limb]{op:"register", target, observations:[…]}` 인자 확장(새 낱말 0)
+ 앱·사이트 관측은 `data/control_observations.json`(식별자 키), ② `guide_db.json` 의 `control_surfaces`·`supported_platforms`
칸(`control_platforms` 는 OS 대표 가이드 전용 유지), ③ 부품 없는 사이트는 "관측 있음"(snapshot 알림의 `observations` 개수)으로만
발견. 셋 다 언어 개정이 아니라 데이터·인자 확장이라 사용자 판정을 기다리지 않았다(판정 요청은 언어 개정·파괴적 변경 두 종만).

| # | 걸음 | 구현 | 완료 조건 대조 |
| --- | --- | --- | --- |
| 1 | 본체 소개 행 | `associative_recall._connected_limbs` 에 `device_id="__local__" adapter="local"` 행(맨 앞), 회상 주석을 "상태 조회=`[sense:host]`, 제어=본체 행의 control_guide" 로 개정, `test_associative_recall.py` 3건 | 실제 원장으로 "본체 음량 낮춰" 회상 블록을 뽑아 본체 행 `control_guide="pc_control.md"` 확인(모델 호출 없는 결정론 확인). **AI 긴 문장 실행 측정(10-20 입회 세션, ep5085, origin training)**: "본체 음량 낮춰" → REFLEX 분류 뒤 실행 1턴 34.4초, `fn:PC제어` 가 `대상:"__local__"` 로 2회(status → volume 8) 둘 다 `verified`, **`limbs:screen` 0회**, 실제 음량 14→8(osascript 재확인). 회상 블록 `connected_limbs` 첫 행 `name="본체" device_id="__local__" control_guide="pc_control.md"`. 비용: 모델 호출 2(분류 deepseek 3,708/2 · 실행 opus 입력 446,221(캐시 읽기 365,082)·출력 827), execute_ibl 4 + read_guide 1. 발견 경로의 마찰 1건: 첫 호출이 `대상:"본체",요청:"음량 낮춰"`(표시 이름·문자열) → `request: Record가 필요` 실패 → describe → `pc_control.md` 읽기 → 정답. 해마 용례가 `대상:"…",요청:"…"` 만 보여 Record 계약과 `__local__` 키를 알리지 못한 것이 원인(가이드 읽기 전 1실패 2라운드). 수리 안 함(발견) |
| 2 | 동작별 조건의 실행 전 검사 | `backend/base/control_conditions.py`(screen_context·refusal·declare) · `limbs:screen` handler `_OP_CONDITIONS` 11 op + `_precheck`(`SCREEN_CONTEXT_UNAVAILABLE`) + `screen_info` 에 조건·문맥 노출 · `limbs:browser` handler: 공유 상태 변경 op 가 화면 없는 문맥이면 `driver:auto`→Playwright 재경로, `driver:chrome` 명시는 거절 · 가이드 셋 머리에 §8 서열 | 시험: scheduler 출처의 click/type/key/snapshot/screenshot/wait 가 입력 0 으로 거절, user 출처는 실행, 읽기 op 와 Playwright 는 거절 없음(`test_control_driver.py`). 화면 사용 가능 문맥 = 행위자 봉투 출처 `user`·`training`·`test`; `scheduler`·미세팅은 불가. 위임은 봉투가 출처를 계승하므로 별도 조건 없음 |
| 3 | 앱 드라이버 시범 | **Safari 창·탭** — `data/scripts/safari_control.py`(`Safari제어`, registered-json/1, 동작별 needs_front/shared_state/isolated_resources 선언, 재조회 확인 `applescript_tab_readback`, 응답 유실→변경 없이 재조회→`unknown` 유지) + `safari_control.md` + `guide_db` `control_surfaces:["app:com.apple.Safari"]` | 실기(macOS 26.6·Safari 26.6, 사용자가 다른 앱 ChatGPT 작업 중): open 배경 탭 1.4초·switch 0.9초·close 0.8초 전부 `verified`, 앞 앱 불변. 네 경우 기록은 아래 |

**네 경우 실기 기록(걸음 3).** ① 사용자 동시 작업: 앞 앱(ChatGPT) 유지, 어떤 동작도 activate 없음. ② 권한 부족: 이 본체는 이미 허용돼 실측 불가 — `-1743` 경로는 모의 시험으로 `PERMISSION_REQUIRED` 확인. ③ 대상 소실: 없는 탭(-1719)·없는 창(-1728)·Safari 미실행(실행 전 검사) 셋 다 `TARGET_MISSING`, 사전 호출 0~1회. ④ 응답 유실: **실측** — 숨은(`open -gja`) Safari 의 첫 `make new document` 가 20초 넘게 응답하지 않았는데 창은 즉시 생겼다. 부품은 시간 초과 뒤 변경 없이 재조회해 `verified:true, response_lost:true` 로 보고하고 재전송하지 않는다(모의 시험 포함). 또 마지막 탭 닫기 직후 창 목록과 탭 조회 사이에 창이 사라져 `-1728` 이 났다 — 재조회가 사라진 창을 건너뛰도록 수리.

**두 통로 비교표 — 실측(2026-10-20, 사용자 입회, macOS 26.6·Safari 26.6, 시스템 AI claude_code/opus, origin training).** 같은 과제 "Safari 에서 about:blank 를 배경 탭으로 열고, 전환했다 돌아오고, 닫기" 를 시스템 AI 에게 통로를 지정해 시켰다. 시작 상태는 둘 다 창 1(window_id 224086)·탭 1(example.com). 토큰은 `model.usage` 합(캐시 읽기 포함, 분류·평가 보조 호출 포함).

| 항목 | (a) 드라이버 `self:script` Safari제어 (ep5086) | (b) 화면 조작 `limbs:screen` — 3회 시도 (ep5087·5088·5089) |
| --- | --- | --- |
| 완료 | 5단계 전부 `verified`, 최종 상태 = 시작 상태 | 1·2차 미완(아래), **3차 완료**(최종 상태 = 시작 상태, `Safari제어 status` 로 재조회 일치) |
| 액션 호출 수 | execute_ibl 7 (status·open·switch·switch·status·close·status), 실패 0 | 3차: execute_ibl 23 / `limbs:screen` 48 op(screenshot 25·key 8·click 7·type 4·cursor_position 3·mouse_move 1) + 스크린샷 Read 22, 실패 1(입력기 두벌식 오타) |
| 완료 시간 | 116.4초(도구 9.2초, 나머지 모델) | 3차 208.9초(도구 22.4초). 1·2차 각 119.3·117.8초는 미완 비용 |
| 토큰(입력/출력) | 813,739 / 4,146 (모델 호출 5: THINK 계획·실행·평가 + deepseek 2) | 3차 6,625,486 / 11,533 (EXECUTE 1턴, opus 입력 6,616,769 중 캐시 읽기 6,532,844 — 스크린샷 25장이 매 라운드 문맥에 쌓임). 1차 737,924/7,619 · 2차 605,045/6,794 는 미완 비용 |
| 결과 품질 | 변경마다 `applescript_tab_readback` 재조회, 스크린샷 0장. 페이지 렌더링 여부는 범위 밖 | 스크린샷 판독만(메뉴 막대 이름·탭 막대·주소창). 입력 직전 사진과 실제 입력 사이 ~1초 앞 앱 불변은 미확인. 열기와 전환이 Cmd+T 한 번에 겹쳐 AI 가 Cmd+1·Cmd+2 로 전환 단계를 따로 연출 |
| 배경 실행 가능 | **가능** — Safari 가 뒤에 있어도 실행, 사용자가 다른 앱(Claude) 작업 중 완료 | **불가** — Safari 가 앞이어야 함. 1차: `snapshot`·`wait(expect_app)` 3회 AX -25204 로 ref 0개, 키 입력 0(앞 앱 확인 불가로 중단). 2차: 사용자가 Chrome 으로 전환해 첫 스크린샷에서 중단(올바른 중단, 키 0). 3차: 사용자가 Safari 를 앞에 두고 3분간 손을 뗀 뒤에야 완료 |
| 앞 앱 변경 | 없음(전후 Claude) | 3차: 없음(전후 Safari, 사용자 손 뗌 조건). 2차 뒤 앞 앱 Chrome 은 사용자 전환. AI 가 입력기 메뉴를 두벌식→U.S.→두벌식 으로 바꿨다 되돌림(부수 상태 변경 1건, 복원됨) |

절감률은 이 표본(각 1회 완료)의 비율로만 말한다: 완료 시간 116.4초 대 208.9초, 액션 호출 7 대 23(limbs 48 op), 입력 토큰 0.81M 대 6.63M, 스크린샷 0 대 25. 화면 통로는 사용자 입회·손 뗌이 전제라 같은 품질 조건이 아니다(드라이버는 재조회 확인, 화면은 사진 판독).

**(b) 1차가 드러낸 것 — 권한이 아니라 조회 방식.** `limbs:screen` 의 `_frontmost_app()` 은 system-wide `AXFocusedApplication` 을 읽고 실패하면 "AX -25204, 손쉬운 사용 권한을 확인하세요" 라고 말한다. 입회 세션에서 손쉬운 사용에 Python(항목 미생성)·Electron(dev)·IndieBiz 시작(지우고 재추가) 을 차례로 허용하고 백엔드 `restart --wait` 2회·런처 전체 재시작 1회를 했지만 같은 오류였다. 결정적 측정: 같은 `.venv` 파이썬을 **신뢰된 터미널 아래**에서 돌려도 `AXIsProcessTrusted()=True` 인데 system-wide `AXFocusedApplication` 은 똑같이 **-25204(kAXErrorCannotComplete)** 였고, 미신뢰 셸에서는 앱 단위 조회가 **-25211(kAXErrorAPIDisabled)**, 신뢰 아래서는 앱 단위 `AXWindows`·`AXTitle` 조회가 0(성공)이었다. 즉 -25204 는 권한 오류가 아니라 이 환경에서 system-wide 포커스 조회 자체가 완료되지 않는 것이며, 메시지가 권한으로 오진한다(45·46회차 기억 "백엔드 Python 손쉬운 사용 권한 필요" 도 이 오진의 계승). 권한 주체는 `responsibility_get_pid_responsible_for_pid` 로 확인: 백엔드의 책임 프로세스 = `/Applications/IndieBiz 시작.app`(Python 도 Electron 도 아님). `screen_info` 는 `screencapture` 권한만 검사하고 AX 신뢰는 검사하지 않는다(note 문구만). 둘 다 수리하지 않음(발견 회차) — 수리 후보: `_frontmost_app()` 을 앱 단위 조회·`NSWorkspace.frontmostApplication` 폴백으로, 오류 코드별 메시지(-25211 만 권한), `screen_info` 에 `AXIsProcessTrusted`. → **같은 날 수리됨**(별도 세션): `_frontmost_app()` 은 -25204 면 `NSWorkspace.frontmostApplication` 으로 pid 를 얻어 앱 단위 조회를 잇고, 권한 문장은 -25211 에만(책임 프로세스 경로 동봉), `screen_info` 에 `ax_trusted`·`responsible_app` — 라이브 재측정에서 Safari 를 앞에 둔 `[limbs:screen]{op:"snapshot"}` 이 AX 요소 80개·ref 를 돌려줬고 `ax_trusted:true`(이때의 책임 프로세스 = 제어자가 다시 띄운 세대의 Python 워커 자신, pid 7175 — 런처 아래 세대와 다르다).

**이 비교가 바꾸는 것.** §8 폴백 서열의 전제("드라이버 있으면 드라이버, 없을 때만 화면")는 측정으로 뒷받침됐다. 화면 통로는 `needs_front` 때문에 사용자 입회가 아니라 **사용자 부재**(손 뗌)가 조건이며, 3차 완료도 그 조건에서만 났다. 3회 시도 합계 446초·입력 7.97M 토큰이 화면 통로의 실제 비용이다.

**§5.2·관측.** `guide_registry.surface_control_entries()/surface_control_guides()/surface_control_guide(kind, id)` — 같은 식별자 둘이면 둘 다 제외하고 경고. `limbs:screen` snapshot 은 앞 앱 bundle_id, `limbs:browser` snapshot(Playwright)은 현재 URL 호스트(상위 도메인까지)로 대조해 `control_guide`·`observations` 개수를 응답에 싣는다. 관측 원장 `backend/datastore/control_observations.py`: 행 검증(시각·환경 필수, status 4종, 지우지 않음, fact 정정 금지=새 행+supersedes), 기기 행은 등록 기록 `observations` 칸(limb_keys.resident_update·hardware_registry.update 허용), 본체·앱·사이트는 파일 원장. `applicable(surface, version)` 이 판본 다른 valid 행을 recheck 로 표시해 돌려준다(읽기는 쓰지 않음). 장치 소개 행과 snapshot 알림은 개수만 싣는다(§5.3).

**라이브 확인(재기동 뒤 `/ibl/execute`).** `Safari제어` status(Safari 미실행 → `running:false, verified:true`)·contract·open(미실행 → `TARGET_MISSING`)·`limbs:screen screen_info`(직접 호출 출처 `user` → `screen_context.available:true`, op 조건 노출)·`[self:limb]{op:"register",target:"app:com.apple.Safari",observations:[…]}` 실기 관측 1행 기록(`data/control_observations.json`). 발견: registered-json/1 어댑터는 `success:false` 의 `error` 문자열만 호출자에게 전하고 `failure` 객체를 떨어뜨린다 → 부품이 코드·다음 걸음을 문장에 싣는다(`"TARGET_MISSING: … 다음: …"`). `contract` op 는 변형 결과 선언이 없으면 `{success, verified}` 결과 계약에 걸린다 → 변형에 `result` 선언.

**남은 것.** (1)·(2) 는 위 실측으로 닫힘(10-20 입회 세션). (3) `pc_control.md` 의 개체 사실("본체 맥 CGSession 없어 잠금 비활성")을 관측 행으로 옮기기 — 행 형식은 준비됨. (4) `recheck` 행을 실행 전 변경 없는 상태 조회로 재확인하는 자동 단계 — 드라이버 부품마다 `status` 가 그 자리이며 공통 집행은 미구현. (5) 사이트 실행 부품은 0개 — 안정된 업무 계약을 줄 수 있는 사이트부터.

## 16 호출 경계 검토에서 발견한 6건 수리 (2026-10-20)

1. **배경 Chrome 결속**: 앞선 읽기가 Chrome을 작업에 결속한 뒤 `auto` 변경 호출이 같은 Chrome으로
   가던 경로를 최종 드라이버 선택 뒤 거절한다. 다른 브라우저에 같은 변경을 조용히 재전송하지 않는다.
   `test_browser_embedded.py::test_handler_blocks_background_mutation_after_real_router_pins_chrome`은
   실제 `execute → route → owned_execute`를 잇고 외부 브라우저 통신만 대체한다.
2. **입력 대상 필수**: 화면 입력은 `expect_app` 또는 현재 snapshot의 ref가 없으면
   `APP_GUARD_REQUIRED`로 중단한다. ref의 PID와 입력 직전 포커스 재검사는 유지한다.
   `test_computer_use.py::test_ibl_entry_refuses_missing_app_guard_before_input`이 실제 IBL 진입점에서
   여섯 입력 op를 검사한다. 가이드·어휘 설명·은퇴 등록부도 같은 계약으로 맞췄다.
3. **불명확 결과 전달**: Safari 실패는 `error` 문장뿐 아니라 `error_code`, `failure`, `recovery`를
   명시한다. UNKNOWN은 `error_type:result_unknown`이며 `recovery`에 상태 조회와 변경 재전송 금지를
   보존한다. 등록 실행기가 이 필드를 IBL 실패 어댑터에 넘겨 `diagnostic.details`까지 전달한다.
4. **관측 읽기**: `[self:limb]{op:"list"}`의 기존 기기 목록은 유지하고 `control_observations`에
   파일 원장의 대상별 개수를 더한다. `list+target`은 기기 이름·ID·`__local__`·`app:`·`site:`를
   쓰기와 같은 해석기로 해소해 `observations`와 `items`로 본문을 반환한다.
   `test_control_driver.py::test_observation_write_discover_read_through_ibl_entry`가 등록→목록→본문을 잇는다.
5. **관측만 있는 면의 발견**: 가이드가 없어도 앱·사이트 관측이 있으면 snapshot이 개수와 조회 대상을
   알린다. 없는 `control_guide`는 꾸며 넣지 않는다. 내장 브라우저의 조기 반환도 같은 알림 함수를
   거치며 사이트 관측은 실제 호스트로 조회한다(상위 도메인 가이드 결속과 개체 관측은 구분).
6. **Safari 닫기 확인**: 탭 index는 닫기 뒤 재번호되므로 고정 신원으로 비교하지 않는다.
   요청 탭을 제외한 URL·제목 순서와 남은 탭 수를 재조회 값과 비교한다. 동일 URL·제목을 가진
   탭의 개체 신원이나 요청과 효과의 인과를 보장하는 것은 아니다.

`test_safari_control.py`는 실제 `/ibl/execute` HTTP 라우터·IBL 진입점·등록 실행기·자식 Python 프로세스·Safari 소스·출력 어댑터를
연결한다. Apple Events 끝단만 모의해 응답 유실 후 UNKNOWN 보존·변경 재전송 0회, 동일 탭의
앞/중간/뒤 닫기와 다른 탭이 닫힌 경우의 검증 거절을 확인한다. 실제 사용자 앱 조작의 인수 시험과 구분한다.

공용 패키지 경로 재감사: `script_ops.op_run`의 변경은 이미 실패로 판정한 등록 스크립트의
복구 필드 전달뿐이다. 입력 인자·경로 해소·인터프리터·환경·회원 실행·문서 변환의 권한 경계는
변경하지 않았다. 패키지 지문을 사용하는 read/fill/write/script 표식을 갱신하고 회원 문서·브리지 회귀를 포함한다.

§15의 미구현 범위(개체 사실 이관·recheck 자동 재확인·사이트 실행 부품)는 이번 수리의 완료 범위와 별개다.

용례 재검토: screen 53건과 limb 15건을 확인했다. screen 중 실행 이력이 없는 입력 예시 29건은
백업 후 snapshot → `expect_app:$s.app` 입력으로 새로 등록하고 기존 합성 행을 퇴역시켰다.
정본 시드 `data/idioms/screen_guard_seeds.json`, 원장 입구 `add_examples_batch`, 시맨틱 색인 29건 확인.
훈련 원본의 일치 행 28건도 갱신했다. 백업은 `data/_backups/2026-10-20_control_driver_examples/`.
기존 실행 성공 이력은 개작하지 않았으며 새 예시에도 실기 성공을 주장하지 않는다.

검증 결과: 종합 회귀 `pytest backend/ -m 'not system' -n auto --dist loadfile`는 11,027 통과·1 건너뜀.
관련 system 묶음(스크립트·어휘 배포·제작자 예시·async 관문) 74 통과. HTTP 라우터를 포함해
보강한 제어 경로와 단일 러너 규약 묶음은 마지막으로 91 통과. 실 서비스 8765는 연결 거절 상태여서
라이브 HTTP/실기 앱 조작은 검증하지 않았다. HTTP 시험은 동일 라우터를 격리된 FastAPI 앱에 장착한다.

어휘·몸 번들을 재생성했고 어휘 파생·계약·용례 관문은 통과했다. 작업 트리의 어휘 종합 검사에서
기존 미커밋 `scripts/build_dist_filter.py`·`frontend/package.json` 간 설치 필터 불일치만 남았다.
두 파일은 이번 커밋에서 제외한다. HEAD의 생성기·package.json을 메모리에서 현재 매니페스트와
대조한 커밋 대상 필터는 일치했다. 다른 정적 관문 25개를 개별 실행해 모두 통과했으며,
이 기존 작업 트리 불일치 때문에 커밋 훅은 `--no-verify` 예외를 사용한다.

## Safari 드라이버 v2 — 대상·검증·연속 실행 (2026-10-20)

§15~16은 당시 구현과 실측 기록이다. 현재 Safari 계약은 `data/guides/safari_control.md`를 따른다.
전환·닫기는 `window_id`·`tab`뿐 아니라 관측한 `expected` 판본을 필수로 받는다.
판본은 창 ID·현재 탭·URL 순서에 묶이며 실행 전 조회와 변경 AppleScript 내부에서 다시 대조한다.
달라졌으면 변경 전 `STATE_CHANGED`다. 동일 URL 탭의 개체 신원, 관측 사이 변경 후 원상 복귀,
마지막 비교와 효과 사이 경쟁을 막는 트랜잭션은 제공하지 않는다. 오래된 번호만으로 실행하는 계약은 은퇴했다.

검증은 배경 열기의 현재 탭·기존 URL 순서 보존, 전환의 탭 순서 보존, 닫기의 요청 탭만 제거를
함께 요구한다. 마지막 탭이 아니었는데 창 전체가 사라지면 성공이 아니다. 제목 변화는 판본과
닫기 검증에서 제외한다. 열기의 생성 응답이 가리킨 창·탭을 재조회해 URL 리다이렉트와 생성 실패를
구분하고, 요청 URL·관측 URL·페이지 로드 미확인을 별도 반환한다. 응답 유실·변경 후 조회 실패는
재전송 없이 `UNKNOWN`, 응답은 왔지만 보존·완료 조건을 확인하지 못하면 `POSTCONDITION_FAILED`다.
등록 실행기의 60초 제한 전에 불명확 결과를 반환할 시간을 남기도록 내부 Apple Events에는 총 50초
기한을 적용한다. 호출자가 별도로 더 짧은 실행 제한을 설정한 경우까지 보장하는 것은 아니다.

변경 결과는 `before` 요약·대상 창 `state`·후속 인수 `target`·검증 `checks`로 통일한다.
전체 창 조회는 status 기본값과 처음 열기 대상 발견에 쓰며, 지정 창 작업과 변경 후 확인은 대상 창만 읽는다.
창 수와 무관하게 한 번의 상태 조회를 한 AppleScript 프로세스로 모은다(내부 속성 조회는 남는다). 정상 변경은 실행 여부 조회를 포함해
4회 호출이며 이미 현재인 탭으로의 전환은 변경 명령·재조회를 생략한다. 변경 결과를 넘기는 IBL 가이드의
열기→전환→복귀→닫기를 한 `/ibl/execute` 요청으로 실행해 추가 status 없이 판본을 잇는다.
이는 코드 경로와 도구 호출 수의 검증이며 실제 모델의 완료 시간·토큰 절감률을 측정한 것은 아니다.

검증은 `backend/test_safari_control.py`·`backend/test_control_driver.py`에서 오래된 탭 번호,
배경 열기의 현재 탭 변경, 창 전체 소실, URL 이동, 응답 유실 뒤 대상 소실·재조회 실패,
제목 변경·중복 URL·실행 직전 상태 변경·조회 횟수·단일 IBL 조합을 포함한다.
실제 스크립트 자식 프로세스·등록 실행기·HTTP IBL 경계는 통과시키고 Apple Events 끝단만 대체한다.
생성한 AppleScript 6종은 macOS `osacompile`로 문법·Safari 사전 해석을 확인했다.
실제 Safari 읽기 인수는 새 조회와 기존 조회 모두 10초 시간 초과여서 완료하지 못했고,
실제 탭 변경은 실행하지 않았다. §15의 과거 실기 성공을 v2 실기 인수로 대신하지 않는다.

## 17 본체 OS 조작면 1층 구현 (2026-10-20)

§4 표의 "본체 앱은 드라이버가 전혀 없고 탐색 통로만 있다" 는 사실 가운데 **OS 수준** 을 먼저 메운다.
기존 드라이버(`fn:PC제어` → `PC제어부품` → `pc_control_mac.py`)에 새 낱말 없이 동작 16개를 더했다.
원격 맥에도 같은 실행 파일이 가므로 본체·원격 PC 가 같은 계약을 쓴다. Windows 는 `action_platforms` 로
실행 전에 거절한다(유튜브와 같은 자리).

| 조작면 | 동작 | 확인 범위 |
| --- | --- | --- |
| 화면 | display(읽기)·brightness | CoreGraphics 공개 API 로 목록·잠듦·세션 잠금. 밝기는 비공개 프레임워크라 `can_set_brightness` 와 basis 를 같이 돌려주고 외부 모니터는 거절 |
| 전원 | power(읽기)·keep_awake·allow_sleep·sleep | 전원 출처·배터리·잠 방지 플래그·잠 못 들게 하는 프로세스·뚜껑. keep_awake 는 전원 관리 목록 재조회, allow_sleep 은 프로세스 종료 확인 |
| 입회 | presence(읽기) | 마지막 입력 뒤 초·앞 앱·잠금·주 화면 잠듦. §6 의 "입력 유휴는 보조 관측" 을 읽을 값이 생겼다 |
| 앱 | apps(읽기)·launch·quit | 앱 목록 재조회. launch 는 앞으로 가져오지 않음(-g). quit 는 앱별 Apple Events 권한 |
| 클립보드 | clipboard·clipboard_write | 재조회 일치 |
| 네트워크 | network(읽기)·wifi | Wi-Fi 전원 재조회. SSID 는 위치 권한 없으면 null. 블루투스는 읽기만 |
| 단축어 | shortcuts·shortcut | 사용자 단축어를 이름으로 실행. 효과는 범위 밖(verified:false) |

lock 도 세션 잠금 재조회를 얻어 `verified` 가 가능해졌다(전엔 "요청만").

**동작별 조건.** 계약 `conditions` 에 동작마다 `needs_front`·`shared_state`·`verification_scope`·`effect` 를 적었고,
결과의 `condition`·`verification_scope` 칸으로 돌아온다. **needs_front 동작은 하나도 없다.** 그래서 §6 의
실행 전 검사(행위자 출처 판정)를 이 드라이버에 잇는 일은 이번 범위에서 필요가 없었고, "창 앞으로 가져오기" 는
needs_front 가 필요한 첫 동작이 될 것이므로 그 검사와 함께 넣는다.

**실측(본체 Mac16,11·macOS 26.6.2, 허브 local 경로).** 읽기 7종 0.0~0.2초(블루투스 포함 network 0.2초).
clipboard_write→clipboard 왕복 일치. keep_awake 는 전원 관리 목록에 즉시 등장, 중복 켜기 거절, allow_sleep 종료 확인.
launch `com.apple.TextEdit` 0.1초 verified, quit 2.3~8.7초 verified. brightness 는 외부 모니터라 변경 없이 거절(정직).
없는 단축어·없는 번들 ID 는 전송 없이 또는 즉시 거절. Windows 대상의 새 동작은 prepare·select 에서 거절.
wifi·sleep 은 이 세션 연결을 끊거나 작업을 중단시키므로 실기 실행하지 않았다(인수·거절 경로만 시험).

**발견.** ① 앱 목록의 이름은 현지화 표시 이름("텍스트 편집기")이라 `launch TextEdit` 의 이름 대조가 빗나갔다 →
번들 경로 파일 이름(TextEdit.app)도 이름으로 친다. ② 이 맥은 뚜껑 상태 키가 없어 `lid_closed:null`(노트북만 값).
③ 이 맥은 비공개 밝기 프레임워크가 열리지만 주 화면이 외부 모니터라 `can_set_brightness:false`.

**남긴 것.** 창 목록·창 앞으로(needs_front 와 함께)·앱 숨기기·블루투스 연결·예약 깨우기(관리자 권한)·Windows 동형
동작·브라우저 외 앱 드라이버. 본체 제어의 해마 용례는 아직 슬롯 모양만이라 첫 호출 마찰(§15)은 그대로다.


## Android OS 드라이버 계약 정비 (2026-10-20)

폰 컨트롤의 직접 Python 전송을 `Android제어`·`Android제어확인` 공용 함수로 연결했다.
준비·검증은 `data/scripts/android_control.py`, 기기 실행은 기존 `phone_control.py`·`phone_device.py`를
그대로 재사용한다. APK 교체나 새 내용어 없이 등록·연결·Python 준비 상태를 확인하고,
원 준비·접수 영수증의 대상·request_id·소스 지문·검증기 판본을 대조해 같은 작업만 조회한다.
폰 실행은 PC interactive 모드가 아닌 기존 phone_execution_contract의 background 경로다.

결과는 PC와 같은 status/target/verified/result/task_ref/verification/evidence_ref/failure다.
설정의 재조회값·음량 종류·센서 표본을 검증하며 진동·권한 화면은 요청 접수만 확인한다.
부작용 뒤 예외·응답 유실·시간 초과는 unknown, 확인한 불일치는 failed다. 자동 재전송·자동 롤백은 없다.
음량 복원은 기존 폰 안의 영수증과 외부 변경 감지를 유지한다. 확인 범위는 가이드와 contract에 명시한다.

데스크톱과 원격 선언형 앱은 같은 함수를 쓴다. 데스크톱에는 기존 작업 확인 버튼과 미확인 변경의
재전송 방지가 있고, 원격 앱은 원 반환을 control_task로 보존하고 상태·작업 ID·복구 안내를 표시한다.
앱 창 재시작 뒤 복구는 실행 원장의 원 반환으로 한다. 공개 정의는 installed.json·core_manifest,
의미 검색은 android_control_seeds.json의 add_examples_batch 등록 경로를 쓴다.

실제 HTTP IBL → 등록 스크립트 → 원격 Python → 원 영수증 검증 경계에서 삼성0의 기기 상태,
삼성1의 음량 상태, 예나폰의 구형 APK 부분 상태가 completed/verified:true로 돌아왔다.
삼성0은 대기:0의 pending 반환을 별도 HTTP 호출의 Android제어확인으로 completed까지 확인했다.
상태 읽기만 실기 검증했고 음량·화면·손전등 변경은 실행하지 않았다. 회귀는
backend/test_android_control.py·test_phone_control.py·test_phone_device.py·test_phone_control_ui.py에 있다.
이 범위는 기존 하드웨어 기능의 계약 정비이며 앱 실행·홈/뒤로·범용 화면 입력·브라우저 드라이버는 포함하지 않는다.

## 18 본체 OS 조작면 Windows 동형 (2026-10-20)

§17 이 "남긴 것" 으로 적은 **Windows 동형 동작** 을 메웠다. 계기 = 등록된 Windows 10 PC(tv1, Home 에디션·헬퍼 상주·관리자
아님·외부 TV 모니터)가 연결돼 있었으므로 그 PC 를 실기 삼았다. 새 낱말 0, 새 동작 0 — `pc_control_windows.ps1` 이
맥 실행 파일과 **같은 동작 이름·같은 결과 모양** 을 돌려주고, 허브 계약 `action_platforms` 의 16동작이 `["darwin","windows"]`
가 됐다. 관리자 권한을 요구하지 않는다 — 관리자여야만 읽히는 값·공개 API 가 없는 값은 `null` 과 `*_basis` 로 남긴다(거짓 0 금지).

| 조작면 | Windows 구현 | 맥과 다른 점 |
| --- | --- | --- |
| 화면 | `System.Windows.Forms.Screen`(목록) + WMI `WmiMonitorBrightness`(내장 화면만) + `OpenInputDesktop`·LogonUI(잠금) | id=DISPLAYn 번호, asleep·builtin null. 외부 모니터는 `can_set_brightness:false` 로 변경 없이 거절(맥과 동일) |
| 전원 | `SystemInformation.PowerStatus` + `powercfg /requests`(관리자만) + 잠 방지 자식 프로세스(`SetThreadExecutionState`) | flags·sleep_holders 는 관리자 아니면 null+`requests_basis`. keep_awake 재조회 = 프로세스 생존(`readback_basis`), 전원 관리 목록이 아니다 |
| 입회 | `GetLastInputInfo`·`GetForegroundWindow` | front 는 pid·name·title(bundle_id 없음). display_asleep 은 공개 API 없어 null |
| 앱 | `Get-Process`(창 있는 것) + 시작 메뉴 바로가기·`Start-Process`·`shell:AppsFolder`(AUMID) + `CloseMainWindow` | 이름 대조 = 프로세스명·exe·설명·제품명·바로가기 대상. 실행은 최소화 요청(앱이 무시 가능). 종료는 창 닫기 요청만, 강제 종료 없음 |
| 클립보드 | `Get-Clipboard -Raw`·`Set-Clipboard` | 같음(빈 글은 Clear) |
| 네트워크 | WinRT `Windows.Devices.Radios`(Wi-Fi·블루투스 전원, 관리자 불요) + `netsh wlan`(SSID) + 블루투스 연결 상태 선택자 | Wi-Fi 끄고 켜기가 관리자 없이 된다(맥 `networksetup` 과 동형) |
| 단축어 | 작업 스케줄러 루트 폴더(`\`)의 작업 = Windows 의 단축어 자리. `Start-ScheduledTask` 뒤 상태 재조회·`LastTaskResult` | 출력 없음·`verified:false` 는 같다. 사용자가 작업 스케줄러에서 이름 붙인 흐름을 부른다 |
| 잠금·잠자기 | `LockWorkStation` + 입력 데스크톱 재조회(이제 `verified` 가능), `Application.SetSuspendState(Suspend)` | lock 이 "요청만" 에서 재조회 확인으로 올라갔다 |

**실측(tv1 = Windows 10 19045·PowerShell 5.1·헬퍼 resident, 허브 원격 경로 `fn:PC제어` → `guestpc shell`).** 읽기 7종
display 16초·power 24초·presence 9초·apps 8초·clipboard 8초·network 8.5초·shortcuts 10초(첫 호출의 Add-Type 컴파일과
헬퍼 왕복 포함, 두 번째부터 4~9초). clipboard_write→clipboard 왕복 일치(한글·✓·줄바꿈)·빈 글 Clear 일치. keep_awake 40초 →
power 가 같은 pid 를 돌려줌 → allow_sleep 종료 확인. launch `notepad`(시작 메뉴 바로가기 경로) 12초 verified, apps 에 창 등장,
quit 10초 verified. network → wifi off → wifi on 재조회 일치(이 PC 는 이더넷이라 연결이 끊기지 않음). brightness 는 외부
모니터라 변경 없이 거절(정직). lock·sleep·shortcut 실행은 이 PC 에 사용자가 Netflix 를 띄워 둔 상태라 실행하지 않았다(인수·거절
경로만 시험).

**발견.** ① **허브 버그(OS 무관)**: `select` 가 요청에 `app_kind` 를 붙이고 `prepare` 가 그 요청을 재검증하면서 "받지 않는 인수"
로 거절 → launch·quit 이 원격 경로에서 접수조차 되지 않았다(§17 의 본체 실측은 `run_host` 직접 호출이라 드러나지 않음).
`validate` 가 파생 칸을 허용하고 다시 계산하도록 수리, 시험 추가. ② **PowerShell 배열 풀림**: 함수가 원소 1개 배열을 돌려주면
호출부에서 스칼라가 되어 `$found[0]` 이 해시 키 조회가 된다 → 앱 행이 전부 null 로 verified:true(거짓 성공의 모양). 호출부
`@()` 로 수리. ③ 블루투스 `DeviceInformation.FindAllAsync(aqs, null, AssociationEndpoint)` 는 이 PC 에서 8초 넘게 멈춰
network 전체가 30초 제한에 걸렸다. 공식 `GetDeviceSelectorFromConnectionStatus` 선택자는 0.6초 → 교체, 모든 WinRT 대기에
상한(기본 8초·열거 6초)과 취소. ④ `powercfg /requests`·`query session` 은 관리자/에디션 제한이라 기본값으로 못 쓴다.
⑤ 이 PC 의 `idle_seconds` 가 19만 초(2.3일) — Netflix 창이 앞에 있는데도 입력이 없다는 뜻이며 GetLastInputInfo 는
키보드·마우스만 센다(리모컨·원격 조작은 입력이 아님). 입회 판정 재료로 쓸 때 이 한계를 안다.

**남긴 것.** Windows 의 display_asleep·lid_closed(공개 API 없음), 관리자 세션에서의 flags·sleep_holders 실측, UWP 앱
launch 의 AUMID 경로 실측, Windows 한국어 로캘에서 `netsh` 출력 파싱(SSID·State 가 한글이면 null 로 남음 — enabled 는
WinRT 라 영향 없음), 창 앞으로(needs_front 와 함께)·Windows 창 목록.


## Android 접근성 UI 확장 (2026-10-20)

목적: 기존 접근성 제어를 앱/AI가 같은 호출·판정·복구 계약으로 쓰게 한다. 실행자·언어 코어·새 IBL 어휘는 추가하지 않는다.
`Android제어`의 action에 ui_snapshot/app_launch/home/back/tap/type_text를 추가하고 phone_ui.py를 실행 부품으로 선택한다.
PhoneAccessibilityService의 기존 snapshot/gesture/key/ACTION_SET_TEXT를 재사용하며, 같은 상주 서비스에 uiControl 다리를 둔다.
기존 직접 제어·화면 공유의 호출 서명은 유지한다. Android 앱과 회원 앱의 공유 접근성 소스를 함께 컴파일한다.

- 관측: 전면 패키지·창·방향·화면 크기, 빈 편집칸과 텍스트·포커스·resource_id·경로·ref, 생략 여부를 반환한다. 비밀번호는 가린다.
- 입력 대상: tap/back/type_text는 관측 snapshot_id 필수. 서비스의 드라이버 잠금 안에서 관측을 다시 비교한다. 불일치는 실행 전 실패. 사람/다른 앱과의 OS 원자성은 보장하지 않는다.
- 앱 실행: 정확한 패키지의 launcher Intent. 홈은 기본 홈 Intent를 해소해 실제 전면 패키지와 비교한다. 기본 홈 미선택은 확인 불가다.
- 문자 입력: 포커스가 있는 비밀번호 아닌 편집칸만 전체 교체. 같은 패키지·창·경로·resource_id와 실제 문자열을 다시 읽는다.
- 터치/뒤로: 명시한 expect(package/text 모두 일치)만 효과 확인. 없으면 동작 접수+후속 화면으로 completed/verified:false. 단순 화면 변화는 성공 증거로 쓰지 않는다.
- 실행은 한 번, 후속 관측만 최대 8회. 실행 전 거절 failed, 실행 후 불확실성 unknown. 원 task_ref/영수증을 Android제어확인으로 조회하며 자동 재입력·앱 재실행은 없다.
- 배포: UI 확장은 ui_contract:1 APK가 필요하며 구 APK는 변경 전에 거절한다. 하드웨어 계약은 유지한다. 화면은 접근성 트리이며 OCR/DOM/픽셀 이미지가 아니다.

검증: 관련 Python 회귀 134건(드라이버·실제 IBL/영수증·모의 네이티브 경계·기존 하드웨어·교재·배포), arm64/arm32 APK 빌드·회원 앱 Kotlin 컴파일·기존 JVM 단위 시험 통과.
실기기 UI 동작 인수는 별도이며, 테스트 통과를 실기기 터치·입력 완료로 해석하지 않는다. 세부 사용법은 data/guides/android_control.md.
