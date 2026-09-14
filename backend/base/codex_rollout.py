"""Codex 롤아웃의 응답 ID 원장. 도구 item 수로 모델 왕복을 추정하지 않는다."""
import json
import re
from datetime import datetime


class CodexResponseLedger:
    """한 CLI 호출 이후의 응답만 증분 조회한다. 부분 JSONL은 다음 조회에서 읽는다."""

    def __init__(self, home, thread_id, started_at):
        self.home = home
        self.thread_id = thread_id
        self.started_at = started_at
        self.path = None
        self.offset = 0
        self.turn_id = None
        self.seen = set()
        self.turn_usage = None
        self.final_text = None

    def poll(self):
        if not re.fullmatch(r"[a-zA-Z0-9-]+", self.thread_id or ""):
            return []
        if self.path is None:
            try:
                hits = list(self.home.glob(f"sessions/**/rollout-*-{self.thread_id}.jsonl"))
                if not hits:
                    return []
                self.path = max(hits, key=lambda p: p.stat().st_mtime)
            except OSError:
                return []
        records = []
        try:
            with self.path.open("rb") as stream:
                stream.seek(self.offset)
                while True:
                    line = stream.readline()
                    if not line.endswith(b"\n"):
                        break
                    self.offset = stream.tell()
                    if not any(marker in line for marker in
                               (b'"token_usage_record"', b'"task_started"', b'"response_item"')):
                        continue
                    try:
                        row = json.loads(line)
                        timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp()
                        payload = row["payload"]
                    except (ValueError, KeyError, TypeError):
                        continue
                    if timestamp < self.started_at:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if row.get("type") == "event_msg" and payload.get("type") == "task_started":
                        self.turn_id = payload.get("turn_id")
                        self.final_text = None
                    elif (self.turn_id and row.get("type") == "response_item"
                          and payload.get("type") == "message"
                          and payload.get("role") == "assistant"
                          and payload.get("phase") == "final_answer"):
                        self.final_text = "".join(
                            part.get("text", "") for part in payload.get("content", [])
                            if isinstance(part, dict) and part.get("type") == "output_text")
                    elif row.get("type") == "token_usage_record":
                        response_id = payload.get("response_id")
                        if (not self.turn_id or payload.get("turn_id") != self.turn_id
                                or not response_id or response_id in self.seen):
                            continue
                        self.seen.add(response_id)
                        self.turn_usage = payload.get("turn_token_usage")
                        records.append({**payload, "timestamp": row["timestamp"]})
        except OSError:
            return records
        return records
