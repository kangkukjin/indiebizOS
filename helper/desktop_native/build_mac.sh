#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
sign_mode="${1:---adhoc}"
case "$sign_mode" in
  --adhoc) ;;
  --interactive) bash sign_mac.sh --check-interactive ;;
  *) echo "사용법: build_mac.sh [--adhoc|--interactive]" >&2; exit 64 ;;
esac
[ "$#" -le 1 ] || exit 64
mkdir -p desktop_native/bin
for arch in arm64 x86_64; do
  minimum=11.0
  test "$arch" != x86_64 || minimum=10.15
  output="desktop_native/bin/mac-$arch"
  pending="$(mktemp "$output.XXXXXX")"
  trap 'rm -f "$pending"' EXIT
  clang -arch "$arch" -mmacosx-version-min="$minimum" -O2 -fobjc-arc -Wno-deprecated-declarations -framework AppKit -framework ApplicationServices desktop_native/mac.m -o "$pending"
  bash sign_mac.sh "$sign_mode" com.indiebiz.screen "$pending"
  mv "$pending" "$output"
  trap - EXIT
done
