"""이름 붙은 용례의 호출 서명 백필 (2026-09-06).

서명은 원장 문(ibl_usage_db.add_example)이 계산해 넣지만, 그 문이 생기기 전에 태어난 행은
비어 있다. 표시 쪽이 `${…}` 로 따로 세던 시절의 행들이라 바로 이들이 어긋난 서명을 가르쳤다
(45건 중 10건 불일치, 5건은 표시가 빈 `{}` 라 가르친 대로 부르면 100% "인자 누락").

한 번만 돌리면 되고, 되풀이해 돌려도 같은 값을 쓴다(멱등).
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import boot_paths  # noqa: F401  경로·원장 배선

from workflow_contract import call_signature     # noqa: E402
from ibl_idiom import uncallable_reason           # noqa: E402


def main(dry: bool = False) -> int:
    db = Path(__file__).resolve().parent.parent / "data" / "ibl_usage.db"
    con = sqlite3.connect(str(db))
    rows = con.execute(
        "SELECT id, COALESCE(alias,''), ibl_code, signature FROM ibl_examples "
        "WHERE COALESCE(alias,'') != '' ORDER BY id").fetchall()
    changed = failed = pruned = 0
    for rid, alias, code, cur in rows:
        try:
            sig = " ".join(call_signature(code))
        except Exception as e:
            print(f"  #{rid} {alias}: 파스 실패 — 서명 미상으로 둠 ({e.__class__.__name__})")
            failed += 1
            continue
        try:
            import hippo_tree
            _n = len(hippo_tree.split_sentences(code))
        except Exception:
            _n = 99
        why = uncallable_reason(sig.split(), _n)
        if cur != sig:
            print(f"  #{rid} {alias}: {cur!r} → {sig!r}")
            changed += 1
            if not dry:
                con.execute("UPDATE ibl_examples SET signature=? WHERE id=?", (sig, rid))
        if why:
            # 관문이 '이름'의 뜻을 정한다 — 부를 수 없는 것은 이름을 내려놓고 무명 용례로 돌아간다.
            # 행은 남는다(회상·재학습의 재료). 다시 부를 수 있는 모양이 되면 증류가 새 이름을 붙인다.
            print(f"  #{rid} {alias}: 이름 회수 — {why}")
            pruned += 1
            if not dry:
                con.execute("UPDATE ibl_examples SET alias='' WHERE id=?", (rid,))
    if not dry:
        con.commit()
    con.close()
    print(f"\n대상 {len(rows)}건 · 서명 갱신 {changed} · 이름 회수 {pruned} · 파스 실패 {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(dry="--dry" in sys.argv))
