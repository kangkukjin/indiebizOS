"""
PC Manager 도구 핸들러
AI 에이전트가 PC Manager 창을 열고, 스토리지를 스캔/검색할 수 있게 한다

기능:
- storage_op: 저장소 인덱스 조작 — scan/summary/volumes op 분기 ([self:storage])
- folder_note_op: 폴더 주석 관리 — set/detail op 분기 ([self:folder_note])
(구 query_storage([self:fs_query])는 2026-08-05 어휘 압축으로 system_essentials 의
 [self:file_find] 메타 검색 모드에 흡수 — 파일 찾기는 한 개념, 기제는 어휘가 아니다.)
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
        # open_file_explorer([limbs:explorer])는 2026-08-15 은퇴 — [limbs:open_window]{app:"files"} 로 흡수.
        # op 보유 도구 — storage/folder_note/forage/host
        # (_OP_DISPATCHERS 는 함수 정의 뒤, 파일 하단)
        if tool_name in _OP_DISPATCHERS:
            op = (tool_input.get("op") or _OP_DEFAULTS.get(tool_name, "")).strip()
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if fn is None:
                return _unknown_op(tool_name, op)
            return fn(tool_input)

        return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _unknown_op(tool_name: str, op: str) -> str:
    """옛 if/elif 체인의 도구별 '알 수 없는 op' 응답 문구 그대로."""
    if tool_name == "forage_op":
        return json.dumps({"success": False, "error": f"알 수 없는 op: {op}"}, ensure_ascii=False)
    return json.dumps({"success": False,
                       "error": f"알 수 없는 op '{op}'. 사용 가능: {list(_OP_DISPATCHERS[tool_name])}"},
                      ensure_ascii=False)


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


def _parse_min_size_mb(raw) -> "float | None":
    """min_size_mb 가 "10MB"/"1.5gb"/"500kb" 문자열로 와도 숫자(MB)로 파싱."""
    if not isinstance(raw, str):
        return raw
    import re as _re
    m = _re.match(r"\s*([\d.]+)\s*([kmgt]?b?)\s*$", raw.strip(), _re.I)
    if not m:
        return None
    _factor = {"kb": 1/1024, "k": 1/1024, "mb": 1, "m": 1,
               "gb": 1024, "g": 1024, "tb": 1024*1024, "t": 1024*1024,
               "b": 1/(1024*1024), "": 1}.get((m.group(2) or "mb").lower(), 1)
    return float(m.group(1)) * _factor


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
    # 통화 병기 (V13-1, 2026-08-19 상상훈련 13회차): volumes 키만으로는 어떤 table
    # 변환자도 뒤에 못 붙는다(sort/take 굶음 실측). title=칸 규약, 원 필드 보존.
    if isinstance(result, dict) and isinstance(result.get("volumes"), list):
        items = [{"title": v.get("name") or v.get("root_path"), **v}
                 for v in result["volumes"] if isinstance(v, dict)]
        result["items"] = items
        result["count"] = len(items)
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


# [self:residual] 은 2026-08-15 은퇴 — 등록 스크립트 "잔여추정"([self:script]{op:run, id:"잔여추정"})으로 대체.
# (순수 측정 산술이라 어휘 자격 없음 — 결정화 사다리의 스크립트 가로대가 정위치.)


# ── [self:forage] 포식 기억 — 냄새지도 (backend/forage_memory 위임) ──────────
def _detect_body() -> str:
    try:
        import runtime_utils
        return (runtime_utils.detect_body().get("profile") or "mac")
    except Exception:
        return "mac"


def _forage_recall(tool_input: dict) -> str:
    """[self:forage]{op:recall} — 냄새지도 회상.

    기본 = 전 공간(body 미지정 → None) — 주입 경로(cognitive_recall 의
    recall_xml(body=None))와 같은 축이다. 하드웨어 감지는 게이트지 회상 파티션이
    아니다(FORAGER_MULTIBODY_DESIGN §1 두 축 분리). 한 몸의 부피가 limit 을
    독점하는 회귀는 forage_memory 의 몸별 공정 인터리브가 막는다.
    body 명시 지정은 여전히 그 몸으로 좁힌다."""
    import forage_memory as FM
    body = tool_input.get("body") or None
    query = tool_input.get("query") or tool_input.get("q")
    try:
        limit = int(tool_input.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    res = FM.recall(body=body, query=query, limit=limit)
    res["xml"] = FM.recall_xml(body=body, query=query, limit=limit)
    return json.dumps(res, ensure_ascii=False)


def _forage_note(tool_input: dict) -> str:
    """[self:forage]{op:note} — 지도(map)/주인모델(owner) 항목 누적."""
    import forage_memory as FM
    layer = (tool_input.get("layer") or "map").strip().lower()
    prior = tool_input.get("prior_class")
    conf = tool_input.get("confidence")
    prov = tool_input.get("provenance")
    if isinstance(prov, str):
        try:
            prov = json.loads(prov)
        except (ValueError, TypeError):
            prov = {"observed": [prov]}
    if layer == "owner":
        facet = tool_input.get("facet")
        value = tool_input.get("value") or tool_input.get("claim")
        if not facet or not value:
            return json.dumps({"success": False,
                               "error": "owner note 는 facet + value 필요"}, ensure_ascii=False)
        r = FM.note_owner(facet=facet, value=value,
                          prior_class=prior or "semantic",
                          confidence=conf if conf is not None else 0.6,
                          provenance=prov)
        return json.dumps(r, ensure_ascii=False)
    # layer == map
    locus = tool_input.get("locus") or tool_input.get("folder_path")
    kind = tool_input.get("kind")
    claim = tool_input.get("claim") or tool_input.get("note")
    if not locus or not kind or not claim:
        return json.dumps({"success": False,
                           "error": "map note 는 locus + kind + claim 필요"}, ensure_ascii=False)
    r = FM.note_map(body=tool_input.get("body") or _detect_body(),
                    locus=locus, kind=kind, claim=claim,
                    prior_class=prior or "structural",
                    confidence=conf if conf is not None else 0.7,
                    provenance=prov,
                    prune_reason=tool_input.get("prune_reason"),
                    generalizes=bool(tool_input.get("generalizes")),
                    surface_flag=bool(tool_input.get("surface_flag")))
    return json.dumps(r, ensure_ascii=False)


def _forage_forget(tool_input: dict) -> str:
    """[self:forage]{op:forget} — 항목 폐기."""
    import forage_memory as FM
    entry_id = tool_input.get("id")
    if entry_id is None:
        return json.dumps({"success": False, "error": "forget 은 id 필요"}, ensure_ascii=False)
    table = tool_input.get("table") or "forage_map"
    try:
        return json.dumps(FM.forget(entry_id=int(entry_id), table=table), ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"success": False, "error": "id 는 정수"}, ensure_ascii=False)


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
        # F8-host (2026-08-16 5회차): 스냅샷 1행 items 병기(quote 선례 동형) — 없으면
        # `[sense:host] & [sense:stock]…>> union` 류 병렬 결합이 통화 층에서 막힌다.
        # 중첩(memory/disk)은 평평한 수치 칸으로 펴서 행에 담는다(파이프가 물 수 있게).
        result["items"] = [{
            "title": result["body"],                      # 칸 규약 1
            "cpu_percent": result["cpu_percent"],
            "memory_percent": vm.percent,
            "memory_used_gb": round(vm.used / 1e9, 1),
            "disk_percent": du.percent,
            "disk_free_gb": round(du.free / 1e9, 1),
            "battery_percent": (bat or {}).get("percent"),
            "uptime_hours": uptime_h,
            "process_count": result["process_count"],
        }]
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
        # 통화 병기 (V13-1 스윕, 2026-08-19): top=주 페이로드 목록 — items 병기로
        # table 변환자 접속 개통(title=칸 규약, 원 필드·top 키 보존).
        items = [{"title": x.get("name"), **x} for x in top]
        return json.dumps({"success": True, "count": len(procs), "top": top,
                           "items": items}, ensure_ascii=False)
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
            # ★V15-1 판정(2026-08-20 사용자): 봉투의 통화 = 디스크 파티션 행들 — "디스크
            # 여유공간"은 분석된 볼륨(storage 도메인)이 아니라 지금 마운트된 파일시스템의
            # 현재 상태(host 영토)다. disks 와 같은 객체를 병기해 파이프가 흐르게 한다
            # ([sense:host]{op:"resources"} >> [table:filter]{where:"percent > 90"}) —
            # 변환 시 disks 는 동일성 재투영(_mirrored)이 자동 동행, CPU·메모리 축은
            # dict 라 자백 대상도 아니어서 봉투 의미 불변.
            "items": parts,
            "network": {"sent_gb": round(net.bytes_sent / 1e9, 2), "recv_gb": round(net.bytes_recv / 1e9, 2)},
            "battery": bat,
            "uptime_hours": round((time.time() - psutil.boot_time()) / 3600.0, 1),
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"host resources 실패: {e}"}, ensure_ascii=False)


# ── op 디스패처 (2026-06-03 #29 storage/folder 통합 → 2026-08-05 진짜 함수 참조) ──
# --check 가 이 dict 키로 src.ops.values 와 정확 비교.
_OP_DISPATCHERS = {
    "storage_op": {"scan": _scan_storage, "summary": _get_storage_summary,
                   "volumes": _list_volumes},
    "folder_note_op": {"set": _annotate_folder, "detail": _get_folder_annotations},
    "host_op": {"status": _host_status, "apps": _host_apps,
                "resources": _host_resources},
    "forage_op": {"recall": _forage_recall, "note": _forage_note,
                  "forget": _forage_forget},
}
_OP_DEFAULTS = {"storage_op": "volumes", "folder_note_op": "detail", "host_op": "status",
                "forage_op": "recall"}
