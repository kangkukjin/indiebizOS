"""결정론 검증 — 목록.csv·폴더를 manifest 기대와 대조한다. IBL 계산을 대신하지 않는다. 사용: verify.py <정리폴더> <csv> <label>"""
import csv, json, sys, hashlib, unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
O = ROOT / 'outputs/long_sentence_imagination/2026-10-14_68회차'
import os
out_dir, csv_path, label = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
DUMP = Path(os.environ.get('DUMP', str(O/'inputs/dump')))
variant = len(sys.argv) > 4 and sys.argv[4] == 'variant'
man = {m['name']: m for m in json.load(open(O/'inputs/manifest.json'))}
if variant:
    for m in json.load(open(O/'inputs/variant_manifest.json')): man[m['name']] = m
raw = list(csv.DictReader(open(csv_path, encoding='utf-8-sig')))
def norm_row(r):
    r = {k.replace(' ', ''): v for k, v in r.items()}
    if '지문' not in r and '내용지문' in r: r['지문'] = r['내용지문']
    if r.get('새경로') and not r['새경로'].startswith('/'): r['새경로'] = str(out_dir / r['새경로'])
    return r
rows = {unicodedata.normalize('NFC', r['원래이름']): r for r in map(norm_row, raw)}
checks = []
def c(name, ok, detail=''): checks.append({'check': name, 'ok': bool(ok), 'detail': detail})
c('목록 행수 = 입력 파일 수', len(rows) == len(man), f'{len(rows)} vs {len(man)}')
c('모든 입력이 목록에 있음', set(rows) == set(man), sorted(set(man) ^ set(rows)))
c('지문 = sha256 일치', all(rows[n]['지문'] == man[n]['sha256'] for n in rows if n in man), [n for n in rows if n in man and rows[n]['지문'] != man[n]['sha256']])
exp_date = {'IMG_0001.jpg':'2026-10-03','IMG_0002.jpg':'2026-10-03','IMG_0002 복사본.jpg':'2026-10-03','IMG_0003.jpg':'2026-10-03','IMG_0003_edit.jpg':'2026-10-03','IMG_0004.jpg':'2026-10-03','IMG_0005.jpg':'2026-10-04','IMG_0006.jpg':'2026-10-04','IMG_0007.jpg':'2026-10-04','KakaoTalk_20261004_154110.jpg':'2026-10-04','IMG_0008.jpg':'2026-10-10','IMG_0009.jpg':'2026-10-10','Screenshot_2026-10-01.png':'2026-10-01','memo_01.m4a':'2026-10-03','memo_02.m4a':'2026-10-10','memo_03.m4a':'2026-10-11','IMG_0010.jpg':'2026-10-04','IMG_0005 (1).jpg':'2026-10-04','memo_04.m4a':'2026-10-04'}
bad = [(n, rows[n]['날짜'], d) for n, d in exp_date.items() if n in rows and rows[n]['날짜'] != d]
c('날짜(EXIF 우선, PNG·음성은 파일 시각)', not bad, bad)
c('PNG 날짜 출처 표시', 'Screenshot_2026-10-01.png' in rows and '파일 시각' in rows['Screenshot_2026-10-01.png']['날짜출처'])
dups = {n for n, r in rows.items() if r['분류'] == '중복'}
exp_dups = {'IMG_0002.jpg', 'KakaoTalk_20261004_154110.jpg'} | ({'IMG_0005 (1).jpg'} if variant else set())
c('정확 중복 집합', dups == exp_dups, sorted(dups ^ exp_dups))
c('중복 행의 새경로가 중복 폴더에 실존', all(Path(rows[n]['새경로']).exists() and '/중복/' in rows[n]['새경로'] for n in dups))
c('유사 중복 후보 = IMG_0003_edit', {n for n, r in rows.items() if r['분류'] == '유사중복후보'} == {'IMG_0003_edit.jpg'}, sorted(n for n, r in rows.items() if r['분류'] == '유사중복후보'))
c('손상 파일 읽기실패·제자리', rows.get('IMG_0099.jpg', {}).get('분류') == '읽기실패' and (DUMP/'IMG_0099.jpg').exists(), rows.get('IMG_0099.jpg', {}).get('분류'))
c('기타 파일 손대지 않음', rows.get('notes.txt', {}).get('분류') == '기타' and (DUMP/'notes.txt').exists())
albums = sorted(p.name for p in (out_dir/'앨범').iterdir() if p.is_dir())
exp_albums = {'2026-10-01', '2026-10-03', '2026-10-04', '2026-10-10'}
c('앨범 날짜 집합', {a[:10] for a in albums} == exp_albums, albums)
c('앨범 주제 2~6글자', all(2 <= len(a[11:]) <= 6 for a in albums), [a[11:] for a in albums])
exp_count = {'2026-10-01': 1, '2026-10-03': 5, '2026-10-04': 4 if variant else 3, '2026-10-10': 2}
got_count = {a[:10]: len(list((out_dir/'앨범'/a).glob('*'))) for a in albums}
c('앨범별 파일수', all(got_count.get(k) == v for k, v in exp_count.items()), got_count)
names_ok = []
for a in albums:
    for f in (out_dir/'앨범'/a).iterdir():
        n = unicodedata.normalize('NFC', f.name); names_ok.append(len(n) > 16 and n[8] == '_' and n[15] == '_' and n[:8].isdigit() and n[9:15].isdigit())
c('파일 이름 YYYYMMDD_HHMMSS_원래이름', all(names_ok), sum(names_ok))
exif_names = {'20261003_110512_IMG_0001.jpg', '20261004_152033_IMG_0005.jpg', '20261001_201500_Screenshot_2026-10-01.png'}
all_names = {unicodedata.normalize('NFC', f.name) for a in albums for f in (out_dir/'앨범'/a).iterdir()}
c('EXIF 시각으로 이름 붙음(표본 3)', exif_names <= all_names, sorted(exif_names - all_names))
voice = {n: r for n, r in rows.items() if r['분류'] in ('음성', '미분류')}
c('음성 3+변형', len(voice) == (4 if variant else 3), len(voice))
c('memo_01→2026-10-03 폴더', (out_dir/'음성/2026-10-03/memo_01.m4a').exists() and (out_dir/'음성/2026-10-03/memo_01.txt').exists())
c('memo_02→2026-10-10 폴더', (out_dir/'음성/2026-10-10/memo_02.m4a').exists())
c('memo_03 무음→미분류+사유', (out_dir/'음성/미분류/memo_03.m4a').exists() and rows.get('memo_03.m4a', {}).get('분류') == '미분류' and '무음' in rows.get('memo_03.m4a', {}).get('비고', ''))
rep_path = csv_path.parent/'보고서.md'
rep = rep_path.read_text(encoding='utf-8') if rep_path.exists() else ''
c('보고서: 전사→앨범 연결', 'memo_01' in rep and '연결 앨범: 2026-10-03' in rep and '연결 앨범: 2026-10-10' in rep)
c('보고서: 유사 중복 후보 쌍', 'IMG_0003_edit.jpg' in rep and 'IMG_0003.jpg' in rep)
c('보고서: 재확인 절', '재확인' in rep and '일치: true' in rep)
t1 = (out_dir/'음성/2026-10-03/memo_01.txt').read_text(encoding='utf-8') if (out_dir/'음성/2026-10-03/memo_01.txt').exists() else ''
c('전사문 내용(생신·산책)', '생신' in t1 and '산책' in t1)
if variant:
    c('변형: 기존 앨범 주제 유지(2026-10-04)', any(a.startswith('2026-10-04_') for a in albums) and (out_dir/'앨범'/[a for a in albums if a.startswith('2026-10-04_')][0]/'20261004_161200_IMG_0010.jpg').exists())
    c('변형: memo_04→2026-10-04 + 연결', (out_dir/'음성/2026-10-04/memo_04.m4a').exists() and '연결 앨범: 2026-10-04' in rep)
    base_rows = list(csv.DictReader(open(out_dir.parent/'base_snapshot/목록.csv', encoding='utf-8')))
    cur = raw
    c('변형: 기존 행 불변', cur[:len(base_rows)] == base_rows)
passed = sum(1 for x in checks if x['ok'])
res = {'label': label, 'passed': passed, 'total': len(checks), 'checks': checks}
print(json.dumps({'label': label, 'passed': passed, 'total': len(checks), 'failed': [x for x in checks if not x['ok']]}, ensure_ascii=False, indent=1))
(Path(__file__).resolve().parents[1]/'evidence'/f'verify-{label}.json').write_text(json.dumps(res, ensure_ascii=False, indent=1))
