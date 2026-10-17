#!/usr/bin/env python3
"""Paid, read-only synthetic voice-command API benchmark; no tools are executed."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import argparse  # noqa: E402
import json  # noqa: E402
import statistics  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from model_resolver import env_key_for_provider  # noqa: E402

SYSTEM = """너는 스마트스피커의 한국어 명령 해석기다. 실제 실행은 하지 않는다.
오직 JSON 객체 하나를 출력한다: {"action":문자열,"args":객체,"say":짧은 한국어 문장}.
지원 action은 timer_start(args.seconds 정수), calendar_update(args.id, args.datetime),
clarify(args는 빈 객체)다. 필요한 대상이나 값이 불명확하면 clarify로 질문한다.
실행 전이므로 완료했다고 말하지 않는다. say는 40자 이내로 쓴다.
현재 날짜는 2026-10-17, 시간대 Asia/Seoul이다. JSON 밖 설명은 쓰지 않는다."""
CASES = [
    {"id": "timer", "text": "15분 타이머 맞춰줘.",
     "action": "timer_start", "args": {"seconds": 900}},
    {"id": "correction", "text": "방금 선택한 일정은 id=meeting-42, 제목=치과, "
     "시작=2026-10-18T14:00:00+09:00야. 그거 내일 오후 세 시로 바꿔줘.",
     "action": "calendar_update",
     "args": {"id": "meeting-42", "datetime": "2026-10-18T15:00:00+09:00"}},
    {"id": "ambiguous", "text": "그거 취소해줘. (이 대화에는 이전 요청이나 선택된 대상이 없다.)",
     "action": "clarify", "args": {}},
]
PROFILES = [
    ("deepseek", "deepseek-flash", "default"),
    ("google", "gemini-3.8-flash", "default"),
    ("deepseek", "deepseek-flash", "low"),
    ("google", "gemini-3.8-flash", "low"),
]


def check_answer(text, case):
    try:
        value = json.loads(text)
        return (value["action"] == case["action"] and value["args"] == case["args"]
                and isinstance(value["say"], str) and 0 < len(value["say"]) <= 40)
    except (ValueError, KeyError, TypeError):
        return False


def invoke(session, profile, case, key):
    provider, model, effort = profile
    result = {"provider": provider, "model": model, "effort": effort, "case": case["id"],
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "first_content_s": None, "text": "", "usage": {}, "finish": None}
    if provider == "deepseek":
        url = "https://api.deepseek.com/chat/completions"
        headers = {"Authorization": "Bearer " + key}
        body = {"model": model, "messages": [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": case["text"]}], "stream": True,
                "stream_options": {"include_usage": True}, "max_tokens": 4096}
        if effort == "low":
            body.update(thinking={"type": "enabled"}, reasoning_effort="low")
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"
        headers = {"x-goog-api-key": key}
        body = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
                "contents": [{"role": "user", "parts": [{"text": case["text"]}]}],
                "generationConfig": {"maxOutputTokens": 4096}}
        if effort == "low":
            body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
    started = time.perf_counter()
    try:
        with session.post(url, headers=headers, json=body, stream=True,
                          params={"alt": "sse"} if provider == "google" else None,
                          timeout=(15, 60), allow_redirects=False) as response:
            result["http_status"] = response.status_code
            if response.status_code != 200:
                # No request headers, URL query credentials, or raw error bodies are saved.
                result["error"] = "http_" + str(response.status_code)
            else:
                response.encoding = "utf-8"
                for line in response.iter_lines(chunk_size=1, decode_unicode=True):
                    if time.perf_counter() - started > 90:
                        result["error"] = "wall_timeout"
                        break
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    event = json.loads(raw)
                    chunk = ""
                    if provider == "deepseek":
                        for choice in event.get("choices", []):
                            chunk += choice.get("delta", {}).get("content") or ""
                            if choice.get("finish_reason"):
                                result["finish"] = choice["finish_reason"]
                        if event.get("usage"):
                            result["usage"] = event["usage"]
                    else:
                        for candidate in event.get("candidates", []):
                            for part in candidate.get("content", {}).get("parts", []):
                                if not part.get("thought"):
                                    chunk += part.get("text", "")
                            if candidate.get("finishReason"):
                                result["finish"] = candidate["finishReason"]
                        if event.get("usageMetadata"):
                            result["usage"] = event["usageMetadata"]
                    if chunk:
                        if result["first_content_s"] is None:
                            result["first_content_s"] = round(time.perf_counter() - started, 4)
                        result["text"] += chunk
    except Exception as exc:
        result["error"] = type(exc).__name__
    result["total_s"] = round(time.perf_counter() - started, 4)
    result["correct"] = check_answer(result["text"], case)
    result["success"] = (not result.get("error") and result["finish"] in {"stop", "STOP"}
                         and bool(result["text"]))
    return result


def summarize(rows):
    summaries = []
    for provider, model, effort in PROFILES:
        group = [r for r in rows if (r["provider"], r["model"], r["effort"]) ==
                 (provider, model, effort)]
        good = [r for r in group if r["success"]]
        item = {"model": model, "effort": effort, "attempts": len(group),
                "successes": len(good), "correct": sum(r["correct"] for r in group)}
        for metric in ("first_content_s", "total_s"):
            vals = [r[metric] for r in good if r[metric] is not None]
            if vals:
                item[metric] = {"median": round(statistics.median(vals), 3),
                                "min": min(vals), "max": max(vals)}
        summaries.append(item)
    return summaries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    keys = {p: env_key_for_provider(p) for p in ("deepseek", "google")}
    if not all(keys.values()):
        raise SystemExit("Required provider key unavailable")
    sessions = {p: requests.Session() for p in keys}
    doc = {"method": "Sequential alternating direct streaming API calls, reused HTTP sessions; "
           "no retries; no tools/STT/TTS/full harness; first content excludes reasoning; "
           "no separate warmup; provider cache state is uncontrolled and usage is recorded.",
           "system_prompt": SYSTEM, "cases": CASES, "rows": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for repeat in range(1 if args.probe else args.repeats):
        for index, case in enumerate(CASES[:1] if args.probe else CASES):
            offset = (repeat + index) % len(PROFILES)
            for profile in PROFILES[offset:] + PROFILES[:offset]:
                row = invoke(sessions[profile[0]], profile, case, keys[profile[0]])
                row["repeat"] = repeat + 1
                doc["rows"].append(row)
                doc["summary"] = summarize(doc["rows"])
                args.output.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
                print(json.dumps({k: row.get(k) for k in ("model", "effort", "case",
                      "repeat", "first_content_s", "total_s", "correct", "error")}), flush=True)
                if row.get("http_status") in {400, 401, 403, 404, 429}:
                    raise SystemExit("API rejected probe; inspect status before further paid calls")
    for session in sessions.values():
        session.close()
    print(json.dumps(doc["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
