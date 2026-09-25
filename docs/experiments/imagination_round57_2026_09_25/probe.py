"""Synthetic round 57 tasks. HTTP checks never send messages or schedule work."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CASES = [
    ("T01", "영상별 팁을 점수순으로 추리고 영상 ID를 보존한다.", '''
$videos=[{id:"v1",tips:[{score:2},{score:8}]},{id:"v2",tips:[]}]
$videos >> [table:each]{mode:"flat_map",parallel:2}{
  $id=$it.id
  $it.tips >> [table:filter]{where:($r)=>$r.score>5} >> [table:select]{columns:($r)=>{video:$id,score:$r.score}}
}''', False),
    ("T02", "빈 지출 목록의 합계가 0인 근거에 실제 조회가 남아야 한다.", '''
$rows=[table:take]{items:[],n:1}
$total=reduce($rows,0,($a,$r)=>$a+$r.amount)
return {total:$total,proof:evidence($total)}''', False),
    ("T03", "자료를 차례로 확인하다 첫 유효 항목을 찾으면 반환하고 앞선 조회 근거도 남긴다.", '''
[def:first](){
  [repeat:2]{
    [if:$i==0]{[table:take]{items:[{id:"inspected"}],n:1}}
    [else]{return "found"}
  }
}
$result=[fn:first]{}
return {result:$result,proof:evidence($result)}''', False),
    ("T04", "매물 조회로 선택한 분기에서 계산에 실패하면 대체 결과에 조회 근거를 남긴다.", '''
$rows=[table:take]{items:[{price:0}],n:1}
$result=[try]{
  [if:len($rows)>0]{1/0}
}[catch]{"가격 확인 필요"}
return {result:$result,proof:evidence($result)}''', False),
    ("T05", "여러 원천 중 실패한 원천의 조회 호출까지 복구 결과에서 추적한다.", '''
$result=[try]{[table:each]{items:[1,0],parallel:2}{
  $source=[table:take]{items:[$it],n:1}
  return 10/$source[0]
}}[catch]{{rows:$error.partial,status:"부분 확인"}}
return {result:$result,proof:evidence($result)}''', False),
    ("T06", "보고서 작업이 실패해도 정리를 수행하고 실패 원인과 정리 근거를 함께 반환한다.", '''
[def:report](){
  [try]{1/0}[finally]{[table:take]{items:["cleanup"],n:1}}
}
$result=[try]{[fn:report]{}}[catch]{"실패 보고"}
return {result:$result,proof:evidence($result)}''', False),
    ("T07", "단가 계산 오류를 수집해 다른 품목은 끝까지 처리한다.", '''
$rows=[{id:"a",n:2},{id:"b",n:0},{id:"c",n:4}]
$rows >> [table:each]{parallel:3,on_error:"collect"}{return {id:$it.id,unit:100/$it.n}}''', False),
    ("T08", "강의 자료별 점수를 합산한 뒤 기준 충족 여부를 반환한다.", '''
[def:score]($rows,$minimum){
  $total=reduce($rows,0,($a,$r)=>$a+$r.score)
  return {total:$total,ready:$total>=$minimum}
}
[fn:score]{rows:[{score:3},{score:7}],minimum:10}''', False),
    ("T09", "자료 축적 작업을 매일 오전에 예약하는 문장을 검사한다.", '''
[self:schedule]{repeat:"daily",time:"09:00",do:"#!ibl edition=2\\n[self:time]{}"}''', True),
    ("T10", "신규 자료가 있을 때만 요약 메일을 보내는 문장을 검사한다.", '''
$new=2
[if:$new>0]{[others:channel_send]{channel_type:"email",to:"나",subject:"훈련 검수",body:f"새 자료 ${new}건"}}''', True),
]


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "before"
    evidence = []
    for name, intent, code, check_only in CASES:
        for check in ([True] if check_only else [True, False]):
            payload = dict(code="#!ibl edition=2\n" + code, edition=2,
                           project_id="컨텐츠", origin="training", check=check)
            run = subprocess.run(
                ["curl", "-sS", "--max-time", "60", "http://127.0.0.1:8765/ibl/execute",
                 "-H", "Content-Type: application/json", "--data-binary", "@-"],
                input=json.dumps(payload), text=True, capture_output=True, check=True)
            response = json.loads(run.stdout)
            evidence.append(dict(name=name, intent=intent, request=payload, response=response))
            result = response.get("result", response)
            if isinstance(result, dict):
                value = result.get("value", {})
                proof = value.get("proof", {}) if isinstance(value, dict) else {}
                invokes = [e.get("action") for e in proof.get("events", []) if e["kind"] == "invoke"]
                print(name, "check" if check else "run", result.get("status", result.get("success")),
                      "invokes=", invokes, "error=", result.get("error"), flush=True)
            else:
                print(name, str(response)[:500], flush=True)
    (HERE / f"{phase}.json").write_text(
        "[\n" + ",\n".join(json.dumps(row, ensure_ascii=False) for row in evidence) + "\n]\n")


if __name__ == "__main__":
    main()
