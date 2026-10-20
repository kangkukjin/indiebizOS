"""Fixture changes and independent checks; all task computation runs in IBL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--mode', choices=['write', 'readonly', 'both'], default='both')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    summary = []
    for mode, filename in [('write', 'base_v0.ibl'), ('readonly', 'readonly.ibl')]:
        if args.mode != 'both' and args.mode != mode:
            continue
        folder = out / mode / 'inputs'
        folder.mkdir(parents=True)
        results = out / mode / 'results'
        results.mkdir()
        code = (here / filename).read_text()
        a, b, c = [folder / (letter + '.txt') for letter in 'abc']
        a.write_text('10')
        b.write_text('20')
        previous = None
        artifacts = {}
        for stage in ['base', 'same', 'content', 'add', 'delete', 'empty', 'new', 'damaged']:
            if stage == 'content':
                stamp = a.stat()
                a.write_text('90')
                os.utime(a, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            elif stage == 'add':
                c.write_text('30')
            elif stage == 'delete':
                b.unlink()
            elif stage == 'empty':
                a.unlink()
                c.unlink()
            elif stage == 'new':
                # Different names, order, signed and zero values after empty input.
                (folder / '한글.txt').write_text('7')
                c.write_text('-5')
                b.write_text('0')
            elif stage == 'damaged':
                c.write_text('not-a-number')
            snapshot = {str(p): {'text': p.read_text(),
                                 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                                 'mtime_ns': p.stat().st_mtime_ns}
                        for p in folder.glob('*.txt')}
            inputs = {'folder': str(folder)}
            target = results / (stage + '.json')
            if mode == 'write':
                inputs['out'] = str(target)
            request = {'edition': 2, 'code': code, 'inputs': inputs,
                       'project_id': 'study', 'origin': 'training'}
            if previous:
                request['reuse'] = previous
            started = time.time()
            record = {'request': request, 'input_snapshot': snapshot, 'started': started}
            evidence = out / mode / (stage + '.json')
            evidence.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            http = urllib.request.Request(args.url + '/ibl/execute',
                data=json.dumps(request).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(http, timeout=60) as response:
                result = json.load(response)
            record.update(response=result, ended=time.time())
            evidence.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            assert result['run_status'] in {'completed', 'interrupted'}, result.get('run_status')
            assert not result.get('suspended'), result.get('waiting')
            assert {str(p): p.read_text() for p in folder.glob('*.txt')} == {
                p: row['text'] for p, row in snapshot.items()}
            for path, digest in artifacts.items():
                assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
            if stage == 'damaged':
                assert not result['success'], result
                assert not target.exists()
            else:
                assert result['success'], result
                expected = {path: {'path': path, 'sha256': row['sha256'],
                                   'value': int(row['text'])} for path, row in snapshot.items()}
                value = result['value']
                assert {row['path']: row for row in value['rows']} == expected
                assert value['total'] == sum(row['value'] for row in expected.values())
                if mode == 'write':
                    assert json.loads(target.read_text()) == value
                    artifacts[str(target)] = hashlib.sha256(target.read_bytes()).hexdigest()
                if stage == 'same':
                    assert result['reuse']['reused_calls'] == 2
                previous = result['resume']
            summary.append({'mode': mode, 'stage': stage, 'run': result['resume'],
                            'status': result['run_status'], 'success': result['success'],
                            'total': result.get('value', {}).get('total'),
                            'reused': result.get('reuse', {}).get('reused_calls', 0),
                            'seconds': record['ended'] - started, 'verified': True})
            (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
            print(json.dumps(summary[-1], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
