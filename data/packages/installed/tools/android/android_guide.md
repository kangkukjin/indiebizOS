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
