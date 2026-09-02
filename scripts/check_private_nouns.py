#!/usr/bin/env python3
"""check_private_nouns.py — 개인 명사 관문 (pre-commit, 2026-09-02).

가족·개인의 이름과 목소리 키가 몸(코드·어휘·가이드·문서·픽스처)에 박히면 그 몸은 빈 몸이
아니라 한 가족 전용 프로그램이 된다(헌법: 몸의 명사=코드, 세계의 명사=데이터). 이 관문은
커밋에 들어가는 파일을 **로컬 전용 목록**과 대조해 실패시킨다.

목록: data/private_nouns.txt (★gitignore — 이름 자체가 저장소에 들어오지 않는 구조)
  한 줄 = 정규식(대소문자 무시). `#` 주석. `allow: <glob>` = 면제 경로(저자 서명·연구 기록처럼
  개작이 위조가 되는 문서).

사용:
    check_private_nouns.py            # 스테이지된 파일(인덱스 내용) 검사 — pre-commit
    check_private_nouns.py --all      # 추적 파일 전부 — 스윕 착수 전 전수 목록
    check_private_nouns.py --files A B  # 지정 파일(작업 트리)
    옵션 --list PATH : 목록 파일 지정(시험용)

목록이 없으면 검사를 *보이게* 건너뛴다(0) — 다른 몸(새 설치)엔 보호할 이름이 없다. 목록이
있는데 못 읽으면 실패(1) — 조용히 사라지는 관문은 주석이다.
"""
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIST = REPO_ROOT / "data" / "private_nouns.txt"
_PROBE = 8192


def load_list(path: Path):
    """(패턴 목록, 면제 글롭 목록). 패턴은 compile 된 정규식."""
    pats, allows = [], []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.lower().startswith("allow:"):
            allows.append(s.split(":", 1)[1].strip())
            continue
        pats.append(re.compile(s, re.IGNORECASE))
    return pats, allows


def _is_binary(data: bytes) -> bool:
    return b"\0" in data[:_PROBE]


def _staged_files():
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    return [l for l in out.splitlines() if l.strip()]


def _tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [l for l in out.splitlines() if l.strip()]


def _read(rel: str, staged: bool) -> bytes:
    if staged:
        r = subprocess.run(["git", "show", f":{rel}"], cwd=REPO_ROOT, capture_output=True)
        return r.stdout if r.returncode == 0 else b""
    try:
        return (REPO_ROOT / rel).read_bytes()
    except OSError:
        return b""


def scan(files, pats, allows, *, staged: bool, list_path: Path):
    """[(path, lineno, 매치 문자열)]"""
    hits = []
    try:
        list_rel = str(list_path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        list_rel = None
    for rel in files:
        if rel == list_rel or any(fnmatch.fnmatch(rel, g) for g in allows):
            continue
        data = _read(rel, staged)
        if not data or _is_binary(data):
            continue
        text = data.decode("utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            for p in pats:
                m = p.search(line)
                if m:
                    hits.append((rel, n, m.group(0)))
                    break
    return hits


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    list_path = DEFAULT_LIST
    if "--list" in argv:
        i = argv.index("--list")
        list_path = Path(argv[i + 1])
        del argv[i:i + 2]
    if not list_path.exists():
        print(f"[private-nouns] {list_path.name} 없음 — 검사 생략 (개인 명사 목록은 이 몸의 로컬 데이터)")
        return 0
    try:
        pats, allows = load_list(list_path)
    except Exception as e:  # 목록이 있는데 못 읽음 = 검사 불능 = 실패
        print(f"[private-nouns] ✗ 목록을 읽지 못함: {e}")
        return 1
    if "--files" in argv:
        files = argv[argv.index("--files") + 1:]
        staged = False
    elif "--all" in argv:
        files, staged = _tracked_files(), False
    else:
        files, staged = _staged_files(), True
    hits = scan(files, pats, allows, staged=staged, list_path=list_path)
    if hits:
        print(f"[private-nouns] ✗ 개인 명사 {len(hits)}건 — 몸에 개인이 박혔다:")
        for rel, n, tok in hits:
            print(f"  {rel}:{n}: {tok}")
        return 1
    print(f"[private-nouns] ✓ 개인 명사 0건 ({len(files)}파일, 패턴 {len(pats)}·면제 {len(allows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
