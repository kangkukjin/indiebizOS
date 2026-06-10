# 안드로이드 관리 도구

## 목적

에이전트가 USB로 연결된 안드로이드 기기를 관리할 수 있게 합니다.
기기 정보 확인, 화면 캡처, 파일 전송, 앱 관리 등을 수행합니다.

## 이 도구가 제공하는 것

- **기기 관리**: 연결된 기기 목록, 상세 정보
- **화면 제어**: 스크린샷 캡처, 텍스트 입력
- **파일 전송**: PC ↔ 안드로이드 파일 복사
- **앱 분석**: 설치된 앱 목록, 용량 분석
- **알림 조회**: 기기의 알림 목록 확인

## 설치 시 필요한 변경사항

### 1. 도구 함수 구현

**android_list_devices()**
- 연결된 안드로이드 기기 목록
- 기기 ID, 상태 반환

**android_device_info(device_id)**
- 기기 상세 정보
- 모델, OS 버전, 배터리 등

**android_capture_screen(device_id, output_path)**
- 현재 화면 스크린샷
- 파일로 저장

**android_notifications(device_id)**
- 알림 목록 조회
- 앱, 제목, 내용

**android_list_apps(device_id)**
- 설치된 앱 목록
- 패키지명, 버전

**android_app_sizes(device_id)**
- 앱별 용량 분석
- 캐시, 데이터 크기

**android_push_file(device_id, local_path, remote_path)**
- PC → 안드로이드 파일 전송

**android_pull_file(device_id, remote_path, local_path)**
- 안드로이드 → PC 파일 전송

**android_send_text(device_id, text)**
- 텍스트 입력 (가상 키보드)

### 2. 도구 정의

```json
{
  "name": "android_capture_screen",
  "description": "연결된 안드로이드 기기의 화면을 캡처합니다",
  "input_schema": {
    "type": "object",
    "properties": {
      "device_id": {"type": "string", "description": "기기 ID (생략 시 첫 번째 기기)"},
      "output_path": {"type": "string", "description": "저장 경로"}
    },
    "required": []
  }
}
```

### 3. ADB 연동

ADB(Android Debug Bridge)를 통해 기기와 통신합니다.

ADB 설치:
```bash
# macOS
brew install android-platform-tools

# Ubuntu
sudo apt install adb

# Windows
# Android SDK에서 platform-tools 다운로드
```

ADB 명령 예시:
```bash
adb devices              # 기기 목록
adb shell getprop        # 시스템 정보
adb screencap            # 스크린샷
adb pull/push            # 파일 전송
```

### 4. 기기 설정

사용자의 안드로이드 기기에서:
1. 설정 → 개발자 옵션 활성화
2. USB 디버깅 활성화
3. USB 연결 후 권한 승인

### 5. 보안 고려

- 민감한 정보 접근 가능 (알림, 파일 등)
- 에이전트에게 적절한 권한만 부여
- 사용자에게 작업 내용 알림

## 설계 고려사항

### 다중 기기
- 여러 기기 연결 시 선택
- device_id로 구분
- 기본값: 첫 번째 기기

### 연결 상태
- 기기 연결 확인
- 연결 끊김 처리
- 재연결 대기

### 권한
- 일부 명령은 루트 필요
- 권한 없는 경우 에러 처리
- 대안 제시

### 크로스 플랫폼
- Windows, macOS, Linux 대응
- ADB 경로 자동 감지

## 참고 구현

이 폴더의 `tool_android.py`는 Python + subprocess(adb) 기반 예시입니다.

```
tool_android.py
├── android_list_devices()
├── android_device_info()
├── android_capture_screen()
├── android_notifications()
├── android_list_apps()
├── android_app_sizes()
├── android_push_file()
├── android_pull_file()
├── android_send_text()
└── ANDROID_TOOLS (도구 정의)
```

### 의존성
```bash
# ADB만 설치하면 됨
# macOS
brew install android-platform-tools

# Ubuntu
sudo apt install adb
```

이 코드를 그대로 사용하지 말고, 현재 시스템에 맞게 구현하세요.

## 설치 완료 확인

- [ ] ADB가 설치되어 PATH에 있음
- [ ] 안드로이드 기기 USB 디버깅 활성화됨
- [ ] 에이전트가 도구를 호출할 수 있음
- [ ] 기기 목록 조회 가능
- [ ] 화면 캡처 가능
- [ ] 파일 전송 가능
