#!/usr/bin/env python3
"""사진·음성 묶음 정리 — survey(조사, 부작용 없음) / apply(원장 기반 적용)."""
import csv, hashlib, json, os, shutil, subprocess, sys, datetime, unicodedata

PHOTO = {'.jpg', '.jpeg', '.png'}
AUDIO = {'.m4a'}
COLS = ['원래 이름', '새 경로', '날짜', '날짜 출처', '내용 지문', '분류', '핵심어', '묘사', '비고']


def nfc(s):
    return unicodedata.normalize('NFC', s)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 16), b''):
            h.update(b)
    return h.hexdigest()


def ledger_rows(org):
    p = os.path.join(org, '목록.csv')
    if not os.path.exists(p):
        return []
    with open(p, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def probe_photo(p):
    from PIL import Image
    r = {}
    try:
        with Image.open(p) as im:
            r['width'], r['height'] = im.size
            exif = im.getexif()
            dto = None
            try:
                dto = exif.get_ifd(0x8769).get(36867)  # DateTimeOriginal
            except Exception:
                dto = None
            if not dto:
                dto = exif.get(36867)
            im.load()  # 실제 디코드
        r['decodable'] = True
        if dto:
            try:
                dt = datetime.datetime.strptime(str(dto).strip('\x00 '), '%Y:%m:%d %H:%M:%S')
                r['taken'] = dt.isoformat(); r['date_source'] = 'EXIF'
            except ValueError:
                r['exif_raw'] = str(dto)
    except Exception as e:
        r['decodable'] = False
        r['error'] = f'{type(e).__name__}: {e}'
    return r


def probe_audio(p):
    try:
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,codec_name',
                              '-of', 'json', p], capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return {'decodable': False, 'error': out.stderr.strip()[:300] or 'ffprobe 실패'}
        d = json.loads(out.stdout)
        return {'decodable': True, 'duration': float(d.get('format', {}).get('duration') or 0),
                'streams': d.get('streams', [])}
    except Exception as e:
        return {'decodable': False, 'error': f'{type(e).__name__}: {e}'}


def survey(src, org):
    done = {(nfc(r['원래 이름']), r['내용 지문']) for r in ledger_rows(org)}
    done_names = {nfc(r['원래 이름']) for r in ledger_rows(org) if r['분류'] not in ('읽기실패', '기타')}
    items = []
    for name in sorted(os.listdir(src)):
        p = os.path.join(src, name)
        if not os.path.isfile(p) or name.startswith('.'):
            continue
        ext = os.path.splitext(name)[1].lower()
        kind = 'photo' if ext in PHOTO else 'audio' if ext in AUDIO else 'other'
        st = os.stat(p)
        fp = sha(p)
        it = {'name': nfc(name), 'path': p, 'kind': kind, 'size': st.st_size, 'sha256': fp,
              'mtime': datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds'),
              'already': (nfc(name), fp) in done or nfc(name) in done_names}
        if kind == 'photo':
            it.update(probe_photo(p))
            if it.get('decodable') and 'taken' not in it:
                it['taken'] = it['mtime']; it['date_source'] = '파일시각'
        elif kind == 'audio':
            it.update(probe_audio(p))
        items.append(it)
    return {'src': src, 'org': org, 'items': items}


def unique_dest(d, name):
    os.makedirs(d, exist_ok=True)
    base, ext = os.path.splitext(name)
    cand, n = os.path.join(d, name), 2
    while os.path.exists(cand):
        cand = os.path.join(d, f'{base} ({n}){ext}'); n += 1
    return cand


def apply(plan_path):
    plan = json.load(open(plan_path, encoding='utf-8'))
    src, org = plan['src'], plan['org']
    os.makedirs(org, exist_ok=True)
    old = ledger_rows(org)
    done = {(nfc(r['원래 이름']), r['내용 지문']) for r in old}
    # 원장의 읽기실패·기타는 제자리 파일이라 다시 보되(바뀌면 재판정) 행은 갱신한다
    keep_old = []
    retry = set()
    for r in old:
        if r['분류'] in ('읽기실패', '기타'):
            retry.add(nfc(r['원래 이름']))
        else:
            keep_old.append(r)
    album_root = os.path.join(org, '앨범')
    existing = {}
    if os.path.isdir(album_root):
        for d in sorted(os.listdir(album_root)):
            if len(d) > 11 and d[10] == '_':
                existing.setdefault(d[:10], d)
    topics = plan.get('topics', {})
    new_rows, processed = [], 0
    stay = {}  # 제자리 행(읽기실패·기타)은 이번 실행 판정으로 대체
    for it in plan['items']:
        name = it['name']
        key = (name, it['sha256'])
        if it['kind'] == 'other' or it.get('outcome') == '읽기실패':
            stay[name] = {'원래 이름': name, '새 경로': '(제자리) ' + os.path.join(src, name),
                          '날짜': '', '날짜 출처': '', '내용 지문': it['sha256'],
                          '분류': '기타' if it['kind'] == 'other' else '읽기실패', '핵심어': '',
                          '묘사': '', '비고': it.get('reason', '사진·음성이 아닌 파일 — 손대지 않음')}
            continue
        if key in done or it.get('already'):
            continue
        p = os.path.join(src, name)
        if not os.path.exists(p) or sha(p) != it['sha256']:
            stay[name] = {'원래 이름': name, '새 경로': '(제자리) ' + p, '날짜': '', '날짜 출처': '',
                          '내용 지문': it['sha256'], '분류': '읽기실패', '핵심어': '', '묘사': '',
                          '비고': '조사 이후 파일이 바뀌거나 사라짐 — 다음 실행에서 재조사'}
            continue
        o = it['outcome']
        date = it.get('date', '')
        if o == '중복':
            dest = unique_dest(os.path.join(org, '중복'), name)
        elif o in ('앨범', '유사중복후보'):
            folder = existing.get(date) or f"{date}_{topics[date]}"
            existing.setdefault(date, folder)
            ts = datetime.datetime.fromisoformat(it['taken']).strftime('%Y%m%d_%H%M%S')
            dest = unique_dest(os.path.join(album_root, folder), f'{ts}_{name}')
        elif o == '음성':
            dest = unique_dest(os.path.join(org, '음성', date), name)
        elif o == '미분류':
            dest = unique_dest(os.path.join(org, '음성', '미분류'), name)
        else:
            raise ValueError(f'알 수 없는 분류 {o} ({name})')
        shutil.move(p, dest)
        if o == '음성':
            txt = os.path.splitext(dest)[0] + '.txt'
            if os.path.exists(txt):
                raise FileExistsError(txt)
            with open(txt, 'w', encoding='utf-8') as f:
                f.write(it['transcript'].rstrip() + '\n')
        processed += 1
        new_rows.append({'원래 이름': name, '새 경로': os.path.relpath(dest, org), '날짜': date,
                         '날짜 출처': it.get('date_source', ''), '내용 지문': it['sha256'], '분류': o,
                         '핵심어': ' / '.join(it.get('keywords', [])), '묘사': it.get('desc', ''),
                         '비고': it.get('note', '')})
    # 지난 원장의 제자리 행 중 이번에 처리·재판정되지 않은 것(파일이 사라진 경우)은 보존
    for r in old:
        if nfc(r['원래 이름']) in retry and nfc(r['원래 이름']) not in stay \
                and nfc(r['원래 이름']) not in {x['원래 이름'] for x in new_rows}:
            stay[nfc(r['원래 이름'])] = r
    rows = keep_old + new_rows + [stay[k] for k in sorted(stay)]
    tmp = os.path.join(org, '.목록.csv.tmp')
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in COLS})
    os.replace(tmp, os.path.join(org, '목록.csv'))
    return {'processed_new': processed, 'rows': len(rows),
            'albums': sorted(os.listdir(album_root)) if os.path.isdir(album_root) else []}


def verify(src, org):
    rows = ledger_rows(org)
    def count(sub):
        root = os.path.join(org, sub); n = 0
        for dp, _, fs in os.walk(root):
            n += sum(1 for f in fs if not f.startswith('.'))
        return n
    exp_album = sum(1 for r in rows if r['새 경로'].startswith('앨범/'))
    exp_dup = sum(1 for r in rows if r['새 경로'].startswith('중복/'))
    exp_voice = sum(1 for r in rows if r['새 경로'].startswith('음성/'))
    exp_voice_txt = sum(1 for r in rows if r['분류'] == '음성')
    missing = [r['새 경로'] for r in rows if not r['새 경로'].startswith('(제자리)')
               and not os.path.exists(os.path.join(org, r['새 경로']))]
    left = sorted(nfc(f) for f in os.listdir(src) if not f.startswith('.'))
    stay = sorted(nfc(r['원래 이름']) for r in rows if r['분류'] in ('읽기실패', '기타'))
    per_album = {}
    for d in sorted(os.listdir(os.path.join(org, '앨범'))) if os.path.isdir(os.path.join(org, '앨범')) else []:
        per_album[d] = {'actual': len([f for f in os.listdir(os.path.join(org, '앨범', d)) if not f.startswith('.')]),
                        'ledger': sum(1 for r in rows if r['새 경로'].startswith(f'앨범/{d}/'))}
    res = {'album': [count('앨범'), exp_album], 'dup': [count('중복'), exp_dup],
           'voice': [count('음성'), exp_voice + exp_voice_txt], 'per_album': per_album,
           'missing_paths': missing, 'src_left': left, 'ledger_stay': stay,
           'src_only_stay': left == stay, 'rows': len(rows)}
    res['ok'] = (res['album'][0] == res['album'][1] and res['dup'][0] == res['dup'][1]
                 and res['voice'][0] == res['voice'][1] and not missing and res['src_only_stay']
                 and all(v['actual'] == v['ledger'] for v in per_album.values()))
    return res


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'survey':
        out = survey(sys.argv[2], sys.argv[3])
    elif mode == 'apply':
        out = apply(sys.argv[2])
    elif mode == 'verify':
        out = verify(sys.argv[2], sys.argv[3])
    print(json.dumps(out, ensure_ascii=False, indent=1))
