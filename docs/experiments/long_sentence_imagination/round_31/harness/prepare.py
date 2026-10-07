"""Synthetic inputs and transport requests; never implement the trainer task here."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DOC = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-07_31회차'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    inventory = []
    for n in range(26):
        name = f'장비 {n:02}.log'
        inventory.append({'device': f'D{n:02}', 'file': name, 'zone': f'Z{n % 3}'})
        if n == 25:
            continue
        lines = []
        if n != 24:
            for j in range(160):
                marker = 'OK'
                if (j + n) % 17 == 0:
                    marker = 'WARN[2] WARN[2]'
                elif (j + n) % 23 == 0:
                    marker = '-ALARM[1] -ALARM[1]'
                elif j % 31 == 0:
                    marker = 'warn[2] -alarm[1]'
                lines.append(f'{j + 1:04} {marker} 점검 {n}/{j}')
        newline = '\r\n' if n % 2 else '\n'
        (OUT / 'source' / name).write_bytes((newline.join(lines) + (newline if lines else '')).encode())
    dump(OUT / 'source/inventory.json', inventory)
    # Diagnosis-assisted and post-repair robustness inputs; separate from the initial task.
    mixed = OUT / 'source_mixed'
    shutil.copytree(OUT / 'source', mixed, dirs_exist_ok=True)
    old = mixed / '장비 00.log'
    old.write_bytes(old.read_bytes().decode().replace('점검', '점검  ').replace('\n', ' \t\n').encode('cp949'))
    spaced = mixed / '장비 01.log'
    spaced.write_bytes(spaced.read_bytes().replace(b'\r\n', b' \t\r\n'))
    new = OUT / 'source_new'
    shutil.copytree(mixed, new, dirs_exist_ok=True)
    boundary = new / '장비 02.log'
    boundary.write_text('WARN[2] 새 첫줄 \t\nWARN[2] 연속 줄 \t\n' + boundary.read_text() + 'WARN[2] 마지막 줄 \t')
    dump(new / 'inventory.json', list(reversed(inventory)))
    task = f'''장비 점검 로그를 감사해줘. 자료 폴더는 {OUT}/source야. inventory.json의 모든 장비를 빠짐없이 포함해줘. 파일 안에서 대소문자를 구분하여 리터럴 WARN[2]를 포함하는 줄을 찾고, 한 줄에 두 번 있어도 한 건으로 세어줘. 파일별 건수와 zone별 총건수, 전체 총건수를 만들어줘. 빈 파일과 일치가 없는 파일은 count=0, 파일이 없는 장비는 count=null/status="missing"으로 구분하고, 존재하는 파일의 status는 "ok"로 해줘. details.json에는 매칭된 모든 줄의 device/file/line/text와 앞뒤 한 줄을 담은 context를 남겨줘. context는 원문 줄을 줄번호와 함께 확인할 수 있으면 되고 앞뒤가 없는 경계는 있는 만큼만 포함해. summary.json은 devices(각 device/file/zone/status/count), zones(각 zone/count), total, missing_devices, complete 필드를 가져야 해. 알려진 누락을 정확히 표시하고 남은 자료를 전건 처리했으면 complete=true야. 출력은 {OUT}/ai/main 아래 저장하고 저장 결과의 합계와 상세 줄 수를 대조해줘. 원본은 읽기만 하고 지정 출력 안에만 써. 외부 발송·공개는 없어. 다른 실행자의 trainer/harness/drafts/evidence/정답은 보지 마. 네가 만든 산출물·중간 참조는 재사용 가능해. 시스템 코드·설정·가이드는 수정하지 마.'''
    (DOC / 'request.txt').write_text(task)
    dump(OUT / 'ai_main_request.json', {'message': task, 'origin': 'training', 'background': True})
    variant = f'같은 자료에 대해 검색할 리터럴만 -ALARM[1]로 바꿔줘. 대소문자를 구분하고, 앞선 요구의 모든 산출·검증 조건을 유지해. 출력은 {OUT}/ai/variant에 저장해서 첫 결과를 보존해. 네 자신의 직전 결과·중간 참조는 재사용해도 돼. 다른 실행자의 trainer/harness/drafts/evidence/정답은 보지 마.'
    (DOC / 'variant_request.txt').write_text(variant)
    dump(OUT / 'ai_variant_request.json', {'message': variant, 'origin': 'training', 'background': True})
    for label, pattern in [('main', 'WARN[2]'), ('variant', '-ALARM[1]')]:
        dump(OUT / f'{label}_request.json', {
            'code': (DOC / 'drafts/main_v0.ibl').read_text(),
            'origin': 'training', 'agent_id': 'LSI31_trainer', 'task_id': 'LSI31',
            'project_path': str(ROOT), 'budget': {'steps': 1000000, 'rows': 100000},
            'inputs': {'source': str(OUT / 'source'), 'out': str(OUT / 'trainer' / label), 'pattern': pattern},
        })


if __name__ == '__main__':
    main()
