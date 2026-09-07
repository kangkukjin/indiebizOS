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
    from ibl_typecheck import typecheck_code, return_type_of
    from workflow_contract import call_signature
    from ibl_idiom import uncallable_reason, _phrase_private_reason, sanitize_fn_name
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
    tc = typecheck_code(code)
    errs = [i for i in (tc.get("issues") or []) if i.get("level") == "error"]
    if errs:
        return None, f"타입 오류: {(errs[0].get('message') or '')[:120]}"
    sig = call_signature(code)
    n = len(hippo_tree.split_sentences(code))
    why = uncallable_reason(sig, n, code) or _phrase_private_reason(code)
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
        print(f"✗ 이름 '{a.add}' 이 이미 있다 — --promote/--demote 로 층만 바꾸거나 다른 이름을 쓰라")
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


def _promote(name: str, on: bool) -> int:
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    row = db.find_phrase_by_alias(name)
    if not row:
        print(f"✗ '{name}' 이 없다")
        return 1
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.execute("UPDATE ibl_examples SET always_on=? WHERE alias=?", (1 if on else 0, name))
    conn.commit()
    conn.close()
    print(f"✓ {name} → {'상시 소개(어휘)' if on else '등록만'}")
    if on:
        from workflow_contract import call_signature
        n = db.add_examples_batch([_corpus_example(name, call_signature(row["ibl_code"]), row["intent"])])
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
    if a.add:
        return cmd_add(a)
    if a.promote:
        return _promote(a.promote, True)
    if a.demote:
        return _promote(a.demote, False)
    if a.candidates:
        return cmd_candidates(a)
    return cmd_list(a) or 0


if __name__ == "__main__":
    sys.exit(main() or 0)
