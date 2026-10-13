#!/usr/bin/env python3
"""폰을 이 중앙 PC 의 손발(limb)로 등록 — USB 설치 때 1회 (2026-10-13).

설계: docs/INDIEBIZ_BODY_AS_LIMB_DESIGN_2026_10_13.md §4·§보안.

이 스크립트는 **허브(중앙 PC) 에서** 돈다. 하드웨어적으로(USB) 연결된 폰에만 자격을 심는다.
등록 조건은 헬퍼 PC 와 같은 둘뿐이다 — "허브가 만든 자격 + 대상 기기에 물리 접근". 비밀번호 단계는 두지
않는다(2026-10-13 사용자 확정: 허브를 이미 쥔 사람에게 허브 비밀번호를 묻는 건 아무것도 더 막지 못하고,
기기마다 등록용 비밀번호를 두면 "비밀번호만 알면 남의 하드웨어를 입양" 하는 길을 여는 꼴이다):
  1) 폰이 USB 로 붙어 있고 IndieBiz 앱이 설치돼 있는지 확인한다.
  2) 1회용 초대(resident_invite)를 만들고 바로 이 설치(installation_id)에 묶어 실행 키로 바꾼다
     (resident_enroll, kind=phone, adapter=indiebiz-v1). 초대는 이 자리에서 소진된다 —
     폰에도 USB 에도 재사용 가능한 등록 키가 남지 않는다.
  3) 실행 자격 {hub, key, installation_id, alias, device_id} 를 adb run-as 로 폰 app-private
     files/secrets/limb_client.json 에 넣는다(keys.json 과 같은 자리). 폰 backend 의
     limb_client 가 부팅 때 이 파일을 보고 허브 하나에만 아웃바운드로 붙는다.
  4) 앱을 재시작해 손발 루프를 띄운다.

폐기 = 허브에서 [self:limb]{op:"remove", target:"<이름>"} 또는 revoke — 폰은 다음 sync 에서 자격을 지운다.

사용:  python3 phone-companion/scripts/provision_phone_limb.py --alias 삼성1 [--hub https://...] [--serial S]
"""
import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("INDIEBIZ_BASE_PATH", str(ROOT))
import boot_paths  # noqa: E402,F401

PKG = "com.indiebiz.phoneagent"
ADAPTER = "indiebiz-v1"


def _adb(serial, *args, check=True, capture=True):
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def _hub_base(explicit: str) -> str:
    if explicit:
        base = explicit.rstrip("/")
    else:
        import resident_pcs
        base = (resident_pcs.public_base() or "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise SystemExit("[limb] 폰이 접속할 허브 주소가 없습니다 — --hub 로 주거나 공개 얼굴(터널)을 설정하세요.")
    return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alias", required=True, help="허브에서 부를 이름 (예: 삼성1)")
    ap.add_argument("--hub", default="", help="폰이 붙을 허브 주소 (기본=공개 얼굴 HTTPS 터널)")
    ap.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", ""), help="adb 시리얼(폰 여러 대일 때)")
    ap.add_argument("--no-restart", action="store_true")
    ap.add_argument("--replace", action="store_true",
                    help="같은 이름의 기존 등록이 있으면 해제·폐기하고 새로 등록 (허브 주소를 바꿀 때)")
    args = ap.parse_args()

    alias = args.alias.strip()
    if not 1 <= len(alias) <= 80:
        raise SystemExit("[limb] 이름은 1~80자")

    # 0) 폰이 USB 로 붙어 있는가 — 하드웨어 연결이 등록의 전제
    devs = _adb(args.serial, "get-state", check=False).stdout.strip()
    if devs != "device":
        raise SystemExit("[limb] adb 디바이스 미연결 — USB 연결 + USB 디버깅 허용 뒤 다시.")
    abis = _adb(args.serial, "shell", "getprop", "ro.product.cpu.abilist").stdout.strip()
    installed = _adb(args.serial, "shell", "pm", "list", "packages", PKG, check=False).stdout
    if PKG not in installed:
        raise SystemExit("[limb] 폰에 IndieBiz 앱이 없습니다 — setup_phone.sh 로 먼저 설치하세요.")

    import limb_keys
    base = _hub_base(args.hub)

    # 0b) 같은 이름의 기존 등록 — --replace 면 허브에서 해제·폐기(옛 실행 키 무효화) 뒤 새로 심는다.
    #     앱을 먼저 멈춰 옛 손발 루프가 새 자격 파일을 지우는 경합을 막는다.
    existing = [r for r in limb_keys.list_keys(include_revoked=False)
                if r.get("alias") == alias and r.get("registration")
                and r["registration"].get("state") != "removed"]
    if existing:
        if not args.replace:
            raise SystemExit(f"[limb] '{alias}' 은(는) 이미 등록돼 있습니다 — 허브 주소를 바꾸려면 --replace.")
        _adb(args.serial, "shell", "am", "force-stop", PKG, check=False)
        import resident_pcs
        for r in existing:
            try:
                resident_pcs.remove(r["device_id"])
            except ValueError:
                pass
            limb_keys.revoke(r["device_id"])
        print(f"[limb] 기존 등록 {len(existing)}건 해제·폐기: {alias}")

    # 1) 1회용 초대 → 이 설치에 묶인 실행 키 (초대는 여기서 소진)
    installation_id = secrets.token_hex(16)
    invite = limb_keys.resident_invite(alias, ttl_days=0)
    try:
        bound = limb_keys.resident_enroll(invite["key"], installation_id, alias,
                                          kind="phone", adapter=ADAPTER)
    except ValueError as e:
        limb_keys.revoke(invite["device_id"])
        raise SystemExit(f"[limb] 등록 실패: {e}")
    limb_keys.revoke(invite["device_id"])  # 초대 레코드는 더 쓸 일 없음 — 원장에서 닫는다

    payload = {"hub": base, "key": bound["key"], "installation_id": installation_id,
               "alias": bound["alias"], "device_id": bound["device_id"],
               "generation": bound["registration"]["generation"], "adapter": ADAPTER,
               "abi": abis, "enrolled_at": __import__("time").time()}

    # 2) 폰 app-private 로 (run-as = 디버그 빌드)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        tf.write(json.dumps(payload, ensure_ascii=False, indent=2))
        tmp = tf.name
    tmp_dev = "/data/local/tmp/_limb_client.json"
    try:
        _adb(args.serial, "push", tmp, tmp_dev)
        inner = (f"mkdir -p files/secrets && chmod 700 files/secrets "
                 f"&& cp {tmp_dev} files/secrets/limb_client.json "
                 f"&& chmod 600 files/secrets/limb_client.json && echo PUSHED")
        out = _adb(args.serial, "shell", f"run-as {PKG} sh -c '{inner}'", check=False)
        if "PUSHED" not in out.stdout:
            limb_keys.revoke(bound["device_id"])
            raise SystemExit(f"[limb] 폰에 자격을 못 심었습니다(run-as 실패) — 등록을 되돌렸습니다.\n{out.stdout}{out.stderr}")
    finally:
        _adb(args.serial, "shell", "rm", "-f", tmp_dev, check=False)
        os.unlink(tmp)

    # 3) 앱 재시작 → 손발 루프
    if not args.no_restart:
        _adb(args.serial, "shell", "am", "force-stop", PKG, check=False)
        _adb(args.serial, "shell", "am", "start", "-n", f"{PKG}/.MainActivity", check=False)

    print(f"[limb] 등록 완료: '{bound['alias']}' ({bound['device_id']}) → {base}")
    print("[limb] 허브에서 확인: [self:limb]{op:\"list\"}  ·  명령: [limbs:guestpc]{op:\"ibl\", limb:\"%s\", code:\"[limbs:phone]{op:'vibrate'}\"}" % bound["alias"])
    print("[limb] ★설치가 끝났으면 폰의 USB 디버깅을 끄세요 — 켜진 채 쥐어진 폰은 누구나 다룰 수 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
