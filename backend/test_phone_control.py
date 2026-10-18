"""Phone control receipts and verified changes; hardware acceptance is separate."""
import boot_paths  # noqa: F401
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phone_control", ROOT / "data/instruments/phone_control.py")
controls = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controls)


class Audio:
    def __init__(self, value=9, maximum=15):
        self.value, self.maximum = value, maximum
        self.fixed = False
        self.ignore = False
        self.calls = []

    def getStreamMaxVolume(self, stream):
        return self.maximum

    def getStreamVolume(self, stream):
        return self.value

    def isVolumeFixed(self):
        return self.fixed

    def setStreamVolume(self, stream, target, flags):
        self.calls.append(target)
        if not self.ignore:
            self.value = target


def execute(tmp_path, audio, op, value=None):
    return controls.volume_control(audio, 3, str(tmp_path / "volume.json"), op, value)


def test_half_and_restore_survive_new_controller_call(tmp_path):
    audio = Audio()
    reduced = execute(tmp_path, audio, "half")
    assert reduced["actual"] == 4 and reduced["previous"] == 9
    assert execute(tmp_path, audio, "status")["can_restore"]
    restored = execute(tmp_path, audio, "restore")
    assert restored["actual"] == 9 and not restored["can_restore"]
    assert audio.calls == [4, 9]


def test_external_volume_change_prevents_stale_restore(tmp_path):
    audio = Audio()
    execute(tmp_path, audio, "half")
    audio.value = 6
    assert not execute(tmp_path, audio, "status")["can_restore"]
    with pytest.raises(ValueError, match="다른 곳"):
        execute(tmp_path, audio, "restore")
    assert audio.value == 6 and audio.calls == [4]


def test_phone_receipts_do_not_cross_devices(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir(); second.mkdir()
    a, b = Audio(), Audio(12, 30)
    execute(first, a, "half")
    assert not execute(second, b, "status")["can_restore"]
    execute(second, b, "mute")
    assert execute(second, b, "restore")["actual"] == 12
    assert execute(first, a, "restore")["actual"] == 9


def test_zero_boundary_noop_keeps_original_undo(tmp_path):
    audio = Audio(1)
    assert execute(tmp_path, audio, "half")["actual"] == 0
    assert execute(tmp_path, audio, "step", -1)["previous"] == 1
    assert execute(tmp_path, audio, "restore")["actual"] == 1


def test_os_rejected_change_is_not_reported_as_success(tmp_path):
    audio = Audio()
    execute(tmp_path, audio, "half")
    audio.ignore = True
    with pytest.raises(ValueError, match="실제"):
        execute(tmp_path, audio, "set", 2)
    assert execute(tmp_path, audio, "status")["previous"] == 9


@pytest.mark.parametrize("value", [-1, 16, True, "3.5", "__import__('os')"])
def test_invalid_levels_do_not_change_volume(tmp_path, value):
    audio = Audio()
    with pytest.raises((ValueError, TypeError)):
        execute(tmp_path, audio, "set", value)
    assert audio.calls == []


def test_fixed_volume_is_readable_but_not_writable(tmp_path):
    audio = Audio()
    audio.fixed = True
    assert execute(tmp_path, audio, "status")["fixed"]
    with pytest.raises(ValueError, match="변경할 수 없습니다"):
        execute(tmp_path, audio, "half")
    assert not (tmp_path / "volume.json").exists()


def test_receipt_precedes_mutation_for_lost_reply_recovery(tmp_path):
    audio = Audio()
    original = audio.setStreamVolume

    def interrupted(stream, target, flags):
        assert controls.read_receipt(str(tmp_path / "volume.json"))["previous"] == 9
        original(stream, target, flags)
        raise RuntimeError("connection lost after apply")

    audio.setStreamVolume = interrupted
    with pytest.raises(RuntimeError):
        execute(tmp_path, audio, "half")
    audio.setStreamVolume = original
    assert execute(tmp_path, audio, "restore")["actual"] == 9


def test_run_stream_receipts_and_vibration_are_independent(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace as NS
    class Streams(Audio):
        def __init__(self):
            super().__init__()
            self.levels = {3: 9, 4: 5, 2: 7, 5: 6}
        def getStreamVolume(self, stream):
            return self.levels[stream]
        def setStreamVolume(self, stream, target, flags):
            self.calls.append((stream, target))
            self.levels[stream] = target
    audio = Streams()
    vibrations = []
    services = {"audio": audio, "batterymanager": NS(getIntProperty=lambda _: 80),
                "vibrator": NS(hasVibrator=lambda: True, vibrate=vibrations.append)}
    context = NS(getFilesDir=lambda: NS(getAbsolutePath=lambda: str(tmp_path)),
                 getSystemService=services.get)
    classes = {"android.media.AudioManager": NS(STREAM_MUSIC=3, STREAM_ALARM=4, STREAM_RING=2, STREAM_NOTIFICATION=5),
               "android.os.Build": NS(MODEL="fixture"),
               "android.os.Build$VERSION": NS(SDK_INT=34, RELEASE="14"),
               "android.os.BatteryManager": NS(BATTERY_PROPERTY_CAPACITY=4),
               "android.os.VibrationEffect": NS(DEFAULT_AMPLITUDE=-1, createOneShot=lambda n, _: n)}
    monkeypatch.setitem(sys.modules, "java", NS(jclass=classes.__getitem__))
    monkeypatch.setitem(sys.modules, "indiebiz_android", NS(context=context))
    assert controls.run({"op": "half", "stream": "music"})["actual"] == 4
    alarm = controls.run({"op": "half", "stream": "alarm"})
    assert alarm["actual"] == 2 and alarm["stream"] == "alarm"
    assert controls.run({"op": "restore", "stream": "music"})["actual"] == 9
    assert controls.run({"op": "restore", "stream": "alarm"})["actual"] == 5
    assert audio.calls == [(3, 4), (4, 2), (3, 9), (4, 5)]
    for duration in [0, 1001, True, 1.5]:
        with pytest.raises((ValueError, TypeError)):
            controls.run({"op": "vibrate", "duration_ms": duration})
    assert vibrations == []
    controls.run({"op": "vibrate", "duration_ms": 100})
    assert vibrations == [100]


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
