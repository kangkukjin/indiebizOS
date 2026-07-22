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

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
BODIES = ROOT / "data" / "bodies"


def _backend_modules():
    return {p.stem for p in BACKEND.glob("*.py")}


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

    mods = _backend_modules()
    ext_imports, be_imports = {}, {}
    for m in mods:
        e, b = _toplevel_imports(BACKEND / f"{m}.py")
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
    for m in mods:
        if any(fnmatch.fnmatch(m, g) for g in glob_exclude):
            reasons.setdefault(m, "force_exclude_glob")
    # 3) 전이: blocklist 모듈을 *가드 없이* 최상위 import 하면 자기도 blocklist
    changed = True
    while changed:
        changed = False
        for m in mods:
            if m in reasons:
                continue
            via = sorted(be_imports[m] & set(reasons))
            if via:
                reasons[m] = f"via {','.join(via)}"
                changed = True

    blocklist = sorted(reasons)
    engine = sorted(mods - set(blocklist))
    return {
        "_doc": "scripts/build_body_bundle.py 가 data/bodies/%s.json 에서 파생. 직접 편집 금지 — 프로파일을 고치고 재생성하라." % body,
        "body": body,
        "engine_modules": engine,
        "blocklist": {m: reasons[m] for m in blocklist},
        "counts": {"total": len(mods), "engine": len(engine), "blocklist": len(blocklist)},
    }


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
    path.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
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
        if cur.get("engine_modules") != derived["engine_modules"] or \
           list(cur.get("blocklist", {})) != list(derived["blocklist"]):
            print(f"✗ 드리프트: {body} 파생 결과가 기록본과 다름 — 재생성 필요.", file=sys.stderr)
            a, b = set(cur.get("engine_modules", [])), set(derived["engine_modules"])
            if b - a:
                print(f"  + 새로 번들돼야 할 모듈: {sorted(b - a)}", file=sys.stderr)
            if a - b:
                print(f"  - 더 이상 번들 안 되는 모듈: {sorted(a - b)}", file=sys.stderr)
            return 1
        print(f"✓ {body} 엔진 번들 일치 ({derived['counts']})")
        return 0

    out_path.write_text(json.dumps(derived, ensure_ascii=False, indent=2), encoding="utf-8")
    kept, npath = derive_nodes_registry(body)
    print(f"✓ {npath.relative_to(ROOT)} 파생: 몸-사전 {kept}개 어휘 (남의 어휘 미탑재)")
    c = derived["counts"]
    print(f"✓ {out_path.relative_to(ROOT)} 파생: 엔진 {c['engine']} / blocklist {c['blocklist']} / 전체 {c['total']}")
    for m, why in derived["blocklist"].items():
        print(f"    blocklist  {m:28s} {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
