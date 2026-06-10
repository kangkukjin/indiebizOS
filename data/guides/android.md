# 안드로이드 폰 조작 가이드 ([limbs:android]{op})

USB 디버깅으로 연결된 안드로이드 폰을, **화면을 읽고 → 터치/입력**하는 방식으로 조작합니다.
데스크톱 `limbs:screen`, 웹 `limbs:browser`의 **폰 버전** — 같은 "지각→행위" 루프입니다.

## 핵심 원칙: 눈대중 금지, 항상 snapshot 먼저

좌표를 추측해서 누르면 **빗나갑니다.** 반드시 `snapshot`으로 화면을 읽어
요소의 **실제 라벨과 OS가 알려준 정확한 좌표**를 받은 뒤, 그걸로 누릅니다.
(uiautomator는 이 기기들에서 잘 작동합니다 — 과거 "불안정하니 좌표로 찍어라"는 조언이
오히려 빗나감의 원인이었습니다. 요소의 bounds 중심 탭은 정밀합니다.)

```
[limbs:android]{op: "snapshot"}                  # ① 화면 독해 (요소+라벨+좌표)
[limbs:android]{op: "tap", query: "전송"}         # ② 라벨로 탭 (가장 견고)
```

- `tap`은 **query(라벨/content-desc/resource-id 일부)** 로 누르는 것이 1순위. 좌표가 바뀌어도 안전.
- query로 안 잡히면 snapshot이 준 `x,y`를 직접 사용 (이것도 눈대중이 아니라 OS 좌표).

## 표준 흐름 (예: 카카오톡 메시지 보내기)

```
[limbs:android]{op: "open_app", package_name: "com.kakao.talk"}   # 앱 실행
# (대화방을 연 상태에서)
[limbs:android]{op: "snapshot"}                                   # 입력창 위치 확인
[limbs:android]{op: "tap", query: "message_edit_text"}           # 입력창 포커스
[limbs:android]{op: "type", text: "안녕하세요"}                    # 텍스트 입력
[limbs:android]{op: "snapshot"}                                   # ★ 다시 읽기 — 전송 버튼이 이제 생김
[limbs:android]{op: "tap", query: "전송"}                         # 전송
```

### ★ 가장 중요한 함정: 동적으로 생기는 버튼

**카카오톡 전송 버튼은 입력창이 비어 있으면 화면에 존재하지 않습니다.**
글자를 입력하는 순간 비로소 나타납니다(`content-desc="전송"`, `resource-id ...:id/send_button_layout`).
그래서 **`type` 다음에는 반드시 `snapshot`을 다시** 떠야 전송 버튼을 찾을 수 있습니다.
입력 전에 전송 버튼을 찾으면 당연히 못 찾습니다 — 과거 실패의 주원인.

이 패턴은 카톡만이 아닙니다. 많은 앱이 입력/선택 후 버튼을 동적 표시합니다.
**행동으로 화면이 바뀌면, 다음 행동 전에 다시 snapshot.**

## op별 요약

| op | 용도 | 주요 파라미터 |
|----|------|--------------|
| `snapshot` | 화면 독해 (기본) | 없음 |
| `tap` | 요소 탭 | `query`(권장) 또는 `x,y`, `index` |
| `type` | 입력창에 텍스트 | `text` |
| `swipe` | 스와이프/스크롤 | `direction`(up/down/left/right) 또는 `x1,y1,x2,y2` |
| `key` | 시스템 키 | `key`: back/home/enter/recent/delete |
| `long_press` | 길게 누르기 | `x,y`, `duration_ms` |
| `open_app` | 앱 실행 | `package_name` (예 com.kakao.talk) |

- **앱 실행은 항상 `open_app`(패키지명)** — 홈 화면 아이콘 탭은 페이지마다 위치가 달라 비추천.
- **키보드 닫기**: `key` + `back`.

## 한글 입력

`type`의 영문/숫자는 ADB로 바로 입력되지만, **한글은 전용 IME(`com.indiebiz.cliphelper`)가
설치·활성화되어 있어야** 합니다 (commitText 주입 방식). 미설치 시 한글 입력은 실패하고
영문만 됩니다. 설치 소스는 패키지 내 `apk/` 참조.

## 한계 (정직하게)

- **접근성 트리에 잡히는 요소만** 정밀 제어됩니다. 게임·커스텀 캔버스·지도/사진 내부 임의 지점은
  요소로 안 잡혀 좌표/추정에 의존 → 정밀도 하락.
- **FLAG_SECURE 앱**(일부 은행/정부 앱)은 screencap·uiautomator를 차단할 수 있음 → 막히면 사용자에게 보고.
- 패널이 뜨는 **애니메이션 순간**엔 snapshot이 빈 결과를 줄 수 있음 → 잠시 후 재시도.
- 같은 방법이 실패하면 **재시도 대신 대안**으로(query↔좌표). 완료 못 하면 막힌 지점을 솔직히 보고.

## 전제 조건

- PC에 ADB 설치 + 폰 USB 디버깅 ON + "이 컴퓨터 허용" 승인.
- 여러 기기 연결 시에만 `device_id` 명시 — 보통은 생략(첫 기기 자동).

## 구조화 데이터: 문자·통화·연락처 (액션 없이 raw adb로)

화면 조작과 **완전히 다른 길**입니다. 문자/통화/연락처는 안드로이드 **content provider**에
구조화되어 저장돼 있어, 화면을 긁지 말고 **DB를 직접 쿼리**하면 100건이든 1000건이든
한 번에 정리·검색·집계할 수 있습니다. (메시지 "정리"가 화면긁기로 안 됐던 이유 = 도구를 잘못 골라서.)

아직 전용 IBL 액션은 없습니다. **`run_command` 도구로 adb 명령을 직접 실행**합니다.
(`run_command`는 `execute_ibl`과 같은 레벨의 최상위 쉘 도구 — IBL 경유가 아니라 곧장 호출.)
자주 쓰게 되면 `[limbs:android_message]{op}` 액션으로 승격 — 백업 `_archive/android_full_*/`에 옛 구현 보존.

### 문자 정리 — 검증된 레시피 (2026-06-06 실측)

```bash
# ① 받은문자 조회 (정렬은 따옴표 이스케이프 필수 — 공백이 원격 셸에서 쪼개짐)
adb shell "content query --uri content://sms/inbox --projection address:date:body --sort \"date DESC\""

# ② 발신처별 집계 예: 재난문자가 몇 건인지
adb shell "content query --uri content://sms/inbox --projection _id --where \"address LIKE '%CMAS%'\""

# ③ 삭제 — 아래 함정 3개를 반드시 지킬 것
adb shell "appops set com.android.shell WRITE_SMS allow"                                   # 권한 선행
adb shell "content delete --uri content://sms --where \"address LIKE '%CMAS%'\""           # 베이스 URI
adb shell "content query --uri content://sms --projection _id --where \"address LIKE '%CMAS%'\"" | grep -c Row:  # 검증(0이어야)
```

### ★ 삭제 함정 3개 (약한 모델이 정확히 미끄러지는 곳 — 반드시 지킬 것)

1. **조용한 실패**: 권한 없이 `content delete` → **exit=0(성공)인데 0건 삭제.** 절대 exit 코드를 믿지 말 것.
   → **삭제 직후 같은 조건으로 재조회해 0건임을 확인**하기 전엔 "지웠다"고 말하지 말 것.
2. **권한 선행**: `appops set com.android.shell WRITE_SMS allow` 먼저. (Android 10+ 제약, 폰 재시작 시 초기화 → 매번 부여.)
3. **삭제는 베이스 URI**: 조회는 `content://sms/inbox` OK지만 **삭제는 `content://sms`**.
   `/inbox`에 delete 하면 `Unknown URL` 에러.

### ★★ 재난문자는 저장소가 다르다 (가장 중요)

실종경보·폭염경보 등 **재난문자(CMAS)의 진짜 원본은 `content://cellbroadcasts`** 라는 별도 저장소입니다.
`content://sms`엔 **사본(미러)** 만 있어서, **sms만 지우면 메시지 앱 화면엔 그대로 남습니다.**
앱에서 없애려면 cellbroadcasts까지 지워야 합니다.

```bash
adb shell "content query --uri content://cellbroadcasts --projection _id:body"             # 재난문자 원본 조회
adb shell "content delete --uri content://cellbroadcasts --where \"_id>0\""                 # 전체 삭제(베이스 URI)
adb shell "am force-stop com.samsung.android.messaging"                                     # 앱 캐시 재읽기 유도
```

- 삼성 메시지 앱은 자기 캐시 DB가 있어 저장소를 비워도 즉시 갱신 안 될 수 있음 → `force-stop` 후 재확인.
- 그래도 남으면 앱 내부 캐시(루트 없이 불가) → 앱 설정에서 직접 삭제하거나 화면긁기로 앱 안에서 삭제.

### 한계 (정직하게)

- **카카오톡 등 서드파티 메신저는 이 길이 없습니다.** 암호화 로컬 DB라 content provider도 API도 없음 →
  화면긁기(위 thin 액션)만 가능하고, 대량 집계·정리는 본질적으로 약합니다. **SMS만 구조화 가능.**
- 통화기록(`content://call_log/calls`)·연락처(`content://contacts`)도 같은 패턴(읽기는 READ_*, 삭제는 WRITE_* appop).

## 보존된 구조화 기능 (백업)

옛 SMS/통화/연락처/앱관리 등 45개 액션은 `data/packages/_archive/android_full_*/`에 백업되어 있습니다
(`sms_manager.py`=문자 get/search/delete, `device_info.py`=appops 권한부여). 위 레시피를 자주 쓰게 되면
이 백업을 바탕으로 `[limbs:android_message]{op}` 액션으로 부활시키되, **함정 3개 + cellbroadcasts**를 반영할 것.
지금 등록된 건 "화면 조작" 센터피스 하나뿐입니다.
