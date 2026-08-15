#!/usr/bin/env python3
"""check_playwright_browsers.py — playwright 브라우저 주소 정합 점검(+설치).

무엇을 보는가: **지금 이 인터프리터에 설치된 playwright 가 기대하는 빌드**가
**백엔드가 실제로 보는 주소**(runtime_utils.get_playwright_browsers_path)에 있는가.

왜 필요한가 (2026-08-15 실측): playwright 를 올리면 브라우저 빌드 번호가 바뀐다
(1228 → 1234). 그때 `playwright install` 을 PLAYWRIGHT_BROWSERS_PATH 없이 돌리면
브라우저는 기본 캐시(~/Library/Caches/ms-playwright)로 가는데 백엔드는 저장소 안
ms-playwright/ 를 보고 있어 어긋난다. 증상이 조용한 게 최악이다 — 평시엔 아무 신호가
없다가 슬라이드 렌더·강의 영상·글자 얹기·browser-action 이 *쓸 때* 처음 터진다.
그래서 (1) 설치를 조리법(bootstrap.py)의 일부로 묶고 (2) 어긋남을 12시간
자가점검이 신고한다. 둘 다 이 스크립트를 부른다 — 검사기가 하나여야 갈라지지 않는다.

사용:
  python scripts/check_playwright_browsers.py             # 점검만 (어긋나면 rc 1)
  python scripts/check_playwright_browsers.py --install    # 없으면 올바른 주소로 받는다
  python scripts/check_playwright_browsers.py --with-deps  # (리눅스 CI) OS 의존성까지
  python scripts/check_playwright_browsers.py --json       # 요약 JSON 만

종료코드: 0=정합 / 1=어긋남(빌드 없음) / 2=점검 자체 실패
마지막 줄에 항상 '@@PLAYWRIGHT_BROWSERS_JSON@@ {…}' 요약 마커를 찍는다
(자가점검이 이 계약으로 읽는다 — check_import_coverage.py 의 @@…_JSON@@ 과 동형).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "base"))

MARKER = "@@PLAYWRIGHT_BROWSERS_JSON@@"


def main() -> int:
    ap = argparse.ArgumentParser(description="playwright 브라우저 주소 정합 점검")
    ap.add_argument("--install", action="store_true",
                    help="기대 빌드가 없으면 올바른 주소로 받는다 (있으면 즉시 통과 — 멱등)")
    ap.add_argument("--with-deps", action="store_true",
                    help="--install 시 OS 의존성까지 (리눅스 CI. sudo 필요)")
    ap.add_argument("--json", action="store_true", help="사람용 출력 없이 요약 마커만")
    args = ap.parse_args()

    def emit(summary: dict, rc: int) -> int:
        print(f"{MARKER} {json.dumps(summary, ensure_ascii=False)}")
        return rc

    try:
        from runtime_utils import check_playwright_browsers, get_playwright_browsers_path
    except Exception as e:
        return emit({"ok": False, "status": "error",
                     "note": f"runtime_utils import 실패: {e}"}, 2)

    res = check_playwright_browsers()

    if res["status"] == "missing" and args.install:
        browsers = str(get_playwright_browsers_path())
        Path(browsers).mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["PLAYWRIGHT_BROWSERS_PATH"] = browsers   # ★설치와 실행이 같은 주소를 보게 하는 지점
        cmd = [sys.executable, "-m", "playwright", "install"]
        if args.with_deps:
            cmd.append("--with-deps")
        cmd.append("chromium")
        if not args.json:
            print(f"  브라우저 다운로드 → {browsers}\n  $ {' '.join(cmd)}", flush=True)
        try:
            proc = subprocess.run(cmd, env=env, timeout=1800)
        except Exception as e:
            return emit({**res, "ok": False, "status": "install_failed",
                         "note": f"playwright install 실행 실패: {e}"}, 2)
        if proc.returncode != 0:
            return emit({**res, "ok": False, "status": "install_failed",
                         "note": f"playwright install rc={proc.returncode}"}, 1)
        res = check_playwright_browsers()   # 받은 뒤 같은 눈으로 재확인

    summary = {"ok": bool(res["ok"]), "status": res["status"],
               "browsers_path": res["browsers_path"],
               "playwright_version": res["playwright_version"],
               "missing": res["missing"], "stale": res["stale"], "note": res["note"]}

    if not args.json:
        print(f"playwright {res['playwright_version'] or '(미설치)'} / 주소 {res['browsers_path']}")
        for e in res["expected"]:
            print(f"  {'✓' if e['present'] else '✗'} {e['name']}-{e['revision']}")
        if res["stale"]:
            # 삭제는 사용자 결정 — 여기서는 알리기만 한다(백업 규약).
            print(f"  ℹ 옛 빌드 {len(res['stale'])}개(정리 후보): "
                  + ", ".join(Path(p).name for p in res["stale"]))
        if res["note"]:
            print(f"  {'⚠' if not res['ok'] else 'ℹ'} {res['note']}")

    if res["status"] == "error":
        return emit(summary, 2)
    return emit(summary, 0 if res["ok"] else 1)


if __name__ == "__main__":
    sys.exit(main())
