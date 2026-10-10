"""50회차 합성 자료 — 일 스크립트(jobs/)·queue.json·oracle. 사용: python3 prepare.py"""
import json, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-10_50회차'
REMOTE = '/Users/kangkukjin/indiebiz-training/r50'
PORTS = {'trainer_base': 18650, 'trainer_a': 18651, 'trainer_b': 18652, 'agent_a': 18653, 'probe': 18659}
PY_SLEEP = 'python3 -c "import signal,sys,time\nif len(sys.argv)>2 and sys.argv[2]==\'ignore\': signal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(600)"'
SCRIPTS = {
 'sum.sh': '#!/bin/sh\n# 판매 기록 집계 — $1=표식, 환경 SECONDS_TOTAL(기본 25)·LINES(기본 150)\nmkdir -p started results; echo $$ > started/sum.pid\nexec python3 jobs/sum.py "$1"\n',
 'sum.py': 'import csv, json, os, sys, time\nn = int(os.environ.get("LINES", "150")); total = float(os.environ.get("SECONDS_TOTAL", "25"))\nrows = list(csv.DictReader(open("jobs/sales.csv", encoding="utf-8")))\nby = {}\nfor i, r in enumerate(rows):\n    by[r["지점"]] = by.get(r["지점"], 0) + int(r["금액"])\nfor i in range(n):\n    print("집계 진행 %d/%d" % (i + 1, n), flush=True); time.sleep(total / n)\njson.dump({"rows": len(rows), "by_store": by, "total": sum(by.values())}, open("results/sum.json", "w", encoding="utf-8"), ensure_ascii=False, sort_keys=True)\nprint("DONE rows=%d total=%d" % (len(rows), sum(by.values())))\n',
 'watch.sh': '#!/bin/sh\n# 끝없이 도는 감시 루프 + 자식 3개 — $1=표식\nmkdir -p started; echo $$ > started/watch.pid\nfor i in 1 2 3; do ' + PY_SLEEP + ' "$1-child$i" &\ndone\nwhile :; do echo "watch tick $(date +%T)"; sleep 5; done\n',
 'brief.sh': '#!/bin/sh\n# 앞 일의 결과(환경 INPUT)로 보고서 — $1=표식\nmkdir -p started results; echo $$ > started/brief.pid\n[ -s "$INPUT" ] || { echo "입력 없음: ${INPUT:-미지정}"; exit 5; }\nsleep "${SECONDS_TOTAL:-10}"\npython3 -c "import json,sys; d=json.load(open(sys.argv[1],encoding=\'utf-8\')); open(\'results/brief.md\',\'w\',encoding=\'utf-8\').write(\'# 판매 요약\\\\n- 행 %d\\\\n- 합계 %d\\\\n\' % (d[\'rows\'], d[\'total\']) + \'\'.join(\'- %s: %d\\\\n\' % kv for kv in sorted(d[\'by_store\'].items())))" "$INPUT" "$1"\necho "DONE brief"\n',
 'hold.sh': '#!/bin/sh\n# 자식 2개를 띄우고 오래 기다림 — $1=표식, $2=ignore 면 자식이 종료 신호를 무시\nmkdir -p started; echo $$ > started/hold.pid\nfor i in 1 2; do ' + PY_SLEEP + ' "$1-child$i" "$2" &\ndone\necho "holding"; sleep 300; echo "hold finished"\n',
 'preview.sh': '#!/bin/sh\n# 미리보기 서버를 띄우고 곧 끝남 — $1=표식, $2=포트\nmkdir -p started site; echo $$ > started/preview.pid\necho "R50 미리보기 $1" > site/index.html\nnohup python3 jobs/serve.py "$1" "$2" > preview.log 2>&1 < /dev/null &\nsleep 2; echo "preview started on $2"\n',
 'serve.py': 'import functools, http.server, sys\nport = int(sys.argv[2])\nh = functools.partial(http.server.SimpleHTTPRequestHandler, directory="site")\nhttp.server.HTTPServer(("127.0.0.1", port), h).serve_forever()\n',
 'bad.sh': '#!/bin/sh\n# 틀린 입력 — 종료 코드 4\nmkdir -p started; echo $$ > started/bad.pid\nsleep 3; echo "입력 형식 오류: 열 \'금액\' 없음" >&2; exit 4\n',
 'next.sh': '#!/bin/sh\nmkdir -p started; echo $$ > started/next.pid\necho "이 일은 돌면 안 된다"; sleep 5\n',
}


def sales():
    stores = ['강남', '홍대', '부산', '대구']; lines = ['지점,품목,금액']
    for i in range(240): lines.append(f'{stores[i % 4]},품목{i % 17},{1000 + (i * 37) % 9000}')
    return '\n'.join(lines) + '\n'


def queue(key, mode):
    m = f'R50={key}'; port = PORTS[key]
    j = [{'id': '가', 'cmd': f'sh jobs/sum.sh {m}-가', 'result': 'results/sum.json'},
         {'id': '나', 'cmd': f'sh jobs/watch.sh {m}-나', 'stop_after_s': 15},
         {'id': '다', 'cmd': f'sh jobs/brief.sh {m}-다', 'after': '가', 'result': 'results/brief.md'},
         {'id': '라', 'cmd': f'sh jobs/hold.sh {m}-라', 'limit_s': 20},
         {'id': '마', 'cmd': f'sh jobs/preview.sh {m}-마 {port}', 'keep_alive': {'port': port, 'expect': f'R50 미리보기 {m}-마'}},
         {'id': '바', 'cmd': f'sh jobs/bad.sh {m}-바'},
         {'id': '사', 'cmd': f'sh jobs/next.sh {m}-사', 'after': '바'}]
    exp = {'가': '성공', '나': '내가 멈춤', '다': '성공', '라': '시간 초과로 끊김', '마': '성공', '바': '실패', '사': '맡기지 않음'}
    if mode == 'a':
        j[1]['cmd'] = f'sh jobs/sum.sh {m}-나'; j[1]['env'] = {'SECONDS_TOTAL': '6', 'LINES': '6'}; j[1]['stop_after_s'] = 25; j[1].pop('result', None); exp['나'] = '성공'
        j[3]['cmd'] = f'sh jobs/hold.sh {m}-라 ignore'
    if mode == 'b':
        j = [{'id': 'p1', 'cmd': f'sh jobs/preview.sh {m}-p1 {port}', 'keep_alive': {'port': port, 'expect': f'R50 미리보기 {m}-p1'}},
             {'id': 's1', 'cmd': f'sh jobs/sum.sh {m}-s1', 'result': 'results/sum.json', 'env': {'SECONDS_TOTAL': '12', 'LINES': '40'}},
             {'id': 'h1', 'cmd': f'sh jobs/hold.sh {m}-h1', 'stop_after_s': 8},
             {'id': 'b1', 'cmd': f'sh jobs/brief.sh {m}-b1', 'after': 's1', 'result': 'results/brief.md', 'env': {'SECONDS_TOTAL': '4'}},
             {'id': 'w1', 'cmd': f'sh jobs/watch.sh {m}-w1', 'limit_s': 12},
             {'id': 'n1', 'cmd': f'sh jobs/next.sh {m}-n1', 'after': 'b1'},
             {'id': 'x1', 'cmd': f'sh jobs/bad.sh {m}-x1', 'after': 'n1'},
             {'id': 'n2', 'cmd': f'sh jobs/next.sh {m}-n2', 'after': 'x1'},
             {'id': 'n3', 'cmd': f'sh jobs/next.sh {m}-n3', 'after': 'h1'}]
        exp = {'p1': '성공', 's1': '성공', 'h1': '내가 멈춤', 'b1': '성공', 'w1': '시간 초과로 끊김', 'n1': '성공', 'x1': '실패', 'n2': '맡기지 않음', 'n3': '맡기지 않음'}
    return {'pc': '맥12', 'remote_dir': f'{REMOTE}/{key}', 'mark': m, 'jobs': j}, exp


def main():
    for sub in ('trainer', 'agent', '_oracle'): shutil.rmtree(OUT / sub, ignore_errors=True)
    (OUT / 'runs').mkdir(parents=True, exist_ok=True); (OUT / '_oracle').mkdir(); allexp = {}
    for who, mode in (('trainer', 'base'), ('trainer', 'a'), ('trainer', 'b'), ('agent', 'a')):
        inp = OUT / who / mode / 'input'; (inp / 'jobs').mkdir(parents=True); (OUT / who / mode / 'out').mkdir()
        for n, t in SCRIPTS.items(): (inp / 'jobs' / n).write_text(t)
        (inp / 'jobs' / 'sales.csv').write_text(sales())
        q, exp = queue(f'{who}_{mode}', mode); (inp / 'queue.json').write_text(json.dumps(q, ensure_ascii=False, indent=1)); allexp[f'{who}_{mode}'] = {'queue': q, 'expect': exp}
    (OUT / '_oracle/expected.json').write_text(json.dumps(allexp, ensure_ascii=False, indent=1)); print({k: v['expect'] for k, v in allexp.items()})


if __name__ == '__main__':
    main()
