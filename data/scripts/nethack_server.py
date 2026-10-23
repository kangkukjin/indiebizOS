"""Local experiment server. Requires an existing BALROG checkout and its Python env."""
import argparse
import json
import os
from pathlib import Path
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from nethack_runtime import Game


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--port", type=int, default=8797)
    args = parser.parse_args(argv)
    if Path(args.run).name != args.run or args.run in {".", ".."}:
        parser.error("run은 새 실행 폴더 이름이어야 합니다")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                op = request.get("op", "observe")
                if op == "instructions":
                    body = {"instructions": game.env.get_instruction_prompt(),
                            "batch_contract": "기본: 피격·질문·막힘·상태변화에서 중단. remaining은 자동 실행하지 않음. "
                            "관찰은 observe. look은 게임 행동이며 실명 시 턴을 소비. "
                            "입력 연속 처리만 stop_on에서 prompt를 제외. 위험 재시도는 allow_risk:true 명시."}
                elif op == "observe":
                    body = game.view()
                elif op == "status":
                    body = game.status()
                elif op == "step":
                    body = game.step(request.get("actions"), str(request.get("tag", "")),
                                     expected_revision=request.get("expected_revision"),
                                     stop_on=request.get("stop_on"), allow_risk=request.get("allow_risk") is True)
                else:
                    raise ValueError(f"알 수 없는 op: {op}")
                code = 200
            except (ValueError, TypeError, KeyError) as exc:
                body, code = {"success": False, "error": str(exc)}, 400
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    # Bind before initializing a game or writing its ledger. A port conflict
    # must not create a phantom run; never remove another process's files.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    game, env = None, None
    try:
        sys.path.insert(0, str(args.workspace / "src/BALROG"))
        from omegaconf import OmegaConf
        from balrog.environments import make_env
        config = OmegaConf.load(args.workspace / "src/BALROG/balrog/config/config.yaml")
        env = make_env("nle", "NetHackChallenge-v0", config)
        game = Game(env, args.seed, args.workspace / "runs" / args.run)
        (game.run_dir / "server.json").write_text(json.dumps(
            {"seed": args.seed, "port": server.server_port, "pid": os.getpid(),
             "run_id": game.run_id, "started_at": game.started_at,
             "env": "BALROG nle NetHackChallenge-v0"}, indent=2))
        server.serve_forever()
    finally:
        server.server_close()
        if game:
            game.log.close()
        if env:
            env.close()


if __name__ == "__main__":
    main()
