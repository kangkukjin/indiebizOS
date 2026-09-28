"""74회차 격리 재현 — 탐침 밖에서 오진을 가르려고 찍은 최소 재현을 다시 찍는 스크립트 (훈련 턴 · 무수정).

전부 스크래치(outputs/IT74_x·IT74_y)에서만 쓴다. 스캔 볼륨은 끝에 앱 REST 로 지운다.
각 항목 = (문장, 응답 요지, 실행 뒤 디스크 상태). 결과는 isolation.json.
사용: .venv/bin/python isolate.py
"""
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402  같은 ex()/post()/LOG 를 쓴다

OUT = probe.OUT
X = OUT / 'IT74_x'
Y = OUT / 'IT74_y'
WX = '~workspace/outputs/IT74_x'
WY = '~workspace/outputs/IT74_y'
ROWS = []


def tree(d):
    return sorted(str(p.relative_to(OUT)) for p in d.rglob('*')) if d.exists() else ['(없음: ' + d.name + ')']


def album():
    if X.exists():
        shutil.rmtree(X)
    (X / '앨범' / '2026').mkdir(parents=True)
    (X / '앨범' / 'a.jpg').write_text('a')
    (X / '앨범' / '2026' / 'b.jpg').write_text('b')


def rec(name, code, before):
    r = probe.ex(code)
    ROWS.append({'case': name, 'code': code, 'before': before,
                 'success': r.get('success'), 'value': r.get('value'),
                 'error': r.get('error'), 'code_diag': (r.get('diagnostic') or {}).get('code'),
                 'after': tree(X) if X.exists() else tree(Y)})
    print(name, r.get('success'), (r.get('diagnostic') or {}).get('code'), ROWS[-1]['after'])


def main():
    # I1 폴더 복사 src == dest(다른 표기) — 원본 폴더가 사라지는가
    album()
    rec('I1 copy src==dest', f'return [self:copy]{{src:"{WX}/앨범", dest:"{X}/앨범"}}', tree(X))
    # I2 폴더 복사 dest = src 의 조상 — 조상 폴더 전체가 사라지는가
    album()
    rec('I2 copy dest=ancestor', f'return [self:copy]{{src:"{WX}/앨범/2026", dest:"{WX}/앨범"}}', tree(X))
    # I3 이동 dest = src 의 조상 (같은 뿌리의 형제 동사)
    album()
    rec('I3 move dest=ancestor', f'return [self:move]{{src:"{WX}/앨범/2026", dest:"{WX}/앨범"}}', tree(X))
    # I4 파일을 기존 폴더로 복사 — 같은 이름 파일 덮어쓰기
    album()
    (X / 'bk').mkdir()
    (X / 'bk' / 'c.txt').write_text('OLD')
    (X / 'c.txt').write_text('NEW')
    rec('I4 copy file into existing dir', f'return [self:copy]{{src:"{WX}/c.txt", dest:"{WX}/bk"}}', tree(X))
    ROWS[-1]['bk_c_txt'] = (X / 'bk' / 'c.txt').read_text()
    # I5 없는 경로 삭제의 실패 분류 — $error.code
    rec('I5 delete missing error code',
        f'[try] {{ $x = [self:delete]{{path:"{WX}/없는.zip"}} }} [catch] {{ $x = $error.code }}\nreturn $x', tree(X))
    shutil.rmtree(X)
    # I6 스캔 — 잠긴 하위 폴더 하나 / 깨진 심볼릭 링크 하나
    (Y / 'ok').mkdir(parents=True)
    (Y / 'locked').mkdir()
    (Y / 'ok' / 'a.txt').write_text('1')
    (Y / 'locked' / 'b.txt').write_text('2')
    os.chmod(Y / 'locked', 0o000)
    rec('I6 scan with locked subfolder', f'return [self:storage]{{op:"scan", path:"{WY}"}}', ['locked=000'])
    os.chmod(Y / 'locked', 0o755)
    os.symlink('/nonexistent/target', Y / 'ok' / 'broken_link')
    rec('I7 scan with broken symlink', f'return [self:storage]{{op:"scan", path:"{WY}"}}', ['broken_link'])
    (Y / 'ok' / 'broken_link').unlink()
    # I8 폴더 메모 — 코퍼스 형태(path 하나)를 스캔 루트의 하위 폴더에
    rec('I8 scan clean', f'return [self:storage]{{op:"scan", path:"{WY}"}}', [])
    rec('I9 folder_note corpus form on subfolder', f'return [self:folder_note]{{op:"set", path:"{WY}/ok", note:"IT74 코퍼스형"}}', [])
    rec('I10 summary on subfolder of scanned root', f'return [self:storage]{{op:"summary", root_path:"{WY}/ok"}}', [])
    # I11 "/" 가 스캔돼 있는데 홈 아래 경로 요약·메모 — 쓰기 없음(정확 일치 없음)
    rec('I11 summary ~/Downloads under scanned /', 'return [self:storage]{op:"summary", root_path:"~/Downloads"}', [])
    # I12 등록 스크립트 폴더용량 — 설명(outputs) 과 실제 측정 루트
    rec('I12 script 폴더용량', '$s = [self:script]{id:"폴더용량"}\nreturn $s.items >> [table:take]{n:4}', [])
    dropped = probe.drop_scratch_scans()
    shutil.rmtree(Y)
    (Path(__file__).resolve().parent / 'isolation.json').write_text(
        json.dumps({'rows': ROWS, 'dropped_scans': dropped, 'log': probe.LOG}, ensure_ascii=False, indent=1))
    print('dropped', dropped, 'residue', [p.name for p in OUT.glob('IT74_*')])


if __name__ == '__main__':
    main()
