#!/usr/bin/env python3
"""data.go.kr 신청 링크 커버리지 검사 — "키는 맞는데 403" 에 링크 없는 안내 차단.

공공데이터포털은 인증키가 계정당 하나지만 권한은 데이터셋마다 따로 '활용신청'으로
열린다. 그래서 이 포털을 부르는 코드의 기본 실패는 403 이고, 그때 사람에게 필요한
것은 포털 첫 화면이 아니라 **그 데이터셋의 신청 페이지**다.

옛 모양(2026-08-30 수리 전): 설정 'API 키' 탭은 MOLIT 키에 데이터셋 하나(아파트 매매
상세)를 가리키는 링크 한 개만 달고 있었고 — 빌라를 조회하다 403 을 만난 사람에게는
아무 쓸모가 없었다 — 도구들의 403 문구는 데이터셋 이름을 각자 손으로 적고 링크는
없었다. 두 자리가 같은 사실을 따로 들고 있으니 한쪽만 고쳐졌다.

이 가드가 고정하는 불변식: **코드가 부르는 data.go.kr 엔드포인트는 전부
common/datagokr_catalog.py 에 신청 링크를 갖는다.** 사람이 고른 grep 범위로 훑지 않고
엔드포인트 모양(`/<7자리 기관코드 또는 B######>/<서비스명>`)으로 전수한다.

사용: python3 scripts/check_datagokr_signup.py            # 저장소 검사
      python3 scripts/check_datagokr_signup.py --self-test # 가드 자기 검증
의존성 0 (stdlib만). 실패 시 exit 1.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# data.go.kr 서비스 경로의 모양: 기관코드(7자리 숫자 또는 B+6자리) + 서비스명.
_ENDPOINT_RE = re.compile(r"/((?:B\d{6}|\d{7})/[A-Za-z0-9_]+)")

SCAN_ROOTS = ("backend", "data/packages/installed", "scripts")
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "_backups"}

# 정본(카탈로그)과 이 가드 자신은 제외 — 전자는 등록부 그 자체이고, 후자의 엔드포인트
# 문자열은 self-test 픽스처다(가드가 자기 픽스처를 위반으로 신고하지 않게).
SELF = {
    os.path.join("backend", "common", "datagokr_catalog.py"),
    os.path.join("scripts", "check_datagokr_signup.py"),
}


def catalog_paths(root: str) -> list:
    sys.path.insert(0, os.path.join(root, "backend"))
    try:
        from common.datagokr_catalog import DATASETS  # noqa: E402
    finally:
        sys.path.pop(0)
    return [d["path"] for d in DATASETS]


def _covered(path: str, known: list) -> bool:
    """세그먼트 경계에서 한쪽이 다른 쪽의 접두사면 같은 데이터셋.

    양방향인 이유: 정규식은 두 세그먼트만 걷어오는데(`/B553077/api`) 카탈로그는
    데이터셋을 특정하는 만큼 더 길 수 있다(`/B553077/api/open/sdsc2`).
    """
    found = "/" + path
    for p in known:
        short, long = (found, p) if len(found) <= len(p) else (p, found)
        if long == short or long.startswith(short + "/"):
            return True
    return False


def scan(root: str, known: list) -> list:
    issues = []
    for sub in SCAN_ROOTS:
        base = os.path.join(root, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root)
                if rel in SELF:
                    continue
                try:
                    text = open(full, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                if "data.go.kr" not in text:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    for m in _ENDPOINT_RE.finditer(line):
                        ep = m.group(1)
                        if not _covered(ep, known):
                            issues.append(f"{rel}:{i}: /{ep} — 카탈로그 미등록")
    return sorted(set(issues))


def self_test() -> bool:
    import tempfile
    ok = True
    known = ["/1613000/RTMSDataSvcRHRent"]
    with tempfile.TemporaryDirectory() as tmp:
        pkg = os.path.join(tmp, "backend")
        os.makedirs(pkg)
        # 등록된 엔드포인트 = 통과
        with open(os.path.join(pkg, "good.py"), "w") as f:
            f.write("U='https://apis.data.go.kr/1613000/RTMSDataSvcRHRent/getRTMSDataSvcRHRent'\n")
        # 미등록 엔드포인트 = 적발
        with open(os.path.join(pkg, "bad.py"), "w") as f:
            f.write("U='https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent'\n")
        # 경로 조각만 있어도 적발 (api_client 처럼 base 와 path 를 나눠 쓰는 자리)
        with open(os.path.join(pkg, "bad2.py"), "w") as f:
            f.write("# data.go.kr\nEP='/B552735/kisedKstartupService01/getAnnouncementInformation01'\n")
        # data.go.kr 과 무관한 숫자 경로 = 무시
        with open(os.path.join(pkg, "unrelated.py"), "w") as f:
            f.write("U='https://example.com/1234567/whatever'\n")
        hits = {i.split(": ")[1].split(" ")[0] for i in scan(tmp, known)}
        expect = {"/1613000/RTMSDataSvcAptRent", "/B552735/kisedKstartupService01"}
        if hits != expect:
            print(f"✗ self-test: 기대 {expect} vs 실제 {hits}")
            ok = False
    print("✓ self-test 통과" if ok else "✗ self-test 실패")
    return ok


def main() -> int:
    if "--self-test" in sys.argv:
        return 0 if self_test() else 1
    issues = scan(ROOT, catalog_paths(ROOT))
    if issues:
        print(f"✗ data.go.kr 신청 링크 미등록 {len(issues)}건:")
        for i in issues:
            print(f"  - {i}")
        print("\n수리: backend/common/datagokr_catalog.py 의 DATASETS 에 "
              "{path, env_var, label, id} 한 줄 추가 "
              "(id = data.go.kr/data/<id>/openapi.do 의 숫자).")
        return 1
    print("✓ data.go.kr 엔드포인트 전부 신청 링크 보유")
    return 0


if __name__ == "__main__":
    sys.exit(main())
