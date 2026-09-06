"""backfill_idiom_meaning.py — 이름 붙은 용례의 intent 를 '사건 요약'에서 '함수의 뜻'으로 (2026-09-06).

왜: 이름 채널·상시 지도는 intent 로 검색·표시된다. 옛 관용구의 intent 는 그 에피소드의 과제 요약
("USB 연결된 폰에서 계기 트리 혼종 문제를 진단하고 수리한다")이라 다음 주행이 자기 일과 맞춰 볼 수 없었다
(09-06 실측: 딱 맞는 이름이 있는 자연 요청 2/2 에 이름 0건). 뜻은 AI 가 쓴다(경량 원샷) — 스크립트는 통로.

    .venv/bin/python3 scripts/backfill_idiom_meaning.py            # 실행(옛 intent 는 _backups 에 보관)
    .venv/bin/python3 scripts/backfill_idiom_meaning.py --dry-run  # 제안만 출력
    .venv/bin/python3 scripts/backfill_idiom_meaning.py --ids 4509,4522
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import boot_paths  # noqa: F401,E402  경로·원장 배선

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")   # 경량 AI 키 — dotenv 먼저

PROMPT = """아래는 IBL(정보 흐름 언어)로 쓴, 이름 붙은 함수(관용구)다. 이 함수의 **뜻**을 한 줄로 써라.

규칙:
- "무엇을 받아 무엇을 내는가" — 사건·파일·사용자 사정이 아니라 *되풀이될 기능* 을 일반 서술로. 80자 안.
- 현재 설명은 그 함수가 태어난 사건의 요약일 수 있다. 사건 이름(USB·계기·특정 파일·특정 질의어)은 지워라.
- 인자 이름(슬롯)이 있으면 그것이 받는 것이다. 마지막 문장이 내는 것이 결과다.
- **현재 설명이 이미 사건이 아니라 기능을 일반 서술로 말하고 있으면 바꾸지 마라** — 그 낱말들이 검색의 손잡이다.
  그때는 {{"keep": true}} 로만 답하라. 사건 요약(특정 문제·기기·파일·사용자 사정)일 때만 새로 써라.
- 한국어 평서문 하나. JSON 으로만 답하라: {{"meaning": "…"}} 또는 {{"keep": true}}

이름: {alias}
인자: {slots}
현재 설명: {intent}
본문:
{code}
"""


def sync_training(db) -> None:
    """학습 원장(data/training/ibl_distilled.json)의 같은 코드 항목에도 새 뜻을 — 두 원장이 어긋나면 재학습이 옛 뜻을 배운다."""
    from runtime_utils import get_base_path
    tp = get_base_path() / "data" / "training" / "ibl_distilled.json"
    if not tp.exists():
        return
    try:
        entries = json.loads(tp.read_text(encoding="utf-8"))
    except ValueError:
        return
    with db._get_connection() as conn:
        bycode = {r[1]: r[0] for r in conn.execute("SELECT intent, ibl_code FROM ibl_examples WHERE COALESCE(alias,'') != ''")}
    n = 0
    for e in entries:
        if isinstance(e, dict) and e.get("ibl_code") in bycode and e.get("intent") != bycode[e["ibl_code"]]:
            e["intent"] = bycode[e["ibl_code"]]
            n += 1
    if n:
        tp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"학습 원장 동기화: {n}건")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ids", default="")
    ap.add_argument("--restore", default="", help="백업 JSON 의 old_intent 로 되돌린 뒤 다시 묻는다")
    ap.add_argument("--force", action="store_true", help="keep 선택지 없이 반드시 새로 쓴다(사건 요약이 분명한 행에)")
    ap.add_argument("--reindex", action="store_true", help="AI 를 묻지 않고 이름 행 전부의 벡터만 다시 세운다")
    args = ap.parse_args()
    from ibl_usage_db import IBLUsageDB, parse_signature
    from consciousness_agent import oneshot_ai_call
    from runtime_utils import parse_first_json, get_base_path
    db = IBLUsageDB()
    # ★모델을 동기로 올린다 — 백그라운드 로드가 끝나기 전의 update_intent 는 벡터를 못 세워 스테일 벡터가 남는다(09-06 실측 cos 0.11 vs 0.37)
    IBLUsageDB._load_model_sync()
    if args.reindex:
        with db._get_connection() as conn:
            rows = conn.execute("SELECT id, intent, ibl_code, COALESCE(alias,'') FROM ibl_examples WHERE COALESCE(alias,'') != ''").fetchall()
        for rid, intent, code, alias in rows:
            db._index_single(int(rid), f"{alias} {intent}", code)
        print(f"재색인: {len(rows)}행")
        sync_training(db)
        return 0
    if args.restore:
        for it in json.loads(Path(args.restore).read_text(encoding="utf-8")):
            db.update_intent(int(it["id"]), it["old_intent"])
        print(f"되돌림: {args.restore}")
    only = {int(x) for x in args.ids.split(",") if x.strip()} if args.ids else None
    with db._get_connection() as conn:
        rows = conn.execute("SELECT id, intent, ibl_code, COALESCE(alias,''), signature FROM ibl_examples "
                            "WHERE COALESCE(alias,'') != '' ORDER BY id").fetchall()
    backup, changed, skipped = [], 0, 0
    for r in rows:
        rid, intent, code, alias = int(r[0]), str(r[1] or ""), str(r[2] or ""), str(r[3] or "")
        if only and rid not in only:
            continue
        sig_raw = r[4] if len(r) > 4 else None
        names, known = parse_signature(sig_raw)
        _prompt = PROMPT if not args.force else PROMPT.replace(
            "- **현재 설명이 이미 사건이 아니라 기능을 일반 서술로 말하고 있으면 바꾸지 마라** — 그 낱말들이 검색의 손잡이다.\n"
            "  그때는 {{\"keep\": true}} 로만 답하라. 사건 요약(특정 문제·기기·파일·사용자 사정)일 때만 새로 써라.\n", "")
        out = oneshot_ai_call(prompt=_prompt.format(alias=alias, slots=", ".join(names) if known and names else "(없음)",
                                                   intent=intent, code=code[:2500]),
                              system_prompt="", role="background")
        obj = parse_first_json(out or "") if out else None
        if isinstance(obj, dict) and obj.get("keep"):
            print(f"[keep] #{rid} {alias}: {intent[:70]}")
            continue
        meaning = str((obj or {}).get("meaning") or "").strip() if isinstance(obj, dict) else ""
        if not meaning or len(meaning) > 160:
            print(f"[skip] #{rid} {alias}: 답 없음/과장 — {str(out)[:80]!r}")
            skipped += 1
            continue
        print(f"#{rid} {alias}\n   옛: {intent[:90]}\n   새: {meaning}")
        backup.append({"id": rid, "alias": alias, "old_intent": intent, "new_intent": meaning})
        if not args.dry_run and db.update_intent(rid, meaning):
            changed += 1
    if backup and not args.dry_run:
        bdir = get_base_path() / "data" / "_backups"
        bdir.mkdir(parents=True, exist_ok=True)
        bp = bdir / f"{date.today().isoformat()}_idiom_meaning_backfill.json"
        prev = json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else []     # 누적 — 되돌릴 첫 원문을 잃지 않는다
        seen = {int(x["id"]) for x in backup}
        bp.write_text(json.dumps([x for x in prev if int(x["id"]) not in seen] + backup, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"옛 intent 보관: {bp}")
    sync_training(db)
    try:
        from ibl_usage_rag import IBLUsageRAG
        IBLUsageRAG().clear_cache()
        from ibl_access import _idioms_cache
        _idioms_cache.update({"text": None})
    except Exception:
        pass
    print(f"완료: 갱신 {changed} · 스킵 {skipped} · 후보 {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
