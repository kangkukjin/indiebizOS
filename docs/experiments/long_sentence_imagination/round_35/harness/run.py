"""Synthetic preparation, independent oracle, HTTP transport and artifact checks."""
import argparse
import hashlib
import json
import random
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DOC = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-08_35회차'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def oracle(source):
    rows = json.loads((source / 'events.json').read_text())
    cutoff = datetime.fromisoformat(json.loads((source / 'policy.json').read_text())['cutoff'])
    accepted, rejected = [], []
    groups = {}
    for row in rows:
        (accepted if datetime.fromisoformat(row['at']) <= cutoff else rejected).append(row)
    for row in accepted:
        g = groups.setdefault(row['desk'], dict(desk=row['desk'], count=0, seats=0))
        g['count'] += 1
        g['seats'] += row['seats']
    key = lambda r: (datetime.fromisoformat(r['at']), r['id'])
    return dict(accepted=sorted(accepted, key=key), rejected=sorted(rejected, key=key),
                summary=sorted(groups.values(), key=lambda r: r['desk']))


def prepare():
    rng = random.Random(351008)
    base = datetime(2026, 10, 8, tzinfo=timezone.utc)
    rows = []
    for i in range(1200):
        instant = base + timedelta(seconds=(i % 241 - 120) * 60,
                                   microseconds=[0, 1, 999999][i % 3])
        offset = timezone(timedelta(minutes=[0, 540, -300, 330, 840, -720][i % 6]))
        rows.append(dict(id=f'E{i:04}', desk=f'D{i % 8}', at=instant.astimezone(offset).isoformat(), seats=i % 5 + 1))
    rng.shuffle(rows)
    for mode in ('base', 'variant', 'new', 'empty', 'boundary'):
        data = list(rows)
        cutoff = base
        if mode == 'variant':
            data.reverse()
            cutoff += timedelta(hours=1)
        if mode == 'new':
            data = []
            for i, (us, hours) in enumerate([(-1, 14), (0, -12), (1, 0), (0, 14), (-1, 0), (1, -12)]):
                data.append(dict(id=f'N{i}', desk='D0', seats=i + 1,
                                 at=(base + timedelta(microseconds=us)).astimezone(timezone(timedelta(hours=hours))).isoformat()))
        if mode == 'boundary':
            data = [dict(id='MIN2',desk='D0',at='0001-01-01T00:00:00.000001+14:00',seats=2),
                    dict(id='MIN1',desk='D0',at='0001-01-01T00:00:00+14:00',seats=1),
                    dict(id='MAX2',desk='D1',at='9999-12-31T23:59:59.999999-12:00',seats=4),
                    dict(id='MAX1',desk='D1',at='9999-12-31T23:59:59.999998-12:00',seats=3)]
        if mode == 'empty':
            data = []
        source = OUT / 'source' / mode
        dump(source / 'events.json', data)
        dump(source / 'policy.json', dict(cutoff=cutoff.isoformat().replace('+00:00', 'Z')))
        dump(OUT / 'expected' / (mode + '.json'), oracle(source))
    dump(OUT / 'input_hashes.json', {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT / 'source').rglob('*.json')})


def request(label, payload=None, endpoint='/ibl/execute'):
    started = time.time()
    req = urllib.request.Request('http://127.0.0.1:8765' + endpoint,
                                 data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=1200) as response:
        result = json.load(response)
    dump(OUT / 'runs' / (label + '.json'), dict(request=payload, response=result, started=started, ended=time.time(), endpoint=endpoint))
    summary = {k: result[k] for k in ('success', 'ok', 'error', 'value', 'resume', 'run_status', 'state', 'task_id', 'status_url', 'result') if k in result}
    print(json.dumps(dict(label=label, wall_s=time.time()-started, response=summary), ensure_ascii=False)[:7000])
    return result


def verify(mode, dest):
    expected = oracle(OUT / 'source' / mode)
    actual = json.loads((dest / 'result.json').read_text())
    report = (dest / 'report.md').read_text()
    mismatches = {}
    for key in expected:
        if actual.get(key) != expected[key]:
            mismatches[key] = dict(expected_count=len(expected[key]), actual_count=len(actual.get(key, [])),
                                   first_expected=expected[key][:2], first_actual=actual.get(key, [])[:2])
    normalized = report.replace(' ', '').replace('*', '')
    missing = [r['desk'] for r in expected['summary'] if f"|{r['desk']}|{r['count']}|{r['seats']}|" not in normalized]
    cutoff = json.loads((OUT/'source'/mode/'policy.json').read_text())['cutoff']
    acc, rej = len(expected['accepted']), len(expected['rejected'])
    seats = sum(r['seats'] for r in expected['accepted'])
    report_totals = (cutoff in report and
                     (f'접수:{acc}\n' in normalized or f'|접수(accepted)|{acc}|' in normalized) and
                     (f'마감후:{rej}\n' in normalized or f'|마감후(rejected)|{rej}|' in normalized) and
                     (f'좌석:{seats}\n' in normalized or f'접수좌석합계:{seats}\n' in normalized))
    unchanged = all(hashlib.sha256((OUT/p).read_bytes()).hexdigest() == h for p,h in json.loads((OUT/'input_hashes.json').read_text()).items())
    record = dict(mode=mode,dest=str(dest),mismatches=mismatches,missing_report_rows=missing,report_totals=report_totals,inputs_unchanged=unchanged,
                  accepted=len(expected['accepted']),rejected=len(expected['rejected']),seats=sum(r['seats'] for r in expected['accepted']))
    dump(OUT / 'runs' / ('verify_' + dest.parent.name + '_' + dest.name + '.json'), record)
    print(json.dumps(record,ensure_ascii=False))
    assert not mismatches and not missing and report_totals and unchanged, 'Artifact verification failed'


def main():
    p=argparse.ArgumentParser()
    p.add_argument('op', choices=['prepare','check','run','ai','poll','verify'])
    p.add_argument('mode', nargs='?',default='base')
    p.add_argument('--label',default='baseline')
    p.add_argument('--draft',default='main_v0.ibl')
    p.add_argument('--url')
    p.add_argument('--who',default='trainer')
    a=p.parse_args()
    if a.op=='prepare':
        prepare()
    elif a.op=='verify':
        verify(a.mode,OUT/a.who/(a.mode+'_'+a.label))
    elif a.op=='ai':
        paragraph=(DOC/'task.md').read_text().split('\n\n')[1]
        message=paragraph + '\n자료 위치: ' + str(OUT/'source'/a.mode) + '\n저장 위치: ' + str(OUT/'ai'/(a.mode+'_'+a.label)) + '\n입력 source 폴더와 자신의 이번 수행에서 만든 산출물만 이용해. 다른 훈련자가 만든 초안·보고서·정답은 참조하지 마. 실제 업무가 아닌 합성자료 훈련이며 발송·공개하지 마.'
        if a.mode=='variant':
            message='앞 과제의 입력 순서가 뒤집혔고 마감이 한 시간 연장됐어. 자신의 앞 결과와 코드는 재사용 가능해.\n'+message
        request('ai_'+a.mode+'_'+a.label,dict(message=message,origin='training',background=True),'/system-ai/chat')
    elif a.op=='poll':
        request(a.label,endpoint=a.url)
    else:
        request(a.op+'_'+a.mode+'_'+a.label,dict(code=(DOC/'drafts'/a.draft).read_text(),origin='training',project_id='수동모드',check=a.op=='check',budget=dict(steps=1000000,rows=100000),inputs=dict(source=str(OUT/'source'/a.mode),out=str(OUT/'trainer'/(a.mode+'_'+a.label)))))


if __name__=='__main__':
    main()
