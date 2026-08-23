#!/usr/bin/env python3
"""카탈로그 인코딩 오프라인 선택 정확도 평가 (2026-07-28).

배경: 카탈로그 감사 메모의 [미측정] 항목 — 인코딩 압축(R1 태그 제거 −32%,
R2 +op설명 전삭 −55%)이 실제 액션·op 선택 정확도에 주는 영향. 인코딩 변경은
이 측정을 통과한 뒤에만 한다(카탈로그는 캐싱되어 토큰 비용은 이미 싸다 —
진짜 쟁점은 경량·중급 티어의 선택 정확도).

방법: 해마 코퍼스(ibl_usage.db)의 단일 액션 예제에서 표본 추출(실경험 우선)
→ 각 인코딩의 카탈로그 + 사용자 명령을 경량 모델(lightweight_ai_config)에 물려
JSON {action, op} 응답 → 골드(예제 코드의 액션·op)와 대조. 프로덕션 코드 무접촉.

사용:
  python3 scripts/catalog_encoding_eval.py --smoke          # 표본 6건 동작 확인
  python3 scripts/catalog_encoding_eval.py --n 150          # 본 실험
  python3 scripts/catalog_encoding_eval.py --report-only    # 캐시로 리포트만

결과 캐시(재개 가능): --out 디렉토리의 results_<encoding>.jsonl
"""
from __future__ import annotations
import argparse
import concurrent.futures as cf
import json
import random
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

REAL_SOURCES = {"distilled", "manual_seed", "manual", "curated", "curated_v2", "manual_coverage"}


# ---------------------------------------------------------------- 카탈로그 로드

def load_nodes() -> dict:
    import yaml
    data = yaml.safe_load((ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
    return data


def _visible_actions(node_config: dict):
    """프로덕션 build_environment 의 가시성 필터 근사 — prompt_hidden·phone_only 제외.

    (dormant 표시·capability_card 는 두 인코딩에 동일하게 생략 — 비교엔 중립)"""
    for aname, acfg in (node_config.get("actions") or {}).items():
        if not isinstance(acfg, dict):
            continue
        if acfg.get("prompt_hidden"):
            continue
        if acfg.get("runs_on") == "phone_only":
            continue
        yield aname, acfg


def _grouped(node_config: dict):
    grouped: dict[str, list] = {}
    ungrouped: list = []
    for aname, acfg in _visible_actions(node_config):
        g = acfg.get("group")
        (grouped.setdefault(g, []) if g else ungrouped).append((aname, acfg))
    return grouped, ungrouped


def render_r0(data: dict) -> str:
    """현행 프로덕션 XML (ibl_access._emit_action_xml 충실 재현)."""
    nodes = data.get("nodes", {})
    parts = ["<ibl_actions>"]
    parts.append(f'<nodes available="{", ".join(sorted(nodes))}">')
    constraint = data.get("meta", {}).get("constraint", "")
    if constraint:
        parts.append(f"<constraint>{constraint}</constraint>")
    for nname, ncfg in nodes.items():
        parts.append(f'<node name="{nname}" description="{ncfg.get("description", "")}">')
        grouped, ungrouped = _grouped(ncfg)
        for gname, acts in grouped.items():
            parts.append(f'<group name="{gname}">')
            for aname, acfg in acts:
                parts.append(_emit_xml(aname, acfg, "  "))
            parts.append("</group>")
        if ungrouped:
            parts.append("<actions>")
            for aname, acfg in ungrouped:
                parts.append(_emit_xml(aname, acfg, "  "))
            parts.append("</actions>")
        parts.append("</node>")
    parts.append("</nodes>")
    parts.append("</ibl_actions>")
    return "\n".join(parts)


def _emit_xml(aname: str, acfg: dict, indent: str = "") -> str:
    desc = acfg.get("description", "")
    ops = acfg.get("ops")
    if not isinstance(ops, dict) or not ops.get("values"):
        return f'{indent}<action name="{aname}" description="{desc}"/>'
    default = ops.get("default")
    lines = [f'{indent}<action name="{aname}" description="{desc}">']
    for op_name, op_desc in (ops.get("values") or {}).items():
        attrs = f'name="{op_name}"'
        if op_name == default:
            attrs += ' default="true"'
        lines.append(f"{indent}  <op {attrs}>{op_desc}</op>")
    lines.append(f"{indent}</action>")
    return "\n".join(lines)


_R1_LEGEND = (
    "# 표기법: '이름 :: 설명' = 액션. 그 아래 들여쓴 '.op이름 설명' = 그 액션의 op (*표=기본 op). "
    "⟨인자: a·(b)⟩ = 실측 입력 인자(괄호=선택).\n"
)

# R3: "이름이 자명한" op 는 설명을 억제(이름만) — 메모의 '49개 비자명만 유지' 경계의 보수판.
# 조건: 이름(또는 _ 앞 어간)이 자명 동사 + 설명 60자 이하 + 파라미터 신호('='·'필수') 없음.
_SELF_EVIDENT_OPS = {
    "list", "detail", "create", "delete", "update", "save", "add", "remove", "search",
    "play", "stop", "pause", "status", "scan", "refresh", "run", "open", "close", "send",
    "read", "write", "get", "set", "start", "download", "upload", "install", "uninstall",
    "enable", "disable", "clear", "cancel", "query", "info", "stats", "summary", "check",
    "test", "preview", "publish", "export", "import", "sync", "toggle", "history",
    "recent", "rename", "move", "copy", "edit", "view", "show",
}


def _op_desc_suppressible(op_name: str, op_desc: str) -> bool:
    base = op_name.split("_")[0]
    d = op_desc or ""
    return ((op_name in _SELF_EVIDENT_OPS or base in _SELF_EVIDENT_OPS)
            and len(d) <= 60 and "=" not in d and "필수" not in d)


_PARAM_SHAPES: dict | None = None


def _param_shapes() -> dict:
    """R4 용 실측 입력 인자(data/ibl_param_shapes.json) — 없으면 빈 dict (R4=R3 와 동일)."""
    global _PARAM_SHAPES
    if _PARAM_SHAPES is None:
        try:
            doc = json.loads((ROOT / "data" / "ibl_param_shapes.json").read_text(encoding="utf-8"))
            _PARAM_SHAPES = {"shapes": doc.get("shapes", {}), "always": float(doc.get("always_ratio", 0.8))}
        except Exception:
            _PARAM_SHAPES = {"shapes": {}, "always": 0.8}
    return _PARAM_SHAPES


def _param_suffix(qualified: str, op: str | None = None) -> str:
    """ibl_access._param_suffix 충실 재현 — ⟨인자: a·b·(c)⟩ (op 줄은 액션과 이름이 다를 때만)."""
    ps = _param_shapes()
    shapes = ps["shapes"]
    if not shapes:
        return ""
    always = ps["always"]
    if op is None:
        ent = shapes.get(qualified)
    else:
        ent = shapes.get(f"{qualified}#{op}")
        base = shapes.get(qualified)
        if ent and base:
            base_keys = {k for k, _ in base.get("keys", [])}
            base_plain = {k for k, r in base.get("keys", []) if r >= always}
            op_keys = [k for k, _ in ent.get("keys", [])[:8]]
            op_plain = {k for k, r in ent.get("keys", [])[:8] if r >= always}
            if not (set(op_keys) - base_keys) and not (op_plain - base_plain):
                return ""
    if not ent or not ent.get("keys"):
        return ""
    parts = [k if r >= always else f"({k})" for k, r in ent["keys"][:8]]
    return " ⟨인자: " + "·".join(parts) + "⟩"


def render_r1(data: dict, strip_op_desc: bool = False, qualify: bool = False,
              suppress_evident: bool = False, only_nodes: set | None = None,
              param_shapes: bool = False) -> str:
    """R1: 태그 제거 줄 표기 (설명 무손실). strip_op_desc=True 면 R2(op 설명 전삭, 이름만).
    qualify=True 면 액션 이름을 node:action 완전수식 — 스모크에서 비수식 R1 이 그룹명을
    노드로 오인(travel:stay 환각)하는 소속 약화가 관측되어 처방 변형으로 추가."""
    nodes = data.get("nodes", {})
    parts = [_R1_LEGEND]
    constraint = data.get("meta", {}).get("constraint", "")
    if constraint:
        parts.append(f"# 제약: {constraint}")
    for nname, ncfg in nodes.items():
        if only_nodes is not None and nname not in only_nodes:
            continue
        parts.append(f"\n= 노드 {nname} :: {ncfg.get('description', '')}")
        grouped, ungrouped = _grouped(ncfg)
        for gname, acts in grouped.items():
            parts.append(f"  [{gname}]")
            for aname, acfg in acts:
                parts.append(_emit_line(aname, acfg, strip_op_desc, nname if qualify else None, suppress_evident, param_shapes))
        for aname, acfg in ungrouped:
            parts.append(_emit_line(aname, acfg, strip_op_desc, nname if qualify else None, suppress_evident, param_shapes))
    return "\n".join(parts)


def _emit_line(aname: str, acfg: dict, strip_op_desc: bool, node: str | None = None,
               suppress_evident: bool = False, param_shapes: bool = False) -> str:
    desc = acfg.get("description", "")
    ops = acfg.get("ops")
    shown = f"{node}:{aname}" if node else aname
    qualified = f"{node}:{aname}" if node else aname
    psfx = _param_suffix(qualified) if param_shapes else ""
    lines = [f"  {shown} :: {desc}{psfx}"]
    if isinstance(ops, dict) and ops.get("values"):
        default = ops.get("default")
        for op_name, op_desc in (ops.get("values") or {}).items():
            star = "*" if op_name == default else ""
            osfx = _param_suffix(qualified, op_name) if param_shapes else ""
            if (strip_op_desc or (suppress_evident and _op_desc_suppressible(op_name, op_desc))) and not osfx:
                lines.append(f"    .{op_name}{star}")
            else:
                lines.append(f"    .{op_name}{star} {op_desc}{osfx}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 표본

_ACT_RE = re.compile(r"\[(\w+):(\w+)\]")
_OP_RE = re.compile(r'op\s*:\s*"([^"]+)"')


def sample_examples(n: int, seed: int = 42) -> list[dict]:
    db = sqlite3.connect(ROOT / "data" / "ibl_usage.db")
    rows = db.execute("select id, intent, ibl_code, source from ibl_examples").fetchall()
    singles = []
    for eid, intent, code, src in rows:
        acts = _ACT_RE.findall(code or "")
        if len(acts) != 1 or not (intent or "").strip():
            continue
        m = _OP_RE.search(code)
        singles.append({
            "id": eid, "intent": intent.strip(), "code": code,
            "gold_action": f"{acts[0][0]}:{acts[0][1]}",
            "gold_op": m.group(1) if m else None,
            "real": src in REAL_SOURCES, "source": src,
        })
    rng = random.Random(seed)
    real = [s for s in singles if s["real"]]
    syn = [s for s in singles if not s["real"]]
    rng.shuffle(real); rng.shuffle(syn)
    n_real = min(len(real), (n * 2) // 3)
    picked = real[:n_real] + syn[: n - n_real]
    rng.shuffle(picked)
    return picked


# ---------------------------------------------------------------- 모델 호출

def _model_conf() -> dict:
    c = json.loads((ROOT / "data" / "lightweight_ai_config.json").read_text())
    key = c.get("apiKey") or ""
    if not key:
        # 설정 json 의 apiKey 가 비어 있으면 .env 의 DEEPSEEK_API_KEY (백엔드와 같은 출처, 2026-08-23)
        import os
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key and (ROOT / ".env").exists():
            for ln in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
                if ln.startswith("DEEPSEEK_API_KEY="):
                    key = ln.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("DeepSeek 키 없음 — data/lightweight_ai_config.json apiKey 또는 .env DEEPSEEK_API_KEY")
    return {"model": c["model"], "key": key,
            "url": "https://api.deepseek.com/chat/completions"}


_PROMPT = """당신은 IndieBiz OS 의 IBL 액션 선택기입니다. 아래 액션 카탈로그에서 사용자 명령을 수행하기에 가장 적합한 액션 하나를 고르세요.

{catalog}

사용자 명령: "{intent}"

JSON 한 줄로만 답하세요 (설명 금지): {{"action": "<노드>:<액션이름>", "op": "<op이름 또는 null>"}}
그 액션에 op 가 없거나 기본 op 면 null 로 두어도 됩니다."""


def ask(conf: dict, catalog: str, intent: str, retries: int = 3) -> dict:
    import requests
    body = {
        "model": conf["model"],
        "messages": [{"role": "user", "content": _PROMPT.format(catalog=catalog, intent=intent)}],
        "temperature": 0,
        # deepseek-v4-flash 는 reasoning 모델 — max_tokens 를 추론이 소진하면
        # content 가 빈다(gemini thinkingBudget 함정과 같은 부류). 넉넉히.
        "max_tokens": 2000,
    }
    last = None
    for i in range(retries):
        try:
            r = requests.post(conf["url"], json=body, timeout=120,
                              headers={"Authorization": f"Bearer {conf['key']}"})
            if r.status_code == 429:
                time.sleep(3 * (i + 1)); continue
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            content = msg.get("content") or ""
            if "{" not in content:  # 추론만 남고 답이 잘린 경우 reasoning 꼬리에서 회수
                content = msg.get("reasoning_content") or ""
            m = re.search(r"\{.*\}", content, re.S)
            if not m:
                return {"error": f"no-json: {content[:120]}"}
            out = json.loads(m.group(0))
            return {"action": out.get("action"), "op": out.get("op")}
        except Exception as e:  # noqa: BLE001
            last = str(e); time.sleep(2 * (i + 1))
    return {"error": last or "unknown"}


# ---------------------------------------------------------------- 노드 스코핑 (2단)

_CORE_NODES = {"self", "others", "table"}  # always_on 기능어 코어 — 스코핑에도 항상 포함

_SCOPE_PROMPT = """당신은 IndieBiz OS 의 노드 선별기입니다. 아래는 노드 개요(설명 + 액션 이름 목록)입니다.

{menu}

사용자 명령: "{intent}"

이 명령을 처리하는 데 필요할 수 있는 노드를 고르세요. self/others/table 은 항상 포함되므로 답에 넣지 마세요 — sense/limbs/engines 중 필요한 것만 고르세요. 확실하지 않으면 포함하세요(빼면 그 노드의 능력을 아예 못 씁니다).
JSON 한 줄로만 답하세요: {{"nodes": ["sense"]}} (필요 없으면 빈 배열)"""


def render_node_menu(data: dict) -> str:
    parts = []
    for nname, ncfg in data.get("nodes", {}).items():
        acts = [a for a, _ in _visible_actions(ncfg)]
        parts.append(f"= {nname} :: {ncfg.get('description', '')}\n  액션: {', '.join(acts)}")
    return "\n".join(parts)


def ask_nodes(conf: dict, menu: str, intent: str) -> list[str]:
    import requests
    body = {"model": conf["model"], "temperature": 0, "max_tokens": 1500,
            "messages": [{"role": "user", "content": _SCOPE_PROMPT.format(menu=menu, intent=intent)}]}
    for i in range(3):
        try:
            r = requests.post(conf["url"], json=body, timeout=120,
                              headers={"Authorization": f"Bearer {conf['key']}"})
            if r.status_code == 429:
                time.sleep(3 * (i + 1)); continue
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            content = msg.get("content") or ""
            if "{" not in content:
                content = msg.get("reasoning_content") or ""
            m = re.search(r"\{.*\}", content, re.S)
            if m:
                got = json.loads(m.group(0)).get("nodes") or []
                return [n for n in got if n in ("sense", "limbs", "engines")]
        except Exception:  # noqa: BLE001
            time.sleep(2 * (i + 1))
    return ["sense", "limbs", "engines"]  # 실패 시 전체(스코핑 무효화 = 안전)


def run_scoped(data: dict, samples: list[dict], out_dir: Path, workers: int = 8):
    """2단: ①경량이 노드 개요만 보고 노드 선별 → ②코어+선별 노드만의 R1q 카탈로그로 액션 선택."""
    conf = _model_conf()
    menu = render_node_menu(data)
    out_path = out_dir / "results_SCOPED.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                done.add(json.loads(line)["id"])
            except Exception:  # noqa: BLE001
                pass
    todo = [s for s in samples if s["id"] not in done]
    if not todo:
        print(f"[SCOPED] 캐시 완료 ({len(done)}건)")
        return
    print(f"[SCOPED] {len(todo)}건 2단 호출 (노드 메뉴 {len(menu):,}자)")
    lock = threading.Lock()
    cat_cache: dict[frozenset, str] = {}
    t0 = time.time()

    def work(s):
        picked = ask_nodes(conf, menu, s["intent"])
        allowed = frozenset(_CORE_NODES | set(picked))
        with lock:
            if allowed not in cat_cache:
                cat_cache[allowed] = render_r1(data, qualify=True, only_nodes=set(allowed))
        catalog = cat_cache[allowed]
        pred = ask(conf, catalog, s["intent"])
        rec = {"id": s["id"], "picked": picked, "cat_chars": len(catalog), **pred}
        with lock:
            with out_path.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    with cf.ThreadPoolExecutor(workers) as ex:
        n_done = 0
        for _ in ex.map(work, todo):
            n_done += 1
            if n_done % 25 == 0:
                print(f"  [SCOPED] {n_done}/{len(todo)} ({time.time()-t0:.0f}s)")
    print(f"[SCOPED] 완료 ({time.time()-t0:.0f}s)")


def report_scoped(samples: list[dict], out_dir: Path):
    p = out_dir / "results_SCOPED.jsonl"
    if not p.exists():
        return
    by_id = {s["id"]: s for s in samples}
    miss = []
    chars = []
    n = 0
    for line in p.read_text().splitlines():
        r = json.loads(line)
        s = by_id.get(r["id"])
        if not s:
            continue
        n += 1
        chars.append(r.get("cat_chars") or 0)
        gnode = s["gold_action"].split(":")[0]
        if gnode not in _CORE_NODES and gnode not in (r.get("picked") or []):
            miss.append((r["id"], s["intent"], gnode, r.get("picked")))
    print(f"\n[SCOPED 부가지표] 평균 축소 카탈로그 {sum(chars)//max(len(chars),1):,}자 | "
          f"노드 선별 누락 {len(miss)}/{n}")
    for eid, intent, gnode, picked in miss[:8]:
        print(f"  누락 #{eid} '{intent[:36]}' 골드노드={gnode} 선별={picked}")


# ---------------------------------------------------------------- 실행/채점

def run_encoding(name: str, catalog: str, samples: list[dict], out_dir: Path, workers: int = 8):
    conf = _model_conf()
    out_path = out_dir / f"results_{name}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                done.add(json.loads(line)["id"])
            except Exception:  # noqa: BLE001
                pass
    todo = [s for s in samples if s["id"] not in done]
    if not todo:
        print(f"[{name}] 캐시 완료 ({len(done)}건)")
        return
    lock = threading.Lock()
    print(f"[{name}] {len(todo)}건 호출 (캐시 {len(done)}건, 카탈로그 {len(catalog):,}자)")
    t0 = time.time()

    def work(s):
        pred = ask(conf, catalog, s["intent"])
        rec = {"id": s["id"], **pred}
        with lock:
            with out_path.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    with cf.ThreadPoolExecutor(workers) as ex:
        n_done = 0
        for _ in ex.map(work, todo):
            n_done += 1
            if n_done % 25 == 0:
                print(f"  [{name}] {n_done}/{len(todo)} ({time.time()-t0:.0f}s)")
    print(f"[{name}] 완료 ({time.time()-t0:.0f}s)")


def _op_default(data: dict, qualified: str):
    try:
        n, a = qualified.split(":")
        ops = data["nodes"][n]["actions"][a].get("ops") or {}
        return ops.get("default"), set((ops.get("values") or {}).keys())
    except Exception:  # noqa: BLE001
        return None, set()


def score(data: dict, samples: list[dict], out_dir: Path, encodings: list[str]):
    by_id = {s["id"]: s for s in samples}
    results = {}
    for enc in list(encodings):
        p = out_dir / f"results_{enc}.jsonl"
        recs = {}
        if p.exists():
            for line in p.read_text().splitlines():
                r = json.loads(line)
                recs[r["id"]] = r
        if not recs:
            encodings.remove(enc)  # 결과 없는 인코딩은 채점 제외 (교집합 붕괴 방지)
            continue
        results[enc] = recs

    common = set(by_id)
    for enc in encodings:
        common &= set(results[enc])
    common = sorted(common)
    print(f"\n===== 채점 (공통 표본 {len(common)}건) =====")

    verdicts = {enc: {} for enc in encodings}
    for enc in encodings:
        act_ok = op_ok = op_total = err = 0
        act_ok_real = n_real = 0
        for eid in common:
            s, r = by_id[eid], results[enc][eid]
            if r.get("error"):
                err += 1
                verdicts[enc][eid] = False
                continue
            pred_act = (r.get("action") or "").strip().strip("[]")
            a_ok = pred_act == s["gold_action"]
            verdicts[enc][eid] = a_ok
            act_ok += a_ok
            if s["real"]:
                n_real += 1; act_ok_real += a_ok
            # op 채점: 골드에 명시 op 가 있을 때만 (없으면 default 합의로 중립)
            if a_ok and s["gold_op"]:
                default, values = _op_default(data, s["gold_action"])
                pred_op = r.get("op") or default
                op_total += 1
                op_ok += (pred_op == s["gold_op"]) or (s["gold_op"] == default and r.get("op") in (None, default))
        n = len(common)
        print(f"[{enc}] 액션 {act_ok}/{n} = {act_ok/n*100:.1f}%"
              f" (실경험 {act_ok_real}/{n_real} = {act_ok_real/max(n_real,1)*100:.1f}%)"
              f" | op {op_ok}/{op_total} = {op_ok/max(op_total,1)*100:.1f}% | 오류 {err}")

    base = encodings[0]
    for enc in encodings[1:]:
        b = c = 0
        flips = []
        for eid in common:
            v0, v1 = verdicts[base][eid], verdicts[enc][eid]
            if v0 and not v1:
                b += 1; flips.append((eid, "잃음"))
            elif v1 and not v0:
                c += 1; flips.append((eid, "얻음"))
        print(f"\n[{base} vs {enc}] {base}만 정답 {b} / {enc}만 정답 {c} (쌍별)")
        for eid, kind in flips[:12]:
            s = by_id[eid]
            r0a = results[base][eid].get("action"); r1a = results[enc][eid].get("action")
            print(f"  {kind} #{eid} '{s['intent'][:40]}' 골드={s['gold_action']} {base}={r0a} {enc}={r1a}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out_dir = Path(args.out) if args.out else ROOT / "outputs" / "catalog_eval"
    out_dir.mkdir(parents=True, exist_ok=True)

    data = load_nodes()
    n = 6 if args.smoke else args.n
    samples = sample_examples(n)
    (out_dir / "samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=1))

    encodings = {
        "R0": render_r0(data),
        "R1": render_r1(data),
        "R1q": render_r1(data, qualify=True),
        "R2": render_r1(data, strip_op_desc=True, qualify=True),
        "R3": render_r1(data, qualify=True, suppress_evident=True),
        # R4 (2026-08-23): R3 + ⟨인자: …⟩ 실측 입력 인자 — 프로덕션 현행.
        "R4": render_r1(data, qualify=True, suppress_evident=True, param_shapes=True),
    }
    for name, cat in encodings.items():
        (out_dir / f"catalog_{name}.txt").write_text(cat)
    print("카탈로그 자수:", {k: f"{len(v):,}" for k, v in encodings.items()},
          f"| 표본 {len(samples)}건 (실경험 {sum(s['real'] for s in samples)})")

    if not args.report_only:
        for name, cat in encodings.items():
            run_encoding(name, cat, samples, out_dir, args.workers)
        run_scoped(data, samples, out_dir, args.workers)

    score(data, samples, out_dir, list(encodings) + ["SCOPED"])
    report_scoped(samples, out_dir)


if __name__ == "__main__":
    main()
