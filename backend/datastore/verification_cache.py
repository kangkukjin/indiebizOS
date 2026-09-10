"""같은 턴의 검수 근거 재사용. 파일·의존 입력·기준·검수 계약이 같을 때만 유효하다."""
import hashlib
from pathlib import Path

POLICY_VERSION = "review-evidence-v1"


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class VerificationCache:
    def __init__(self):
        self.records = []

    def remember(self, checks, criteria_hash, store):
        for check in checks if isinstance(checks, list) else []:
            if not isinstance(check, dict) or check.get("status") != "passed":
                continue
            if not all(check.get(k) for k in ("path", "coverage", "tool_version", "evidence_ids")):
                continue
            try:
                # 원문 증거가 없으면 재사용 자료로도 인정하지 않는다. 승인 자체를 대신하지는 않는다.
                for key in check["evidence_ids"]:
                    store.read_evidence(key, 0, 1)
                dependencies = [check["path"], *check.get("dependencies", []), *check.get("validator_paths", [])]
                hashes = {str(Path(p).resolve()): file_hash(p) for p in dependencies}
                self.records.append({**check, "hashes": hashes, "criteria_hash": criteria_hash,
                                     "policy_version": POLICY_VERSION})
            except (OSError, ValueError, TypeError, KeyError):
                continue

    def valid(self, criteria_hash):
        valid = []
        for record in self.records:
            try:
                if (record["criteria_hash"] == criteria_hash and record["policy_version"] == POLICY_VERSION
                        and all(file_hash(p) == h for p, h in record["hashes"].items())):
                    valid.append(record)
            except OSError:
                pass
        # 같은 파일·검사 범위의 최신 기록만 보여준다.
        unique = {(r["path"], str(r["coverage"]), r["tool_version"]): r for r in valid}
        return list(unique.values())

    def visual_input(self, artifacts, criteria_hash, store):
        """명시적으로 합격한 동일 픽셀의 배치 검수만 재사용. 사실·주장 검수는 별도다."""
        reviewed = {str(Path(r["path"]).resolve()): r for r in self.valid(criteria_hash)
                    if r["coverage"] == "visual_layout"}
        pending, attached, reused = [], [], []
        for artifact in artifacts:
            path = str(Path(artifact.get("_path", "")).resolve())
            if path in reviewed:
                reused.append({"path": path, "coverage": "visual_layout", "evidence_ids": reviewed[path]["evidence_ids"]})
            else:
                pending.append(artifact)
                try:
                    ref = store.evidence({"path": path, "hash": file_hash(path), "kind": "attached_visual"})
                    attached.append({"path": path, "evidence_id": ref["id"]})
                except OSError:
                    pass
        return pending or None, {"attached": attached, "reused": reused}
