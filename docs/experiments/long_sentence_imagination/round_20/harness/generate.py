"""Synthetic inputs only. No production files or task implementation."""
import csv
import json
from pathlib import Path


def generate(folder, *, terminator='\r\n', bom=False, empty_last=False):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    notes = ['일반', '쉼표, 따옴표 "확인"', '두 줄\r\n유지', '캐리지\r리턴', '탭\t유지', '줄\n바꿈']
    for component in range(3):
        part = [dict(component=f'part{component}', path=f'part{component}/file{i}.bin',
                     expected_bytes=str(100 + component * 10 + i), note=notes[i]) for i in range(6)]
        with (folder / f'part{component}.csv').open('w', encoding='utf-8-sig' if bom else 'utf-8', newline='') as stream:
            if not (empty_last and component == 2):
                writer = csv.DictWriter(stream, fieldnames=list(part[0]), lineterminator=terminator,
                                        quoting=csv.QUOTE_ALL if terminator == '\r' else csv.QUOTE_MINIMAL)
                writer.writeheader()
                writer.writerows(part)
        rows.extend(part)
    actual = [dict(path=row['path'], bytes=int(row['expected_bytes']))
              for row in rows if row['path'] != 'part0/file0.bin']
    actual[0]['bytes'] = 999
    actual.extend([dict(path='part0/file2.bin', bytes=102), dict(path='extra.bin', bytes=9)])
    (folder / 'actual.json').write_text(json.dumps(actual, ensure_ascii=False), encoding='utf-8')
    return rows


if __name__ == '__main__':
    import sys
    generate(sys.argv[1])
