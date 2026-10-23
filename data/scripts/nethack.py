"""NetHack 도구 서버(projects/study/nethack/server.py)에 요청을 보내는 창구.

args: {op: "instructions"|"observe"|"step"|"status", actions: [행동 문자열…](최대 50),
       expected_revision: 관측의 status.revision, tag: 메모(선택), port: 8797}
step은 피격·질문·막힘·상태변화에서 멈추고 remaining과 stop_reason을 반환한다.
질문 입력 연속 처리만 stop_on:["damage","blocked","status_change"]로 지정한다.
위험한 명시적 재시도는 allow_risk:true. observe는 무행동 조회, look은 게임 행동이다.
observation·inventory·state·status를 다음 판단에 재사용한다. 클라이언트와 서버 본문은
같은 폴더의 nethack_client.py·nethack_server.py이며 실험 기록은 projects/에 둔다.
"""
import json
import sys
import urllib.error
import urllib.request

args = json.loads(sys.stdin.read() or "{}")
port = int(args.pop("port", 8797))
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/",
    data=json.dumps(args).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print(r.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print(json.dumps({"success": False, "error": e.read().decode("utf-8", "replace")}, ensure_ascii=False))
except urllib.error.URLError as e:
    print(json.dumps({"success": False, "error": f"NetHack 서버에 연결하지 못했다: {e.reason}"}, ensure_ascii=False))
