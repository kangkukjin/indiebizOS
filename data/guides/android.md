# Android Device Manager 사용 가이드

## 기기 연결 기본 흐름

```
android_list_devices → android_grant_permissions → 기능 사용
   (연결 확인)           (권한 부여)               (SMS, 앱, 파일 등)
```

### 1단계: 기기 연결 확인
```python
android_list_devices()
# 반환: 기기 ID, 연결 상태, 모델명
```

**전제 조건:**
- USB 디버깅 활성화 필요
- 기기가 표시되지 않으면 USB 케이블/설정 확인

### 2단계: 권한 부여
```python
android_grant_permissions()
# device_id 생략 시 첫 번째 기기 자동 선택
```

### device_id 생략 규칙
- 모든 android 도구에서 `device_id` 생략 시 **첫 번째 기기 자동 선택**
- 여러 기기 연결 시에만 device_id 명시 필요

---

## 권한 관리

### android_grant_permissions 필요 시점
- SMS, 통화기록, 연락처 조회가 **빈 결과를 반환할 때**
- SMS, 통화기록, 연락처 **삭제가 필요할 때**
- Android 10 이상 기기에서 **처음 연결했을 때**
- **폰을 재시작한 후** (권한이 초기화될 수 있음)

### 권한 진단
```python
# 현재 권한 상태 확인
android_check_permissions()
# → READ/WRITE_SMS, READ/WRITE_CALL_LOG, READ/WRITE_CONTACTS 각각의 상태 반환
```

---

## SMS/MMS/RCS 도구 선택 가이드

### 상황별 도구 선택

| 목적 | 사용할 도구 | 속도 |
|------|------------|------|
| 메시지 개수 확인 | `android_delete_mms_by_content` (dry_run=true) | 빠름 (2-3초) |
| 메시지 삭제 | `android_delete_mms_by_content` (dry_run=false) | 빠름 (2-3초) |
| 메시지 내용 확인 | `android_search_sms` | 느림 (4-5초) |
| SMS만 조회 | `android_get_sms` | - |
| MMS/채팅+ 조회 | `android_get_mms` | - |
| SMS+MMS 통합 조회 | `android_get_all_messages` | - |
| SMS 단일/조건부 삭제 | `android_delete_sms` | - |
| SMS+MMS ID 기반 삭제 | `android_delete_messages` | - |

### 핵심 판단 기준
- **"~~ 몇 개야?"** → `android_delete_mms_by_content(body_contains="검색어", dry_run=true)`
- **"~~ 삭제해줘"** → `android_delete_mms_by_content(body_contains="검색어", dry_run=false)`
- **"~~ 내용 보여줘"** → `android_search_sms(query="검색어")`

---

## 삭제 안전 규칙

### 반드시 dry_run=true 먼저 실행

```python
# 1단계: 삭제 대상 미리보기
android_delete_mms_by_content(body_contains="광고", dry_run=True)
# → target_count, sms_count, mms_count, rcs_count 확인

# 2단계: 사용자 확인 후 실제 삭제
android_delete_mms_by_content(body_contains="광고", dry_run=False)
```

```python
# SMS 조건부 삭제도 동일
android_delete_sms(body_contains="광고", dry_run=True)   # 미리보기
android_delete_sms(body_contains="광고", dry_run=False)   # 실제 삭제
```

**중요:** 모든 삭제는 **복구 불가**

---

## android_delete_sms 상세 사용법

### 삭제 방법 (여러 조건 조합 가능 - AND 조건)

| 파라미터 | 설명 | 예시 |
|---------|------|------|
| `sms_id` | 특정 메시지 1개 삭제 | `sms_id="12345"` |
| `address` | 특정 발신자의 모든 메시지 | `address="01012345678"` |
| `body_contains` | 본문에 특정 문자열 포함 | `body_contains="광고"` |
| `before_date` | 특정 날짜 이전 메시지 | `before_date="2024-01-01"` |

### 와일드카드 사용
- `address` 필드에서 `%` 사용 가능
- 예: `address="1588%"` → 1588로 시작하는 모든 번호

### 삭제 예시
```python
# 긴급재난문자 삭제
android_delete_sms(address="#CMAS#Severe", dry_run=True)

# 광고 문자 삭제
android_delete_sms(body_contains="광고", dry_run=True)

# 특정 번호의 배송 관련 문자만 삭제
android_delete_sms(address="1588%", body_contains="배송", dry_run=True)

# 2023년 이전 문자 전체 삭제
android_delete_sms(before_date="2023-01-01", dry_run=True)
```

### SMS vs MMS 삭제 구분
- `android_delete_sms`: **SMS만** 삭제 가능
- `android_delete_messages`: SMS와 MMS를 **ID 목록으로** 일괄 삭제
- `android_delete_mms_by_content`: SMS/MMS/RCS **모두** 조건부 삭제

---

## 앱 관리 워크플로우

### 불필요한 앱 정리
```
android_list_apps → android_app_sizes → android_uninstall_app
   (앱 목록 확인)     (용량 큰 앱 확인)    (앱 삭제)
```

### 상세 앱 분석
```python
# 용량 순위 조회
android_app_sizes(limit=20)

# 사용량 통계 (최근 24시간)
android_app_usage()
# → 마지막 사용 시간, 총 사용 시간, 세션 횟수

# 전체 정보 한 번에 조회
android_apps_with_details(limit=50)
# → 패키지명, 용량, 마지막 사용, 총 사용 시간

# 특정 앱 상세
android_app_info(package_name='com.example.app')
```

### 앱 삭제
```python
android_uninstall_app(package_name='com.example.app')
```
**주의:** 사용자 설치 앱만 삭제 가능, 시스템 앱 불가, 복구 불가

---

## 파일 전송

### PC에서 기기로 (push)
```python
android_push_file(
    local_path='/Users/user/Documents/report.pdf',
    remote_path='/sdcard/Download/'   # 기본 저장 위치
)
```

### 기기에서 PC로 (pull)
```python
android_pull_file(
    remote_path='/sdcard/DCIM/Camera/photo.jpg',
    local_path='/Users/user/Desktop/'   # 생략 시 자동
)
```

**주의사항:**
- 대용량 파일은 전송 시간이 걸릴 수 있음
- 기기 저장 공간 확인 필요 (`android_system_status`)
- 일부 시스템 경로는 접근 제한될 수 있음

---

## 연락처/통화 관련 도구

### 연락처
```python
# 목록 조회
android_get_contacts(limit=100)

# 검색 (이름 또는 번호)
android_search_contacts(query='홍길동')
android_search_contacts(query='010-1234')

# 삭제 (contact_id 또는 phone_number)
android_delete_contact(contact_id='123')
android_delete_contact(phone_number='01012345678')
```
**삭제 시 WRITE_CONTACTS 권한 필요** → `android_grant_permissions` 먼저 실행

### 통화
```python
# 통화 기록 조회
android_get_call_log(call_type='all', limit=50)
# call_type: all, incoming(수신), outgoing(발신), missed(부재중)

# 전화 걸기
android_make_call(phone_number='01012345678')

# 통화 종료
android_end_call()

# 통화 기록 삭제
android_delete_call_log(call_id='456')
```

---

## 기타 유용한 도구

### 기기 상태 확인
```python
# 상세 정보 (모델, OS 버전, 빌드 등)
android_device_info()

# 종합 상태 (배터리, 온도, 저장 공간)
android_system_status()
```

### 화면 캡처
```python
android_capture_screen()
# → 스크린샷 파일 경로 반환
```

### 알림 확인
```python
android_notifications()
# → 알림 제목, 내용, 앱 이름, 시간
```

### 텍스트 전송
```python
android_send_text(text='전송할 텍스트')
# 주의: 기기에서 텍스트 입력 필드가 활성화되어 있어야 함
# 한글은 클립보드 방식으로 전송됨
```

### Android Manager UI
```python
open_android_manager()
# 전화, 문자, 연락처를 관리할 수 있는 UI 열기
```

---

## UI 자동화 (Computer-Use 패턴)

ADB를 통해 안드로이드 화면을 직접 제어하는 기능이다.
AI가 스크린샷을 보고 → 분석하고 → 조작하는 루프를 반복한다.

### 기본 루프

```
android_ui_screenshot → 화면 분석 → android_ui_tap / type_text / swipe → 확인
```

### 핵심 원칙 (반드시 준수)

1. **앱 실행은 반드시 `open_app`** 사용 (패키지명 기반, 가장 안정적)
2. **`find_tap`/`find_element`/`hierarchy`는 사용하지 마라** — uiautomator가 불안정하여 대부분 실패한다. 반드시 `android_screenshot` + `tap`(좌표)으로 조작한다.
3. **좌표 추정이 어려우면 `android_screenshot_grid` 사용** (그리드 오버레이)
4. **매 동작 후 반드시 `android_screenshot`으로 결과 확인** — 스크린샷 없이 다음 동작 금지
5. **한글 입력은 `type_text`** — IndieBiz IME가 자동으로 처리
6. **실패한 방법은 다시 시도하지 마라** — `find_element`가 한 번 실패하면 다시 시도해도 실패한다. 즉시 스크린샷 기반으로 전환한다.
7. **완료하지 못한 작업을 완료했다고 보고하지 마라** — 작업이 끝나지 않았으면 현재 상황과 막힌 부분을 솔직하게 보고한다.

### 실패 시 행동 규칙

```
hierarchy 실패 → screenshot_grid로 전환 (find_element/find_tap 재시도 금지)
screenshot 실패 → FLAG_SECURE 앱일 수 있음 → 사용자에게 보고
tap 후 화면 변화 없음 → 좌표가 잘못됨 → screenshot_grid로 재확인
작업 완료 불가 → 현재까지 진행 상황 + 막힌 이유를 솔직하게 보고
```

### 앱 실행

```python
# 패키지명으로 실행 (가장 확실)
open_app(package_name='com.tempdiary')

# 패키지명 모르면 검색
# adb shell pm list packages | grep 키워드
```

**주의: 홈 화면 아이콘 탭은 비추천** — 좌표가 부정확하고 페이지에 따라 다름

### 화면 캡처 및 좌표 파악

```python
# 일반 스크린샷 (AI 비전 분석용)
android_ui_screenshot()

# 그리드 오버레이 스크린샷 (좌표 캘리브레이션)
android_ui_screenshot_grid(rows=10, cols=5)
# → 셀 ID(A0~E9)와 실제 좌표가 오버레이된 이미지 반환
# → grid_map에 각 셀의 center/bounds 좌표 포함
```

### 화면 조작

```python
# 좌표 탭 (스크린샷에서 추정한 좌표)
android_ui_tap(x=540, y=1800)

# 그리드 셀 탭 (screenshot_grid로 확인한 셀 ID)
android_ui_tap_grid(cell='C7')

# 스와이프 (스크롤, 페이지 넘기기)
android_ui_swipe(x1=900, y1=1200, x2=200, y2=1200, duration_ms=300)  # 왼쪽으로
android_ui_swipe(x1=200, y1=1200, x2=900, y2=1200, duration_ms=300)  # 오른쪽으로
android_ui_swipe(x1=540, y1=2000, x2=540, y2=800, duration_ms=300)   # 위로 스크롤

# 길게 누르기
android_ui_long_press(x=540, y=1200, duration_ms=1000)

# 시스템 키
android_ui_press_key(keycode='HOME')    # 홈
android_ui_press_key(keycode='BACK')    # 뒤로 (키보드 닫기에도 유용)
android_ui_press_key(keycode='RECENT')  # 최근 앱
android_ui_press_key(keycode='ENTER')   # 엔터
```

### 텍스트 입력

```python
# 입력 필드를 먼저 탭한 후
android_ui_tap(x=270, y=1810)

# 텍스트 입력 (한글/영문 자동 처리)
android_ui_type_text(text='코스트코 방문, 머리깍음')
# → 영문/숫자: ADB input text 직접 입력
# → 한글: IndieBiz IME commitText() 주입

# 키보드 닫기
android_ui_press_key(keycode='BACK')
```

### UI 요소 검색 (hierarchy/find_element/find_tap)

`uiautomator dump`는 `waitForIdle()`에 의존하며, 아래 조건에서 실패한다:

| 상황 | dump 결과 | 원인 |
|------|-----------|------|
| **삼성 홈 런처** | ❌ 항상 실패 | 위젯(Tesla, 시계 등)이 주기적 UI 업데이트 → idle 불가 |
| **앱 전환 직후** | ❌ 실패 확률 높음 | 전환 애니메이션이 끝나지 않음 |
| **일반 앱 (3초+ 대기 후)** | ✅ 대부분 성공 | 정적 화면은 idle 도달 |
| **FLAG_SECURE 앱** | ❌ 항상 실패 | 보안 정책으로 차단 |

**사용 규칙:**
- 홈 화면에서는 **절대 사용하지 마라** (항상 실패)
- 앱 내에서는 **open_app 후 3초 이상 대기한 뒤** 시도 가능
- **한 번 실패하면 재시도하지 말고** screenshot + tap(좌표)로 전환
- 가장 안정적인 패턴은 항상 `screenshot` + `tap`(좌표)

```python
# ⚠️ 홈 화면에서 사용 금지, 앱 내에서만 사용
android_ui_find_element(query='저장하기')
android_ui_find_and_tap(query='확인', index=0)
android_ui_hierarchy()
```

### 실전 예시: TempDiary 앱에서 일기 작성

**올바른 패턴** (스크린샷 → 분석 → 탭 반복):
```
1. [limbs:open_app]{package_name: "com.tempdiary"}  # 앱 실행
2. (2~3초 대기)
3. [limbs:android_screenshot]                        # ✅ 화면 확인 (일기 목록 보임)
4. [limbs:tap]{x: 980, y: 2150}                      # 우하단 + 버튼 탭
5. [limbs:android_screenshot]                        # ✅ 화면 확인 (일기 작성 폼)
6. [limbs:tap]{x: 270, y: 1810}                      # "제목을 입력하세요" 필드 탭
7. [limbs:type_text]{text: "오늘의 일기"}             # 제목 입력
8. [limbs:android_key]{keycode: "BACK"}              # 키보드 닫기
9. [limbs:android_screenshot]                        # ✅ 화면 확인 (제목 입력 확인)
10. [limbs:tap]{x: 270, y: 2020}                     # "오늘 하루는..." 본문 필드 탭
11. [limbs:type_text]{text: "내용 작성"}              # 본문 입력
12. [limbs:android_key]{keycode: "BACK"}             # 키보드 닫기
13. [limbs:swipe]{x1:540, y1:2000, x2:540, y2:800}  # 아래로 스크롤 (저장 버튼 찾기)
14. [limbs:android_screenshot]                       # ✅ 화면 확인 (저장하기 보임)
15. [limbs:tap]{x: 360, y: 2060}                     # 저장하기 탭
16. [limbs:android_screenshot]                       # ✅ 결과 확인 ("저장되었습니다" 다이얼로그)
```

**잘못된 패턴** (❌ 절대 하지 마라):
```
❌ hierarchy 실패 → find_element 시도 → 또 find_tap 시도  (같은 방법 반복)
❌ 스크린샷 확인 없이 연속 탭  (어디를 탭하는지 모름)
❌ 실패했는데 "완료했습니다"라고 보고  (거짓 보고)
❌ 좌표를 확인 안 하고 추측으로 탭  (screenshot_grid 사용하라)
```

### 알려진 제약사항

| 제약 | 설명 | 대응 |
|------|------|------|
| **FLAG_SECURE 앱** | 정부24, 은행 앱 등은 screencap/uiautomator 차단 | 사용자에게 수동 조작 안내 |
| **uiautomator 불안정** | hierarchy/find_tap/find_element가 대부분 실패 | **사용 금지** — screenshot + tap(좌표) 사용 |
| **좌표 추정 오차** | AI 스크린샷 분석 시 축소로 인한 오차 | screenshot_grid(그리드 캘리브레이션) 사용 |
| **홈 화면 페이지** | 홈 화면 아이콘은 페이지마다 다른 위치 | open_app(패키지명)으로 실행 |
| **앱 로딩 시간** | 앱이 열리기까지 대기 필요 | 2~4초 대기 후 스크린샷 확인 |
| **실패 반복** | 같은 방법으로 재시도해도 동일 실패 | 즉시 대안으로 전환, 재시도 금지 |
| **거짓 완료 보고** | 완료하지 못한 작업을 완료라고 보고 | 현재 상황 + 막힌 이유를 솔직하게 보고 |

### 화면 크기 참고

```python
android_ui_screen_info()
# → 일반적으로 1080x2400 (FHD+), 밀도 480dpi
# → 그리드 기본(5x10): 셀 크기 216x240px
```
