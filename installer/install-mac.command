#!/bin/bash
# IndieBiz OS — 더블클릭 설치기 (macOS)
#
# 일반 사용자용 무터미널 경로: 이 파일을 더블클릭하면 (1) 키 입력창,
# (2) 모델 선택창이 뜨고, 리턴을 치면 알아서 씨앗 바이너리를 받아 설치한다.
# 터미널 명령을 직접 칠 필요도, 설치 중 확인(a)에 답할 필요도 없다.
#
# 구현 노트: .command 는 맥에서 "더블클릭 → 터미널에서 실행"되는 표준 파일이다.
# 입력은 osascript 네이티브 대화상자로 받아(붙여넣기 쉬움), 키는 명령줄이 아니라
# 환경변수로만 씨앗에 전달한다(ps/로그 노출 회피). 진행 로그는 이 터미널에 보인다.

set -euo pipefail

TITLE="IndieBiz OS 설치"
REPO="kangkukjin/indiebizOS"
ARCH="$(uname -m)"                       # arm64(애플실리콘) | x86_64(인텔)
BIN_URL="https://github.com/${REPO}/releases/download/seed-latest/indiebiz-seed-macos-${ARCH}"
BIN="${HOME}/.indiebiz-seed"

# 취소 시 깔끔히 종료
_cancelled() { osascript -e "display notification \"설치를 취소했습니다.\" with title \"${TITLE}\"" 2>/dev/null || true; exit 0; }

# 1) API 키 (붙여넣기, 가림 입력)
KEY="$(osascript <<END 2>/dev/null
text returned of (display dialog "AI API 키를 붙여넣으세요.\n\n· Anthropic: sk-ant-…\n· OpenAI: sk-…\n· Google: AIza…\n\n(키는 이 컴퓨터의 설정 파일에만 저장되며 외부로 전송되지 않습니다.)" default answer "" with hidden answer with title "${TITLE}" buttons {"취소","계속"} default button "계속" cancel button "취소")
END
)" || _cancelled

KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"
if [ -z "$KEY" ]; then
  osascript -e "display dialog \"키가 비어 있습니다. 다시 실행해 주세요.\" with title \"${TITLE}\" buttons {\"확인\"} default button \"확인\"" 2>/dev/null || true
  exit 1
fi

# 2) 키 접두사로 프로바이더 추론 → 기본 모델 결정 (씨앗과 동일 규칙)
case "$KEY" in
  sk-ant-*) DEFMODEL="claude-haiku-4-5" ;;
  AIza*)    DEFMODEL="gemini-3.1-flash-lite" ;;
  sk-*)     DEFMODEL="gpt-5-mini" ;;
  *)        DEFMODEL="gemini-3.1-flash-lite" ;;
esac

# 3) 모델 선택 (기본값 채워둠 — 그대로 두고 계속 눌러도 됨)
MODEL="$(osascript <<END 2>/dev/null
text returned of (display dialog "사용할 모델 이름입니다. 그대로 두거나 원하는 모델로 바꾼 뒤 계속을 누르세요." default answer "${DEFMODEL}" with title "${TITLE}" buttons {"취소","계속"} default button "계속" cancel button "취소")
END
)" || _cancelled
MODEL="$(printf '%s' "$MODEL" | tr -d '[:space:]')"
[ -z "$MODEL" ] && MODEL="$DEFMODEL"

# 4) 아키텍처에 맞는 씨앗 바이너리 내려받기 (curl=격리 속성 없음 → Gatekeeper 무경고)
echo "· IndieBiz OS 설치를 시작합니다 (${ARCH})"
echo "· 설치 프로그램 내려받는 중…"
curl -fL --retry 3 -o "$BIN" "$BIN_URL"
chmod +x "$BIN"

# 5) 무인 실행: 키·모델은 환경변수로만, 확인 프롬프트(a) 없음
echo "· 설치 프로그램 실행 (모델: ${MODEL})"
echo
INDIEBIZ_API_KEY="$KEY" INDIEBIZ_MODEL="$MODEL" INDIEBIZ_YES=1 "$BIN" || true

echo
echo "──────────────────────────────────────────"
echo "위 로그를 확인하세요. 이 창은 닫으셔도 됩니다."
# 더블클릭 실행 시 창이 바로 사라지지 않게 잠깐 대기
read -r -n 1 -s -p "아무 키나 누르면 종료합니다…" 2>/dev/null || true
echo
