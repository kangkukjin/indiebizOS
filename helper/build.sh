#!/usr/bin/env bash
# 손발 헬퍼 크로스컴파일 — 런타임 없는 단일 실행파일 3종(win/mac/linux).
# 산출물은 dist/ 에. 발급기([self:limb]{op:issue})가 이 중 대상 OS 것을 USB 에 복사한다.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p dist
python3 ../scripts/build_member_shell.py

echo "▶ windows/amd64"
GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o dist/indiebiz-helper-win.exe .
echo "▶ darwin/arm64"
GOOS=darwin GOARCH=arm64 go build -ldflags="-s -w" -o dist/indiebiz-helper-mac-arm64 .
echo "▶ darwin/amd64"
GOOS=darwin GOARCH=amd64 go build -ldflags="-s -w" -o dist/indiebiz-helper-mac-amd64 .
# 구형 인텔 맥(macOS 10.15~11)용 — Go 1.25+ 산출물은 최소 macOS 12 라 Catalina 에서
# dyld 'Symbol not found: _SecTrustCopyCertificateChain' 으로 꺼진다. 10.15 를 지원하는
# 마지막 툴체인(Go 1.22)과 그것이 받는 의존성(go.legacy.mod)으로 따로 굽는다.
# GOTOOLCHAIN 이 1.22.12 를 모듈 캐시에 자동으로 받는다(전역 go 교체 없음).
echo "▶ darwin/amd64 legacy (macOS 10.15+, Go 1.22)"
GOTOOLCHAIN=go1.22.12 GOOS=darwin GOARCH=amd64 go build -modfile=go.legacy.mod -ldflags="-s -w" -o dist/indiebiz-helper-mac-amd64-legacy .
echo "▶ linux/amd64"
GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o dist/indiebiz-helper-linux .

echo "완료 — dist/:"
ls -lh dist/
