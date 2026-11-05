"""검수 대기 산출물과 알림. 승인한 바이트를 옮기며 모델에게 본문 재출력을 시키지 않는다."""
import hashlib
import json
import os
import threading
import uuid
from pathlib import Path

STAGING_ENV = "INDIEBIZ_REVIEW_STAGING"


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_bytes(content)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def stage_artifact(target, content, public_root, *, directory=None):
    """협력하는 등록 스크립트의 공개 출력 계약. 감독 문맥 밖에서는 기존 쓰기를 유지한다."""
    directory = directory or os.environ.get(STAGING_ENV)
    if not directory:
        return None
    target, root = Path(target).resolve(), Path(public_root).resolve()
    if not target.is_relative_to(root):
        return None  # 사적인 중간 파일은 검수 대기 공개물이 아니다.
    directory = Path(directory).resolve()
    key = _hash(str(target).encode())
    staged = directory / (key + target.suffix)
    _atomic(staged, content)
    record = {"staged": str(staged), "target": str(target)}
    _atomic(directory / (key + ".publication.json"), json.dumps(record, ensure_ascii=False).encode())
    return record


class DeliveryQueue:
    def __init__(self, directory, public_root, log):
        self.directory = Path(directory).resolve()
        self.public_root = Path(public_root).resolve()
        self.log = log
        self.lock = threading.RLock()
        self.notifications = {}
        saved = self.directory / "notifications.json"
        if saved.exists():
            self.notifications = {row['title']: row for row in json.loads(saved.read_text())}
        self.finished = False
        self.observed = ""

    def environment(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        return {**os.environ, STAGING_ENV: str(self.directory)}

    def notify(self, title, body, kind):
        with self.lock:
            if self.finished:
                raise ValueError("이미 전달을 확정한 턴입니다")
            # 같은 제목의 수정본은 대체한다. 보완 중 옛 수치의 알림을 중복 발송하지 않는다.
            candidate = {"title": title, "body": body, "kind": kind, "source": "ai"}
            previous = self.notifications.get(title, {})
            if self._notification(previous) != candidate:
                if previous.get('_delivery') == 'pending':
                    raise ValueError("이 알림의 전송 결과가 미확인입니다. 재전송 전에 기존 효과를 확인하세요")
                self.notifications[title] = candidate
            self.log("delivery.notification_queued", notification=self.notifications[title])
            self._save_notifications()

    def _save_notifications(self):
        _atomic(self.directory / "notifications.json", json.dumps(
            list(self.notifications.values()), ensure_ascii=False).encode())

    @staticmethod
    def _notification(row):
        return {k: v for k, v in row.items() if not k.startswith('_')}

    def _artifacts(self):
        artifacts = []
        for record in sorted(self.directory.glob("*.publication.json")):
            row = json.loads(record.read_text(encoding="utf-8"))
            staged, target = Path(row["staged"]).resolve(), Path(row["target"]).resolve()
            if staged.parent != self.directory or not target.is_relative_to(self.public_root):
                raise ValueError("검수 대기 파일 또는 공개 경로가 턴의 범위를 벗어났습니다")
            content = staged.read_bytes()
            artifacts.append({"staged": str(staged), "target": str(target),
                              "hash": _hash(content), "bytes": len(content)})
        return artifacts

    def manifest(self):
        with self.lock:
            artifacts = self._artifacts()
            notifications = [self._notification(row) for row in self.notifications.values()]
            if self.finished or not (artifacts or notifications):
                return None
            body = {"artifacts": artifacts, "notifications": notifications}
            fingerprint = _hash(json.dumps(body, sort_keys=True, ensure_ascii=False).encode())
            if fingerprint != self.observed:
                self.observed = fingerprint
                self.log("delivery.pending", manifest={**body, "hash": fingerprint})
            return {**body, "hash": fingerprint}

    def deliver(self, approved_hash, cancelled=lambda: False):
        """현재 초안 전체의 지문을 먼저 검증한다. 실패하면 완료 알림은 보내지 않는다."""
        with self.lock:
            manifest = self.manifest()
            if manifest is None:
                return
            if approved_hash != manifest["hash"] or cancelled():
                raise ValueError("승인한 공개 산출물·알림의 지문이 현재 초안과 다릅니다")
            payloads = []
            for row in manifest["artifacts"]:
                content = Path(row["staged"]).read_bytes()
                if _hash(content) != row["hash"]:
                    raise ValueError("승인 후 산출물이 변경되었습니다")
                payloads.append((row, content))
            if cancelled():
                raise ValueError("공개 전에 작업이 취소되었습니다")
            for row, content in payloads:
                if cancelled():
                    raise ValueError("공개 중 작업이 취소되었습니다")
                target = Path(row["target"])
                if target.exists() and _hash(target.read_bytes()) == row['hash']:
                    continue  # 재개 시 이미 발행된 같은 바이트를 다시 쓰지 않는다.
                _atomic(target, content)
                self.log("delivery.published", **row)
            from notify_dispatch import notify_user
            for notification in manifest["notifications"]:
                saved = self.notifications[notification['title']]
                if saved.get('_delivery') == 'completed':
                    continue
                if saved.get('_delivery') == 'pending':
                    raise ValueError("알림 전송 결과가 미확인입니다. 자동으로 다시 보내지 않습니다")
                if cancelled():
                    raise ValueError("알림 전달 전에 작업이 취소되었습니다")
                saved['_delivery'] = 'pending'
                self._save_notifications()
                delivered = notify_user(**notification)
                self.log("delivery.notified", notification=notification, delivered_to_launcher=delivered)
                if not delivered:
                    raise ValueError("알림 전달을 확인하지 못했습니다")
                saved['_delivery'] = 'completed'
                self._save_notifications()
            self.finished = True
            self.log("delivery.completed", manifest_hash=manifest["hash"])
