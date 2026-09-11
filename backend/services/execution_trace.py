"""On-demand composition of existing ledgers. No event DB, writes, repair, or publication."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from datetime import datetime, timezone

from common.value_semantics import numeric_value
from conversation_db import read_task_trace, read_task_result
from episode_logger import read_trajectory_page, read_episode_text, read_trace_store_links
from execution_trace_scope import ScopeResolver, TraceAccess, observe_runtime
from pursuit_ledger import read_trace_events as read_pursuit_events, read_trace_text as read_pursuit_text
from supervision_store import read_trace_events as read_supervision_events, read_trace_document, inspect_trace_document
from trace_read import ReadFault, fingerprint, guarded, result, safe_child, stamp
from write_ledger import read_trace_page as read_writes

_SECRET = secrets.token_bytes(32)  # Restart expires capabilities; no persistent secret/file.
TOKEN_TTL = 900
MAX_TOKEN = 64000
TOKEN_FIELDS = ("input", "output", "cache_read", "cache_create", "reasoning")
SAFE_FIELDS = {"call_id", "parent_call_id", "provider", "model", "role", "phase", "round_index",
               "accounting", "usage_partial", "response_id", "status", "version", "gate", "event",
               "path", "size", "elapsed_ms", "latency_ms", "elapsed_s", "is_error", "operation", "name",
               "child_task_id", "child_run_id", "parent_task_id", "parent_run_id", *TOKEN_FIELDS}


def seal(payload):
    raw = json.dumps({"v": 1, "expires": int(time.time()) + TOKEN_TTL, **payload},
                     ensure_ascii=False, separators=(",", ":")).encode()
    token = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return token + "." + hmac.new(_SECRET, token.encode(), hashlib.sha256).hexdigest()


def unseal(token, purpose, scope):
    try:
        if not isinstance(token, str) or len(token) > MAX_TOKEN:
            raise ValueError
        raw, signature = token.rsplit(".", 1)
        if not hmac.compare_digest(hmac.new(_SECRET, raw.encode(), hashlib.sha256).hexdigest(), signature):
            raise ValueError
        value = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if value["v"] != 1 or value["expires"] < time.time():
            raise ReadFault("partial", "cursor_expired")
        if value["purpose"] != purpose or value["scope"] != scope:
            raise ValueError
        return value
    except (ValueError, KeyError, TypeError):
        raise ReadFault("forbidden", "invalid_reference") from None


def observed_time(value):
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


class ExecutionTrace:
    def __init__(self, root, *, system_db=None, runtime_probe=observe_runtime):
        self.resolver = ScopeResolver(root, system_db)
        self.runtime_probe = runtime_probe

    def _scope(self, access, query):
        return fingerprint([str(self.resolver.root), sorted(access.scopes) if access.scopes is not None else None,
                            access.evidence, query])

    def query(self, access, *, episode_id=None, task_id=None, run_id=None, project=None,
              owner=None, cursor=None, limit=50):
        query = {"episode_id": episode_id, "task_id": task_id, "run_id": run_id,
                 "project": project, "owner": owner}
        try:
            if type(limit) is not int or not 1 <= limit <= 100:
                raise ReadFault("malformed", "invalid_page_limit")
            scope = self._scope(access, query)
            previous = unseal(cursor, "cursor", scope) if cursor else {}
            resolved = self.resolver.resolve(access, **query)
            ident = resolved["identity"]
            task_source = read_task_trace(resolved["db"], ident["task_id"]) if resolved["db"] else result(
                "tasks", status="missing", reason="scope_identity_missing")
            metadata = fingerprint([resolved["episodes"], resolved["bindings"], task_source["rows"], task_source["status"]])
            if previous and previous["metadata"] != metadata:
                raise ReadFault("partial", "cursor_expired")
            positions = dict(previous.get("positions", {}))
            stores = dict(previous.get("stores", {}))
            usage = previous.get("usage") or {"measured": {}, "unattributed_records": 0,
                                              "records": 0, "partial_reasons": []}
            sources, events, evidence = [], [], []
            sources.append({k: v for k, v in task_source.items() if k != "rows"})
            sources.append({"source": "scope", "status": resolved["scope_status"], "observed_at": stamp()})
            sources.append({"source": "messages", "status": "missing", "reason": "no_task_foreign_key", "observed_at": stamp()})
            diagnostics = list(resolved["diagnostics"]) + previous.get("diagnostics", [])
            more = False

            def consume(name, page):
                nonlocal more
                if page.get("high_water"):
                    positions[name] = page["high_water"]
                elif page["status"] == "missing":
                    positions.setdefault(name, {"absent": True})
                if page.get("more"):
                    more = True
                sources.append({**{k: v for k, v in page.items() if k != "rows"}, "source": name})
                if page["status"] not in {"ok", "empty"} and page.get("reason") != "page_budget":
                    diagnostics.append(name + ":" + str(page.get("reason") or page["status"]))
                if name == "trajectory" and page["status"] not in {"ok", "empty"}:
                    usage["partial_reasons"].append(name + ":" + str(page.get("reason") or page["status"]))
                return page["rows"]

            def reference(source, record, **extra):
                return seal({"purpose": "source", "scope": scope, "source": source, "record": record, **extra})

            def event(source, record, kind, data, when=None, links=None, diagnostic=None):
                summary = {k: v for k, v in data.items() if k in SAFE_FIELDS
                           and isinstance(v, (str, int, float, bool, type(None)))}
                summary = {k: v[:160] if isinstance(v, str) else v for k, v in summary.items()}
                row = {"source": source, "source_record_id": record, "source_ref": reference(source, record),
                       "identity": ident, "kind": kind, "observed_at": observed_time(when),
                       "summary": summary, "links": links or [], "diagnostics": []}
                if row["observed_at"] is None:
                    row["diagnostics"].append("timestamp_timezone_unknown")
                if diagnostic:
                    row["diagnostics"].append(diagnostic)
                events.append(row)
                return row

            if not previous:
                store_links = read_trace_store_links(self.resolver.pulse, ident["episode_ids"])
                sources.append({k: v for k, v in store_links.items() if k != "rows"})
                for link in store_links["rows"]:
                    try:
                        relative = Path(link["store"]).relative_to(self.resolver.supervision)
                        if len(relative.parts) != 1:
                            raise ValueError
                        from supervision_store import trace_directory
                        trace_directory(self.resolver.supervision, relative.name)
                        if len(stores) >= 32 and relative.name not in stores:
                            raise ReadFault("partial", "store_budget")
                        stores.setdefault(relative.name, {})
                    except (ValueError, ReadFault):
                        diagnostics.append("forbidden_or_excess_store_reference")

            traj = read_trajectory_page(self.resolver.pulse, ident["episode_ids"], positions.get("trajectory"), limit)
            for row in consume("trajectory", traj):
                data = row["data"]
                record = f"pulse:{row['run_id']}:{row['event_seq']}"
                ev = event("trajectory", record, row["kind"], data, row["ts"], diagnostic=row.get("_diagnostic"))
                if row["kind"] == "model.usage" and data.get("accounting") == "billable_usage":
                    usage["records"] += 1
                    if not data.get("call_id"):
                        usage["unattributed_records"] += 1
                    for key in TOKEN_FIELDS:
                        if key not in data:
                            continue
                        number = numeric_value(data[key])
                        if number is None or number < 0:
                            usage["partial_reasons"].append("invalid_usage_number")
                        else:
                            usage["measured"][key] = usage["measured"].get(key, 0) + number
                if data.get("usage_partial"):
                    usage["partial_reasons"].append("usage_partial")
                if row["kind"].startswith("supervision.") and data.get("store"):
                    # The stored path is only a proposed handle. Resolve against one allowed root.
                    try:
                        path = Path(data["store"])
                        relative = path.relative_to(self.resolver.supervision)
                        if len(relative.parts) != 1:
                            raise ValueError
                        store_id = relative.name
                        from supervision_store import trace_directory
                        trace_directory(self.resolver.supervision, store_id)
                        if len(stores) >= 32 and store_id not in stores:
                            raise ReadFault("partial", "store_budget")
                        if store_id not in stores:
                            raise ReadFault("partial", "store_not_in_snapshot")
                        # Only seq is explicit; candidates are not merged by similar content.
                        ev["links"].append({"relation": "supervision_observation", "store_id": store_id,
                                            "seq": data.get("seq"), "relationship": "explicit"})
                    except (ValueError, ReadFault):
                        diagnostics.append("forbidden_store_reference")

            for suffix in (".1", ""):
                name = "writes" + suffix
                path = safe_child(self.resolver.root / "data", "write_ledger.jsonl" + suffix)
                page = read_writes(ident["episode_ids"], positions.get(name), limit, path)
                for row in consume(name, page):
                    water = page["high_water"]
                    record = f"{name}:{fingerprint(water['file'])[:16]}:{row['_offset']}:{row['_hash']}"
                    target = f"pulse:{row.get('run')}:{row.get('event_seq')}"
                    links = [{"relation": "observation_of", "source_record_id": target, "relationship": "explicit"}] if row.get("run") and row.get("event_seq") else []
                    observation = event("writes", record, "side_effect." + str(row.get("event", "write")), row, row.get("ts"), links)
                    target_row = next((e for e in events[:-1] if e["source_record_id"] == target
                                       and e["source"] == "trajectory" and e["kind"] == "side_effect.write"), None)
                    if target_row is not None:
                        target_row.setdefault("observations", []).append(observation)
                        events.pop()
            diagnostics.append("writes_partial:gate_only_heartbeat_compressed_retention_limited")

            if resolved["db"]:
                page = read_pursuit_events(resolved["db"], ident["task_id"], ident["owner"], positions.get("pursuit_events"), limit)
                for row in consume("pursuit_events", page):
                    event("pursuit", f"{ident['project']}:{row['pursuit_id']}:{row['id']}",
                          "pursuit." + row["kind"], {}, row["created_at"])
            for store_id in stores:
                name = "supervision:" + store_id
                page = read_supervision_events(self.resolver.supervision, store_id, positions.get(name), limit)
                seen = stores[store_id]
                for row in consume(name, page):
                    if row.get("task_id") != ident["task_id"]:
                        diagnostics.append("supervision_task_mismatch")
                        continue
                    seq = str(row.get("seq"))
                    seen[seq] = seen.get(seq, 0) + 1
                    if seen[seq] > 1:
                        diagnostics.append("ambiguous_supervision_sequence")
                    record = f"{store_id}:{fingerprint(page['high_water']['file'])[:16]}:{row['_offset']}:{row['_hash']}"
                    ev = event("supervision", record, "supervision." + str(row.get("kind", "unknown")), row, row.get("time"))
                    ev["summary"]["seq"] = row.get("seq")
                    for field in ("input", "result", "evidence", "response"):
                        value = row.get(field)
                        if not isinstance(value, dict):
                            continue
                        key = value.get("id")
                        if field == "response" and type(value.get("version")) is int:
                            name = f"response-v{value['version']}.txt"
                        elif isinstance(key, str) and len(key) == 64 and all(c in "0123456789abcdef" for c in key):
                            name = key + ".txt"
                        else:
                            continue
                        ref = reference("supervision", name, store_id=store_id)
                        availability = inspect_trace_document(self.resolver.supervision, store_id, name)
                        link = {"status": availability["status"], "reason": availability.get("reason"), "source_ref": ref, "label": field, "chars": value.get("chars"),
                                "access": "explicit_read_required", "source_record_id": record}
                        ev["links"].append(link)
                        evidence.append(link)
                        if availability["status"] != "ok":
                            diagnostics.append("evidence:" + str(availability.get("reason") or availability["status"]))
            if not stores:
                sources.append({"source": "supervision", "status": "missing", "reason": "explicit_store_link_missing", "observed_at": stamp()})
            runtime = self.runtime_probe(ident["episode_ids"])
            own = next((r for r in task_source["rows"] if r["task_id"] == ident["task_id"]), {})
            task_state = own.get("status", "unknown")
            conflict = runtime["status"] == "running" and (task_state == "completed" or any(r["ended_at"] for r in resolved["episodes"]))
            if conflict:
                diagnostics.append("task_runtime_conflict")
            state = {"task": task_state, "runtime": runtime, "episodes": resolved["episodes"],
                     "assessment": "conflict" if conflict else "unconfirmed" if runtime["status"] == "unknown" else "observed",
                     "last_event": next((e["source_record_id"] for e in reversed(events) if e["source"] == "trajectory"), previous.get("last_event")),
                     "observed_at": stamp()}
            links = {"parents": [], "children": [], "pursuits": resolved["bindings"], "evidence": evidence,
                     "messages": [], "documents": []}
            if own.get("parent_task_id"):
                links["parents"].append({"task_id": own["parent_task_id"], "relationship": "explicit"})
            for ep in resolved["episodes"]:
                if ep.get("parent_run_id"):
                    links["parents"].append({"run_id": ep["parent_run_id"], "relationship": "explicit"})
                links["documents"].append({"label": f"episode {ep['id']} log", "source_ref": reference("episode", ep["id"])})
            links["children"] = [{**r, "relationship": "explicit"} for r in task_source["rows"] if r.get("parent_task_id") == ident["task_id"]]
            for binding in resolved["bindings"]:
                for field in ("input", "response"):
                    links["documents"].append({"label": "pursuit " + field,
                        "source_ref": reference("pursuits", binding["pursuit_id"], field=field)})
            if own:
                links["documents"].append({"label": "task result", "source_ref": reference("tasks", ident["task_id"])})
            usage["partial_reasons"] = sorted(set(usage["partial_reasons"]))
            usage.update(complete=False, scope="billable_usage_observed_through_this_page", currency=None)
            if usage["unattributed_records"]:
                usage["partial_reasons"] = sorted(set(usage["partial_reasons"] + ["legacy_call_identity_missing"]))
            # Observation hooks are best effort. Finishing a page never proves zero missing charges.
            usage["complete"] = False
            usage["recorded_events_complete"] = not more and bool(usage["records"]) and not usage["partial_reasons"]
            usage["coverage"] = "recorded_billable_events_only; best_effort_observation_cannot_prove_full_billing"
            expired = any(s.get("reason") == "cursor_expired" for s in sources)
            next_cursor = seal({"purpose": "cursor", "scope": scope, "metadata": metadata,
                                "positions": positions, "stores": stores, "usage": usage,
                                "last_event": state["last_event"], "diagnostics": sorted(set(diagnostics))}) if more and not expired else None
            if next_cursor and len(next_cursor) > MAX_TOKEN:
                next_cursor = None
                diagnostics.append("cursor_size_budget")
            return {"status": "ok", "identity": ident, "state": state, "events": events, "links": links,
                    "usage": usage, "sources": sources, "diagnostics": sorted(set(diagnostics)),
                    "partial": bool(diagnostics) or more or any(s["status"] not in {"ok", "empty"} for s in sources),
                    "next_cursor": next_cursor, "cursor_expired": expired,
                    "ordering": "per_source; trajectory order is per run; no global causal order"}
        except ReadFault as exc:
            return {"status": exc.status, "reason": exc.reason, "partial": True,
                    "events": [], "sources": [], "next_cursor": None,
                    "cursor_expired": exc.reason == "cursor_expired"}
        except (OSError, ValueError, TypeError, KeyError):
            return {"status": "unavailable", "reason": "scope_resolution_failed", "partial": True,
                    "events": [], "sources": [], "next_cursor": None}

    def document(self, access, source_ref, *, episode_id=None, task_id=None, run_id=None,
                 project=None, owner=None, offset=0, limit=12000, cursor=None):
        query = {"episode_id": episode_id, "task_id": task_id, "run_id": run_id, "project": project, "owner": owner}
        try:
            if not access.evidence:
                raise ReadFault("forbidden", "access_denied")
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 12000:
                raise ReadFault("malformed", "invalid_page_bounds")
            scope = self._scope(access, query)
            ref = unseal(source_ref, "source", scope)
            resolved = self.resolver.resolve(access, **query)
            previous = unseal(cursor, "document", scope) if cursor else {}
            if previous and (previous["ref"] != fingerprint(source_ref) or previous["offset"] != offset):
                raise ReadFault("forbidden", "invalid_reference")
            if ref["source"] == "supervision":
                page = read_trace_document(self.resolver.supervision, ref["store_id"], ref["record"], offset, limit, previous.get("water"))
            elif ref["source"] == "episode" and ref["record"] in resolved["identity"]["episode_ids"]:
                page = read_episode_text(self.resolver.pulse, ref["record"], offset, limit)
            elif ref["source"] == "tasks" and ref["record"] == resolved["identity"]["task_id"] and resolved["db"]:
                page = read_task_result(resolved["db"], ref["record"], offset, limit)
            elif ref["source"] == "pursuits" and resolved["db"] and any(
                    r["pursuit_id"] == ref["record"] for r in resolved["bindings"]):
                page = read_pursuit_text(resolved["db"], ref["record"], resolved["identity"]["task_id"],
                                         resolved["identity"]["owner"], ref["field"], offset, limit)
            else:
                raise ReadFault("forbidden", "invalid_reference")
            if previous and page["status"] in {"ok", "empty"} and page.get("high_water") != previous["water"]:
                raise ReadFault("partial", "cursor_expired")
            rows = page.pop("rows")
            if rows:
                page.update(rows[0])
                end = offset + len(page.get("text") or "")
                page["next_offset"] = end if end < (page.get("chars") or 0) else None
                page["next_cursor"] = seal({"purpose": "document", "scope": scope, "ref": fingerprint(source_ref),
                                            "offset": end, "water": page["high_water"]}) if page["next_offset"] is not None else None
            page.update(offset=offset, inspection_only=True)
            return page
        except ReadFault as exc:
            return {"status": exc.status, "reason": exc.reason, "partial": True, "next_cursor": None}
