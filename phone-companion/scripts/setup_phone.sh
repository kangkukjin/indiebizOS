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

PKG="com.indiebiz.phoneagent"
LISTENER="$PKG/$PKG.NotificationCaptureService"
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJ="$(cd "$HERE/.." && pwd)"        # phone-companion/
APK="$PROJ/app/build/outputs/apk/debug/app-debug.apk"

say() { printf "\n\033[1m▶ %s\033[0m\n" "$*"; }

# 0) 디바이스 확인
say "디바이스 확인"
if ! adb get-state >/dev/null 2>&1; then
  echo "✗ adb 디바이스 미연결. USB + 디버깅 허용 후 다시." >&2; exit 1
fi
adb devices | sed -n '2p'

# 1) APK (없거나 --build 면 빌드)
if [[ "${1:-}" == "--build" || ! -f "$APK" ]]; then
  say "APK 빌드 (./gradlew assembleDebug)"
  ( cd "$PROJ" && ./gradlew :app:assembleDebug --console=plain | tail -2 )
fi
say "APK 설치"
adb install -r "$APK" | tail -1

# 2) 알림 리스너 권한 (수신 알림 → [sense:phone])
say "알림 접근 권한 부여"
adb shell cmd notification allow_listener "$LISTENER" || true
if adb shell settings get secure enabled_notification_listeners | tr ':' '\n' | grep -qi "$PKG"; then
  echo "✓ 알림 리스너 활성"
else
  echo "⚠ 알림 리스너 미확인 — 폰 설정에서 수동 허용 필요할 수 있음"
fi

# 3) API 키 주입 (.env 부분집합 → app-private)
say "API 키 주입"
python3 "$HERE/provision_phone_keys.py" || echo "⚠ 키 주입 건너뜀(.env 확인)"

# 4) 안내 (백엔드 시작은 앱에서 1탭 — 자동화는 후속)
say "완료 — 마지막 한 단계"
cat <<EOF
폰에서 'IndieBiz Phone Agent' 앱을 열고 "🌐 폰 백엔드 시작 (:8765)" 을 한 번 탭하세요.
그러면 폰이 자체 IBL 엔진으로 앱모드·실제 액션·[sense:phone] 알림을 서빙합니다.

확인:  adb forward tcp:8788 tcp:8765 \\
       && curl -s 127.0.0.1:8788/launcher/instruments | head -c 200 \\
       && adb forward --remove tcp:8788
EOF
