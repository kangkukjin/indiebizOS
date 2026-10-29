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

현재 등록·개정·소개는 판본 2 본문(`#!ibl edition=2`)만 받는다.
판본 1 원문과 실적은 역사 자료로 보존하며 실행·승격하지 않는다.
같은 이름의 옛 기록을 새 정의로 덮어쓰거나 그 실적을 승계하지 않는다.

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


def _edition(code: str) -> int:
    from ibl_edition import source_edition
    return source_edition(code or "", 2)


def _gates_v2(name: str, when: str, code: str, *, metadata_only=False):
    """현재 함수 등록의 정적 관문. 소개 선정 정책은 promote가 따로 소유한다."""
    from ibl_v2_store import definition_name, definitions
    from ibl_v2_learning import check_source
    from ibl_v2_parser import parse
    try:
        if definition_name(code) != name:
            return None, f"정의 이름이 등록 이름과 다르다: [def:{definition_name(code)}] ≠ {name}"
    except Exception as e:
        return None, f"판본 2 정의가 아니다: {getattr(e, 'message', e)}"
    library = definitions()
    library[name] = code
    why = check_source(code, True, library=library)
    if why:
        return None, f"판본 2 검사 실패: {why}"
    params = parse(code).data["statements"][0].data["params"]
    sig = list(params)
    n = code.count("\n")
    return {"signature": sig, "returns": "", "sentences": n, "edition": 2}, None


def _gates(name: str, when: str, code: str, *, metadata_only=False):
    return _gates_v2(name, when, code, metadata_only=metadata_only)


def _find(db, name: str):
    return db.find_phrase_by_alias(name)


def _corpus_example(name: str, sig, when: str):
    """승격과 함께 심는 용례 — 그 이름을 **부르는** 한 문장. 코퍼스에 언급돼야 등록 자격이다."""
    args = ", ".join(f'{s}: "…"' for s in sig)
    return {"intent": when[:150], "ibl_code": f"[fn:{name}]{{{args}}}",
            "nodes": "fn", "category": "phrase", "difficulty": 1,
            "source": "idiom_registry", "tags": "manual,always_on"}


def cmd_list(_a):
    import function_store
    from capability_history import function_statistics
    exposed = set()
    if os.path.isfile(_db_path()):
        with sqlite3.connect(_db_path()) as conn:
            conn.row_factory = sqlite3.Row
            exposed = {r['alias'] for r in conn.execute(
                "SELECT DISTINCT alias FROM ibl_examples WHERE always_on=1")}
    for row in sorted(function_store.snapshot()['records'].values(), key=lambda r: (r['name'], r['edition'])):
        stats = function_statistics(function_store.reference(row))
        label = '상시 소개 선정' if row['name'] in exposed else '등록'
        print(f"{row['name']:20} ed{row['edition']} · {row['state']} · {label} · "
              f"성공 {stats['success_count']} / 실패 {stats['fail_count']} · {row.get('description', '')[:60]}")


def cmd_add(a):
    code = open(a.body, encoding="utf-8").read().strip() if os.path.exists(a.body) else a.body
    from ibl_edition import require_current
    try:
        require_current(code, _edition(code))
    except ValueError as exc:
        print(f"✗ 등록 거절 — {exc}")
        return 1
    info, why = _gates(a.add, a.when, code)
    if why:
        print(f"✗ 등록 거절 — {why}")
        return 1
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    if _find(db, a.add):
        print(f"✗ 이름 '{a.add}' 의 판본 {info['edition']} 정의가 이미 있다 — 본문 수리는 --update, 소개 층은 --promote/--demote로 바꾸라")
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
    from ibl_usage_db import _signature_of, _tree_refresh

    from ibl_edition import require_current
    edition = require_current(code, _edition(code))
    old = _find(db, name)
    if not old:
        raise ValueError(f"'{name}' 의 판본 {edition} 정의가 없다(같은 판본의 본문만 개정한다 — 다른 판본은 --add)")
    if not reason.strip():
        raise ValueError("--reason에 수리 이유와 검증 결과를 적으세요")
    intent = when or old["intent"]
    info, why = _gates(name, intent, code)
    if why:
        raise ValueError(f"개정 거절 — {why}")
    old_sig = set(_gates(name, intent, old["ibl_code"], metadata_only=True)[0]["signature"])
    resigned = old_sig != set(info["signature"])
    if resigned and not resign:
        raise ValueError("호출 서명이 달라집니다 — 기존 인자를 유지해 수리하거나 --resign 으로 서명 개정을 명시하세요")
    if old["ibl_code"].strip() == code.strip() and old["intent"] == intent:
        return False
    from function_memory import attach
    prior = json.loads(old.get('provenance') or '{}')
    new_provenance = attach(name, code, intent, prior,
                            expected_revision=old['function_ref']['revision'], reason=reason)
    if old.get('id') is None:
        return True
    now = datetime.now().isoformat()
    with db._get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM ibl_current_examples WHERE id=?", (old["id"],)).fetchone()
        if (not current or current["intent"] != old["intent"] or current["alias"] != name):
            raise ValueError("검사 중 본문이 바뀌었습니다 — 새 정의를 읽고 다시 개정하세요")
        conn.execute("""CREATE TABLE IF NOT EXISTS ibl_idiom_revisions (
            id INTEGER PRIMARY KEY, example_id INTEGER NOT NULL, alias TEXT NOT NULL,
            revised_at TEXT NOT NULL, reason TEXT NOT NULL, old_row TEXT NOT NULL,
            new_code TEXT NOT NULL)""")
        conn.execute('UPDATE ibl_examples SET provenance=? WHERE id=?',
                     (json.dumps(new_provenance, ensure_ascii=False), old['id']))
        conn.execute("INSERT INTO ibl_idiom_revisions "
                     "(example_id, alias, revised_at, reason, old_row, new_code) VALUES (?,?,?,?,?,?)",
                     (old["id"], name, now, reason, json.dumps(dict(current), ensure_ascii=False), code))
        returns = old.get("returns") or ""
        conn.execute("UPDATE ibl_examples SET ibl_code=?, intent=?, returns=?, signature=?, "
                     "success_count=0, fail_count=0, bypass_count=0, avg_ms=-1, avg_tokens=-1, "
                     "updated_at=? WHERE id=?",
                     (code, intent, returns, _signature_of(code), now, old["id"]))
        conn.commit()
    # 새 본문에 옛 실적을 붙이지 않는다. 이름·always_on·topic·용례 id는 유지한다.
    db._index_single(old["id"], f"{name} {intent}", code)
    if hasattr(db, "_search_cache"):
        db._search_cache.clear()
    _tree_refresh(old["topic"])
    if resigned:
        with db._get_connection() as conn:
            callers = conn.execute("SELECT id, source, ibl_code FROM ibl_current_examples WHERE id != ? AND ibl_code LIKE ?",
                                   (old["id"], f"%[fn:{name}]%")).fetchall()
        for c in callers:
            print(f"  ! 옛 서명으로 부르는 용례 #{c['id']}({c['source']}): {c['ibl_code'][:100]!r} — 새 서명 {info['signature']} 으로 고칠 것")
    return True


def refresh_idiom_metadata(db, name):
    """Current contracts are compiler projections, never separately stored copies."""
    old = _find(db, name)
    if not old:
        raise ValueError(f"'{name}' 이 없다")
    _, why = _gates(name, old['intent'], old['ibl_code'], metadata_only=True)
    if why:
        raise ValueError(f'계약 갱신 거절 — {why}')
    return False


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
    row = _find(db, name)
    if not row:
        print(f"✗ '{name}' 이 없다")
        return 1
    if on and len((when or row.get('intent') or '').strip()) < 10:
        print("✗ 승격에는 부를 조건을 --when으로 설명하세요(10자 이상). 관용구 등록과 소개 선정은 별개입니다.")
        return 1
    if on and row.get('id') is None:
        eid = db.add_example(intent=when or row['intent'], ibl_code=row['ibl_code'],
                             category='phrase', source='manual_registry', alias=name)
        if not eid:
            print('✗ 소개할 관용구 참조 카드를 만들지 못했습니다.')
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
        conn.execute("UPDATE ibl_examples SET always_on=1 WHERE alias=?", (name,))
        conn.execute("UPDATE ibl_examples SET intent=? WHERE alias=? AND executable=1", (when, name))
    else:
        conn.execute("UPDATE ibl_examples SET always_on=? WHERE alias=?", (1 if on else 0, name))
    conn.commit()
    conn.close()
    print(f"✓ {name} → {'상시 소개(어휘)' if on else '등록만'}")
    if on:
        sig = _gates(name, when or row["intent"], row["ibl_code"], metadata_only=True)[0]["signature"]
        example = _corpus_example(name, sig, when or row["intent"])
        example["ibl_code"] = "#!ibl edition=2\n" + example["ibl_code"]
        n = db.add_examples_batch([example])
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
