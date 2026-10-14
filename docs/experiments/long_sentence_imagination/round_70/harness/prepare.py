"""Generate public synthetic notices, input-only AI copies, and a local HTTP fixture."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-15_70회차'
BASE = 'http://127.0.0.1:8876'

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

def notice(n):
    return {'event_id': f'E{n:02}', 'title': f'{["행사", "모집", "나눔"][n % 3]} 소식 {n:02}',
            'region': ['동쪽동', '서쪽동', '중앙동'][n % 3],
            'date': None if n in (10,20) else f'2026-10-{10 + n % 15:02}',
            'status': 'cancelled' if n % 11 == 0 else 'active',
            'updated_at': '2026-10-14T09:00:00+09:00',
            'description': f'합성 동네 공지 {n:02}. 참가 조건은 원문을 확인하세요.'}

def build():
    snapshots = {}
    for phase in ('base','variant','new'):
        docs = {}
        for wh, ids in [('a',range(1,19)),('b',range(19,37)),('c',range(1,19))]:
            docs[wh] = []
            for n in ids:
                row=notice(n)
                if wh=='c' and n==5: row['date']='2026-10-19'
                if wh=='c' and n==6:
                    row.update(date='2026-10-20',updated_at='2026-10-14T10:00:00+09:00')
                if phase!='base' and wh=='a' and n in (8,9):
                    row.update(updated_at='2026-10-15T10:00:00+09:00')
                    row.update(status='cancelled') if n==8 else row.update(date='2026-10-21')
                if phase=='new' and wh=='b' and n==21:
                    row.update(date='2026-10-17',updated_at='2026-10-15T11:00:00+09:00')
                docs[wh].append(row)
        snapshots[phase]=docs
    save(HERE/'fixtures/notices.json', snapshots)
    for who in ('trainer','ai'):
        for phase in snapshots:
            inp={'start':'2026-10-15','end':'2026-10-21',
                 'warehouses':[{'id':k,'name':name,'url':f'{BASE}/{who}/{phase}/{k}'}
                               for k,name in [('a','동네회관'),('b','마을도서관'),('c','주민모임')]]}
            save(OUT/f'{who}-input/{phase}.json',inp)
    save(HERE/'evidence/expected.json', {
        'notices':54,'unique_events':36,'variant_failed_warehouse':'b',
        'conflict':['E05'],'undated':['E10','E20'],
        'variant_cancel':'E08','variant_moved':'E09'})

if __name__=='__main__': build()
