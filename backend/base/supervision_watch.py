"""침묵도 관측하는 값싼 시계. LLM 폴링 없이 실제 백그라운드 작업 로그의 증분만 읽는다."""
import json
import re
import time
from pathlib import Path


class JobWatch:
    def __init__(self, log_path, now=None):
        self.path = Path(log_path)
        self.offset = 0
        self.started = now if now is not None else time.monotonic()
        self.last_progress = self.started
        self.last_alive = self.started
        self.phase = "running"
        self.units = None
        self.detail = ""
        self.signature = None
        self.metadata = {}
        self._tail = b""
        self._inode = None
        self._job_mtime = None

    def poll(self, now=None):
        now = time.monotonic() if now is None else now
        try:
            stat = self.path.stat()
            if stat.st_size < self.offset or self._inode != stat.st_ino:
                self.offset = 0  # runner의 완료 시 원자 재작성
                self._tail = b""
            self._inode = stat.st_ino
            with self.path.open("rb") as stream:
                stream.seek(self.offset)
                raw = stream.read(65536)
                self.offset = stream.tell()
            raw = self._tail + raw
            split = raw.rfind(b"\n")
            chunk = raw[:split + 1].decode("utf-8", errors="replace") if split >= 0 else ""
            self._tail = raw[split + 1:][-65536:]
        except OSError:
            chunk = ""
        changed = False
        if chunk:
            self.last_alive = now
            for line in chunk.splitlines():
                # 구조화 PROGRESS가 우선. 기존 나레이션의 N/M, 모델 로딩, 다운로드도 해석.
                payload = None
                if "PROGRESS " in line:
                    try:
                        payload = json.loads(line.split("PROGRESS ", 1)[1])
                    except (ValueError, TypeError):
                        pass
                match = re.search(r"(\d+)\s*/\s*(\d+)", line)
                phase = next((p for p in ("model-load", "generate", "download", "cleanup", "complete")
                              if p in line.lower()), self.phase)  # vj-ok: 로그 단계 프로토콜 토큰
                units = [int(match[1]), int(match[2])] if match else self.units
                if isinstance(payload, dict):
                    phase = payload.get("phase", phase)
                    if "completed" in payload:
                        units = [payload["completed"], payload.get("total")]
                    self.metadata.update({k: v for k, v in payload.items() if k not in {"elapsed_s", "phase", "completed", "total"}})
                signature = (phase, str(units))
                if signature != self.signature and (phase != "running" or units is not None):
                    self.last_progress = now
                    changed = True
                    self.signature = signature
                self.phase, self.units, self.detail = phase, units, line[-600:]
        # 러너의 종료는 산문을 추측하지 않고 원자적으로 기록되는 job 행으로 확인한다.
        job_path = self.path.parent / "jobs" / (self.path.stem + ".json")
        try:
            modified = job_path.stat().st_mtime_ns
            if modified != self._job_mtime:
                with job_path.open(encoding="utf-8") as stream:
                    row = json.loads(stream.read(1024 * 1024))
                self._job_mtime = modified
                status = row.get("status")
                self.metadata.update(job_status=status, runner_pid=row.get("runner_pid"), error=row.get("error"))
                if status in {"done", "failed", "timeout", "lost"}:
                    self.phase = "complete"
                    changed = True
                    self.last_progress = now
        except (OSError, ValueError):
            pass
        return {**self.metadata, "path": str(self.path), "phase": self.phase, "units": self.units,
                "elapsed_s": round(now - self.started), "stalled_s": round(now - self.last_progress),
                "silent_s": round(now - self.last_alive), "changed": changed, "detail": self.detail}
