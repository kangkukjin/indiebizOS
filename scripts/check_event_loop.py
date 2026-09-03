#!/usr/bin/env python3
"""이벤트 루프 규율 정적 검사 — async 함수 본문의 동기 블로킹 호출 탐지(직접 + 간접).

왜: 백엔드가 단일 프로세스라 async 라우트 하나가 루프를 막으면 *서버 전체*가 선다.
게다가 이 서버는 자기 자신을 부르는 일이 잦아(창고 폴러→public_face→터널→자기,
폰↔맥 핑, /ibl/execute) 루프가 막힌 채 자기 요청을 기다리면 **자기교착**이 된다.
같은 부류가 세 번 재발했다(창고 폴러 add/poll · public_face 인프로세스 프록시 ·
/ibl/execute). 실행이 아니라 파싱으로 잡을 수 있는 부류라 AST 로 훑는다.

두 층으로 잡는다:
  ① 직접 — async 본문에 BLOCKING 원시 호출(time.sleep·subprocess·requests·os.walk…)
  ② 간접 — async 본문이 부르는 *같은 저장소의 sync 함수*가 (전이적으로) ①을 품은 경우.
     2026-09-03 사진 스캔 사고(`696b8007`)가 이 부류다: `async def scan_directory` 가
     `scanner.scan_media()` 를 그대로 불렀고, scan_media 안의 os.walk·MD5 가 외장 디스크
     16분 동안 루프를 막아 /health 까지 무응답 → keeper 가 백엔드를 죽이기 직전이었다.
     ①만 보는 검사는 그 라우트를 통과시켰다(원시 호출이 한 단계 아래 있었으므로).
     그래서 저장소 전체(backend/ + 패키지)의 호출 그래프를 만들고 sync 함수의
     블로킹 여부를 고정점까지 전파한 뒤, async 본문의 호출부에서 대조한다.

     해소 규칙(보수적 — 풀리는 것만 본다, 못 풀면 통과):
       · `foo()`        → 같은 파일 톱레벨 def / `from mod import foo` 의 mod 톱레벨 def
       · `mod.foo()`    → 파일 어디서든 `import mod`(함수 안 lazy import 포함) 한 mod 의 톱레벨 def
                          (모듈은 저장소 안 *.py 를 파일명(stem)으로 찾는다 — 이 저장소의
                          import 는 boot_paths 가 층 폴더를 sys.path 에 올린 평면 stem 방식.
                          stem 이 겹치면 같은 폴더 → 유일 후보 순, 그래도 모호하면 미해소)
       · `self.m()`     → 같은 클래스의 메서드 m
       · 그 밖(객체 메서드·동적 디스패치)은 미해소 = 통과.

허용(플래그하지 않음) — ★이 세 가지가 이 검사의 정확도를 결정한다:
  - 중첩 sync 함수 / 람다 본문
      async 안에 def 를 두고 executor 에 넘기는 것이 *정석*이다. 이걸 구분 못 하는
      나이브 스캔은 backend/api_nodes.py 의 모범 사례를 오탐한다(2026-07-25 실측).
      (sync 함수의 블로킹 판정에서도 같은 규칙 — 스레드에 넘기려 정의한 중첩 def 는 제외.)
  - 중첩 class 의 sync 메서드
  - 줄 끝 또는 바로 윗줄의 `# eventloop-ok: <사유>` 주석
      진짜 예외는 사유와 함께 선언한다(부팅 1회성 등). 사유 없는 벌거벗은 억제는 불가.
      sync 함수 안의 원시 호출에 달면 그 함수는 전파 원천에서 빠진다.

고치는 법: `await asyncio.to_thread(fn, *args)` 또는
`await asyncio.get_running_loop().run_in_executor(None, fn)` 로 스레드에 내린다.
(FastAPI 라우트라면 `async def` 를 그냥 `def` 로 바꾸는 것도 답이다 — Starlette 이
sync 라우트를 알아서 스레드풀에서 돌린다.)

대상: backend/ + data/packages/installed/. async 함수가 없는 파일은 자연히 무관.
pre-commit 훅과 CI(seam-guards.yml) 양쪽에서 호출된다.
정확도 회귀 = scripts/check_event_loop_fixtures.py (오탐/미탐 픽스처, 간접 추적 포함).
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = [ROOT / "backend", ROOT / "data" / "packages" / "installed"]
SKIP_DIRS = {"__pycache__", "_archive", "node_modules", ".git", "build", "dist"}

ALLOW_COMMENT = "eventloop-ok"

# 동기 블로킹 호출 — 점 표기 전체 이름으로 매칭한다(`import x` 든 함수 안 lazy
# import 든 호출부 모양은 같다). 보수적으로 "확실히 막는 것"만 넣는다:
# 파일 한 개 읽기·sqlite 단문처럼 짧고 편재하는 것은 넣지 않는다(오탐이 가드를 죽인다).
BLOCKING = {
    "time.sleep":                   "이벤트 루프 전체가 그 시간만큼 정지",
    "subprocess.run":               "자식 프로세스 종료까지 루프 정지",
    "subprocess.call":              "자식 프로세스 종료까지 루프 정지",
    "subprocess.check_call":        "자식 프로세스 종료까지 루프 정지",
    "subprocess.check_output":      "자식 프로세스 종료까지 루프 정지",
    "subprocess.getoutput":         "자식 프로세스 종료까지 루프 정지",
    "subprocess.getstatusoutput":   "자식 프로세스 종료까지 루프 정지",
    "os.system":                    "자식 프로세스 종료까지 루프 정지",
    "requests.get":                 "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.post":                "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.put":                 "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.patch":               "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.delete":              "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.head":                "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.request":             "동기 HTTP — 자기 자신을 부르면 자기교착",
    "httpx.get":                    "동기 HTTP(httpx 모듈 함수) — AsyncClient 를 쓰라",
    "httpx.post":                   "동기 HTTP(httpx 모듈 함수) — AsyncClient 를 쓰라",
    "httpx.put":                    "동기 HTTP(httpx 모듈 함수) — AsyncClient 를 쓰라",
    "httpx.patch":                  "동기 HTTP(httpx 모듈 함수) — AsyncClient 를 쓰라",
    "httpx.delete":                 "동기 HTTP(httpx 모듈 함수) — AsyncClient 를 쓰라",
    "httpx.head":                   "동기 HTTP(httpx 모듈 함수) — AsyncClient 를 쓰라",
    "httpx.request":                "동기 HTTP(httpx 모듈 함수) — AsyncClient 를 쓰라",
    "urllib.request.urlopen":       "동기 HTTP",
    "urllib.request.urlretrieve":   "동기 HTTP 다운로드",
    "socket.create_connection":     "동기 소켓 연결",
    "socket.gethostbyname":         "동기 DNS 조회",
    "smtplib.SMTP":                 "동기 SMTP 연결",
    "smtplib.SMTP_SSL":             "동기 SMTP 연결",
    "imaplib.IMAP4":                "동기 IMAP 연결",
    "imaplib.IMAP4_SSL":            "동기 IMAP 연결",
    "ftplib.FTP":                   "동기 FTP 연결",
    # 디스크 순회·대량 복사 — 외장/네트워크 볼륨이면 분 단위(사진 스캔 16분 실측).
    "os.walk":                      "디스크 재귀 순회 — 외장 볼륨이면 분 단위로 루프 정지",
    "os.fwalk":                     "디스크 재귀 순회 — 외장 볼륨이면 분 단위로 루프 정지",
    "shutil.rmtree":                "디스크 재귀 삭제",
    "shutil.copytree":              "디스크 재귀 복사",
    "shutil.copy":                  "파일 복사(크기 비례)",
    "shutil.copy2":                 "파일 복사(크기 비례)",
    "shutil.copyfile":              "파일 복사(크기 비례)",
    "shutil.move":                  "파일 이동(볼륨 넘으면 복사+삭제)",
}

# 수신자 타입을 정적으로 모르는 메서드 호출 중, 이름만으로 뜻이 유일한 것.
# (`Path(...).rglob` 은 점표기로 안 풀린다 — 호출 결과에 붙기 때문.)
BLOCKING_METHODS = {
    "rglob": "디스크 재귀 순회(pathlib) — 외장 볼륨이면 분 단위로 루프 정지",
}

# `from time import sleep` 처럼 벌거벗은 이름으로 들어온 경우도 잡는다.
# {모듈: {심볼}} — 위 BLOCKING 에서 파생.
_FROM_TARGETS: dict[str, set[str]] = {}
for _dotted in BLOCKING:
    _mod, _, _sym = _dotted.rpartition(".")
    _FROM_TARGETS.setdefault(_mod, set()).add(_sym)


def _dotted_name(node: ast.AST) -> str | None:
    """ast.Attribute/Name 체인을 'a.b.c' 로 편다."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _bare_aliases(tree: ast.AST) -> dict[str, str]:
    """`from time import sleep` / `from subprocess import run as srun` →
    {로컬이름: 정식 점표기}. 모듈 어디에 있든(톱레벨·함수 안) 수집한다."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in _FROM_TARGETS:
            for alias in node.names:
                if alias.name in _FROM_TARGETS[node.module]:
                    out[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return out


def _allowed_lines(src: str) -> set[int]:
    """`# eventloop-ok: 사유` 가 달린 줄 + 그 바로 다음 줄(주석을 위에 단 경우)."""
    ok: set[int] = set()
    for i, line in enumerate(src.splitlines(), start=1):
        if ALLOW_COMMENT in line:
            ok.add(i)
            ok.add(i + 1)
    return ok


def _primitive(call: ast.Call, bare: dict[str, str]):
    """호출이 BLOCKING 원시면 (이름, 사유), 아니면 None."""
    name = _dotted_name(call.func)
    if name in bare:
        name = bare[name]
    if name in BLOCKING:
        return name, BLOCKING[name]
    if isinstance(call.func, ast.Attribute) and call.func.attr in BLOCKING_METHODS:
        return f".{call.func.attr}", BLOCKING_METHODS[call.func.attr]
    return None


def _body_calls(node: ast.AST):
    """함수 본문의 Call 들 — 중첩 sync 함수·람다·클래스 서브트리는 들어가지 않는다.
    (그것들은 즉시 실행되지 않는다 — executor 에 넘기는 정석 패턴.)
    중첩 async def 도 건너뛴다(별도 함수로 따로 순회된다)."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(child, ast.Call):
            yield child
        yield from _body_calls(child)


# ── 저장소 호출 그래프 ────────────────────────────────────────────────────────

class _Module:
    """파일 하나의 인덱스: 톱레벨 함수·클래스 메서드·import 별칭."""

    def __init__(self, path: Path, src: str, tree: ast.Module):
        self.path = path
        self.src = src
        self.tree = tree
        self.bare = _bare_aliases(tree)
        self.ok_lines = _allowed_lines(src)
        self.funcs: dict[str, ast.AST] = {}          # 톱레벨 def/async def
        self.methods: dict[tuple[str, str], ast.AST] = {}  # (클래스, 메서드)
        self.mod_alias: dict[str, str] = {}          # 로컬이름 → 모듈 stem  (`import x [as y]`)
        self.sym_alias: dict[str, tuple[str, str]] = {}  # 로컬이름 → (모듈 stem, 심볼)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs[node.name] = node
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.methods[(node.name, sub.name)] = sub
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.mod_alias[alias.asname or alias.name.rpartition(".")[2]] = alias.name.rpartition(".")[2]
            elif isinstance(node, ast.ImportFrom) and node.module:
                stem = node.module.rpartition(".")[2]
                for alias in node.names:
                    if alias.name != "*":
                        self.sym_alias[alias.asname or alias.name] = (stem, alias.name)

    def all_functions(self):
        """(키, 노드, 감싸는 클래스명|None) — 톱레벨·클래스 메서드·중첩 정의 전부."""
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield node


class Corpus:
    def __init__(self, paths: list[Path]):
        self.mods: dict[Path, _Module] = {}
        self.by_stem: dict[str, list[Path]] = {}
        for p in paths:
            try:
                src = p.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=str(p))
            except (SyntaxError, UnicodeDecodeError) as e:
                rel = p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
                print(f"[warn] parse skip {rel}: {e.__class__.__name__}")
                continue
            self.mods[p] = _Module(p, src, tree)
            self.by_stem.setdefault(p.stem, []).append(p)
        # 함수 노드 → 감싸는 클래스 (self.m() 해소용)
        self._owner: dict[int, str | None] = {}
        for m in self.mods.values():
            for node in m.tree.body:
                if isinstance(node, ast.ClassDef):
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            self._owner[id(sub)] = node.name
        # sync 함수의 블로킹 판정(전이) — 키 = id(노드)
        self._blocking: dict[int, tuple] = {}   # id → (사유 문자열, 원천 위치)
        self._propagate()

    # ── 해소 ──
    def _module_for(self, stem: str, from_path: Path) -> _Module | None:
        cands = self.by_stem.get(stem) or []
        if not cands:
            return None
        if len(cands) > 1:
            same_dir = [c for c in cands if c.parent == from_path.parent]
            if len(same_dir) == 1:
                return self.mods[same_dir[0]]
            return None  # 모호 — 통과
        return self.mods[cands[0]]

    def resolve(self, call: ast.Call, mod: _Module, owner_cls: str | None) -> ast.AST | None:
        """호출부를 저장소 안 함수 노드로 푼다. 못 풀면 None."""
        f = call.func
        if isinstance(f, ast.Name):
            if f.id in mod.funcs:
                return mod.funcs[f.id]
            if f.id in mod.sym_alias:
                stem, sym = mod.sym_alias[f.id]
                target = self._module_for(stem, mod.path)
                if target and sym in target.funcs:
                    return target.funcs[sym]
            return None
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            base = f.value.id
            if base == "self" and owner_cls:
                return mod.methods.get((owner_cls, f.attr))
            if base in mod.mod_alias:
                target = self._module_for(mod.mod_alias[base], mod.path)
                if target and f.attr in target.funcs:
                    return target.funcs[f.attr]
        return None

    # ── 전파 ──
    def _propagate(self):
        """sync 함수: 본문(중첩 정의 제외)에 원시 호출이 있거나, 블로킹으로 판정된 sync
        함수를 부르면 블로킹. 고정점까지 반복."""
        entries = []
        for m in self.mods.values():
            for node in m.all_functions():
                if isinstance(node, ast.AsyncFunctionDef):
                    continue
                entries.append((m, node, self._owner.get(id(node))))
        # 1단계: 직접 원시
        for m, node, _cls in entries:
            for call in _body_calls(node):
                if call.lineno in m.ok_lines:
                    continue
                prim = _primitive(call, m.bare)
                if prim:
                    self._blocking[id(node)] = (f"{prim[0]}() — {prim[1]}", self._loc(m, call.lineno), node.name)
                    break
        # 2단계: 전이
        changed = True
        while changed:
            changed = False
            for m, node, cls in entries:
                if id(node) in self._blocking:
                    continue
                for call in _body_calls(node):
                    tgt = self.resolve(call, m, cls)
                    if tgt is not None and id(tgt) in self._blocking:
                        why, loc, leaf = self._blocking[id(tgt)]
                        self._blocking[id(node)] = (why, loc, leaf)
                        changed = True
                        break

    @staticmethod
    def _loc(m: _Module, lineno: int) -> str:
        rel = m.path.relative_to(ROOT) if m.path.is_relative_to(ROOT) else m.path
        return f"{rel}:{lineno}"

    # ── 보고 ──
    def scan(self, path: Path) -> list[tuple]:
        """파일 하나의 async 함수들을 대조. 반환: (lineno, 호출이름, 사유, async 함수명)."""
        m = self.mods.get(path)
        if m is None:
            return []
        out: list = []
        for node in m.all_functions():
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            cls = self._owner.get(id(node))
            for call in _body_calls(node):
                if call.lineno in m.ok_lines:
                    continue
                prim = _primitive(call, m.bare)
                if prim:
                    out.append((call.lineno, prim[0], prim[1], node.name))
                    continue
                tgt = self.resolve(call, m, cls)
                if tgt is not None and not isinstance(tgt, ast.AsyncFunctionDef) and id(tgt) in self._blocking:
                    why, loc, leaf = self._blocking[id(tgt)]
                    shown = _dotted_name(call.func) or tgt.name
                    out.append((call.lineno, shown, f"간접: {leaf}() 안 {why} ({loc})", node.name))
        seen = set()
        kept = []
        for item in sorted(out):
            key = (item[0], item[1])
            if key in seen:
                continue
            seen.add(key)
            kept.append(item)
        return kept


def _corpus_paths() -> list[Path]:
    paths = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            # 시험 파일(pytest 수집 대상)은 서버 이벤트 루프 위에서 돌지 않는다 — 시험 대역의
            # async 함수는 이 규율의 대상이 아니다(2026-09-03, test_narration_injection 의 fake_tts).
            if path.name.startswith("test_"):
                continue
            paths.append(path)
    return paths


def scan_file(path: Path, corpus: "Corpus | None" = None):
    """파일 하나 검사(픽스처용). corpus 를 안 주면 그 파일 하나만으로 그래프를 만든다."""
    if corpus is None:
        corpus = Corpus([path])
    return corpus.scan(path)


def main() -> int:
    paths = _corpus_paths()
    corpus = Corpus(paths)
    flagged = []
    for path in paths:
        for lineno, name, why, fname in corpus.scan(path):
            flagged.append((path.relative_to(ROOT), lineno, name, why, fname))

    if flagged:
        print(f"[FAIL] async 함수 본문의 동기 블로킹 호출 {len(flagged)}건 — 이벤트 루프가 멈춥니다:")
        for rel, lineno, name, why, fname in flagged:
            print(f"  {rel}:{lineno}  {name}()  in async {fname}()  — {why}")
        print()
        print("고치는 법:")
        print("  · await asyncio.to_thread(fn, *args)  (권장)")
        print("  · await asyncio.get_running_loop().run_in_executor(None, _nested_sync_fn)")
        print("  · FastAPI 라우트면 `async def` → `def` (Starlette 이 스레드풀로 돌림)")
        print("  · 진짜 예외면 그 줄에 `# eventloop-ok: <사유>` (사유 필수)")
        return 1

    print(f"[OK] 이벤트 루프 규율 통과 (async 본문에 동기 블로킹 호출 없음 — 직접·간접, {len(paths)}파일)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
