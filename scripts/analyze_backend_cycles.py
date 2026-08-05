#!/usr/bin/env python3
"""backend/ 의존 매듭 실측 — 감사 부채 ⑦(디렉토리화)의 지도.

왜 스크립트인가: 핸드오프에 숫자만 적어두면 다음 세션엔 이미 낡은다. ⑦은 "순환을 하나씩
푼다"가 통하지 않는 작업이라(2026-08-05 실측: 진짜 순환은 개수가 아니라 **한 덩어리 매듭**),
들어가기 전에 매듭의 현재 모양을 다시 재는 게 첫 단계다. 그 첫 단계를 도구로 고정한다.

무엇을 재나:
  ① 함수-안 import 비율 — 매듭을 *보이지 않게* 만드는 장치의 크기
  ② 톱레벨만 볼 때의 순환(=착시로 0에 가깝다) vs 함수-안까지 포함한 진짜 순환(SCC)
  ③ 매듭 안에서 **간선 하나를 끊었을 때 매듭이 얼마나 줄어드는가** — 층을 다시 그을 때
     어디를 먼저 건드릴지의 후보. 최대 감소폭이 작으면(예: -5) 단일 간선으로는 안 쪼개진다는
     뜻이고, 그러면 '층을 선언하고 거스르는 간선을 집합으로 끊는' 쪽으로 가야 한다.

사용: python3 scripts/analyze_backend_cycles.py [--edges N]
"""

import ast
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")


def _module_graph():
    """(톱레벨 그래프, 전체 그래프, 함수-안 import 수) — 노드는 backend/*.py 의 stem."""
    mods = {f[:-3] for f in os.listdir(BACKEND) if f.endswith(".py")}
    top = collections.defaultdict(set)
    allg = collections.defaultdict(set)
    infunc = collections.Counter()
    toplevel_n = 0

    def targets(node):
        if isinstance(node, ast.Import):
            return [a.name.split(".")[0] for a in node.names]
        if isinstance(node, ast.ImportFrom):
            return [(node.module or "").split(".")[0]]
        return []

    for name in sorted(mods):
        path = os.path.join(BACKEND, name + ".py")
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for n in tree.body:                      # 톱레벨
            for t in targets(n):
                if t in mods and t != name:
                    top[name].add(t)
                    toplevel_n += 1
        for fn in [x for x in ast.walk(tree)
                   if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for n in ast.walk(fn):               # 함수 안
                for t in targets(n):
                    if t in mods and t != name:
                        infunc[name] += 1
        for n in ast.walk(tree):                 # 전체(위치 무관)
            for t in targets(n):
                if t in mods and t != name:
                    allg[name].add(t)
    return top, allg, infunc, toplevel_n, mods


def _sccs(graph):
    """Tarjan — 반환은 컴포넌트 리스트(크기 1 포함)."""
    idx, low, on, st, out, c = {}, {}, set(), [], [], [0]

    def walk(v):
        idx[v] = low[v] = c[0]; c[0] += 1
        st.append(v); on.add(v)
        for w in graph.get(v, ()):
            if w not in idx:
                walk(w); low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = st.pop(); on.discard(w); comp.append(w)
                if w == v:
                    break
            out.append(comp)

    for v in list(graph):
        if v not in idx:
            walk(v)
    return out


def main() -> int:
    sys.setrecursionlimit(10000)
    show = 12
    if "--edges" in sys.argv:
        show = int(sys.argv[sys.argv.index("--edges") + 1])

    top, allg, infunc, toplevel_n, mods = _module_graph()
    infunc_n = sum(infunc.values())
    total = toplevel_n + infunc_n
    print(f"backend/*.py 모듈 {len(mods)}개")
    print(f"intra-backend import: 톱레벨 {toplevel_n} · 함수 안 {infunc_n} "
          f"→ 함수 안 {infunc_n / total * 100:.0f}%" if total else "import 없음")

    top_cyc = [c for c in _sccs(top) if len(c) > 1]
    print(f"\n① 톱레벨만 볼 때의 순환: {len(top_cyc)}개  ← 이게 '순환 0' 착시의 정체")

    comps = [c for c in _sccs(allg) if len(c) > 1]
    comps.sort(key=len, reverse=True)
    print(f"② 함수-안까지 포함한 진짜 순환: {len(comps)}개")
    for comp in comps:
        head = ", ".join(sorted(comp)[:10])
        print(f"   크기 {len(comp):3}: {head}{' …' if len(comp) > 10 else ''}")
    if not comps:
        print("   (매듭 없음 — ⑦의 전제가 사라졌다. 핸드오프를 갱신할 것)")
        return 0

    big = set(comps[0])
    edges = [(a, b) for a in big for b in allg[a] if b in big]
    print(f"\n③ 가장 큰 매듭: 모듈 {len(big)} · 내부 간선 {len(edges)}")
    scores = []
    for (a, b) in edges:
        g2 = {k: set(v) for k, v in allg.items()}
        g2[a].discard(b)
        biggest = max((len(c) for c in _sccs(g2)), default=0)
        scores.append((len(big) - biggest, a, b))
    scores.sort(reverse=True)
    useful = [s for s in scores if s[0] > 0]
    print(f"   간선 하나로 매듭이 줄어드는 것: {len(useful)}개 "
          f"(최대 감소폭 {useful[0][0] if useful else 0})")
    for d, a, b in useful[:show]:
        print(f"   -{d:3}  {a} → {b}")
    if useful and useful[0][0] < len(big) // 3:
        print("\n   ★단일 간선으로는 안 쪼개진다 — 층을 선언하고 거스르는 간선을 "
              "집합으로 끊는 쪽으로. (핸드오프 §1-⑦)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
