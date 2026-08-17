"""
안드로이드 폰 화면 조작 핸들러 (얇은 센터피스)

2026-06-05 부활: 옛 45개 bespoke 액션을 폐기하고, computer-use/desktop(limbs:screen)과
같은 결의 단일 op 액션 [limbs:android]{op} 하나로 재설계.
핵심 원칙: snapshot(화면 독해)으로 요소를 읽고 → ref/좌표로 탭 (눈대중 좌표 금지).
SMS/통화/연락처 등 구조화 기능은 백업(data/packages/_archive/)에 보존, 추후 선별 부활.

표준 ToolContext 시그니처 + _OP_DISPATCHERS (radio 패턴, --check 삼각 검증 대상).
"""

import os
import sys
from pathlib import Path

_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

import ui_control as _ui


# 2026-06-05 dispatcher 표준 — src.ops.values 와 AST 정확 비교 대상.
# ★_OP_DISPATCHERS(진짜 함수 참조 테이블)·_OP_DEFAULTS 는 함수 정의 뒤, 파일 하단.


def _is_phone_profile() -> bool:
    """몸 분기 공용 헬퍼 — 집 PC=ADB+uiautomator(USB) / 폰=네이티브 AccessibilityService.

    ★INDIEBIZ_PROFILE 분기는 이 파일이 포크-가드 allowlist(iblbuild_guards
    PROFILE_BRANCH_ALLOWLIST, 이음매 아래 핸들러)에 있어 허용 — 옛 execute 의 분기를
    android_op 각 op 함수가 공유하도록 뽑아낸 것(시맨틱 동일)."""
    return os.environ.get("INDIEBIZ_PROFILE") == "phone"


def _snapshot(tool_input: dict) -> dict:
    """화면 독해 — 누를 수 있는/의미 있는 요소를 라벨+좌표로 반환 (탭 전 필수).

    limbs:screen 의 snapshot 데스크톱판. uiautomator dump → 요소를 ref 번호와 함께 제공.
    AI는 라벨을 보고 tap{query} 또는 tap{x,y} 로 누른다.
    """
    device_id = tool_input.get("device_id")
    elements = _ui._parse_ui_elements(device_id)
    if not elements:
        return {
            "success": False,
            "message": "화면 독해 실패 (uiautomator dump 비었음). 애니메이션 중이면 잠시 후 다시 snapshot.",
        }

    out = []
    for el in elements:
        label = (el.get("text") or "").strip() or (el.get("content_desc") or "").strip()
        rid = el.get("resource_id", "") or ""
        cls = el.get("class", "") or ""
        clickable = bool(el.get("clickable"))
        is_input = ("edit" in cls.lower()) or ("edit" in rid.lower())
        # 의미 없는 요소(라벨 없고 클릭 불가하고 입력칸도 아님)는 노이즈라 제외
        if not (clickable or label or is_input):
            continue
        center = el.get("center")
        if not center:
            continue
        out.append({
            "ref": len(out),
            "label": label,
            "id": rid.split("/")[-1] if rid else "",
            "class": cls,
            "clickable": clickable,
            "input": is_input,
            "x": center["x"],
            "y": center["y"],
        })

    return {
        "success": True,
        "count": len(out),
        "elements": out,
        "hint": "tap은 query(라벨/id 일부)로 누르는 게 가장 견고. 또는 위 x,y 사용. "
                "입력 후 전송류 버튼은 동적 생성되니 type 다음 반드시 snapshot 재실행.",
    }


def _swipe(tool_input: dict) -> dict:
    """방향(direction) 또는 좌표(x1,y1,x2,y2)로 스와이프/스크롤."""
    device_id = tool_input.get("device_id")
    direction = (tool_input.get("direction") or "").strip().lower()

    if direction:
        info = _ui.get_screen_info(device_id)
        if not info.get("success"):
            return info
        w, h = info.get("width", 1080), info.get("height", 2400)
        cx, cy = w // 2, h // 2
        dx, dy = int(w * 0.35), int(h * 0.35)
        # 스크롤 방향과 스와이프 방향: "down"=아래로 스크롤=손가락 위로
        moves = {
            "down": (cx, cy + dy, cx, cy - dy),
            "up": (cx, cy - dy, cx, cy + dy),
            "left": (cx + dx, cy, cx - dx, cy),
            "right": (cx - dx, cy, cx + dx, cy),
        }
        if direction not in moves:
            return {"success": False, "error": f"알 수 없는 direction '{direction}'. up/down/left/right."}
        x1, y1, x2, y2 = moves[direction]
        return _ui.swipe(x1, y1, x2, y2, tool_input.get("duration_ms", 300), device_id)

    # 좌표 기반
    try:
        x1 = int(tool_input["x1"]); y1 = int(tool_input["y1"])
        x2 = int(tool_input["x2"]); y2 = int(tool_input["y2"])
    except (KeyError, TypeError, ValueError):
        return {"success": False, "error": "swipe엔 direction(up/down/left/right) 또는 x1,y1,x2,y2 필요."}
    return _ui.swipe(x1, y1, x2, y2, tool_input.get("duration_ms", 300), device_id)


def _phone_notifications(tool_input: dict) -> dict:
    """폰 포획소 조회 ([sense:phone]{op:notifications}).

    폰의 NotificationCaptureService 가 붙잡아 둔 알림을 읽는다(USB). ★범위는 폰 화이트리스트
    (결제 앱 등 지정 앱)뿐 — 2026-06-22 에 전수 수집을 폐기하고 2026-08-17 에 범위를 좁혀
    복귀시켰다. 그러니 "폰에 온 모든 연락"의 소스가 아니다.

    폰 미연결이면 옛 Nostr 수신분(SQLite)으로 떨어지는데 그건 2026-06-22 이후 **얼어붙어**
    있다 — 그래서 stale 플래그로 명시한다(옛 구현은 72일 전 데이터를 success=true 로
    현재인 양 반환했다).
    """
    import time as _time
    try:
        import phone_notifications as _pn
    except Exception as e:
        return {"success": False, "error": f"phone_notifications 모듈 로드 실패: {e}"}

    limit = int(tool_input.get("limit", 20))
    now_ms = int(_time.time() * 1000)

    def _ago(ts):
        try:
            v = int(ts or 0)
        except (TypeError, ValueError):
            return "?"
        if not v:
            return "?"
        if v < 1_000_000_000_000:  # 초 단위로 들어온 값 방어 (혼합 단위)
            v *= 1000
        mins = max(0, (now_ms - v) // 60000)
        if mins < 1:
            return "방금"
        if mins < 60:
            return f"{mins}분 전"
        if mins < 1440:
            return f"{mins // 60}시간 전"
        return f"{mins // 1440}일 전"

    pkg = tool_input.get("pkg") or tool_input.get("package_name")
    rows = _pn.recent(limit=limit, pkg=pkg)
    items = []
    for r in rows:
        ts = r.get("posted_at") or r.get("received_at") or 0
        items.append({
            "pkg": r.get("pkg"),
            "title": r.get("title"),
            "body": r.get("body"),
            "ago": _ago(ts),
            "posted_at": ts,
        })
    latest_ago = items[0]["ago"] if items else None
    # 레코드 통화(비파괴) — 알림 목록 >> [table:document] 등
    records = [{
        "title": (it.get("title") or it.get("pkg") or "(알림)"),
        "meta": " · ".join(x for x in [it.get("pkg"), it.get("ago")] if x),
        "summary": it.get("body") or "",
        "url": None,
    } for it in items]
    # ★얼어붙은 피드 방어: 가장 최근이 이틀보다 오래면 '현재 상태'로 읽히면 안 된다.
    # (2026-08-17 실측 — 수집기가 폐기된 뒤에도 success=true 로 72일 전 데이터를 냈다.)
    newest = items[0]["posted_at"] if items else 0
    stale = bool(items) and (now_ms - int(newest or 0)) > 2 * 86400_000
    out = {
        "success": True,
        "count": len(items),
        "latest_ago": latest_ago,
        "stale": stale,
        "notifications": items,
        "items": records,
        "hint": "ago='방금'/'N분 전'이면 방금 온 연락. 가장 최근이 수시간/수일 전이면 지금 오는 연락은 없음.",
    }
    if stale:
        out["warning"] = (f"가장 최근 알림이 {latest_ago}입니다 — 포획소가 꺼져 있거나 폰이"
                          " 연결되지 않아 옛 기록을 보고 있을 수 있습니다. 현재 상태로 읽지 마세요.")
    return out


# === [limbs:phone] 송신측 — 폰 네이티브 effector ===
# 폰의 파이썬 뇌가 폰 하드웨어를 직접 만진다. Chaquopy Java 브리지로 Kotlin
# PhoneActions(@JvmStatic)를 호출. runs_on=phone_only 라 폰 프로파일에서만 노출되지만,
# 혹시 PC에서 호출돼도 `from java import` 가 없어 graceful 거부.
# sms/call 은 채워서 열기만 — 전송·통화는 사용자 탭.

def _act_bridge():
    """공용 전처리 — Chaquopy jclass + PhoneActions 로드. 반환 (jclass, PA, 오류dict|None)."""
    try:
        from java import jclass  # Chaquopy 브리지 — 폰 네이티브 런타임에만 존재
    except Exception:
        return None, None, {"success": False,
                            "error": "[limbs:phone] 는 폰 네이티브 앱에서만 동작합니다(Chaquopy 브리지 부재). "
                                     "집 PC에선 limbs:android(USB-ADB)를 쓰세요.",
                            "phone_only": True}
    try:
        PA = jclass("com.indiebiz.phoneagent.PhoneActions")
    except Exception as e:
        return None, None, {"success": False, "error": f"PhoneActions 브리지 로드 실패: {e}"}
    return jclass, PA, None


def _act_notify(tool_input: dict) -> dict:
    jclass, PA, err = _act_bridge()
    if err:
        return err
    title = (tool_input.get("title") or "IndieBiz").strip()
    body = (tool_input.get("body") or tool_input.get("text") or "").strip()
    ok = bool(PA.notify(title, body))
    return {"success": ok, "message": f"알림 표시: {title}" if ok
            else "알림 실패(POST_NOTIFICATIONS 권한 확인)."}


def _act_vibrate(tool_input: dict) -> dict:
    jclass, PA, err = _act_bridge()
    if err:
        return err
    try:
        ms = int(tool_input.get("duration_ms", 400))
    except (TypeError, ValueError):
        ms = 400
    ok = bool(PA.vibrate(ms))
    return {"success": ok, "message": f"진동 {ms}ms" if ok else "진동 실패."}


def _act_toast(tool_input: dict) -> dict:
    jclass, PA, err = _act_bridge()
    if err:
        return err
    text = (tool_input.get("text") or tool_input.get("body") or "").strip()
    if not text:
        return {"success": False, "error": "toast 엔 text 가 필요합니다."}
    ok = bool(PA.toast(text))
    return {"success": ok, "message": "토스트 표시"}


def _act_clipboard(tool_input: dict) -> dict:
    jclass, PA, err = _act_bridge()
    if err:
        return err
    # 이미지 클립보드(ClipData.newUri): image_path(로컬 경로)·image_b64/b64·image(data URI) 중
    # 하나가 있으면 이미지로 얹는다 — 카카오톡 등 입력창에서 붙여넣기. 없으면 텍스트 경로.
    image_path = tool_input.get("image_path") or tool_input.get("path")
    img_b64 = tool_input.get("image_b64") or tool_input.get("b64") or tool_input.get("image")
    if image_path or img_b64:
        import base64 as _b64
        import uuid as _uuid
        try:
            if img_b64:
                if isinstance(img_b64, str) and img_b64.startswith("data:"):
                    img_b64 = img_b64.split(",", 1)[-1]
                data = _b64.b64decode(img_b64)
            else:
                with open(image_path, "rb") as _f:
                    data = _f.read()
        except Exception as e:
            return {"success": False, "error": f"이미지 로드 실패: {e}"}
        mime = (tool_input.get("mime") or "image/png").strip()
        filename = (tool_input.get("filename") or f"clip_{_uuid.uuid4().hex[:8]}.png").strip()
        try:
            MS = jclass("com.indiebiz.phoneagent.MediaSaver")
        except Exception as e:
            return {"success": False, "error": f"MediaSaver 브리지 로드 실패: {e}"}
        res = str(MS.imageToClipboard(data, filename, mime))
        if res.startswith("ERROR"):
            return {"success": False, "error": res}
        return {"success": True, "message": "이미지 클립보드 복사 — 카카오톡 등에서 붙여넣기"}
    text = tool_input.get("text")
    if text is None:
        return {"success": False, "error": "clipboard 엔 text 또는 image_path/b64 가 필요합니다."}
    ok = bool(PA.setClipboard(str(text)))
    return {"success": ok, "message": "클립보드 복사" if ok else "복사 실패."}


def _act_speak(tool_input: dict) -> dict:
    jclass, PA, err = _act_bridge()
    if err:
        return err
    text = (tool_input.get("text") or tool_input.get("body") or "").strip()
    if not text:
        return {"success": False, "error": "speak 엔 text 가 필요합니다."}
    ok = bool(PA.speak(text))
    return {"success": ok, "message": f"음성 출력: {text[:30]}" if ok
            else "음성 출력 실패(TTS 엔진/한국어 음성 미준비일 수 있음)."}


def _act_open_app(tool_input: dict) -> dict:
    jclass, PA, err = _act_bridge()
    if err:
        return err
    pkg = tool_input.get("package_name") or tool_input.get("pkg")
    if not pkg:
        return {"success": False, "error": "open_app 엔 package_name 이 필요합니다 (예 com.kakao.talk)."}
    ok = bool(PA.openApp(str(pkg)))
    return {"success": ok, "message": f"앱 실행: {pkg}" if ok
            else f"앱을 찾을 수 없습니다: {pkg}"}


def _act_sms(tool_input: dict) -> dict:
    # 스테이징: 작성창을 수신자·본문 채워 연다. 전송은 사용자 탭(자율 발송 아님).
    # SEND_SMS/CALL_PHONE 위험권한 불필요 — augmentation-over-autonomy.
    jclass, PA, err = _act_bridge()
    if err:
        return err
    to = str(tool_input.get("to") or tool_input.get("number") or "").strip()
    text = (tool_input.get("text") or tool_input.get("body") or "").strip()
    ok = bool(PA.composeSms(to, text))
    return {"success": ok, "staged": True,
            "message": (f"문자 작성창 열림 (받는사람 {to or '미지정'}) — 전송은 직접 탭하세요" if ok
                        else "문자 작성창 열기 실패.")}


def _act_call(tool_input: dict) -> dict:
    # 스테이징: 다이얼러를 번호 채워 연다. 통화 시작은 사용자 탭(즉시 발신 아님).
    jclass, PA, err = _act_bridge()
    if err:
        return err
    number = str(tool_input.get("to") or tool_input.get("number") or "").strip()
    if not number:
        return {"success": False, "error": "call 엔 number(또는 to) 가 필요합니다."}
    ok = bool(PA.dial(number))
    return {"success": ok, "staged": True,
            "message": (f"다이얼러 열림 ({number}) — 통화는 직접 탭하세요" if ok
                        else "다이얼러 열기 실패.")}


def _act_save_share(op: str, tool_input: dict) -> dict:
    # 파일을 폰의 공유 가능한 위치(공용 Downloads)에 저장(save) 또는 저장 후 공유 시트 열기(share).
    # 내용원: content(텍스트 — 신문/보고서 마크다운 등) 또는 b64(바이너리 — PDF/이미지).
    # 파이프 이전 단계([self:read] 등)의 텍스트도 _prev_result 로 수용.
    jclass, PA, err = _act_bridge()
    if err:
        return err
    import base64 as _b64mod
    filename = (tool_input.get("filename") or tool_input.get("name") or "").strip()
    mime = (tool_input.get("mime") or tool_input.get("mime_type") or "").strip()
    content = tool_input.get("content")
    b64 = tool_input.get("b64")
    if content is None and b64 is None:
        prev = tool_input.get("_prev_result")
        # @맥 등으로 포워드된 read 결과는 {"result": "<본문>", "_forwarded_to": ...} JSON 봉투로 옴 → 벗긴다.
        # (로컬 read 는 순수 문자열이라 파싱 실패 → 그대로 사용.)
        if isinstance(prev, str):
            try:
                import json as _json
                _parsed = _json.loads(prev)
                if isinstance(_parsed, dict):
                    prev = _parsed
            except Exception:
                pass
        if isinstance(prev, dict):
            content = (prev.get("result") or prev.get("message") or prev.get("markdown")
                       or prev.get("text") or prev.get("content"))
        elif isinstance(prev, str):
            content = prev
    if b64:
        try:
            data = _b64mod.b64decode(b64)
        except Exception:
            return {"success": False, "error": "b64 디코드 실패."}
    elif content is not None:
        data = str(content).encode("utf-8")
    else:
        return {"success": False,
                "error": f"{op} 엔 content(텍스트) 또는 b64(바이너리)가 필요합니다."}
    if not filename:
        filename = "indiebiz_share.txt"
    if not mime:
        mime = "text/plain"
    try:
        MS = jclass("com.indiebiz.phoneagent.MediaSaver")
    except Exception as e:
        return {"success": False, "error": f"MediaSaver 브리지 로드 실패: {e}"}
    res = str(MS.shareFile(data, filename, mime) if op == "share"
              else MS.saveToDownloads(data, filename, mime))
    if res.startswith("ERROR"):
        return {"success": False, "error": res}
    if op == "share":
        return {"success": True, "staged": True, "location": res,
                "message": f"공유 시트 열림 — {res} 에 저장, 앱(카카오톡 등)을 골라 공유하세요"}
    return {"success": True, "location": res, "message": f"공유 가능한 위치에 저장됨: {res}"}


def _act_save(tool_input: dict) -> dict:
    return _act_save_share("save", tool_input)


def _act_share(tool_input: dict) -> dict:
    return _act_save_share("share", tool_input)


def _phone_locate(tool_input: dict) -> dict:
    """지금 이 몸이 있는 곳 ([sense:here]) — 지표어(deixis): 몸마다 자기 방식으로 측정.

    어휘는 하나, 값은 몸이 정한다: 폰=fused GPS(±수십 m) / 데스크탑=선언 위치 >
    OS 위치서비스(WiFi 수십~수백 m) > IP 지오(도시 수준) + 움직임-증거 캐시(네트워크
    지문 불변이면 재측정 안 함 = 0원). 상시 추적 없이 물을 때만
    (augmentation-over-autonomy) — 캐시는 수집이 아니라 읽기 시점의 신선도 검사다.
    통화 정직성: {success, lat, lng, source(gps|declared|wifi|ip), accuracy_m,
    measured_at, address?, cached?} — 소비자가 정밀도를 보고 판단한다(도시 수준이면
    날씨엔 충분, 길찾기 출발점이면 폰 몸에 [others:ask]).
    """
    try:
        from java import jclass  # Chaquopy 브리지 — 능력 감지(폰 네이티브 런타임에만 존재)
    except Exception:
        jclass = None
    if jclass is not None:
        return _here_phone(jclass)  # 폰 프로브 — 내부 예외는 폰 에러로 정직 반환(데스크탑로 새지 않음)
    return _here_desktop(tool_input)


def _here_phone(jclass) -> dict:
    """폰 프로브 — fused GPS 1회 (Chaquopy→Kotlin). 폰=움직이는 몸이라 캐시 없음(항상 실측)."""
    try:
        PA = jclass("com.indiebiz.phoneagent.PhoneActions")
    except Exception as e:
        return {"success": False, "error": f"PhoneActions 브리지 로드 실패: {e}"}

    import json as _json
    import time as _time
    raw = PA.getCurrentLocationNow()
    try:
        data = _json.loads(str(raw))
    except Exception:
        return {"success": False, "error": f"위치 응답 파싱 실패: {raw}"}
    if data.get("error"):
        return {"success": False, "error": data["error"]}
    out = {"success": True, **data}
    out.setdefault("source", "gps")
    if "accuracy" in out and "accuracy_m" not in out:
        out["accuracy_m"] = out["accuracy"]
    out.setdefault("measured_at", out.get("captured_at")
                   or _time.strftime("%Y-%m-%dT%H:%M:%S"))
    return out


def _here_net_fingerprint() -> str:
    """움직임-증거 지문 — 로컬 IP(라우팅 기준). 네트워크가 안 바뀌면 몸도 안 움직였다고
    본다(데스크탑 기준 충분). 순수 stdlib·무권한·윈도우 호환(SSID 는 macOS 권한 필요라 배제)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(2)
        s.connect(("8.8.8.8", 53))  # 실제 송신 없음(UDP connect) — 라우팅 소스 IP 만 얻음
        return s.getsockname()[0]
    except Exception:
        return "offline"
    finally:
        s.close()


def _here_os_location() -> dict | None:
    """OS 위치서비스 프로브 — GPS 없이 주변 WiFi AP 지문으로 수십~수백 m(랩탑의 정답).

    macOS=CoreLocation(pyobjc, 폴백 CoreLocationCLI) / Windows=GeoCoordinateWatcher
    (PowerShell) / Linux=GeoClue(where-am-i 데모). 권한 거부·미지원·타임아웃은 전부
    조용히 None → 호출측이 IP 폴백(현행 유지). 반환={"lat","lng","accuracy_m"}.
    ★TCC 권한(macOS): 백엔드가 Electron 스폰이라 팝업 귀속 주체가 Python/Electron —
    1회 허용 필요, 거부돼도 None 이라 무해.
    """
    import platform
    try:
        sysname = platform.system()
        if sysname == "Darwin":
            return _here_os_macos()
        if sysname == "Windows":
            return _here_os_windows()
        if sysname == "Linux":
            return _here_os_linux()
    except Exception:
        pass
    return None


def _here_os_macos() -> dict | None:
    """CoreLocation — pyobjc 바인딩 우선, 없으면 CoreLocationCLI(brew) 폴백."""
    try:
        import CoreLocation  # pyobjc-framework-CoreLocation (requirements-tools.txt)
        from Foundation import NSDate, NSRunLoop
        if not CoreLocation.CLLocationManager.locationServicesEnabled():
            return None
        mgr = CoreLocation.CLLocationManager.alloc().init()
        # 권한: 0=미결정 1=제한 2=거부 3/4=허용. 미결정이면 start 가 TCC 팝업 유발.
        try:
            auth = mgr.authorizationStatus()  # macOS 11+ 인스턴스 속성
        except Exception:
            auth = CoreLocation.CLLocationManager.authorizationStatus()
        if auth in (1, 2):
            return None
        if auth == 0:  # 미결정 → TCC 팝업 명시 요청(헤드리스에선 안 뜰 수 있음 — 폴백 무해)
            try:
                mgr.requestWhenInUseAuthorization()
            except Exception:
                pass
        mgr.startUpdatingLocation()
        try:
            loc = None
            for _ in range(24):  # 최대 ~6초 — 워커 스레드에서 런루프 수동 스핀
                NSRunLoop.currentRunLoop().runUntilDate_(
                    NSDate.dateWithTimeIntervalSinceNow_(0.25))
                loc = mgr.location()
                if loc is not None:
                    break
                try:
                    if mgr.authorizationStatus() in (1, 2):  # 스핀 중 거부 → 조기 탈출
                        return None
                except Exception:
                    pass
        finally:
            mgr.stopUpdatingLocation()
        if loc is None:
            return None
        coord = loc.coordinate()
        acc = float(loc.horizontalAccuracy())
        if acc < 0:  # CoreLocation 관례: 음수=무효 fix
            return None
        return {"lat": float(coord.latitude), "lng": float(coord.longitude),
                "accuracy_m": round(acc)}
    except ImportError:
        pass
    except Exception:
        return None
    # 폴백: CoreLocationCLI (brew install corelocationcli)
    import re
    import shutil
    import subprocess
    cli = shutil.which("CoreLocationCLI")
    if not cli:
        return None
    try:
        p = subprocess.run([cli, "-once", "-json"], capture_output=True,
                           text=True, timeout=15)
        if p.returncode == 0:
            try:
                import json as _json
                d = _json.loads(p.stdout)
                lat = d.get("latitude") or d.get("lat")
                lng = d.get("longitude") or d.get("lng") or d.get("lon")
                if lat is not None and lng is not None:
                    return {"lat": float(lat), "lng": float(lng),
                            "accuracy_m": round(float(d.get("h_accuracy")
                                                      or d.get("accuracy") or 200))}
            except Exception:
                pass
        # 구판 폴백: 기본 출력 "위도 경도" 두 실수
        p = subprocess.run([cli, "-once"], capture_output=True, text=True, timeout=15)
        nums = re.findall(r"-?\d+\.\d+", p.stdout)
        if len(nums) >= 2:
            return {"lat": float(nums[0]), "lng": float(nums[1]), "accuracy_m": 200}
    except Exception:
        pass
    return None


def _here_os_windows() -> dict | None:
    """Windows 위치 서비스 — System.Device.Location.GeoCoordinateWatcher (PowerShell).

    ★숫자는 InvariantCulture 로 강제 출력(로케일 소수점 콤마 방어). 권한 거부·미측정
    =exit 2 → None. subprocess 만 사용(check_win_portability 게이트 무관).
    """
    import subprocess
    script = (
        "Add-Type -AssemblyName System.Device;"
        "$w = New-Object System.Device.Location.GeoCoordinateWatcher('High');"
        "$w.Start();"
        "$i = 0;"
        "while ($i -lt 100 -and $w.Permission -ne 'Denied' -and "
        "$w.Position.Location.IsUnknown) { Start-Sleep -Milliseconds 100; $i++ };"
        "$L = $w.Position.Location; $w.Stop();"
        "if ($w.Permission -eq 'Denied' -or $L.IsUnknown) { exit 2 };"
        "$ci = [System.Globalization.CultureInfo]::InvariantCulture;"
        "Write-Output ($L.Latitude.ToString($ci) + ',' + $L.Longitude.ToString($ci)"
        " + ',' + $L.HorizontalAccuracy.ToString($ci))"
    )
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if p.returncode != 0:
            return None
        parts = p.stdout.strip().splitlines()[-1].split(",")
        lat, lng = float(parts[0]), float(parts[1])
        acc = float(parts[2]) if len(parts) > 2 else 200.0
        if not (acc == acc) or acc <= 0:  # NaN(정확도 미제공) 또는 무효
            acc = 200.0
        return {"lat": lat, "lng": lng, "accuracy_m": round(acc)}
    except Exception:
        return None


def _here_os_linux() -> dict | None:
    """GeoClue — where-am-i 데모 바이너리가 있으면 사용(없으면 None)."""
    import os
    import re
    import shutil
    import subprocess
    cands = [shutil.which("where-am-i"),
             "/usr/lib/geoclue-2.0/demos/where-am-i",
             "/usr/libexec/geoclue-2.0/demos/where-am-i"]
    cli = next((c for c in cands if c and os.path.exists(c)), None)
    if not cli:
        return None
    try:
        p = subprocess.run([cli, "-t", "10"], capture_output=True, text=True, timeout=15)
        lat = re.search(r"Latitude:\s*(-?\d+\.\d+)", p.stdout)
        lng = re.search(r"Longitude:\s*(-?\d+\.\d+)", p.stdout)
        if not (lat and lng):
            return None
        acc = re.search(r"Accuracy:\s*(-?\d+\.?\d*)", p.stdout)
        return {"lat": float(lat.group(1)), "lng": float(lng.group(1)),
                "accuracy_m": round(float(acc.group(1))) if acc else 200}
    except Exception:
        return None


def _here_cache_put(cache_path: str, fp: str, out: dict) -> None:
    """움직임-증거 캐시 기록 — 실패는 조용히(캐시는 최적화일 뿐)."""
    import json as _json
    import os as _os
    try:
        _os.makedirs(_os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            _json.dump({"fingerprint": fp, "result": out}, f, ensure_ascii=False)
    except Exception:
        pass


def _here_desktop(tool_input: dict) -> dict:
    """데스크탑 프로브 — 선언 위치 > OS 위치서비스(WiFi) > IP 지오 + 움직임-증거 캐시.

    ★선언 위치(data/body_location.json): 고정 몸(데스크탑)의 정답 소스. IP 지오는
    ISP 등록지 기준이라 도시가 통째로 틀릴 수 있다(오송 거주인데 '제천' 실측,
    2026-08-06) — 안 움직이는 몸은 사용자가 한 번 선언하는 쪽이 유일하게 정확하다.
    파일이 있으면 아무것도 안 잰다. 이동하는 몸(랩탑)은 이 파일을 만들지 말 것 —
    OS 위치서비스 층(CoreLocation/Windows 위치서비스/GeoClue, WiFi AP 지문 수십~
    수백 m)이 랩탑의 정답이고, 권한 거부·미지원이면 조용히 IP 폴백.

    정책(보편): 움직였다는 증거(지문 변경)가 없으면 캐시를 내놓는다 — 안 바뀌는 걸
    시간·돈 들여 재확인하지 않는다. refresh=true 로 강제 재측정(선언 위치는 불변).
    """
    import json as _json
    import os as _os
    import time as _time

    # ★base 폴백 = 레포 루트 — 핸들러 위치(data/packages/installed/tools/android)에서
    # 5단계 위. 옛 4단계 폴백은 data/ 로 풀려 라이브(INDIEBIZ_BASE_PATH 미설정)가
    # data/data/here_cache.json 을 읽고 쓰던 잠복 버그(2026-08-06 발견 — data/data/ 잔재의 진범).
    base = _os.environ.get("INDIEBIZ_BASE_PATH") or _os.path.abspath(_os.path.join(
        _os.path.dirname(__file__), "..", "..", "..", "..", ".."))

    # 0) 선언 위치 — 고정 몸의 정답 (있으면 IP 측정·캐시 모두 생략)
    declared_path = _os.path.join(base, "data", "body_location.json")
    try:
        with open(declared_path, "r", encoding="utf-8") as f:
            decl = _json.load(f)
        if decl.get("lat") is not None and decl.get("lng") is not None:
            return {"success": True, "lat": decl["lat"], "lng": decl["lng"],
                    "city": decl.get("city"), "address": decl.get("address"),
                    "source": "declared", "accuracy_m": decl.get("accuracy_m", 3000),
                    "measured_at": decl.get("declared_at"), "cached": False,
                    "note": "사용자 선언 위치(고정 몸 — data/body_location.json). "
                            "이사했으면 그 파일을 수정하세요. 정밀 위치(길찾기 출발점)는 "
                            "폰 몸에 부탁: [others:ask]{message: \"지금 위치 알려줘\"}"}
    except FileNotFoundError:
        pass
    except Exception:
        pass  # 파일 손상 → IP 폴백으로 진행(조용히)

    cache_path = _os.path.join(base, "data", "here_cache.json")
    fp = _here_net_fingerprint()

    if not tool_input.get("refresh"):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = _json.load(f)
            if cache.get("fingerprint") == fp and cache.get("result", {}).get("success"):
                out = dict(cache["result"])
                out["cached"] = True
                out["note"] = ("네트워크 지문 불변 → 캐시(측정 " + str(out.get("measured_at"))
                               + "). 이사/이동했으면 refresh: true 로 재측정.")
                return out
        except Exception:
            pass

    if fp == "offline":
        return {"success": False, "error": "오프라인 — 네트워크 없이 이 몸의 위치를 측정할 수 없습니다.",
                "source": "ip"}

    # 1) OS 위치서비스 — 이동하는 몸(랩탑)의 정답: WiFi AP 지문 수십~수백 m.
    #    권한 거부·미지원·타임아웃은 None → IP 폴백(조용히, 현행 유지).
    osloc = _here_os_location()
    if osloc is not None:
        out = {"success": True, "lat": osloc["lat"], "lng": osloc["lng"],
               "source": "wifi", "accuracy_m": osloc.get("accuracy_m", 200),
               "measured_at": _time.strftime("%Y-%m-%dT%H:%M:%S"), "cached": False,
               "note": "OS 위치서비스(WiFi 기반) — 수십~수백 m 정밀도. "
                       "이동했으면 refresh: true 로 재측정."}
        _here_cache_put(cache_path, fp, out)
        return out

    # 2) 측정: 공인 IP 지오 (1차 https ipapi.co, 2차 ip-api.com lang=ko)
    import requests
    result = None
    try:
        r = requests.get("https://ipapi.co/json/", timeout=10)
        d = r.json()
        if r.status_code == 200 and d.get("latitude") is not None:
            result = {"lat": d.get("latitude"), "lng": d.get("longitude"),
                      "city": d.get("city"), "ip": d.get("ip"),
                      "address": " ".join(x for x in (d.get("country_name"),
                                                      d.get("region"), d.get("city")) if x)}
    except Exception:
        pass
    if result is None:
        try:
            r = requests.get("http://ip-api.com/json/?lang=ko", timeout=10)
            d = r.json()
            if d.get("status") == "success":
                result = {"lat": d.get("lat"), "lng": d.get("lon"),
                          "city": d.get("city"), "ip": d.get("query"),
                          "address": " ".join(x for x in (d.get("country"),
                                                          d.get("regionName"), d.get("city")) if x)}
        except Exception:
            pass
    if result is None:
        return {"success": False, "error": "IP 위치 측정 실패(지오 서비스 모두 미응답).",
                "source": "ip"}

    out = {"success": True, **result, "source": "ip", "accuracy_m": 10000,
           "measured_at": _time.strftime("%Y-%m-%dT%H:%M:%S"), "cached": False,
           "note": "IP 기반 — 도시 수준 정밀도이며 ISP 등록지라 도시가 틀릴 수 있음. "
                   "고정 몸(데스크탑)이면 data/body_location.json 에 위치를 선언하면 "
                   "정확해짐. 정밀 위치는 폰 몸에 부탁: [others:ask]{message: \"지금 위치 알려줘\"}"}
    _here_cache_put(cache_path, fp, out)
    return out


def _listen_run(op: str, tool_input: dict) -> dict:
    """폰 마이크 온디맨드 ([sense:listen]) — transcribe(STT→텍스트)/record(녹음→파일). phone_only.

    Chaquopy→Kotlin PhoneActions. transcribe 는 텍스트라 맥↔폰 포워드 무손실;
    record 파일은 폰에 잔류(경로 반환, 회수는 후속). 상시 수집 아닌 호출 시 1회.
    """
    try:
        from java import jclass  # Chaquopy 브리지 — 능력 감지(폰 네이티브 런타임에만 존재)
    except Exception:
        jclass = None
    if jclass is None:
        # 지표어 — 데스크탑 몸의 마이크 프로브(ffmpeg). 하드웨어 없으면 정직한 작동불능.
        from desktop_av import listen_desktop
        return listen_desktop(op, tool_input)
    try:
        PA = jclass("com.indiebiz.phoneagent.PhoneActions")
    except Exception as e:
        return {"success": False, "error": f"PhoneActions 브리지 로드 실패: {e}"}

    import json as _json
    if op == "transcribe":
        try:
            timeout = int(tool_input.get("timeout_sec") or 15)
        except (TypeError, ValueError):
            timeout = 15
        raw = PA.transcribeFromMic(timeout)
    else:  # record (op 는 디스패처가 transcribe/record 로 게이트)
        try:
            dur = int(tool_input.get("duration_sec") or 5)
        except (TypeError, ValueError):
            dur = 5
        raw = PA.recordAudio(dur)

    try:
        data = _json.loads(str(raw))
    except Exception:
        return {"success": False, "error": f"마이크 응답 파싱 실패: {raw}"}
    if data.get("error"):
        return {"success": False, "error": data["error"]}
    return {"success": True, **data}


def _listen_transcribe(tool_input: dict) -> dict:
    return _listen_run("transcribe", tool_input)


def _listen_record(tool_input: dict) -> dict:
    return _listen_run("record", tool_input)


def _phone_capture(tool_input: dict) -> dict:
    """폰 카메라 촬영 온디맨드 ([sense:see]) — 사진 1장 → 폰 파일. phone_only.

    Chaquopy→Kotlin PhoneActions.capturePhoto. facing=back(기본)/front. 파일은 폰에 잔류
    (경로 반환, 회수는 후속). 상시 촬영 아닌 호출 시 1회. 앱 포그라운드일 때 가장 안정적.
    """
    try:
        from java import jclass  # Chaquopy 브리지 — 능력 감지(폰 네이티브 런타임에만 존재)
    except Exception:
        jclass = None
    if jclass is None:
        # 지표어 — 데스크탑 몸의 카메라 프로브(ffmpeg 웹캠). 하드웨어 없으면 정직한 작동불능.
        from desktop_av import see_desktop
        return see_desktop(tool_input)
    try:
        PA = jclass("com.indiebiz.phoneagent.PhoneActions")
    except Exception as e:
        return {"success": False, "error": f"PhoneActions 브리지 로드 실패: {e}"}

    import json as _json
    facing = str(tool_input.get("facing") or "back").strip()
    raw = PA.capturePhoto(facing)
    try:
        data = _json.loads(str(raw))
    except Exception:
        return {"success": False, "error": f"촬영 응답 파싱 실패: {raw}"}
    if data.get("error"):
        return {"success": False, "error": data["error"]}
    return {"success": True, **data}


def _android_native(tool_input: dict) -> dict:
    """[limbs:android] 폰 네이티브 경로 — INDIEBIZ_PROFILE=phone 일 때 PC-ADB 대신 AccessibilityService.

    폰이 USB 없이 자기 화면을 독해·조작한다(Chaquopy→Kotlin PhoneAccessibilityService).
    PC-ADB(ui_control)와 같은 op·파라미터 계약을 그대로 따른다 — 핸들러 분기만 환경별로.
    접근성 서비스 미활성이면 needs_accessibility 안내 반환.
    """
    op = (tool_input.get("op") or _OP_DEFAULTS["android_op"]).strip()
    try:
        from java import jclass  # Chaquopy 브리지 — 폰 네이티브 런타임에만 존재
    except Exception:
        return {"success": False,
                "error": "[limbs:android] 폰 네이티브 경로는 폰 앱에서만 동작합니다(Chaquopy 부재).",
                "phone_only": True}
    import json as _json
    SVC = jclass("com.indiebiz.phoneagent.PhoneAccessibilityService")

    if op == "snapshot":
        raw = SVC.snapshot()
    elif op == "tap":
        query = tool_input.get("query")
        if query:
            raw = SVC.tapByText(str(query), int(tool_input.get("index", 0) or 0))
        else:
            x, y = tool_input.get("x"), tool_input.get("y")
            if x is None or y is None:
                return {"success": False, "error": "tap엔 query(요소 라벨) 또는 x,y 좌표가 필요합니다."}
            raw = SVC.tap(int(x), int(y))
    elif op == "type":
        raw = SVC.typeText(str(tool_input.get("text", "")))
    elif op == "swipe":
        direction = tool_input.get("direction")
        if direction:
            raw = SVC.swipeDir(str(direction))
        else:
            try:
                raw = SVC.swipe(int(tool_input["x1"]), int(tool_input["y1"]),
                                int(tool_input["x2"]), int(tool_input["y2"]),
                                int(tool_input.get("duration_ms", 300)))
            except (KeyError, TypeError, ValueError):
                return {"success": False, "error": "swipe엔 direction(up/down/left/right) 또는 x1,y1,x2,y2 가 필요합니다."}
    elif op == "key":
        raw = SVC.pressKey(str(tool_input.get("key") or tool_input.get("keycode", "")))
    elif op == "long_press":
        x, y = tool_input.get("x"), tool_input.get("y")
        if x is None or y is None:
            return {"success": False, "error": "long_press엔 x,y 좌표가 필요합니다."}
        raw = SVC.longPress(int(x), int(y), int(tool_input.get("duration_ms", 1000)))
    elif op == "open_app":
        pkg = tool_input.get("package_name") or tool_input.get("package")
        if not pkg:
            return {"success": False, "error": "open_app엔 package_name 이 필요합니다 (예 com.kakao.talk)."}
        PA = jclass("com.indiebiz.phoneagent.PhoneActions")
        ok = bool(PA.openApp(str(pkg)))
        return {"success": ok, "message": f"앱 실행: {pkg}" if ok else f"앱을 찾을 수 없습니다: {pkg}"}
    else:
        return {"success": False,
                "error": f"알 수 없는 op '{op}'. 사용 가능: snapshot/tap/type/swipe/key/long_press/open_app"}

    try:
        return _json.loads(str(raw))
    except Exception:
        return {"success": False, "error": f"네이티브 응답 파싱 실패: {raw}"}


# === [limbs:android] op 함수들 — 몸 분기(집 PC=ADB / 폰=네이티브 접근성)를 각 op 안에 보존 ===
# 폰 프로파일: PC-ADB(USB) 대신 폰 네이티브 AccessibilityService 로 자기 화면 조작(자급).

def _and_snapshot(tool_input: dict) -> dict:
    if _is_phone_profile():
        return _android_native(tool_input)
    return _snapshot(tool_input)


def _and_tap(tool_input: dict) -> dict:
    if _is_phone_profile():
        return _android_native(tool_input)
    device_id = tool_input.get("device_id")
    query = tool_input.get("query")
    if query:
        return _ui.find_and_tap(query, tool_input.get("index", 0), device_id)
    x, y = tool_input.get("x"), tool_input.get("y")
    if x is None or y is None:
        return {"success": False, "error": "tap엔 query(요소 라벨/id 일부) 또는 x,y 좌표가 필요합니다."}
    return _ui.tap(int(x), int(y), device_id)


def _and_long_press(tool_input: dict) -> dict:
    if _is_phone_profile():
        return _android_native(tool_input)
    device_id = tool_input.get("device_id")
    x, y = tool_input.get("x"), tool_input.get("y")
    if x is None or y is None:
        return {"success": False, "error": "long_press엔 x,y 좌표가 필요합니다."}
    return _ui.long_press(int(x), int(y), tool_input.get("duration_ms", 1000), device_id)


def _and_type(tool_input: dict) -> dict:
    if _is_phone_profile():
        return _android_native(tool_input)
    return _ui.type_text(tool_input.get("text", ""), tool_input.get("device_id"))


def _and_swipe(tool_input: dict) -> dict:
    if _is_phone_profile():
        return _android_native(tool_input)
    return _swipe(tool_input)


def _and_key(tool_input: dict) -> dict:
    if _is_phone_profile():
        return _android_native(tool_input)
    return _ui.press_key(tool_input.get("key") or tool_input.get("keycode", ""),
                         tool_input.get("device_id"))


def _and_open_app(tool_input: dict) -> dict:
    if _is_phone_profile():
        return _android_native(tool_input)
    pkg = tool_input.get("package_name") or tool_input.get("package", "")
    return _ui.open_app(pkg, tool_input.get("device_id"))


# === 디스패처 (진짜 함수 참조 — src.ops.values 와 AST 정확 비교 대상) ===

_OP_DISPATCHERS = {
    "android_op": {
        "snapshot": _and_snapshot,
        "tap": _and_tap,
        "type": _and_type,
        "swipe": _and_swipe,
        "key": _and_key,
        "long_press": _and_long_press,
        "open_app": _and_open_app,
    },
    # 2026-06-06 폰 컴패니언 sense 피드 ([sense:phone]). limbs:android(제어)와
    # 짝을 이루는 입력측 — 폰 에이전트가 보낸 알림을 읽는다(이벤트 구동, 상시 폴링 아님).
    # raw ADB dumpsys 우회 대신 이 액션이 "지금 폰에 오는 연락"의 정답 소스.
    # (2026-06-12 location/steps 상시 수집 폐기 — 위치는 [sense:here] 온디맨드로 분리.)
    "phone_op": {
        "notifications": _phone_notifications,
    },
    # 2026-06-12 폰 현재위치 온디맨드 ([sense:here]) — 단일 목적이라 op 없음(디스패처 미등록).
    # 2026-06-12 폰 마이크 ([sense:listen]) — transcribe(STT)/record(녹음).
    "phone_listen": {
        "transcribe": _listen_transcribe,
        "record": _listen_record,
    },
    # 2026-06-11 송신측(폰→동작) — [limbs:phone]. sense:phone(입력)의 출력 짝.
    # Chaquopy Java 브리지로 Kotlin PhoneActions 호출(폰 네이티브 전용, runs_on phone_only).
    "phone_act": {
        "notify": _act_notify,
        "vibrate": _act_vibrate,
        "toast": _act_toast,
        "clipboard": _act_clipboard,
        "speak": _act_speak,
        "open_app": _act_open_app,
        # 외부·비가역 동작은 스테이징(작성창/다이얼러를 채워 열고, 전송·통화는 사용자가 탭).
        # SEND_SMS/CALL_PHONE 위험권한 불필요 — augmentation-over-autonomy.
        "sms": _act_sms,
        "call": _act_call,
        # 파일을 공유 가능한 위치(Downloads)에 저장(save) / 저장 후 공유 시트(share, 카카오톡 등 — 사용자 탭).
        "save": _act_save,
        "share": _act_share,
    },
}
_OP_DEFAULTS = {"android_op": "snapshot", "phone_op": "notifications",
                "phone_listen": "transcribe", "phone_act": "notify"}


def execute(tool_input: dict, context) -> dict:
    """ToolContext 기반 표준 시그니처. limbs:android(PC-ADB or 폰 네이티브 접근성) + sense:phone(알림 피드)
    + sense:here(현재위치) + sense:listen(마이크) + sense:see(카메라) + limbs:phone(폰 네이티브 effector) 디스패처."""
    tool_name = context.tool_name
    if tool_name == "phone_locate":
        return _phone_locate(tool_input)
    if tool_name == "phone_capture":
        return _phone_capture(tool_input)
    if tool_name in _OP_DISPATCHERS:
        op = (tool_input.get("op") or _OP_DEFAULTS.get(tool_name, "")).strip()
        fn = _OP_DISPATCHERS[tool_name].get(op)
        if fn is None:
            return {"success": False,
                    "error": f"알 수 없는 op '{op}'. 사용 가능: {'/'.join(_OP_DISPATCHERS[tool_name])}"}
        return fn(tool_input)
    raise ValueError(f"Unknown tool: {tool_name}")
