#!/usr/bin/env python3
"""bootstrap.py — 정본 설치 경로의 단일 레시피 (맥·윈도우·리눅스 공용).

헌법(canonical-install-path, 2026-08-10): 공식 설치 = git clone 한 소스 트리.
이 스크립트가 그 경로의 **유일한 조리법**이다 — README 가 이걸 가리키고,
CI(portability.yml boot-smoke)가 매 푸시마다 이걸로 설치해 부팅을 증명하고,
설치본(.exe/.dmg)은 이 레시피를 감싼 포장이다. 레시피가 하나면 갈라질 수 없다.

stdlib 만 사용(pip 설치 *전*에 돌아야 하므로), 멱등(재실행 안전).

사용:
  python3 scripts/bootstrap.py              # venv + 의존성(core+tools) + .env 시드 + 프론트(있으면)
  python3 scripts/bootstrap.py --core-only  # 백엔드 코어만 (CI·최소 설치)
  python3 scripts/bootstrap.py --run        # 설치 후 백엔드 실행까지

윈도우는 python3 대신:  py scripts\\bootstrap.py
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV = os.path.join(ROOT, ".venv")

# venv 를 만들 파이썬의 지원 범위. 상한이 있는 이유(2026-08-10 실측): 3.14 는
# coincurve(pynostr 의존, Nostr 통신)가 휠을 아직 안 내놔 소스빌드가 죽는다 —
# 최신 파이썬만 가진 낯선 기계가 첫 pip 에서 막히는 부류. 휠이 따라오면 상한을 올린다.
PY_MIN, PY_MAX_EXCL = (3, 10), (3, 14)


def pick_base_python() -> str:
    """venv 의 밑 파이썬 선택 — 현재 인터프리터가 지원 범위면 그대로, 아니면 PATH 에서
    범위 안 파이썬을 찾는다(윈도우는 py 런처 경유도). 못 찾으면 현재 것 + 경고."""
    cur = sys.version_info[:2]
    if PY_MIN <= cur < PY_MAX_EXCL:
        return sys.executable

    def _version_of(argv):
        try:
            out = subprocess.run(argv + ["-c", "import sys;print(sys.version_info[0],sys.version_info[1]);print(sys.executable)"],
                                 capture_output=True, text=True, timeout=15)
            if out.returncode != 0:
                return None
            ver_line, exe_line = out.stdout.strip().splitlines()[:2]
            major, minor = (int(x) for x in ver_line.split())
            return ((major, minor), exe_line)
        except Exception:
            return None

    candidates = []
    for minor in range(PY_MAX_EXCL[1] - 1, PY_MIN[1] - 1, -1):  # 3.13 → 3.10 (높은 쪽 선호)
        candidates.append([f"python3.{minor}"])
        if os.name == "nt":
            candidates.append(["py", f"-3.{minor}"])
    for argv in candidates:
        if argv[0] != "py" and not shutil.which(argv[0]):
            continue
        got = _version_of(argv)
        if got and PY_MIN <= got[0] < PY_MAX_EXCL:
            print(f"  현재 파이썬 {sys.version.split()[0]} 은 지원 범위 밖 — {got[1]} 사용", flush=True)
            return got[1]

    print(f"  ⚠ 지원 범위(3.{PY_MIN[1]}~3.{PY_MAX_EXCL[1]-1}) 파이썬을 못 찾음 — 현재 "
          f"{sys.version.split()[0]} 로 진행. 일부 코어 의존성(coincurve 등)이 빌드 실패할 수 "
          f"있습니다. 막히면 Python 3.12 나 3.13 설치 후 재실행하세요.", flush=True)
    return sys.executable


def venv_python() -> str:
    """이 저장소 관례(.venv — start.sh 도 이 경로를 본다)의 파이썬 경로."""
    if os.name == "nt":
        return os.path.join(VENV, "Scripts", "python.exe")
    p = os.path.join(VENV, "bin", "python3")
    return p if os.path.exists(p) else os.path.join(VENV, "bin", "python")


def step(title: str):
    print(f"\n▶ {title}", flush=True)


def run(cmd, **kw) -> None:
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    subprocess.check_call(cmd, **kw)


def main() -> int:
    ap = argparse.ArgumentParser(description="IndieBiz OS 소스 설치 부트스트랩 (3 OS)")
    ap.add_argument("--core-only", action="store_true",
                    help="백엔드 코어 의존성만 (requirements-tools·프론트엔드 생략 — CI·최소 설치)")
    ap.add_argument("--run", action="store_true", help="설치 후 백엔드를 바로 실행")
    ap.add_argument("--recreate", action="store_true", help=".venv 를 지우고 새로 만든다")
    args = ap.parse_args()

    if sys.version_info < (3, 10):
        print(f"Python 3.10 이상이 필요합니다 (현재 {sys.version.split()[0]}).")
        return 1

    step("가상환경 (.venv)")
    if os.path.exists(venv_python()):
        # 기존 venv 의 파이썬이 지원 범위 밖이면 알린다 (사용자 데이터가 아니라 재생성 가능물이지만,
        # 조용히 갈아엎지는 않는다 — --recreate 로 명시).
        got = subprocess.run([venv_python(), "-c", "import sys;print(sys.version_info[0],sys.version_info[1])"],
                             capture_output=True, text=True)
        ver = tuple(int(x) for x in got.stdout.split()) if got.returncode == 0 else None
        if args.recreate or ver is None or not (PY_MIN <= ver < PY_MAX_EXCL):
            print(f"  기존 .venv 재생성 (버전 {ver} → 지원 범위 파이썬)", flush=True)
            shutil.rmtree(VENV)
            run([pick_base_python(), "-m", "venv", VENV])
        else:
            print("  이미 있음 — 재사용", flush=True)
    else:
        run([pick_base_python(), "-m", "venv", VENV])
    vpy = venv_python()

    step("백엔드 의존성 — requirements-core.txt")
    run([vpy, "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    run([vpy, "-m", "pip", "install", "--quiet", "-r",
         os.path.join(ROOT, "backend", "requirements-core.txt")])

    if not args.core_only:
        step("도구 의존성 — requirements-tools.txt (실패해도 코어는 동작)")
        try:
            run([vpy, "-m", "pip", "install", "--quiet", "-r",
                 os.path.join(ROOT, "backend", "requirements-tools.txt")])
        except subprocess.CalledProcessError:
            print("  ⚠ 일부 도구 의존성 설치 실패 — 해당 도구만 비활성, 나중에 재시도 가능", flush=True)

        step("브라우저 바이너리 — playwright chromium (~550MB, 슬라이드·영상 렌더의 손)")
        # 왜 조리법 안에 있나(2026-08-15): pip 로 playwright 를 올려도 브라우저 바이너리는
        # 따로 받아야 하고, 그때 PLAYWRIGHT_BROWSERS_PATH 를 안 주면 기본 캐시로 가는데
        # 백엔드는 base_path/ms-playwright 를 본다 → 어긋난 채로 조용히 있다가 렌더할 때
        # 터진다. 설치가 레시피의 일부가 아니면 이 어긋남은 playwright 를 올릴 때마다 난다.
        # 주소는 check_playwright_browsers.py 가 runtime_utils(단일 소스)에서 가져온다.
        try:
            run([vpy, os.path.join(ROOT, "scripts", "check_playwright_browsers.py"), "--install"])
        except subprocess.CalledProcessError:
            print("  ⚠ 브라우저 다운로드 실패 — 슬라이드/영상 렌더·browser-action 만 비활성. "
                  "나중에 `python scripts/check_playwright_browsers.py --install` 로 재시도", flush=True)

        step("시맨틱 메모리 — requirements-ml.txt (해마 벡터 회상, ~2GB — 실패 시 키워드 회상으로 저하)")
        try:
            run([vpy, "-m", "pip", "install", "--quiet", "-r",
                 os.path.join(ROOT, "backend", "requirements-ml.txt")])
        except subprocess.CalledProcessError:
            print("  ⚠ 시맨틱 메모리 설치 실패 — 해마가 키워드(FTS) 회상으로 동작. "
                  "나중에 이 스크립트 재실행으로 재시도 가능", flush=True)

    step(".env — API 키 자리")
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        shutil.copyfile(os.path.join(ROOT, ".env.example"), env_path)
        print("  .env.example → .env 생성. LLM API 키(Anthropic/Google/OpenAI 중 하나)를 채우세요.", flush=True)
    else:
        print("  이미 있음 — 그대로 둠", flush=True)

    if not args.core_only:
        step("프론트엔드 (Electron 데스크탑 UI — 선택)")
        npm = shutil.which("npm")
        if npm:
            try:
                run([npm, "install", "--no-audit", "--no-fund"],
                    cwd=os.path.join(ROOT, "frontend"))
            except subprocess.CalledProcessError:
                print("  ⚠ npm install 실패 — 백엔드 전용으로 계속(원격 런처/REST 사용 가능)", flush=True)
        else:
            print("  npm 없음 — 백엔드 전용 설치(데스크탑 UI 는 Node ≥ 18 설치 후 재실행)", flush=True)

    if not args.core_only:
        step("의존성 커버리지 감사 — 코드가 import 하는 서드파티가 방금 만든 .venv 에 실재하는가")
        # fresh 설치의 누락(requirements 선언 빠짐·설치 실패·ABI 파손)을 지금 잡는다 —
        # 안 잡으면 그 코드가 도는 순간(며칠 뒤)에야 터진다(.venv 전환 잔재 부류, 2026-08-13).
        # --core-only 는 tools/ml 이 의도적으로 빠져 있어 감사 대상이 아니다(CI 는
        # portability.yml 의 import-coverage 잡이 core+tools 로 따로 검사한다).
        # 실패해도 부트스트랩은 계속 — 코어 서버는 뜨고, 무엇이 빠졌는지는 위에 찍혔다.
        try:
            rc = subprocess.run([vpy, os.path.join(ROOT, "scripts", "check_import_coverage.py")],
                                cwd=ROOT, timeout=600).returncode
            if rc == 1:
                print("  ⚠ 위 결손 의존성은 해당 기능이 돌 때 터집니다 — requirements 선언/설치 후 재실행 권장", flush=True)
            elif rc != 0:
                print("  ⚠ 감사 스크립트 자체 문제 (무시하고 계속)", flush=True)
        except Exception as e:
            print(f"  ⚠ 의존성 감사 실행 실패 (무시하고 계속): {e}", flush=True)

    step("완료")
    if os.name == "nt":
        print("  실행:  .venv\\Scripts\\python.exe backend\\api.py", flush=True)
    else:
        print("  실행:  ./start.sh   (또는 .venv/bin/python3 backend/api.py)", flush=True)
    print("  데스크탑 UI:  cd frontend && npm run electron:dev", flush=True)

    if args.run:
        step("백엔드 실행 (Ctrl-C 로 종료)")
        os.chdir(os.path.join(ROOT, "backend"))
        os.execv(vpy, [vpy, "api.py"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
