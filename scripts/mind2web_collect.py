"""Mind2Web 2 원자료 수집: 위임 원장(tasks.worker_request = <prefix>-<task_id>)에서 결과·실행자 도구 호출을 모아
runs/<prefix>_raw.json 을 만들고, 완료된 답을 answers/<agent>/<task_id>/answer_<n>.md 로 쓴다(공식 제출 구조).
부정 조회 점검: 벤치마크·저장소·HF·봉인 폴더·권한 변경 접근을 찾는다.
사용: .venv/bin/python3 scripts/mind2web_collect.py <tasks.json> <prefix> <agent_name> <answer_index> [--wait 초]"""
import argparse
import collections
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: F401

BAD = re.compile(
    r'mind2web|m2w2|osu-nlp|osunlp|huggingface\.co/datasets|eval_scripts|chmod', re.I)
START_TYPES = {'tool_start', 'handoff.tool_start'}
ACTIVE = ('running', 'queued', 'pending', 'waiting_children')


def audit(db, sess):
    ev = [json.loads(p) for (p,) in db.execute(
        "select payload from conversation_events where session_id=? order by id",
        (sess,))]
    return audit_events(ev)


def audit_events(ev):
    # 같은 호출의 전송 사본만 합친다. ID 없는 사건·서로 다른 재시도는 보존한다.
    starts, seen = [], set()
    for event in ev:
        if event.get('type') not in START_TYPES:
            continue
        ident = event.get('id')
        if ident and ident in seen:
            continue
        if ident:
            seen.add(ident)
        starts.append(event)
    names, hits = collections.Counter(), []
    for e in starts:
        inp = json.dumps(e.get('input', {}), ensure_ascii=False)
        nm = e.get('name', '?')
        if 'execute_ibl' in nm:
            acts = set(re.findall(r'\[(sense|self|limbs|others|engines|table):(\w+)\]', inp))
            for a in acts:
                names[f'{a[0]}:{a[1]}'] += 1
            if not acts:
                names['execute_ibl(other)'] += 1
        else:
            names[nm.split('__')[-1]] += 1
    for e in ev:
        if e.get('type') in START_TYPES:
            inp = json.dumps(e.get('input', {}), ensure_ascii=False)
            if BAD.search(inp) and inp[:300] not in hits:
                hits.append(inp[:300])
    return len(starts), dict(names), hits


def answer_text(res):
    m = re.search(r'===ANSWER START===(.*?)===ANSWER END===', res or '', re.S)
    return (m.group(1) if m else (res or '')).strip(), bool(m)


def collect(tasks, prefix, db_path):
    db = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    out = []
    for q in tasks:
        rows = db.execute("select task_id,status,result,created_at,completed_at,worker_session from tasks "
                          "where worker_request=? order by created_at", (f"{prefix}-{q['task_id']}",)).fetchall()
        rec = {'task_id': q['task_id'], 'attempts': len(rows)}
        if rows:
            tid, st, res, c, d, sess = rows[-1]
            el = db.execute("select (julianday(?)-julianday(?))*86400", (d, c)).fetchone()[0] if d else None
            n, br, hits = audit(db, sess) if sess else (0, {}, [])
            ans, marked = answer_text(res)
            rec.update(child_task_id=tid, state=st, created_at=c, completed_at=d,
                       elapsed_s=round(el, 1) if el is not None else None, worker_session=sess,
                       result=res or '', answer=ans, answer_marked=marked,
                       tool_calls=n, tool_breakdown=br, contamination_hits=hits)
        else:
            rec.update(state='unsubmitted', result='', answer='', tool_calls=0, contamination_hits=[])
        out.append(rec)
    db.close()
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks_path", type=Path)
    parser.add_argument("prefix")
    parser.add_argument("agent")
    parser.add_argument("idx", type=int)
    parser.add_argument("--wait", type=float, default=0)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args(argv)
    tasks_path, prefix, agent = args.tasks_path, args.prefix, args.agent
    idx, wait = args.idx, args.wait
    for name in (prefix, agent):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            parser.error("prefix/agent는 영문·숫자·밑줄·하이픈만 허용합니다")
    if idx < 1:
        parser.error("answer index는 양수여야 합니다")
    root = tasks_path.resolve().parent.parent
    db_path = args.db or root.parent / "conversations.db"
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    for task in tasks:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", task["task_id"]):
            parser.error("task_id는 영문·숫자·밑줄·하이픈만 허용합니다")
    t0 = time.monotonic()
    while True:
        out = collect(tasks, prefix, db_path)
        if not any(r['state'] in ACTIVE for r in out) or time.monotonic() - t0 > wait:
            break
        time.sleep(min(30, max(0, wait - (time.monotonic() - t0))))
    (root / 'runs' / f'{prefix}_raw.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for r in out:
        if r['state'] == 'completed' and r['answer']:
            p = root / 'answers' / agent / r['task_id']
            p.mkdir(parents=True, exist_ok=True)
            (p / f'answer_{idx}.md').write_text(r['answer'] + '\n', encoding='utf-8')
    print(dict(collections.Counter(r['state'] for r in out)))
    for r in out:
        print(r['task_id'], r['state'], r.get('elapsed_s'), 'tools', r['tool_calls'],
              'marked' if r.get('answer_marked') else 'UNMARKED', 'hits', len(r['contamination_hits']))


if __name__ == '__main__':
    main()
