"""51회차 합성 자료 — 밤일 스크립트·night.json 5종·무음 WAV·oracle. 사용: python3 prepare.py"""
import json, shutil, wave
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-11_51회차'
REMOTE = '/Users/kangkukjin/indiebiz-training/r51'
NIGHT = '''#!/bin/sh
# 밤일 — $1=표식, 환경 MINUTES(기본 6)·NAME(기본 night). 5초마다 results/<NAME>.beat 에 "epoch 번호" 한 줄, 끝에 results/<NAME>.json
mkdir -p results; N="${NAME:-night}"; : > "results/$N.beat"
total=$(python3 -c "import os;print(int(float(os.environ.get('MINUTES','6'))*60/5))")
n=0
while [ "$n" -lt "$total" ]; do n=$((n+1)); echo "$(date +%s) $n" >> "results/$N.beat"; echo "beat $n/$total"; sleep 5; done
python3 jobs/summary.py "results/$N.beat" "results/$N.json" "$1"
echo "DONE $N"
'''
SUMMARY = '''import json, sys
rows = [l.split() for l in open(sys.argv[1]) if l.strip()]
t = [int(r[0]) for r in rows]
gaps = [b - a for a, b in zip(t, t[1:])]
json.dump({"beats": len(t), "first": t[0], "last": t[-1], "max_gap_s": max(gaps) if gaps else 0, "mark": sys.argv[3]}, open(sys.argv[2], "w"), sort_keys=True)
'''
REQ = {'ac_power': True, 'min_free_gb': 5, 'no_thermal_limit': True, 'sleep_never_or_longer_than_job': True}


def night(key, mode):
    m = f'R51={key}'
    jobs = [{'id': 'night', 'cmd': f'sh jobs/night.sh {m}-night', 'minutes': 6, 'limit_s': 900, 'result': 'results/night.json', 'partial': 'results/night.beat'}]
    req = dict(REQ)
    if mode == 'b': jobs[0]['limit_s'] = 150
    if mode == 'c': req.update({'min_free_gb': 500, 'min_idle_hours': 12})
    if mode == 'd': jobs = [{'id': 'tidy', 'cmd': f'sh jobs/night.sh {m}-tidy', 'minutes': 2, 'limit_s': 600, 'result': 'results/tidy.json', 'partial': 'results/tidy.beat', 'env': {'NAME': 'tidy'}},
                            {'id': 'index', 'cmd': f'sh jobs/night.sh {m}-index', 'minutes': 3, 'limit_s': 600, 'result': 'results/index.json', 'partial': 'results/index.beat', 'env': {'NAME': 'index'}}]
    for j in jobs: j.setdefault('env', {}); j['env']['MINUTES'] = str(j['minutes'])
    return {'pc': '맥12', 'remote_dir': f'{REMOTE}/{key}', 'mark': m, 'requires': req, 'jobs': jobs}


def main():
    for sub in ('trainer', 'agent', '_oracle'): shutil.rmtree(OUT / sub, ignore_errors=True)
    (OUT / 'runs').mkdir(parents=True, exist_ok=True); (OUT / '_oracle').mkdir(); exp = {}
    for who, mode in (('trainer', 'base'), ('trainer', 'b'), ('trainer', 'c'), ('trainer', 'd'), ('agent', 'base')):
        inp = OUT / who / mode / 'input'; (inp / 'jobs').mkdir(parents=True); (OUT / who / mode / 'out').mkdir()
        (inp / 'jobs/night.sh').write_text(NIGHT); (inp / 'jobs/summary.py').write_text(SUMMARY)
        with wave.open(str(inp / 'silence.wav'), 'wb') as w: w.setnchannels(1); w.setsampwidth(1); w.setframerate(8000); w.writeframes(b'\x80' * 8000 * 30)
        q = night(f'{who}_{mode}', mode); (inp / 'night.json').write_text(json.dumps(q, ensure_ascii=False, indent=1)); exp[f'{who}_{mode}'] = q
    (OUT / '_oracle/expected.json').write_text(json.dumps(exp, ensure_ascii=False, indent=1)); print(list(exp))


if __name__ == '__main__':
    main()
