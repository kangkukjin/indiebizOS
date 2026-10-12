#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p desktop_native/bin
for arch in arm64 x86_64; do
  minimum=11.0
  test "$arch" != x86_64 || minimum=10.15
  clang -arch "$arch" -mmacosx-version-min="$minimum" -O2 -fobjc-arc -Wno-deprecated-declarations -framework AppKit -framework ApplicationServices desktop_native/mac.m -o "desktop_native/bin/mac-$arch"
  codesign --force --sign - --identifier com.indiebiz.screen "desktop_native/bin/mac-$arch"
done
