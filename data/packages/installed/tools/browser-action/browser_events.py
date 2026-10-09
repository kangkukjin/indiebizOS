"""Playwright session events: one bounded journal and operation receipt for every op.

An event is observed during a command, not proof that the command caused it.
Late events remain pending for the next receipt. Download bytes never enter JSON.
"""
import asyncio
import os
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from weakref import WeakKeyDictionary

from tool_context import ToolContext


class BrowserEvents:
    def __init__(self, session):
        self.session = session
        self.pending = deque(maxlen=256)
        self.dropped = 0
        self.tasks = set()
        self.downloads = deque(maxlen=100)
        self.project_path = "."
        self.destination = None
        self.download_index = 0
        self.before_tab = ""
        self.urls = {}
        self.responses = WeakKeyDictionary()

    def record(self, kind, **data):
        row = {"kind": kind, **data, "timestamp": datetime.now().isoformat()}
        if len(self.pending) == self.pending.maxlen:
            self.dropped += 1
        self.pending.append(row)
        return row

    def begin(self, params, project_path):
        self.project_path = project_path
        # Other path users (upload, screenshot, PDF) must not become download sinks.
        self.destination = params.get("path") if params.get("op") in (
            "click", "press_key", "evaluate", "type") else None
        self.download_index = 0
        self.before_tab = self.session.active_tab_id


    def page_hooks(self, page, tab_id):
        self.urls[tab_id] = page.url
        page.on("download", lambda download: self.download(download, tab_id))
        page.on("filechooser", lambda chooser: self.record(
            "file_chooser", tab_id=tab_id, multiple=chooser.is_multiple(),
            hint="upload_file의 ref/selector와 path로 파일을 명시하세요."))
        page.on("pageerror", lambda error: self.page_error(error, tab_id))
        page.on("close", lambda: self.closed(page, tab_id))
        page.on("framenavigated", lambda frame: self.navigated(page, frame, tab_id))

    def page_error(self, error, tab_id):
        row = self.record("page_errors", tab_id=tab_id, message=str(error))
        self.session._console_logs.append({
            "type": "error", "source": "pageerror", "text": str(error),
            "tab_id": tab_id, "timestamp": row["timestamp"]})

    def closed(self, page, tab_id):
        if self.session._pages.get(tab_id) is not page:
            return
        self.record("closed_tabs", tab_id=tab_id, url=page.url)
        self.session._pages.pop(tab_id, None)
        self.urls.pop(tab_id, None)
        if self.session._active_tab_id == tab_id:
            self.session._active_tab_id = next(reversed(self.session._pages), "")
            self.session._active_frame = None
            self.session.clear_refs()

    def response(self, response):
        # Bind status to this frame's actual document response, never a same-URL old log.
        try:
            request = response.request
            if request.is_navigation_request():
                self.responses[request.frame] = {"url": response.url, "status": response.status}
        except Exception:
            pass  # Early requests may not expose a frame yet; do not invent a status.

    def navigated(self, page, frame, tab_id):
        response = self.responses.pop(frame, None)
        if frame is page.main_frame:
            row = self.record("navigated", tab_id=tab_id,
                              from_url=self.urls.get(tab_id), url=frame.url)
            self.urls[tab_id] = frame.url
            if response and response["url"] == frame.url:
                row["status_code"] = response["status"]

    def download(self, download, tab_id):
        self.download_index += 1
        row = self.record("downloads", tab_id=tab_id, url=download.url,
                          suggested_filename=download.suggested_filename, saved=False)
        # Filename is untrusted server input; only its basename enters the default path.
        name = download.suggested_filename.replace("\\", "/").split("/")[-1]
        name = name if name not in ("", ".", "..") else "download.bin"
        raw = self.destination
        if raw and self.download_index > 1:
            path = Path(raw)
            raw = str(path.with_name(f"{path.stem}_{self.download_index}{path.suffix}"))
        raw = raw or f"outputs/browser_downloads/{uuid.uuid4().hex}/{name}"
        task = asyncio.create_task(self.save(download, row, raw, self.project_path))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        self.downloads.append(row)

    async def save(self, download, row, raw, project_path):
        temporary = None
        try:
            resolved = await asyncio.to_thread(
                ToolContext(project_path, "browser_op").resolve_output_path, raw)
            if resolved.get("error"):
                raise ValueError(resolved["error"])
            path = Path(resolved["path"])
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.part")
            await asyncio.wait_for(download.save_as(str(temporary)), timeout=30)
            size = await asyncio.to_thread(lambda: temporary.stat().st_size)
            await asyncio.to_thread(os.replace, temporary, path)
            row.update(saved=True, path=str(path), size=size)
        except asyncio.CancelledError:
            row.update(error="내려받기 저장이 취소되었습니다.")
            raise
        except Exception as exc:
            row.update(error=str(exc))
        finally:
            if temporary is not None:
                try:
                    await asyncio.to_thread(temporary.unlink, missing_ok=True)
                except OSError as exc:
                    row["cleanup_error"] = str(exc)

    async def finish(self, result, *, settle=False):
        if settle:
            # Bounded grace for browser IPC (not an assertion that the page is idle).
            await asyncio.sleep(0.08)
        else:
            await asyncio.sleep(0)
        deadline = asyncio.get_running_loop().time() + 30
        while self.tasks:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                await self.cancel_downloads()
                break
            await asyncio.wait(list(self.tasks), timeout=remaining)
        session = self.session
        rows = list(self.pending)
        self.pending.clear()
        for row in rows:
            kind = row["kind"]
            item = {key: value for key, value in row.items() if key != "kind"}
            if kind == "opened_tabs":
                page = session.get_tab_page(item["tab_id"])
                if page is not None:
                    item["url"] = page.url
            result.setdefault(kind, []).append(item)
        if result.get("error_code") == "TARGET_CLOSED_DURING_ACTION" and any(
            row["kind"] == "closed_tabs" and row.get("tab_id") == self.before_tab for row in rows
        ):
            # Report the observed close, not an invented completed key-up or business success.
            result.pop("error_code", None)
            result.pop("error", None)
            result.update(success=True, verification="page_closed_during_input", input_completed=False,
                          warning="입력 도중 대상 탭이 닫혔습니다. 전체 키 입력 완료는 확인하지 못했으며 남은 탭에서 결과를 확인하세요.")
        if rows or self.before_tab != session.active_tab_id:
            result["active_tab"] = session.active_tab_id
            result["event_scope"] = "pending_and_during_operation"
        if self.before_tab != session.active_tab_id:
            result["active_tab_changed"] = {"from": self.before_tab, "to": session.active_tab_id}
        if self.dropped:
            result["events_omitted"] = self.dropped
            self.dropped = 0
        if any(not row.get("saved") for row in result.get("downloads", [])):
            result.update(success=False, error_code="DOWNLOAD_NOT_SAVED",
                          error="내려받기가 시작됐으나 저장되지 않았습니다. downloads의 오류를 확인하세요.")
        self.destination = None
        return result

    async def cancel_downloads(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
