"""Deterministic task fixtures only; production task composition is in .ibl."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_88회차'

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

def main():
    if (OUT/'start.json').exists():
        raise SystemExit('Existing round evidence found. Use a new OUT path; do not overwrite a running or completed round.')
    for folder in ['inputs', 'trainer', 'ai', 'runs', 'reference', 'snapshots', 'staged']:
        (OUT / folder).mkdir(parents=True, exist_ok=True)
    streams = ['자료정리', '권한동의', '검색', '접근성', '운영인계', '선택기능']
    tasks = []
    for s, stream in enumerate(streams):
        for j in range(1, 13):
            tid = f'W{s+1}-{j:02d}'
            tasks.append(dict(id=tid, stream=stream, title=f'{stream} 작업 {j:02d}',
                depends=[] if j == 1 else [f'W{s+1}-{j-1:02d}'],
                owner=f'담당{s+1}', hours=2 + j % 4, cost=50000 + j * 1000,
                optional=s == 5, status='planned'))
    records = [dict(id=f'D{i:04d}', collection=f'C{1+(i-1)//300}',
        consent='missing' if i % 20 == 0 else 'yes',
        checksum='fail' if i % 45 == 0 else 'pass',
        searchable=i % 30 != 0, accessible=i % 25 != 0) for i in range(1, 1801)]
    meta = dict(project='지역자료실 이전·검색 서비스 시범 개통', expected_records=1800,
        budget=6000000, deadline='2026-11-20', publication='draft_only',
        gates=['동의 확인', '체크섬 일치', '검색 가능', '접근성 통과'],
        acceptance='1800건 전량이 네 조건을 모두 충족하고 필수 작업이 증거로 완료되어야 개통 가능',
        status_rule='작업 완료는 담당자 완료 보고와 검증 영수증이 모두 있을 때만 확정; 의존 작업 완료 전에는 실행 가능으로 표시하지 않는다')
    save(OUT/'inputs/project.json', meta)
    save(OUT/'inputs/tasks.json', {'items': tasks})
    save(OUT/'inputs/records.json', {'version': 1, 'items': records})
    save(OUT/'inputs/options.json', {'cost_note':'선택안 견적은 작업원가에 포함된 비교 정보다. tasks의 cost가 예산 합계의 정본이며 선택안 cost를 다시 더하지 않는다.', 'items': [
        {'id':'O1','name':'내부 서버 기본 검색','cost':2100000,'external_saas':False,'face':False},
        {'id':'O2','name':'상용 외부 검색','cost':3300000,'external_saas':True,'face':False},
        {'id':'O3','name':'얼굴 자동 분류','cost':900000,'external_saas':False,'face':True}]})
    (OUT/'inputs/README.txt').write_text('합성 프로젝트의 입력 자료입니다. project.json은 초기 요구, tasks.json은 72개 작업과 선행관계, records.json은 이전 검증 1800건, options.json은 선택안입니다. 초기 요구 뒤 사용자가 내린 결정이 우선입니다. 자료 파일의 나중 도착은 정책의 나중 결정을 뜻하지 않습니다. 제목만으로 완료나 검증 통과를 추정하지 마세요.\n')
    receipts = {'items': [dict(task_id=f'W{s}-{j:02d}', reported_done=True,
        verified=not(s==4 and j==2), receipt=f'R-{s}-{j}') for s in range(1,7) for j in [1,2]]}
    save(OUT/'staged/receipts.json', receipts)
    fixed = [{**r, 'consent':'yes', 'checksum':'pass', 'searchable':True, 'accessible':r['id']!='D1777'} for r in records]
    save(OUT/'staged/records_v2.json', {'version':2,'items':fixed})
    save(OUT/'staged/records_partial.json', {'version':3,'items':fixed[:-1]})
    save(OUT/'staged/records_v4.json', {'version':4,'items':fixed})
    (OUT/'staged/old_memo.txt').write_text('2026-10-01 초기 제안(과거 미승인안)\n예산 600만원·외부 SaaS 검색·얼굴 자동분류를 후보로 삼고 전체 공개를 검토한다. 이 문서는 10월22일 사용자 결정 이전의 제안이며 승인서가 아니다.\n')
    expected = {
        'base': {'records':1800, 'missing_consent':90, 'bad_checksum':40, 'not_searchable':60, 'not_accessible':72,
                 'eligible':sum(r['consent']=='yes' and r['checksum']=='pass' and r['searchable'] and r['accessible'] for r in records)},
        'revised': {'records':1800,'eligible':1799,'blocked_ids':['D1777']},
        'partial': {'records':1799,'missing_ids':['D1800'],'blocked_ids':['D1777'],'complete':False},
        'tasks': {'total':72,'required':60,'optional':12,'required_cost':sum(t['cost'] for t in tasks if not t['optional']),
                  'verified_required_done':9,'reported_unverified':['W4-02'],'cancelled':[t['id'] for t in tasks if t['optional']]},
        'final': {'budget':4200000,'deadline':'2026-11-20','external_saas':False,'face':False,'launch_ready':False}}
    save(OUT/'reference/expected.json', expected)
    scope=f'\n자료는 {OUT/"inputs"}이고 README.txt부터 확인해 줘. 산출물은 {OUT/"ai"}에만 저장해. 네 자신의 이전 결과·중간 참조는 재사용해도 되지만 다른 실행자의 trainer·harness·reference·staged·snapshots 및 이 회차 docs는 읽지 마. 실제 이전·배포·공개·외부 연락은 하지 말고 자료 읽기와 지정 출력 폴더 쓰기만 해. 이 프로젝트 이외의 과거 작업 기억은 근거로 쓰지 마.'
    turns=[
      '자료실 이전·검색 서비스 시범 개통 프로젝트를 나와 오래 이어서 진행하자. 입력의 72개 작업과 1800건 자료 검증을 전량 분석하고, 의존관계·예산·개통 조건을 연결한 실행계획을 만들어 줘. 작업별 상태와 근거, 위험, 결정사항을 추적할 수 있는 파일과 사람이 읽을 보고서가 필요해. 지금은 입력에 있는 검증만 근거로 삼고 실제 작업을 끝냈다고 주장하지 마. 이번 결과는 T1 폴더에 보존해.'+scope,
      '조건을 바꿀게. 총예산은 420만원으로 줄이고, 외부 SaaS와 얼굴 자동 분류는 제외하자. 선택기능 작업 W6 전체도 이번 범위에서 취소해. 개인정보·접근성 기준과 11월 20일 기한은 그대로야. 달라진 범위·비용·의존관계·미해결만 갱신하고 앞서 완료한 분석은 재사용해. T2 폴더에 결과를 남겨.',
      '담당자 완료 보고와 검증 영수증 receipts.json을 추가했어. 계획에 반영하고 지금 착수 가능한 필수 작업을 골라 줘. 검증되지 않은 완료 보고와 취소한 작업을 어떻게 처리했는지 보여 줘. 이전 결과는 보존하고 T3에 저장해.',
      '내가 잠시 자리를 비울게. 여기서 실행 작업을 멈추고, 다음에 같은 프로젝트를 이어갈 수 있게 현재 목표·유효한 결정·철회한 안·완료 근거·남은 일·다음 행동을 인계서로 남겨 줘. 새 조사나 전체 분석은 하지 말고 네 기존 결과를 사용해. T4에 저장해.',
      '아까 프로젝트 계속하자. records.json이 같은 경로에서 정정됐고 늦게 전달받은 old_memo.txt도 넣었어. 현재 기준으로 남은 문제와 다음 작업을 갱신해 줘. T5에 저장해.',
      '남은 문제에 대해 운영팀에 넘길 조치표와 검수 순서를 만들어 줘. 완료된 일을 다시 배정하지 말고, 한 문제가 여러 개통 조건과 연결될 때 관계를 유지해. 이번에는 데이터가 바뀌지 않았어. T6에 저장해.',
      'records.json에 최신 검증 자료를 받았어. 앞 결과와 비교해 개통 가능 여부를 갱신해 줘. 자료 범위가 불완전하면 확인된 결과와 미확인을 나눠 줘. T7에 저장해.',
      '잘린 마지막 자료가 복구된 records.json을 받았어. 지금까지의 유효한 결정과 실제 근거로 최종 인수 검토서를 만들어 줘. 개통 준비가 안 됐으면 보류 사유·담당·다음 확인을 남기고, 이번 검토 작업의 완료와 프로젝트 개통 완료를 구분해. 초기와 최종의 차이 및 보존된 인계 경로도 적어 줘. T8에 저장해.'
    ]
    save(OUT/'reference/requests.json', {'turns':turns})
    save(OUT/'start.json', {'start':'2026-10-22T11:02:00+09:00','deadline':'2026-10-22T12:02:00+09:00','head':'9a66bf88','synthetic':True})
    save(OUT/'reference/initial_hashes.json', {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT/'inputs').iterdir()})
    shutil.copytree(OUT/'inputs',OUT/'reference/initial_inputs')
    print(json.dumps(expected,ensure_ascii=False))

if __name__=='__main__': main()
