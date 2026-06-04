"""레거시 별칭 은퇴(#24) 마이그레이션.

ibl_parser._ACTION_NAME_ALIASES 159개를 은퇴하기 전, 모든 방출/교재/운영/코퍼스
표면의 옛 액션 이름을 최종 캐노니컬(op/파라미터 주입 포함)로 치환한다.

- 옛 이름 → 최종 캐노니컬은 별칭 dict를 체인 해소(연쇄 별칭 추적)하여 자동 산출.
- 체인이 카탈로그에 없는 중간 이름(stale double-alias)에서 끝나면 OVERRIDES로 교정.
- slide는 스키마 변경(topic/title → slides 배열)이라 특수 변환.

실행:
  python3 migrate_alias_retirement.py --dry-run   # 검증 + 미리보기만
  python3 migrate_alias_retirement.py             # 실제 치환 (코퍼스+usage_db+world_pulse)
재색인:
  python3 -c "from ibl_usage_db import IBLUsageDB; print(IBLUsageDB().rebuild_index())"
"""
import json, re, ast, sys, sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PARSER = BASE / "backend" / "ibl_parser.py"
CATALOG = BASE / "data" / "ibl_nodes.yaml"
TRAINING_FILES = [
    BASE / "data" / "training" / "ibl_training_balanced_20260516.json",
    BASE / "data" / "training" / "ibl_distilled.json",
]
WORLD_PULSE = BASE / "data" / "world_pulse.db"

# 체인 해소가 카탈로그에 없는 이름에서 끝나는 경우의 교정(최종 캐노니컬).
# blog 계열은 별칭 dict가 #3(blog op 통합) 이전이라 stale → 현재 blog{op} 액션으로.
OVERRIDES = {
    ("self", "blog_semantic"):  ("self", "blog", {"op": "search", "mode": "semantic"}),
    ("self", "blog_content"):   ("self", "blog", {"op": "search", "mode": "content"}),
    ("self", "blog_get_post"):  ("self", "blog", {"op": "search", "mode": "content"}),
    ("self", "blog_search"):    ("self", "blog", {"op": "search"}),
    ("self", "blog_posts"):     ("self", "blog", {"op": "posts"}),
    ("self", "posts"):          ("self", "blog", {"op": "posts"}),
    ("self", "blog_check_new"): ("self", "blog", {"op": "check_new"}),
    ("self", "check_new"):      ("self", "blog", {"op": "check_new"}),
    ("self", "blog_rebuild_index"): ("self", "blog", {"op": "rebuild_index"}),
    ("self", "rebuild_index"):  ("self", "blog", {"op": "rebuild_index"}),
    # photo bare 별칭(double): 최종 photo{op}
    ("self", "gallery"):        ("self", "photo", {"op": "gallery"}),
    ("self", "list_scans"):     ("self", "photo", {"op": "list_scans"}),
    ("self", "timeline"):       ("self", "photo", {"op": "timeline"}),
    # memory bare 별칭(double)
    ("self", "search_memory"):  ("self", "memory", {"op": "search"}),
    # web_builder 옛 이름들(아카이브에만 존재, 안전상 최종 매핑 명시)
    ("engines", "web_create_site"):      ("engines", "web", {"op": "create", "target": "site"}),
    ("engines", "web_create_page"):      ("engines", "web", {"op": "create", "target": "page"}),
    ("engines", "web_list_components"):  ("engines", "web_component", {"op": "catalog", "kind": "components"}),
    ("engines", "web_list_sections"):    ("engines", "web_component", {"op": "catalog", "kind": "sections"}),
}

# slide는 스키마 변경 → 특수 변환(generic 매핑에서 제외)
SLIDE_OLD = ("engines", "slide")
SLIDE_NEW = "slide_shadcn"


def load_alias_map():
    src = PARSER.read_text(encoding="utf-8")
    start = src.index("_ACTION_NAME_ALIASES")
    brace = src.index("{", start)
    depth = 0; i = brace
    while i < len(src):
        if src[i] == "{": depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return ast.literal_eval(src[brace:i + 1])


def load_catalog_actions():
    import yaml
    cat = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    nodes = cat.get("nodes", cat)
    existing = set()
    for nname, ndata in nodes.items():
        acts = ndata.get("actions", {}) if isinstance(ndata, dict) else {}
        if isinstance(acts, dict):
            for a in acts:
                existing.add((nname, a))
    return existing


def build_resolve(amap, existing):
    """옛 (node,name) → (newnode, newname, inject_params) 최종 해소."""
    resolve = {}
    for (node, name) in amap:
        if (node, name) == SLIDE_OLD:
            continue  # 특수 처리
        # 체인 추적
        cn, ca, inject = node, name, {}
        seen = set()
        while (cn, ca) in amap and (cn, ca) not in seen:
            seen.add((cn, ca))
            canon = amap[(cn, ca)]
            cn, ca = canon[0], canon[1]
            if len(canon) >= 3 and canon[2]:
                for k, v in canon[2].items():
                    inject.setdefault(k, v)
        # 카탈로그에 없으면 OVERRIDE
        if (cn, ca) not in existing:
            ov = OVERRIDES.get((node, name))
            if ov:
                cn, ca, ovp = ov[0], ov[1], dict(ov[2] or {})
                for k, v in ovp.items():
                    inject.setdefault(k, v)
        resolve[(node, name)] = (cn, ca, inject)
    return resolve


def _fmt_inject(inject):
    """inject dict → 'op: "search", mode: "semantic"' 문자열(코퍼스 스타일, 문자열은 따옴표)."""
    parts = []
    for k, v in inject.items():
        if isinstance(v, str):
            parts.append(f'{k}: "{v}"')
        else:
            parts.append(f'{k}: {json.dumps(v, ensure_ascii=False)}')
    return ", ".join(parts)


def transform(code, resolve):
    if not code:
        return code
    # 1) slide 특수: topic/title 형 → slides 배열
    def slide_topic_repl(m):
        params = m.group(1)
        tm = re.search(r'(?:topic|title)\s*:\s*"([^"]*)"', params)
        title = tm.group(1) if tm else "슬라이드"
        return f'[engines:slide_shadcn]{{slides: [{{layout: "hero", title: "{title}"}}]}}'
    code = re.sub(r'\[engines:slide\]\{((?:[^{}]|\{[^{}]*\})*?)\}',
                  lambda m: slide_topic_repl(m) if re.search(r'(?:topic|title|pages)\s*:', m.group(1)) and 'slides' not in m.group(1) else m.group(0),
                  code)
    # slides 배열 형 + 무인자 형 → 단순 rename
    code = re.sub(r'\[engines:slide\](?=\{)', '[engines:slide_shadcn]', code)
    code = re.sub(r'\[engines:slide\](?!\{)', '[engines:slide_shadcn]', code)

    # 2) generic: 각 옛 이름 치환 (3 brace 케이스)
    for (node, name), (cn, ca, inject) in resolve.items():
        old = f'[{node}:{name}]'
        if old not in code:
            continue
        new = f'[{cn}:{ca}]'
        inj = _fmt_inject(inject)
        # 빈 중괄호
        if inj:
            code = code.replace(f'{old}{{}}', f'{new}{{{inj}}}')
            # 여는 중괄호 직후 주입 (내용 있는 경우)
            code = re.sub(re.escape(old) + r'\{(?!\})', f'{new}{{{inj}, ', code)
            # 무중괄호
            code = re.sub(re.escape(old) + r'(?!\{)', f'{new}{{{inj}}}', code)
        else:
            code = code.replace(old, new)
    return code


def migrate_file(path, resolve, dry):
    if not path.exists():
        print(f"  [skip] 없음: {path.name}")
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else (data.get("items") or data.get("data") or [])
    n = 0
    samples = []
    for it in items:
        if not isinstance(it, dict):
            continue
        code = it.get("ibl_code")
        if not code:
            continue
        new = transform(code, resolve)
        if new != code:
            if len(samples) < 4:
                samples.append((code, new))
            if not dry:
                it["ibl_code"] = new
            n += 1
    if not dry and n:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {path.name}: {n}건 {'(dry)' if dry else '치환'}")
    for o, nw in samples:
        print(f"      {o[:80]}")
        print(f"   -> {nw[:80]}")
    return n


def migrate_usage_db(resolve, dry):
    sys.path.insert(0, str(BASE / "backend"))
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    with db._get_connection() as conn:
        rows = conn.execute("SELECT id, ibl_code FROM ibl_examples").fetchall()
        n = 0
        for row in rows:
            rid, code = row[0], row[1]
            new = transform(code, resolve)
            if new != code:
                if not dry:
                    conn.execute("UPDATE ibl_examples SET ibl_code=? WHERE id=?", (new, rid))
                n += 1
        if not dry:
            conn.commit()
    print(f"  usage_db ibl_examples: {n}건 {'(dry)' if dry else '치환'} (재색인은 rebuild_index 별도)")
    return n


def migrate_world_pulse(resolve, dry, existing):
    if not WORLD_PULSE.exists():
        print("  [skip] world_pulse.db 없음"); return
    # action_health/self_checks는 bare 액션명으로 키잉됨. 옛 이름 중 일부(find/create 등)는
    # 다른 노드의 현재 캐노니컬명과 충돌하므로, 현재 카탈로그에 없는 bare명만 삭제(보수적).
    current_bare = {a for (n, a) in existing}
    old_actions = sorted(({name for (node, name) in resolve} | {"slide"}) - current_bare)
    conn = sqlite3.connect(str(WORLD_PULSE))
    try:
        ph = ",".join("?" * len(old_actions))
        d1 = conn.execute(f"SELECT COUNT(*) FROM action_health WHERE action IN ({ph})", old_actions).fetchone()[0]
        d2 = conn.execute(f"SELECT COUNT(*) FROM self_checks WHERE action IN ({ph})", old_actions).fetchone()[0]
        if not dry:
            conn.execute(f"DELETE FROM action_health WHERE action IN ({ph})", old_actions)
            conn.execute(f"DELETE FROM self_checks WHERE action IN ({ph})", old_actions)
            conn.commit()
        print(f"  world_pulse: action_health {d1}건, self_checks {d2}건 {'(dry)' if dry else '삭제'}")
    except Exception as e:
        print(f"  world_pulse 오류(무시): {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    amap = load_alias_map()
    existing = load_catalog_actions()
    resolve = build_resolve(amap, existing)

    # 검증: 모든 최종 타깃이 카탈로그에 존재하는가
    print(f"=== 검증: 별칭 {len(amap)}개 → 최종 캐노니컬 (slide 특수 제외 {len(resolve)}개) ===")
    bad = [(k, v) for k, v in resolve.items() if (v[0], v[1]) not in existing]
    if bad:
        print(f"❌ 최종 타깃이 카탈로그에 없는 별칭 {len(bad)}개:")
        for (node, name), (cn, ca, inj) in bad:
            print(f"    [{node}:{name}] -> [{cn}:{ca}] {inj}")
    else:
        print("✅ 모든 최종 타깃이 카탈로그에 존재")
    # slide 타깃 확인
    print(f"  slide -> engines:{SLIDE_NEW} 존재: {('engines', SLIDE_NEW) in existing}")
    print()

    print(f"=== 코퍼스 마이그 {'(DRY-RUN)' if dry else '(실행)'} ===")
    for f in TRAINING_FILES:
        migrate_file(f, resolve, dry)
    migrate_usage_db(resolve, dry)
    migrate_world_pulse(resolve, dry, existing)
    if not dry:
        print("\n완료. 이어서 rebuild_index() 실행 필요.")
