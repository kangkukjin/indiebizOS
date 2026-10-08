"""Round 36 fixture generation, HTTP transport and independent ZIP oracle."""
import argparse
import hashlib
import json
import sqlite3
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DOC = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-08_36회차'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def data_bytes(name):
    # Mixed line endings and literal text must survive ZIP composition unchanged.
    return (f'자료 {name}\r\n인용: "쉼표, 구분"\n끝\r' * 40).encode('utf-8')


def prepare():
    shared = [f'common/guide{i:02}.txt' for i in range(12)]
    kits = [dict(id=k, files=shared + [f'{k}/lesson{i:02}.txt' for i in range(24)])
            for k in ('alpha', 'beta', 'gamma')]
    for who in ('trainer', 'ai'):
        src = OUT / who / 'source'
        dump(src / 'catalog.json', dict(kits=kits))
        names = sorted({p for kit in kits for p in kit['files']})
        names += [f'{k}/{sub}/not_for_delivery.txt' for k in ('alpha', 'beta', 'gamma')
                  for sub in ('draft', 'internal')]
        for name in names:
            if name == 'gamma/lesson07.txt':
                continue
            path = src / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data_bytes(name))
    dump(OUT / 'evidence' / 'initial_inputs.json',
         {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
          for who in ('trainer', 'ai') for p in (OUT / who / 'source').rglob('*') if p.is_file()})
    con = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
    last = con.execute('select max(id) from episode_log').fetchone()[0]
    dump(OUT / 'evidence' / 'start.json', dict(start='2026-10-08T09:11:00+09:00',
         deadline='2026-10-08T10:11:00+09:00', head='13b82148', last_episode=last))
    print(json.dumps(dict(kits=3, required_per_kit=36, actual_required_files=83,
                          distractors=6, last_episode=last)))


def request(label, payload=None, endpoint='/ibl/execute'):
    started = time.time()
    req = urllib.request.Request('http://127.0.0.1:8765' + endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=600) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        result = dict(http_error=exc.code, body=exc.read().decode())
    record = dict(request=payload, response=result, started=started, ended=time.time(), endpoint=endpoint)
    dump(OUT / 'runs' / (label + '.json'), record)
    summary = {k: result[k] for k in ('success', 'ok', 'error', 'run_status', 'state',
        'task_id', 'status_url', 'result_ref', 'resume', 'issues', 'warnings') if k in result}
    if 'value' in result:
        summary['value'] = result['value']
    if 'result' in result:
        summary['result'] = result['result']
    if 'http_error' in result:
        summary = result
    print(json.dumps(dict(label=label, wall_s=record['ended']-started, response=summary),
                     ensure_ascii=False)[:9000])
    return result


def verify(who, stage):
    dest = OUT / who / stage
    source = OUT / who / 'source'
    catalog = json.loads((source / 'catalog.json').read_text())['kits']
    actual = json.loads((dest / 'result.json').read_text())
    report = (dest / 'report.md').read_text()
    order = ['alpha', 'beta', 'gamma'] if stage == 'base' else ['gamma', 'beta', 'alpha']
    title = '교육 자료 인계 v1' if stage == 'base' else '교육 자료 최종 인계'
    checks = {'title': actual['title'] == title and title in report,
              'order': [x['id'] for x in actual['kits']] == order}
    archive_states = {}
    for spec in catalog:
        kit = next(x for x in actual['kits'] if x['id'] == spec['id'])
        missing = ['gamma/lesson07.txt'] if spec['id'] == 'gamma' and stage != 'recovery' else []
        ready = not missing
        checks[spec['id'] + '_contract'] = (kit['status'] == ('ready' if ready else 'blocked')
            and sorted(kit['files']) == sorted(spec['files'])
            and kit['missing'] == missing and kit['verified_count'] == (36 if ready else 0))
        rows = [[cell.strip().strip('`') for cell in line.strip().strip('|').split('|')]
                for line in report.splitlines() if line.strip().startswith('|')]
        report_row = next((row for row in rows if row and row[0] == spec['id']), [])
        checks[spec['id'] + '_report'] = (len(report_row) == 6
            and report_row[1:4] == [kit['status'], '36', str(36 if ready else 0)]
            and (report_row[5] == str(kit['archive']) if ready else missing[0] in report_row[4]))
        if ready:
            path = Path(kit['archive'])
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                checks[spec['id'] + '_members'] = (sorted(names) == sorted(spec['files'])
                    and len(set(names)) == len(names))
                checks[spec['id'] + '_bytes'] = all(z.read(name) == data_bytes(name) for name in names)
                checks[spec['id'] + '_crc'] = z.testzip() is None
            archive_states[spec['id']] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                             mtime_ns=path.stat().st_mtime_ns)
        else:
            checks[spec['id'] + '_no_archive'] = kit['archive'] is None
    if stage != 'base':
        before = json.loads((OUT / 'evidence' / f'verify_{who}_base.json').read_text())['archives']
        checks['prior_archives_unchanged'] = all(archive_states[k] == v for k, v in before.items())
    originals = json.loads((OUT / 'evidence' / 'initial_inputs.json').read_text())
    checks['original_inputs_unchanged'] = all(hashlib.sha256((OUT / name).read_bytes()).hexdigest() == sha
        for name, sha in originals.items() if name.startswith(who + '/'))
    # Recovery allows exactly the one supplied source file; any other file change/addition fails.
    expected_source = {name for name in originals if name.startswith(who + '/')}
    if stage == 'recovery':
        expected_source.add(f'{who}/source/gamma/lesson07.txt')
    checks['source_members'] = {str(p.relative_to(OUT)) for p in source.rglob('*') if p.is_file()} == expected_source
    checks['zip_count'] = len(list((OUT / who).rglob('*.zip'))) == (3 if stage == 'recovery' else 2)
    evidence = dict(who=who, stage=stage, checks=checks, archives=archive_states,
                    passed=all(checks.values()))
    dump(OUT / 'evidence' / f'verify_{who}_{stage}.json', evidence)
    print(json.dumps(evidence, ensure_ascii=False))
    return evidence


def ai_message(stage):
    out = OUT / 'ai'
    if stage == 'base':
        message = (DOC / 'task.md').read_text().split('\n\n')[1]
        message += f'\n입력 자료 위치: {out / "source"}\n저장 위치: {out / "base"}'
    elif stage == 'presentation':
        message = (f'앞 교육 자료 인계의 설명만 바꿔줘. 제목은 “교육 자료 최종 인계”, 반 순서는 gamma,beta,alpha야. '
            f'자료와 ZIP 내용은 그대로야. 앞 결과와 검증 근거로 result.json/report.md만 {out / stage}에 새로 저장해. '
            '기존 ZIP은 재압축·복사·덮어쓰기 하지 말고 이전 절대경로를 그대로 인계해. 이전 산출물도 보존해. '
            '세 반의 상태·필요 파일 목록·누락·검증 수·ZIP 경로를 유지하고 두 새 파일을 재독해.')
    else:
        message = (f'누락됐던 gamma/lesson07.txt를 {out / "source/gamma/lesson07.txt"}에 보충했어. '
            '나머지 입력은 그대로야. 자기 직전 결과를 이어받아 막혔던 gamma만 준비하고 전건 경로·바이트를 검증해. '
            '이미 완성한 alpha·beta ZIP은 재생성·복사·덮어쓰기 하지 말고 그 경로와 검증 결과를 유지해. '
            f'제목 “교육 자료 최종 인계”와 gamma,beta,alpha 순서로 최종 result.json/report.md를 {out / stage}에 저장·재독해. '
            '세 반 모두 기본 요청의 동일한 필드를 유지해. 이전 산출물은 보존해.')
    return message + ('\n자신의 직전 결과·중간 참조·코드는 재사용해도 된다. 다른 실행자의 trainer/harness/drafts·정답은 참조하지 마. '
                      '입력 source와 자신의 ai 출력 폴더, 공개 가이드·계약·현재 등록 기능만 이용해. '
                      '합성 훈련이며 외부 발송·공개하지 마.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('op', choices=['prepare', 'request', 'run', 'check', 'ai', 'poll', 'verify', 'supply'])
    parser.add_argument('stage', nargs='?', default='base')
    parser.add_argument('--who', default='trainer')
    parser.add_argument('--label')
    parser.add_argument('--draft', default='main_v0.ibl')
    parser.add_argument('--payload')
    parser.add_argument('--url')
    args = parser.parse_args()
    label = args.label or (args.op + '_' + args.stage)
    if args.op == 'prepare':
        prepare()
    elif args.op == 'supply':
        path = OUT / args.who / 'source/gamma/lesson07.txt'
        assert not path.exists(), 'Only the prescribed missing input may be supplied once'
        path.write_bytes(data_bytes('gamma/lesson07.txt'))
        print(str(path))
    elif args.op == 'verify':
        assert verify(args.who, args.stage)['passed'], 'Independent artifact checks failed'
    elif args.op == 'request':
        request(label, json.loads(Path(args.payload).read_text()))
    elif args.op == 'ai':
        message = ai_message(args.stage)
        dump(OUT / 'requests' / f'ai_{args.stage}.json', dict(message=message))
        request(label, dict(message=message, origin='training', background=True), '/system-ai/chat')
    elif args.op == 'poll':
        request(label, endpoint=args.url)
    else:
        payload = dict(code=(DOC / 'drafts' / args.draft).read_text(), origin='training',
            project_id='수동모드', check=args.op == 'check', budget=dict(steps=1000000, rows=100000),
            inputs=dict(source=str(OUT / 'trainer/source'), out=str(OUT / 'trainer' / args.stage),
                        title='교육 자료 인계 v1', order=['alpha', 'beta', 'gamma']))
        if args.payload:
            payload.update(json.loads(Path(args.payload).read_text()))
        request(label, payload)


if __name__ == '__main__':
    main()
