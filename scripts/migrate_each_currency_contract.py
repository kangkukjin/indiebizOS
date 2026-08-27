#!/usr/bin/env python3
"""migrate_each_currency_contract.py — 옛 `each >> flatten` 을 코퍼스에서 걷어낸다.  (retired-ok: 그 관용구를 지우는 연장 자신이므로 이름을 부른다)

멱등: 이미 이관된 코퍼스면 0건. 기본은 dry-run, `--write` 로 반영.

## 왜

2026-08-23 언어 개정(커밋 `bccf4c3`)으로 `[table:each]` 가 **통화를 그대로** 내게 됐다.
옛 계약은 출력 행을 `원 행 + _ok + (_error|_result)` 봉투로 싸서 뒤에 변환자를 이으려면
`>> [table:flatten]` 이 반드시 필요했고, 코퍼스 49건 중 15건이 그 2낱말 관용구였다.
개정 뒤 그 15건은 **없어진 관용구를 가르치는 교재**가 되므로 같은 날 이관했다.

★그런데 그때 나는 인라인으로 처리하고 스크립트를 남기지 않았다 — 이 저장소의
`scripts/migrate_*.py` 규약을 어긴 것이다. 코퍼스 두 소스(`data/ibl_usage.db`,
`data/training/ibl_distilled.json`)는 **둘 다 gitignore** 라 이 기계에만 있다. 백업에서
복구하는 순간 그 15건이 옛 형태로 되살아나고, 교재가 다시 죽은 관용구를 가르친다.
이 스크립트가 그 구멍을 막는다 — 복구 후 한 번 돌리면 상태가 같아진다.

## 무엇을 어떻게 바꾸는가

    A >> [table:each]{…} >> [table:flatten]{}            → A >> [table:each]{…}
    A >> [table:each]{…} >> [table:flatten]{keep: [x]}   → A >> [table:each]{keep: [x], …}
    A >> [table:each]{…} >> [table:flatten]{field: "_result"} >> B  → A >> [table:each]{…} >> B

★`keep` 은 버리지 않고 **자리를 옮긴다**. 옛 `flatten{keep: […]}` 이 하던 일("이 결과 행이
어느 부모에서 왔는가")을 개정이 `each{keep: […]}` 로 승계했기 때문이다 — 능력을 없애는
개정이 아니었으므로 이관도 능력을 버리면 안 된다.

★`field` 를 **명시적으로 다른 필드**로 지목한 flatten(진짜 중첩 목록 펴기)은 건드리지
않는다. 그건 each 봉투를 푸는 관용구가 아니라 제 일을 하는 문장이다.

## 안전

- 기본 dry-run. `--write` 없이는 아무것도 안 쓴다.
- 쓰기 전에 **파서로 검증**한다 — 하나라도 파싱 실패면 **전건 중단**(교재에 깨진 문장을
  넣느니 아무것도 안 하는 게 낫다).
- `--write` 시 DB·JSON 을 `data/_backups/<날짜>_each_contract_migration/` 에 먼저 뜬다.
- ★두 소스를 **함께** 고친다. 트레이너는 DB 와 ibl_distilled.json 을 둘 다 읽으므로
  한쪽만 고치면 다음 학습이 갈린다.

사용: .venv/bin/python3 scripts/migrate_each_currency_contract.py [--write]
"""
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if ".worktrees" in ROOT.parts:
    ROOT = Path(*ROOT.parts[:ROOT.parts.index(".worktrees")])
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("INDIEBIZ_BASE_PATH", str(ROOT))
# ★층 디렉토리(backend/{base,ibl,…})를 경로에 올린다 — 이게 없으면 아래 파서 검증이
#   ModuleNotFoundError 로 죽는다. 이 저장소의 독립 스크립트 공통 규약(CLAUDE.md).
#   ★이 결함은 "이관 대상 0건" 실행이 가렸다 — 검증까지 못 가서 import 를 안 밟는다.
#     0건은 '통과'가 아니라 '아무것도 안 봤다'일 수 있다. 이관 전 백업으로 실동 확인할 것.
import boot_paths  # noqa: F401,E402

DB = ROOT / "data" / "ibl_usage.db"
DIST = ROOT / "data" / "training" / "ibl_distilled.json"

# `>> [table:flatten]{…}` 한 step. 중첩 중괄호 한 겹까지 허용(keep: […] 안엔 없지만 방어).
_FLATTEN_STEP = re.compile(r'\s*>>\s*\[table:flatten\]\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}')
_EACH_HEAD = re.compile(r'\[table:each\]\s*\{')
_KEEP = re.compile(r'keep\s*:\s*(\[[^\]]*\])')
_FIELD = re.compile(r'field\s*:\s*["\']([^"\']*)["\']')


def migrate(code: str):
    """(새 코드, 사유) — 대상이 아니면 (None, 사유)."""
    if not code or "table:each" not in code or "table:flatten" not in code:
        return None, "대상 아님"
    m = _FLATTEN_STEP.search(code)
    if not m:
        return None, "flatten 이 파이프 step 이 아님 — 수동 검토"
    inner = m.group(1)
    fld = _FIELD.search(inner)
    if fld and fld.group(1) not in ("_result", "_result.items"):
        # 진짜 중첩 목록을 펴는 문장 — each 봉투 관용구가 아니다. 손대지 않는다.
        return None, f"field:{fld.group(1)!r} 는 봉투 관용구가 아님 — 보존"
    new = _FLATTEN_STEP.sub("", code, count=1)
    keep = _KEEP.search(inner)
    if keep:
        em = _EACH_HEAD.search(new)
        if not em:
            return None, "each 를 못 찾음 — 수동 검토"
        new = new[:em.end()] + f"keep: {keep.group(1)}, " + new[em.end():]
        return new, "flatten 제거 + keep 이관"
    return new, "flatten 제거"


def parses(code: str):
    from ibl_parser import parse, IBLSyntaxError
    try:
        parse(code)
        return True, ""
    except IBLSyntaxError as e:
        return False, str(e)
    except Exception as e:                      # 파서가 다른 예외를 내도 통과시키지 않는다
        return False, f"{type(e).__name__}: {e}"


def main(write: bool):
    if not DB.exists():
        print(f"[migrate] 코퍼스 DB 가 없습니다: {DB}")
        return 2
    conn = sqlite3.connect(str(DB))
    rows = [(i, c) for i, c in conn.execute("SELECT id, ibl_code FROM ibl_examples") if c]
    plan, skipped = [], []
    for i, code in rows:
        new, why = migrate(code)
        (plan if new else skipped).append((i, code, new, why))
    skipped = [s for s in skipped if "대상 아님" not in s[3]]

    print(f"[migrate] 코퍼스 {len(rows)}건 · 이관 대상 {len(plan)}건"
          + (f" · 보존/검토 {len(skipped)}건" if skipped else ""))
    for i, _, _, why in skipped:
        print(f"  · #{i} 보존: {why}")
    if not plan:
        print("[migrate] 이미 이관된 상태입니다 (멱등 — 할 일 0건).")
        conn.close()
        return 0

    bad = []
    for i, _, new, _ in plan:
        ok, err = parses(new)
        if not ok:
            bad.append((i, err))
    if bad:
        print(f"[migrate] ✗ 파서 검증 실패 {len(bad)}건 — **전건 중단**"
              " (교재에 깨진 문장을 넣느니 아무것도 안 한다):")
        for i, err in bad:
            print(f"    #{i}: {err}")
        conn.close()
        return 1

    for i, old, new, why in plan:
        print(f"  #{i} [{why}]\n     - {old[:110]}\n     + {new[:110]}")
    if not write:
        print(f"\n[migrate] dry-run 입니다. 반영하려면 --write 를 주세요.")
        conn.close()
        return 0

    bdir = ROOT / "data" / "_backups" / f"{date.today().isoformat()}_each_contract_migration"
    bdir.mkdir(parents=True, exist_ok=True)
    conn.execute("VACUUM INTO ?", (str(bdir / "ibl_usage.db"),))
    if DIST.exists():
        shutil.copy2(DIST, bdir / "ibl_distilled.json")
    print(f"[migrate] 백업: {bdir}")

    for i, _, new, _ in plan:
        conn.execute("UPDATE ibl_examples SET ibl_code=?, updated_at=datetime('now') WHERE id=?",
                     (new, i))
    conn.commit()
    conn.close()
    print(f"[migrate] DB 갱신 {len(plan)}건")

    # ★두 소스를 함께 — 트레이너는 DB 와 이 파일을 둘 다 읽는다.
    n = 0
    if DIST.exists():
        dist = json.loads(DIST.read_text(encoding="utf-8"))
        for item in dist:
            if not isinstance(item, dict):
                continue
            new, _ = migrate(item.get("ibl_code") or "")
            if new:
                item["ibl_code"] = new
                n += 1
        if n:
            DIST.write_text(json.dumps(dist, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[migrate] ibl_distilled 갱신 {n}건")
    print("[migrate] ★벡터 색인은 별개다 — 코드가 바뀌었으므로 rebuild_index() 후 백엔드 재기동할 것"
          " (재기동 전에 scripts/preflight_restart.py).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(write="--write" in sys.argv))
