#!/usr/bin/env python3
"""폰 API 키 프로비저닝 (#4) — 정본 .env 의 폰 패키지 부분집합만 폰에 안전 주입.

정본 .env(루트, git 밖) → 폰 패키지가 실제 쓰는 키만 추출 → 임시 keys.json →
adb 로 폰 app-private files/secrets/keys.json 에 푸시(run-as, 디버그 빌드) → 임시 삭제.
phone_api._init_base 가 이 파일을 os.environ 에 주입한다.

설계 원칙:
- APK 에 키를 넣지 않는다(평문 금지). app-private 스토리지(=APK 밖·world 밖·git 밖)에만.
- 폰 패키지(PHONE_VERIFIED_PACKAGES)가 실제 참조하는 키만 — 식별/인프라 키는 제외(노출 최소화).
- 값은 화면에 찍지 않는다(키 이름만).

사용: python3 phone-companion/scripts/provision_phone_keys.py
프로덕션 향후: 폰 설정 UI → EncryptedSharedPreferences (현재는 dev 푸시).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = "com.indiebiz.phoneagent"

# 폰 패키지 6개가 실제 참조하는 데이터 API 키 (handler 전수 스캔 결과, 2026-06-11).
# 식별/인프라(OWNER_*, CLOUDFLARE_*, VERCEL, CONTEXT7, SYSTEM_AI_GMAIL)는 의도적 제외.
PHONE_KEYS = [
    # location-services (항공/호텔·맛집)
    "AMADEUS_API_KEY", "AMADEUS_API_SECRET", "KAKAO_REST_API_KEY",
    "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET",
    # investment (주식)
    "DART_API_KEY", "FINNHUB_API_KEY", "FMP_API_KEY",
    # culture (도서·전시·공연)
    "DATA4LIBRARY_API_KEY", "DATA_GO_KR_API_KEY", "KOPIS_API_KEY",
    # web (뉴스)
    "GUARDIAN_API_KEY",
    # real-estate (실거래가)
    "MOLIT_API_KEY",
    # 폰-자아 호스팅 step7: 경량 티어 = gemini_http(폰이 구글 API 직접 호출). 추론 자아의
    # 분류·평가를 맥 안 거치고 폰서 직접 — 맥과 동일 모델(Gemini), 자급도↑.
    "GEMINI_API_KEY",
]

# 분산 IBL 위임 설정 — 폰 자율주행 표면이 맥 백엔드로 프록시할 대상.
# .env 에 있으면 함께 주입(없으면 건너뜀 → 폰은 오프라인 폴백, 앱모드만).
#   INDIEBIZ_MAC_URL      = http://<맥 LAN IP>:8765  또는  http://127.0.0.1:8766 (adb reverse 시)
#   INDIEBIZ_MAC_PASSWORD = 맥 원격 런처 비번 (터널 경유 시 필수; LAN 직결은 생략 가능)
MAC_DELEGATION_KEYS = [
    "INDIEBIZ_MAC_URL",
    "INDIEBIZ_MAC_PASSWORD",
]


def load_env(env_path: Path) -> dict:
    out = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> int:
    root = Path(__file__).resolve().parents[2]   # phone-companion/scripts → repo root
    env_path = root / ".env"
    if not env_path.is_file():
        print(f"[provision] .env 없음: {env_path}", file=sys.stderr)
        return 2

    env = load_env(env_path)
    keys = {k: env[k] for k in PHONE_KEYS if env.get(k)}
    missing = [k for k in PHONE_KEYS if not env.get(k)]
    # 분산 IBL 위임 설정도 .env 에 있으면 합류(비밀 아닌 URL + 비번).
    mac_cfg = {k: env[k] for k in MAC_DELEGATION_KEYS if env.get(k)}
    keys.update(mac_cfg)
    if not keys:
        print("[provision] .env 에 폰 키가 하나도 없습니다.", file=sys.stderr)
        return 1

    # 디바이스 연결 확인
    devs = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
    if "\tdevice" not in devs:
        print("[provision] adb 디바이스 미연결.", file=sys.stderr)
        return 1

    payload = json.dumps(keys, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        tf.write(payload)
        tmp = tf.name
    tmp_dev = "/data/local/tmp/_phone_keys.json"
    try:
        subprocess.run(["adb", "push", tmp, tmp_dev], check=True, capture_output=True)
        # app-private files/secrets/ 로 run-as 복사 (디버그 빌드만 run-as 허용).
        # adb shell 은 인자를 device 측에서 한 줄로 합치므로 전체를 한 문자열로 넘긴다.
        inner = (f"mkdir -p files/secrets && chmod 700 files/secrets "
                 f"&& cp {tmp_dev} files/secrets/keys.json "
                 f"&& chmod 600 files/secrets/keys.json")
        r = subprocess.run(["adb", "shell", f"run-as {PKG} sh -c '{inner}'"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[provision] run-as 실패(디버그 빌드 맞나요?): {r.stderr.strip()}", file=sys.stderr)
            return 1
        subprocess.run(["adb", "shell", "rm", "-f", tmp_dev], capture_output=True)
    finally:
        os.unlink(tmp)

    data_keys = sorted(k for k in keys if k not in MAC_DELEGATION_KEYS)
    print(f"[provision] ✅ 폰에 데이터 키 {len(data_keys)}개 주입: {', '.join(data_keys)}")
    if mac_cfg:
        url_shown = mac_cfg.get("INDIEBIZ_MAC_URL", "(미설정)")
        pw = "비번 동봉" if "INDIEBIZ_MAC_PASSWORD" in mac_cfg else "비번 없음(LAN 직결 전제)"
        print(f"[provision] ✅ 맥 위임: {url_shown} ({pw}) — 자율주행이 맥으로 프록시됩니다.")
    else:
        print("[provision] ℹ️  맥 위임 미설정(.env 에 INDIEBIZ_MAC_URL 없음) → 폰 자율주행은 오프라인 폴백, 앱모드만 동작.")
    if missing:
        print(f"[provision] (.env 에 없어 건너뜀: {', '.join(missing)})")
    print("[provision] 폰 백엔드 재기동(앱 force-stop 후 '폰 백엔드 시작')하면 반영됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
