"""응답 후보·증거 원문 한 벌. 부분 읽기, 검수 범위, CAS 패치와 채택 지문을 소유한다."""
import hashlib
import json
import re
import threading
from pathlib import Path

EVENT_PAGE_LIMIT = 12000
RESPONSE_PAGE_LIMIT = 13000


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TurnStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.version = 0
        self.blocks = []
        self.coverage = set()
        self.sequence = 0

    def evidence(self, value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        key = digest(text)
        path = self.directory / (key + ".txt")
        if not path.exists():
            path.write_text(text, encoding="utf-8")
        return {"id": key, "chars": len(text), "excerpt": text[:1000]}

    def read_evidence(self, key, offset=0, limit=12000):
        if not re.fullmatch(r"[0-9a-f]{64}", key or ""):
            raise ValueError("잘못된 증거 ID")
        text = (self.directory / (key + ".txt")).read_text(encoding="utf-8")
        return {"id": key, "offset": offset, "chars": len(text), "text": text[offset:offset + limit]}

    def log(self, kind, **fields):
        with self.lock:
            self.sequence += 1
            record = {"seq": self.sequence, "kind": kind, **fields}
            with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return record

    def read_events(self, offset=0, limit=12000):
        requested = limit
        limit = min(limit, EVENT_PAGE_LIMIT)
        rows, size, cursor = [], 0, None
        with self.lock, (self.directory / "events.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if event["seq"] <= offset:
                    continue
                if rows and size + len(line) > limit:
                    cursor = rows[-1]["seq"]
                    break
                rows.append(event)
                size += len(line)
        return {"events": rows, "next_offset": cursor, "requested": requested,
                "limit": limit, "clamped": requested != limit}

    def put_response(self, text):
        with self.lock:
            if self.version:
                raise ValueError("후보가 이미 있습니다. 변경 블록만 patch 하세요")
            # 최대 2000자: 장문/코드 단락도 뒤쪽을 페이지 단위로 빠짐없이 읽을 수 있다.
            parts = re.findall(r"[\s\S]{1,2000}", text)
            self.blocks = [{"id": str(i), "text": p, "hash": digest(p)} for i, p in enumerate(parts)]
            self.version = 1
            self._save()
            return self.manifest()

    @property
    def text(self):
        with self.lock:
            return "".join(b["text"] for b in self.blocks)

    def manifest(self):
        with self.lock:
            return {"version": self.version, "hash": digest(self.text), "chars": len(self.text),
                    "blocks": [{"id": b["id"], "hash": b["hash"], "chars": len(b["text"])} for b in self.blocks]}

    def read_response(self, offset=0, limit=12000, *, mark=False):
        requested = limit
        limit = min(limit, RESPONSE_PAGE_LIMIT)
        with self.lock:
            page, count = [], 0
            for b in self.blocks[offset:]:
                encoded_size = len(json.dumps(b, ensure_ascii=False))
                if page and count + encoded_size > limit:
                    break
                page.append(dict(b))
                count += encoded_size
                if mark:
                    self.coverage.add((b["id"], b["hash"]))
            return {"version": self.version, "hash": digest(self.text), "blocks": page,
                    "requested": requested, "limit": limit, "clamped": requested != limit,
                    "next_offset": offset + len(page) if offset + len(page) < len(self.blocks) else None}

    def fully_read(self):
        return all((b["id"], b["hash"]) in self.coverage for b in self.blocks)

    def patch(self, version, patches):
        with self.lock:
            if version != self.version:
                raise ValueError("후보 버전이 바뀌었습니다. response를 다시 읽으세요")
            by_id = {b["id"]: b for b in self.blocks}
            if not patches or len({p["id"] for p in patches}) != len(patches):
                raise ValueError("패치는 비어 있거나 같은 블록을 중복 변경할 수 없습니다")
            for p in patches:
                if p["id"] not in by_id or p["hash"] != by_id[p["id"]]["hash"]:
                    raise ValueError("블록 지문 불일치 — 원문을 다시 읽으세요")
                if not isinstance(p["text"], str):
                    raise ValueError("교체 본문은 문자열이어야 합니다")
                if len(json.dumps(p["text"], ensure_ascii=False)) > 12000:
                    raise ValueError("한 변경 블록이 너무 큽니다. 기존 블록 여러 개에 나눠 patch 하세요")
            for p in patches:
                by_id[p["id"]].update(text=p["text"], hash=digest(p["text"]))
            self.version += 1
            self._save()
            return self.manifest()

    def _save(self):
        # JSON 문서에 본문은 복제하지 않는다. 전달은 같은 메모리의 문자열에서 한다.
        path = self.directory / f"response-v{self.version}.txt"
        path.write_text(self.text, encoding="utf-8")
        (self.directory / "response.json").write_text(json.dumps(self.manifest(), ensure_ascii=False), encoding="utf-8")
