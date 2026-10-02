"""코딩 과제의 작업 공간·검토·정본 반영. 실행자에게 반영 권한은 주지 않는다."""
import os
import time
from pathlib import Path

from coding_git import (CodingConflict, commit_paths, current_tree, delta, git,
                        identity, require_clean_targets, safe_path, status,
                        target_state, text_git, untracked)
from coding_store import CodingStore, fingerprint, identifier
from pursuit_ledger import PursuitLedger
from runtime_utils import get_base_path


class CodingWorkspace:
    def __init__(self, store=None):
        self.store = store or CodingStore()
        self.ledger = PursuitLedger(self.store.root / "pursuits.db", "coding:owner")

    def open_repository(self, path):
        root, common = identity(path)
        own = Path(get_base_path()).resolve()
        _, own_common = identity(own)
        key = "repo_" + fingerprint(common)[:24]
        row = {"id": key, "path": str(root), "common": common,
               "kind": "repair" if common == own_common else "git",
               "head": text_git(root, "rev-parse", "HEAD"), "existing_changes": status(root),
               "start_policy": "clean_head", "dirty_import_supported": False}
        return self.store.save("repository", row)

    def create_task(self, repository_id, goal):
        if not goal.strip() or len(goal) > 1500:
            raise ValueError("목표는 1~1500자로 입력하세요")
        repo = self.store.get("repository", repository_id)
        if repo["kind"] == "repair":
            # 자기 저장소 반영은 기존 REPAIR·RED 적용 경로만 소유한다. 그 연동 전에는 일반 반영으로 우회하지 않는다.
            raise ValueError("indiebizOS 자기 저장소는 아직 코딩 앱에서 다룰 수 없습니다(자기수리 연동 미구현). 시스템 AI의 수리 경로를 사용하세요")
        task_id = identifier("coding")
        with self.store.lock(repo["common"]):
            start = text_git(repo["path"], "rev-parse", "HEAD")
            workspace = self.store.root / "workspaces" / task_id
            workspace.parent.mkdir(exist_ok=True)
            git(repo["path"], "worktree", "add", "--detach", str(workspace), start)
            pursuit = self.ledger.create(goal[:60], goal, task_id)
            task = {"id": task_id, "repository_id": repository_id,
                    "workspace_id": identifier("workspace"), "workspace": str(workspace),
                    "start": start, "start_tree": text_git(workspace, "rev-parse", "HEAD^{tree}"),
                    "goal": goal, "pursuit_id": pursuit["id"], "active_run": None,
                    "review_id": None, "apply_id": None, "created_at": time.time(),
                    "existing_changes": status(repo["path"]), "kind": repo["kind"]}
            self.store.save("task", task)
            self.store.event(task_id, "", "task.created", {"pursuit_id": pursuit["id"], "start": start})
            return task

    def idle(self, task):
        if task.get("active_run"):
            raise CodingConflict("실행과 소유 프로세스 종료 후 사용할 수 있습니다")

    def files(self, task_id):
        task = self.store.get("task", task_id)
        root = task["workspace"]
        paths = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
        return sorted(set(p for p in paths if p))

    def read_file(self, task_id, path):
        task = self.store.get("task", task_id)
        target = safe_path(task["workspace"], path)
        if not target.is_file():
            raise ValueError("파일이 없습니다")
        data = target.read_bytes()
        binary = b"\0" in data[:8192]
        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError:
            binary, decoded = True, ""
        return {"path": path, "fingerprint": fingerprint(data), "binary": binary,
                "size": len(data), "truncated": len(data) > 200000,
                "text": "" if binary else decoded[:200000]}

    def save_file(self, task_id, path, content, expected, *, run_id=None):
        if len(content.encode()) > 200000:
            raise ValueError("간단 편집은 200KB 이하 텍스트만 지원합니다")
        with self.store.lock(task_id):
            task = self.store.get("task", task_id)
            if run_id is None or task.get('active_run') != run_id:
                self.idle(task)
            target = safe_path(task["workspace"], path)
            if run_id is None and target.exists():
                opened = self.read_file(task_id, path)
                if opened["binary"] or opened["truncated"]:
                    raise ValueError("간단 편집은 200KB 이하 UTF-8 텍스트만 지원합니다")
            actual = fingerprint(target.read_bytes()) if target.exists() else None
            if actual != expected:
                raise CodingConflict("파일이 변경되었습니다. 다시 읽고 저장하세요")
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + ".coding-save")
            if temp.exists():
                raise CodingConflict("저장 임시 경로가 이미 있습니다")
            try:
                with temp.open("x", encoding="utf-8") as stream:
                    stream.write(content)
                if target.exists():
                    temp.chmod(target.stat().st_mode & 0o777)
                if (fingerprint(target.read_bytes()) if target.exists() else None) != expected:
                    raise CodingConflict("저장 직전에 파일이 변경되었습니다")
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
            task["review_id"] = None
            self.store.save("task", task)
            self.store.event(task_id, "", "file.saved", {"path": path, "fingerprint": fingerprint(content.encode())})
            return self.read_file(task_id, path)

    def review(self, task_id, selected):
        with self.store.lock(task_id):
            task = self.store.get("task", task_id)
            self.idle(task)
            root = task["workspace"]
            if not set(selected).issubset(set(untracked(root))):
                raise ValueError("선택한 미추적 파일 목록이 바뀌었습니다")
            tree = current_tree(root, selected)
            paths, patch = delta(root, task["start_tree"], tree)
            repo = self.store.get("repository", task["repository_id"])
            validations = [v for v in self.store.list("verification") if v["task_id"] == task_id]
            work_fingerprint = current_tree(root)
            row = {"id": identifier("review"), "task_id": task_id, "tree": tree,
                   "start": task["start_tree"], "paths": paths, "selected": selected,
                   "patch": patch.decode(), "patch_hash": fingerprint(patch),
                   "workspace_fingerprint": work_fingerprint,
                   "target": target_state(repo["path"], paths), "approved": False,
                   "verifications": [{**v, "fresh": v["fingerprint"] == work_fingerprint} for v in validations],
                   "created_at": time.time()}
            row["fingerprint"] = fingerprint(row)
            self.store.save("review", row)
            task["review_id"] = row["id"]
            self.store.save("task", task)
            return row

    def fresh_review(self, task, review_id, expected):
        self.idle(task)
        review = self.store.get("review", review_id)
        if review["task_id"] != task["id"] or task["review_id"] != review_id or review["fingerprint"] != expected:
            raise CodingConflict("현재 과제의 검토 묶음과 일치하지 않습니다")
        if current_tree(task["workspace"]) != review["workspace_fingerprint"]:
            raise CodingConflict("검토 뒤 파일이 바뀌었습니다. 다시 검토하세요")
        return review

    def approve(self, task_id, review_id, expected):
        with self.store.lock(task_id):
            task = self.store.get("task", task_id)
            review = self.fresh_review(task, review_id, expected)
            review["approved"] = True
            self.store.event(task_id, "", "review.approved", {"review_id": review_id, "fingerprint": expected})
            return self.store.save("review", review)

    def apply(self, task_id, review_id, expected, command_id, message):
        if not command_id or not message.strip():
            raise ValueError("반영 명령 ID와 커밋 메시지가 필요합니다")
        with self.store.lock(task_id):
            task = self.store.get("task", task_id)
            repo = self.store.get("repository", task["repository_id"])
            with self.store.lock(repo["common"]):
                review = self.fresh_review(task, review_id, expected)
                if not review["approved"] or not review["paths"]:
                    raise CodingConflict("승인된 변경 묶음이 필요합니다")
                key = "apply_" + fingerprint([task_id, command_id])[:32]
                matches = [r for r in self.store.list("apply") if r["id"] == key]
                operation = matches[0] if matches else None
                if operation and (operation["review_id"] != review_id or operation["message"] != message):
                    raise CodingConflict("같은 명령 ID로 다른 반영을 요청할 수 없습니다")
                if operation and operation["state"] == "completed":
                    return operation
                root = repo["path"]
                if not operation:
                    if target_state(root, review["paths"]) != review["target"]:
                        raise CodingConflict("정본 상태가 바뀌었습니다. 검토 묶음을 갱신하세요")
                    require_clean_targets(root, review["start"], review["paths"])
                    if not any(v["fresh"] and v["state"] == "passed" for v in review["verifications"]):
                        raise CodingConflict("현재 변경의 성공한 검증이 필요합니다")
                    patch = review["patch"].encode()
                    git(root, "apply", "--check", "--binary", "-", data=patch)
                    operation = {"id": key, "task_id": task_id, "review_id": review_id,
                                 "message": message, "state": "applying", "before": review["target"],
                                 "commit": None}
                    self.store.save("apply", operation)
                    task["apply_id"] = key
                    self.store.save("task", task)
                    if target_state(root, review["paths"]) != operation["before"]:
                        raise CodingConflict("쓰기 직전에 정본이 변경되었습니다")
                    git(root, "apply", "--binary", "-", data=patch)
                    operation["after"] = target_state(root, review["paths"])
                    operation["state"] = "commit_pending"
                    self.store.save("apply", operation)
                if operation["state"] == "applying":
                    raise CodingConflict("반영 중 중단됐습니다. 자동 재복사는 하지 않습니다. 복구 확인이 필요합니다")
                if target_state(root, review["paths"]) != operation["after"]:
                    raise CodingConflict("부분 반영 후 정본이 바뀌었습니다. 복구 확인이 필요합니다")
                try:
                    operation["commit"] = commit_paths(root, review["paths"], message, operation["after"]["head"])
                    operation["state"] = "completed"
                    operation.pop("error", None)
                except (CodingConflict, OSError) as exc:
                    operation["state"] = "commit_pending"
                    operation["error"] = str(exc)
                self.store.save("apply", operation)
                self.store.event(task_id, "", "apply." + operation["state"], operation)
                return operation
