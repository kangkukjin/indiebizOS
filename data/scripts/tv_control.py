"""Registered Samsung Tizen TV control shared by the app and AI.

stdin: {target: device_id, op: status/on/off/key/volume/mute/launch/to_pc/
        pair/dlna_play/dlna_stop/epg_now/epg_channel/epg_scan, ...}
Uses the controlling hub's private limb ledger. Never accepts a config/IP override.
The script can be copied to ~turn; INDIEBIZ_BASE_PATH locates the installed body.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import ssl
import struct
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

_transport = ContextVar("tv_transport", default=None)


def registry():
    base = os.environ.get("INDIEBIZ_BASE_PATH")
    root = Path(base) if base else Path(__file__).resolve().parents[2]
    if not (root / "backend" / "boot_paths.py").is_file():
        raise RuntimeError("허브 실행 환경(INDIEBIZ_BASE_PATH)이 필요합니다")
    sys.path.insert(0, str(root / "backend"))
    import boot_paths  # noqa: F401
    import hardware_registry
    return hardware_registry, root


def rest(cfg, method, path, timeout=4):
    if transport := _transport.get():
        return transport.request(f'http://{cfg["ip"]}:8001{path}', method=method, timeout=timeout).decode("utf-8", "replace")
    request = urllib.request.Request(f'http://{cfg["ip"]}:8001{path}', method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def power_status(cfg):
    """Read only power; app availability must not delay wake or key preconditions."""
    try:
        info = json.loads(rest(cfg, "GET", "/api/v2/"))["device"]
        power = str(info.get("PowerState", "unknown")).lower()
        if power not in {"on", "off", "standby"}:
            power = "unknown"
        out = {"reachable": True, "power": power, "verified": power != "unknown", "apps": {}}
    except (OSError, ValueError, KeyError, TypeError):
        return {"reachable": False, "power": "unknown", "verified": False, "apps": {},
                "message": "TV 응답 없음. 전원·네트워크 상태는 확인되지 않았습니다."}
    return out


def status(cfg):
    out = power_status(cfg)
    if out["power"] == "on":
        for name, app in cfg.get("apps", {}).items():
            try:
                state = app_state(cfg, app)
                out["apps"][name] = {k: state.get(k) for k in ("running", "visible")}
            except (OSError, ValueError):
                out["apps"][name] = {"running": None, "visible": None}
    return out


class ObservationError(Exception):
    """Public diagnostic code only; never include transport URLs or credentials."""

    def __init__(self, state, code):
        self.state, self.code = state, code


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def observation_request(url, *, data=None, headers=None):
    """Bounded reads; cloud credentials must never follow a redirect."""
    request = urllib.request.Request(url, data=data, headers=headers or {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        if transport := _transport.get():
            raw = transport.request(url, data=data, headers=headers, timeout=3)
        else:
            with opener.open(request, timeout=3) as response:
                raw = response.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise ObservationError("invalid_response", "response_too_large")
        return raw
    except urllib.error.HTTPError as exc:
        # SOAP faults commonly use HTTP 500; preserve their numeric code only.
        raw = exc.read(512 * 1024 + 1) if exc.code == 500 else b""
        if raw:
            root = observation_xml(raw)
            code = root.findtext(".//{*}errorCode")
            if code:
                raise ObservationError("unsupported" if code == "401" else "unavailable",
                                       "upnp_" + code if code.isdigit() else "upnp_fault") from None
        raise ObservationError("unauthorized" if exc.code in (401, 403) else "unavailable",
                               "http_" + str(exc.code)) from None
    except (OSError, ValueError):
        raise ObservationError("unavailable", "connection_failed") from None


def observation_xml(raw):
    declarations = raw.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in declarations or b"<!ENTITY" in declarations:
        raise ObservationError("invalid_response", "xml_declaration_rejected")
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise ObservationError("invalid_response", "invalid_xml") from None


def observation(value=None, *, state="observed", source="upnp", scope="tv", code=None,
                reported_at=None):
    result = {"value": value, "state": state, "verified": state == "observed",
              "source": source, "scope": scope,
              "observed_at": datetime.now(timezone.utc).isoformat()}
    if code:
        result["reason"] = code
    if reported_at is not None:
        result["reported_at"] = reported_at
    return result


def service_url(cfg, base, path):
    """TV advertisements may only point back to the registered TV on the same port."""
    try:
        url = urllib.parse.urljoin(base, path)
        parsed, origin = urllib.parse.urlsplit(url), urllib.parse.urlsplit(base)
        valid = (parsed.scheme == "http" and parsed.hostname == cfg["ip"] and
                 parsed.port == origin.port and not (parsed.username or parsed.password or parsed.fragment))
    except ValueError:
        valid = False
    if not valid:
        raise ObservationError("invalid_response", "foreign_service_url")
    return url


def observation_services(cfg):
    base = f'http://{cfg["ip"]}:9197/dmr'
    root = observation_xml(observation_request(base))
    if root.tag.split("}")[-1] != "root" or root.find("{*}device") is None:
        raise ObservationError("invalid_response", "invalid_device_description")
    services = {}
    for element in root.findall(".//{*}service"):
        urn = element.findtext("{*}serviceType", "")
        for name in ("RenderingControl", "AVTransport", "MainTVAgent2"):
            prefix = ("urn:samsung.com:service:" if name == "MainTVAgent2"
                      else "urn:schemas-upnp-org:service:")
            if not re.fullmatch(re.escape(prefix + name + ":") + r"\d+", urn):
                continue
            control, scpd = element.findtext("{*}controlURL"), element.findtext("{*}SCPDURL")
            if control and scpd:
                services[name] = {"urn": urn, "url": service_url(cfg, base, control),
                                  "scpd": service_url(cfg, base, scpd)}
    return services


def read_service(service):
    root = observation_xml(observation_request(service["scpd"]))
    if root.tag.split("}")[-1] != "scpd":
        raise ObservationError("invalid_response", "invalid_service_description")
    return {**service, "actions": {a.findtext("{*}name") for a in root.findall(".//{*}action")}}


def observation_soap(service, action, args):
    if action not in service["actions"]:
        raise ObservationError("unsupported", "action_not_advertised")
    urn = service["urn"]
    body = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
            f'<u:{action} xmlns:u="{urn}">{args}</u:{action}></s:Body></s:Envelope>')
    raw = observation_request(service["url"], data=body.encode(), headers={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{urn}#{action}"'})
    root = observation_xml(raw)
    if root.find(".//{*}Fault") is not None:
        code = root.findtext(".//{*}errorCode", "")
        raise ObservationError("unsupported" if code == "401" else "unavailable",
                               "upnp_" + code if code.isdigit() else "upnp_fault")
    response = root.find(f".//{{{urn}}}{action}Response")
    if response is None:
        raise ObservationError("invalid_response", "missing_action_response")
    values = {e.tag.split("}")[-1]: (e.text or "").strip() for e in response}
    if values.get("Result", "OK") != "OK":
        raise ObservationError("unavailable", "device_rejected_read")
    return values


def upnp_observations(cfg):
    # AVTransport observes its DLNA renderer, never arbitrary HDMI/native app playback.
    specs = {
        "volume": ("RenderingControl", "GetVolume", "CurrentVolume", "tv_audio"),
        "mute": ("RenderingControl", "GetMute", "CurrentMute", "tv_audio"),
        "input_source": ("MainTVAgent2", "GetCurrentExternalSource", "CurrentExternalSource", "tv_input"),
        "dlna_transport": ("AVTransport", "GetTransportInfo", "CurrentTransportState", "dlna_renderer"),
        "dlna_position": ("AVTransport", "GetPositionInfo", None, "dlna_renderer"),
    }
    try:
        services = observation_services(cfg)
    except ObservationError as exc:
        return {key: observation(state=exc.state, scope=spec[3], code=exc.code)
                for key, spec in specs.items()}

    def load(pair):
        name, service = pair
        try:
            return name, read_service(service)
        except ObservationError as exc:
            return name, exc

    with ThreadPoolExecutor(max_workers=3) as pool:
        services = dict(f.result() for f in [pool.submit(copy_context().run, load, pair) for pair in services.items()])

    def read(pair):
        key, (name, action, field, scope) = pair
        try:
            if name not in services:
                raise ObservationError("unsupported", "service_not_advertised")
            service = services[name]
            if isinstance(service, ObservationError):
                raise service
            args = "" if name == "MainTVAgent2" else "<InstanceID>0</InstanceID>"
            if name == "RenderingControl":
                args += "<Channel>Master</Channel>"
            values = observation_soap(service, action, args)
            value = values.get(field) if field else {
                "position": values.get("RelTime"), "duration": values.get("TrackDuration"),
                "track": values.get("Track")}
            if key == "volume":
                if not isinstance(value, str) or not value.isdigit() or not 0 <= int(value) <= 100:
                    raise ValueError()
                value = int(value)
            elif key == "mute":
                if value not in ("0", "1", "true", "false"):
                    raise ValueError()
                value = value in ("1", "true")
            elif key == "dlna_position":
                if not value["position"] or not value["duration"] or value["position"] == "NOT_IMPLEMENTED":
                    raise ValueError()
            elif not value:
                raise ValueError()
            return key, observation(value, scope=scope)
        except ObservationError as exc:
            return key, observation(state=exc.state, scope=scope, code=exc.code)
        except (ValueError, TypeError):
            return key, observation(state="invalid_response", scope=scope, code="missing_or_invalid_value")

    with ThreadPoolExecutor(max_workers=5) as pool:
        return dict(f.result() for f in [pool.submit(copy_context().run, read, pair) for pair in specs.items()])


def cloud_observations(cfg):
    """Optional SmartThings last-reported state; fetching is not a fresh TV observation."""
    specs = {"volume": ("audioVolume", "volume"), "mute": ("audioMute", "mute"),
             "input_source": ("mediaInputSource", "inputSource"),
             "media_playback": ("mediaPlayback", "playbackStatus")}
    auth = cfg.get("smartthings")
    def absent(state, code):
        return {key: observation(state=state, source="smartthings", scope="cloud_last_reported", code=code)
                for key in specs}
    if not auth:
        return absent("not_configured", "smartthings_not_configured")
    try:
        raw = observation_request("https://api.smartthings.com/v1/devices/" + auth["device_id"] + "/status",
                                  headers={"Authorization": "Bearer " + auth["token"]})
        payload = json.loads(raw)
        main = payload["components"]["main"]
        if not isinstance(main, dict):
            raise ValueError()
    except ObservationError as exc:
        return absent(exc.state, exc.code)
    except (ValueError, KeyError, TypeError):
        return absent("invalid_response", "invalid_cloud_status")
    out = {}
    for key, (capability, attribute) in specs.items():
        group = main.get(capability)
        item = group.get(attribute) if isinstance(group, dict) else None
        if capability not in main:
            state, value, stamp = "unsupported", None, None
        elif not isinstance(item, dict) or item.get("value") is None:
            state, value, stamp = "unavailable", None, None
        else:
            state, value, stamp = "reported", item["value"], item.get("timestamp")
            if key == "mute" and value in ("muted", "unmuted"):
                value = value == "muted"
            valid = ((key == "volume" and type(value) in (int, float) and 0 <= value <= 100)
                     or (key == "mute" and type(value) is bool)
                     or (key in ("input_source", "media_playback") and isinstance(value, str) and 0 < len(value) <= 100))
            if not valid:
                state, value = "invalid_response", None
            if not isinstance(stamp, str):
                stamp = None
        out[key] = observation(value, state=state, source="smartthings", scope="cloud_last_reported",
                               reported_at=stamp)
        # Explicit even when the cloud omitted its update time.
        out[key]["reported_at"] = stamp
    return out


def detailed_status(cfg):
    with ThreadPoolExecutor(max_workers=3) as pool:
        basic_job = pool.submit(copy_context().run, status, cfg)
        local_job = pool.submit(copy_context().run, upnp_observations, cfg)
        cloud_job = pool.submit(copy_context().run, cloud_observations, cfg)
        result, local, cloud = basic_job.result(), local_job.result(), cloud_job.result()
    observations = dict(local)
    for key, item in cloud.items():
        if key not in observations or (observations[key]["state"] != "observed" and item["state"] == "reported"):
            observations[key] = item
    result.update(observations=observations, cloud_observations=cloud,
                  local_observations=local, verification_scope="power_only",
                  message=result.get("message", "") + " 각 항목의 state·scope를 확인하세요. DLNA 상태는 HDMI/유튜브 재생 상태가 아닙니다. "
                          "SmartThings 값은 reported_at 시점의 마지막 보고이며 현재 화면·소리를 검증하지 않습니다.")
    # Keep the old reachable meaning (Samsung REST endpoint), do not let cloud data turn it on.
    return result


class Remote:
    """Bounded WebSocket transport, including ping/close and fragmented messages."""
    def __init__(self, cfg, token_sink, *, check=None, deadline=None):
        self.s = None
        self.check = check or (lambda: None)
        self.deadline = deadline
        self.read_end = deadline or time.monotonic() + 8
        try:
            name = base64.b64encode(cfg.get("client_name", "IndieBiz").encode()).decode()
            query = urllib.parse.urlencode({"name": name, **({"token": cfg["token"]} if cfg.get("token") else {})})
            # Samsung local TVs use a self-signed certificate; IP is an explicit registration.
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self.check()
            timeout = min(8, max(.01, deadline - time.monotonic())) if deadline else 8
            raw = socket.create_connection((cfg["ip"], 8002), timeout=timeout)
            try:
                self.check()
                if deadline:
                    raw.settimeout(max(.01, min(8, deadline - time.monotonic())))
                self.s = ctx.wrap_socket(raw, server_hostname=cfg["ip"])
            except Exception:
                raw.close()
                raise
            self.check()
            self.read_end = min(deadline or float("inf"), time.monotonic() + 8)
            key = base64.b64encode(os.urandom(16)).decode()
            request = (f"GET /api/v2/channels/samsung.remote.control?{query} HTTP/1.1\r\n"
                       f'Host: {cfg["ip"]}:8002\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                       f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
            self.s.sendall(request.encode())
            header = b""
            while not header.endswith(b"\r\n\r\n"):
                header += self._n(1)
                if len(header) > 16384:
                    raise ValueError("WebSocket 응답 헤더 초과")
            lines = header.decode("latin1").split("\r\n")
            headers = {k.lower(): v.strip() for line in lines[1:] if ":" in line for k, v in [line.split(":", 1)]}
            accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            if " 101 " not in lines[0] or headers.get("sec-websocket-accept") != accept:
                raise RuntimeError("TV WebSocket 연결 확인 실패")
            end = min(time.monotonic() + 35, deadline or float("inf"))
            while time.monotonic() < end:
                event = json.loads(self._message(end))
                if event.get("event") == "ms.channel.connect":
                    token = (event.get("data") or {}).get("token")
                    if token and str(token) != cfg.get("token"):
                        token_sink(str(token))
                    self.check()
                    return
                if event.get("event") in {"ms.channel.unauthorized", "ms.channel.timeOut"}:
                    raise PermissionError("TV 화면에서 연결을 허용한 뒤 페어링을 다시 요청하세요")
            raise TimeoutError("TV 연결 승인 대기 시간 초과")
        except Exception:
            self.close()
            raise

    def close(self):
        if self.s:
            self.s.close()
            self.s = None

    def _n(self, count):
        chunks = bytearray()
        while len(chunks) < count:
            if hasattr(self, "check"):
                self.check()
                if time.monotonic() >= self.read_end:
                    raise TimeoutError("TV 응답 대기 시간 초과")
                self.s.settimeout(min(.25, max(.01, self.read_end - time.monotonic())))
            try:
                part = self.s.recv(count - len(chunks))
            except socket.timeout:
                if not hasattr(self, "check"):
                    raise
                continue
            if not part:
                raise EOFError("TV 연결 종료")
            chunks.extend(part)
        return bytes(chunks)

    def _send(self, payload, opcode=1):
        mask = os.urandom(4)
        size = len(payload)
        header = bytes([0x80 | opcode]) + (bytes([0x80 | size]) if size < 126
                                         else bytes([0xfe]) + struct.pack(">H", size))
        self.s.sendall(header + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(payload)))

    def _message(self, end):
        self.read_end = end
        data = bytearray()
        while time.monotonic() < end:
            self.s.settimeout(max(.1, end - time.monotonic()))
            head = self._n(2)
            size = head[1] & 127
            if size == 126:
                size = struct.unpack(">H", self._n(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", self._n(8))[0]
            if size > 1048576 or len(data) + size > 1048576 or head[1] & 128:
                raise ValueError("TV WebSocket 프레임 오류")
            payload = self._n(size)
            opcode = head[0] & 15
            if opcode == 8:
                raise EOFError("TV 연결 종료")
            if opcode == 9:
                self._send(payload, 10)
                continue
            if opcode == 10:
                continue
            if opcode not in (0, 1):
                raise ValueError("TV WebSocket 메시지 형식 오류")
            data.extend(payload)
            if head[0] & 128:
                return data.decode("utf-8")
        raise TimeoutError("TV 연결 승인 대기 시간 초과")

    def key(self, key):
        self._send(json.dumps({"method": "ms.remote.control", "params": {
            "Cmd": "Click", "DataOfCmd": key, "Option": "false", "TypeOfRemote": "SendRemoteKey"}}).encode())


def parse_keys(seq):
    if not isinstance(seq, list) or not 1 <= len(seq) <= 40:
        raise ValueError("keys는 1~40개 키 목록입니다")
    parsed = []
    for item in seq:
        key, _, delay = str(item).partition(":")
        if not re.fullmatch(r"KEY_[A-Z0-9_]{1,40}", key):
            raise ValueError("지원하는 리모컨 키 형식은 KEY_이름입니다")
        wait = float(delay or .4)
        if not 0 <= wait <= 5:
            raise ValueError("키 간 대기는 0~5초입니다")
        parsed.append((key, wait))
    return parsed


def send_keys(cfg, seq, token_sink):
    parsed = parse_keys(seq)
    remote = Remote(cfg, token_sink)
    try:
        for key, wait in parsed:
            remote.key(key)
            time.sleep(wait)
    finally:
        remote.close()
    return {"sent": [k for k, _ in parsed], "verified": False,
            "message": "리모컨 명령 전달. 실제 화면·음량 변화는 확인되지 않았습니다."}


def wake(cfg, token_sink, *, send=None, sleep=None, transport=None):
    send = send or send_keys
    sleep = sleep or time.sleep
    initial = power_status(cfg)
    if initial["power"] == "on":
        return initial
    if not cfg.get("mac") or not cfg.get("broadcast"):
        raise ValueError("켜기에는 등록 설정의 MAC·브로드캐스트 주소가 필요합니다")
    packet = b"\xff" * 6 + bytes.fromhex(cfg["mac"].replace(":", "")) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for port in (9, 7):
            if transport:
                transport.before_change()
            sock.sendto(packet, (cfg["broadcast"], port))
    # Power is a toggle: send at most once and only on explicit standby evidence.
    toggled = False
    end = time.monotonic() + 40
    while time.monotonic() < end:
        state = power_status(cfg)
        if state["power"] == "on":
            return state
        if state["power"] == "standby" and not toggled:
            toggled = True
            send(cfg, ["KEY_POWER:2"], token_sink)
        sleep(2)
    return {**state, "success": False, "verified": False, "error": "켜짐 미확인. 변경 명령을 자동 반복하지 마세요."}


def app_state(cfg, app_id):
    return json.loads(rest(cfg, "GET", "/api/v2/applications/" + urllib.parse.quote(app_id, safe="")))


def soap(cfg, action, args):
    service = "urn:schemas-upnp-org:service:AVTransport:1"
    body = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<s:Body><u:{action} xmlns:u="{service}">{args}</u:{action}></s:Body></s:Envelope>')
    request = urllib.request.Request(f'http://{cfg["ip"]}:9197/upnp/control/AVTransport1', data=body.encode(),
                                    headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{service}#{action}"'})
    if transport := _transport.get():
        transport.request(request.full_url, data=body.encode(), headers=dict(request.header_items()), timeout=8)
    else:
        with urllib.request.urlopen(request, timeout=8) as response:
            response.read()


def execute(args, cfg, token_sink, root, *, transport=None):
    send = transport.send_keys if transport else send_keys
    sleep = transport.sleep if transport else time.sleep
    op = args.get("op", "status")
    if op.startswith("epg_") and op in {"epg_now", "epg_channel", "epg_scan"}:
        import tv_epg as epg
        epg.CACHE_ROOT = root / "data/tv_epg"
        return {**epg.epg_op(args), "verified": True}
    if op == "status":
        return detailed_status(cfg)
    if op == "on":
        return wake(cfg, token_sink, send=send, sleep=sleep, transport=transport)
    if op == "pair":
        transport.pair(cfg, token_sink) if transport else Remote({**cfg, "token": ""}, token_sink).close()
        return {"paired": True, "verified": True}
    if op not in {"off", "key", "volume", "mute", "launch", "to_pc", "dlna_play", "dlna_stop"}:
        raise ValueError("지원하지 않는 TV 동작입니다")
    if power_status(cfg)["power"] != "on":
        raise RuntimeError("TV 켜짐을 확인하지 못했습니다. 상태·연결을 확인하세요")
    if op == "off":
        sent = send(cfg, ["KEY_POWER:2"], token_sink)
        state = power_status(cfg)
        verified = state["power"] in {"off", "standby"}
        return {**sent, **state, "verified": verified,
                "message": "전원 대기 확인" if verified else "전원 명령 전달. 꺼짐은 확인되지 않았습니다."}
    if op == "key":
        return send(cfg, args.get("keys"), token_sink)
    if op == "volume":
        steps = args.get("steps")
        if type(steps) is not int or not 1 <= abs(steps) <= 10:
            raise ValueError("음량 증감은 -10~-1 또는 1~10 단계입니다")
        return send(cfg, ["KEY_VOLUP" if steps > 0 else "KEY_VOLDOWN"] * abs(steps), token_sink)
    if op == "mute":
        return send(cfg, ["KEY_MUTE"], token_sink)
    if op == "to_pc":
        index = cfg.get("pc_input_index")
        if index is None:
            raise ValueError("등록 설정에서 PC 입력 위치를 지정하세요")
        return send(cfg, ["KEY_SOURCE:3"] + ["KEY_LEFT"] * 12 +
                         ["KEY_RIGHT"] * (index - 1) + ["KEY_ENTER:1"], token_sink)
    if op == "launch":
        app = str(args.get("app", ""))
        app_id = cfg.get("apps", {}).get(app.lower(), app)
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", app_id):
            raise ValueError("등록된 앱 이름 또는 앱 ID가 필요합니다")
        rest(cfg, "POST", "/api/v2/applications/" + app_id)
        for _ in range(10):
            sleep(1)
            if app_state(cfg, app_id).get("visible") is True:
                return {"app": app, "visible": True, "verified": True,
                        "message": "앱 화면 표시 확인. 영상 재생은 별도 확인이 필요합니다."}
        return {"success": False, "app": app, "visible": False, "verified": False, "error": "앱 표시 미확인"}
    if op == "dlna_play":
        url = str(args.get("url", ""))
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or any(ord(c) < 32 for c in url):
            raise ValueError("인증 정보 없는 HTTP(S) 미디어 주소가 필요합니다")
        uri = escape(url)
        didl = escape('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
                      'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
                      '<item id="0" parentID="-1" restricted="1"><dc:title>IndieBiz</dc:title>'
                      '<upnp:class>object.item.videoItem</upnp:class><res protocolInfo="http-get:*:video/mp4:*">'
                      + uri + '</res></item></DIDL-Lite>')
        soap(cfg, "SetAVTransportURI", f"<InstanceID>0</InstanceID><CurrentURI>{uri}</CurrentURI><CurrentURIMetaData>{didl}</CurrentURIMetaData>")
        soap(cfg, "Play", "<InstanceID>0</InstanceID><Speed>1</Speed>")
    else:
        soap(cfg, "Stop", "<InstanceID>0</InstanceID>")
    return {"verified": False, "message": "DLNA 요청 전달. TV의 실제 재생 상태는 별도 확인하세요."}


def run(args):
    store, root = registry()
    if any(k in args for k in ("config", "ip", "token", "base")):
        raise ValueError("연결 설정 대신 손발에 등록된 target을 지정하세요")
    rec = store.connection(args.get("target"))
    if rec["driver"] != "samsung-tizen":
        raise ValueError("이 스크립트가 지원하지 않는 기기입니다")
    result = execute(args, rec["connection"], lambda token: store.save_token(rec["device_id"], token), root)
    if "reachable" in result:
        store.observe(rec["device_id"], result["reachable"])
    return {"success": True, "op": args.get("op", "status"), "target": rec["device_id"], **result}


if __name__ == "__main__":
    try:
        result = run(json.loads(sys.stdin.read() or "{}"))
    except Exception as exc:
        # Do not echo transport URLs or tokens in exceptions.
        safe = str(exc) if isinstance(exc, (ValueError, PermissionError, RuntimeError)) else "TV 연결 또는 응답 처리 실패. 상태를 조회하고 변경 명령은 자동 반복하지 마세요."
        result = {"success": False, "verified": False, "error": safe}
    text = json.dumps(result, ensure_ascii=False)
    print(text)
    if dest := os.environ.get("INDIEBIZ_SCRIPT_RESULT"):
        Path(dest + ".tmp").write_text(text, encoding="utf-8")
        os.replace(dest + ".tmp", dest)
