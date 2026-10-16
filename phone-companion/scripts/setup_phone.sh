#!/usr/bin/env bash
# 새 안드로이드 폰 일괄 설치 — APK 설치 + 알림 권한 + API 키 주입을 한 번에.
#
# 전제: 폰 USB 연결 + USB 디버깅 허용 + adb 인증됨. 디버그 빌드(키 주입 run-as 용).
# 엔진/레지스트리/패키지/런처는 APK 안(indiebiz_base.zip)에 번들 → 폰마다 복사 불필요.
# 키만 APK 밖(보안) → 정본 .env 에서 이 스크립트가 주입.
#
# 사용:  ./phone-companion/scripts/setup_phone.sh         (필요 시 빌드 후 설치)
#        ./phone-companion/scripts/setup_phone.sh --build  (무조건 재빌드)
set -euo pipefail

# 인자: --build · --limb <이름>(USB로 손발 등록, 원격 센서 화면 시작 허용)
#       --remote-media(기존 등록 폰의 원격 센서 화면 시작 허용)
BUILD=0; LIMB=""; REMOTE_MEDIA=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build) BUILD=1 ;;
    --limb) LIMB="${2:-}"; REMOTE_MEDIA=1; BUILD=1; shift ;;
    --remote-media) REMOTE_MEDIA=1; BUILD=1 ;;
    *) echo "알 수 없는 인자: $1" >&2; exit 2 ;;
  esac
  shift
done

PKG="com.indiebiz.phoneagent"
LISTENER="$PKG/$PKG.NotificationCaptureService"
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJ="$(cd "$HERE/.." && pwd)"        # phone-companion/
# 폰이 여러 대 꽂혀 있으면 ANDROID_SERIAL=<serial> 로 고른다(adb 표준 변수).

say() { printf "\n\033[1m▶ %s\033[0m\n" "$*"; }

# 0) 디바이스 확인
say "디바이스 확인"
if ! adb get-state >/dev/null 2>&1; then
  echo "✗ adb 디바이스 미연결. USB + 디버깅 허용 후 다시." >&2; exit 1
fi
adb devices | sed -n '2p'

# 0b) ABI 로 flavor 선택 — Chaquopy 16 의 Python 3.12 는 64비트만 지원해 32비트 전용 기기
#     (Galaxy J7 2017 등)는 Python 3.11 의 arm32 flavor 로만 설치된다(app/build.gradle productFlavors).
ABILIST="$(adb shell getprop ro.product.cpu.abilist | tr -d '\r')"
if [[ "$ABILIST" == *arm64-v8a* ]]; then FLAVOR=arm64; else FLAVOR=arm32; fi
APK="$PROJ/app/build/outputs/apk/$FLAVOR/debug/app-$FLAVOR-debug.apk"
echo "ABI=$ABILIST → flavor=$FLAVOR"

# 1) APK (없거나 --build 면 빌드)
if [[ "$BUILD" == 1 || ! -f "$APK" ]]; then
  TASK=":app:assemble$(tr '[:lower:]' '[:upper:]' <<< "${FLAVOR:0:1}")${FLAVOR:1}Debug"
  say "APK 빌드 (./gradlew $TASK)"
  ( cd "$PROJ" && ./gradlew "$TASK" --no-watch-fs --console=plain | tail -2 )
fi
say "APK 설치"
adb install -r "$APK" | tail -1

# 중앙 관리형 APK 업데이트의 최초 설치 권한. 이후 APK 전송·설치는 resident 통신을 쓴다.
say "중앙 업데이트 설치 권한 준비"
adb shell appops set "$PKG" REQUEST_INSTALL_PACKAGES allow \
  && echo "✓ IndieBiz 앱 설치 허용" \
  || echo "⚠ 폰 설정에서 IndieBiz의 '알 수 없는 앱 설치'를 허용해야 합니다"

# 2) 알림 리스너 권한 (수신 알림 → [sense:phone])
say "알림 접근 권한 부여"
adb shell cmd notification allow_listener "$LISTENER" || true
if adb shell settings get secure enabled_notification_listeners | tr ':' '\n' | grep -qi "$PKG"; then
  echo "✓ 알림 리스너 활성"
else
  echo "⚠ 알림 리스너 미확인 — 폰 설정에서 수동 허용 필요할 수 있음"
fi

# 2b) 알림 표시 권한 (송신측 [limbs:phone]{op:notify} — Android 13+ 런타임 권한)
#     VIBRATE 는 일반 권한이라 설치시 자동 부여. notify 만 명시 grant.
adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS 2>/dev/null \
  && echo "✓ 알림 표시 권한(POST_NOTIFICATIONS) 부여" \
  || echo "⚠ POST_NOTIFICATIONS 부여 실패 — 폰 설정에서 수동 허용"

# 2c) 미디어 세션 센서 권한(카메라·마이크) — best effort.
say "미디어 세션 권한(CAMERA·RECORD_AUDIO) 부여"
for PERM in android.permission.CAMERA android.permission.RECORD_AUDIO; do
  adb shell pm grant "$PKG" "$PERM" 2>/dev/null \
    && echo "✓ $PERM 부여" \
    || echo "⚠ $PERM 부여 실패 — 폰 설정 또는 앱의 '카메라 대기 모드' 화면에서 허용"
done
if [[ "$REMOTE_MEDIA" == 1 ]]; then
  say "등록된 중앙 PC의 원격 센서 화면 시작 허용"
  adb shell appops set "$PKG" SYSTEM_ALERT_WINDOW allow
  echo "※ 카메라·마이크 요청 시 잠금 위에 연결 화면을 켭니다. 잠금은 유지하며 연결 종료 시 화면도 닫습니다."
else
  echo "※ Android 10+ 원격 카메라는 '카메라 대기 모드' 또는 --remote-media 설치가 필요합니다."
fi

# 3) API 키 주입 (.env 부분집합 → app-private)
say "API 키 주입"
if [[ "$REMOTE_MEDIA" == 1 && -z "$LIMB" ]] && adb shell run-as "$PKG" test -s files/secrets/keys.json; then
  echo "✓ 기존 키와 노드 별칭 유지"
elif [[ -n "$LIMB" ]]; then
  python3 "$HERE/provision_phone_keys.py" --alias "$LIMB" || echo "⚠ 키 주입 건너뜀(.env 확인)"
else
  python3 "$HERE/provision_phone_keys.py" || echo "⚠ 키 주입 건너뜀(.env 확인)"
fi

# 3b) 손발 등록 (--limb 이름) — USB 연결된 폰에 로컬 허브의 1회용 초대로 등록.
if [[ -n "$LIMB" ]]; then
  say "손발 등록: $LIMB"
  python3 "$HERE/provision_phone_limb.py" --alias "$LIMB" ${INDIEBIZ_LIMB_HUB:+--hub "$INDIEBIZ_LIMB_HUB"}
fi

# 4) 안내 (백엔드는 앱 포그라운드 진입 시 자동 기동 — 별도 버튼 없음)
say "완료"
cat <<EOF
폰에서 'IndieBiz Phone Agent' 앱을 열기만 하면 됩니다.
앱이 포그라운드로 뜨면 백엔드(:8765)가 자동 기동되어, 폰이 자체 IBL 엔진으로
앱모드·실제 액션·[sense:phone] 알림을 서빙합니다. (별도 '시작' 버튼 없음)
※ 키를 새로 주입했다면, 앱 force-stop 후 다시 열어야 새 키가 로드됩니다.

확인:  adb forward tcp:8788 tcp:8765 \\
       && curl -s 127.0.0.1:8788/launcher/instruments | head -c 200 \\
       && adb forward --remove tcp:8788
EOF
