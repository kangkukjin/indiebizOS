#!/usr/bin/env python3
"""IBL v2 check/run/replay/register/inventory. Defaults to check, never execution."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401
import argparse
import json
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault, projection
from ibl_v2_parser import edition_of
from ibl_v2_runtime import Runtime
from ibl_v2_store import definitions, action


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "run", "replay", "register", "inventory", "capabilities"])
    parser.add_argument("source", nargs="?")
    parser.add_argument("--inputs", help="JSON 입력 파일(이름→값)")
    parser.add_argument("--record", help="replay가 읽을 이전 run 결과 JSON")
    parser.add_argument("--output", help="결과 JSON 파일(생략=stdout)")
    parser.add_argument("--project", default=".")
    args = parser.parse_args()
    try:
        registry = load_registry(args.project)
        if args.command == "capabilities":
            result = {"editions": [1, 2], "value_protocols": ["ibl-value/1"],
                      "v2_actions": {k: v.contract for k, v in registry.items()},
                      "resume": False, "remote_script_v2": False}
        elif args.command == "inventory":
            from workflow_store import list_workflows
            result = {"workflows": [{"id": w["id"], "name": w["name"], "edition": w.get("edition", 1)}
                                    for w in list_workflows()],
                      "changed": False, "note": "판본 1 자산은 새 id로 검증 후 등록합니다. 자동 의미 변환은 하지 않습니다."}
        else:
            if not args.source:
                parser.error("source 파일이 필요합니다.")
            source = Path(args.source).read_text(encoding="utf-8")
            edition_of(source, 2)
            inputs = json.loads(Path(args.inputs).read_text()) if args.inputs else {}
            if args.command == "register":
                result = action("save", {"edition": 2, "code": source}, args.project)
            else:
                plan = compile_program(source, registry, inputs, definitions())
                if args.command == "check":
                    result = plan.report()
                else:
                    if args.command == "replay" and not args.record:
                        parser.error("replay에는 --record가 필요합니다.")
                    recorded = json.loads(Path(args.record).read_text()).get("recordings", []) if args.record else []
                    result = Runtime(plan, inputs, recordings=recorded, replay=args.command == "replay").run()
    except (Fault, ValueError, OSError) as exc:
        result = {"success": False, "error": str(exc)}
    output = json.dumps(projection(result), ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 1 if result.get("success") is False or result.get("ok") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
