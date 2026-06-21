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

        # 포식 기억 — 냄새지도 ([self:forage]{op: recall|note|forget})
        elif tool_name == "forage_op":
            return _forage_op(tool_input)

        # 음성-단언 측정 — 탐색 잔여 ([self:residual]{op: sample|estimate})
        elif tool_name == "residual_op":
            return _residual_op(tool_input)

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


def _query_storage(tool_input: dict) -> str:
    """[self:fs_query] 파일 메타 검색 — OS 색인(file_index) 직접. 선스캔 불필요·항상 최신.

    self:photo 와 같은 backend/file_index 보편 질의 위의 얇은 preset(종류 무관).
    mdfind 어댑터를 재구현하지 않는다 — 보편 질의는 단일 출처에서 한 번만.
    """
    import file_index  # pc-manager 핸들러는 이미 runtime_utils 등 backend 모듈 import(경로 확보됨)

    min_size_mb = _parse_min_size_mb(tool_input.get("min_size_mb"))
    min_size_bytes = int(min_size_mb * 1024 * 1024) if min_size_mb else None
    try:
        limit = max(1, int(tool_input.get("limit") or 100))
    except (TypeError, ValueError):
        limit = 100

    res = file_index.query(
        kind=tool_input.get("kind") or "any",
        q=tool_input.get("search_term") or tool_input.get("q"),
        ext=tool_input.get("extension"),
        path=tool_input.get("root_path") or tool_input.get("volume_name"),
        min_size=min_size_bytes,
        limit=limit,
        sort=tool_input.get("sort") or "mtime",
    )
    if not res.get("success"):
        return json.dumps(res, ensure_ascii=False)

    items = res.get("items", [])
    records, rows = [], []
    for it in items:
        path = it.get("path") or ""
        size = it.get("size") or 0
        size_mb = round(size / 1048576, 2)
        mtime = _epoch_to_iso(it.get("mtime"))
        meta_bits = [f"{size_mb} MB", it.get("kind") or "", mtime]
        records.append({
            "title": it.get("name") or os.path.basename(path),
            "meta": " · ".join(b for b in meta_bits if b),
            "summary": "", "url": path,
            "path": path, "size": size, "size_mb": size_mb,
            "mtime": mtime, "kind": it.get("kind"), "ext": it.get("ext"),
        })
        rows.append([it.get("name") or "", size_mb, path, mtime])

    out = {
        "success": True,
        "count": res.get("count"),
        "shown": len(records),
        "scope": res.get("scope"),
        "records": records,
        # table 통화(비파괴) — fs_query >> [engines:spreadsheet/document] 호환 유지.
        "table": {"columns": ["이름", "크기(MB)", "경로", "수정일"], "rows": rows},
    }
    if res.get("fallback"):
        out["fallback"] = res["fallback"]
    return json.dumps(out, ensure_ascii=False)


def _epoch_to_iso(mtime) -> str:
    """epoch(float/int) → 'YYYY-MM-DD HH:MM' (file_index mtime 표시용)."""
    try:
        from datetime import datetime as _dt
        return _dt.fromtimestamp(float(mtime)).strftime("%Y-%m-%d %H:%M") if mtime else ""
    except (TypeError, ValueError, OSError):
        return ""


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
    "forage_op": {"recall": None, "note": None, "forget": None},
    "residual_op": {"sample": None, "estimate": None},
}
_OP_DEFAULTS = {"storage_op": "volumes", "folder_note_op": "get", "host_op": "status",
                "forage_op": "recall", "residual_op": "sample"}


# ── [self:residual] 음성-단언 측정 — 탐색 잔여(elusion 디스크판) ────────────
#   "거기 없음" vs "덜 봤음"을 *측정*으로 가른다(apparatus 아닌 측정 행위).
#   sample=미관측 더미 균일 무작위 표본 → AI가 열어 판단 / estimate=이항 추정(Wilson).
def _wilson(r: int, n: int, z: float = 1.96):
    """Wilson score 95% 신뢰구간 (r 성공/n 시행). r=0 도 정상 처리(rule-of-three 근사)."""
    import math
    if n <= 0:
        return (0.0, 0.0, 1.0)
    p = r / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (p, max(0.0, center - half), min(1.0, center + half))


def _residual_op(tool_input: dict) -> str:
    import file_index
    op = (tool_input.get("op") or _OP_DEFAULTS["residual_op"]).strip()

    if op == "sample":
        # 모집단(질의 매칭 전체) − 이미 본 것 = 미관측 → 균일 무작위 N개.
        seen = tool_input.get("seen") or []
        if isinstance(seen, str):
            seen = [seen]
        seen_set = {os.path.abspath(os.path.expanduser(str(p))) for p in seen}
        try:
            n = max(1, int(tool_input.get("n") or tool_input.get("sample") or 20))
        except (TypeError, ValueError):
            n = 20
        # 포식 공간 분기(FORAGER_MULTIBODY_DESIGN §4): code:<repo> 면 코드판 candidate provider,
        # 아니면 디스크판(mdfind/walk). body 또는 space 로 명시.
        space = str(tool_input.get("space") or tool_input.get("body") or "").lower()
        repo = tool_input.get("repo") or tool_input.get("path")
        if space.startswith("code") and repo:
            exts = tool_input.get("exts") or tool_input.get("ext") or tool_input.get("extension")
            if isinstance(exts, str):
                exts = [e for e in exts.replace(",", " ").split() if e]
            pool = file_index.code_candidate_paths(
                repo, q=tool_input.get("q") or tool_input.get("query"), exts=exts)
            facets = ()
        else:
            pool = file_index.candidate_paths(
                kind=tool_input.get("kind") or "any",
                q=tool_input.get("q") or tool_input.get("query"),
                start=tool_input.get("start"), end=tool_input.get("end"),
                ext=tool_input.get("extension") or tool_input.get("ext"),
                path=tool_input.get("path"),
                min_size=_parse_min_size_mb(tool_input.get("min_size_mb")))
            facets = ("taken_at",)
        total = len(pool)
        unseen = [p for p in pool if os.path.abspath(p) not in seen_set]
        import random
        k = min(n, len(unseen))
        picked = random.sample(unseen, k) if k > 0 else []
        sample = [file_index.describe(p, facets=facets) for p in picked]
        return json.dumps({
            "success": True, "op": "sample",
            "pool_total": total, "seen": len(seen_set), "unseen": len(unseen),
            "sample_size": k, "sample": sample,
            "note": ("이 표본을 열어 관련성을 판단한 뒤 [self:residual]{op:estimate, "
                     "relevant:<관련 수>, sampled:%d, unseen:%d} 로 미관측 누락을 추정하세요. "
                     "0건이면 '거기 없음' 단언이 강해집니다." % (k, len(unseen))),
        }, ensure_ascii=False)

    if op == "estimate":
        # (표본 중 관련 r, 표본 n, 미관측 M) → 누락 추정 + 신뢰구간.
        try:
            r = int(tool_input.get("relevant", 0))
            n = int(tool_input.get("sampled") or tool_input.get("n") or 0)
            M = int(tool_input.get("unseen") or tool_input.get("pool") or 0)
        except (TypeError, ValueError):
            return json.dumps({"success": False, "error": "relevant/sampled/unseen 는 정수"}, ensure_ascii=False)
        if n <= 0:
            return json.dumps({"success": False, "error": "sampled(n)는 1 이상"}, ensure_ascii=False)
        p, lo, hi = _wilson(r, n)
        hi_missed = round(hi * M, 1)
        # ★측정만 반환 — "없음 vs 덜봄" 판단은 AI 몫(목표 recall 대비). 도구는 숫자+해석만.
        interp = (f"미관측 {M}개 중 관련 항목이 점추정 {round(p*M,1)}개, 95% 상한 {hi_missed}개로 추정됩니다. "
                  f"상한 {hi_missed}개가 이 작업의 목표(예: '전부' 찾기/'없음' 단언)에 비해 "
                  f"작으면 사실상 커버된 것, 크면 더 봐야 합니다 — 판단은 목표에 달렸습니다.")
        return json.dumps({
            "success": True, "op": "estimate",
            "relevant_in_sample": r, "sampled": n, "unseen": M,
            "rate": round(p, 4), "rate_ci95": [round(lo, 4), round(hi, 4)],
            "missed_estimate": round(p * M, 1),
            "missed_ci95": [round(lo * M, 1), hi_missed],
            "interpretation": interp,
        }, ensure_ascii=False)

    return json.dumps({"success": False, "error": f"알 수 없는 op: {op}"}, ensure_ascii=False)


# ── [self:forage] 포식 기억 — 냄새지도 (backend/forage_memory 위임) ──────────
def _detect_body() -> str:
    try:
        import runtime_utils
        return (runtime_utils.detect_body().get("profile") or "mac")
    except Exception:
        return "mac"


def _forage_op(tool_input: dict) -> str:
    """[self:forage]{op} — recall(회상)/note(누적)/forget(폐기) 단일 디스패처."""
    import forage_memory as FM
    op = (tool_input.get("op") or _OP_DEFAULTS["forage_op"]).strip()

    if op == "recall":
        body = tool_input.get("body") or _detect_body()
        query = tool_input.get("query") or tool_input.get("q")
        try:
            limit = int(tool_input.get("limit") or 20)
        except (TypeError, ValueError):
            limit = 20
        res = FM.recall(body=body, query=query, limit=limit)
        res["xml"] = FM.recall_xml(body=body, query=query, limit=limit)
        return json.dumps(res, ensure_ascii=False)

    if op == "note":
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

    if op == "forget":
        entry_id = tool_input.get("id")
        if entry_id is None:
            return json.dumps({"success": False, "error": "forget 은 id 필요"}, ensure_ascii=False)
        table = tool_input.get("table") or "forage_map"
        try:
            return json.dumps(FM.forget(entry_id=int(entry_id), table=table), ensure_ascii=False)
        except (TypeError, ValueError):
            return json.dumps({"success": False, "error": "id 는 정수"}, ensure_ascii=False)

    return json.dumps({"success": False, "error": f"알 수 없는 op: {op}"}, ensure_ascii=False)


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
