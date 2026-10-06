"""응답 후보·증거 원문 한 벌. 부분 읽기, 검수 범위, CAS 패치와 채택 지문을 소유한다."""
import hashlib
import json
import os
import re
import tempfile
import threading
from collections import Counter
from pathlib import Path

from logging_utils import mask_secret_data

EVENT_PAGE_LIMIT = 12000
RESPONSE_PAGE_LIMIT = 13000
MASKED_PATHS_CAP = 256


class EvidenceNotFound(FileNotFoundError, ValueError):
    """이 저장소(대화·작업)에 없는 증거 — 기존 OSError 처리와 값 오류 처리가 모두 받는다."""


def masked_paths(original, masked):
    """마스킹 전후 값에서 바뀐 자리의 JSON 경로. 문자열은 JSON이면 구조로 비교한다."""
    if isinstance(original, str) and isinstance(masked, str):
        try:
            original, masked = json.loads(original), json.loads(masked)
        except ValueError:
            return [[]]
    out = []

    def walk(a, b, path):
        if len(out) > MASKED_PATHS_CAP:
            return
        if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
            for key in a:
                walk(a[key], b[key], path + [key])
        elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
            for index, (x, y) in enumerate(zip(a, b)):
                walk(x, y, path + [index])
        elif a != b and not (isinstance(a, float) and isinstance(b, float) and a != a and b != b):
            out.append(path)

    walk(original, masked, [])
    return [[]] if len(out) > MASKED_PATHS_CAP else out


def current_evidence_store():
    from supervision_bus import current
    controller = current()
    if controller:
        return controller.store
    from runtime_utils import get_base_path
    from thread_context import execution_key
    # 턴 밖 직접 호출도 다른 사용자의 증거와 섞이지 않는 독립 네임스페이스다.
    agent, task = execution_key()
    from member_runtime import is_member, private_path
    from common.spill import spill_dir
    root = private_path("tool_evidence") if is_member() else Path(spill_dir()) / "tool_evidence"   # 스필 루트 시임(2026-10-04)
    # 구분자를 포함한 신원도 충돌하지 않는다. 구분이 명백한 기존 작업의 참조는 유지한다.
    legacy = root / hashlib.sha256(f"{agent or None}:{task or None}".encode()).hexdigest()
    if ":" not in agent and ":" not in task and legacy.is_dir():
        return TurnStore(legacy)
    key = hashlib.sha256(json.dumps([agent, task], ensure_ascii=False).encode()).hexdigest()
    return TurnStore(root / key)


LINEAGE_DEPTH = 8      # 이어 읽을 수 있는 앞 턴 수
LINEAGE_KEEP = 64      # 행위자별 턴 원장에 남기는 줄 수
_LINEAGE_LOCK = threading.Lock()


def _lineage_ledger(directory, key):
    # 턴 저장소 뿌리 옆 — 회원은 자기 사적 경로 안이라 주인·다른 회원의 원장과 섞이지 않는다.
    return Path(directory).parent.parent / "supervision_lineage" / (key + ".jsonl")


def _ledger_turns(ledger):
    try:
        rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return []
    return [r["turn"] for r in rows if isinstance(r, dict) and isinstance(r.get("turn"), str)]


def response_parts(text):
    """Preserve bytes and paragraph boundaries; bound unusually long paragraphs too."""
    parts = []
    for paragraph in re.split(r"(?<=\n)(?=\n)", text):
        parts.extend(paragraph[i:i + 2000] for i in range(0, len(paragraph), 2000))
    return parts


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evidence_integrity(directory, key, text):
    """Read-only certification, shared by input references and trace inspection."""
    try:
        certificate = Path(directory) / (key + ".evidence.json")
        if certificate.is_symlink():
            return "unknown", [[]]
        encoded = certificate.read_text(encoding="utf-8")
        record = json.loads(encoded)
        paths = record["masked_paths"]
        if (digest(encoded) == key and record["version"] == 1 and record["text"] == text
                and isinstance(paths, list) and all(isinstance(p, list) for p in paths)):
            return "verified", paths
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return "unknown", [[]]


def patch_text(text, patch):
    modes = sum(k in patch for k in ("text", "old_string", "replacements"))
    if modes != 1:
        raise ValueError("text, old_string/new_string, replacements 중 하나만 지정하세요")
    if "text" in patch:
        if "new_string" in patch:
            raise ValueError("text와 범위 수정을 섞을 수 없습니다")
        return patch["text"]
    edits = patch.get("replacements") if "replacements" in patch else [patch]
    if not isinstance(edits, list) or not 1 <= len(edits) <= 50:
        raise ValueError("replacements는 1~50개 배열이어야 합니다")
    ranges = []
    for edit in edits:
        old, new = edit.get("old_string"), edit.get("new_string")
        if not isinstance(old, str) or not old or not isinstance(new, str) or text.count(old) != 1:
            raise ValueError("old_string은 원문에서 정확히 한 번 일치하고 new_string은 문자열이어야 합니다")
        start = text.index(old)
        ranges.append((start, start + len(old), new))
    ranges.sort()
    if any(b[0] < a[1] for a, b in zip(ranges, ranges[1:])):
        raise ValueError("수정 범위가 겹칩니다")
    for start, end, new in reversed(ranges):
        text = text[:start] + new + text[end:]
    return text


def tool_index_at(directory, limit=40):
    pending, rows = {}, []
    path = Path(directory) / "events.jsonl"
    if not path.exists():
        return rows
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        event = json.loads(line)
        if event["kind"] == "tool.started":
            pending[event.get("id")] = event
        elif event["kind"] in {"tool.finished", "tool.supervisor"}:
            if event["kind"] == "tool.supervisor" and event.get("operation") != "execute":
                continue
            start = pending.pop(event.get("id"), event)
            inp = start.get("input", {})
            result = event.get("result") or event.get("evidence", {})
            if not result.get("id"):
                continue
            rows.append({"seq": event["seq"], "name": start.get("name", event.get("operation", "")),
                         "input": {"id": inp.get("id"), "excerpt": inp.get("excerpt", "")[:240]},
                         "result": {"id": result["id"], "chars": result.get("chars")},
                         "is_error": bool(event.get("is_error")),
                         **({"check_rejected": True} if event.get("check_rejected") else {})})
    return rows[-limit:]


class TurnStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.version = 0
        self.blocks = []
        self.coverage = set()
        self.evidence_coverage = {}
        self.sequence = 0
        self.cost = Counter()
        self.operation_failures_seen = set()
        self.operations_seen = set()

    def evidence(self, value):
        # 도구가 직렬화한 JSON도 구조로 가린다. 문자열 정규식으로 JSON을
        # 편집하면 본문 속 \"x-api-key: ...\"의 escape가 깨져 부분 조회까지 실패한다.
        original = value
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        masked = mask_secret_data(value)
        if isinstance(original, str) and value != original:
            masked = original if masked == value else json.dumps(masked, ensure_ascii=False, default=str)
        text = masked if isinstance(masked, str) else json.dumps(masked, ensure_ascii=False, default=str)
        altered = masked_paths(original, masked) if masked != original else []
        # Identity includes the transformation facts: a literal '****' and a
        # redacted secret must never certify one another merely by sharing text.
        record = {"version": 1, "text": text, "masked_paths": altered}
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True)
        key = digest(encoded)
        # .txt is the existing display/trace surface. The atomic record is its
        # integrity certificate, published last. An absent/invalid certificate
        # permits display only; a crash can never turn 'unknown' into 'unaltered'.
        self._publish_evidence(key + ".txt", text)
        self._publish_evidence(key + ".evidence.json", encoded)
        return {"id": key, "chars": len(text), "excerpt": text[:1000],
                "integrity": "verified", **({"masked_paths": altered} if altered else {})}

    def _publish_evidence(self, name, text):
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                             prefix=".evidence-", delete=False) as stream:
                temp = Path(stream.name)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.directory / name)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)

    def _evidence_integrity(self, key, text):
        return evidence_integrity(self.directory, key, text)

    def masked_paths(self, key):
        """Verified transformations, or [[]] for unverified historical/corrupt data."""
        try:
            text = (self.directory / (key + ".txt")).read_text(encoding="utf-8")
        except OSError:
            return [[]]
        return self._evidence_integrity(key, text)[1]

    def read_evidence(self, key, offset=0, limit=12000, *, mark=False):
        if not re.fullmatch(r"[0-9a-f]{64}", key or ""):
            raise ValueError("잘못된 증거 ID")
        try:
            text = (self.directory / (key + ".txt")).read_text(encoding="utf-8")
        except FileNotFoundError:
            # 저장소는 대화(작업)별 네임스페이스다. 내부 경로·OS 문구 대신 참조의 범위를 알린다.
            raise EvidenceNotFound(
                "이 대화(작업)의 저장소에 없는 결과입니다. result_ref는 같은 대화의 그 턴과 바로 앞 턴들"
                f"(같은 에이전트·요청 주체, 최근 {LINEAGE_DEPTH}개)에서만 유효합니다 — 여기서는 원천을 다시 조회하세요.") from None
        end = offset + limit if limit is not None else None
        if mark:
            self.evidence_coverage.setdefault(key, []).append((offset, min(end or len(text), len(text))))
        page = {"id": key, "offset": offset, "chars": len(text), "text": text[offset:end]}
        page["integrity"], masked = self._evidence_integrity(key, text)
        if masked:
            page["masked_paths"] = masked
        return page

    def join_lineage(self, agent, project, principal_key):
        """이 턴을 같은 행위자(에이전트·프로젝트·요청 주체)의 턴 원장에 올린다.

        다음 턴이 앞 턴의 result_ref 를 이어 쓰는 범위다(긴문장 9회차 L9-1). 발급하는 쪽이 범위를
        적고, 읽는 쪽은 자기 턴과 같은 키의 턴만 본다 — 다른 저장소를 훑지 않는다."""
        key = digest(json.dumps([str(agent or ""), str(project or ""), str(principal_key or "")], ensure_ascii=False))
        ledger = _lineage_ledger(self.directory, key)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        name = self.directory.name
        with _LINEAGE_LOCK:
            turns = [t for t in _ledger_turns(ledger) if t != name][-(LINEAGE_KEEP - 1):] + [name]
            temp = ledger.with_suffix(".jsonl.tmp")
            temp.write_text("".join(json.dumps({"turn": t}) + "\n" for t in turns), encoding="utf-8")
            os.replace(temp, ledger)
        (self.directory / "lineage.json").write_text(json.dumps({"key": key}), encoding="utf-8")

    def earlier_turns(self):
        """같은 행위자의 바로 앞 턴 저장소들(가까운 것부터). 원장과 각 턴의 자기 표기가 모두 맞아야 한다."""
        try:
            key = json.loads((self.directory / "lineage.json").read_text(encoding="utf-8")).get("key")
        except (OSError, ValueError, AttributeError):
            return []
        if not re.fullmatch(r"[0-9a-f]{64}", key or ""):
            return []
        turns, name = _ledger_turns(_lineage_ledger(self.directory, key)), self.directory.name
        if name not in turns:
            return []
        out = []
        for turn in reversed(turns[:turns.index(name)][-LINEAGE_DEPTH:]):
            directory = self.directory.parent / turn
            if not re.fullmatch(r"[0-9a-f]{32}", turn) or directory.is_symlink() or not directory.is_dir():
                continue
            try:
                other = json.loads((directory / "lineage.json").read_text(encoding="utf-8")).get("key")
            except (OSError, ValueError, AttributeError):
                continue
            if other == key:
                out.append(directory)
        return out

    def read_evidence_across_turns(self, key, offset=0, limit=12000):
        """현재 턴에 없으면 같은 행위자의 앞 턴에서 읽는다. 앞 턴 값은 인증된 원문만 넘기고 출처 턴을 표시한다."""
        try:
            return self.read_evidence(key, offset, limit)
        except EvidenceNotFound:
            for directory in self.earlier_turns():
                path = directory / (key + ".txt")
                if path.is_symlink() or not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8")
                integrity, masked = evidence_integrity(directory, key, text)
                if integrity != "verified":
                    raise EvidenceNotFound("앞 턴에 저장된 결과이지만 원문 인증을 확인할 수 없어 이어 쓸 수 없습니다 — "
                                           "원천을 다시 조회하세요.") from None
                end = offset + limit if limit is not None else None
                page = {"id": key, "offset": offset, "chars": len(text), "text": text[offset:end],
                        "integrity": integrity, "from_turn": directory.name}
                if masked:
                    page["masked_paths"] = masked
                return page
            raise

    def evidence_fully_read(self, key):
        length = self.read_evidence(key, 0, 0)["chars"]
        end = 0
        for start, stop in sorted(self.evidence_coverage.get(key, [])):
            if start > end:
                return False
            end = max(end, stop)
        return end >= length

    def evidence_quote_read(self, key, quote):
        if not isinstance(quote, str) or not quote.strip():
            return False
        try:
            text = self.read_evidence(key, 0, None)["text"]
        except (ValueError, OSError, TypeError):
            return False
        escaped = json.dumps(quote, ensure_ascii=False)[1:-1]
        spans = []
        for start, end in sorted(self.evidence_coverage.get(key, [])):
            if spans and start <= spans[-1][1]:
                spans[-1][1] = max(spans[-1][1], end)
            else:
                spans.append([start, end])
        return any(quote in text[a:b] or escaped in text[a:b] for a, b in spans)

    def present_evidence(self, value, limit=12000):
        """Return the exact visible page and its citation ID; hidden tails stay unread."""
        ref = self.evidence(value)
        page = self.read_evidence(ref["id"], 0, limit, mark=True)
        return {"evidence": {k: ref[k] for k in ("id", "chars")}, "page": page}

    def tool_index(self, limit=40):
        """Small, chronological handles for repair. Does not claim the manager read them."""
        with self.lock:
            return tool_index_at(self.directory, limit)

    def call_history(self, turns=3, limit=30):
        """이 턴과 같은 행위자의 바로 앞 턴들이 실행한 호출 목록 — 프로그램 원문과 결과를 다시 읽는 손잡이.

        같은 일을 다른 자료로 반복할 때 앞서 통한 프로그램을 새로 쓰지 않게 한다(긴문장 10회차 L10-6).
        본문은 싣지 않는다 — input.id·result.id 를 read_result 로 읽는다."""
        out = [{"turn": self.directory.name, "current": True, "calls": self.tool_index(limit)}]
        for directory in self.earlier_turns()[:max(0, turns - 1)]:
            out.append({"turn": directory.name, "current": False, "calls": tool_index_at(directory, limit)})
        return out

    def log(self, kind, **fields):
        with self.lock:
            self.sequence += 1
            record = mask_secret_data({"seq": self.sequence, "kind": kind, **fields})
            if kind == "tool.finished":
                # Same job can be polled, projected, or replayed several times.
                # This is a work verdict, not a transport/tool exception.
                outcomes = [o for o in (fields.get('operation_outcomes') or [])
                            if isinstance(o, dict) and isinstance(o.get('id'), str)
                            and o.get('status') in ('passed', 'failed')]
                observed = {o['id'] for o in outcomes}
                failed = {o['id'] for o in outcomes if o['status'] == 'failed'}
                record['operation_failures'] = len(failed - self.operation_failures_seen)
                self.operation_failures_seen.update(failed)
                if outcomes:
                    self.cost['operations_observed'] += len(observed - self.operations_seen)
                    self.cost['operation_failures'] += record['operation_failures']
                    self.operations_seen.update(observed)
                self.cost["execution_calls"] += 1
                self.cost["execution_failures"] += int(bool(fields.get("is_error")))
                self.cost["internal_tool_failures"] += fields.get("internal_tool_failures", 0)
                self.cost["source_failures"] += fields.get("source_failures", 0)
                self.cost["check_rejections"] += int(bool(fields.get("check_rejected")))
                self.cost["execution_tool_s"] += fields.get("elapsed_s", 0)
            elif kind in {"tool.supervisor", "tool.error"} and fields.get("role") == "consciousness":
                self.cost["supervisor_tools"] += 1
                self.cost["supervisor_tool_failures"] += int(kind == "tool.error" or bool(fields.get("is_error")))
            elif kind == "model.native_tool":
                self.cost["supervisor_native_tools"] += int(fields.get("event_type") == "tool_start")
                self.cost["supervisor_native_failures"] += int(bool(fields.get("is_error")))
            elif kind == "model.started":
                self.cost["supervisor_calls"] += 1
            elif kind == "model.finished":
                self.cost["supervisor_model_s"] += fields.get("elapsed_s", 0)
                for key, value in fields.get("usage", {}).items():
                    self.cost["supervisor_" + key] += value
            elif kind == "evaluation.started":
                self.cost["evaluation_calls"] += 1
            elif kind == "evaluation.finished":
                self.cost["evaluation_model_s"] += fields.get("elapsed_s", 0)
            elif kind == "evaluation.stage_finished" and fields.get("stage") in {
                    "wait", "prepare", "visual", "checkpoint"}:
                self.cost["evaluation_" + fields["stage"] + "_s"] += fields.get("elapsed_s", 0)
            elif kind in {"decision.stale", "instruction.delivered"}:
                self.cost[kind] += 1
            with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return record

    def cost_summary(self, elapsed_s):
        with self.lock:
            summary = {**self.cost, "wall_s": round(elapsed_s, 3), "events_path": str(self.directory / "events.jsonl"),
                       "time_scope": "wall_s=사용자 턴 경과, model/tool_s=겹칠 수 있는 호출 지연 합",
                       "token_scope": "supervisor 입력은 캐시 포함. 후처리 비용은 postprocess.json에 별도 기록"}
            (self.directory / "cost.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
            return summary

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
            parts = response_parts(text)
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

    def read_response(self, offset=0, limit=12000, *, mark=False, block_id=None):
        requested = limit
        limit = min(limit, RESPONSE_PAGE_LIMIT)
        with self.lock:
            page, count = [], 0
            candidates = self.blocks[offset:]
            if block_id is not None:
                candidates = [b for b in self.blocks if b["id"] == str(block_id)]
                if not candidates:
                    raise ValueError("없는 응답 블록 ID")
            for b in candidates:
                encoded_size = len(json.dumps(b, ensure_ascii=False))
                if page and count + encoded_size > limit:
                    break
                page.append(dict(b))
                count += encoded_size
                if mark:
                    self.coverage.add((b["id"], b["hash"]))
            return {"version": self.version, "hash": digest(self.text), "blocks": page,
                    "requested": requested, "limit": limit, "clamped": requested != limit,
                    "next_offset": (offset + len(page) if block_id is None and offset + len(page) < len(self.blocks) else None)}

    def fully_read(self):
        return all((b["id"], b["hash"]) in self.coverage for b in self.blocks)

    def patch(self, version, patches):
        with self.lock:
            if version != self.version:
                raise ValueError("후보 버전이 바뀌었습니다. response를 다시 읽으세요")
            by_id = {b["id"]: dict(b) for b in self.blocks}
            if not patches or len({p["id"] for p in patches}) != len(patches):
                raise ValueError("패치는 비어 있거나 같은 블록을 중복 변경할 수 없습니다")
            for p in patches:
                if p["id"] not in by_id or p["hash"] != by_id[p["id"]]["hash"]:
                    raise ValueError("블록 지문 불일치 — 원문을 다시 읽으세요")
                block = by_id[p["id"]]
                replacement = patch_text(block["text"], p)
                if not isinstance(replacement, str):
                    raise ValueError("교체 본문은 문자열이어야 합니다")
                from quantity_checks import arithmetic_issues
                issues = arithmetic_issues(replacement)
                if issues:
                    raise ValueError("시간 합산 오류 — 패치 미적용: " + json.dumps(issues, ensure_ascii=False))
                if len(json.dumps(replacement, ensure_ascii=False)) > 12000:
                    raise ValueError("한 변경 블록이 너무 큽니다. 기존 블록 여러 개에 나눠 patch 하세요")
                block.update(text=replacement, hash=digest(replacement))
            updated = []
            changed = {p["id"] for p in patches}
            for block in self.blocks:
                b = by_id[block["id"]]
                if b["id"] not in changed:
                    updated.append(b)
                    continue
                for i, part in enumerate(response_parts(b["text"])):
                    key = b["id"] if i == 0 else f'{b["id"]}.{self.version + 1}.{i}'
                    updated.append({"id": key, "text": part, "hash": digest(part)})
            previous = self.blocks
            self.blocks = updated
            self.version += 1
            try:
                self._save()
            except OSError:
                self.blocks = previous
                self.version -= 1
                raise
            return self.manifest()

    def _save(self):
        # JSON 문서에 본문은 복제하지 않는다. 전달은 같은 메모리의 문자열에서 한다.
        path = self.directory / f"response-v{self.version}.txt"
        path.write_text(self.text, encoding="utf-8")
        manifest = self.directory / "response.json"
        temp = manifest.with_suffix(".json.tmp")
        temp.write_text(json.dumps(self.manifest(), ensure_ascii=False), encoding="utf-8")
        temp.replace(manifest)


def trace_directory(root, store_id):
    from trace_read import ReadFault, safe_child
    if not re.fullmatch(r"[0-9a-f]{32}", store_id or ""):
        raise ReadFault("forbidden", "access_denied")
    return safe_child(root, store_id)


def read_trace_events(root, store_id, cursor=None, limit=50):
    from trace_read import guarded, jsonl_page, safe_child
    return guarded("supervision", lambda: jsonl_page(
        "supervision", safe_child(trace_directory(root, store_id), "events.jsonl"), cursor, limit))


def read_trace_document(root, store_id, name, offset=0, limit=12000, expected=None):
    """Inspection only: no TurnStore construction, coverage, patch, adopt or delivery."""
    from trace_read import ReadFault, fingerprint, guarded, result, safe_child
    def read():
        directory = trace_directory(root, store_id)
        if not (re.fullmatch(r"[0-9a-f]{64}\.txt", name or "")
                or re.fullmatch(r"response-v[1-9][0-9]*\.txt", name or "")):
            raise ReadFault("forbidden", "access_denied")
        path = safe_child(directory, name)
        st = path.stat()
        if st.st_size > 4 * 1024 * 1024:
            raise ReadFault("partial", "document_size_budget")
        # Evidence is content addressed; responses additionally require approved bytes.
        text = path.read_text(encoding="utf-8")
        actual_hash = digest(text)
        if name.startswith("response-v"):
            review_path = safe_child(directory, "review_status.json")
            if review_path.stat().st_size > 128 * 1024:
                raise ReadFault("malformed", "invalid_review")
            review = json.loads(review_path.read_text(encoding="utf-8"))
            response = review.get("response") or {}
            manifest_path = safe_child(directory, "response.json")
            if manifest_path.stat().st_size > 128 * 1024:
                raise ReadFault("malformed", "invalid_response_manifest")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest != response:
                raise ReadFault("forbidden", "response_not_approved")
            if (review.get("status") != "ACHIEVED" or response.get("hash") != actual_hash
                    or name != f"response-v{response.get('version')}.txt"):
                raise ReadFault("forbidden", "response_not_approved")
        elif actual_hash != name[:-4] and evidence_integrity(directory, name[:-4], text)[0] != "verified":
            raise ReadFault("malformed", "evidence_hash_mismatch")
        water = fingerprint([st.st_dev, st.st_ino, st.st_mtime_ns, st.st_size, actual_hash])
        if expected and water != expected:
            raise ReadFault("partial", "cursor_expired")
        return result("supervision", [{"text": text[offset:offset + limit], "chars": len(text)}],
                      high_water=water)
    return guarded("supervision", read)


def inspect_trace_document(root, store_id, name):
    """Small availability metadata, without reading evidence bytes or filling coverage."""
    from trace_read import ReadFault, guarded, result, safe_child
    def read():
        directory = trace_directory(root, store_id)
        if not (re.fullmatch(r"[0-9a-f]{64}\.txt", name or "")
                or re.fullmatch(r"response-v[1-9][0-9]*\.txt", name or "")):
            raise ReadFault("forbidden", "access_denied")
        path = safe_child(directory, name)
        size = path.stat().st_size
        if size > 4 * 1024 * 1024:
            raise ReadFault("partial", "document_size_budget")
        if name.startswith("response-v"):
            review_path = safe_child(directory, "review_status.json")
            if review_path.stat().st_size > 128 * 1024:
                raise ReadFault("malformed", "invalid_review")
            review = json.loads(review_path.read_text(encoding="utf-8"))
            if review.get("status") != "ACHIEVED":
                raise ReadFault("forbidden", "response_not_approved")
        return result("supervision", status="ok", bytes=size)
    return guarded("supervision", read)


def read_trace_response_link(root, store_id):
    """응답 원문 위치만 읽는다. 사건 전 페이지를 모델이 읽어야 찾는 우회를 없앤다."""
    from trace_read import ReadFault, guarded, result, safe_child

    def read():
        path = safe_child(trace_directory(root, store_id), "response.json")
        if path.stat().st_size > 128 * 1024:
            raise ReadFault("malformed", "invalid_response_manifest")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        version = manifest.get("version") if isinstance(manifest, dict) else None
        if type(version) is not int or version < 1:
            raise ReadFault("malformed", "invalid_response_manifest")
        name = f"response-v{version}.txt"
        availability = inspect_trace_document(root, store_id, name)
        return result("supervision_response", [{"name": name, "status": availability["status"],
                                                "reason": availability.get("reason")}])

    return guarded("supervision_response", read)
