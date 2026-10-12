"""Resident live desktop worker: X11 or the user's Wayland RemoteDesktop portal."""
import base64
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import gi

gi.require_version('Gst', '1.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gst

Gst.init(None)


class Desktop:
    def __init__(self, root):
        self.buttons = 0
        self.held = set()
        self.codes = {}
        self.session = None
        self.fd = None
        self.pipeline = None
        self.wayland = bool(os.environ.get('WAYLAND_DISPLAY'))
        try:
            if self.wayland:
                self.portal(root)
            else:
                screen = Gdk.Screen.get_default()
                if screen is None:
                    raise RuntimeError('로그인한 그래픽 데스크톱이 없습니다.')
                self.width, self.height = screen.get_width(), screen.get_height()
                self.start_pipeline('ximagesrc use-damage=false show-pointer=true')
        except Exception:
            self.close()
            raise

    def start_pipeline(self, source):
        width = min(1600, self.width)
        height = max(1, self.height * width // self.width)
        self.pipeline = Gst.parse_launch(source + f' ! videorate drop-only=true ! video/x-raw,framerate=15/1 ! videoconvert ! videoscale ! video/x-raw,width={width},height={height},pixel-aspect-ratio=1/1 ! jpegenc quality=65 ! appsink name=frames drop=true max-buffers=1 sync=false')
        self.frames = self.pipeline.get_by_name('frames')
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError('화면 캡처를 시작하지 못했습니다.')

    def portal(self, root):
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        DBusGMainLoop(set_as_default=True)
        self.dbus = dbus
        self.bus = dbus.SessionBus()
        self.loop = GLib.MainLoop()
        threading.Thread(target=self.loop.run, daemon=True).start()
        obj = self.bus.get_object('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop')
        self.remote = dbus.Interface(obj, 'org.freedesktop.portal.RemoteDesktop')
        self.cast = dbus.Interface(obj, 'org.freedesktop.portal.ScreenCast')
        self.session = self.request(self.remote.CreateSession, options={'session_handle_token': 'ib' + uuid.uuid4().hex})['session_handle']
        options = {'types': dbus.UInt32(3)}
        props = dbus.Interface(obj, 'org.freedesktop.DBus.Properties')
        token_path = Path(root) / 'screen-portal-token'
        if int(props.Get('org.freedesktop.portal.RemoteDesktop', 'version')) >= 2:
            options['persist_mode'] = dbus.UInt32(2)
            if token_path.is_file():
                options['restore_token'] = token_path.read_text()
        self.request(self.remote.SelectDevices, self.session, options=options)
        self.request(self.cast.SelectSources, self.session, options={'types': dbus.UInt32(1), 'multiple': False, 'cursor_mode': dbus.UInt32(2)})
        selected = self.request(self.remote.Start, self.session, '', options={})
        if int(selected.get('devices', 0)) & 3 != 3 or not selected.get('streams'):
            raise RuntimeError('화면·마우스·키보드 공유 권한이 필요합니다.')
        if selected.get('restore_token'):
            fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(str(selected['restore_token']))
        self.node, properties = selected['streams'][0]
        size = properties.get('logical_size') or properties.get('size')
        if not size or len(size) != 2 or min(size) <= 0:
            raise RuntimeError('공유할 모니터의 크기를 확인할 수 없습니다.')
        self.width, self.height = map(int, size)
        self.fd = self.cast.OpenPipeWireRemote(self.session, {}).take()
        self.start_pipeline(f'pipewiresrc fd={self.fd} path={int(self.node)} do-timestamp=true')

    def request(self, method, *args, options):
        token = 'ib' + uuid.uuid4().hex
        sender = self.bus.get_unique_name()[1:].replace('.', '_')
        path = '/org/freedesktop/portal/desktop/request/' + sender + '/' + token
        done, result = threading.Event(), {}
        def receive(code, values):
            result.update(code=int(code), values=values)
            done.set()
        match = self.bus.add_signal_receiver(receive, signal_name='Response', dbus_interface='org.freedesktop.portal.Request', path=path)
        try:
            method(*args, {**options, 'handle_token': token})
            if not done.wait(120) or result.get('code') != 0:
                raise RuntimeError('화면 공유 권한을 허용해 주세요.')
            return result['values']
        finally:
            match.remove()

    def notify(self, method, *args):
        getattr(self.remote, method)(self.session, {}, *args)

    def xtool(self, *args):
        subprocess.run(['xdotool', *map(str, args)], check=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def key(self, key, down):
        if self.wayland:
            self.notify('NotifyKeyboardKeysym', self.dbus.Int32(key), self.dbus.UInt32(int(down)))
        else:
            self.xtool('keydown' if down else 'keyup', hex(key))
        if down:
            self.held.add(key)
        else:
            self.held.discard(key)

    def button(self, button, down):
        if self.wayland:
            self.notify('NotifyPointerButton', self.dbus.Int32([272, 273, 274][button]), self.dbus.UInt32(int(down)))
        else:
            self.xtool('mousedown' if down else 'mouseup', [1, 3, 2][button])

    def reset(self):
        for key in list(self.held):
            self.key(key, False)
        for button in range(3):
            if self.buttons & (1 << button):
                self.button(button, False)
        self.buttons = 0
        self.codes.clear()

    def execute(self, message):
        kind = message['type']
        if kind == 'frame':
            sample = self.frames.emit('try-pull-sample', 5 * Gst.SECOND)
            if sample is None:
                raise RuntimeError('화면 캡처 응답이 없습니다.')
            buffer = sample.get_buffer()
            return {'image': base64.b64encode(buffer.extract_dup(0, buffer.get_size())).decode('ascii')}
        if kind == 'reset':
            self.reset()
        elif kind == 'pointer':
            x, y = message.get('x', 0) * (self.width - 1), message.get('y', 0) * (self.height - 1)
            if self.wayland:
                self.notify('NotifyPointerMotionAbsolute', self.dbus.UInt32(self.node), self.dbus.Double(x), self.dbus.Double(y))
            else:
                self.xtool('mousemove', int(x), int(y))
            next_buttons = message.get('buttons', 0)
            for button in range(3):
                if (next_buttons ^ self.buttons) & (1 << button):
                    self.button(button, bool(next_buttons & (1 << button)))
            self.buttons = next_buttons
        elif kind == 'wheel':
            dx, dy = message.get('dx', 0), message.get('dy', 0)
            if self.wayland:
                self.notify('NotifyPointerAxis', self.dbus.Double(dx / 10), self.dbus.Double(dy / 10))
            else:
                for delta, positive, negative in ((dx, 7, 6), (dy, 5, 4)):
                    if delta:
                        self.xtool('click', '--repeat', min(20, max(1, int(abs(delta) / 40))), positive if delta > 0 else negative)
        elif kind == 'key':
            name = message.get('key', '')
            names = {'Enter': 'Return', 'Backspace': 'BackSpace', 'ArrowLeft': 'Left', 'ArrowRight': 'Right', 'ArrowUp': 'Up', 'ArrowDown': 'Down', 'PageUp': 'Page_Up', 'PageDown': 'Page_Down', ' ': 'space'}
            code = message.get('code', '')
            for prefix, xname in [('Control', 'Control'), ('Shift', 'Shift'), ('Alt', 'Alt'), ('Meta', 'Super')]:
                if code.startswith(prefix):
                    name = xname + ('_R' if code.endswith('Right') else '_L')
            key = Gdk.keyval_from_name(names.get(name, name))
            if len(name) == 1:
                key = Gdk.unicode_to_keyval(ord(name))
            if key and name not in ('Dead', 'Unidentified'):
                down = bool(message.get('down'))
                if down:
                    key = self.codes.setdefault(code, key)
                else:
                    key = self.codes.pop(code, key)
                self.key(key, down)
        elif kind == 'text':
            for char in message.get('text', ''):
                key = Gdk.unicode_to_keyval(ord(char))
                self.key(key, True)
                self.key(key, False)
        return {}

    def close(self):
        try:
            self.reset()
        finally:
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
            if self.session:
                self.dbus.Interface(self.bus.get_object('org.freedesktop.portal.Desktop', self.session), 'org.freedesktop.portal.Session').Close()
                self.loop.quit()
            if self.fd is not None:
                os.close(self.fd)


def main():
    desktop = None
    try:
        desktop = Desktop(sys.argv[1])
        if '--permissions' in sys.argv:
            return
        for line in sys.stdin:
            try:
                result = desktop.execute(json.loads(line))
            except Exception:
                result = {'error': '화면 공유 권한이나 그래픽 세션을 확인하세요.'}
            print(json.dumps(result, ensure_ascii=False), flush=True)
    except Exception:
        print(json.dumps({'error': '화면 공유 권한이나 필수 구성요소를 확인하세요.'}, ensure_ascii=False), flush=True)
        raise SystemExit(1)
    finally:
        if desktop:
            desktop.close()


if __name__ == '__main__':
    main()
