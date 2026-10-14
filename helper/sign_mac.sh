#!/bin/bash
# 일반 빌드는 --adhoc. 실제 개인키 사용은 사람이 연 터미널의 --interactive만 허용한다.
# 인증서 유효성은 개인키의 무인 사용 권한을 보증하지 않는다.
set -euo pipefail
mode="${1:-}"
case "$mode" in
  --adhoc) shift ;;
  --interactive|--setup-identity|--check-interactive)
    if [ ! -t 0 ] || [ "${INDIEBIZ_REPAIR_CHILD:-}" = 1 ] || [ -n "${PYTEST_CURRENT_TEST:-}" ]; then
      echo "AUTHORIZATION_REQUIRED: 실제 서명·키체인 설정은 일반 시험/자동 수리에서 실행하지 않습니다. 사람이 연 터미널에서 실행하세요. 자동 재시도 금지." >&2
      exit 77
    fi
    [ "$mode" != --check-interactive ] || exit 0
    [ "$mode" = --setup-identity ] || shift
    ;;
  *) echo "사용법: sign_mac.sh --adhoc|--interactive <식별자> <파일>... 또는 --setup-identity" >&2; exit 64 ;;
esac
if [ "$mode" = --adhoc ]; then
  [ "$#" -ge 2 ] || { echo "식별자와 파일이 필요합니다" >&2; exit 64; }
  identifier="$1"; shift
  echo "개발용 ad-hoc 서명: 교체 시 macOS 권한 재승인이 필요할 수 있습니다." >&2
  for f in "$@"; do codesign --force --sign - --identifier "$identifier" "$f"; done
  exit 0
fi
identity="${INDIEBIZ_MAC_SIGN_IDENTITY:-IndieBiz Helper Signing}"
keychain="${INDIEBIZ_MAC_SIGN_KEYCHAIN:-$HOME/Library/Keychains/login.keychain-db}"

has_identity() {  # 키체인에 인증서와 개인키가 있다(신뢰 여부 무관)
  security find-identity -p codesigning "$keychain" | grep -F "\"$identity\"" >/dev/null
}
usable_identity() {  # 인증서 신뢰만 확인한다. 개인키 접근 승인과는 별개다
  security find-identity -v -p codesigning "$keychain" | grep -F "\"$identity\"" >/dev/null
}
here="$(cd "$(dirname "$0")" && pwd)"

if [ "${1:-}" = "--setup-identity" ]; then
  if usable_identity; then echo "이미 있다: '$identity' ($keychain)"; exit 0; fi
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/indiebiz-sign.XXXXXX")"
  trap 'rm -rf "$tmp"' EXIT
  if ! has_identity; then
  # macOS 기본 LibreSSL 은 security import 가 읽는 PKCS#12 를 만든다(OpenSSL 3 기본값은 못 읽는다).
  /usr/bin/openssl req -x509 -newkey rsa:2048 -nodes -days 7300 -subj "/CN=$identity" \
    -keyout "$tmp/key.pem" -out "$tmp/cert.pem" \
    -addext "keyUsage=critical,digitalSignature" -addext "extendedKeyUsage=critical,codeSigning" \
    -addext "basicConstraints=critical,CA:false" 2>/dev/null
  pass="$(/usr/bin/openssl rand -hex 16)"
  /usr/bin/openssl pkcs12 -export -inkey "$tmp/key.pem" -in "$tmp/cert.pem" -name "$identity" \
    -out "$tmp/id.p12" -passout "pass:$pass"
  security import "$tmp/id.p12" -k "$keychain" -P "$pass" -T /usr/bin/codesign >/dev/null
  has_identity || { echo "코드서명 인증서 '$identity' 를 키체인에 넣지 못했다" >&2; exit 1; }
  fi
  # 코드서명 신뢰 설정이다. 개인키 접근 승인은 별도이며 횟수를 보장할 수 없다.
  security find-certificate -c "$identity" -p "$keychain" > "$tmp/trust.pem"
  security add-trusted-cert -r trustRoot -p codeSign -k "$keychain" "$tmp/trust.pem"
  usable_identity || { echo "'$identity' 의 코드서명 신뢰 설정을 확인하지 못했다" >&2; exit 1; }
  echo "만들었다: '$identity' ($keychain) — 이 인증서로 처음 서명한 헬퍼는 각 맥에서 권한을 한 번 다시 등록해야 한다"
  exit 0
fi

[ "$#" -ge 2 ] || { echo "식별자와 파일이 필요합니다" >&2; exit 64; }
identifier="$1"; shift
if ! usable_identity; then
  echo "코드서명 인증서 '$identity' 가 없거나 신뢰되지 않습니다. 터미널에서 bash $here/sign_mac.sh --setup-identity 를 확인하세요. 자동 재시도 금지." >&2
  exit 77
fi

for f in "$@"; do
  codesign --force --sign "$identity" --keychain "$keychain" --identifier "$identifier" --timestamp=none "$f"
  # cdhash 요구사항으로 떨어졌으면 권한이 또 끊기므로 빌드를 실패시킨다.
  req="$(codesign -d -r- "$f" 2>&1)"
  case "$req" in
    *"identifier \"$identifier\" and certificate leaf"*) ;;
    *) echo "서명 요구사항이 식별자·인증서 기반이 아니다: $f"$'\n'"$req" >&2; exit 1 ;;
  esac
done
