#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""register_idiom.py — 관용구 **수동** 등록·승격 (2026-09-07 사용자 판정).

상시 프롬프트에 소개되는 관용구는 실질적으로 **어휘**다. 어휘는 자동으로 늘어나서는 안 되므로
(ibl.md §8 "작업보다 느리게 자란다") 매 에피소드 자동 증류를 멈추고, 등록의 방아쇠를 사람에게 옮겼다.

두 층:
  · `always_on=1` — 시스템 프롬프트의 이름 지도에 선다 = 어휘. 매 턴 세금을 문다.
  · `always_on=0` — 등록만. 이름으로 부를 수는 있으나 소개되지 않아 보통은 쓰이지 않는다
                    (앱 버튼처럼 명시 호출이 있는 자리).

등록 자격(사용자 판정 "코퍼스에서도 언급해줘야 한다 — 그럴만 해야 등록해준다"): 승격은 **코퍼스에
용례로 실릴 만한 것**만. 그래서 `--promote` 는 그 이름을 부르는 용례를 해마 코퍼스에 함께 심는다
(단일 경로 `add_examples_batch`) — 낱말이 문장 안에 있는 모습을 본 적 있어야 실제로 불린다
(실측 상관 r=0.72, ibl_access._partners 주석).

쓰기:
  python3 scripts/register_idiom.py --list
  python3 scripts/register_idiom.py --add 이름 --when "언제 부르는가" --body 몸.ibl [--always-on]
  python3 scripts/register_idiom.py --update 이름 --body 수리.ibl --reason "재발 원인과 검증 결과"
  python3 scripts/register_idiom.py --refresh 이름  # 본문·실적 유지, 파생 반환형·서명 재산정
  python3 scripts/register_idiom.py --promote 이름 | --demote 이름
  python3 scripts/register_idiom.py --candidates [--days 3]     # 부정기 수동 수집 보조
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import boot_paths  # noqa: E402,F401

from runtime_utils import get_base_path  # noqa: E402


NAME_MAX_CHARS = 12


def _db_path():
    return str(get_base_path() / "data" / "ibl_usage.db")


def _gates(name: str, when: str, code: str):
    """등록 관문 — 자동 증류가 쓰던 바로 그 관문들. 방아쇠만 사람에게 갔지 자는 그대로다."""
    from ibl_parser import parse_function_body
    from ibl_usage_rag import _validate_ibl_actions
    from ibl_param_vocab import check_code_params
    from ibl_typecheck import typecheck_code, return_type_of
    from workflow_contract import call_signature
    from ibl_idiom import (uncallable_reason, _phrase_private_reason, sanitize_fn_name,
                           frozen_incident_reason)
    import hippo_tree

    if sanitize_fn_name(name, name) != name:
        return None, f"이름이 규약에 안 맞는다 — 권장: {sanitize_fn_name(name, name)}"
    # 이름은 **이번 사건이 아니라 되풀이될 모양**을 말한다(옛 반성기 프롬프트의 규약을 관문으로 옮겼다,
    # 2026-09-07): 12자를 넘으면 사건 이름일 확률이 크다 — 사건 이름은 다음 주행이 못 부른다.
    if len(name) > NAME_MAX_CHARS:
        return None, (f"이름 {len(name)}자 — 상한 {NAME_MAX_CHARS}. 이번 사건이 아니라 되풀이될 모양의 "
                      f"동사 골격만 남겨라(나쁜 예 '오버레이레이아웃무관허용및재적용')")
    if not when or len(when.strip()) < 10:
        return None, "`--when` 이 없다 — 지도는 뜻이 아니라 **부를 조건**을 싣는다(10자 이상)"
    try:
        parse_function_body(code)
    except Exception as e:
        return None, f"파싱 불가: {e}"
    if not _validate_ibl_actions(code) or check_code_params(code):
        return None, "존재하지 않는 액션 또는 인자"
    tc = typecheck_code(f"[def: {name}]{{\n{code}\n}}")
    if tc.get("syntax_error"):
        return None, f"타입 검사 파싱 불가: {tc['syntax_error']}"
    errs = [i for i in (tc.get("issues") or []) if i.get("severity", i.get("level")) == "error"]
    if errs:
        return None, f"타입 오류: {(errs[0].get('message') or '')[:120]}"
    sig = call_signature(code)
    n = len(hippo_tree.split_sentences(code))
    # 일회성 관문(2026-09-07): 슬롯 0·슬롯 6+·얼어붙은 경로 리터럴 — 다시 부를 수 없는 몸에는 이름을 주지 않는다.
    why = uncallable_reason(sig, n, code) or _phrase_private_reason(code) or frozen_incident_reason(code, sig)
    if why:
        return None, why
    return {"signature": sig, "returns": return_type_of(code), "sentences": n}, None


def _corpus_example(name: str, sig, when: str):
    """승격과 함께 심는 용례 — 그 이름을 **부르는** 한 문장. 코퍼스에 언급돼야 등록 자격이다."""
    args = ", ".join(f'{s}: "…"' for s in sig)
    return {"intent": when[:150], "ibl_code": f"[fn:{name}]{{{args}}}",
            "nodes": "fn", "category": "phrase", "difficulty": 1,
            "source": "idiom_registry", "tags": "manual,always_on"}


def cmd_list(_a):
    conn = sqlite3.connect(_db_path())
    rows = conn.execute(
        "SELECT alias, COALESCE(always_on,0), success_count+fail_count, COALESCE(topic,''), intent "
        "FROM ibl_examples WHERE COALESCE(alias,'') != '' ORDER BY COALESCE(always_on,0) DESC, alias").fetchall()
    conn.close()
    on = [r for r in rows if r[1]]
    off = [r for r in rows if not r[1]]
    print(f"■ 상시 소개(어휘) {len(on)}건")
    for a, _o, n, t, i in on:
        print(f"   {a:20} · 사용 {n:>3}회 · [{t}] {i[:60]}")
    print(f"\n■ 등록만(소개 안 함) {len(off)}건 — 이름으로 부를 수는 있다")
    for a, _o, n, t, i in off:
        print(f"   {a:20} · 사용 {n:>3}회 · [{t}] {i[:60]}")


def cmd_add(a):
    code = open(a.body, encoding="utf-8").read().strip() if os.path.exists(a.body) else a.body
    info, why = _gates(a.add, a.when, code)
    if why:
        print(f"✗ 등록 거절 — {why}")
        return 1
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    if db.find_phrase_by_alias(a.add):
        print(f"✗ 이름 '{a.add}' 이 이미 있다 — 본문 수리는 --update, 소개 층은 --promote/--demote로 바꾸라")
        return 1
    eid = db.add_example(intent=a.when, ibl_code=code, nodes="", category="phrase",
                         source="manual_registry", tags="manual", topic=a.topic or "",
                         alias=a.add, returns=info["returns"])
    if not eid:
        print("✗ 입구 게이트가 거부했다(구문·소유)")
        return 1
    print(f"✓ 등록 #{eid}  [fn:{a.add}]{{{', '.join(info['signature'])}}} → {info['returns']} · 문장 {info['sentences']}")
    if a.promote_too:
        return _promote(a.add, True)
    print("  (상시 소개는 --promote 이름 또는 --always-on 으로 — 어휘가 되므로 따로 고른다)")
    return 0


def update_idiom(db, name, code, reason, when="", resign=False):
    """명시 개정: 같은 호출 서명·이름 유지, 옛 본문과 통계를 한 트랜잭션으로 보존.

    resign=True 는 **서명 개정**(슬롯이 달라지는 개정, 2026-09-09 노출 실험 지렛대 1 — 파이프형을 자족형으로).
    옛 서명으로 부르는 코퍼스 용례는 다음 회상에서 거절당할 몸이므로 함께 고쳐야 한다 — 여기서는 그 행을
    찾아 돌려주고(callers), 고치는 것은 부르는 쪽의 책임이다."""
    import json
    from datetime import datetime
    from workflow_contract import call_signature
    from ibl_usage_db import _signature_of, _tree_refresh

    old = db.find_phrase_by_alias(name)
    if not old:
        raise ValueError(f"'{name}' 이 없다")
    if not reason.strip():
        raise ValueError("--reason에 수리 이유와 검증 결과를 적으세요")
    intent = when or old["intent"]
    info, why = _gates(name, intent, code)
    if why:
        raise ValueError(f"개정 거절 — {why}")
    resigned = set(call_signature(old["ibl_code"])) != set(info["signature"])
    if resigned and not resign:
        raise ValueError("호출 서명이 달라집니다 — 기존 인자를 유지해 수리하거나 --resign 으로 서명 개정을 명시하세요")
    if old["ibl_code"].strip() == code.strip() and old["intent"] == intent:
        return False
    now = datetime.now().isoformat()
    with db._get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM ibl_examples WHERE id=?", (old["id"],)).fetchone()
        if (not current or current["ibl_code"] != old["ibl_code"]
                or current["intent"] != old["intent"] or current["alias"] != name):
            raise ValueError("검사 중 본문이 바뀌었습니다 — 새 정의를 읽고 다시 개정하세요")
        conn.execute("""CREATE TABLE IF NOT EXISTS ibl_idiom_revisions (
            id INTEGER PRIMARY KEY, example_id INTEGER NOT NULL, alias TEXT NOT NULL,
            revised_at TEXT NOT NULL, reason TEXT NOT NULL, old_row TEXT NOT NULL,
            new_code TEXT NOT NULL)""")
        conn.execute("INSERT INTO ibl_idiom_revisions "
                     "(example_id, alias, revised_at, reason, old_row, new_code) VALUES (?,?,?,?,?,?)",
                     (old["id"], name, now, reason, json.dumps(dict(current), ensure_ascii=False), code))
        conn.execute("UPDATE ibl_examples SET ibl_code=?, intent=?, returns=?, signature=?, "
                     "success_count=0, fail_count=0, bypass_count=0, avg_ms=-1, avg_tokens=-1, "
                     "updated_at=? WHERE id=?",
                     (code, intent, info["returns"], _signature_of(code), now, old["id"]))
        conn.commit()
    # 새 본문에 옛 실적을 붙이지 않는다. 이름·always_on·topic·용례 id는 유지한다.
    db._index_single(old["id"], f"{name} {intent}", code)
    if hasattr(db, "_search_cache"):
        db._search_cache.clear()
    _tree_refresh(old["topic"])
    if resigned:
        with db._get_connection() as conn:
            callers = conn.execute("SELECT id, source, ibl_code FROM ibl_examples WHERE id != ? AND ibl_code LIKE ?",
                                   (old["id"], f"%[fn:{name}]%")).fetchall()
        for c in callers:
            print(f"  ! 옛 서명으로 부르는 용례 #{c['id']}({c['source']}): {c['ibl_code'][:100]!r} — 새 서명 {info['signature']} 으로 고칠 것")
    return True


def refresh_idiom_metadata(db, name):
    """현재 본문의 파생 계약만 갱신한다. 실행 실적·호출 용례·벡터는 보존한다."""
    from ibl_usage_db import _signature_of, _tree_refresh

    old = db.find_phrase_by_alias(name)
    if not old:
        raise ValueError(f"'{name}' 이 없다")
    info, why = _gates(name, old["intent"], old["ibl_code"])
    if why:
        raise ValueError(f"계약 갱신 거절 — {why}")
    signature = _signature_of(old["ibl_code"])
    changed = old.get("returns") != info["returns"] or old.get("signature") != signature
    with db._get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT ibl_code, intent FROM ibl_examples WHERE id=?",
                               (old["id"],)).fetchone()
        if not current or current["ibl_code"] != old["ibl_code"] or current["intent"] != old["intent"]:
            raise ValueError("검사 중 정의가 바뀌었습니다 — 다시 갱신하세요")
        conn.execute("UPDATE ibl_examples SET returns=?, signature=? WHERE id=? AND ibl_code=? AND intent=?",
                     (info["returns"], signature, old["id"], old["ibl_code"], old["intent"]))
        conn.commit()
    if hasattr(db, "_search_cache"):
        db._search_cache.clear()
    _tree_refresh(old["topic"], strict=True)
    return changed


def cmd_update(a):
    from ibl_usage_db import IBLUsageDB
    code = open(a.body, encoding="utf-8").read().strip() if os.path.exists(a.body) else a.body
    try:
        changed = update_idiom(IBLUsageDB(), a.update, code, a.reason, a.when, resign=a.resign)
    except ValueError as exc:
        print(f"✗ {exc}")
        return 1
    print(f"✓ {a.update}: " + ("개정 완료 — 이전 본문·실적은 ibl_idiom_revisions에 보존" if changed else "변경 없음"))
    return 0


def _promote(name: str, on: bool, when: str = "") -> int:
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    row = db.find_phrase_by_alias(name)
    if not row:
        print(f"✗ '{name}' 이 없다")
        return 1
    if on and when:
        # 승격하며 '언제'를 다시 쓴다 — 자동 증류가 남긴 intent 는 *무엇을 하는가*(뜻)라서
        # 지도의 '언제' 자리에 그대로 두면 부를 조건이 되지 못한다(2026-09-07).
        info, why = _gates(name, when, row["ibl_code"])
        if why:
            print(f"✗ 승격 거절 — {why}")
            return 1
    conn = sqlite3.connect(_db_path(), timeout=10)
    if on and when:
        conn.execute("UPDATE ibl_examples SET always_on=1, intent=? WHERE alias=?", (when, name))
    else:
        conn.execute("UPDATE ibl_examples SET always_on=? WHERE alias=?", (1 if on else 0, name))
    conn.commit()
    conn.close()
    print(f"✓ {name} → {'상시 소개(어휘)' if on else '등록만'}")
    if on:
        from workflow_contract import call_signature
        n = db.add_examples_batch([_corpus_example(name, call_signature(row["ibl_code"]), when or row["intent"])])
        print(f"  코퍼스에 호출 용례 {n}건 심음 — 낱말은 문장 안에 있는 모습을 본 적 있어야 불린다")
    return 0


def cmd_candidates(a):
    """부정기 수동 수집 보조 — 실행 원장에서 되풀이된 여러 문장 프로그램을 보여준다. 고르는 것은 사람."""
    conn = sqlite3.connect(str(get_base_path() / "data" / "world_pulse.db"))
    rows = conn.execute(
        "SELECT code, seen_count, success_count FROM ibl_code_corpus "
        "WHERE seen_count >= ? AND last_seen >= date('now', ?) ORDER BY seen_count DESC LIMIT 40",
        (a.min_seen, f"-{a.days} day")).fetchall()
    conn.close()
    import re
    shown = 0
    for code, seen, ok in rows:
        if len(re.findall(r'\[[a-z_]+:[a-z_]+\]', code or "")) < 2:
            continue
        shown += 1
        print(f"\n── {seen}회 실행(성공 {ok})")
        print("   " + (code or "").replace("\n", "\n   ")[:400])
    print(f"\n{shown}건 — 되풀이될 모양이면 --add 로 등록하라(값은 ${{슬롯}} 으로 비우고).")


def main():
    p = argparse.ArgumentParser(description="관용구 수동 등록·승격")
    p.add_argument("--list", action="store_true")
    p.add_argument("--add", metavar="이름")
    p.add_argument("--update", metavar="이름", help="호출 서명을 유지하며 본문을 명시 개정")
    p.add_argument("--refresh", metavar="이름", help="본문·실적 유지, 반환형·서명 재산정")
    p.add_argument("--reason", default="", help="개정 이유와 검증 결과")
    p.add_argument("--resign", action="store_true", help="--update 와 함께 — 호출 서명(슬롯)이 달라지는 개정을 명시 허용")
    p.add_argument("--when", default="", help="언제 부르는가 — 지도에 실리는 조건")
    p.add_argument("--body", default="", help="몸(.ibl 파일 경로 또는 코드 문자열)")
    p.add_argument("--topic", default="", help="가지")
    p.add_argument("--promote", metavar="이름")
    p.add_argument("--demote", metavar="이름")
    p.add_argument("--always-on", dest="always_on", action="store_true",
                   help="--add 와 함께 — 등록하면서 곧바로 상시 소개(어휘)로 올린다")
    p.add_argument("--candidates", action="store_true")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--min-seen", type=int, default=2)
    a = p.parse_args()
    a.promote_too = bool(a.add and a.always_on)
    if a.refresh:
        from ibl_usage_db import IBLUsageDB
        changed = refresh_idiom_metadata(IBLUsageDB(), a.refresh)
        print(f"✓ {a.refresh}: " + ("파생 계약 갱신" if changed else "파생 계약 일치"))
        return 0
    if a.update:
        return cmd_update(a)
    if a.add:
        return cmd_add(a)
    if a.promote:
        return _promote(a.promote, True, a.when)
    if a.demote:
        return _promote(a.demote, False)
    if a.candidates:
        return cmd_candidates(a)
    return cmd_list(a) or 0


if __name__ == "__main__":
    sys.exit(main() or 0)
