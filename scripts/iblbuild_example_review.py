#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""용례 재검토 관문 — 어휘의 **행동 계약**이 바뀌면 그 액션의 용례를 다시 보게 한다 (2026-09-18).

왜: 실행기억(해마)의 용례는 "이 의도엔 이 문장"이라는 주장인데, 그 주장은 액션의 행동에 기대어 있다.
행동이 바뀌면 용례는 **문법적으로 멀쩡한 채** 거짓이 된다 — 어떤 검사기도 잡지 못한다(구문·인자·타입·
어휘 생존 전부 초록). 09-17 전수 정독의 H 부류 27건이 그랬다: `[self:memory]{op:"save"}` 는 09-12 부터
저장하지 않는데 용례 15건이 "기억해둬"에 회상됐고, `sense:phone` 은 결제 알림 전용이 됐는데 카톡·문자
확인 용례가 남아 있었다. 그 변화들은 전부 사전의 계약 필드(target_description·ops.returns·
ops.side_effect·ops.values·implementation)에 드러나 있었다 — 읽는 절차가 없었을 뿐이다.

무엇: 액션마다 계약 필드의 지문을 원장(`data/ibl_example_review.json`)에 둔다. 빌드 `--check` 는 지금의
지문과 원장을 대조해, 달라진 액션이 있으면 **바뀐 필드와 그 액션을 쓰는 로컬 용례 수**를 말하고 실패한다.
사람이(또는 AI 가) 용례를 읽고 고친 뒤 `--ack` 로 원장을 올린다. 원장은 빌드가 쓰지 않는다 — 읽었다는
서명은 읽은 쪽이 남긴다.

  python3 scripts/iblbuild_example_review.py                 # 상태(바뀐 액션·필드·용례 수)
  python3 scripts/iblbuild_example_review.py --show node:action   # 그 액션의 용례를 읽는다
  python3 scripts/iblbuild_example_review.py --ack node:action …  # 읽었다(원장 갱신). --ack-all = 전부

지문에 넣는 것은 **행동을 말하는 필드**뿐이다(예산·표시용 필드는 뺀다). 핸들러 코드만 바뀌고 사전이 안
바뀐 변화는 여기서 못 잡는다 — 그건 "어휘 변경 시 문서 표면 갱신 의무"(new_action_checklist.md)가 막는 자리다.
"""
import hashlib, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "data" / "ibl_example_review.json"
# 행동 계약 — 이 필드가 바뀌면 "같은 문장이 다른 일을 한다"가 가능해진다.
CONTRACT_FIELDS = ("description", "target_description", "implementation", "returns", "returns_variants",
                   "target_key", "params", "aliases", "ops", "side_effect", "runs_on", "router", "tool")


def _h(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:12]


def fingerprints(data: dict) -> dict:
    """{"node:action": {필드: 지문}} — 없는 필드는 싣지 않는다(있다가 없어지는 것도 변화로 잡힌다)."""
    out = {}
    for node, nd in (data.get("nodes") or {}).items():
        for action, ad in ((nd or {}).get("actions") or {}).items():
            if isinstance(ad, dict):
                out[f"{node}:{action}"] = {f: _h(ad[f]) for f in CONTRACT_FIELDS if ad.get(f) is not None}
    return out


def load_ledger() -> dict:
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8")).get("actions", {})
    except Exception:
        return {}


def changed_actions(data: dict) -> dict:
    """{"node:action": [바뀐 필드…]} — 원장에 없는 액션은 ["(신규)"]. 은퇴한 액션은 말하지 않는다."""
    ledger, out = load_ledger(), {}
    for q, fp in fingerprints(data).items():
        old = (ledger.get(q) or {}).get("fields")
        if old is None:
            out[q] = ["(신규)"]
        elif old != fp:
            out[q] = sorted(f for f in set(old) | set(fp) if old.get(f) != fp.get(f))
    return out


def examples_of(q: str, root: Path = ROOT) -> list:
    """로컬 실행기억에서 그 액션을 쓰는 용례(id, intent, code). DB 가 없는 기계(CI)에서는 빈 목록."""
    db = root / "data" / "ibl_usage.db"
    if not db.exists():
        return []
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        pat = re.compile(r"\[" + re.escape(q) + r"\]|\b" + re.escape(q) + r"\{")   # 조건식의 `node:action{…}` 꼴 포함
        return [(i, it, c) for i, it, c in con.execute(
            "select id, intent, ibl_code from ibl_examples where ibl_code like ?", (f"%{q}%",)) if pat.search(c)]
    except Exception:
        return []


def validate_example_review(data: dict, root: Path = ROOT) -> list:
    issues = []
    for q, fields in sorted(changed_actions(data).items()):
        n = len(examples_of(q, root))
        issues.append(f"{q}: 계약이 바뀌었다 {fields} — 이 액션을 쓰는 용례 {n}건을 재검토할 것 "
                      f"(`python3 scripts/iblbuild_example_review.py --show {q}` 로 읽고, 고친 뒤 `--ack {q}`)")
    return issues


def ack(data: dict, names) -> int:
    fps, ledger = fingerprints(data), load_ledger()
    today = time.strftime("%Y-%m-%d")
    targets = list(changed_actions(data)) if names == "all" else list(names)
    done = 0
    for q in targets:
        if q not in fps:
            print(f"  ✗ {q}: 그런 액션이 없다", file=sys.stderr)
            continue
        ledger[q] = {"fields": fps[q], "reviewed": today, "examples": len(examples_of(q))}
        done += 1
    ledger = {q: v for q, v in ledger.items() if q in fps}          # 은퇴한 액션은 원장에서 내린다
    LEDGER.write_text(json.dumps({
        "_comment": "용례 재검토 원장 — scripts/iblbuild_example_review.py --ack 로만 갱신(빌드는 읽기만). "
                    "fields=액션 계약 필드의 지문, reviewed=그 계약으로 용례를 읽은 날, examples=그때의 로컬 용례 수.",
        "actions": dict(sorted(ledger.items()))}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return done


def _load_data() -> dict:
    import yaml
    return yaml.safe_load((ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8")) or {}


def main() -> int:
    data, a = _load_data(), sys.argv[1:]
    if "--show" in a:
        q = a[a.index("--show") + 1]
        rows = examples_of(q)
        print(f"{q} — 용례 {len(rows)}건 · 바뀐 필드 {changed_actions(data).get(q, '없음')}")
        ad = ((data.get("nodes") or {}).get(q.split(":")[0], {}).get("actions") or {}).get(q.split(":", 1)[1]) or {}
        print(f"  지금의 계약: {str(ad.get('description') or '')[:200]}\n  인자·op: {str(ad.get('target_description') or '')[:400]}")
        for i, it, c in rows:
            print(f"  #{i} {it[:50]!r}\n      " + " ⏎ ".join(c.split("\n"))[:240])
        return 0
    if "--ack-all" in a:
        print(f"원장 갱신 {ack(data, 'all')}건")
        return 0
    if "--ack" in a:
        print(f"원장 갱신 {ack(data, [x for x in a[a.index('--ack') + 1:] if not x.startswith('--')])}건")
        return 0
    issues = validate_example_review(data)
    for i in issues:
        print("  ✗", i)
    print(f"재검토 대기 {len(issues)}건" if issues else "용례 재검토 원장 일치 ✓")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
