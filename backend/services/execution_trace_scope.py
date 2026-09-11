"""Trusted read scopes resolved from registered metadata, never from request paths."""
import os
from dataclasses import dataclass
from pathlib import Path

from episode_logger import read_episode_identity, trajectory_run_id
from pursuit_ledger import read_trace_bindings
from trace_read import ReadFault, safe_child, stamp


@dataclass(frozen=True)
class TraceAccess:
    # None means the local body owner / authenticated launcher session.
    scopes: frozenset | None = frozenset()
    evidence: bool = False

    def allows(self, scope):
        return self.scopes is None or scope in self.scopes


class ScopeResolver:
    def __init__(self, root, system_db=None):
        self.root = Path(root).resolve()
        self.pulse = self.root / "data" / "world_pulse.db"
        self.supervision = self.root / "data" / "spill" / "supervision"
        self.system_db = Path(system_db) if system_db else (
            Path(os.environ.get("INDIEBIZ_USERDATA") or self.root / "data") / "system_ai_memory.db")

    def scopes(self, access):
        # Read the existing owner's metadata without ProjectManager's mkdir/init.
        import json
        registry = safe_child(self.root / "projects", "projects.json")
        if registry.stat().st_size > 256 * 1024:
            raise ReadFault("partial", "scope_registry_budget")
        projects = json.loads(registry.read_text(encoding="utf-8"))
        if not isinstance(projects, list) or len(projects) > 64:
            raise ReadFault("partial", "scope_registry_budget")
        scopes = {"system": self.system_db} if access.allows("system") else {}
        for project in projects:
            if project.get("type") != "project":
                continue
            key = project.get("id")
            if not key or not access.allows(key):
                continue
            # Registered path is authority, but its resolved location must stay in projects.
            registered = Path(project.get("path") or self.root / "projects" / key)
            try:
                parts = registered.relative_to(self.root / "projects").parts
            except ValueError:
                continue
            scopes[key] = safe_child(self.root / "projects", *parts, "conversations.db")
        return scopes

    def resolve(self, access, *, episode_id=None, task_id=None, run_id=None,
                project=None, owner=None):
        if access.scopes == frozenset() or (project is not None and not access.allows(project)):
            raise ReadFault("forbidden", "access_denied")
        if episode_id is None and (not project or not owner or not (task_id or run_id)):
            raise ReadFault("forbidden", "validated_scope_required")
        catalog = self.scopes(access)
        if project is not None and project not in catalog:
            raise ReadFault("forbidden", "access_denied")
        episode = read_episode_identity(self.pulse, episode_id=episode_id, task_id=task_id, run_id=run_id)
        if episode["status"] not in {"ok", "empty"}:
            raise ReadFault(episode["status"], episode["reason"])
        episodes = episode["rows"]
        if episode_id is not None and not episodes:
            raise ReadFault("missing", "episode_missing")
        tasks = {r["task_id"] for r in episodes if r.get("task_id")}
        if task_id:
            tasks.add(task_id)
        if len(tasks) > 1:
            raise ReadFault("partial", "ambiguous_task_identity")
        if not tasks and episode_id is None:
            raise ReadFault("missing", "task_identity_missing")
        task = next(iter(tasks), "")
        candidates, diagnostics, failed_scopes = [], [], []
        for scope, path in catalog.items():
            if project is not None and scope != project:
                continue
            binding = read_trace_bindings(path, episode_id=episode_id, task_id=task, owner=owner)
            if binding["status"] not in {"ok", "empty", "missing"}:
                failed_scopes.append(scope)
            for row in binding["rows"]:
                if row["task_id"] == task:
                    candidates.append({**row, "project": scope})
        owners = {(r["project"], r["agent_key"]) for r in candidates}
        selected = None
        if len(owners) == 1 and not failed_scopes:
            selected = next(iter(owners))
        elif len(owners) > 1:
            diagnostics.append("ambiguous_scope_identity")
        else:
            diagnostics.append("scope_identity_missing" if not failed_scopes else "scope_lookup_incomplete")
        # Explicit project+owner with a real pursuit binding is still required for task-only.
        if episode_id is None:
            if selected is None and not owners and project and owner and not failed_scopes:
                from conversation_db import read_task_trace
                task_rows = read_task_trace(catalog[project], task)
                if any(r["task_id"] == task for r in task_rows["rows"]):
                    selected = (project, owner)
                    diagnostics.append("task_owner_relationship_missing")
            if selected is None:
                raise ReadFault("partial", diagnostics[0])
            ids = {str(r["episode_id"]) for r in candidates if r["episode_id"]}
            episodes = [r for r in episodes if str(r["id"]) in ids]
        elif access.scopes is not None and (selected is None or selected[0] not in access.scopes):
            raise ReadFault("forbidden", "access_denied")
        # A user-supplied mismatched scope never silently falls back to the global episode.
        if project is not None and (selected is None or selected != (project, owner)):
            raise ReadFault("forbidden", "access_denied")
        if not episodes:
            diagnostics.append("scoped_episode_missing")
        runs = {r.get("run_id") for r in episodes if r.get("run_id")}
        if run_id and runs and run_id not in runs:
            raise ReadFault("partial", "ambiguous_run_identity")
        run = next(iter(runs)) if len(runs) == 1 else trajectory_run_id(task) if not runs and task else None
        identity = {"task_id": task, "run_id": run, "episode_ids": [r["id"] for r in episodes],
                    "project": selected[0] if selected else None, "owner": selected[1] if selected else None,
                    "relationship": "ambiguous" if len(runs) > 1 else "explicit" if runs else "deterministic_legacy" if task else "missing",
                    "scope_relationship": "explicit" if selected else "ambiguous" if len(owners) > 1 else "missing"}
        return {"identity": identity, "episodes": episodes, "bindings": candidates if selected else [],
                "db": catalog[selected[0]] if selected else None, "diagnostics": diagnostics,
                "scope_status": "unavailable" if failed_scopes else "ok" if selected else "missing"}


def observe_runtime(episode_ids):
    """Only this process's explicit live episode registry is evidence. Absence is unknown."""
    from episode_logger import live_episode_ids
    active = sorted(set(episode_ids) & set(live_episode_ids()))
    return {"status": "running" if active else "unknown", "episode_ids": active,
            "basis": "local_live_episode_registry", "observed_at": stamp()}
