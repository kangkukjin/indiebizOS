#!/usr/bin/env python3
"""replay_idioms.py — 과거 에피소드에 관용구 질문을 되돌려 묻는다 (2026-09-04, 사용자 판정
"천 개 넘는 에피소드가 있으니 자주 쓰이는 관용구 10개쯤은 지금 찾을 수 있다").

원리(docs/IBL_IDIOM_TIER_HANDOFF.md 와 같은 길, 시점만 과거):
- 뽑는 주체는 같은 반성기(경량 AI)다 — `ibl_usage_rag._build_distill_prompt` 의 두 번째 질문
  「이 주행에서 되풀이될 모양은?」을 에피소드 원장(episode_log)의 실행 궤적에 그대로 묻는다.
  코드 분류기(n-gram 마이닝)로 관용구를 *만들지* 않는다 — 기계는 접지·순서·슬롯 되돌림·개인
  명사만 검증하고(같은 관문 `_phrase_grounded` 등), **빈도**는 궤적 원장(trajectory_event 의
  머리 열)으로 증명한다: 같은 머리 열이 여러 주행에서 되풀이된 골격만 남긴다(결정화 사다리 —
  빈도가 증명했을 때 데이터로만).
- 저장은 라이브 증류와 같은 단일 경로(`_distill_phrase` → add_example category='phrase' +
  ibl_distilled.json). 시딩 경로(add_examples_batch)가 아니다.

사용:
    .venv/bin/python scripts/replay_idioms.py                # dry-run: 후보 목록만
    .venv/bin/python scripts/replay_idioms.py --limit 200    # 되돌려 물을 에피소드 수(최근순)
    .venv/bin/python scripts/replay_idioms.py --apply --top 12
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")        # ★경량 AI 는 키가 먼저 — boot_paths 보다 앞
import boot_paths  # noqa: E402,F401

USE_RE = re.compile(r" tool_use (\S+) (\{.*)$")
RESULT_RE = re.compile(r" tool_result (.*)$")
HEAD_RE = re.compile(r"\[([a-z_-]+:[a-z_0-9]+)\]")
QUOTED_RE = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'")


def _strip(s: str) -> str:
    return QUOTED_RE.sub('""', s or "")


def heads_of(code: str) -> tuple:
    return tuple(HEAD_RE.findall(_strip(code)))


def _result_ok(body: str):
    b = body[:200]
    if re.match(r'\{"success"\s*:\s*true', b) or re.match(r'\{"result"\s*:\s*"\{\\"success\\"\s*:\s*true', b) \
            or b.startswith('{"items"') or b.startswith('{"result":"Successfully'):
        return True
    if re.match(r'\{"success"\s*:\s*false', b) or '"error"' in b[:120] or 'is_error' in b[:120]:
        return False
    return None   # 판정 불능(빈 결과·절단) → 성공으로 치지 않는다


def parse_episode(log: str):
    """로그 → [{code, ok}] (execute_ibl 만, 실행 순서). tool_use 큐와 tool_result 를 순서대로 짝짓는다."""
    pending, calls = [], []
    for line in log.splitlines():
        m = USE_RE.search(line)
        if m:
            name, body = m.group(1), m.group(2)
            code = None
            if name.endswith("execute_ibl"):
                try:
                    code = (json.loads(body) or {}).get("code")
                except Exception:
                    mm = re.search(r'"code"\s*:\s*"(.*)"\s*\}?\s*$', body)
                    code = json.loads('"' + mm.group(1) + '"') if mm else None
            pending.append(code)
            continue
        m = RESULT_RE.search(line)
        if m and pending:
            code = pending.pop(0)
            if code:
                from episode_logger import TRUNC_MARK_RE
                if TRUNC_MARK_RE.search(code):
                    continue          # 로그가 자른 문장은 원문이 없다 — 되돌려 묻기·접지 모두에서 뺀다
                calls.append({"code": code.strip(), "ok": _result_ok(m.group(1))})
    return calls


def split_statements(code: str):
    """프로그램 본문 → 문장 목록. 따옴표·괄호 깊이 0 의 줄바꿈만 경계(document blocks 처럼 여러 줄에 걸친 문장 보존), 주석 줄 제외."""
    out, buf, q, depth = [], [], None, 0
    i, n = 0, len(code or "")
    while i < n:
        ch = code[i]
        if q:
            buf.append(ch)
            if ch == "\\" and i + 1 < n:
                buf.append(code[i + 1]); i += 2; continue
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch; buf.append(ch)
        elif ch in "{[(":
            depth += 1; buf.append(ch)
        elif ch in "}])":
            depth = max(0, depth - 1); buf.append(ch)
        elif ch == "\n" and depth == 0:
            out.append("".join(buf).strip()); buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return [x for x in out if x and not x.startswith("#")]


def load_programs(paths):
    """완주가 실증된 프로그램(JSON {code}) → 에피소드 꼴. 문장 = 빈 줄·주석 뺀 각 줄(한 프로그램 안에서 실행 순서 그대로)."""
    out = []
    for i, p in enumerate(paths):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
            code = d.get("code") if isinstance(d, dict) else None
        except Exception:
            code = None
        if not code:
            print(f"[replay] 프로그램 읽기 실패: {p}")
            continue
        lines = split_statements(code)
        name = Path(p).stem
        out.append({"id": -(i + 1), "when": "2026-08-28",
                    "message": (f"완주 프로그램 {name} 에서 관용구를 짓는다. 이것은 실제로 끝까지 돌아 산출물을 낸 프로그램이므로 "
                                "되풀이될 모양은 반드시 있다 — 다음 호·다른 주제에서 다시 쓸 뼈대 문장 3~8개를 실행 순서 그대로 골라라."),
                    "calls": lines, "program": str(p)})
    return out


def load_episodes(db_path: Path, limit: int, min_ok: int = 3):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out = []
    for r in conn.execute("SELECT id, started_at, user_message, log FROM episode_log "
                          "WHERE (source IS NULL OR source='usage') ORDER BY id DESC"):
        if not (r["user_message"] or "").strip():
            continue
        calls = parse_episode(r["log"] or "")
        ok = [c["code"] for c in calls if c["ok"]]
        if len(ok) >= min_ok:
            out.append({"id": r["id"], "when": r["started_at"], "message": r["user_message"], "calls": ok})
        if len(out) >= limit:
            break
    conn.close()
    return out


def trajectory_shapes(db_path: Path) -> Counter:
    """궤적 원장의 머리 열 → 그 열(연속 n=2..6)이 성공으로 등장한 *주행 수*."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    runs = defaultdict(list)
    for run_id, kind, data in conn.execute(
            "SELECT run_id, kind, data FROM trajectory_event WHERE source='usage' "
            "AND kind IN ('ibl.started','ibl.finished') ORDER BY rowid"):
        try:
            d = json.loads(data or "{}")
        except Exception:
            d = {}
        if kind == "ibl.started":
            runs[run_id].append([tuple(d.get("actions") or []), None])
        else:
            lst = runs[run_id]
            if lst and lst[-1][1] is None:
                lst[-1][1] = bool(d.get("success"))
    conn.close()
    per = defaultdict(set)
    for rid, v in runs.items():
        seq = [a for a, ok in v if ok and a]
        for n in range(2, 7):
            for i in range(len(seq) - n + 1):
                per[tuple(seq[i:i + n])].add(rid)
    return Counter({k: len(v) for k, v in per.items()})


def ask(ep: dict, topic_map: str, system_prompt: str):
    import ibl_usage_rag as rag
    from consciousness_agent import oneshot_ai_call
    from runtime_utils import parse_first_json
    tool_log = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(ep["calls"][:40]))
    prompt = rag._build_distill_prompt(ep["message"], tool_log, "", topic_map)
    try:
        res = oneshot_ai_call(prompt=prompt, system_prompt=system_prompt, role="background")
        d = parse_first_json(res or "")
    except Exception as e:
        return {"episode": ep["id"], "reject": f"호출 실패: {e}"}
    if not isinstance(d, dict):
        return {"episode": ep["id"], "reject": "JSON 아님"}
    return {"episode": ep["id"], "distilled": d}


def gate(ep: dict, d: dict):
    """라이브 증류와 같은 관문 — 통과하면 후보, 아니면 사유."""
    import hippo_tree
    import ibl_usage_rag as rag
    from ibl_param_vocab import code_syntax_error, check_code_params
    phrase = d.get("phrase")
    slots = d.get("slots") if isinstance(d.get("slots"), dict) else {}
    topic = hippo_tree.norm_topic(str(d.get("topic") or ""))
    intent = str(d.get("intent") or "").strip()
    if not isinstance(phrase, list) or not phrase:
        return None, "phrase 없음(되풀이될 모양 없음)"
    phrase = [x for p in phrase if isinstance(p, str) for x in split_statements(p)]
    n = len(phrase)
    if not (hippo_tree.PHRASE_MIN_SENTENCES <= n <= hippo_tree.PHRASE_MAX_SENTENCES):
        return None, f"문장 수 {n}"
    if not topic:
        return None, "topic 없음"
    phrase = [rag._normalize_slot_quoting(p, slots) for p in phrase]
    why = rag._phrase_grounded(phrase, slots, ep["calls"])
    if why:
        return None, "접지: " + why
    code = hippo_tree.join_sentences(phrase)
    err = code_syntax_error(code)
    if err:
        return None, "구문: " + str(err)
    if not rag._validate_ibl_actions(code):
        return None, "미존재 액션"
    issues = check_code_params(code)
    if issues:
        return None, "미인식 파라미터: " + str([(i['action'], i['unknown']) for i in issues])
    why = rag._phrase_private_reason(code)
    if why:
        return None, "개인 명사: " + why
    return {"episode": ep["id"], "when": ep["when"], "intent": intent or ep["message"][:80], "topic": topic,
            "phrase": phrase, "slots": slots, "code": code,
            "heads": tuple(heads_of(s) for s in phrase), "n_slots": len(hippo_tree.slot_names(code)),
            "calls": ep["calls"]}, None


def _calls_of(db_path: Path, episode_id: int):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    row = conn.execute("SELECT log FROM episode_log WHERE id=?", (episode_id,)).fetchone()
    conn.close()
    return [c["code"] for c in parse_episode(row[0] if row else "") if c["ok"]]


def save_phrases(items, db_path: Path):
    """라이브 증류와 같은 단일 경로로 저장. items = [{intent, topic, phrase, slots, episode, calls?}]."""
    import hippo_tree
    import ibl_usage_rag as rag
    from ibl_usage_db import IBLUsageDB
    from thread_context import clear_phrase_recall
    db = IBLUsageDB()
    if hasattr(db, "_load_model_sync"):
        db._load_model_sync()      # 벡터 색인까지 즉시 — 안 그러면 조용히 임베딩 없는 행이 된다
    existing = set()
    with db._get_connection() as conn:
        for (code,) in conn.execute("SELECT ibl_code FROM ibl_examples WHERE category='phrase'"):
            existing.add(tuple(heads_of(s) for s in hippo_tree.split_sentences(code)))
    saved = 0
    for it in items:
        heads = tuple(heads_of(s) for s in it["phrase"])
        if heads in existing:
            print(f"[replay] 이미 있는 골격 — 건너뜀: {it['intent'][:50]}")
            continue
        calls = it.get("calls") or _calls_of(db_path, it["episode"])
        clear_phrase_recall()
        ok = rag._distill_phrase(it["intent"], {"phrase": it["phrase"], "slots": it.get("slots") or {}},
                                 calls, it["topic"], tool_calls=[], turn_tokens=None)
        saved += bool(ok)
        if ok:
            existing.add(heads)
    print(f"[replay] 저장 {saved}건")
    return saved


def _fill(sentence: str, slots: dict) -> str:
    import re as _re
    def _v(m):
        k = m.group(1).strip()
        v = slots.get(k)
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        return str(v) if v is not None else m.group(0)
    s = _re.sub(r"\$\{([^}]+)\}", _v, sentence)
    s = _re.sub(r"\$([A-Za-z_\uac00-\ud7a3][\w\uac00-\ud7a3]*)", lambda m: _v(m) if m.group(1) in slots else m.group(0), s)
    return s


def rehearse(path: Path, db_path: Path, apply: bool, project_id: str = ""):
    """설계한 관용구의 리허설 — 슬롯을 채운 문장들을 한 프로그램으로 라이브 백엔드에서 실행한다.
    성공 = 접지(그 실행이 곧 주행). 실패는 오류 요지를 남긴다 — 언어 공백(문법·어휘 개정 후보)의 신호."""
    import urllib.request
    items = json.loads(path.read_text(encoding="utf-8"))
    ok_items, fails = [], []
    for it in items:
        lines = [_fill(sent, it.get("slots") or {}) for sent in it["phrase"]]
        setup = [_fill(sent, it.get("slots") or {}) for sent in (it.get("setup") or [])]
        program = "\n".join(setup + lines)      # setup 은 무대 준비(관용구 밖) — 접지 호출에는 넣지 않는다
        body = json.dumps({"code": program, **({"project_id": project_id} if project_id else {})}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:8765/ibl/execute", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                res = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            res = {"success": False, "error": f"호출 실패: {e}"}
        success = bool(res.get("success", False)) and not res.get("error")
        digest = (res.get("error") or res.get("message") or "")
        if not success:
            tb = res.get("traceback") or {}
            digest = f"{digest} | {str(tb.get('error') or '')[:200]} @ {tb.get('frames')}"
        print(f"\n[rehearse] {'✓' if success else '✗'} {it['intent'][:60]}")
        for j, l in enumerate(lines, 1):
            print(f"   {j}. {l[:160]}")
        if success:
            ok_items.append({**it, "calls": lines, "episode": 0})
        else:
            print(f"   → {str(digest)[:400]}")
            fails.append({"intent": it["intent"], "error": str(digest)[:800]})
    out = path.with_name(path.stem + "_result.json")
    out.write_text(json.dumps({"ok": [{k: v for k, v in o.items() if k != "calls"} for o in ok_items], "fail": fails},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[rehearse] 성공 {len(ok_items)} · 실패 {len(fails)} → {out}")
    if apply and ok_items:
        save_phrases(ok_items, db_path)
    return 0


NAME_PROMPT = """아래는 IBL 관용구들(의도 + 골격 문장)이다. 관용구는 이름 붙은 함수라 `[fn:이름]{{슬롯}}` 으로 부른다.
각 관용구에 **이름**을 붙여라 — 짧은 한국어 동사형 명사, 띄어쓰기 없이 2~5어절을 붙여 쓴다(예: 뉴스모아쓰기·직전보고서읽기·찾아고치기).
서로 다른 관용구는 다른 이름. 기호·공백·영문 금지, 한글·숫자만.

{rows}

JSON 객체로만 응답: {{"<id>": "이름", ...}}"""


def name_idioms(apply: bool, topics_prefix: str = ""):
    import hippo_tree
    import ibl_idiom
    from ibl_usage_db import IBLUsageDB
    from consciousness_agent import oneshot_ai_call
    from runtime_utils import parse_first_json
    db = IBLUsageDB()
    with db._get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, intent, ibl_code, COALESCE(alias,'') AS alias, COALESCE(topic,'') AS topic FROM ibl_examples "
            "WHERE COALESCE(alias,'')='' AND (category='phrase' OR category='pipeline') ORDER BY id").fetchall()]
    # 다문장 프로그램(pipeline)도 이름을 받는다(2026-09-05 처방 2) — 한 문장짜리 pipeline 은 낱말이라 제외
    rows = [r for r in rows if len(hippo_tree.split_sentences(r["ibl_code"])) >= 2]
    if topics_prefix:
        rows = [r for r in rows if (r.get("topic") or "").startswith(topics_prefix)]
    if not rows:
        print("[name] 이름 없는 관용구·다문장 용례 없음"); return 0
    listing = "\n".join(f"{r['id']}: {r['intent']}\n   " + " / ".join(hippo_tree.split_sentences(r['ibl_code']))[:300] for r in rows)
    res = oneshot_ai_call(prompt=NAME_PROMPT.format(rows=listing), system_prompt="관용구 작명기. JSON 객체로만 응답.", role="background")
    verdict = parse_first_json(res or "") or {}
    named = 0
    for r in rows:
        raw = verdict.get(str(r["id"])) if isinstance(verdict, dict) else None
        name = ibl_idiom.unique_fn_name(ibl_idiom.sanitize_fn_name(raw, r["intent"]), db, r["ibl_code"])
        print(f"  #{r['id']} {r['intent'][:36]:38} → [fn:{name}]")
        if apply:
            with db._get_connection() as conn:
                conn.execute("UPDATE ibl_examples SET alias=? WHERE id=?", (name, r["id"])); conn.commit()
            named += 1
    if apply:
        if hasattr(db, "_load_model_sync"):
            db._load_model_sync()
        for r in rows:
            row = db.find_phrase_by_alias  # noqa — 색인은 이름+의도
        with db._get_connection() as conn:
            for r in conn.execute("SELECT id, intent, ibl_code, alias FROM ibl_examples WHERE COALESCE(alias,'')!=''").fetchall():
                db._index_single(r["id"], f"{r['alias']} {r['intent']}".strip(), r["ibl_code"])
        for t in {r["topic"] for r in rows}:
            hippo_tree.refresh_topic(t)
        print(f"[name] 이름 {named}건 적용 · 재색인 · 가지 문서 갱신")
    else:
        print("[name] dry-run — --apply 로 적용")
    return 0


def apply_report(report: Path, db_path: Path, top: int):
    d = json.loads(report.read_text(encoding="utf-8"))
    chosen = d.get("chosen") or []
    print(f"[replay] 보고서 chosen {len(chosen)} → 상위 {min(top, len(chosen))} 저장")
    save_phrases(chosen[:top], db_path)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=150, help="되돌려 물을 에피소드 수(최근순, IBL 성공 3문장 이상)")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--min-evidence", type=int, default=2, help="후보 에피소드 수 또는 궤적 주행 수가 이 이상인 골격만")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--call-timeout", type=float, default=90.0, help="호출 한 건의 시한(초) — 매달린 호출은 버린다")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--apply-report", action="store_true",
                    help="AI 를 다시 부르지 않고 --report 의 chosen 을 저장(에피소드 호출은 원장에서 다시 읽어 접지)")
    ap.add_argument("--report", default=str(ROOT / "data" / "_backups" / "2026-09-04_idiom_replay" / "candidates.json"))
    ap.add_argument("--rehearse", default=None,
                    help="짓기(상상): 설계한 관용구 JSON [{intent, topic, phrase, slots}] 을 슬롯 값으로 채워 라이브 백엔드(/ibl/execute)에서 한 번 돌리고, 성공한 것만 같은 관문으로 저장(--apply)")
    ap.add_argument("--project", default="", help="리허설 실행의 프로젝트 문맥(project_id) — 검색·논문 등 프로젝트 도구가 요구")
    ap.add_argument("--name-idioms", action="store_true",
                    help="이름 없는 관용구에 반성기가 이름을 붙인다(관용구=이름 붙은 함수, 2026-09-05) — 색인·가지 문서 갱신")
    ap.add_argument("--topics", default="", help="작명 대상 주제 접두(예: 보고서/) — 비우면 전부")
    ap.add_argument("--programs", nargs="*", default=None,
                    help="짓기 재료: 완주가 실증된 프로그램 JSON({code, …})들 — 문장 줄을 실행 호출로 보고 같은 질문·같은 관문. 빈도 필터 없음")
    args = ap.parse_args()

    import hippo_tree
    wp = ROOT / "data" / "world_pulse.db"
    if args.apply_report:
        return apply_report(Path(args.report), wp, args.top)
    if args.rehearse:
        return rehearse(Path(args.rehearse), wp, apply=args.apply, project_id=args.project)
    if args.name_idioms:
        return name_idioms(apply=args.apply, topics_prefix=args.topics)
    if args.programs is not None:
        episodes = load_programs(args.programs)
        shapes = Counter()
        args.min_evidence = 0
    else:
        episodes = load_episodes(wp, args.limit)
        shapes = trajectory_shapes(wp)
    print(f"[replay] 에피소드 {len(episodes)}건(IBL 성공 3문장 이상, 최근순) · 궤적 골격 {len(shapes)}종")
    topic_map = hippo_tree.map_text()
    pp = ROOT / "data" / "common_prompts" / "reflection_prompt.md"
    system_prompt = pp.read_text(encoding="utf-8").strip() if pp.exists() else ""

    # 답 캐시: 건마다 즉시 적어 매달린 호출·중단에도 잃지 않는다. 시한(--call-timeout)을 넘긴 호출은 버린다.
    import threading
    from concurrent.futures import as_completed
    cache_path = Path(args.report).with_name(Path(args.report).stem + "_answers_cache.json")
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    except Exception:
        cache = {}
    lock = threading.Lock()
    todo = [e for e in episodes if str(e["id"]) not in cache]
    print(f"[replay] 캐시 {len(cache)}건 · 새로 물을 것 {len(todo)}건")
    ex = ThreadPoolExecutor(max_workers=args.workers)
    futs = {ex.submit(ask, e, topic_map, system_prompt): e for e in todo}
    done_n = 0
    try:
        for f in as_completed(futs, timeout=args.call_timeout * max(1, len(todo)) / max(1, args.workers) + args.call_timeout):
            try:
                a = f.result(timeout=0)
            except Exception as e:
                a = {"episode": futs[f]["id"], "reject": f"호출 실패: {e}"}
            with lock:
                cache[str(a["episode"])] = a
                done_n += 1
                if done_n % 10 == 0:
                    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                    print(f"[replay] 진행 {done_n}/{len(todo)}")
    except Exception as e:
        print(f"[replay] 시한 초과 — 남은 호출 {len(todo) - done_n}건 버림: {e}")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    ex.shutdown(wait=False, cancel_futures=True)
    answers = [cache[str(e["id"])] for e in episodes if str(e["id"]) in cache]
    by_id = {e["id"]: e for e in episodes}
    cands, rejects, detail = [], Counter(), []
    for a in answers:
        if "reject" in a:
            rejects[a["reject"][:30]] += 1
            detail.append({"episode": a["episode"], "why": a["reject"]})
            continue
        c, why = gate(by_id[a["episode"]], a["distilled"])
        if c:
            cands.append(c)
        else:
            rejects[why.split(":")[0]] += 1
            detail.append({"episode": a["episode"], "why": why, "answer": a["distilled"],
                           "calls": by_id[a["episode"]]["calls"][:12]})
    print(f"[replay] 관문 통과 후보 {len(cands)} · 거절 {dict(rejects)}")

    groups = defaultdict(list)
    for c in cands:
        groups[c["heads"]].append(c)
    ranked = []
    for heads, cs in groups.items():
        flat = tuple(h for sent in heads for h in sent)   # 궤적은 문장 단위가 아니라 호출 단위 머리 열
        traj = shapes.get(tuple((h,) for h in flat), 0) if all(len(s) == 1 for s in heads) else shapes.get(heads, 0)
        n_ep = len({c["episode"] for c in cs})
        if args.min_evidence and n_ep < args.min_evidence and traj < max(args.min_evidence, 3):
            continue
        rep = sorted(cs, key=lambda c: (c["n_slots"], c["when"]), reverse=True)[0]
        ranked.append({"episodes": n_ep, "trajectory_runs": traj, "rep": rep})
    ranked.sort(key=lambda r: (r["episodes"], r["trajectory_runs"]), reverse=True)
    chosen = ranked[:args.top]

    print(f"\n[replay] 되풀이가 증명된 골격 {len(ranked)} · 상위 {len(chosen)}")
    for i, r in enumerate(chosen, 1):
        rep = r["rep"]
        print(f"\n#{i} 에피소드 {r['episodes']} · 궤적 주행 {r['trajectory_runs']} · 가지 {rep['topic']} · 슬롯 {rep['n_slots']}")
        print(f"   의도: {rep['intent'][:100]}")
        for j, sent in enumerate(rep["phrase"], 1):
            print(f"   {j}. {sent[:180]}")
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(
        {"chosen": [{"episodes": r["episodes"], "trajectory_runs": r["trajectory_runs"],
                     **{k: v for k, v in r["rep"].items() if k not in ("heads",) and (k != "calls" or r["rep"]["episode"] < 0)}}
                    for r in chosen],
         "all_candidates": [{k: v for k, v in c.items() if k not in ("calls", "heads")} for c in cands],
         "rejects": dict(rejects), "reject_detail": detail}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[replay] 보고서 → {args.report}")

    if not args.apply:
        print("[replay] dry-run — 저장하지 않음(--apply 로 저장)")
        return 0
    save_phrases([r["rep"] for r in chosen], wp)
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc or 0)      # 매달린 호출 스레드가 있어도 프로세스는 끝난다
