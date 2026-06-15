"""
PC Manager 도구 핸들러
AI 에이전트가 PC Manager 창을 열고, 스토리지를 스캔/검색할 수 있게 한다

기능:
- open_file_explorer: PC Manager 파일 탐색기 창 열기
- query_storage: 파일 검색 ([self:fs_query])
- storage_op: 저장소 인덱스 조작 — scan/summary/volumes op 분기 ([self:storage])
- folder_note_op: 폴더 주석 관리 — set/get op 분기 ([self:folder_note])
"""

import os
import sys
import json

# 현재 디렉토리를 path에 추가 (storage_db 임포트용)
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)


def execute(tool_input: dict, context) -> str:
    """도구 실행 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    try:
        # PC Manager 창 열기
        if tool_name == "open_file_explorer":
            return _open_file_explorer(tool_input)

        # 파일 검색 ([self:fs_query])
        elif tool_name == "query_storage":
            return _query_storage(tool_input)

        # 저장소 인덱스 조작 ([self:storage]{op: scan|summary|volumes})
        elif tool_name == "storage_op":
            return _storage_op(tool_input)

        # 폴더 주석 관리 ([self:folder_note]{op: set|get})
        elif tool_name == "folder_note_op":
            return _folder_note_op(tool_input)

        # 호스트(자기 기계) 자기수용감각 ([sense:host]{op: status|apps|resources})
        elif tool_name == "host_op":
            return _host_op(tool_input)

        return f"알 수 없는 도구: {tool_name}"

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _open_file_explorer(tool_input: dict) -> str:
    """PC Manager 창 열기"""
    path = tool_input.get("path", None)

    try:
        from api_pcmanager import _pending_window_requests
        request_id = os.urandom(8).hex()
        _pending_window_requests.append({
            "id": request_id,
            "path": path,
        })

        if path:
            return f"PC Manager 창 열기 요청을 전송했습니다. 경로: {path}"
        else:
            return "PC Manager 창 열기 요청을 전송했습니다. (홈 디렉토리)"

    except ImportError as e:
        return f"api_pcmanager 모듈을 불러올 수 없습니다: {e}"


def _scan_storage(tool_input: dict) -> str:
    """스토리지 스캔"""
    import storage_db

    path = tool_input.get("path")
    if not path:
        return json.dumps({"success": False,
                           "error": "scan은 워크할 경로가 필요합니다 (예: [self:storage]{op:scan, path:'~/Documents'}). "
                                    "전체 볼륨 개요는 op:volumes, 용량 요약은 op:summary를 인자 없이 쓰세요."},
                          ensure_ascii=False)

    volume_name = tool_input.get("volume_name")
    result = storage_db.scan_directory(path, volume_name)

    if result["success"]:
        # scan_directory 반환 키: name/file_count/total_size_mb/error_count
        return json.dumps({
            "success": True,
            "message": f"스캔 완료: {result.get('name', path)}",
            "file_count": result.get('file_count'),
            "total_size_mb": result.get('total_size_mb'),
            "error_count": result.get('error_count'),
        }, ensure_ascii=False)
    else:
        return json.dumps(result, ensure_ascii=False)


def _annotate_folder(tool_input: dict) -> str:
    """폴더 주석 추가"""
    import storage_db

    # add_annotation(root_path, folder_path, note) — root_path로 스캔된 볼륨 DB를 찾는다.
    root_path = tool_input.get("root_path") or tool_input.get("volume_name")
    folder_path = tool_input.get("folder_path")
    note = tool_input.get("note")

    if not root_path or not folder_path or not note:
        return json.dumps({"success": False,
                           "error": "root_path(스캔된 볼륨 경로), folder_path, note가 모두 필요합니다"},
                          ensure_ascii=False)

    result = storage_db.add_annotation(root_path, folder_path, note)

    if result["success"]:
        return json.dumps({
            "success": True,
            "message": f"주석 추가됨: {folder_path}",
            "note": note
        }, ensure_ascii=False)
    else:
        return json.dumps(result, ensure_ascii=False)


def _query_storage(tool_input: dict) -> str:
    """파일 검색"""
    import storage_db

    root_path = tool_input.get("volume_name") or tool_input.get("root_path")

    # min_size_mb가 "10MB"/"1.5gb"/"500kb" 같은 문자열로 와도 숫자(MB)로 파싱.
    _raw_size = tool_input.get("min_size_mb")
    min_size_mb = _raw_size
    if isinstance(_raw_size, str):
        import re as _re
        m = _re.match(r"\s*([\d.]+)\s*([kmgt]?b?)\s*$", _raw_size.strip(), _re.I)
        if m:
            _v = float(m.group(1))
            _unit = (m.group(2) or "mb").lower()
            _factor = {"kb": 1/1024, "k": 1/1024, "mb": 1, "m": 1,
                       "gb": 1024, "g": 1024, "tb": 1024*1024, "t": 1024*1024,
                       "b": 1/(1024*1024), "": 1}.get(_unit, 1)
            min_size_mb = _v * _factor
        else:
            min_size_mb = None

    # root_path 생략 시 스캔된 전체 볼륨을 가로질러 검색.
    if not root_path:
        result = storage_db.query_files_all(
            search_term=tool_input.get("search_term"),
            extension=tool_input.get("extension"),
            min_size_mb=min_size_mb,
            limit=tool_input.get("limit", 100),
        )
    else:
        result = storage_db.query_files(
            root_path=root_path,
            search_term=tool_input.get("search_term"),
            extension=tool_input.get("extension"),
            min_size_mb=min_size_mb,
            limit=tool_input.get("limit", 100)
        )

    # table 통화(비파괴) — 파일 검색 결과를 표로. fs_query >> [engines:spreadsheet/document].
    if isinstance(result, dict):
        files = result.get("files") if isinstance(result.get("files"), list) else (
            result.get("results") if isinstance(result.get("results"), list) else None)
        if files and all(isinstance(f, dict) for f in files):
            rows = [[f.get("name") or f.get("filename") or "",
                     f.get("size_mb") or f.get("size") or "",
                     f.get("path") or f.get("full_path") or "",
                     f.get("modified") or f.get("mtime") or ""] for f in files]
            result["table"] = {"columns": ["이름", "크기(MB)", "경로", "수정일"], "rows": rows}

    return json.dumps(result, ensure_ascii=False)


def _get_storage_summary(tool_input: dict) -> str:
    """볼륨 요약"""
    import storage_db

    root_path = tool_input.get("volume_name") or tool_input.get("root_path")

    # root_path 생략 시 스캔된 전체 볼륨 통합 요약.
    if not root_path:
        result = storage_db.get_summary_all()
    else:
        result = storage_db.get_summary(root_path)

    return json.dumps(result, ensure_ascii=False)


def _list_volumes(tool_input: dict) -> str:
    """볼륨 목록"""
    import storage_db

    result = storage_db.list_volumes()
    return json.dumps(result, ensure_ascii=False)


def _get_folder_annotations(tool_input: dict) -> str:
    """폴더 주석 조회"""
    import storage_db

    root_path = tool_input.get("volume_name") or tool_input.get("root_path")

    # root_path 생략 시 전체 볼륨의 폴더 주석을 통합 조회.
    if not root_path:
        result = storage_db.get_annotations_all()
    else:
        result = storage_db.get_annotations(root_path)

    return json.dumps(result, ensure_ascii=False)


# ── op 디스패처 (2026-06-03 #29 storage/folder 통합) ──────────────
# 값은 None — 분기 로직은 _storage_op/_folder_note_op 함수 안에 유지.
# --check 가 이 dict 키로 src.ops.values 와 정확 비교.
_OP_DISPATCHERS = {
    "storage_op": {"scan": None, "summary": None, "volumes": None},
    "folder_note_op": {"set": None, "get": None},
    "host_op": {"status": None, "apps": None, "resources": None},
}
_OP_DEFAULTS = {"storage_op": "volumes", "folder_note_op": "get", "host_op": "status"}


# ── [sense:host] 호스트 자기수용감각 (이 기계 자신의 운영 상태) ───────────
def _host_frontmost_app() -> str:
    """현재 전면(frontmost) 앱 이름 — 권한 프롬프트 없는 best-effort (lsappinfo)."""
    try:
        import subprocess
        out = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=3)
        asn = (out.stdout or "").strip()
        if asn:
            info = subprocess.run(["lsappinfo", "info", "-only", "name", asn],
                                  capture_output=True, text=True, timeout=3)
            # 형식: "LSDisplayName"="Safari"
            line = (info.stdout or "").strip()
            if '"' in line:
                return line.rsplit('=', 1)[-1].strip().strip('"')
    except Exception:
        pass
    return ""


def _host_body_name() -> str:
    """이 몸(하드웨어) 이름 — runtime_utils.detect_body() best-effort."""
    try:
        import runtime_utils
        b = runtime_utils.detect_body()
        if isinstance(b, dict):
            return b.get("name") or b.get("model") or ""
        return str(b or "")
    except Exception:
        return ""


def _host_status(tool_input: dict) -> str:
    """[sense:host]{op:status} — 이 기계의 운영 상태 한 눈에 (자기수용감각 1샷)."""
    import psutil, time
    try:
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("/")
        try:
            la = list(psutil.getloadavg())
        except Exception:
            la = None
        bat = None
        try:
            b = psutil.sensors_battery()
            if b is not None:
                bat = {"percent": round(b.percent), "plugged": bool(b.power_plugged)}
        except Exception:
            bat = None
        uptime_h = round((time.time() - psutil.boot_time()) / 3600.0, 1)
        result = {
            "success": True,
            "body": _host_body_name() or "Mac",
            "frontmost_app": _host_frontmost_app() or None,
            "cpu_percent": psutil.cpu_percent(interval=0.3),
            "memory": {"used_gb": round(vm.used / 1e9, 1), "total_gb": round(vm.total / 1e9, 1),
                       "percent": vm.percent},
            "disk_root": {"free_gb": round(du.free / 1e9, 1), "total_gb": round(du.total / 1e9, 1),
                          "percent": du.percent},
            "battery": bat,
            "uptime_hours": uptime_h,
            "load_avg": [round(x, 2) for x in la] if la else None,
            "process_count": len(psutil.pids()),
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"host status 실패: {e}"}, ensure_ascii=False)


def _host_apps(tool_input: dict) -> str:
    """[sense:host]{op:apps} — 자원을 많이 쓰는 프로세스 상위 N (몸을 점유하는 것)."""
    import psutil
    limit = int(tool_input.get("limit") or 12)
    try:
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_percent", "cpu_percent"]):
            try:
                procs.append(p.info)
            except Exception:
                continue
        procs.sort(key=lambda x: (x.get("memory_percent") or 0), reverse=True)
        top = [{
            "pid": x.get("pid"),
            "name": x.get("name"),
            "mem_percent": round(x.get("memory_percent") or 0, 1),
            "cpu_percent": round(x.get("cpu_percent") or 0, 1),
        } for x in procs[:limit]]
        return json.dumps({"success": True, "count": len(procs), "top": top}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"host apps 실패: {e}"}, ensure_ascii=False)


def _host_resources(tool_input: dict) -> str:
    """[sense:host]{op:resources} — 상세 지표 (per-CPU·메모리·스왑·디스크 파티션·네트워크·배터리)."""
    import psutil, time
    try:
        parts = []
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
                parts.append({"mount": part.mountpoint, "fs": part.fstype,
                              "free_gb": round(u.free / 1e9, 1), "total_gb": round(u.total / 1e9, 1),
                              "percent": u.percent})
            except Exception:
                continue
        sw = psutil.swap_memory()
        vm = psutil.virtual_memory()
        net = psutil.net_io_counters()
        bat = None
        try:
            b = psutil.sensors_battery()
            if b is not None:
                bat = {"percent": round(b.percent), "plugged": bool(b.power_plugged),
                       "secs_left": (b.secsleft if b.secsleft and b.secsleft > 0 else None)}
        except Exception:
            bat = None
        result = {
            "success": True,
            "cpu": {"percent_overall": psutil.cpu_percent(interval=0.3),
                    "per_core": psutil.cpu_percent(interval=0.0, percpu=True),
                    "logical_cores": psutil.cpu_count()},
            "memory": {"used_gb": round(vm.used / 1e9, 1), "total_gb": round(vm.total / 1e9, 1),
                       "percent": vm.percent},
            "swap": {"used_gb": round(sw.used / 1e9, 1), "total_gb": round(sw.total / 1e9, 1),
                     "percent": sw.percent},
            "disks": parts,
            "network": {"sent_gb": round(net.bytes_sent / 1e9, 2), "recv_gb": round(net.bytes_recv / 1e9, 2)},
            "battery": bat,
            "uptime_hours": round((time.time() - psutil.boot_time()) / 3600.0, 1),
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"host resources 실패: {e}"}, ensure_ascii=False)


def _host_op(tool_input: dict) -> str:
    """[sense:host]{op} — status(기본)/apps/resources 단일 디스패처."""
    op = (tool_input.get("op") or _OP_DEFAULTS["host_op"]).strip()
    if op == "status":
        return _host_status(tool_input)
    elif op == "apps":
        return _host_apps(tool_input)
    elif op == "resources":
        return _host_resources(tool_input)
    return json.dumps({"success": False,
                       "error": f"알 수 없는 op '{op}'. 사용 가능: ['status', 'apps', 'resources']"},
                      ensure_ascii=False)


def _storage_op(tool_input: dict) -> str:
    """[self:storage]{op} — scan/summary/volumes 단일 디스패처."""
    op = (tool_input.get("op") or _OP_DEFAULTS["storage_op"]).strip()
    if op == "scan":
        return _scan_storage(tool_input)
    elif op == "summary":
        return _get_storage_summary(tool_input)
    elif op == "volumes":
        return _list_volumes(tool_input)
    return json.dumps({"success": False,
                       "error": f"알 수 없는 op '{op}'. 사용 가능: ['scan', 'summary', 'volumes']"},
                      ensure_ascii=False)


def _folder_note_op(tool_input: dict) -> str:
    """[self:folder_note]{op} — set(주석 추가)/get(주석 조회) 단일 디스패처."""
    op = (tool_input.get("op") or _OP_DEFAULTS["folder_note_op"]).strip()
    if op == "set":
        return _annotate_folder(tool_input)
    elif op == "get":
        return _get_folder_annotations(tool_input)
    return json.dumps({"success": False,
                       "error": f"알 수 없는 op '{op}'. 사용 가능: ['set', 'get']"},
                      ensure_ascii=False)
