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
            ("width", "height", "orig_width", "orig_height", "bytes", "tool", "did")
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
        ("display", tool_input.get("display")),
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

    결과는 헬퍼가 회신한 뒤 phone_jobs 에 RESULT_TTL(5분)간 보존되고, 회수는 1회(pop)다.
    아직 없으면 pending — 명령이 그 PC 에서 계속 실행 중일 수 있다."""
    import phone_jobs
    job_id = (tool_input.get("job") or tool_input.get("job_id") or "").strip()
    if not job_id:
        return {"success": False, "error": "result 엔 job(작업 ID)이 필요합니다 — shell 응답의 job_id 를 넣으세요."}
    result = phone_jobs.wait_result(job_id, timeout=float(tool_input.get("wait") or 5.0))
    if result is None:
        # 중간 경과가 있으면 함께 준다 — '돌고 있음'과 '멎었음'을 구별하게 하는 유일한 단서다.
        # 이게 없으면 AI 가 판단 못 해 같은 명령을 재전송(이중 실행)하기 쉽다.
        partial = phone_jobs.get_partial(job_id)
        out = {"success": False, "op": "result", "job_id": job_id, "pending": True,
               "message": ("아직 결과가 없습니다 — 명령이 그 PC 에서 실행 중이면 잠시 후 같은 op 로 "
                           "다시 확인하세요. (완료 후 5분이 지났거나 백엔드가 재시작됐으면 결과가 유실된 것 — "
                           "상태 확인 명령을 새로 보내세요.)")}
        if partial:
            out["progress"] = partial          # {tail, bytes, running}
            out["message"] = (f"실행 중입니다(출력 {partial.get('bytes', 0)}바이트까지 나옴). "
                              "아래 progress.tail 이 지금까지의 출력 꼬리입니다. "
                              "진행이 멈춘 것 같으면 잠시 후 다시 확인하세요.")
        return out
    return {"success": True, "op": "result", "job_id": job_id, "result": result}


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
    job_id = phone_jobs.enqueue(device_id, json.dumps(envelope, ensure_ascii=False))

    # 백그라운드 모드(설치·빌드 등 오래 걸리는 셸) — 즉시 job_id 반환, 결과는 op=result 로.
    if bool(tool_input.get("background")) and op == "shell":
        return {"success": True, "op": "shell", "background": True,
                "limb": device_id, "limb_name": alias, "job_id": job_id,
                "message": (f"손발 '{alias}' 에서 백그라운드로 실행 중입니다. 결과는 "
                            f'[limbs:guestpc]{{op: "result", job: "{job_id}"}} 로 확인하세요.')}

    result = phone_jobs.wait_result(job_id, timeout=wait)
    if result is None:
        # ★실패 단정 금지: 명령은 그 PC 에서 계속 실행 중일 수 있다(오프라인과 구별 불가).
        #   같은 명령 재전송은 이중 실행 위험 — job_id 로 결과를 회수하는 게 정도(正道).
        return {"success": False, "queued": True, "job_id": job_id,
                "message": (f"손발 '{alias}' 의 응답을 {wait:.0f}초 안에 못 받았습니다 — 명령이 오래 걸리는 "
                            f"중이거나(설치·빌드 등) 손발이 오프라인입니다. ★같은 명령을 다시 보내지 말고 "
                            f'[limbs:guestpc]{{op: "result", job: "{job_id}"}} 로 결과를 확인하세요. '
                            f'오래 걸릴 명령은 처음부터 background: true 로 보내는 게 좋습니다.')}
    if op == "screen" or op in _INPUT_OPS:
        return _finish_visual(result, device_id, alias, op)
    # limb_name 을 항상 실어 어느 PC 에서 돌았는지 결과에 명시(오배송 사후 인지).
    return {"success": True, "limb": device_id, "limb_name": alias, "result": result}


def _op_shell(tool_input: dict) -> dict:
    device_id, alias, err = _guestpc_begin(tool_input)
    if err:
        return err
    envelope = {"op": "shell"}
    cmd = tool_input.get("cmd") or ""
    if not cmd.strip():
        return {"success": False, "error": "shell 엔 cmd 가 필요합니다."}
    envelope["cmd"] = cmd
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
    to = int(to) if to else (1800 if background else 120)
    envelope["timeout"] = to
    # 명령 실행시간 + 왕복 여유 — 단, MCP 층이 120s 에 먼저 끊으므로 상한을 둔다.
    wait = min(float(to) + 25.0, _SYNC_WAIT_CAP)
    return _send_wait(tool_input, device_id, alias, "shell", envelope, wait)


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


def _limb_list(tool_input: dict) -> dict:
    import limb_keys
    import device_registry as dr
    live_ids = {e.get("device_id") for e in dr.live_with_capability(limb_keys.GUEST_PC_CLASS)}
    rows = limb_keys.list_keys()
    for r in rows:
        r["connected"] = r["device_id"] in live_ids
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
            "connected_count": len(live_ids)}


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


# === 디스패처 (진짜 함수 참조 — --check 가 이 dict 키로 src.ops.values 와 정확 비교) ===

_OP_DISPATCHERS = {
    "guestpc_op": {
        "shell": _op_shell,
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
    },
    "limb_op": {
        "issue": _issue,
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
