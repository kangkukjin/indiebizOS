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

# _OP_DISPATCHERS(진짜 함수 참조 테이블)·_OP_DEFAULTS 는 함수 정의 뒤, 파일 하단.


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
    if target:
        registered = [r for r in limb_keys.list_keys() if r.get("registration") and
                      (target == r["device_id"] or (target == r["alias"] and not r.get("revoked")
                       and r["registration"]["state"] != "removed"))]
        if len(registered) == 1:
            r = registered[0]
            return r["device_id"], r["alias"], None
        if len(registered) > 1:
            return None, None, "PC 이름이 중복입니다. device_id를 지정하세요."
    live = dr.live_with_capability(limb_keys.GUEST_PC_CLASS)
    if target:
        for e in live:
            if e.get("device_id") == target or e.get("alias") == target:
                return e.get("device_id"), e.get("alias"), None
        # 라이브가 아니어도 원장에 있으면 오프라인 안내
        return None, None, f"'{target}' 손발이 지금 연결돼 있지 않습니다."
    if not live:
        return None, None, "연결된 손발이 없습니다. 조종실 손발 (USB) 또는 [self:limb]{op:register}로 공용 폴더를 준비하고 대상 PC에서 헬퍼를 실행해 등록하세요."
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
        import limb_keys
        if (limb_keys.get_by_device(device_id) or {}).get("registration"):
            return
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

    import limb_keys
    if (limb_keys.get_by_device(device_id) or {}).get("registration"):
        return {"success": False, "error": "상주 PC는 작업 후 detach하지 않습니다. 새 작업 일시 중지는 self:limb pause, 등록 해제·헬퍼 제거는 명시적으로 self:limb remove를 사용하세요."}
    job_id = phone_jobs.enqueue(device_id, json.dumps({"op": "exit"}, ensure_ascii=False))
    result = phone_jobs.wait_result(job_id, timeout=12.0)
    exited = result is not None
    return {"success": True, "op": "detach", "limb": device_id, "limb_name": alias,
            "helper_exited": exited,
            "message": (f"손발 '{alias}' 을(를) 해제했습니다 — 그 PC 의 헬퍼가 종료됐습니다. "
                        "그 PC 엔 아무것도 남지 않습니다. (다시 쓰려면 그 PC 에서 헬퍼를 재실행하면 "
                        "자동으로 붙습니다. 영구 차단은 [self:limb]{op:revoke}.)") if exited else
                       f"손발 '{alias}' 에 해제 명령을 보냈지만 응답이 없습니다(이미 닫혔을 수 있음)."}


# === 화면 캡처(눈) — 결과 후처리 ===

_SCREEN_KEEP = 20   # 손발당 보관할 캡처 장수(디스크 무한 증식 방지)


def _screens_dir(alias: str, device_id: str) -> str:
    safe = _SAFE.sub("_", alias or "") or device_id or "unknown"
    return os.path.join(_issue_root(), "outputs", "limb_screens", safe)


def _prune_screens(folder: str):
    """오래된 캡처 정리 — 최근 _SCREEN_KEEP 장만 남긴다."""
    try:
        shots = sorted(
            (os.path.join(folder, n) for n in os.listdir(folder)
             if n.startswith("screen_")),
            key=os.path.getmtime, reverse=True)
        for p in shots[_SCREEN_KEEP:]:
            os.remove(p)
    except Exception:
        pass


def _finish_visual(result: dict, device_id: str, alias: str, op: str) -> dict:
    """그림이 실린 결과(screen, 그리고 재캡처를 동반한 입력 op)를 마무리한다:
    (1) 허브 파일로 저장하고 (2) image_data 봉투로 싣는다.

    두 갈래인 이유: 봉투는 execute_tool 의 이미지 관문이 수확해 **모델의 눈**으로 가고
    (base64 는 본문에서 제거된다), 파일은 이미지를 못 보는 경로(claude_code 등)와 사람이
    나중에 확인할 감사 흔적으로 남는다. 봉투만 있으면 흔적이 안 남고, 파일만 있으면
    모델이 못 본다."""
    b64 = result.get("b64") or ""
    meta = {k: result.get(k) for k in
            ("width", "height", "orig_width", "orig_height", "bytes", "tool", "did", "image_observation", "warning")
            if result.get(k) is not None}

    if not b64:
        if op == "screen":
            return {"success": False, "op": op, "limb": device_id, "limb_name": alias,
                    "error": result.get("message") or result.get("error") or "캡처 결과가 비었습니다.",
                    "hint": "그 PC 에 화면 접근 권한이 없거나(맥=화면 기록) 그래픽 세션이 아닐 수 있습니다."}
        # 입력 op 는 조작 자체가 본론이고 그림은 덤 — 실패했어도 조작 성공은 성공이다.
        if result.get("error"):
            return {"success": False, "op": op, "limb": device_id, "limb_name": alias,
                    "error": result.get("message") or result["error"]}
        return {"success": True, "op": op, "limb": device_id, "limb_name": alias,
                **meta, "shot": False,
                "note": result.get("shot_error") or "조작은 됐지만 화면 재확인은 없습니다(shot:false 이거나 캡처 실패).",
                "next": "결과를 눈으로 확인하려면 [limbs:guestpc]{op:\"screen\"} 을 부르세요."}

    media = result.get("media_type") or "image/png"
    ext = "jpg" if "jpeg" in media else "png"
    path = ""
    try:
        import base64 as _b64
        folder = _screens_dir(alias, device_id)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"screen_{time.strftime('%Y%m%d_%H%M%S')}.{ext}")
        with open(path, "wb") as f:
            f.write(_b64.b64decode(b64))
        _prune_screens(folder)
    except Exception as e:
        path = f"(저장 실패: {e})"

    img_meta = {k: v for k, v in meta.items() if k != "did"}
    return {
        "success": True, "op": op, "limb": device_id, "limb_name": alias,
        "path": path, **meta,
        # ★이 키가 이미지 관문(system_tools._pluck_image_envelopes)의 계약이다.
        "image_data": {"b64": b64, "media_type": media, "path": path, **img_meta},
    }


# === 입력 주입(손) — 봉투 구성 ===

_INPUT_OPS = ("click", "move", "type", "key", "scroll", "drag")


def _copy_shot_keys(tool_input: dict, envelope: dict) -> None:
    """캡처 화질·재캡처 옵션 전달 — screen 과 입력 op 가 공유한다.

    ★키를 하나씩 `tool_input.get("리터럴")` 로 적는 이유: 빌드의 코퍼스-param 가드가
    핸들러를 AST 로 읽어 '선언한 파라미터를 핸들러가 정말 읽는지' 대조한다. 키 목록을
    상수 튜플로 접고 루프를 돌면 코드는 짧아지지만 그 검증이 통과가 아니라 **무력화**된다
    (실제로 max_width 가 조용히 미검증으로 빠져 가드에 걸렸다)."""
    for k, v in (
        ("max_width", tool_input.get("max_width")),
        ("format", tool_input.get("format")),
        ("quality", tool_input.get("quality")),
        ("display", tool_input.get("limit") or tool_input.get("display")),
        ("shot", tool_input.get("shot")),
        ("settle_ms", tool_input.get("settle_ms")),
    ):
        if v is not None:
            envelope[k] = v


def _as_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _fill_input_envelope(op: str, tool_input: dict, envelope: dict):
    """입력 봉투를 채운다. 반환 = 오류 메시지(정상이면 None).

    ★좌표를 여기서 **엄격히 검증**하는 이유: 좌표가 빠지거나 문자열이면 헬퍼는 (0,0)으로
    해석해 화면 왼쪽 위 구석을 누른다 — 조용히 엉뚱한 것을 클릭하는 게 가장 나쁜 실패다.
    빠졌으면 실행하지 않고 되묻는다."""
    if op in ("click", "move", "drag"):
        x, y = _as_int(tool_input.get("x")), _as_int(tool_input.get("y"))
        if x is None or y is None:
            return (f"{op} 엔 x·y 가 필요합니다 — 좌표는 **직전 screen 이 보낸 이미지 위의 좌표**입니다. "
                    "먼저 [limbs:guestpc]{op:\"screen\"} 으로 화면을 보고 누를 지점을 정하세요.")
        envelope["x"], envelope["y"] = x, y

    if op == "drag":
        x2, y2 = _as_int(tool_input.get("x2")), _as_int(tool_input.get("y2"))
        if x2 is None or y2 is None:
            return "drag 엔 도착점 x2·y2 가 필요합니다(출발점은 x·y)."
        envelope["x2"], envelope["y2"] = x2, y2

    if op == "click":
        btn = (tool_input.get("button") or "left").strip().lower()
        if btn not in ("left", "right", "middle"):
            return f"button 은 left/right/middle 중 하나여야 합니다(받은 값: {btn})."
        envelope["button"] = btn
        clicks = _as_int(tool_input.get("clicks")) or 1
        envelope["clicks"] = max(1, min(3, clicks))

    if op == "type":
        text = tool_input.get("text")
        if not text:
            return "type 엔 text 가 필요합니다."
        envelope["text"] = str(text)

    if op == "key":
        key = (tool_input.get("key") or "").strip()
        if not key:
            return "key 가 필요합니다(예: return, escape, tab, cmd+s, ctrl+c)."
        envelope["key"] = key

    if op == "scroll":
        direction = (tool_input.get("direction") or "down").strip().lower()
        if direction not in ("up", "down", "left", "right"):
            return f"direction 은 up/down/left/right 중 하나여야 합니다(받은 값: {direction})."
        envelope["direction"] = direction
        envelope["amount"] = max(1, min(50, _as_int(tool_input.get("amount")) or 5))
        for k in ("x", "y"):   # 스크롤 위치 지정은 선택
            v = _as_int(tool_input.get(k))
            if v is not None:
                envelope[k] = v
    return None


# 동기 대기 상한(초) — MCP 층(/ibl/execute urllib timeout 120s)보다 확실히 아래.
# 이걸 넘기면 호출자는 불투명한 {"error":"timed out"} 을 받는다(에피소드 852 실측) —
# 그보다 일찍 우리가 job_id 를 실어 정직하게 돌려주는 게 낫다.
_SYNC_WAIT_CAP = 100.0


def _job_result(tool_input: dict) -> dict:
    """op=result — 백그라운드/시간초과 셸 명령의 결과를 job_id 로 회수.

    결과는 헬퍼가 회신한 뒤 phone_jobs 에 RESULT_TTL(7일)간 보존되고, 회수는 1회(pop)다.
    아직 없으면 pending — 명령이 그 PC 에서 계속 실행 중일 수 있다."""
    import phone_jobs
    job_id = (tool_input.get("job") or tool_input.get("job_id") or "").strip()
    if not job_id:
        return {"success": False, "error": "result 엔 job(작업 ID)이 필요합니다 — shell 응답의 job_id 를 넣으세요."}
    result = phone_jobs.wait_result(job_id, timeout=float(tool_input.get("wait") or 5.0))
    if result is None:
        status = task_status({"kind": "guestpc", "task_id": job_id})
        return {**status, "op": "result", "job_id": job_id,
                "pending": status["state"] in {"queued", "running"}}
    return _execution_response(result, op="result", job_id=job_id)


def _execution_response(result, **metadata):
    """회신 수신과 원격 명령 성공을 구분하고 실패 원문·재관측 참조를 보존한다."""
    import task_receipts
    failed = bool(result.get("success") is False or result.get("exit_code") not in (None, 0) or result.get("error") or result.get("timeout") or result.get("cancelled")
                  or result.get("unknown") or result.get("exit", 0) != 0)
    out = {**metadata, "success": not failed, "result": result}
    if metadata.get("job_id"):
        out["task_ref"] = task_receipts.ref(TASK_KIND, metadata["job_id"])
    if failed:
        out["error"] = result.get("error") or "원격 작업 실패 또는 결과 미확인"
        out["details"] = {"execution_result": result, **metadata,
                          "task_ref": out.get("task_ref")}
    return out


def _guestpc_begin(tool_input: dict):
    """공용 전처리 — 대상 손발 해소 + 작업 시작 서사. 반환 (device_id, alias, 오류dict|None).

    (detach/result 를 제외한 모든 guestpc op 가 공유. 오류면 그 dict 를 그대로 반환하면 된다.)"""
    device_id, alias, err = _resolve_limb(tool_input.get("limb") or tool_input.get("target"))
    if err:
        return None, None, {"success": False, "error": err}
    _task_start_note(device_id)   # 작업 시작 서사(원 요청)를 그 손발 창에 — 한 번만
    return device_id, alias, None


def _send_wait(tool_input: dict, device_id: str, alias: str, op: str,
               envelope: dict, wait: float) -> dict:
    """공용 후처리 — 봉투 enqueue → (셸 백그라운드 단락) → 동기 대기 → 결과 마무리."""
    import phone_jobs
    import limb_keys
    resident = bool((limb_keys.get_by_device(device_id) or {}).get("registration"))
    if resident:
        import resident_pcs
        try:
            envelope.update({k: tool_input[k] for k in ("mode", "env") if k in tool_input})
            receipt = resident_pcs.submit(device_id, envelope, tool_input.get("request_id"))
        except (ValueError, PermissionError) as exc:
            return {"success": False, "error": str(exc)}
        if tool_input.get("background"):
            return receipt
        job_id = receipt["job_id"]
    else:
        if tool_input.get("mode") == "observe":
            return {"success": False, "error": "mode:observe는 상주 PC 헬퍼에서만 지원합니다"}
        job_id = phone_jobs.enqueue(device_id, json.dumps(envelope, ensure_ascii=False))

    # 백그라운드 모드(설치·빌드 등 오래 걸리는 셸) — 즉시 job_id 반환, 결과는 op=result 로.
    if bool(tool_input.get("background")) and op == "shell":
        import task_receipts
        # ③ 공통 접수증 — [self:task]{op: wait, ref: $r.task_ref} 가 읽는다. 옛 op=result(1회 pop)도 그대로.
        return task_receipts.receipt(TASK_KIND, job_id, state=task_receipts.QUEUED, op="shell", background=True,
                                     limb=device_id, limb_name=alias, job_id=job_id,
                                     message=(f"손발 '{alias}' 에서 백그라운드로 실행 중입니다. 결과는 "
                                              f'[self:task]{{op: "wait", ref: $r.task_ref}} 또는 '
                                              f'[limbs:guestpc]{{op: "result", job: "{job_id}"}} 로 확인하세요.'))

    if resident:
        import resident_store
        result = resident_store.wait_result(job_id, timeout=wait)
    else:
        result = phone_jobs.wait_result(job_id, timeout=wait)
    if result is None:
        if op == "screen":
            import task_receipts
            cancelled = (resident_store.cancel(job_id) if resident
                         else phone_jobs.cancel_pending(job_id))
            return {"success": False, "accepted": True, "job_id": job_id,
                    "task_ref": task_receipts.ref(TASK_KIND, job_id),
                    "cancel_requested": cancelled, "timed_out": True,
                    "message": "화면 대기가 끝나 촬영 취소를 요청했습니다. 이미 시작했거나 완료했을 수 있으니 "
                               "같은 task_ref로 self:task status/wait를 확인하세요. 취소 확인 전 재접수하지 마세요."}
        # ★실패 단정 금지: 명령은 그 PC 에서 계속 실행 중일 수 있다(오프라인과 구별 불가).
        #   같은 명령 재전송은 이중 실행 위험 — job_id 로 결과를 회수하는 게 정도(正道).
        import task_receipts
        observation = task_status(task_receipts.ref(TASK_KIND, job_id))
        pending = observation["state"] in task_receipts.LIVE
        return {**observation, "success": (op in {"shell", "python"} and pending)
                                         or observation["state"] == task_receipts.SUCCEEDED,
                "queued": observation["state"] == task_receipts.QUEUED,
                "accepted": True, "job_id": job_id, "limb": device_id, "limb_name": alias,
                "helper_mode": "resident" if resident else "portable", "op": op,
                "timed_out": pending,
                "task_observation": observation,
                "message": (f"손발 '{alias}' 의 응답을 {wait:.0f}초 안에 못 받았습니다 — 명령이 오래 걸리는 "
                            f"중이거나(설치·빌드 등) 손발이 오프라인입니다. ★같은 명령을 다시 보내지 말고 "
                            f'[self:task]{{op: "wait", ref: {{kind: "guestpc", task_id: "{job_id}"}}}} 로 결과를 확인하세요. '
                            f'포기하려면 같은 task_ref로 self:task cancel을 요청하고 종료를 확인하세요. '
                            f'오래 걸릴 명령은 처음부터 background: true 로 보내는 게 좋습니다.')}
    if op == "screen" or op in _INPUT_OPS:
        return _finish_visual(result, device_id, alias, op)
    out = _execution_response(result, limb=device_id, limb_name=alias, job_id=job_id,
                              helper_mode="resident" if resident else "portable", op=op)
    if op == "read" and result.get("truncated"):
        out["warning"] = ('원격 read 크기 제한입니다. 상주 PC는 transfer action:"receive" 후 '
                          'collect로 파일을 가져오세요. read에는 offset·limit 인자가 없습니다.')
    return out


def _op_shell(tool_input: dict) -> dict:
    device_id, alias, err = _guestpc_begin(tool_input)
    if err:
        return err
    envelope = {"op": "shell"}
    cmd = tool_input.get("cmd") or ""
    if not cmd.strip():
        return {"success": False, "error": "shell 엔 cmd 가 필요합니다."}
    envelope["cmd"] = cmd
    if "elevate" in tool_input:
        if type(tool_input["elevate"]) is not bool:
            return {"success": False, "error": "elevate는 true/false여야 합니다."}
        envelope["elevate"] = tool_input["elevate"]
    if tool_input.get("cwd"):
        envelope["cwd"] = tool_input["cwd"]
    if tool_input.get("stdin"):
        envelope["stdin"] = str(tool_input["stdin"])
    if tool_input.get("reset"):
        envelope["reset"] = True
    shell_kind = (tool_input.get("shell") or "").strip().lower()
    if shell_kind:
        if shell_kind not in ("cmd", "powershell", "pwsh", "ps", "sh"):
            return {"success": False,
                    "error": f"shell 은 cmd/powershell 중 하나여야 합니다(받은 값: {shell_kind}). "
                             "윈도우에서만 의미가 있습니다."}
        envelope["shell"] = shell_kind
    # 헬퍼가 이 시간에 명령을 죽인다. 백그라운드 모드의 기본은 넉넉히(30분) —
    # 명시 120s 기본을 그대로 두면 설치·빌드가 헬퍼 쪽에서 잘린다.
    background = bool(tool_input.get("background"))
    to = tool_input.get("timeout")
    import limb_keys
    resident = bool((limb_keys.get_by_device(device_id) or {}).get("registration"))
    if envelope.get("elevate") and not resident:
        return {"success": False, "error": "관리자 인증은 상주 헬퍼에서 지원합니다."}
    if to is None and resident and tool_input.get("request_id"):
        import resident_pcs
        import resident_store
        previous = resident_store.find_request(resident_pcs.resolve(device_id), tool_input["request_id"])
        if previous:
            # Preserve defaults captured before upgrade when recovering an old request.
            to = previous["summary"].get("timeout")
    reg = (limb_keys.get_by_device(device_id) or {}).get("registration") or {}
    phone = reg.get("adapter") == "indiebiz-v1"
    to = (to if to is not None else 120) if phone else (int(to) if to else (1800 if background or resident else 120))
    for key in ("env", "mode"):
        if key in tool_input:
            envelope[key] = tool_input[key]
    envelope["timeout"] = to
    if phone:
        for key in ("inputs", "code", "reset", "stdin", "cwd", "shell"):
            if key in tool_input:
                envelope[key] = tool_input[key]
    # 명령 실행시간 + 왕복 여유 — 단, MCP 층이 120s 에 먼저 끊으므로 상한을 둔다.
    wait = min(float(to) + 25.0, _SYNC_WAIT_CAP)
    return _send_wait(tool_input, device_id, alias, "shell", envelope, wait)


def _op_python(tool_input: dict) -> dict:
    """Explicit embedded runtime; never translate this into a different machine's shell."""
    device_id, alias, err = _guestpc_begin(tool_input)
    if err:
        return err
    import limb_keys
    reg = (limb_keys.get_by_device(device_id) or {}).get("registration") or {}
    if reg.get("adapter") != "indiebiz-v1":
        return {"success": False, "error": "embedded_python_requires_registered_phone"}
    from phone_execution_contract import validate
    envelope = {"op": "python"}
    for key in ("code", "inputs", "cwd", "timeout", "mode", "env", "stdin", "shell", "reset", "elevate", "cmd"):
        if key in tool_input:
            envelope[key] = tool_input[key]
    try:
        envelope = validate(envelope)
    except (ValueError, TypeError) as error:
        return {"success": False, "error": str(error)}
    return _send_wait(tool_input, device_id, alias, "python", envelope,
                      min(envelope["timeout"] + 25.0, _SYNC_WAIT_CAP))


def _op_ibl(tool_input: dict) -> dict:
    """op=ibl — IndieBiz OS 손발(폰 등)에 IBL 을 하달해 **그 몸의 사전**으로 돌린다 (2026-10-13).

    헬퍼(Go) 손발은 IBL 엔진이 없으므로 adapter=indiebiz-v1 등록에만 허용한다(허브 submit 도 같은
    관문). 결과는 IBL 통화 그대로 result 에 — 실패 봉투(success:false)는 실패로 투영한다.
    설계: docs/INDIEBIZ_BODY_AS_LIMB_DESIGN_2026_10_13.md"""
    device_id, alias, err = _guestpc_begin(tool_input)
    if err:
        return err
    code = (tool_input.get("code") or "").strip()
    if not code:
        return {"success": False, "error": "ibl 엔 code(그 몸에서 실행할 IBL)가 필요합니다."}
    import limb_keys
    reg = (limb_keys.get_by_device(device_id) or {}).get("registration") or {}
    if reg.get("adapter") != "indiebiz-v1":
        return {"success": False,
                "error": f"'{alias}' 은(는) IndieBiz OS 손발이 아닙니다(헬퍼 PC) — IBL 대신 shell 을 쓰세요."}
    to = tool_input.get("timeout")
    try:
        to = int(to) if to else 300
    except (TypeError, ValueError):
        to = 300
    envelope = {"op": "ibl", "ibl": code, "timeout": to}
    wait = min(float(to) + 25.0, _SYNC_WAIT_CAP)
    out = _send_wait(tool_input, device_id, alias, "ibl", envelope, wait)
    inner = out.get("result") if isinstance(out, dict) else None
    if out.get("success") and isinstance(inner, dict) and inner.get("success") is False:
        out = {**out, "success": False,
               "error": inner.get("error") or inner.get("message") or "그 몸이 IBL 실행을 거절했습니다"}
    return out


def _op_read(tool_input: dict) -> dict:
    device_id, alias, err = _guestpc_begin(tool_input)
    if err:
        return err
    envelope = {"op": "read", "path": tool_input.get("path") or ""}
    return _send_wait(tool_input, device_id, alias, "read", envelope, 30.0)


def _op_list(tool_input: dict) -> dict:
    device_id, alias, err = _guestpc_begin(tool_input)
    if err:
        return err
    envelope = {"op": "list", "path": tool_input.get("path") or ""}
    return _send_wait(tool_input, device_id, alias, "list", envelope, 30.0)


def _op_write(tool_input: dict) -> dict:
    device_id, alias, err = _guestpc_begin(tool_input)
    if err:
        return err
    if not tool_input.get("path"):
        return {"success": False, "error": "write 엔 path 가 필요합니다."}
    envelope = {"op": "write", "path": tool_input["path"],
                "content": tool_input.get("content") or ""}
    return _send_wait(tool_input, device_id, alias, "write", envelope, 30.0)


def _op_info(tool_input: dict) -> dict:
    device_id, alias, err = _guestpc_begin(tool_input)
    if err:
        return err
    return _send_wait(tool_input, device_id, alias, "info", {"op": "info"}, 30.0)


def _op_screen(tool_input: dict) -> dict:
    device_id, alias, err = _guestpc_begin(tool_input)
    if err:
        return err
    # 캡처는 인코딩·전송이 있어 파일 op 보다 굼뜨다 — 넉넉히 준다.
    envelope = {"op": "screen"}
    _copy_shot_keys(tool_input, envelope)
    return _send_wait(tool_input, device_id, alias, "screen", envelope, 60.0)


def _op_input(op: str, tool_input: dict) -> dict:
    """입력 op(click/move/type/key/scroll/drag) 공통 흐름 — 좌표 검증 + 재캡처 옵션."""
    device_id, alias, err = _guestpc_begin(tool_input)
    if err:
        return err
    envelope = {"op": op}
    msg = _fill_input_envelope(op, tool_input, envelope)
    if msg:
        return {"success": False, "error": msg}
    _copy_shot_keys(tool_input, envelope)   # 재캡처 화질 옵션도 함께
    return _send_wait(tool_input, device_id, alias, op, envelope, 60.0)


def _op_click(tool_input: dict) -> dict:
    return _op_input("click", tool_input)


def _op_move(tool_input: dict) -> dict:
    return _op_input("move", tool_input)


def _op_type(tool_input: dict) -> dict:
    return _op_input("type", tool_input)


def _op_key(tool_input: dict) -> dict:
    return _op_input("key", tool_input)


def _op_scroll(tool_input: dict) -> dict:
    return _op_input("scroll", tool_input)


def _op_drag(tool_input: dict) -> dict:
    return _op_input("drag", tool_input)


# === [self:limb] — 손발 자격 원장 ===

_SAFE = re.compile(r"[^0-9A-Za-z가-힣_-]+")


def _hub_address():
    """헬퍼가 /limb/* 로 백엔드에 직접 닿을 주소. Worker CDN 은 /h·/s 등만 프록시하므로
    /limb/* 는 **직접 서빙 호스트(direct_hosts)** 로 가야 한다 — public_base 가 Worker 도메인인
    배포에서도 깨지지 않도록 direct host 를 우선한다. 반환 (주소, 경고)."""
    try:
        import face_config
        cfg = face_config.load_config()
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
    """USB 페이로드와 dist는 런타임 루트 기준. backend 층별 파일 깊이에 의존하지 않는다."""
    from runtime_utils import get_base_path
    return str(get_base_path())


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
    # 회원 열쇠(2026-09-14): neighbor_id 가 오면 기존 이웃에 기기를 결합(새 이웃 생성 금지).
    neighbor_id = tool_input.get("neighbor_id")
    link = None
    if neighbor_id not in (None, ""):
        from body_trust import link_body
        minted = limb_keys.mint(alias, ttl_days=ttl, neighbor_id=int(neighbor_id))
        link = link_body(minted["device_id"], int(neighbor_id))
        if not link.get("linked"):
            limb_keys.revoke(minted["device_id"])
            return {"success": False, "op": "issue", "error": link.get("error")}
    else:
        minted = limb_keys.mint(alias, ttl_days=ttl)

    # USB 페이로드 폴더 — <루트>/outputs/limb_issue/<alias>/
    root = _issue_root()
    payload_dir = _payload_dir_for(minted["alias"], minted["device_id"])
    os.makedirs(payload_dir, exist_ok=True)

    cfg = {"base": base, "key": minted["key"], "alias": minted["alias"],
           "mode": "member" if neighbor_id not in (None, "") else "limb"}
    with open(os.path.join(payload_dir, "indiebiz-helper.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    # 실행파일 동봉 — os 생략 시 빌드된 전 OS 를 모두 담는다(휴대 USB: 어느 PC 를
    # 만날지 미리 모름). os 지정 시 그 OS 것만.
    target_os = (tool_input.get("os") or "").strip().lower()
    bin_map = {
        "win": ["indiebiz-helper-win.exe"], "windows": ["indiebiz-helper-win.exe"],
        "mac": ["indiebiz-helper-mac-arm64", "indiebiz-helper-mac-amd64",
                  "indiebiz-helper-mac-amd64-legacy"],
        "macos": ["indiebiz-helper-mac-arm64", "indiebiz-helper-mac-amd64",
                  "indiebiz-helper-mac-amd64-legacy"],
        "darwin": ["indiebiz-helper-mac-arm64", "indiebiz-helper-mac-amd64",
                  "indiebiz-helper-mac-amd64-legacy"],
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
        "member": link,
        "note": ("회원 열쇠 — 이 폴더를 그 사람에게 주면 헬퍼가 /m/chat 을 그 사람 주체·레벨로 엽니다."
                 if link else
                 "이 폴더를 USB 에 복사 → 그 PC 에서 헬퍼 실행. 첫 접속 후 [self:limb]{op:approve}로 승인하세요."),
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
                    "     맥(인텔)    → indiebiz-helper-mac-amd64 (macOS 12 이상)\n"
                    "     맥(인텔, macOS 11 이하 — Catalina 10.15 등)\n"
                    "                 → indiebiz-helper-mac-amd64-legacy\n"
                    "       ('Symbol not found: _SecTrustCopyCertificateChain' 으로 꺼지면 이쪽)\n"
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
        "   · 맥에서 '확인되지 않은 개발자'로 막히면:  xattr -d com.apple.quarantine 실행파일\n"
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


def _limb_list(tool_input: dict) -> dict:
    import limb_keys
    import device_registry as dr
    live_ids = {e.get("device_id") for e in dr.live_with_capability(limb_keys.GUEST_PC_CLASS)}
    rows = [r for r in limb_keys.list_keys() if not r.get("invitation")]
    for r in rows:
        r["connected"] = r["device_id"] in live_ids
        if not r.get("registration"):
            payload_dir = _payload_dir_for(r.get("alias", ""), r["device_id"])
            r["payload_dir"] = payload_dir if os.path.isdir(payload_dir) else None
        # 접속 때 수확한 환경 프로브 요약 — 어떤 PC 인지 왕복 없이 알아보게.
        # 전체(PATH·도구 목록까지)는 [limbs:guestpc]{op:"info"} 로 다시 물으면 된다.
        env = r.get("env") or {}
        if env:
            r["env"] = {k: env.get(k) for k in
                        ("os", "os_version", "hostname", "user", "admin", "gui")
                        if env.get(k) is not None}
    # items 병행 방출 — self:agents(d74461b)·self:switch(8a6aacd)와 같은 이유·같은 방식.
    # `limbs` 만 내면 `>> [table:*]` 가 "items 통화를 찾지 못했습니다"로 끊긴다.
    return {"success": True, "op": "list", "limbs": rows, "items": rows,
            "connected_count": len(live_ids),
            "helper_dist_dir": os.path.join(_issue_root(), "helper", "dist"),
            "issue_parent_dir": _issue_parent()}


def _limb_revoke(tool_input: dict) -> dict:
    import limb_keys
    target = tool_input.get("target") or tool_input.get("key") or tool_input.get("device_id")
    if not target:
        return {"success": False, "error": "revoke 엔 target(키·device_id·별칭)이 필요합니다."}
    r = limb_keys.revoke(target)
    if not r:
        return {"success": False, "error": f"'{target}' 손발을 찾을 수 없습니다."}
    removed = _remove_payload(r)   # 폐기 시 USB 페이로드 폴더도 삭제(누적 방지)
    return {"success": True, "op": "revoke", "limb": r, "payload_removed": removed}


def _limb_approve(tool_input: dict) -> dict:
    import limb_keys
    target = tool_input.get("target") or tool_input.get("device_id") or tool_input.get("alias")
    if not target:
        return {"success": False, "error": "approve 엔 target(키·device_id·별칭)이 필요합니다."}
    approved = tool_input.get("approved")
    approved = True if approved is None else bool(approved)
    r = limb_keys.approve(target, approved=approved)
    if not r:
        return {"success": False, "error": f"'{target}' 손발을 찾을 수 없습니다."}
    return {"success": True, "op": "approve", "limb": r}



def _resident_operation(tool_input):
    """상주 PC: media/wake/history/cancel/transfer. 전송은 파일 바이트를 별도 통로로 보낸다."""
    import resident_pcs
    import resident_store
    op = tool_input.get("op")
    target = tool_input.get("limb") or tool_input.get("target")
    try:
        if op == "history":
            return {"success": True, **resident_store.history(
                device=resident_pcs.resolve(target, active=False)["device_id"] if target else None,
                job=tool_input.get("job"), cursor=tool_input.get("cursor", 0))}
        if op == "cancel":
            return {"success": True, "cancel_requested": resident_store.cancel(tool_input.get("job"))}
        if op == "wake":
            if tool_input.get("mac"):
                return {"success": True, "registration": resident_pcs.configure_wake(
                    target, tool_input["mac"], tool_input["broadcast"], tool_input["relay"])}
            return resident_pcs.wake(target)
        if op == "transfer":
            return resident_pcs.transfer_local(target, tool_input)
        command = {k: v for k, v in tool_input.items() if k not in {"limb", "target", "request_id"}}
        return resident_pcs.submit(target, command, tool_input.get("request_id"))
    except (ValueError, OSError, KeyError) as exc:
        return {"success": False, "error": str(exc)}


def _resident_registration(tool_input):
    """공용 USB 폴더 준비·상주 PC 해제·일시 중지."""
    import resident_pcs
    import limb_keys
    op = tool_input.get("op")
    target = tool_input.get("target")
    try:
        if op == "register":
            return {"success": True, **resident_pcs.prepare_usb(),
                    "message": "이 폴더를 통째로 USB에 복사하세요. 대상 PC에서 맞는 헬퍼를 실행하고 이름을 정해 등록합니다. 목록·해제는 조종실의 손발 (USB)에 있습니다."}
        if op == "remove":
            return {"success": True, "registration": resident_pcs.remove(target)}
        rec = resident_pcs.resolve(target, active=False)
        return {"success": True, "registration": limb_keys.resident_update(
            rec["device_id"], paused=bool(tool_input.get("paused", True)))}
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

# === 디스패처 (진짜 함수 참조 — --check 가 이 dict 키로 src.ops.values 와 정확 비교) ===

_OP_DISPATCHERS = {
    "guestpc_op": {
        "shell": _op_shell,
        "python": _op_python,
        "ibl": _op_ibl,      # IndieBiz OS 손발(adapter=indiebiz-v1)에 IBL 하달 — 2026-10-13
        "read": _op_read,
        "write": _op_write,
        "list": _op_list,
        "info": _op_info,
        "screen": _op_screen,
        "click": _op_click,
        "move": _op_move,
        "type": _op_type,
        "key": _op_key,
        "scroll": _op_scroll,
        "drag": _op_drag,
        "result": _job_result,   # job_id 전역 조회 — 손발 해소·liveness 불요
        "detach": _detach,
        "media": _resident_operation,
        "transfer": _resident_operation,
        "wake": _resident_operation,
        "history": _resident_operation,
        "cancel": _resident_operation,
    },
    "limb_op": {
        "issue": _issue,
        "register": _resident_registration,
        "remove": _resident_registration,
        "pause": _resident_registration,
        "list": _limb_list,
        "revoke": _limb_revoke,
        "approve": _limb_approve,
    },
}
_OP_DEFAULTS = {"guestpc_op": "shell", "limb_op": "issue"}


# === 엔트리포인트 ===

def execute(tool_input: dict, context) -> dict:
    """ToolContext 표준 시그니처. guestpc_op(손발 조작) + limb_op(자격 원장) 디스패처."""
    tool_name = context.tool_name
    if tool_name in _OP_DISPATCHERS:
        op = (tool_input.get("op") or _OP_DEFAULTS.get(tool_name, "")).strip()
        fn = _OP_DISPATCHERS[tool_name].get(op)
        if fn is None:
            return {"success": False,
                    "error": f"알 수 없는 op '{op}'. 사용 가능: {'/'.join(_OP_DISPATCHERS[tool_name])}"}
        return fn(tool_input)
    raise ValueError(f"Unknown tool: {tool_name}")


# ── ③ 접수증 어댑터(kind=guestpc) — phone_jobs 를 비파괴로 읽는다(결과 pop 은 op=result 그대로) ──
TASK_KIND = "guestpc"


def task_status(ref: dict) -> dict:
    import phone_jobs
    import task_receipts as T
    jid = ref["task_id"]
    import resident_store
    history = resident_store.history(job=jid, limit=5, tail=True, include_images=True)
    if history["tasks"]:
        task = history["tasks"][0]
        state = T.FAILED if task["state"] == "expired" else task["state"]
        events = []
        for event in history["events"]:
            # Results/commands have their own fields; progress is a bounded preview.
            item = {k: event[k] for k in ("cursor", "kind", "occurred")}
            if event["kind"] in {"log", "log_gap"}:
                payload = json.dumps(event["payload"], ensure_ascii=False)
                item["preview"] = payload[-2000:]
                item["preview_truncated"] = len(payload) > 2000
            events.append(item)
        view = T.view(ref, state, result=task["result"], progress=events,
                      limb=task["device"], helper_mode="resident",
                      op=task["summary"].get("op"), request_id=task["request_id"],
                      cwd=task["summary"].get("cwd"), shell=task["summary"].get("shell"),
                      progress_scope="recent_5_events", history_cursor=history["cursor"],
                      history_args={"op": "history", "limb": task["device"], "job": jid, "cursor": 0},
                      started_at=task["started_at"], ended_at=task["ended_at"], seconds=task["seconds"],
                      outcome=task["outcome"],
                      execution_result=task["result"] if state != T.SUCCEEDED else None,
                      error=(task["result"] or {}).get("error"), accepted_at=task["created"])
        return {**view, "ended_at": task["ended_at"]}
    got = phone_jobs.peek_result(jid)
    if got is not None:
        if got.get("consumed"):
            return T.view(ref, T.SUCCEEDED, result=None, note="결과는 이미 op=result 로 회수(pop)됐습니다 — 회수한 쪽이 들고 있습니다")
        return T.view(ref, T.SUCCEEDED, result=got["result"])   # succeeded = 손발이 결과를 회신했다(내용의 성패는 result 안)
    status = phone_jobs.job_status(jid)
    state = status["state"]
    if state == "queued":
        return T.view(ref, T.QUEUED, note="접수됨 — 기기 전달 대기")
    if state == "dispatched":
        return T.view(ref, T.RUNNING, progress=phone_jobs.get_partial(jid),
                      note="기기에 전달됨 — 결과 대기")
    if state == "cancelled":
        return T.view(ref, T.CANCELLED)
    if state == "expired":
        return T.view(ref, T.FAILED, error="전달 전에 유효기간이 만료됨 — 실행하지 않음")
    return T.view(ref, T.UNKNOWN, error="실행 결과 미확인 — 같은 명령을 재전송하지 말고 기기 상태를 확인하세요")


def task_status_cancel(ref: dict) -> dict:
    """기기가 아직 가져가지 않은 작업만 되돌린다 — 실행된 것으로 추정하지 않는다."""
    import phone_jobs
    import task_receipts as T
    import resident_store
    if resident_store.history(job=ref["task_id"])["tasks"]:
        resident_store.cancel(ref["task_id"])
        return task_status(ref)
    if phone_jobs.cancel_pending(ref["task_id"]):
        return T.view(ref, T.CANCELLED)
    cur = task_status(ref)
    return {**cur, "error": "기기가 이미 가져간(또는 모르는) 작업은 취소할 수 없습니다"}
