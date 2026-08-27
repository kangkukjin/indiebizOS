#!/usr/bin/env python3
"""build_body_bundle.py — 몸(body)별 backend 엔진 번들을 *파생*한다 (손-리스트 폐기).

indiebizOS 는 하나의 코드베이스를 여러 하드웨어(맥·android·향후 ios/windows/linux)에 설치한다.
'제약된 몸'(전체 트리를 못 돌려 서브셋을 패키징해야 하는 몸 — android·ios)의 번들은
**자동 파생**되어야 한다: 모든 backend 모듈을 기본 포함하고, *그 몸이 못 돌리는 것*(선언된
substrate 예외)만 뺀다. 그래야 새 기능이 자연히 모든 몸으로 흐른다(드리프트 없음).

원칙(헌법1조 substrate/superstructure seam):
  - 번들 = (전체 backend 모듈) − (blocklist)
  - blocklist = 그 몸에 *없는 외부 패키지*(body.json absent_packages)를 **모듈 최상위에서**
    import 하는 모듈 + 그걸 가드 없이 import 하는 모듈(전이) + force_exclude.
    (가드된 import = try/except·지연 import 는 런타임에 건너뛰므로 무관.)
  - 즉 blocklist 는 손-큐레이션이 아니라 '없는 능력'에서 파생된다.
  - **글롭 제외(`_force_exclude_glob`, 예: `test_*`)는 규칙만 기록하고 전개하지 않는다.**
    그건 "없는 능력"이 아니라 "애초에 엔진 모듈이 아니다"라는 선언이라, 파일별로 펼치면
    시험 파일 하나가 늘 때마다 파생본이 흔들려 관문이 무관한 커밋을 막는다(2026-08-27).

새 몸 추가 = data/bodies/<body>.json 하나 작성 → 이 도구가 매니페스트 파생.

사용:
  python3 scripts/build_body_bundle.py android            # 파생 + 매니페스트 기록
  python3 scripts/build_body_bundle.py android --check     # 게이트: 파생 결과가 기록본과 일치하나(빌드/pre-commit)
출력: data/bodies/<body>.engine.json  (build.gradle 이 이걸 _ENGINE_MODULES 로 읽음)
"""
import ast
import json
import sys
import fnmatch
from pathlib import Path
from iblbuild_common import atomic_write_text

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
BODIES = ROOT / "data" / "bodies"


_SKIP_DIRS = {"__pycache__", "common", "drivers", "providers", "static", "channels",
              "assets", "checkpoints", "data", "outputs", "projects", "testdata", "tokens"}


def _backend_module_paths():
    """{모듈명: backend 상대경로(.py 제외)} — 층 디렉토리(물리 이동 후) 재귀."""
    out = {}
    for p in BACKEND.rglob("*.py"):
        rel = p.relative_to(BACKEND)
        if any(part in _SKIP_DIRS for part in rel.parts[:-1]):
            continue
        out[p.stem] = rel.with_suffix("").as_posix()
    return out


def _backend_modules():
    return set(_backend_module_paths())


def _toplevel_imports(pyfile):
    """모듈 *최상위*(함수 밖·try 밖) import 만 반환.
       → (외부 top-package 집합, backend 모듈 집합).
    try 블록 안 import 는 '가드됨'으로 보아 제외(런타임에 ImportError 를 삼킴)."""
    ext, be = set(), set()
    try:
        tree = ast.parse(pyfile.read_text(encoding="utf-8"))
    except Exception:
        return ext, be
    backend_mods = _backend_modules()
    # try 블록 내부의 import 노드 id 수집 → 가드로 간주
    guarded = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Try):
            for c in ast.walk(n):
                if isinstance(c, (ast.Import, ast.ImportFrom)):
                    guarded.add(id(c))
    for n in tree.body:  # 최상위 문장만 (조건부/함수 내 import 는 가드로 간주)
        if not isinstance(n, (ast.Import, ast.ImportFrom)) or id(n) in guarded:
            continue
        if isinstance(n, ast.Import):
            for a in n.names:
                top = a.name.split(".")[0]
                (be if top in backend_mods else ext).add(top)
        elif n.module and n.level == 0:
            top = n.module.split(".")[0]
            (be if top in backend_mods else ext).add(top)
    return ext, be


def derive(body):
    """body 프로파일 → {engine_modules, blocklist, ...}."""
    profile = json.loads((BODIES / f"{body}.json").read_text(encoding="utf-8"))
    absent = set(profile.get("absent_packages", []))
    force_exclude = set(profile.get("force_exclude", []))
    glob_exclude = profile.get("force_exclude_glob", []) or profile.get("_force_exclude_glob", [])

    paths = _backend_module_paths()
    # ★글롭 제외는 **전개하지 않는다 — 규칙만 기록한다**(2026-08-27).
    #   `test_*` 같은 글롭은 "이 파일들은 애초에 엔진 모듈이 아니다"라는 *선언*이지,
    #   몸이 못 돌리는 능력의 목록이 아니다. 그런데 옛 코드는 이 규칙을 파일별 키로
    #   펼쳐 blocklist 에 넣었고(128건 중 108건이 test_*), 그 바람에 backend 에 시험
    #   파일이 하나 생길 때마다 파생본이 흔들려 pre-commit 이 **무관한 커밋을 막았다**
    #   — 49회차 상상훈련 수리 커밋이 실제로 이 덫에 걸려 미커밋으로 남았다.
    #   규칙만 기록하면 파생본은 '무엇이 폰에 못 가는가'의 함수로만 남는다.
    glob_covered = {m for m in paths if any(fnmatch.fnmatch(m, g) for g in glob_exclude)}
    mods = set(paths) - glob_covered
    ext_imports, be_imports = {}, {}
    for m in mods:
        e, b = _toplevel_imports(BACKEND / (paths[m] + ".py"))
        ext_imports[m], be_imports[m] = e, b

    reasons = {}
    # 1) seed: 몸-부재 외부 패키지를 최상위 import → import 시 즉사
    for m in mods:
        hit = sorted(ext_imports[m] & absent)
        if hit:
            reasons[m] = f"top-level import: {','.join(hit)}"
    # 2) force_exclude (프로토타입/맥 진입점/비-엔진)
    for m in force_exclude & mods:
        reasons.setdefault(m, "force_exclude (프로파일 명시)")
    # 3) 전이: blocklist 모듈을 *가드 없이* 최상위 import 하면 자기도 blocklist.
    #    글롭에 걸린 모듈(mods 밖)도 전이의 씨앗이다 — 엔진 모듈이 시험 파일을 최상위
    #    import 하면 폰에서 즉사하므로, 그건 조용히 넘길 게 아니라 blocklist 에 사유째
    #    남아야 한다(`via test_foo` 로 읽힌다).
    changed = True
    while changed:
        changed = False
        for m in mods:
            if m in reasons:
                continue
            via = sorted(be_imports[m] & (set(reasons) | glob_covered))
            if via:
                reasons[m] = f"via {','.join(via)}"
                changed = True

    blocklist = sorted(reasons)
    # ★engine 항목 = backend 상대경로 — 폰 gradle 이 from("backend/${m}.py") 로 그대로
    # 집는다(zip 안에서는 into 'backend' 로 평면화 → 폰 import 는 종전과 동일).
    engine = sorted(paths[m] for m in (mods - set(blocklist)))
    return {
        "_doc": "scripts/build_body_bundle.py 가 data/bodies/%s.json 에서 파생. 직접 편집 금지 — 프로파일을 고치고 재생성하라." % body,
        "body": body,
        "engine_modules": engine,
        "blocklist": {m: reasons[m] for m in blocklist},
        # 규칙 자체(전개본 아님) — 이 글롭에 걸린 파일은 엔진 모듈 후보에서 아예 빠진다.
        "blocklist_globs": sorted(glob_exclude),
        # total = 글롭 밖 backend 모듈 수(= engine + blocklist). 시험 파일이 늘어도
        # 흔들리지 않는다 — 흔들리는 수를 파생본에 적으면 그게 곧 드리프트가 된다.
        "counts": {"total": len(mods), "engine": len(engine), "blocklist": len(blocklist)},
    }


def diff_against(cur, derived):
    """기록본 ↔ 파생본 차이를 **사람이 읽는 줄들**로 — 비면 일치.

    ★관문이 "다름"이라고만 말하고 이유를 못 대던 자리(2026-08-27 수리).
    옛 코드는 *판정*(engine_modules + blocklist 키 비교)과 *설명*(engine_modules 집합
    차이만 출력)을 서로 다른 식으로 계산했다. 그래서 차이가 blocklist 쪽에만 있으면
    "✗ 드리프트 … 재생성 필요" 한 줄만 나오고 **무엇이 다른지가 빈칸**이었다 — 실제로
    49회차 커밋이 막혔을 때 이유가 로그 어디에도 없어 원장 JSON 을 파야 했다.
    이제 판정과 설명이 같은 목록 하나에서 나오므로, 드리프트가 이유 없이 신고되는
    경우가 원리적으로 없다(그 성질을 시험이 지킨다).
    """
    out = []

    def _cmp(label, a, b):
        sa, sb = set(a), set(b)
        if sb - sa:
            out.append(f"  + {label}: 새로 들어와야 함 — {sorted(sb - sa)}")
        if sa - sb:
            out.append(f"  - {label}: 더 이상 아님 — {sorted(sa - sb)}")
        if sa == sb and list(a) != list(b):
            out.append(f"  ~ {label}: 항목은 같고 순서만 다름 — 재생성하면 정렬된다")

    _cmp("engine_modules", cur.get("engine_modules", []), derived["engine_modules"])
    _cmp("blocklist", list(cur.get("blocklist", {})), list(derived["blocklist"]))
    _cmp("blocklist_globs", cur.get("blocklist_globs", []), derived["blocklist_globs"])

    # 키는 같은데 *사유*가 달라진 것도 파생 드리프트다(무엇 때문에 빠지는지가 바뀌었다).
    ca, cb = cur.get("blocklist", {}), derived["blocklist"]
    moved = [m for m in cb if m in ca and ca[m] != cb[m]]
    for m in moved[:5]:
        out.append(f"  ~ blocklist 사유 변경: {m} — \"{ca[m]}\" → \"{cb[m]}\"")
    if len(moved) > 5:
        out.append(f"  ~ blocklist 사유 변경 …외 {len(moved) - 5}건")
    return out


def derive_nodes_registry(body):
    """몸-사전 물리 파생 — 배포물(data/ibl_nodes.yaml = 전체 사전집)에서 이 몸의
    어휘만 추출해 번들용 레지스트리를 만든다. 폰은 PC 전용 어휘를 알 필요가 없고
    그 역도 마찬가지 — 번들은 애초에 남의 어휘를 싣지 않는다(설치=자기 사전만).
    소유 기준 = phone_manifest.runnable_actions (런타임 로더의 설치 필터와 동일 기준).
    출력: data/bodies/<body>.nodes.yaml → build.gradle 이 zip 의 data/ibl_nodes.yaml 로 rename.
    """
    import yaml
    full = yaml.safe_load((ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "data" / "phone_manifest.json").read_text(encoding="utf-8"))
    runnable = set(manifest.get("runnable_actions") or [])
    nodes, kept = {}, 0
    for node, cfg in (full.get("nodes") or {}).items():
        acts = {a: c for a, c in ((cfg or {}).get("actions") or {}).items()
                if f"{node}:{a}" in runnable}
        if not acts:
            continue  # 이 몸에 어휘가 0인 노드는 노드째 제외
        ncfg = {k: v for k, v in cfg.items() if k != "actions"}
        ncfg["actions"] = acts
        nodes[node] = ncfg
        kept += len(acts)
    out = {"meta": {**(full.get("meta") or {}), "_body": body,
                    "_doc": "몸-사전 파생본 — build_body_bundle.py 가 전체 사전집에서 "
                            "이 몸의 어휘만 추출. 직접 편집 금지(사전집·매니페스트를 고치고 재생성)."},
           "nodes": nodes}
    path = BODIES / f"{body}.nodes.yaml"
    atomic_write_text(path, yaml.safe_dump(out, allow_unicode=True, sort_keys=False))
    return kept, path


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    body = args[0] if args else "android"
    out_path = BODIES / f"{body}.engine.json"
    derived = derive(body)

    if check:
        if not out_path.exists():
            print(f"✗ {out_path.name} 없음 — `python3 scripts/build_body_bundle.py {body}` 먼저", file=sys.stderr)
            return 1
        cur = json.loads(out_path.read_text(encoding="utf-8"))
        # 판정과 설명이 같은 목록에서 나온다 — 이유 없는 드리프트 신고가 불가능하다.
        problems = diff_against(cur, derived)
        if problems:
            print(f"✗ 드리프트: {body} 파생 결과가 기록본과 다름 — 재생성 필요.", file=sys.stderr)
            for line in problems:
                print(line, file=sys.stderr)
            return 1
        print(f"✓ {body} 엔진 번들 일치 ({derived['counts']})")
        return 0

    atomic_write_text(out_path, json.dumps(derived, ensure_ascii=False, indent=2))
    kept, npath = derive_nodes_registry(body)
    print(f"✓ {npath.relative_to(ROOT)} 파생: 몸-사전 {kept}개 어휘 (남의 어휘 미탑재)")
    c = derived["counts"]
    print(f"✓ {out_path.relative_to(ROOT)} 파생: 엔진 {c['engine']} / blocklist {c['blocklist']} / 전체 {c['total']}"
          f"  (글롭 제외 규칙 {derived['blocklist_globs']} — 전개하지 않음)")
    for m, why in derived["blocklist"].items():
        print(f"    blocklist  {m:28s} {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
