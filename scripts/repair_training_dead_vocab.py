#!/usr/bin/env python3
"""repair_training_dead_vocab.py — 훈련 파일의 죽은 어휘 정리 (2026-08-22).

라이브 코퍼스(`data/ibl_usage.db`)는 어휘 은퇴 때마다 이관돼 죽은 어휘 0건이지만,
`data/training/ibl_training_balanced_20260516.json`(2026-05-16 스냅샷)은 부분적으로만
따라와서 은퇴 어휘를 다수 안고 있다. 트레이너는 **DB 와 data/training/*.json 을 둘 다**
읽으므로(ibl_embedding_trainer.py:542 glob), 이 파일이 다음 풀 재학습에 죽은 어휘를
그대로 되살린다.

정리 원칙 — 추측하지 않는다. 라이브 DB 가 이미 내린 이관 판정을 권위로 쓴다.
  A. intent 가 DB 에 있으면 → DB 의 (이관된) ibl_code 로 **교체**. 추측 0.
  B. A 에서 파생한 액션 매핑(dead→new)이 **일관**되고, 옛 파라미터가 새 액션의
     허용키를 통과하면(check_params) → 재기입. 하나라도 어긋나면 B 를 포기한다.
  C. 나머지 → **드롭**. 존재하지 않는 액션을 가르치는 용례는 정보가 아니라 잡음이고,
     후계가 불분명한 것을 지어내면 잘못된 파라미터를 가르치게 된다.

실행: .venv/bin/python3 scripts/repair_training_dead_vocab.py [--apply]
      (기본은 dry-run — 무엇이 교체/재기입/드롭되는지 보고만 한다)
"""
import sys, os, json, sqlite3, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
import yaml
from ibl_parser import parse, IBLSyntaxError
from ibl_param_vocab import check_params

ROOT = os.path.join(os.path.dirname(__file__), "..")
TRAINING = os.path.join(ROOT, "data", "training", "ibl_training_balanced_20260516.json")
DB = os.path.join(ROOT, "data", "ibl_usage.db")
APPLY = "--apply" in sys.argv

REG = yaml.safe_load(open(os.path.join(ROOT, "data", "ibl_nodes.yaml"), encoding="utf-8"))["nodes"]


def leaves(steps, out):
    for st in steps:
        if not isinstance(st, dict):
            continue
        if st.get("_node"):
            out.append((st["_node"], st.get("action"), st.get("params") or {}))
        for k in ("branches", "_fallback_chain", "body", "catch", "finally", "_branch_steps"):
            v = st.get(k)
            if isinstance(v, list):
                leaves(v, out)
            elif isinstance(v, dict):
                leaves([v], out)


def dead_of(code):
    """코드가 참조하는 죽은 (노드, 액션) 목록. 문법 실패는 ('?','?') 하나로."""
    try:
        steps = parse(code or "")
    except IBLSyntaxError:
        return [("?", "?", {})]
    acts = []
    leaves(steps, acts)
    return [(n, a, p) for n, a, p in acts
            if n not in REG or a not in REG[n]["actions"]]


data = json.load(open(TRAINING, encoding="utf-8"))
conn = sqlite3.connect(DB)
db_by_intent = {}
for intent, code in conn.execute("SELECT intent, ibl_code FROM ibl_examples"):
    db_by_intent.setdefault(intent, code)   # 첫 것 사용 (중복 intent 는 사실상 동일본)
conn.close()

rotten = [(i, ex) for i, ex in enumerate(data) if dead_of(ex.get("ibl_code"))]
print(f"훈련 파일 {len(data)}건 · 죽은 어휘 항목 {len(rotten)}건\n")

# ── A. DB 권위 교체 ────────────────────────────────────────────────────────
replaced, rest = [], []
for idx, ex in rotten:
    new = db_by_intent.get(ex.get("intent"))
    if new and not dead_of(new):
        replaced.append((idx, ex.get("ibl_code"), new))
    else:
        rest.append((idx, ex))
print(f"A. DB 권위 교체: {len(replaced)}건")

# ── B. 파생 액션 매핑 (일관될 때만) ────────────────────────────────────────
pairs = collections.defaultdict(set)
for _idx, old, new in replaced:
    old_dead = {f"{n}:{a}" for n, a, _ in dead_of(old)}
    new_acts = []
    leaves(parse(new), new_acts)
    new_set = {f"{n}:{a}" for n, a, _ in new_acts}
    if len(old_dead) == 1 and len(new_set) == 1:
        pairs[old_dead.pop()].add(new_set.pop())
mapping = {k: list(v)[0] for k, v in pairs.items() if len(v) == 1}
ambiguous = {k: sorted(v) for k, v in pairs.items() if len(v) > 1}
print(f"   파생 매핑 {len(mapping)}개" + (f" · 모호해서 버린 것 {len(ambiguous)}개 {ambiguous}" if ambiguous else ""))

rewritten, dropped = [], []
for idx, ex in rest:
    dead = dead_of(ex.get("ibl_code"))
    if len(dead) != 1:
        dropped.append((idx, ex, "죽은 어휘 2개 이상 또는 문법 실패"))
        continue
    n, a, params = dead[0]
    tgt = mapping.get(f"{n}:{a}")
    if not tgt:
        dropped.append((idx, ex, f"{n}:{a} 후계 불명"))
        continue
    tn, ta = tgt.split(":")
    warn = check_params(tn, ta, params, REG[tn]["actions"][ta])
    if warn and warn.get("unknown"):
        dropped.append((idx, ex, f"{n}:{a}→{tgt} 이나 파라미터 불일치 {warn['unknown']}"))
        continue
    code = ex["ibl_code"].replace(f"[{n}:{a}]", f"[{tn}:{ta}]")
    if dead_of(code):
        dropped.append((idx, ex, f"{n}:{a}→{tgt} 재기입 후에도 죽은 어휘 잔존"))
        continue
    rewritten.append((idx, ex["ibl_code"], code))
print(f"B. 매핑 재기입: {len(rewritten)}건")
print(f"C. 드롭: {len(dropped)}건")

reasons = collections.Counter(r for _, _, r in dropped)
for r, c in reasons.most_common():
    print(f"     {c:3}  {r}")

if not APPLY:
    print("\n(dry-run — 적용하려면 --apply)")
    for idx, old, new in (replaced[:3] + rewritten[:3]):
        print(f"  · {old[:62]}\n    → {new[:62]}")
    sys.exit(0)

for idx, _old, new in replaced + rewritten:
    data[idx]["ibl_code"] = new
drop_idx = {idx for idx, _, _ in dropped}
out = [ex for i, ex in enumerate(data) if i not in drop_idx]
with open(TRAINING, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n적용 완료 — {len(data)} → {len(out)}건")
still = [ex for ex in out if dead_of(ex.get("ibl_code"))]
print("남은 죽은 어휘 항목:", len(still))
assert not still, still[:3]
