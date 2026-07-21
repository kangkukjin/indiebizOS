#!/usr/bin/env python3
"""audit_bundle_secrets.py — 빌드 산출물에 개인 데이터·비밀이 섞였는지 검사하는 게이트.

배경: 배포 패키지는 `../data`·`../backend` 등을 번들한다(frontend/package.json extraResources).
개발 머신에서 로컬 빌드하면 gitignore된 개인 파일(OAuth 토큰·Nostr 개인키·gmail 자격증명·
business.db·대화 이력…)이 디스크에 있어 번들에 섞일 수 있다. extraResources 필터가 1차로
막지만, 필터는 파일명을 손으로 나열하는 denylist라 새 비밀 파일을 놓칠 수 있다. 이 스크립트는
*실제 산출물*을 스캔해 고신뢰 비밀이 발견되면 **빌드를 실패**시킨다(침묵 유출 방지 — 최후 방어).

사용:
    python scripts/audit_bundle_secrets.py <빌드 산출물 루트>
    # 예: python scripts/audit_bundle_secrets.py frontend/release

동작: 루트 아래에서 *우리가 번들하는 디렉토리*(backend/data/templates/projects/tokens)에
속한 파일만 검사한다. 번들 런타임(python/node/site-packages/*.asar 등 — certifi cacert.pem 등
정상 인증서 포함)은 스캔에서 제외해 오탐을 막는다. 발견 0건이면 exit 0, 있으면 목록 출력 후 exit 1.
표준 라이브러리만 사용(어느 몸·CI 러너에서든 동작).
"""
import os
import re
import sys

# ★Windows CI 등 비-UTF-8 로케일(cp1252/cp949)에서 한글 출력이 UnicodeEncodeError 로
# 죽지 않도록 stdout/stderr 를 UTF-8 로 고정한다(이 스크립트가 바로 그 이식성 버그로
# 빌드를 깨뜨렸다 — strftime 과 같은 부류: 개발 맥은 UTF-8이라 재현 안 됨).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 우리가 번들하는 디렉토리 세그먼트(경로에 이게 있어야 검사). 그 외(런타임)는 스킵.
BUNDLE_SEGMENTS = ("backend", "data", "templates", "projects", "tokens")
# 스캔 제외 세그먼트 — 번들 런타임/서드파티(정상 인증서·테스트 키가 있어 오탐 유발).
SKIP_SEGMENTS = (
    "python", "runtime", "node", "node_modules", "site-packages",
    "dist-packages", "__pycache__", "chrome-sandbox",
)
SKIP_EXT_BINARY = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".icns", ".pdf",
    ".zip", ".gz", ".7z", ".dmg", ".exe", ".dll", ".so", ".dylib", ".node",
    ".woff", ".woff2", ".ttf", ".mp4", ".mp3", ".wav", ".blockmap", ".asar",
    ".model", ".bin", ".pt", ".onnx", ".safetensors",
}
MAX_CONTENT_BYTES = 3_000_000  # 이보다 큰 파일은 내용 스캔 생략(대용량 모델·DB 등)

# 내용 기반 고신뢰 비밀 패턴 (코드의 접두어 문자열이 아니라 *실제 값*을 잡도록 구체적).
CONTENT_PATTERNS = [
    (re.compile(rb"sk-ant-(?:oat|api)\d{2}-[A-Za-z0-9_\-]{20,}"), "Anthropic 토큰(sk-ant-*)"),
    (re.compile(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"), "PEM 개인키"),
    (re.compile(rb"\bnsec1[a-z0-9]{50,}\b"), "Nostr 개인키(nsec1…)"),
    (re.compile(rb"AIza[0-9A-Za-z_\-]{30,}"), "Google API 키(AIza…)"),
    (re.compile(rb"xox[baprs]-[0-9A-Za-z\-]{10,}"), "Slack 토큰(xox*)"),
]

# 파일명 기반(이름만으로 비밀/개인 확정). basename 소문자 비교.
# ★2026-07-21 보강: 이 감사는 "고신뢰 비밀 값"(토큰·개인키) 위주라, 값에 비밀 패턴이 없는
#   *신원·명부* 파일은 통과시켰다(showcase_state.json=창고 주소, portal_state.json=회원
#   비밀번호 해시·발급 키, dms.db=DM 캐시). 새 몸이 물려받으면 안 되는 것들이라 이름으로 막는다.
#   dist 필터(build_dist_filter.PERSONAL_STATE_PATTERNS)가 1차, 여기가 최후 방어선.
NAME_EXACT = {".env", "nostr_keys", "business.db", "my_profile.txt",
              "multi_chat.db", "conversations.db", "conversation.db", "device_id.txt",
              # 몸 전속 신원 — 주소는 몸마다 달라야 한다
              "showcase_state.json", "public_face.json", "warehouse.json",
              "warehouse_feed.db", "device_registry.json",
              # 개인 명부·대화·기억
              "portal_state.json", "dms.db"}
NAME_GLOBS = ["credentials*.json", "*credential*.json", "*.pem", "*.key",
              "forage_*.db"]
# 디렉토리 이름만으로 개인/비밀 확정 — 통째로 잡는다(nostr_keys 와 같은 처리).
DIR_EXACT = {"nostr_keys", "tokens"}


def _fnmatch(name, pat):
    import fnmatch
    return fnmatch.fnmatch(name, pat)


def _in_bundle(path_parts):
    """이 경로가 우리가 번들하는 디렉토리에 속하고, 런타임 제외 세그먼트가 아닌가."""
    lower = [p.lower() for p in path_parts]
    if any(seg in lower for seg in SKIP_SEGMENTS):
        return False
    return any(seg in lower for seg in BUNDLE_SEGMENTS)


def audit(root):
    findings = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        parts = dirpath.replace("\\", "/").split("/")
        # 런타임 디렉토리는 통째로 가지치기(성능+오탐 방지)
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_SEGMENTS]
        # nostr_keys·tokens 가 디렉토리로 존재하는 경우도 잡는다
        # (★tokens: dist 필터의 `!tokens/**` 가 data/ 최상위만 매칭해서
        #  packages/installed/extensions/gmail/tokens/ 의 OAuth 토큰이 새어나간 적 있음)
        for d in list(dirnames):
            if d.lower() in DIR_EXACT and _in_bundle(parts + [d]):
                findings.append((os.path.join(dirpath, d), f"파일명: {d}(디렉토리)"))
        if not _in_bundle(parts):
            continue
        for fn in filenames:
            fpath = os.path.join(dirpath, fn)
            low = fn.lower()
            # 1) 파일명 기반
            if low in NAME_EXACT:
                findings.append((fpath, f"파일명: {fn}"))
                continue
            if any(_fnmatch(low, g) for g in NAME_GLOBS):
                findings.append((fpath, f"파일명 패턴: {fn}"))
                continue
            # 2) 내용 기반(텍스트·소용량만)
            ext = os.path.splitext(low)[1]
            if ext in SKIP_EXT_BINARY:
                continue
            try:
                if os.path.getsize(fpath) > MAX_CONTENT_BYTES:
                    continue
                with open(fpath, "rb") as f:
                    blob = f.read()
            except OSError:
                continue
            scanned += 1
            for rx, label in CONTENT_PATTERNS:
                if rx.search(blob):
                    findings.append((fpath, f"내용: {label}"))
                    break
    return findings, scanned


def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/audit_bundle_secrets.py <빌드 산출물 루트>", file=sys.stderr)
        return 2
    root = sys.argv[1]
    if not os.path.isdir(root):
        print(f"[audit] 경로 없음: {root}", file=sys.stderr)
        return 2

    findings, scanned = audit(root)
    print(f"[audit] 스캔: 번들 파일 {scanned}개 (런타임 제외)  루트={root}")
    if not findings:
        print("[audit] ✅ 개인 데이터·비밀 미발견 — 번들 안전")
        return 0

    print(f"[audit] ❌ 개인 데이터/비밀 {len(findings)}건 발견 — 배포 차단:", file=sys.stderr)
    for path, why in findings:
        print(f"  - {why}\n      {path}", file=sys.stderr)
    print(
        "\n[audit] extraResources/build-windows.ps1 필터를 보강하거나 해당 파일을 빌드 소스에서 "
        "제거하세요. (오탐이면 이 스크립트의 패턴을 조정)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
