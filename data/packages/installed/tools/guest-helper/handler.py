"""guest-helper handler — USB 손발 발급([self:limb]) + 조작([limbs:guestpc]).

표준 ToolContext 시그니처 + _OP_DISPATCHERS (--check 삼각 검증 대상).

두뇌는 허브, 손발은 얇다. guestpc_op 는 허브에서 실행되며 셸 봉투를 phone_jobs 큐에 넣고
(대상 손발 device_id) wait_result 로 결과를 동기 대기한다 — 손발(Go 헬퍼)이 /limb/poll
롱폴로 당겨가 그 PC 에서 실행 후 /limb/result 로 회신. IBL 엔진이 없는 손발은 IBL 을 모르므로
큐엔 IBL 이 아니라 셸 봉투 JSON 을 싣는다.

limb_op 는 자격 원장(limb_keys.py)을 다루고, issue 는 USB 에 담을 페이로드를 만든다.
백엔드 모듈(limb_keys/phone_jobs/device_registry/public_face)은 지연 임포트 — 이 핸들러는
백엔드 프로세스 안에서만 실행되고, --check 는 AST 라 임포트하지 않는다.
"""
import json
import os
import re
import shutil
import time

_OP_DISPATCHERS = {
    "guestpc_op": {
        "shell": None,
        "read": None,
        "write": None,
        "list": None,
        "info": None,
        "detach": None,
    },
    "limb_op": {
        "issue": None,
        "list": None,
        "revoke": None,
        "approve": None,
    },
}
_OP_DEFAULTS = {"guestpc_op": "shell", "limb_op": "issue"}


# === [limbs:guestpc] — 손발 조작 ===

def _resolve_limb(target: str):
    """대상 손발을 해소. 반환 (device_id, alias, err).

    ★자동승인 체제의 오배송 방어가 여기 산다: 승인 게이트가 없으므로, 명령이 엉뚱한 PC
    에서 돌지 않게 하는 유일한 장치가 '이름 명시'다. target(별칭·device_id) 명시 우선.
    미지정이면 라이브 손발이 **딱 하나일 때만** 그것을 쓴다 — 둘 이상이면(유출된 키로
    낯선 PC 가 하나 더 붙은 경우 포함) 이름을 강제하고 목록을 보여준다. 그 강제 자체가
    '어? 손발이 둘이네?' 하고 유출을 알아채는 신호가 된다."""
    import device_registry as dr
    import limb_keys
    live = dr.live_with_capability(limb_keys.GUEST_PC_CLASS)
    if target:
        for e in live:
            if e.get("device_id") == target or e.get("alias") == target:
                return e.get("device_id"), e.get("alias"), None
        # 라이브가 아니어도 원장에 있으면 오프라인 안내
        return None, None, f"'{target}' 손발이 지금 연결돼 있지 않습니다."
    if not live:
        return None, None, "연결된 손발이 없습니다. USB 헬퍼를 그 PC 에서 실행하세요([self:limb]{op:issue}로 발급)."
    if len(live) > 1:
        names = ", ".join(e.get("alias", "?") for e in live)
        return None, None, f"손발이 여럿 연결돼 있습니다({names}). limb 로 대상 이름을 지정하세요."
    return live[0].get("device_id"), live[0].get("alias"), None


# === 손발 콘솔 서사(note) — AI 가 뭘 하는지 헬퍼 창에 찍기 ===

_NOTE_SENT = {}   # device_id -> (task_id, ts) — 같은 작업의 시작 서사를 한 번만


def _notify_limb(device_id: str, text: str):
    """헬퍼 콘솔에 서사 한 줄({op:note, text}) — fire-and-forget(결과 안 기다림).
    옛 헬퍼 바이너리는 unknown_op 로 조용히 무시하므로 혼합 버전에도 안전."""
    try:
        import phone_jobs
        phone_jobs.enqueue(device_id, json.dumps({"op": "note", "text": text}, ensure_ascii=False))
    except Exception:
        pass


def _task_start_note(device_id: str):
    """작업 시작 서사 — 현재 태스크의 원 요청("p0 시스템 상태 알아봐")을 그 손발 창에
    한 번만 알린다. 이후 개별 명령은 헬퍼의 로컬 에코(◀/└)가 생중계하므로, 여긴 '왜'만.

    best-effort: task_id 없으면(예: claude_code 재진입 스레드의 task 전파 유실 — 별도
    수정 진행 중) 조용히 생략 — 로컬 에코는 그와 무관하게 항상 찍힌다."""
    try:
        from thread_context import get_current_task_id
        tid = get_current_task_id()
        if not tid:
            return
        prev = _NOTE_SENT.get(device_id)
        now = time.time()
        if prev and prev[0] == tid and now - prev[1] < 600:
            return
        req = ""
        try:
            from system_ai_memory import get_task
            t = get_task(tid) or {}
            req = (t.get("original_request") or "").strip()
        except Exception:
            pass
        _NOTE_SENT[device_id] = (tid, now)
        _notify_limb(device_id, f'AI 작업: "{req[:120]}"' if req else "AI 작업 시작")
    except Exception:
        pass


def _detach(tool_input: dict) -> dict:
    """손발 해제 — 헬퍼에 exit 봉투를 보내 그 PC 의 헬퍼를 종료시킨다.

    로밍 사용(휴대 USB 로 PC 를 옮겨 다님)의 '볼일 끝' 동작. 헬퍼가 종료되면 그 PC 는
    더는 명령을 당겨가지 않는다(그 PC 엔 아무것도 남지 않음). 자동승인 체제라, 그 PC 에서
    헬퍼를 **다시 실행하면** 또 자동으로 붙는다 — detach 는 '지금 이 세션 끝'이지 영구
    차단이 아니다. 영구 차단(유출·이탈)은 [self:limb]{op:revoke} 로 키를 폐기한다.
    헬퍼가 이미 닫혀 있으면(오프라인) 할 일이 없다.
    """
    import phone_jobs
    target = tool_input.get("limb") or tool_input.get("target")
    device_id, alias, err = _resolve_limb(target)

    if not device_id:
        return {"success": False, "error": err}

    job_id = phone_jobs.enqueue(device_id, json.dumps({"op": "exit"}, ensure_ascii=False))
    result = phone_jobs.wait_result(job_id, timeout=12.0)
    exited = result is not None
    return {"success": True, "op": "detach", "limb": device_id, "limb_name": alias,
            "helper_exited": exited,
            "message": (f"손발 '{alias}' 을(를) 해제했습니다 — 그 PC 의 헬퍼가 종료됐습니다. "
                        "그 PC 엔 아무것도 남지 않습니다. (다시 쓰려면 그 PC 에서 헬퍼를 재실행하면 "
                        "자동으로 붙습니다. 영구 차단은 [self:limb]{op:revoke}.)") if exited else
                       f"손발 '{alias}' 에 해제 명령을 보냈지만 응답이 없습니다(이미 닫혔을 수 있음)."}


def _guestpc(tool_input: dict) -> dict:
    import phone_jobs
    op = (tool_input.get("op") or _OP_DEFAULTS["guestpc_op"]).strip()
    if op == "detach":
        return _detach(tool_input)
    device_id, alias, err = _resolve_limb(tool_input.get("limb") or tool_input.get("target"))
    if err:
        return {"success": False, "error": err}

    _task_start_note(device_id)   # 작업 시작 서사(원 요청)를 그 손발 창에 — 한 번만
    envelope = {"op": op}
    wait = 30.0
    if op == "shell":
        cmd = tool_input.get("cmd") or ""
        if not cmd.strip():
            return {"success": False, "error": "shell 엔 cmd 가 필요합니다."}
        envelope["cmd"] = cmd
        if tool_input.get("cwd"):
            envelope["cwd"] = tool_input["cwd"]
        to = int(tool_input.get("timeout") or 120)
        envelope["timeout"] = to
        wait = float(to) + 25.0        # 명령 실행시간 + 왕복 여유
    elif op in ("read", "list"):
        envelope["path"] = tool_input.get("path") or ""
    elif op == "write":
        if not tool_input.get("path"):
            return {"success": False, "error": "write 엔 path 가 필요합니다."}
        envelope["path"] = tool_input["path"]
        envelope["content"] = tool_input.get("content") or ""
    elif op == "info":
        pass
    else:
        return {"success": False, "error": f"알 수 없는 op '{op}'. 사용 가능: shell/read/write/list/info"}

    job_id = phone_jobs.enqueue(device_id, json.dumps(envelope, ensure_ascii=False))
    result = phone_jobs.wait_result(job_id, timeout=wait)
    if result is None:
        return {"success": False, "queued": True,
                "message": f"손발 '{alias}' 이(가) 응답하지 않습니다(오프라인이거나 명령이 오래 걸림). 헬퍼 창이 떠 있는지 확인하세요."}
    # limb_name 을 항상 실어 어느 PC 에서 돌았는지 결과에 명시(오배송 사후 인지).
    return {"success": True, "limb": device_id, "limb_name": alias, "result": result}


# === [self:limb] — 손발 자격 원장 ===

_SAFE = re.compile(r"[^0-9A-Za-z가-힣_-]+")


def _hub_address():
    """헬퍼가 /limb/* 로 백엔드에 직접 닿을 주소. Worker CDN 은 /h·/s 등만 프록시하므로
    /limb/* 는 **직접 서빙 호스트(direct_hosts)** 로 가야 한다 — public_base 가 Worker 도메인인
    배포에서도 깨지지 않도록 direct host 를 우선한다. 반환 (주소, 경고)."""
    try:
        import public_face
        cfg = public_face.load_config()
    except Exception:
        return "", "공개 주소 설정을 읽지 못했습니다."
    base = (cfg.get("public_base") or "").rstrip("/")
    directs = [h for h in (cfg.get("direct_hosts") or []) if h]
    host = base.split("://")[-1].split("/")[0].split(":")[0] if base else ""
    if host and host in [d.split(":")[0] for d in directs]:
        return base, None                       # public_base 가 곧 direct host — 정본이자 직결
    if directs:
        return "https://" + directs[0].split(":")[0], None
    if base:
        return base, "public_base 가 직접 서빙 호스트가 아닐 수 있습니다 — Worker 프록시는 /limb/ 를 지원하지 않습니다. 터널 직결 호스트를 확인하세요."
    return "", "공개 주소(터널/얼굴)가 없습니다. 먼저 발급해야 손발이 허브에 닿습니다."


def _issue_root() -> str:
    """USB 페이로드·헬퍼 dist 의 루트. limb_keys(backend/..)에서 얻는다 — 핸들러 위치에서
    dirname 을 세면 패키지 깊이가 바뀔 때 조용히 어긋난다(실제로 data/ 를 루트로 잡던 버그)."""
    import limb_keys
    base_path = os.environ.get("INDIEBIZ_BASE_PATH")
    return base_path if base_path else os.path.dirname(
        os.path.dirname(os.path.abspath(limb_keys.__file__)))


def _issue_parent() -> str:
    return os.path.join(_issue_root(), "outputs", "limb_issue")


def _payload_dir_for(alias: str, device_id: str = "") -> str:
    """손발의 USB 페이로드 폴더 경로. 폴더명 = 정제된 alias(없으면 device_id)."""
    safe = _SAFE.sub("_", alias or "") or device_id
    return os.path.join(_issue_parent(), safe)


def _remove_payload(rec: dict) -> bool:
    """폐기된 손발의 USB 페이로드 폴더 삭제 — 조종간에서 제거하면 디스크에도 안 남게(누적 방지).

    폴더는 alias 로 명명돼 같은 이름의 여러 키가 공유할 수 있으므로, **같은 폴더를 쓰는
    다른 미폐기 키가 남아 있으면 보존**한다. 삭제는 outputs/limb_issue 하위로만 제한(경로 이탈 방어).
    """
    import limb_keys
    alias = rec.get("alias") or ""
    device_id = rec.get("device_id") or ""
    safe = _SAFE.sub("_", alias) or device_id
    if not safe:
        return False
    # 같은 폴더(safe)를 쓰는 다른 미폐기 키가 있으면 보존
    for k in limb_keys.list_keys(include_revoked=False):
        if k.get("device_id") == device_id:
            continue
        other_safe = _SAFE.sub("_", k.get("alias") or "") or k.get("device_id")
        if other_safe == safe:
            return False
    parent = _issue_parent()
    path = os.path.join(parent, safe)
    # 안전판: 실제로 limb_issue 하위이고 디렉토리일 때만
    if os.path.isdir(path) and \
            os.path.abspath(path).startswith(os.path.abspath(parent) + os.sep):
        shutil.rmtree(path, ignore_errors=True)
        return not os.path.exists(path)
    return False


def _issue(tool_input: dict) -> dict:
    import limb_keys
    base, addr_warn = _hub_address()

    alias = (tool_input.get("alias") or "").strip()
    ttl = tool_input.get("ttl_days")
    ttl = float(ttl) if ttl is not None else limb_keys.DEFAULT_TTL_DAYS
    minted = limb_keys.mint(alias, ttl_days=ttl)

    # USB 페이로드 폴더 — <루트>/outputs/limb_issue/<alias>/
    root = _issue_root()
    payload_dir = _payload_dir_for(minted["alias"], minted["device_id"])
    os.makedirs(payload_dir, exist_ok=True)

    cfg = {"base": base, "key": minted["key"], "alias": minted["alias"]}
    with open(os.path.join(payload_dir, "indiebiz-helper.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    # 실행파일 동봉 — os 생략 시 빌드된 전 OS 를 모두 담는다(휴대 USB: 어느 PC 를
    # 만날지 미리 모름). os 지정 시 그 OS 것만.
    target_os = (tool_input.get("os") or "").strip().lower()
    bin_map = {
        "win": ["indiebiz-helper-win.exe"], "windows": ["indiebiz-helper-win.exe"],
        "mac": ["indiebiz-helper-mac-arm64", "indiebiz-helper-mac-amd64"],
        "macos": ["indiebiz-helper-mac-arm64", "indiebiz-helper-mac-amd64"],
        "darwin": ["indiebiz-helper-mac-arm64", "indiebiz-helper-mac-amd64"],
        "linux": ["indiebiz-helper-linux"],
    }
    dist_dir = os.path.join(root, "helper", "dist")
    if target_os in bin_map:
        wanted = bin_map[target_os]
    else:                                       # 생략(기본)=전부
        wanted = sorted(set(n for ns in bin_map.values() for n in ns))
    copied = []
    for name in wanted:
        src = os.path.join(dist_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(payload_dir, name))
            copied.append(name)

    # 안내문
    readme = _issue_readme(minted, base, copied)
    with open(os.path.join(payload_dir, "사용법.txt"), "w", encoding="utf-8") as f:
        f.write(readme)

    return {
        "success": True,
        "op": "issue",
        "alias": minted["alias"],
        "device_id": minted["device_id"],
        "key_hint": minted["key"][:10] + "…",
        "address": base,
        "expires_at": minted["expires_at"],
        "payload_dir": payload_dir,
        "binary_included": copied,
        "note": "이 폴더를 USB 에 복사 → 그 PC 에서 헬퍼 실행. 첫 접속 후 [self:limb]{op:approve}로 승인하세요.",
        "warning": addr_warn or (None if copied else
                                 "helper/dist 에 빌드된 실행파일이 없어 키·안내문만 동봉했습니다. helper/build.sh 로 빌드하세요."),
    }


def _issue_readme(minted: dict, base: str, copied) -> str:
    exp = minted.get("expires_at")
    exp_s = time.strftime("%Y-%m-%d %H:%M", time.localtime(exp)) if exp else "무기한"
    if copied:
        run_line = ("그 PC 의 OS 에 맞는 실행파일을 실행하세요:\n"
                    "     윈도우      → indiebiz-helper-win.exe (더블클릭)\n"
                    "     맥(M1~)     → indiebiz-helper-mac-arm64\n"
                    "     맥(인텔)    → indiebiz-helper-mac-amd64\n"
                    "     리눅스      → indiebiz-helper-linux")
    else:
        run_line = "헬퍼 실행파일(indiebiz-helper)을 이 폴더에 함께 두고 실행하세요."
    return (
        "indiebiz 손발(USB 헬퍼) 사용법\n"
        "================================\n\n"
        f"손발 이름 : {minted['alias']}\n"
        f"내 몸 주소 : {base or '(미설정 — 터널 발급 필요)'}\n"
        f"유효기간   : {exp_s}\n\n"
        "1) 이 폴더 전체를 USB 에 복사합니다.\n"
        f"2) 일을 시킬 PC 에 USB 를 꽂고, {run_line}\n"
        "   (indiebiz-helper.json 이 실행파일과 같은 폴더에 있어야 합니다.)\n"
        "   · 맥/리눅스에서 더블클릭이 안 되면 터미널에서:  chmod +x 실행파일 && ./실행파일\n"
        "     (USB(FAT/exFAT)에서는 실행 권한이 빠질 수 있습니다.)\n"
        "3) 헬퍼가 붙으면 바로 쓸 수 있습니다(자동 연결). 폰/런처에서\n"
        f"   '{minted['alias']} 에서 ○○ 해줘' 라고 이름을 붙여 명령하면 그 PC 에서 실행됩니다.\n"
        "4) 볼일이 끝나면 '그 PC 손발 해제해줘' 또는 그 PC 에서 창 닫기.\n"
        "   그 PC 에는 아무것도 남지 않습니다.\n\n"
        "· 명령할 땐 손발 이름을 붙이세요 — 여러 PC 를 붙였을 때 엉뚱한 PC 로 가지 않게 하는\n"
        "  안전장치입니다(손발이 둘 이상이면 이름이 없으면 실행되지 않습니다).\n"
        "· 창을 닫으면 손발이 떨어집니다. USB 를 뽑아도 됩니다. 다시 실행하면 자동으로 붙습니다.\n"
        "· 잃어버리면 허브에서 [self:limb]{op:revoke} 로 이 키만 폐기하세요(영구 차단).\n"
        "· 이 파일의 키는 허브 비밀번호가 아니며, 이 손발 하나만 인가합니다.\n"
    )


def _limb(tool_input: dict) -> dict:
    import limb_keys
    op = (tool_input.get("op") or _OP_DEFAULTS["limb_op"]).strip()
    if op == "issue":
        return _issue(tool_input)
    if op == "list":
        import device_registry as dr
        live_ids = {e.get("device_id") for e in dr.live_with_capability(limb_keys.GUEST_PC_CLASS)}
        rows = limb_keys.list_keys()
        for r in rows:
            r["connected"] = r["device_id"] in live_ids
        return {"success": True, "op": "list", "limbs": rows,
                "connected_count": len(live_ids)}
    if op == "revoke":
        target = tool_input.get("target") or tool_input.get("key") or tool_input.get("device_id")
        if not target:
            return {"success": False, "error": "revoke 엔 target(키·device_id·별칭)이 필요합니다."}
        r = limb_keys.revoke(target)
        if not r:
            return {"success": False, "error": f"'{target}' 손발을 찾을 수 없습니다."}
        removed = _remove_payload(r)   # 폐기 시 USB 페이로드 폴더도 삭제(누적 방지)
        return {"success": True, "op": "revoke", "limb": r, "payload_removed": removed}
    if op == "approve":
        target = tool_input.get("target") or tool_input.get("device_id") or tool_input.get("alias")
        if not target:
            return {"success": False, "error": "approve 엔 target(키·device_id·별칭)이 필요합니다."}
        approved = tool_input.get("approved")
        approved = True if approved is None else bool(approved)
        r = limb_keys.approve(target, approved=approved)
        if not r:
            return {"success": False, "error": f"'{target}' 손발을 찾을 수 없습니다."}
        return {"success": True, "op": "approve", "limb": r}
    return {"success": False, "error": f"알 수 없는 op '{op}'. 사용 가능: issue/list/revoke/approve"}


# === 엔트리포인트 ===

def execute(tool_input: dict, context) -> dict:
    """ToolContext 표준 시그니처. guestpc_op(손발 조작) + limb_op(자격 원장) 디스패처."""
    tool_name = context.tool_name
    if tool_name == "guestpc_op":
        return _guestpc(tool_input)
    if tool_name == "limb_op":
        return _limb(tool_input)
    raise ValueError(f"Unknown tool: {tool_name}")
