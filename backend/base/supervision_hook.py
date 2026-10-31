"""Claude Code 네이티브 도구 실행 직전의 감독 지시 전달. stdout는 훅 프로토콜 자리다."""
import json
import os
import sys
import urllib.request

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import boot_paths  # noqa: E402,F401


def check():
    if os.environ.get("INDIEBIZOS_SUPERVISED") != "1":
        return None
    payload = {"agent_id": os.environ.get("INDIEBIZOS_AGENT_ID", ""),
               "task_id": os.environ.get("INDIEBIZOS_TASK_ID", ""), "payload": {}}
    req = urllib.request.Request("http://127.0.0.1:8765/ibl/supervision/boundary",
                                 data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=220) as response:
        result = json.load(response)
    if not result.get("active"):
        return "감독 턴이 종료됐습니다. 더 실행하지 말고 현재 결과로 마무리하세요."
    if result.get("instruction"):
        return "[의식 개입 — 이 도구는 아직 실행되지 않았습니다] " + json.dumps(result["instruction"], ensure_ascii=False)
    return None


def main():
    try:
        instruction = check()
    except Exception as exc:
        instruction = f"감독 통로를 확인하지 못해 이번 도구는 실행하지 않았습니다: {type(exc).__name__}"
    if instruction:
        sys.stderr.write(instruction + "\n")
        return 2
    try:
        payload = json.load(sys.stdin)
        context = situation_context()
        output = context_output(payload, context)
    except (ValueError, TypeError) as exc:
        sys.stderr.write(f"도구 입력을 확인하지 못해 실행하지 않았습니다: {type(exc).__name__}\n")
        return 2
    if output:
        print(json.dumps(output, ensure_ascii=False))
    return 0


def situation_context():
    if os.environ.get('INDIEBIZOS_SITUATION') != '1':
        return ''
    try:
        payload = {'agent_id': os.environ.get('INDIEBIZOS_AGENT_ID', ''),
                   'task_id': os.environ.get('INDIEBIZOS_TASK_ID', '')}
        req = urllib.request.Request('http://127.0.0.1:8765/ibl/situation',
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response).get('context', '')
    except Exception:
        return ''  # Missing context is not permission to cancel or repeat an already completed tool.


def context_output(payload, context=''):
    output = shell_input(payload)
    if context:
        output = output or {'hookSpecificOutput': {'hookEventName': 'PreToolUse'}}
        output['hookSpecificOutput']['additionalContext'] = context
    return output


def shell_input(payload):
    """Bash의 마지막 파이프에서 앞 명령 실패를 보존한다. 실행/재시도는 CLI 소유다.

    PreToolUse updatedInput은 전체 입력을 교체하므로 나머지 필드를 보존한다.
    permissionDecision을 주지 않아 변경된 명령도 기존 권한 검사를 거친다.
    set -e는 쓰지 않는다. 명시적인 || 복구와 셸 제어 흐름은 원문대로다.
    """
    if not isinstance(payload, dict):
        raise ValueError("invalid hook payload")
    if payload.get("tool_name") != "Bash":
        return None
    params = payload.get("tool_input")
    if not isinstance(params, dict) or not isinstance(params.get("command"), str):
        raise ValueError("invalid Bash input")
    prefix = "set -o pipefail\n"
    command = params["command"]
    if not command.strip() or command.startswith(prefix):
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
            "updatedInput": {**params, "command": prefix + command}}}


if __name__ == "__main__":
    raise SystemExit(main())
