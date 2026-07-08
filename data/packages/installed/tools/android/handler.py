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
_OP_DISPATCHERS = {
    "android_op": {
        "snapshot": None,
        "tap": None,
        "type": None,
        "swipe": None,
        "key": None,
        "long_press": None,
        "open_app": None,
    },
    # 2026-06-06 폰 컴패니언 sense 피드 ([sense:phone]). limbs:android(제어)와
    # 짝을 이루는 입력측 — 폰 에이전트가 보낸 알림을 읽는다(이벤트 구동, 상시 폴링 아님).
    # raw ADB dumpsys 우회 대신 이 액션이 "지금 폰에 오는 연락"의 정답 소스.
    # (2026-06-12 location/steps 상시 수집 폐기 — 위치는 [sense:here] 온디맨드로 분리.)
    "phone_op": {
        "notifications": None,
    },
    # 2026-06-12 폰 현재위치 온디맨드 ([sense:here]) — 단일 목적이라 op 없음(디스패처 미등록).
    # 2026-06-12 폰 마이크 ([sense:listen]) — transcribe(STT)/record(녹음).
    "phone_listen": {
        "transcribe": None,
        "record": None,
    },
    # 2026-06-11 송신측(폰→동작) — [limbs:phone]. sense:phone(입력)의 출력 짝.
    # Chaquopy Java 브리지로 Kotlin PhoneActions 호출(폰 네이티브 전용, runs_on phone_only).
    "phone_act": {
        "notify": None,
        "vibrate": None,
        "toast": None,
        "clipboard": None,
        "speak": None,
        "open_app": None,
        # 외부·비가역 동작은 스테이징(작성창/다이얼러를 채워 열고, 전송·통화는 사용자가 탭).
        # SEND_SMS/CALL_PHONE 위험권한 불필요 — augmentation-over-autonomy.
        "sms": None,
        "call": None,
        # 파일을 공유 가능한 위치(Downloads)에 저장(save) / 저장 후 공유 시트(share, 카카오톡 등 — 사용자 탭).
        "save": None,
        "share": None,
    },
}
_OP_DEFAULTS = {"android_op": "snapshot", "phone_op": "notifications",
                "phone_listen": "transcribe", "phone_act": "notify"}


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
            return {"success": False, "message": f"알 수 없는 direction '{direction}'. up/down/left/right."}
        x1, y1, x2, y2 = moves[direction]
        return _ui.swipe(x1, y1, x2, y2, tool_input.get("duration_ms", 300), device_id)

    # 좌표 기반
    try:
        x1 = int(tool_input["x1"]); y1 = int(tool_input["y1"])
        x2 = int(tool_input["x2"]); y2 = int(tool_input["y2"])
    except (KeyError, TypeError, ValueError):
        return {"success": False, "message": "swipe엔 direction(up/down/left/right) 또는 x1,y1,x2,y2 필요."}
    return _ui.swipe(x1, y1, x2, y2, tool_input.get("duration_ms", 300), device_id)


def _phone(tool_input: dict) -> dict:
    """폰 컴패니언 sense 피드 조회 ([sense:phone]). op: notifications/location/steps.

    폰 에이전트(NotificationListenerService)가 NIP-17 DM 으로 보내 60초마다 폴링·저장된
    데이터를 읽는다 (backend/phone_notifications.py). USB-ADB 불필요 — 폰이 켜져 있고
    컴패니언 앱이 살아 있기만 하면 됨. "지금 폰에 연락/알림 오나"의 정답 소스.
    """
    import time as _time
    try:
        import phone_notifications as _pn
    except Exception as e:
        return {"success": False, "error": f"phone_notifications 모듈 로드 실패: {e}"}

    op = (tool_input.get("op") or _OP_DEFAULTS["phone_op"]).strip()
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

    if op == "notifications":
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
        return {
            "success": True,
            "count": len(items),
            "latest_ago": latest_ago,
            "notifications": items,
            "items": records,
            "hint": "ago='방금'/'N분 전'이면 방금 온 연락. 가장 최근이 수시간/수일 전이면 지금 오는 연락은 없음.",
        }

    return {
        "success": False,
        "error": f"알 수 없는 op '{op}'. 사용 가능: notifications",
    }


def _phone_act(tool_input: dict) -> dict:
    """송신측 — 폰 네이티브 effector ([limbs:phone]). 폰의 파이썬 뇌가 폰 하드웨어를 직접 만진다.

    Chaquopy Java 브리지로 Kotlin PhoneActions(@JvmStatic)를 호출. runs_on=phone_only 라
    폰 프로파일에서만 노출되지만, 혹시 PC에서 호출돼도 `from java import` 가 없어 graceful 거부.
    op: notify(알림)/vibrate(진동)/toast/clipboard(복사)/speak(TTS)/open_app(앱실행)/
        sms(문자 작성창 스테이징)/call(다이얼러 스테이징). sms/call 은 채워서 열기만 — 전송·통화는 사용자 탭.
    """
    op = (tool_input.get("op") or _OP_DEFAULTS["phone_act"]).strip()
    try:
        from java import jclass  # Chaquopy 브리지 — 폰 네이티브 런타임에만 존재
    except Exception:
        return {"success": False,
                "error": "[limbs:phone] 는 폰 네이티브 앱에서만 동작합니다(Chaquopy 브리지 부재). "
                         "집 PC에선 limbs:android(USB-ADB)를 쓰세요.",
                "phone_only": True}

    try:
        PA = jclass("com.indiebiz.phoneagent.PhoneActions")
    except Exception as e:
        return {"success": False, "error": f"PhoneActions 브리지 로드 실패: {e}"}

    if op == "notify":
        title = (tool_input.get("title") or "IndieBiz").strip()
        body = (tool_input.get("body") or tool_input.get("text") or "").strip()
        ok = bool(PA.notify(title, body))
        return {"success": ok, "message": f"알림 표시: {title}" if ok
                else "알림 실패(POST_NOTIFICATIONS 권한 확인)."}

    if op == "vibrate":
        try:
            ms = int(tool_input.get("duration_ms", 400))
        except (TypeError, ValueError):
            ms = 400
        ok = bool(PA.vibrate(ms))
        return {"success": ok, "message": f"진동 {ms}ms" if ok else "진동 실패."}

    if op == "toast":
        text = (tool_input.get("text") or tool_input.get("body") or "").strip()
        if not text:
            return {"success": False, "error": "toast 엔 text 가 필요합니다."}
        ok = bool(PA.toast(text))
        return {"success": ok, "message": "토스트 표시"}

    if op == "clipboard":
        text = tool_input.get("text")
        if text is None:
            return {"success": False, "error": "clipboard 엔 text 가 필요합니다."}
        ok = bool(PA.setClipboard(str(text)))
        return {"success": ok, "message": "클립보드 복사" if ok else "복사 실패."}

    if op == "speak":
        text = (tool_input.get("text") or tool_input.get("body") or "").strip()
        if not text:
            return {"success": False, "error": "speak 엔 text 가 필요합니다."}
        ok = bool(PA.speak(text))
        return {"success": ok, "message": f"음성 출력: {text[:30]}" if ok
                else "음성 출력 실패(TTS 엔진/한국어 음성 미준비일 수 있음)."}

    if op == "open_app":
        pkg = tool_input.get("package_name") or tool_input.get("pkg")
        if not pkg:
            return {"success": False, "error": "open_app 엔 package_name 이 필요합니다 (예 com.kakao.talk)."}
        ok = bool(PA.openApp(str(pkg)))
        return {"success": ok, "message": f"앱 실행: {pkg}" if ok
                else f"앱을 찾을 수 없습니다: {pkg}"}

    if op == "sms":
        # 스테이징: 작성창을 수신자·본문 채워 연다. 전송은 사용자 탭(자율 발송 아님).
        to = str(tool_input.get("to") or tool_input.get("number") or "").strip()
        text = (tool_input.get("text") or tool_input.get("body") or "").strip()
        ok = bool(PA.composeSms(to, text))
        return {"success": ok, "staged": True,
                "message": (f"문자 작성창 열림 (받는사람 {to or '미지정'}) — 전송은 직접 탭하세요" if ok
                            else "문자 작성창 열기 실패.")}

    if op == "call":
        # 스테이징: 다이얼러를 번호 채워 연다. 통화 시작은 사용자 탭(즉시 발신 아님).
        number = str(tool_input.get("to") or tool_input.get("number") or "").strip()
        if not number:
            return {"success": False, "error": "call 엔 number(또는 to) 가 필요합니다."}
        ok = bool(PA.dial(number))
        return {"success": ok, "staged": True,
                "message": (f"다이얼러 열림 ({number}) — 통화는 직접 탭하세요" if ok
                            else "다이얼러 열기 실패.")}

    if op in ("save", "share"):
        # 파일을 폰의 공유 가능한 위치(공용 Downloads)에 저장(save) 또는 저장 후 공유 시트 열기(share).
        # 내용원: content(텍스트 — 신문/보고서 마크다운 등) 또는 b64(바이너리 — PDF/이미지).
        # 파이프 이전 단계([self:read] 등)의 텍스트도 _prev_result 로 수용.
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

    return {"success": False,
            "error": f"알 수 없는 op '{op}'. 사용 가능: notify/vibrate/toast/clipboard/speak/open_app/sms/call/save/share"}


def _phone_locate(tool_input: dict) -> dict:
    """현재 위치 온디맨드 조회 ([sense:here]) — 폰 fused GPS (Chaquopy→Kotlin). phone_only.

    상시 수집·저장 없이, 물을 때 그 순간 위치를 한 번 가져온다(augmentation-over-autonomy).
    PC/원격에서 부르면 분산 IBL(ibl_engine)이 폰으로 포워드하므로, 맥의 AI 도 자기 위치를 안다.
    반환: {success, lat, lng, accuracy, captured_at, address?}.
    """
    try:
        from java import jclass  # Chaquopy 브리지 — 폰 네이티브 런타임에만 존재
    except Exception:
        return {"success": False,
                "error": "[sense:here] 는 폰 네이티브 앱에서만 동작합니다(Chaquopy 브리지 부재). "
                         "맥/원격에선 INDIEBIZ_PHONE_URL 설정 시 분산 IBL 이 폰으로 포워드합니다.",
                "phone_only": True}
    try:
        PA = jclass("com.indiebiz.phoneagent.PhoneActions")
    except Exception as e:
        return {"success": False, "error": f"PhoneActions 브리지 로드 실패: {e}"}

    import json as _json
    raw = PA.getCurrentLocationNow()
    try:
        data = _json.loads(str(raw))
    except Exception:
        return {"success": False, "error": f"위치 응답 파싱 실패: {raw}"}
    if data.get("error"):
        return {"success": False, "error": data["error"]}
    return {"success": True, **data}


def _phone_listen(tool_input: dict) -> dict:
    """폰 마이크 온디맨드 ([sense:listen]) — transcribe(STT→텍스트)/record(녹음→파일). phone_only.

    Chaquopy→Kotlin PhoneActions. transcribe 는 텍스트라 맥↔폰 포워드 무손실;
    record 파일은 폰에 잔류(경로 반환, 회수는 후속). 상시 수집 아닌 호출 시 1회.
    """
    op = (tool_input.get("op") or _OP_DEFAULTS["phone_listen"]).strip()
    try:
        from java import jclass  # Chaquopy 브리지 — 폰 네이티브 런타임에만 존재
    except Exception:
        return {"success": False,
                "error": "[sense:listen] 는 폰 네이티브 앱에서만 동작합니다(Chaquopy 브리지 부재). "
                         "맥/원격에선 INDIEBIZ_PHONE_URL 설정 시 분산 IBL 이 폰으로 포워드합니다.",
                "phone_only": True}
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
    elif op == "record":
        try:
            dur = int(tool_input.get("duration_sec") or 5)
        except (TypeError, ValueError):
            dur = 5
        raw = PA.recordAudio(dur)
    else:
        return {"success": False, "error": f"알 수 없는 op '{op}'. 사용 가능: transcribe/record"}

    try:
        data = _json.loads(str(raw))
    except Exception:
        return {"success": False, "error": f"마이크 응답 파싱 실패: {raw}"}
    if data.get("error"):
        return {"success": False, "error": data["error"]}
    return {"success": True, **data}


def _phone_capture(tool_input: dict) -> dict:
    """폰 카메라 촬영 온디맨드 ([sense:see]) — 사진 1장 → 폰 파일. phone_only.

    Chaquopy→Kotlin PhoneActions.capturePhoto. facing=back(기본)/front. 파일은 폰에 잔류
    (경로 반환, 회수는 후속). 상시 촬영 아닌 호출 시 1회. 앱 포그라운드일 때 가장 안정적.
    """
    try:
        from java import jclass  # Chaquopy 브리지 — 폰 네이티브 런타임에만 존재
    except Exception:
        return {"success": False,
                "error": "[sense:see] 는 폰 네이티브 앱에서만 동작합니다(Chaquopy 브리지 부재). "
                         "맥/원격에선 INDIEBIZ_PHONE_URL 설정 시 분산 IBL 이 폰으로 포워드합니다.",
                "phone_only": True}
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
                return {"success": False, "message": "tap엔 query(요소 라벨) 또는 x,y 좌표가 필요합니다."}
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
                return {"success": False, "message": "swipe엔 direction(up/down/left/right) 또는 x1,y1,x2,y2 가 필요합니다."}
    elif op == "key":
        raw = SVC.pressKey(str(tool_input.get("key") or tool_input.get("keycode", "")))
    elif op == "long_press":
        x, y = tool_input.get("x"), tool_input.get("y")
        if x is None or y is None:
            return {"success": False, "message": "long_press엔 x,y 좌표가 필요합니다."}
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


def execute(tool_input: dict, context) -> dict:
    """ToolContext 기반 표준 시그니처. limbs:android(PC-ADB or 폰 네이티브 접근성) + sense:phone(알림 피드)
    + sense:here(현재위치) + sense:listen(마이크) + sense:see(카메라) + limbs:phone(폰 네이티브 effector) 디스패처."""
    tool_name = context.tool_name
    if tool_name == "phone_op":
        return _phone(tool_input)
    if tool_name == "phone_locate":
        return _phone_locate(tool_input)
    if tool_name == "phone_listen":
        return _phone_listen(tool_input)
    if tool_name == "phone_capture":
        return _phone_capture(tool_input)
    if tool_name == "phone_act":
        return _phone_act(tool_input)
    if tool_name != "android_op":
        raise ValueError(f"Unknown tool: {tool_name}")

    # 폰 프로파일: PC-ADB(USB) 대신 폰 네이티브 AccessibilityService 로 자기 화면 조작(자급).
    if os.environ.get("INDIEBIZ_PROFILE") == "phone":
        return _android_native(tool_input)

    op = (tool_input.get("op") or _OP_DEFAULTS["android_op"]).strip()
    device_id = tool_input.get("device_id")

    if op == "snapshot":
        return _snapshot(tool_input)

    if op == "tap":
        query = tool_input.get("query")
        if query:
            return _ui.find_and_tap(query, tool_input.get("index", 0), device_id)
        x, y = tool_input.get("x"), tool_input.get("y")
        if x is None or y is None:
            return {"success": False, "message": "tap엔 query(요소 라벨/id 일부) 또는 x,y 좌표가 필요합니다."}
        return _ui.tap(int(x), int(y), device_id)

    if op == "long_press":
        x, y = tool_input.get("x"), tool_input.get("y")
        if x is None or y is None:
            return {"success": False, "message": "long_press엔 x,y 좌표가 필요합니다."}
        return _ui.long_press(int(x), int(y), tool_input.get("duration_ms", 1000), device_id)

    if op == "type":
        return _ui.type_text(tool_input.get("text", ""), device_id)

    if op == "swipe":
        return _swipe(tool_input)

    if op == "key":
        return _ui.press_key(tool_input.get("key") or tool_input.get("keycode", ""), device_id)

    if op == "open_app":
        pkg = tool_input.get("package_name") or tool_input.get("package", "")
        return _ui.open_app(pkg, device_id)

    return {
        "success": False,
        "error": f"알 수 없는 op '{op}'. 사용 가능: snapshot/tap/type/swipe/key/long_press/open_app",
    }
