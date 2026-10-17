#!/usr/bin/env python3
"""Synthetic command latency through official subscription CLIs and DeepSeek API.

Run from the canonical repository. No action tools are executed. CLI credentials
stay in the existing official login stores or the child environment, never output.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import selectors  # noqa: E402
import signal  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from model_resolver import env_key_for_provider  # noqa: E402
from providers.claude_code import (find_claude_binary,
                                  load_oauth_token_from_central_config)  # noqa: E402
from providers.codex import find_codex_binary  # noqa: E402
from benchmark_voice_command_latency import SYSTEM, CASES, check_answer, invoke  # noqa: E402

MODELS = ["deepseek-flash", "haiku", "gpt-6-luna"]


def annotate_usage(row, previous):
    """Codex exec reports session totals on resume; don't double-count them."""
    usage = row.get("usage", {})
    if row["model"] == "gpt-6-luna":
        row["usage_scope"] = "session_cumulative"
        row["turn_usage"] = {
            key: value - previous.get(key, 0)
            for key, value in usage.items()
            if isinstance(value, (int, float))
        }
    else:
        row["usage_scope"] = "turn"
        row["turn_usage"] = usage
    return usage


def cli_env(model):
    env = os.environ.copy()
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY"):
        env.pop(name, None)
    if model == "haiku":
        token = load_oauth_token_from_central_config()
        if token:
            if not token.startswith("sk-ant-oat"):
                raise RuntimeError("Configured Claude credential is not subscription OAuth")
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env


def command(model, session_id):
    if model == "haiku":
        cmd = [find_claude_binary(), "--print", "--model", "haiku",
               "--output-format", "stream-json", "--verbose", "--include-partial-messages",
               "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
               "--setting-sources", "", "--disable-slash-commands",
               "--system-prompt", SYSTEM]
        if session_id:
            cmd += ["--resume", session_id]
    else:
        cmd = [find_codex_binary(), "exec", "--ignore-user-config", "--json",
               "--skip-git-repo-check", "--sandbox", "read-only",
               "--model", model, "-c", 'model_reasoning_effort="low"',
               "-c", 'approval_policy="never"', "-c", "project_doc_max_bytes=0"]
        if session_id:
            cmd += ["resume", session_id]
        cmd += ["-"]
    return cmd


def run_cli(model, case, cwd, session_id=None):
    row = {"model": model, "case": case["id"], "phase": "resume" if session_id else "fresh",
           "started_at_utc": datetime.now(timezone.utc).isoformat(), "text": "", "usage": {},
           "first_content_s": None, "answer_ready_s": None, "tool_events": 0,
           "first_content_granularity": "text_delta" if model == "haiku" else "message_complete",
           "effort": "default" if model == "haiku" else "low", "session_id": session_id}
    prompt = case["text"]
    if model != "haiku" and not session_id:
        prompt = SYSTEM + "\n도구를 호출하지 말고 명령 해석 결과만 답하라.\n\n" + prompt
    started = time.perf_counter()
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command(model, session_id), cwd=cwd, env=cli_env(model),
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                   start_new_session=True)
        process.stdin.write(prompt.encode())
        process.stdin.close()
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        buffer = b""
        alive = True
        while alive:
            if time.perf_counter() - started > 90:
                row["error"] = "wall_timeout"
                os.killpg(process.pid, signal.SIGTERM)
                break
            for key, _ in selector.select(timeout=1):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    alive = False
                    break
                buffer += chunk
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    try:
                        event = json.loads(raw)
                    except ValueError:
                        continue
                    elapsed = round(time.perf_counter() - started, 4)
                    kind = event.get("type")
                    if model == "haiku":
                        if event.get("session_id"):
                            row["session_id"] = event["session_id"]
                        if kind == "system" and event.get("subtype") == "init":
                            row["resolved_model"] = event.get("model")
                            row["api_key_source"] = event.get("apiKeySource")
                            row["init_s"] = elapsed
                        if kind == "stream_event":
                            delta = event.get("event", {}).get("delta", {})
                            if delta.get("type") == "text_delta" and delta.get("text"):
                                if row["first_content_s"] is None:
                                    row["first_content_s"] = elapsed
                        if kind == "assistant":
                            message = event.get("message", {})
                            row["resolved_model"] = message.get("model", row.get("resolved_model"))
                            content = message.get("content", [])
                            text = "".join(x.get("text", "") for x in content if x.get("type") == "text")
                            row["tool_events"] += sum(x.get("type") == "tool_use" for x in content)
                            if text:
                                row["text"] = text
                                row["answer_ready_s"] = elapsed
                                if row["first_content_s"] is None:
                                    row["first_content_s"] = elapsed
                        if kind == "result":
                            row["text"] = event.get("result", row["text"])
                            row["usage"] = event.get("usage", {})
                            row["reported_api_ms"] = event.get("duration_api_ms")
                            row["cli_cost_estimate_not_subscription_bill"] = event.get("total_cost_usd")
                            row["result_subtype"] = event.get("subtype")
                            if event.get("is_error"):
                                row["error"] = "cli_result_error"
                    else:
                        if kind == "thread.started":
                            row["session_id"] = event.get("thread_id")
                            row["init_s"] = elapsed
                        item = event.get("item", {})
                        if kind == "item.completed" and item.get("type") == "agent_message":
                            row["text"] = item.get("text", "")
                            row["answer_ready_s"] = elapsed
                            if row["first_content_s"] is None:
                                row["first_content_s"] = elapsed
                        if kind == "item.completed" and item.get("type") in {
                                "command_execution", "mcp_tool_call", "file_change", "web_search"}:
                            row["tool_events"] += 1
                        if kind == "turn.completed":
                            row["usage"] = event.get("usage", {})
                        if kind in {"error", "turn.failed"}:
                            row["error"] = kind
        selector.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        row["exit_code"] = process.returncode
        row["total_s"] = round(time.perf_counter() - started, 4)
        errors.seek(0)
        error_text = errors.read().decode(errors="replace")
        if process.returncode:
            # Only safe diagnostics: all configured secrets are redacted before storage.
            for value in cli_env(model).values():
                if len(value) > 20 and value in error_text:
                    error_text = error_text.replace(value, "[REDACTED]")
            row["stderr_tail"] = error_text[-1200:]
    row["correct"] = check_answer(row["text"], case)
    row["success"] = (process.returncode == 0 and not row.get("error") and
                      row["answer_ready_s"] is not None and row["tool_events"] == 0)
    return row


def summarize(rows):
    result = []
    for model in MODELS:
        for phase in ("fresh", "resume"):
            group = [r for r in rows if r["model"] == model and r["phase"] == phase]
            if not group:
                continue
            good = [r for r in group if r["success"]]
            item = {"model": model, "phase": phase, "attempts": len(group),
                    "successes": len(good), "correct": sum(r["correct"] for r in group)}
            for metric in ("answer_ready_s", "total_s"):
                values = [r[metric] for r in good]
                if values:
                    item[metric] = {"median": round(statistics.median(values), 3),
                                    "min": min(values), "max": max(values)}
            result.append(item)
    return result


def save_results(path, doc):
    """Keep each measured sample on one line, with readable metadata/summary."""
    header = json.dumps({k: v for k, v in doc.items() if k != "rows"},
                        ensure_ascii=False, indent=2)
    rows = ",\n".join("    " + json.dumps(r, ensure_ascii=False) for r in doc["rows"])
    path.write_text(header[:-1].rstrip() + ',\n  "rows": [\n' + rows + '\n  ]\n}\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    doc = {"method": "Official CLIs via existing subscription auth, API keys removed from CLI "
           "environment. Synthetic commands only; no tools executed. Each pair is a fresh conversation "
           "then the same command repeated via resume. CLI restarts per turn, as in existing IndieBiz "
           "CLI provider; this is not a persistent-process benchmark. CLI native envelopes differ "
           "from the direct API. DeepSeek uses default reasoning; Luna low; Haiku default. "
           "Codex first content is a completed-message event, not first token. Answer-ready is the "
           "comparable metric. STT, TTS and full IBL harness are excluded.",
           "system_prompt": SYSTEM, "cases": CASES, "rows": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="indiebiz-voice-bench-") as cwd:
        for repeat in range(1 if args.probe else args.repeats):
            for index, case in enumerate(CASES[:1] if args.probe else CASES):
                offset = (repeat + index) % len(MODELS)
                for model in MODELS[offset:] + MODELS[:offset]:
                    session_id = None
                    history = []
                    previous_usage = {}
                    with requests.Session() as http:
                        for phase in ("fresh", "resume"):
                            if model == "deepseek-flash":
                                row = invoke(http, ("deepseek", model, "default"), case,
                                             env_key_for_provider("deepseek"), history)
                                row.update(phase=phase, answer_ready_s=row["total_s"], tool_events=0)
                                history += [{"role": "user", "content": case["text"]},
                                            {"role": "assistant", "content": row["text"]}]
                            else:
                                row = run_cli(model, case, cwd, session_id)
                                session_id = row["session_id"]
                            row["repeat"] = repeat + 1
                            previous_usage = annotate_usage(row, previous_usage)
                            doc["rows"].append(row)
                            doc["summary"] = summarize(doc["rows"])
                            save_results(args.output, doc)
                            print(json.dumps({k: row.get(k) for k in ("model", "resolved_model",
                                  "case", "phase", "repeat", "answer_ready_s", "total_s", "correct",
                                  "error", "stderr_tail")}, ensure_ascii=False), flush=True)
                            if not row["success"]:
                                raise SystemExit("Probe failed; inspect saved sanitized result")
    print(json.dumps(doc["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
