"""67회차: 09-27 공통 값 연산 개정·Python 라이브러리 호출의 업무 조합 24과제.

외부 효과(쓰기·발신·예약)는 check만 한다. 모든 요청은 origin=training.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PY = '[self:script]{id:"python_libraries",args:'
FOLDER = ('$d=[self:list]{path:"~workspace/projects"} >> '
          '[table:filter]{where:($r)=>contains($r.name,"음악")}; $n=$d[0].name; ')

CASES = [
 ('T01', '가족신문 태그 문자열을 공백 정리·중복 제거해 한 줄로',
  '$t="해외 여행, 강의 ,음악,강의"; $s=split($t,",") >> [table:each]{strip($it)}; '
  'return join(", ",unique($s))',
  'value', '해외 여행, 강의, 음악'),
 ('T02', '강의 1차시엔 왔지만 2차시엔 빠진 학생',
  'return difference(["가","나","다"],["가","다"])', 'value', ['나']),
 ('T03', '강의 두 차시 모두 출석한 학생',
  'return intersection(["가","나","다"],["다","가"])', 'value', ['가', '다']),
 ('T04', '두 부동산 사이트 관심 매물 번호를 순서 보존해 합치기',
  'return union(["m1","m2"],["m2","m3"])', 'value', ['m1', 'm2', 'm3']),
 ('T05', '이름·점수 두 목록을 묶어 순위 문구 만들기',
  '$r=zip(["가","나","다"],[70,90,80]) >> [table:each]{return {이름:$it[0],점수:$it[1]}}; '
  '$s=sorted($r,"점수",true); '
  'return enumerate($s,1) >> [table:each]{return f"${$it[0]}위 ${$it[1].이름}"}',
  'value', ['1위 나', '2위 다', '3위 가']),
 ('T06', '강의 평균 평점을 JSON 문자열로 만들어 저장 준비',
  '$평균=3.5; return json({평균:$평균})', 'value', '{"평균": 3.5}'),
 ('T07', '학생별 평점 행 목록을 JSON 본문으로',
  'return json([{이름:"가",평점:4.5}])', 'value', '[{"이름": "가", "평점": 4.5}]'),
 ('T08', '가계부 분류별 지출 합계를 pandas로',
  '$t=' + PY + '{op:"call",target:"pandas:DataFrame",args:[[{분류:"식비",금액:12000},{분류:"교통",금액:3000},{분류:"식비",금액:8000}]]}}; '
  '$g=' + PY + '{receiver:$t,op:"call",name:"groupby",args:["분류"],kwargs:{as_index:false}}}; '
  '$s=' + PY + '{receiver:$g,op:"call",name:"sum",kwargs:{numeric_only:true}}}; '
  'return ' + PY + '{receiver:$s,op:"call",name:"to_dict",kwargs:{orient:"records"}}}',
  'value', [{'분류': '교통', '금액': 3000}, {'분류': '식비', '금액': 20000}]),
 ('T09', '관심 매물 두 곳의 평균 면적을 pandas로',
  '$t=' + PY + '{op:"call",target:"pandas:DataFrame",args:[[{면적:84.5},{면적:59.5}]]}}; '
  '$m=' + PY + '{receiver:$t,op:"call",name:"mean",kwargs:{numeric_only:true}}}; '
  'return ' + PY + '{receiver:$m,op:"call",name:"to_dict"}}',
  'value', {'면적': 72.0}),
 ('T10', '과제 점수 평균을 numpy로 구해 값으로 받기',
  'return ' + PY + '{op:"call",target:"numpy:mean",args:[[1,2,3]],result:"value"}}',
  'value', 2.0),
 ('T11', '음악 프로젝트 폴더명의 단어를 영문으로 바꾼 새 이름 만들기',
  FOLDER + 'return replace($n,"음악","music")', 'value', 'music'),
 ('T12', '음악 프로젝트 폴더명 첫 글자로 색인 머리 만들기',
  FOLDER + 'return $n[0:1]', 'value', '음'),
 ('T13', '음악 프로젝트 폴더명의 글자 수로 제목 폭 맞추기',
  FOLDER + 'return len($n)', 'value', 2),
 ('T14', '가족신문 원고를 여러 줄 본문으로 만들고 줄 수 확인',
  '$제목="가을 소풍"; $본문=f"""제목: ${$제목}\n작성: 나\n본문: 즐거웠다"""; '
  'return len(split($본문,"\\n"))',
  'value', 3),
 ('T15', '명단이 비었으면 발송 준비를 멈추고 안내',
  '$명단=[]; [try]{assert len($명단)>0, "명단이 비었습니다"; return "발송준비"}'
  '[catch]{return f"확인 필요: ${$error.message}"}',
  'value', '확인 필요: 명단이 비었습니다'),
 ('T16', '학생별로 60점 미달을 실패로 모으고 나머지는 계속',
  '$r=[{이름:"가",점수:50},{이름:"나",점수:80}] >> [table:each]{on_error:"collect"}'
  '{assert $it.점수>=60, "미달", {이름:$it.이름}; return $it.이름}; '
  'return [is_ok($r[0]),is_ok($r[1])]',
  'partial', [False, True]),
 ('T17', '공통 추출 옵션을 한 번 정의해 매물 상위 목록에 재사용',
  '$기본={n:2}; return [{id:"a"},{id:"b"},{id:"c"}] >> [table:take]{**$기본}',
  'value', [{'id': 'a'}, {'id': 'b'}]),
 ('T18', '원고 기본 정보에 상태만 덮어써 완료 기록 만들기',
  '$기본={상태:"초안",작성자:"나"}; return {**$기본, 상태:"완료", 제목:"가족여행"}',
  'value', {'상태': '완료', '작성자': '나', '제목': '가족여행'}),
 ('T19', '가족신문 주제별 편수 표의 열 이름과 요약 문구',
  '$g=[{topic:"여행"},{topic:"강의"},{topic:"여행"}] >> [table:groupby]{by:"topic"}; '
  '$s=$g.items >> [table:each]{return join("=",[$it.topic,text($it.count)])}; '
  'return {열:keys($g.items[0]),요약:$s}',
  'value', {'열': ['topic', 'count'], '요약': ['여행=2', '강의=1']}),
 ('T20', '줄머리 연산자로 이어 쓴 최저가 매물 추천',
  '$r=[{id:"a",p:300},{id:"b",p:100}]\n  >> [table:sort]{by:"p"}\n  >> [table:take]{n:1}\nreturn $r',
  'value', [{'id': 'b', 'p': 100}]),
 ('T21', '해외 구독료 19.9달러 3개월 합계',
  '$단가=19.9; return $단가*3', 'value', 59.7),
 ('T22', '매물 평균 면적 기록을 JSON 파일로 저장 (검수만)',
  '$r=[{면적:72.5}]; [self:write]{path:"outputs/IT67_area.json",content:json($r)}',
  'check', None),
 ('T23', '결석 학생 명단 안내 메일 (검수만)',
  '$결석=difference(["가","나"],["가"]); '
  '[others:channel_send]{channel_type:"email",to:"나",subject:"결석 안내",body:join(", ",$결석)}',
  'check', None),
 ('T24', '매일 아침 지출 요약 예약 (검수만)',
  '$do="#!ibl edition=2\\n[self:time]{}"; [self:schedule]{repeat:"daily",time:"08:00",do:$do}',
  'check', None),
]


def passed(result, mode, expected, check):
    if check:
        return (result.get('status') in ('valid', 'incomplete') and not result.get('issues')
                and result.get('executed') is False)
    if mode == 'runtime_error':
        return result.get('success') is False and result.get('diagnostic', {}).get('code') == expected
    return (result.get('success') is True and result.get('value') == expected
            and result.get('source_complete') is (mode != 'partial'))


def main():
    rows = []
    phase = sys.argv[1]
    for name, intent, code, mode, expected in CASES:
        for check in ([True] if mode == 'check' else [True, False]):
            payload = dict(code='#!ibl edition=2\n' + code, edition=2, project_id='컨텐츠',
                           origin='training', check=check)
            started = time.monotonic()
            proc = subprocess.run(
                ['curl', '-sS', '--max-time', '90', 'http://127.0.0.1:8765/ibl/execute',
                 '-H', 'Content-Type: application/json', '--data-binary', '@-'],
                input=json.dumps(payload), text=True, capture_output=True, check=True)
            response = json.loads(proc.stdout)
            result = response.get('result', response)
            ok = passed(result, mode, expected, check)
            rows.append(dict(name=name, intent=intent, request=payload, mode=mode,
                             expected=expected, response=response, passed=ok,
                             seconds=round(time.monotonic() - started, 4)))
            (HERE / f'{phase}.json').write_text(
                '[\n' + ',\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n]\n')
            brief = {k: result[k] for k in ('status', 'value', 'issues', 'diagnostic', 'error')
                     if k in result}
            print(name, 'check' if check else 'run', 'PASS' if ok else 'FAIL',
                  json.dumps(brief, ensure_ascii=False)[:400], flush=True)
    print('SUMMARY', sum(r['passed'] for r in rows), '/', len(rows))


if __name__ == '__main__':
    main()
