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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
