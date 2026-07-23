#!/usr/bin/env bash
# 손발 헬퍼 크로스컴파일 — 런타임 없는 단일 실행파일 3종(win/mac/linux).
# 산출물은 dist/ 에. 발급기([self:limb]{op:issue})가 이 중 대상 OS 것을 USB 에 복사한다.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p dist

echo "▶ windows/amd64"
GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o dist/indiebiz-helper-win.exe .
echo "▶ darwin/arm64"
GOOS=darwin GOARCH=arm64 go build -ldflags="-s -w" -o dist/indiebiz-helper-mac-arm64 .
echo "▶ darwin/amd64"
GOOS=darwin GOARCH=amd64 go build -ldflags="-s -w" -o dist/indiebiz-helper-mac-amd64 .
echo "▶ linux/amd64"
GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o dist/indiebiz-helper-linux .

echo "완료 — dist/:"
ls -lh dist/
