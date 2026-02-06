#!/bin/bash
# 터널 테스트 스크립트 - indiebizOS와 무관하게 cloudflared 직접 실행

echo "=== Cloudflare Tunnel 테스트 ==="
echo ""

# 1. cloudflared 찾기
CLOUDFLARED=""
for path in /opt/homebrew/bin/cloudflared /usr/local/bin/cloudflared /usr/bin/cloudflared cloudflared; do
    if command -v "$path" &>/dev/null; then
        CLOUDFLARED="$path"
        break
    fi
done

if [ -z "$CLOUDFLARED" ]; then
    echo "[FAIL] cloudflared가 설치되어 있지 않습니다."
    echo "  설치: brew install cloudflared"
    exit 1
fi

echo "[OK] cloudflared 경로: $CLOUDFLARED"
$CLOUDFLARED --version
echo ""

# 2. 인증 상태 확인
echo "=== 인증 상태 ==="
CRED_DIR="$HOME/.cloudflared"
if [ -d "$CRED_DIR" ]; then
    echo "[OK] $CRED_DIR 디렉토리 존재"
    echo "  내용:"
    ls -la "$CRED_DIR/" 2>/dev/null
else
    echo "[FAIL] $CRED_DIR 디렉토리 없음"
    echo "  먼저 로그인하세요: cloudflared tunnel login"
    exit 1
fi
echo ""

# 3. 터널 목록 확인
echo "=== 등록된 터널 목록 ==="
$CLOUDFLARED tunnel list 2>&1
echo ""

# 4. config.yml 확인
echo "=== config.yml 확인 ==="
CONFIG="$HOME/.cloudflared/config.yml"
if [ -f "$CONFIG" ]; then
    echo "[OK] $CONFIG 존재"
    echo "--- 내용 ---"
    cat "$CONFIG"
    echo "--- 끝 ---"
else
    echo "[WARN] $CONFIG 없음 (터널 이름으로 직접 실행 시도)"
fi
echo ""

# 5. 터널 실행 시도
TUNNEL_NAME="${1:-indiebiz-os}"
echo "=== 터널 '$TUNNEL_NAME' 실행 시도 ==="
echo "명령어: $CLOUDFLARED tunnel run $TUNNEL_NAME"
echo "(5초 후 자동 종료됩니다)"
echo ""

# 5초 타임아웃으로 실행 (macOS에는 timeout이 없으므로 백그라운드+sleep 사용)
$CLOUDFLARED tunnel run "$TUNNEL_NAME" 2>&1 &
TUNNEL_PID=$!
sleep 5
if kill -0 $TUNNEL_PID 2>/dev/null; then
    echo ""
    echo "=== 결과 ==="
    echo "[OK] 터널이 5초간 정상 실행됨 (성공!)"
    kill $TUNNEL_PID 2>/dev/null
    wait $TUNNEL_PID 2>/dev/null
else
    wait $TUNNEL_PID 2>/dev/null
    EXIT_CODE=$?
    echo ""
    echo "=== 결과 ==="
    echo "[FAIL] 터널이 5초 안에 종료됨 (exit code: $EXIT_CODE)"
fi
