"""music-player/handler.py — 내 음악 라이브러리 ([self:music]).

소스 폴더 등록 → 백그라운드 스캔(mutagen 태그) → 라이브러리 질의 + 플레이리스트.
재생은 핸들러가 하지 않는다 — 통화의 stream 필드(/music/stream)를 보는 표면의
<audio>(media_player 프리미티브)가 문다. [limbs:music](유튜브뮤직)과 다른 개념:
그쪽은 유튜브 스트림 재생, 이쪽은 내 파일 라이브러리 (sense:radio/limbs:radio 공존 선례).

로직은 music_core.py — api_music.py(스트리밍·앨범아트)와 sys.modules 공유 키로
같은 인스턴스를 쓴다(bulletin_core 선례).
"""

import json
import os
import random
import re
import sys
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[5]
_BACKEND = str(_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from common.currency import items  # IBL 단일 통화 생성자

_CORE = None


def _core():
    """music_core 를 sys.modules 공유 키로 로드 — api_music 과 같은 인스턴스(락 공유)."""
    global _CORE
    if _CORE is not None:
        return _CORE
    key = "indiebiz_music_core"
    if key in sys.modules:
        _CORE = sys.modules[key]
        return _CORE
    p = Path(__file__).resolve().parent / "music_core.py"
    spec = importlib.util.spec_from_file_location(key, str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[key] = mod
    _CORE = mod
    return mod


_EMPTY_HINT = "라이브러리가 비어 있습니다. 보관함 탭에서 음악 폴더를 등록하고 스캔하세요."


# ── 라이브러리 질의 ──────────────────────────────────────────────────────

def _library(params: dict) -> dict:
    c = _core()
    rows = c.query_tracks(
        q=(params.get("q") or "").strip(),
        artist=(params.get("artist") or "").strip(),
        album=(params.get("album") or "").strip(),
        albumartist=(params.get("albumartist") or "").strip(),
        path=(params.get("path") or "").strip(),
        folder=(params.get("folder") or "").strip(),
        limit=params.get("limit") or 300,
    )
    if not rows:
        return items([], message=_EMPTY_HINT if not c.load_sources() else "조건에 맞는 곡이 없습니다.")
    return items(rows, count=len(rows))


def _track(params: dict) -> dict:
    """곡 하나 상세 — 재생 + 태그 + '플레이리스트에 담기' 드릴용 (playlists 에 track_path 동봉)."""
    c = _core()
    path = (params.get("path") or "").strip()
    rows = c.query_tracks(path=path, limit=1)
    if not rows:
        return items([], success=False, message="곡을 찾을 수 없습니다 (스캔이 오래됐을 수 있어요).")
    t = rows[0]
    pls = [{"name": p["name"], "meta": f"{len(p.get('tracks', []))}곡",
            "track_path": t["path"],
            "has_track": t["path"] in p.get("tracks", [])}
           for p in c.load_playlists()]
    related = c.related_of(t["path"])
    return items([t], track=t, playlists=pls, related=related,
                 related_note="" if related else "관련곡이 아직 없습니다 (스캔 후 그래프가 만들어집니다).",
                 playlists_note="" if pls else "플레이리스트가 아직 없습니다. 플레이리스트 탭에서 만드세요.")


def _albums(params: dict) -> dict:
    c = _core()
    rows = c.list_albums()
    if not rows:
        return items([], message=_EMPTY_HINT)
    return items(rows, count=len(rows))


def _artists(params: dict) -> dict:
    c = _core()
    rows = c.list_artists()
    if not rows:
        return items([], message=_EMPTY_HINT)
    return items(rows, count=len(rows))


# ── 관련곡 그래프 · 폴더 ────────────────────────────────────────────────

def _related(params: dict) -> dict:
    c = _core()
    path = (params.get("path") or "").strip()
    if not path:
        return items([], success=False, message="path(곡 절대경로)를 주세요.")
    rows = c.related_of(path, limit=params.get("limit") or 10)
    return items(rows, count=len(rows),
                 message="" if rows else "관련곡이 없습니다 (스캔 후 그래프가 만들어집니다).")


def _walk(params: dict) -> dict:
    """관련곡 랜덤 워크 재생목록 — q(시작곡 검색) 또는 path, 둘 다 없으면 랜덤 시작."""
    c = _core()
    rows = c.walk_playlist(
        start_path=(params.get("path") or "").strip(),
        q=(params.get("q") or "").strip(),
        length=params.get("length") or 30,
    )
    if not rows:
        return items([], message=_EMPTY_HINT)
    return items(rows, count=len(rows), start=rows[0]["title"],
                 message=f"'{rows[0]['title']}'에서 시작하는 관련곡 산책 {len(rows)}곡.")


def _folders(params: dict) -> dict:
    c = _core()
    rows = c.list_folders()
    if not rows:
        return items([], message=_EMPTY_HINT)
    return items(rows, count=len(rows))


def _graph(params: dict) -> dict:
    """에고 그래프 (중심+1·2홉) — 그래프 뷰 계기가 소비. items=노드(통화 유지)."""
    c = _core()
    g = c.ego_graph(
        path=(params.get("path") or "").strip(),
        q=(params.get("q") or "").strip(),
    )
    return items(g["nodes"], edges=g["edges"], center=g["center"],
                 message="" if g["nodes"] else _EMPTY_HINT)


# ── 플레이리스트 ─────────────────────────────────────────────────────────

def _playlists(params: dict) -> dict:
    c = _core()
    rows = [{"name": p["name"], "title": p["name"], "n": len(p.get("tracks", [])),
             "meta": f"{len(p.get('tracks', []))}곡", "created_at": p.get("created_at", "")}
            for p in c.load_playlists()]
    if not rows:
        return items([], message="플레이리스트가 없습니다. 이름을 넣어 만들어 보세요.")
    return items(rows, count=len(rows))


def _playlist(params: dict) -> dict:
    c = _core()
    name = (params.get("name") or "").strip()
    pl = c.find_playlist(c.load_playlists(), name)
    if pl is None:
        return items([], success=False, message=f"플레이리스트가 없습니다: {name}")
    rows = c.playlist_tracks(pl)
    return items(rows, name=pl["name"], count=len(rows),
                 message="" if rows else "빈 플레이리스트입니다. 전곡 탭에서 곡을 눌러 담으세요.")


def _playlist_create(params: dict) -> dict:
    c = _core()
    name = (params.get("name") or "").strip()
    if not name:
        return items([], success=False, message="플레이리스트 이름을 입력해 주세요.")
    pls = c.load_playlists()
    if c.find_playlist(pls, name):
        return items([], success=False, message=f"같은 이름의 플레이리스트가 이미 있습니다: {name}")
    from datetime import datetime
    pls.append({"name": name, "created_at": datetime.now().isoformat(timespec="seconds"), "tracks": []})
    c.save_playlists(pls)
    return items([{"name": name, "title": name, "n": 0, "meta": "0곡"}],
                 success=True, message=f"플레이리스트 '{name}' 생성. 전곡 탭에서 곡을 눌러 담으세요.")


def _playlist_delete(params: dict) -> dict:
    c = _core()
    name = (params.get("name") or "").strip()
    pls = c.load_playlists()
    kept = [p for p in pls if p["name"] != name]
    if len(kept) == len(pls):
        return items([], success=False, message=f"플레이리스트가 없습니다: {name}")
    c.save_playlists(kept)
    return items([], success=True, message=f"플레이리스트 '{name}' 삭제.")


def _playlist_add(params: dict) -> dict:
    c = _core()
    name = (params.get("name") or "").strip()
    path = c.norm_path(params.get("path") or "")
    pls = c.load_playlists()
    pl = c.find_playlist(pls, name)
    if pl is None:
        return items([], success=False, message=f"플레이리스트가 없습니다: {name}")
    if not c.query_tracks(path=path, limit=1):
        return items([], success=False, message="라이브러리에 없는 곡입니다.")
    if path in pl.setdefault("tracks", []):
        return items([], success=False, message=f"이미 '{name}'에 있는 곡입니다.")
    pl["tracks"].append(path)
    c.save_playlists(pls)
    return items([], success=True, message=f"'{name}'에 담았습니다 ({len(pl['tracks'])}곡).")


def _playlist_remove(params: dict) -> dict:
    c = _core()
    name = (params.get("name") or "").strip()
    path = c.norm_path(params.get("path") or "")
    pls = c.load_playlists()
    pl = c.find_playlist(pls, name)
    if pl is None:
        return items([], success=False, message=f"플레이리스트가 없습니다: {name}")
    if path not in pl.get("tracks", []):
        return items([], success=False, message="이 플레이리스트에 없는 곡입니다.")
    pl["tracks"] = [p for p in pl["tracks"] if p != path]
    c.save_playlists(pls)
    return items([], success=True, message=f"'{name}'에서 뺐습니다 ({len(pl['tracks'])}곡).")


# ── AI 추천 플레이리스트 (compose) ───────────────────────────────────────

def _parse_json(text):
    """LLM 응답에서 JSON 오브젝트 하나를 관대하게 추출 (코드펜스·잡설 허용)."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:].strip()
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                return None
    return None


def _compose(params: dict) -> dict:
    """AI 추천 플레이리스트 — theme(주제 자연어)로 경량 AI가 라이브러리에서 선곡해 저장.

    2단 하강(서재 탐색 절차의 음악판 — 전 곡 제목을 한 번에 안 읽음):
    ① 아티스트·폴더 개요만 보여주고 후보 무리를 고르게 함(세상 지식으로 판단)
    ② 후보 곡 목록(번호|아티스트|제목|앨범|폴더)에서 선곡·듣는 순서·이름까지.
    폴더명=사용자의 의미 단위라 모르는 곡의 힌트로 쓴다. 결과는 플레이리스트로 영속
    (플레이리스트 탭에도 등장) + items 로 즉시 연속재생.
    """
    theme = (params.get("theme") or "").strip()
    if not theme:
        return items([], success=False, message="theme(주제)을 주세요. 예: 비 오는 날 조용한 발라드")
    try:
        size = max(5, min(int(params.get("size") or 25), 60))
    except (TypeError, ValueError):
        size = 25
    c = _core()
    try:
        from consciousness_agent import lightweight_ai_call
    except Exception as e:  # 폰 등 경량 AI 부재 몸 — 정직 거절
        return items([], success=False, message=f"경량 AI 를 부를 수 없습니다: {e}")

    # 전 곡 브리프 — query_tracks 의 limit 캡(2000)을 우회해 전곡을 한 번에
    with c._conn() as conn:
        raw = [dict(r) for r in conn.execute(
            "SELECT path, artist, title, album, filename FROM tracks")]
    if not raw:
        return items([], message=_EMPTY_HINT)
    folders = c.list_folders()

    # ① 후보 무리 선별 — 아티스트·폴더 개요 (제목 4,800개가 아니라 이름 1,400여 개)
    from collections import Counter
    artist_n = Counter((t["artist"] or "").strip() for t in raw)
    artist_n.pop("", None)
    a_lines = "\n".join(f"- {a} ({n}곡)" for a, n in sorted(artist_n.items()))
    f_lines = "\n".join(f"- {f['name']} ({f['n']}곡)" for f in folders)
    sys_p = ("당신은 음악 큐레이터입니다. 세상 지식(가수·장르·시대·분위기)으로 판단하고, "
             "반드시 JSON 만 출력합니다.")
    p1 = (f"주제: {theme}\n\n[아티스트 목록]\n{a_lines}\n\n[폴더 목록]\n{f_lines}\n\n"
          "위는 내 음악 라이브러리 개요입니다. 주제에 어울리는 곡을 가졌을 법한 아티스트(최대 40)와 "
          "폴더(최대 12)를 고르세요. 표기는 목록의 문자열을 그대로 복사하세요(아티스트 필드가 지저분해 "
          "앨범명 같은 값도 있음 — 그래도 그대로). "
          '출력: {"artists": ["..."], "folders": ["..."]}')
    r1 = _parse_json(lightweight_ai_call(p1, system_prompt=sys_p, role="background"))

    sel_artists, sel_folder_paths = set(), []
    if isinstance(r1, dict):
        norm = {a.replace(" ", ""): a for a in artist_n}
        for w in (r1.get("artists") or []):
            hit = norm.get(str(w).strip().replace(" ", ""))
            if hit:
                sel_artists.add(hit)
        fmap = {f["name"]: f["path"] for f in folders}
        for w in (r1.get("folders") or []):
            p = fmap.get(str(w).strip())
            if p:
                sel_folder_paths.append(p)

    cands, seen = [], set()
    for t in raw:
        a = (t["artist"] or "").strip()
        in_f = any(t["path"].startswith(fp + os.sep) or t["path"] == fp
                   for fp in sel_folder_paths)
        if (a in sel_artists or in_f) and t["path"] not in seen:
            seen.add(t["path"])
            cands.append(t)
    if not cands:
        cands = list(raw)  # ①이 빗나가도 전곡 표본으로 계속 (침묵 실패 금지)
    # 캡 500: 도구 타임아웃 60초 안에 경량 LLM 2호출이 들어와야 한다 (800에서 58초 실측)
    if len(cands) > 500:
        cands = random.sample(cands, 500)

    # ② 선곡 — 번호 매긴 후보에서 고르고, 듣는 순서로 배열, 이름까지 짓게
    lines = []
    for i, t in enumerate(cands):
        rel = c._rel_folder(os.path.dirname(t["path"]))
        lines.append(f"{i}|{t['artist'] or ''}|{t['title'] or t['filename'] or ''}|{rel}")
    p2 = (f"주제: {theme}\n\n[후보 곡: 번호|아티스트|제목|폴더]\n" + "\n".join(lines) +
          f"\n\n주제에 가장 어울리는 {size}곡을 골라 듣기 좋은 흐름의 순서로 배열하세요. "
          "아는 곡은 세상 지식으로, 모르는 곡은 제목·아티스트·폴더명에서 유추하세요. "
          "짧고 감각 있는 플레이리스트 이름도 지으세요. "
          '출력: {"name": "이름", "picks": [번호, ...]}')
    r2 = _parse_json(lightweight_ai_call(p2, system_prompt=sys_p, role="background"))
    if not isinstance(r2, dict) or not r2.get("picks"):
        return items([], success=False, message="AI 선곡에 실패했습니다. 잠시 후 다시 시도해 주세요.")

    picks, picked_paths = [], set()
    for x in r2.get("picks") or []:
        try:
            i = int(x)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(cands) and cands[i]["path"] not in picked_paths:
            picked_paths.add(cands[i]["path"])
            picks.append(cands[i])
        if len(picks) >= size:
            break
    if len(picks) < 3:
        return items([], success=False, message="AI 가 고른 곡이 너무 적습니다. 주제를 조금 넓혀 보세요.")

    # 플레이리스트로 영속 (이름 충돌 시 숫자 붙임)
    name = (params.get("name") or "").strip() or (str(r2.get("name") or "")).strip() or f"AI: {theme[:24]}"
    pls = c.load_playlists()
    base, k = name, 2
    while c.find_playlist(pls, name):
        name = f"{base} {k}"
        k += 1
    from datetime import datetime
    pls.append({"name": name, "created_at": datetime.now().isoformat(timespec="seconds"),
                "tracks": [t["path"] for t in picks], "theme": theme, "by": "ai"})
    c.save_playlists(pls)

    order = {t["path"]: i for i, t in enumerate(picks)}
    qmarks = ",".join("?" * len(order))
    with c._conn() as conn:
        full = [c.track_row(r) for r in conn.execute(
            f"SELECT * FROM tracks WHERE path IN ({qmarks})", list(order))]
    full.sort(key=lambda t: order.get(t["path"], 9999))
    return items(full, name=name, count=len(full), theme=theme, success=True,
                 message=f"주제 '{theme}' — {len(full)}곡을 골라 플레이리스트 '{name}'로 저장했습니다.")


# ── 소스 폴더 · 스캔 ─────────────────────────────────────────────────────

def _sources(params: dict) -> dict:
    """보관함 탭 한 화면 — 소스 목록 + 라이브러리 통계 + 스캔 상태."""
    c = _core()
    st = c.stats()
    rows = [{"path": s["path"], "title": s["path"], "n": st["per_source"].get(s["path"], 0),
             "meta": f"{st['per_source'].get(s['path'], 0)}곡", "added_at": s.get("added_at", "")}
            for s in c.load_sources()]
    return items(rows, stats=st, scan={"label": c.scan_label(), **c.scan_state()},
                 message="" if rows else "등록된 음악 폴더가 없습니다. 폴더를 등록하면 스캔이 시작됩니다.")


def _add_source(params: dict) -> dict:
    c = _core()
    r = c.add_source(params.get("path") or "")
    if not r["ok"]:
        return items([], success=False, message=r["error"])
    c.start_scan([r["path"]])  # 등록 즉시 그 폴더만 백그라운드 스캔
    return items([], success=True,
                 message=f"폴더 등록 — 스캔을 시작했습니다: {r['path']} (보관함 탭에서 진행 상태 확인)")


def _remove_source(params: dict) -> dict:
    c = _core()
    r = c.remove_source(params.get("path") or "")
    if not r["ok"]:
        return items([], success=False, message=r["error"])
    return items([], success=True, message=f"폴더 제거 — 라이브러리에서 {r['removed']}곡을 내렸습니다.")


def _scan(params: dict) -> dict:
    c = _core()
    r = c.start_scan()
    if not r["ok"]:
        return items([], success=False, message=r["error"], scan=r.get("scan", {}))
    return items([], success=True, queued=True,
                 message=f"전체 스캔을 시작했습니다 ({len(r['roots'])}개 폴더, 백그라운드). 보관함 탭에서 진행 상태를 확인하세요.")


# ── 디스패치 (--check 가 AST 로 키 정확 비교) ────────────────────────────

_OP_DISPATCHERS = {
    "music_library_op": {
        "library": _library,
        "track": _track,
        "albums": _albums,
        "artists": _artists,
        "related": _related,
        "walk": _walk,
        "folders": _folders,
        "graph": _graph,
        "playlists": _playlists,
        "playlist": _playlist,
        "playlist_create": _playlist_create,
        "playlist_delete": _playlist_delete,
        "playlist_add": _playlist_add,
        "playlist_remove": _playlist_remove,
        "compose": _compose,
        "sources": _sources,
        "add_source": _add_source,
        "remove_source": _remove_source,
        "scan": _scan,
    }
}
_OP_DEFAULTS = {"music_library_op": "library"}


def execute(tool_input: dict, context):
    tool_name = context.tool_name
    try:
        if tool_name in _OP_DISPATCHERS:
            op = tool_input.get("op") or _OP_DEFAULTS.get(tool_name)
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if fn is None:
                return items([], success=False,
                             message=f"알 수 없는 op: {op} (가능: {', '.join(_OP_DISPATCHERS[tool_name])})")
            return fn(tool_input)
        return items([], success=False, message=f"알 수 없는 도구: {tool_name}")
    except Exception as e:
        return items([], success=False, message=f"music-player 오류: {e}")
