#!/usr/bin/env python3
"""seed_self_check_source.py — [sense:self_check]{op:"results"} 의 source 축 시드 (2026-08-22).

커밋 bcb46f1(V18-2)로 열린 자리를 해마에 앉힌다: **건강 원장은 둘이다.**
  - `source: "self_check"` (기본) = 자가점검 원장(self_checks) — 매일 도는 전수 점검
  - `source: "usage"`             = 실사용 원장(action_health) — **"만성 실패" 경보가 세는 곳**
  - `source: "all"`               = 둘 다 (같은 칸 모양이라 한 파이프에서 대조된다)

★왜 시드가 필요한가: 이 어휘를 만든 턴이 증류한 용례(id 4146)는 intent 가
"경보나 알림의 근거가 되는 데이터가 기본 조회에서…" 라는 **긴 추상문**이다. 사람은
"만성 실패 왜 났어?" 라고 친다 — 긴 intent 는 짧은 질의와 겨루지 못한다(08-22 실측
부류). 사람이 실제로 치는 길이로 같은 패턴을 다시 앉힌다.

★문형 편중 교정도 겸한다: 조합 지표에서 **축적(수집→저장)이 파이프 안 1건**으로 최저다.
같은 어휘를 조회로만 가르치지 않고 저장·발신 꼬리까지 붙여 가르친다.

실행: .venv/bin/python3 scripts/seed_self_check_source.py [--dry-run]
      (파서·어휘 검증을 통과해야만 적재된다 — 시드는 교재라 틀리면 그대로 학습된다)
"""
import sys, os, json, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

NEW = [
    # ── ① 경보 → 근거 (이 수리의 핵심 자리) ─────────────────────────────────
    ("만성 실패 경보 근거 보여줘",
     '[sense:self_check]{op: "results", source: "usage", limit: 200} >> [table:filter]{where: "success == false"}',
     "sense,table", "system", "self_check,source,usage,만성실패,근거"),
    ("실사용에서 뭐가 실패했어?",
     '[sense:self_check]{op: "results", source: "usage", limit: 200} >> [table:filter]{where: "success == false"}',
     "sense,table", "system", "self_check,source,usage,실패"),
    ("자가점검 말고 실제로 쓴 기록으로 봐줘",
     '[sense:self_check]{op: "results", source: "usage"}',
     "sense", "system", "self_check,source,usage,원장구분"),
    ("점검이랑 실사용 둘 다 합쳐서 최근 실패 보여줘",
     '[sense:self_check]{op: "results", source: "all", limit: 200} >> [table:filter]{where: "success == false"}',
     "sense,table", "system", "self_check,source,all,대조"),

    # ── ② 집계·투영 (근거를 읽을 수 있는 모양으로) ──────────────────────────
    ("요즘 자꾸 실패하는 액션 순위 뽑아줘",
     '[sense:self_check]{op: "results", source: "usage", limit: 500} >> [table:filter]{where: "success == false"} '
     '>> [table:groupby]{by: "title"} >> [table:sort]{by: "count", desc: true} >> [table:take]{n: 5}',
     "sense,table", "system", "self_check,source,usage,groupby,순위"),
    ("실패한 것들 오류 문구까지 같이 보여줘",
     '[sense:self_check]{op: "results", source: "usage", limit: 200} >> [table:filter]{where: "success == false"} '
     '>> [table:select]{columns: ["title", "error", "checked_at", "source"]}',
     "sense,table", "system", "self_check,source,usage,select,오류문"),
    ("지난번 본 이후로 새로 생긴 실사용 실패만 보여줘",
     '[sense:self_check]{op: "results", source: "usage", limit: 500} >> [table:filter]{where: "success == false"} '
     '>> [table:since]{key: "실사용실패", by: "checked_at"}',
     "sense,table", "system", "self_check,source,usage,since,검침"),

    # ── ③ 축적 — 수집→저장 (조합 지표에서 가장 결핍된 문형) ─────────────────
    ("실사용 실패 목록 파일로 남겨줘",
     '[sense:self_check]{op: "results", source: "usage", limit: 500} >> [table:filter]{where: "success == false"} '
     '>> [self:write]{path: "실사용_실패.md"}',
     "sense,table,self", "system", "self_check,source,usage,축적,저장"),
    ("실패 기록 표로 저장해줘",
     '[sense:self_check]{op: "results", source: "all", limit: 500} >> [table:filter]{where: "success == false"} '
     '>> [table:spreadsheet]{path: "action_failures.xlsx"}',
     "sense,table", "system", "self_check,source,all,축적,표"),

    # ── ④ 발신 ─────────────────────────────────────────────────────────────
    ("실사용에서 실패 나면 알려줘",
     '[sense:self_check]{op: "results", source: "usage", limit: 200} >> [table:filter]{where: "success == false"} '
     '>> [table:take]{n: 10} >> [self:notify_user]{title: "실사용 실패"}',
     "sense,table,self", "system", "self_check,source,usage,알림,발신"),
    ("아침마다 실사용 실패만 정리해서 알려줘",
     '[self:trigger]{op: "create", name: "실사용 실패 점검", cron: "0 8 * * *", '
     'do: "[sense:self_check]{op: \'results\', source: \'usage\', limit: 500} '
     '>> [table:filter]{where: \'success == false\'} >> [self:notify_user]{title: \'실사용 실패\'}"}',
     "self,sense,table", "system", "self_check,source,usage,trigger,정기"),

    # ── ⑤ 짧은 표현 (사람이 실제로 치는 길이) ───────────────────────────────
    ("실사용 실패",
     '[sense:self_check]{op: "results", source: "usage"} >> [table:filter]{where: "success == false"}',
     "sense,table", "system", "self_check,source,usage,짧은표현"),
    ("경보 근거가 뭐야",
     '[sense:self_check]{op: "results", source: "usage", limit: 200} >> [table:filter]{where: "success == false"}',
     "sense,table", "system", "self_check,source,usage,근거,짧은표현"),
    ("둘 다 봐줘",
     '[sense:self_check]{op: "results", source: "all", limit: 100}',
     "sense", "system", "self_check,source,all,짧은표현"),
    # 1차 시딩 후 회상 실측: 검침(since) 용례가 짧은 질의로는 안 잡혔다("새로 생긴 실패만"
    # → self:goal log 가 top1). 사람이 치는 길이로 같은 패턴을 다시 앉힌다.
    ("새로 생긴 실패만 보여줘",
     '[sense:self_check]{op: "results", source: "usage", limit: 500} >> [table:filter]{where: "success == false"} '
     '>> [table:since]{key: "실사용실패", by: "checked_at"}',
     "sense,table", "system", "self_check,source,usage,since,짧은표현"),
    ("지난번 이후 새 실패 있어?",
     '[sense:self_check]{op: "results", source: "usage", limit: 500} >> [table:filter]{where: "success == false"} '
     '>> [table:since]{key: "실사용실패", by: "checked_at"}',
     "sense,table", "system", "self_check,source,usage,since,짧은표현"),
]


def _preflight():
    """시드는 교재다 — 넣기 전에 ①파싱 ②어휘 실존을 확인한다(중첩 pipeline 안까지)."""
    import yaml
    from ibl_parser import parse, IBLSyntaxError
    reg = yaml.safe_load(open(os.path.join(ROOT, "data", "ibl_nodes.yaml"), encoding="utf-8"))
    known = {f"{n}:{a}" for n, body in reg["nodes"].items()
             for a in (body.get("actions") or {})}
    import re
    bad = []
    for intent, code, *_ in NEW:
        try:
            parse(code)
        except IBLSyntaxError as e:
            bad.append((intent, f"파싱 실패: {e}"))
            continue
        # 중첩 IBL(pipeline·do)도 따로 판다 — 이스케이프 정상형인지까지 본다
        for nested in re.findall(r'(?:pipeline|do)\s*:\s*"((?:[^"\\]|\\.)*)"', code):
            try:
                parse(nested.encode().decode("unicode_escape"))
            except Exception as e:
                bad.append((intent, f"중첩 파싱 실패: {e}"))
        for node, act in re.findall(r"\[(\w+):(\w+)\]", code):
            key = f"{node}:{act}"
            if key not in known:
                bad.append((intent, f"없는 어휘: {key}"))
                continue
            # ★op 값도 본다(2026-08-22 실측): 파싱·어휘 실존만 보던 검사는
            # `[self:trigger]{op:"add"}` 를 통과시켰다 — 실제 enum 은 create 다.
            # 파라미터는 대부분 미선언이라 자동 검증이 안 되지만, op 는 선언돼 있다.
            spec = (reg["nodes"][node]["actions"][act].get("ops") or {})
            values = set((spec.get("values") or {}).keys())
            if values:
                m = re.search(re.escape(f"[{node}:{act}]") + r'\{[^}]*?op\s*:\s*["\']([\w_]+)["\']', code)
                if m and m.group(1) not in values:
                    bad.append((intent, f"{key} 의 op '{m.group(1)}' 없음 — {sorted(values)}"))
    return bad


# 라이브 실행으로 확인 가능한(부작용 없는) 어휘 — 이 밖은 실행하지 않는다.
_READ_ONLY = {"sense:self_check", "table:filter", "table:take", "table:select",
              "table:groupby", "table:sort"}


def _live_check():
    """읽기 전용 시드는 실제로 돌려 본다 — 교재가 도는지 확인하는 가장 강한 검사."""
    import re, json, urllib.request
    ok = skipped = 0
    for intent, code, *_ in NEW:
        acts = {f"{n}:{a}" for n, a in re.findall(r"\[(\w+):(\w+)\]", code)}
        if not acts <= _READ_ONLY:
            skipped += 1
            continue
        req = urllib.request.Request("http://127.0.0.1:8765/ibl/execute",
                                     data=json.dumps({"code": code}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=60))
        except Exception as e:
            print(f"  ✗ {intent!r}: 라이브 호출 실패 {e}")
            return False
        if not r.get("success") or r.get("steps_completed") != r.get("steps_total"):
            print(f"  ✗ {intent!r}: {str(r)[:200]}")
            return False
        ok += 1
    print(f"라이브 확인 ✓ {ok}건 실행 통과 · {skipped}건 미실행(부작용 있는 어휘 — 실행하지 않는다)")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="검증만 하고 적재하지 않는다")
    ap.add_argument("--live", action="store_true",
                    help="읽기 전용 시드를 라이브 백엔드에서 실제로 실행해 본다(:8765)")
    args = ap.parse_args()

    bad = _preflight()
    if bad:
        for intent, why in bad:
            print(f"  ✗ {intent!r}: {why}")
        sys.exit(f"검증 실패 {len(bad)}건 — 적재 중단 (틀린 시드는 그대로 학습된다)")
    print(f"검증 통과 ✓ ({len(NEW)}건 파싱·어휘·op enum)")
    if args.live and not _live_check():
        sys.exit("라이브 확인 실패 — 적재 중단")
    if args.dry_run:
        return

    # ★트레이너는 DB 와 data/training/*.json 을 **둘 다** 읽는다 — 양쪽에 넣는다.
    from ibl_usage_db import IBLUsageDB
    import sqlite3
    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단"
    conn = sqlite3.connect(os.path.join(ROOT, "data", "ibl_usage.db"))
    existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
    conn.close()
    batch = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2,
              "source": "manual_seed", "tags": t} for i, c, n, cat, t in NEW if i not in existing]
    print(f"시드 추가: {db.add_examples_batch(batch)}건 (중복 스킵 {len(NEW) - len(batch)}건)")

    dist_path = os.path.join(ROOT, "data", "training", "ibl_distilled.json")
    with open(dist_path, encoding="utf-8") as f:
        dist = json.load(f)
    have = {d.get("intent") for d in dist}
    added = 0
    for i, c, n, cat, t in NEW:
        if i not in have:
            dist.append({"intent": i, "ibl_code": c, "nodes": n, "category": cat,
                         "difficulty": 2, "source": "manual_seed"})
            added += 1
    with open(dist_path, "w", encoding="utf-8") as f:
        json.dump(dist, f, ensure_ascii=False, indent=2)
    print(f"ibl_distilled: +{added}건 → {len(dist)}건")


if __name__ == "__main__":
    main()
