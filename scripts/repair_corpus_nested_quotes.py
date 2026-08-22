#!/usr/bin/env python3
"""코퍼스 중첩 IBL 따옴표 수리 (2026-08-22)

증상: `[self:schedule]{..., pipeline: "[limbs:music]{op: "play", ...}"}` 처럼
중첩 IBL 을 값으로 실은 예제가 안쪽 따옴표를 이스케이프하지 않았다.

이 모양은 **한 번도 동작한 적이 없다.** 수리 전 파서는 조용히 잘라서
pipeline='[limbs:music]{op: ' 을 돌려줬고(침묵 절단), 코퍼스는 그 깨진 모양을
3개월간 교재로 가르쳤다. 파서 수리로 이제 IBLSyntaxError 가 나므로 드러났다.

정본 모양은 코퍼스 자신에게 이미 있다(정상 4건):
    pipeline: "[self:notify_user]{message: \\"알림 내용\\", title: \\"리마인더\\"}"

수리 대상: data/training/*.json + 라이브 코퍼스 data/ibl_usage.db (트레이너가 둘 다 읽는다).
추측하지 않는다 — 이 스크립트가 고치는 것은 "안쪽 따옴표 이스케이프" 하나뿐이고,
고친 뒤 ①바깥이 파싱되고 ②pipeline 값이 그 자체로 유효한 IBL 인 것을 둘 다
확인한 항목만 기록한다. 하나라도 실패하면 그 항목은 손대지 않고 보고만 한다.

실행: python3 scripts/repair_corpus_nested_quotes.py [--apply]
"""
import argparse
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: F401,E402

from ibl_parser import parse, IBLSyntaxError  # noqa: E402

NEEDLE = 'pipeline: "'


def _parses(code: str) -> bool:
    try:
        parse(code)
        return True
    except IBLSyntaxError:
        return False
    except Exception:
        return True  # 이 스크립트의 관할 밖(다른 부류) — 손대지 않는다


def repair(code: str):
    """(고친 코드, 사유) 또는 (None, 사유). 안전하지 않으면 None."""
    if _parses(code):
        return None, "이미 정상"
    if NEEDLE not in code:
        return None, "pipeline 중첩 모양이 아님 — 손대지 않음"
    if not code.rstrip().endswith('"}'):
        return None, "pipeline 뒤에 다른 파라미터가 있음 — 손대지 않음"

    i = code.index(NEEDLE) + len(NEEDLE)
    j = code.rindex('"')
    inner = code[i:j]
    # 이스케이프 정규화: 이미 escape 된 것을 되돌린 뒤 일괄 escape (중복 방지)
    fixed = inner.replace('\\"', '"').replace('"', '\\"')
    out = code[:i] + fixed + code[j:]

    if not _parses(out):
        return None, "수리 후에도 파싱 실패 — 손대지 않음"
    # 중첩된 pipeline 값 자체가 유효한 IBL 인가
    try:
        nested = parse(out)[0]["params"]["pipeline"]
        parse(nested)
    except Exception as e:
        return None, "pipeline 값이 유효한 IBL 이 아님(%s) — 손대지 않음" % type(e).__name__
    return out, "수리"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다 (기본은 예행)")
    args = ap.parse_args()

    fixed_n = skipped = 0

    # 1) 학습 파일
    for path in sorted((ROOT / "data" / "training").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        xs = raw if isinstance(raw, list) else raw.get("examples")
        if not isinstance(xs, list):
            continue
        touched = 0
        for x in xs:
            if not isinstance(x, dict) or "ibl_code" not in x:
                continue
            out, why = repair(x["ibl_code"])
            if out:
                x["ibl_code"] = out
                touched += 1
            elif why not in ("이미 정상", "pipeline 중첩 모양이 아님 — 손대지 않음"):
                skipped += 1
                print("  ⊘ %s: %s :: %s" % (path.name, x.get("intent", "")[:40], why))
        if touched:
            fixed_n += touched
            print("  ✎ %s: %d건" % (path.name, touched))
            if args.apply:
                path.write_text(
                    json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )

    # 2) 라이브 코퍼스 DB
    db = ROOT / "data" / "ibl_usage.db"
    if db.exists():
        con = sqlite3.connect(str(db))
        rows = con.execute("SELECT id, intent, ibl_code FROM ibl_examples").fetchall()
        updates = []
        for rid, intent, code in rows:
            out, why = repair(code or "")
            if out:
                updates.append((out, rid))
            elif why not in ("이미 정상", "pipeline 중첩 모양이 아님 — 손대지 않음"):
                skipped += 1
                print("  ⊘ ibl_usage.db#%s: %s :: %s" % (rid, (intent or "")[:40], why))
        if updates:
            fixed_n += len(updates)
            print("  ✎ ibl_usage.db: %d건" % len(updates))
            if args.apply:
                con.executemany(
                    "UPDATE ibl_examples SET ibl_code=?, updated_at=datetime('now') WHERE id=?",
                    updates,
                )
                con.commit()
        con.close()

    print("\n%s — 수리 %d건 / 손대지 않음 %d건"
          % ("적용됨" if args.apply else "예행(--apply 로 실제 적용)", fixed_n, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
