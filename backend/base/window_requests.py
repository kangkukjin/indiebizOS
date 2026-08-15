"""내장 도구 창(PC Manager 파일 / Photo Manager 사진) 열기 요청 큐.

Electron 프론트엔드가 폴링(`/pcmanager/pending-windows`·`/photo/pending-windows`)해
큐에 쌓인 요청을 회수하고 해당 창을 연다. 생산자는 두 갈래:
  - surface: api_pcmanager·api_photo 의 POST /open-window
  - ibl: ibl_routing `_execute_launcher_command` 의 open_window{app: files|photos}

층 가드(아래층이 위층을 import 금지) 때문에 큐를 base 층으로 내린 단일 저장소 —
ibl_routing 이 surface 모듈을 직접 import 하던 것의 의존 역전 (2026-08-15).
"""
import os

_QUEUES: dict[str, list] = {"files": [], "photos": []}


def request_window(kind: str, path=None) -> dict:
    """창 열기 요청을 큐에 적재. kind = 'files' | 'photos'."""
    req = {"id": os.urandom(8).hex(), "path": path}
    _QUEUES[kind].append(req)
    return req


def drain(kind: str) -> list:
    """대기 중인 요청 전부 회수 후 비움 (프론트엔드 폴링용)."""
    items = list(_QUEUES[kind])
    _QUEUES[kind].clear()
    return items
