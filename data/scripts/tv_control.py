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
from xml.sax.saxutils import escape


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
    request = urllib.request.Request(f'http://{cfg["ip"]}:8001{path}', method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def status(cfg):
    try:
        info = json.loads(rest(cfg, "GET", "/api/v2/"))["device"]
        power = str(info.get("PowerState", "unknown")).lower()
        if power not in {"on", "off", "standby"}:
            power = "unknown"
        out = {"reachable": True, "power": power, "verified": power != "unknown", "apps": {}}
    except (OSError, ValueError, KeyError, TypeError):
        return {"reachable": False, "power": "unknown", "verified": False, "apps": {},
                "message": "TV 응답 없음. 전원·네트워크 상태는 확인되지 않았습니다."}
    if power == "on":
        for name, app in cfg.get("apps", {}).items():
            try:
                state = app_state(cfg, app)
                out["apps"][name] = {k: state.get(k) for k in ("running", "visible")}
            except (OSError, ValueError):
                out["apps"][name] = {"running": None, "visible": None}
    return out


class Remote:
    """Bounded WebSocket transport, including ping/close and fragmented messages."""
    def __init__(self, cfg, token_sink):
        self.s = None
        try:
            name = base64.b64encode(cfg.get("client_name", "IndieBiz").encode()).decode()
            query = urllib.parse.urlencode({"name": name, **({"token": cfg["token"]} if cfg.get("token") else {})})
            # Samsung local TVs use a self-signed certificate; IP is an explicit registration.
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            raw = socket.create_connection((cfg["ip"], 8002), timeout=8)
            try:
                self.s = ctx.wrap_socket(raw, server_hostname=cfg["ip"])
            except Exception:
                raw.close()
                raise
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
            end = time.monotonic() + 35
            while time.monotonic() < end:
                event = json.loads(self._message(end))
                if event.get("event") == "ms.channel.connect":
                    token = (event.get("data") or {}).get("token")
                    if token and str(token) != cfg.get("token"):
                        token_sink(str(token))
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
            part = self.s.recv(count - len(chunks))
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


def send_keys(cfg, seq, token_sink):
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
    remote = Remote(cfg, token_sink)
    try:
        for key, wait in parsed:
            remote.key(key)
            time.sleep(wait)
    finally:
        remote.close()
    return {"sent": [k for k, _ in parsed], "verified": False,
            "message": "리모컨 명령 전달. 실제 화면·음량 변화는 확인되지 않았습니다."}


def wake(cfg, token_sink):
    initial = status(cfg)
    if initial["power"] == "on":
        return initial
    if not cfg.get("mac") or not cfg.get("broadcast"):
        raise ValueError("켜기에는 등록 설정의 MAC·브로드캐스트 주소가 필요합니다")
    packet = b"\xff" * 6 + bytes.fromhex(cfg["mac"].replace(":", "")) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for port in (9, 7):
            sock.sendto(packet, (cfg["broadcast"], port))
    # Power is a toggle: send at most once and only on explicit standby evidence.
    toggled = False
    end = time.monotonic() + 40
    while time.monotonic() < end:
        state = status(cfg)
        if state["power"] == "on":
            return state
        if state["power"] == "standby" and not toggled:
            toggled = True
            send_keys(cfg, ["KEY_POWER:2"], token_sink)
        time.sleep(2)
    return {**state, "success": False, "verified": False, "error": "켜짐 미확인. 변경 명령을 자동 반복하지 마세요."}


def app_state(cfg, app_id):
    return json.loads(rest(cfg, "GET", "/api/v2/applications/" + urllib.parse.quote(app_id, safe="")))


def soap(cfg, action, args):
    service = "urn:schemas-upnp-org:service:AVTransport:1"
    body = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<s:Body><u:{action} xmlns:u="{service}">{args}</u:{action}></s:Body></s:Envelope>')
    request = urllib.request.Request(f'http://{cfg["ip"]}:9197/upnp/control/AVTransport1', data=body.encode(),
                                    headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{service}#{action}"'})
    with urllib.request.urlopen(request, timeout=8) as response:
        response.read()


def execute(args, cfg, token_sink, root):
    op = args.get("op", "status")
    if op.startswith("epg_") and op in {"epg_now", "epg_channel", "epg_scan"}:
        import tv_epg as epg
        epg.CACHE_ROOT = root / "data/tv_epg"
        return {**epg.epg_op(args), "verified": True}
    if op == "status":
        return status(cfg)
    if op == "on":
        return wake(cfg, token_sink)
    if op == "pair":
        Remote({**cfg, "token": ""}, token_sink).close()
        return {"paired": True, "verified": True}
    if op not in {"off", "key", "volume", "mute", "launch", "to_pc", "dlna_play", "dlna_stop"}:
        raise ValueError("지원하지 않는 TV 동작입니다")
    if status(cfg)["power"] != "on":
        raise RuntimeError("TV 켜짐을 확인하지 못했습니다. 상태·연결을 확인하세요")
    if op == "off":
        sent = send_keys(cfg, ["KEY_POWER:2"], token_sink)
        state = status(cfg)
        verified = state["power"] in {"off", "standby"}
        return {**sent, **state, "verified": verified,
                "message": "전원 대기 확인" if verified else "전원 명령 전달. 꺼짐은 확인되지 않았습니다."}
    if op == "key":
        return send_keys(cfg, args.get("keys"), token_sink)
    if op == "volume":
        steps = args.get("steps")
        if type(steps) is not int or not 1 <= abs(steps) <= 10:
            raise ValueError("음량 증감은 -10~-1 또는 1~10 단계입니다")
        return send_keys(cfg, ["KEY_VOLUP" if steps > 0 else "KEY_VOLDOWN"] * abs(steps), token_sink)
    if op == "mute":
        return send_keys(cfg, ["KEY_MUTE"], token_sink)
    if op == "to_pc":
        index = cfg.get("pc_input_index")
        if index is None:
            raise ValueError("등록 설정에서 PC 입력 위치를 지정하세요")
        return send_keys(cfg, ["KEY_SOURCE:3"] + ["KEY_LEFT"] * 12 +
                         ["KEY_RIGHT"] * (index - 1) + ["KEY_ENTER:1"], token_sink)
    if op == "launch":
        app = str(args.get("app", ""))
        app_id = cfg.get("apps", {}).get(app.lower(), app)
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", app_id):
            raise ValueError("등록된 앱 이름 또는 앱 ID가 필요합니다")
        rest(cfg, "POST", "/api/v2/applications/" + app_id)
        for _ in range(10):
            time.sleep(1)
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
