#!/bin/bash
# make_mac_launcher.sh — "IndieBiz 시작" 앱 아이콘 생성 (macOS, 멱등 재생성)
#
# 시작방식 개편(2026-08-05): 터미널 없이 더블클릭으로 시스템 전체(vite+Electron+백엔드
# +keeper)를 시작한다. Electron main.js 가 수명주기의 주인 — 창을 다 닫으면 백엔드까지
# 전부 정리하고 죽는다(사용자 확정: "시스템이 꺼지면 다 정리하고 죽어야지").
#
# - 생성 위치: /Applications/IndieBiz 시작.app (독에 끌어다 놓으면 원클릭)
# - 중복 실행: Electron 단일 인스턴스 잠금이 둘째를 조용히 물리고 첫 창을 앞으로
# - 첫 실행 시 macOS 가 "데스크탑 폴더 접근" 권한을 한 번 물어본다 — 허용해야 한다
#   (저장소가 ~/Desktop 아래라서. launchd 와 달리 GUI 앱은 프롬프트가 뜬다)
# - 로그: 백엔드 stdout → data/backend_runtime.log (조종실 '시스템 로그' 뷰어로 열람)
# - ★PATH 에 /usr/sbin 필수 — 없으면 종료 정리의 lsof 포트 소탕이 침묵 실패해
#   "창을 닫아도 백엔드가 산다"(2026-08-05 실발. main.js 는 절대경로 폴백도 가짐)

set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
APP="/Applications/IndieBiz 시작.app"
NPM="$(command -v npm || echo /opt/homebrew/bin/npm)"
NPM_DIR="$(dirname "$NPM")"

TMP=$(mktemp -d)
cat > "$TMP/launcher.applescript" <<EOF
do shell script "cd '$REPO/frontend' && PATH='$NPM_DIR:/usr/bin:/bin:/usr/sbin:/sbin' nohup '$NPM' run electron:dev >> '$REPO/data/electron_dev.log' 2>&1 &"
EOF

rm -rf "$APP"
osacompile -o "$APP" "$TMP/launcher.applescript"
rm -rf "$TMP"

# ── 이름 개선(2026-08-05): osacompile 산출물의 실행 파일명 기본값이 "applet"이라
# macOS 권한 경고창(화면 기록·손쉬운 사용·Automation)이 전부 "applet이 ~하려고 합니다"로
# 뜬다(백엔드가 이 앱 아래 스폰되므로 권한 귀속이 여기로 온다). 실행 파일을 개명하고
# Info.plist 를 동기, 번들 ID 를 고정(재생성해도 TCC 귀속이 같은 앱으로 유지되게).
# ★재서명 필수 — Apple Silicon 은 내용이 바뀐 ad-hoc 서명 앱을 실행 즉시 죽인다.
EXEC_NAME="IndieBiz"
mv "$APP/Contents/MacOS/applet" "$APP/Contents/MacOS/$EXEC_NAME"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable $EXEC_NAME" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.indiebiz.launcher" "$APP/Contents/Info.plist" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.indiebiz.launcher" "$APP/Contents/Info.plist"
codesign --force --sign - "$APP"
echo "생성 완료: $APP"
echo "독(Dock)에 끌어다 놓으면 원클릭 시작. 창을 다 닫으면 시스템 전체가 정리·종료됩니다."
