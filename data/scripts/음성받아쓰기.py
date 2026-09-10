"""[sense:listen]{path, op:"transcribe"}의 호환용 등록 스크립트.

stdin JSON: path, out, segment_seconds, model, prompt/instruction(전사 지침).
새 작업은 sense:listen을 직접 사용한다. 모델·캐시·진척·실패 계약은 공통 구현 한 벌이다.
"""
import contextlib
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "backend"))
import boot_paths  # noqa: E402,F401
sys.path.insert(0, str(_ROOT / "data/packages/installed/tools/android"))


def main():
    from dotenv import load_dotenv
    from tool_context import ToolContext
    from android_audio import listen_file
    load_dotenv(_ROOT / ".env")
    args = json.loads(sys.stdin.read().strip() or "{}")
    params = {"path": args.get("path"), "out": args.get("out"),
              "segment_seconds": args.get("segment_seconds"), "model": args.get("model"),
              "instruction": args.get("instruction") or args.get("prompt")}
    params = {key: value for key, value in params.items() if value is not None}
    context = ToolContext(project_path=str(_ROOT), tool_name="phone_listen")
    with contextlib.redirect_stdout(sys.stderr):
        result = listen_file(params, context, "transcribe")
    result["duration_sec"] = result.get("metadata", {}).get("duration")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
