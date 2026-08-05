"""hippocampus_provision.py — 첫 실행 해마(hippocampus) 공급.

fresh 설치(특히 윈도우)엔 해마의 세 조각이 다 없다(맥 개발기엔 있어 안 드러났던 이식성 문제):
  ① 임베딩 런타임(sentence-transformers/torch/sqlite-vec) — 어느 requirements 에도 없어 미번들
  ② 모델 가중치(model.safetensors 422MB) — .gitignore·미번들
  ③ 용례 + 미리계산 벡터(ibl_hippo_index.json / ibl_hippo_vecs.f32 / training/ibl_distilled.json)

이 모듈이 첫 실행에 ②③을 GitHub Release 에셋에서 userData 로 내려받고, ①을 pip 로 설치한다.
전부 백그라운드·멱등·시끄럽게(로그). 이미 갖춰졌으면 아무것도 안 한다. 실패해도 부팅·본체엔
영향 없이 키워드(FTS5) 폴백으로 계속.

- 모델/벡터는 릴리스 에셋 zip(INDIEBIZ_HIPPOCAMPUS_URL, 기본=repo releases/hippocampus) → userData/data 아래 전개.
- 런타임 lib 은 runtime_utils.install_python_dependency 로 userData/pylibs 에 설치.
- 다운로드 자체는 stdlib(urllib/zipfile)만 — 추가 의존성 없음.

★공급 자체는 실기 번들·네트워크·릴리스 에셋 존재가 필요해 개발기에서 종단 검증 불가.
  경로·전개 레이아웃·멱등·폴백 로직만 정적 검증됨. 에셋은 scripts/publish_hippocampus.py 로 올린다.
"""
import os
import threading
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request

# 릴리스 에셋 기본 URL(고정 태그 'hippocampus'). 다른 곳에 두려면 INDIEBIZ_HIPPOCAMPUS_URL 로 덮어씀.
DEFAULT_URL = "https://github.com/kangkukjin/indiebizOS/releases/download/hippocampus/hippocampus.zip"


def _base() -> Path:
    from runtime_utils import get_base_path
    return get_base_path()


def _model_present() -> bool:
    return (_base() / "data" / "models" / "ibl_embedding" / "model.safetensors").exists()


def _libs_present() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except Exception:
        return False


def ensure_runtime_libs() -> bool:
    """sentence-transformers(+torch) · sqlite-vec 를 userData/pylibs 에 설치. 이미 있으면 즉시 True."""
    if _libs_present():
        return True
    print("[해마공급] 임베딩 런타임 설치 시작 — 최초 1회, 수백MB~수GB 다운로드(torch 포함) …")
    from runtime_utils import install_python_dependency
    ok = True
    for pkg in ("sqlite-vec", "sentence-transformers"):
        r = install_python_dependency(pkg, timeout=1800)
        state = "OK" if r.get("success") else f"실패 — {r.get('message')}"
        print(f"[해마공급] {pkg}: {state}")
        if not r.get("success") and pkg == "sentence-transformers":
            ok = False
    return ok and _libs_present()


def download_model(url: str = None) -> bool:
    """모델+벡터+용례 zip 을 받아 userData/data 아래 전개. 이미 있으면 즉시 True."""
    if _model_present():
        return True
    url = url or os.environ.get("INDIEBIZ_HIPPOCAMPUS_URL") or DEFAULT_URL
    data_dir = _base() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.gettempdir()) / "hippocampus_dl.zip"
    print(f"[해마공급] 모델·용례 다운로드 시작: {url}")
    try:
        req = Request(url, headers={"User-Agent": "indiebizOS"})
        total = 0
        with urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
        print(f"[해마공급] 다운로드 완료 {total / 1024 / 1024:.0f}MB → 전개 중")
        with zipfile.ZipFile(tmp) as z:
            # zip 은 data/ 기준 상대경로: models/ibl_embedding/…, ibl_hippo_index.json, training/…
            z.extractall(data_dir)
        tmp.unlink(missing_ok=True)
        ok = _model_present()
        print(f"[해마공급] 전개 {'완료' if ok else '실패(모델 파일 없음 — zip 레이아웃 확인)'}")
        return ok
    except Exception as e:
        print(f"[해마공급] 다운로드 실패(무시, 키워드 폴백으로 계속): {e}")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def provision_async(enabled: bool = True):
    """첫 실행 해마 공급을 백그라운드로 수행. 이미 완비(모델+런타임)면 즉시 종료(조용).

    데스크탑 진입점(api.py)에서 호출한다 — 폰-자아는 렌트 모드라 대상 아님(호출 안 함).
    """
    if not enabled:
        return
    if _model_present() and _libs_present():
        return  # 이미 완비 — 조용히 통과(개발기 맥 포함)

    def _run():
        try:
            libs = ensure_runtime_libs()
            model = download_model()
            if libs and model:
                print("[해마공급] ✅ 해마 완비 — 임베딩 모델 로딩 시작(다음 요청부터 시맨틱 연상 활성)")
                try:
                    from ibl_usage_db import IBLUsageDB
                    IBLUsageDB._start_background_model_load()
                except Exception as e:
                    print(f"[해마공급] 모델 로딩 트리거 실패(재시작 시 로드): {e}")
            else:
                print("[해마공급] ⚠️ 해마 미완비(런타임 or 모델 확보 실패) — "
                      "키워드(FTS5) 폴백으로 동작. 네트워크 확인 후 재시작하면 재시도.")
        except Exception as e:
            print(f"[해마공급] 공급 중 오류(무시): {e}")

    threading.Thread(target=_run, daemon=True, name="hippocampus-provision").start()
